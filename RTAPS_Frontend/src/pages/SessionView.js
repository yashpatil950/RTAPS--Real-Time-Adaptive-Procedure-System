import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Expand, Clock, Lightbulb } from 'lucide-react';
import { getProcedureByTrain } from '../data/procedures';
import { appendCompletedSession } from '../data/analyticsStorage';
import { getStepFeedback } from '../data/stepFeedback';
import {
  ensureStoredStreamId,
  getStoredStreamId,
  isStreamingIntegrationEnabled,
  streamingSessionStart,
  streamingStepChange,
  streamingSessionEnd,
  subscribePredictions,
} from '../services/streamingApi';
import CalibrationScreen from '../components/CalibrationScreen';

// How long the operator sits at the fixation cross before the procedure starts.
// Must match Streaming_Backend `BASELINE_DURATION_S` (default 120 s) so the
// frontend countdown matches what the backend needs.
const CALIBRATION_DURATION_S = 120;

// Valid workload labels emitted by the backend smoother.
//
// Display rule (operator UI):
//   - Each step opens at "low" (no extra guidance shown).
//   - When the backend smoother reports "high" (which already required
//     3 s of model "high" in a row), the display flips to "high".
//   - Once a step has reached "high", the display STAYS at "high" for
//     the rest of that step — even if the model later drops back to
//     "low". This is intentional: the operator should not see guidance
//     appear and disappear within the same step. Sticky-within-step.
//   - On the next step (operator checks the box and the active step
//     advances), the display resets to "low" and the cycle repeats.
//
// The backend smoother is independent of this sticky behavior — it
// reports the *true* current level. The dashboard (/streaming) shows
// that raw smoothed level for ML inspection. Only this operator page
// applies the sticky-within-step rule.
const VALID_WORKLOAD_LEVELS = new Set(['low', 'medium', 'high']);

const SessionView = () => {
  const { procedureId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const trainNumber = parseInt(searchParams.get('train')) || 1; // Default to Train 1 if not provided
  
  const procedure = getProcedureByTrain(procedureId, trainNumber);
  
  // Redirect to dashboard if procedure not found
  useEffect(() => {
    if (!procedure) {
      navigate('/');
    }
  }, [procedure, navigate]);
  
  // Gates: calibration must complete before the procedure UI engages. If
  // streaming is disabled (no ML), calibration is skipped so the UI is
  // immediately usable for offline rehearsal.
  const streamingEnabled =
    typeof window !== 'undefined' && isStreamingIntegrationEnabled();
  const [calibrationComplete, setCalibrationComplete] = useState(
    !streamingEnabled
  );
  // Defer the procedure clock until AFTER calibration finishes — that way step
  // 1's elapsed time starts at 0, not at "120 s into the page mount".
  const [sessionStartTime, setSessionStartTime] = useState(null);
  const [stepStartTimes, setStepStartTimes] = useState({});
  const [stepTimes, setStepTimes] = useState({});
  const [completedSteps, setCompletedSteps] = useState(new Set());
  const [expandedSteps, setExpandedSteps] = useState(new Set());
  const [, setCurrentStepIndex] = useState(0);
  const [sessionEndTime, setSessionEndTime] = useState(null);
  const [isSessionComplete, setIsSessionComplete] = useState(false);
  const hasSavedAnalyticsRef = useRef(false);
  const [blockedHintSteps, setBlockedHintSteps] = useState(new Set());
  // devExtraSeconds is still added into the session-timer math so the legacy
  // "+10s (dev)" mechanism doesn't break for anyone still using it programmatically.
  // The setter is unused now that the +10s button was removed from the UI.
  // eslint-disable-next-line no-unused-vars
  const [devExtraSeconds, setDevExtraSeconds] = useState(0);
  const [devExtraAtEnd, setDevExtraAtEnd] = useState(0);

  // The workload-based feedback path is the only one the UI uses now. The
  // legacy time-threshold fallback (and its dev toggle) has been removed —
  // operator instructions are driven entirely by the model's smoothed
  // workload level. This flag is kept as a const so the few remaining
  // references read cleanly; it should not be turned off.
  const useWorkloadFeedback = true;
  
  // Per-step workload state from the streaming ML backend.
  // Format: { [stepId]: { current, reachedHigh, proba, decisionTime, rawLabel } }
  //   current      — latest smoothed label from the SSE stream (follows
  //                  the backend smoother exactly).
  //   reachedHigh  — sticky boolean: true once the step has ever shown
  //                  "high". Drives the operator UI: while reachedHigh
  //                  is true, the page keeps showing the "high"
  //                  guidance even if `current` later drops to "low".
  //                  Cleared on step transition because a fresh step
  //                  starts with no entry in this dict.
  const [stepWorkloadStates, setStepWorkloadStates] = useState({});
  const [latestPrediction, setLatestPrediction] = useState(null);
  const [streamingHookReady, setStreamingHookReady] = useState(false);

  useEffect(() => {
    if (!procedure || typeof window === 'undefined') {
      setStreamingHookReady(false);
      return undefined;
    }
    const enabled = isStreamingIntegrationEnabled();
    const sid = ensureStoredStreamId(procedure.id, trainNumber).trim();
    if (!enabled || !sid) {
      setStreamingHookReady(false);
      return undefined;
    }
    // Don't start the procedure session on the backend until calibration ends.
    // session/start anchors the procedure clock — if we POST it during
    // calibration, the first step gets counted from second 0 of the calibration
    // period instead of from when the operator actually started step 1.
    if (!calibrationComplete) {
      setStreamingHookReady(false);
      return undefined;
    }
    let cancelled = false;
    setStreamingHookReady(false);

    const run = async () => {
      try {
        const currentUser = JSON.parse(localStorage.getItem('currentParticipant') || '{}');
        const participantId =
          currentUser.role === 'admin' ? 'admin' : currentUser.id || currentUser.username || 'unknown';
        await streamingSessionStart({
          streamId: sid,
          procedureId: procedure.id,
          participantId: String(participantId),
          nStepsTotal: procedure.steps.length,
        });
        if (cancelled) return;

        await streamingStepChange({
          streamId: sid,
          stepNumber: procedure.steps[0]?.stepNumber ?? 1,
          stepId: procedure.steps[0]?.id,
        });
        if (!cancelled) setStreamingHookReady(true);
      } catch (err) {
        if (!cancelled) console.warn('[RTAPS streaming]', err.message || err);
      }
    };

    run();

    return () => {
      cancelled = true;
      setStreamingHookReady(false);
      streamingSessionEnd(sid).catch(() => {});
    };
  }, [procedure?.id, trainNumber, calibrationComplete]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!procedure || typeof window === 'undefined') return undefined;
    const enabled = isStreamingIntegrationEnabled();
    const sid = ensureStoredStreamId(procedure.id, trainNumber).trim();
    if (!enabled || !sid || !procedure?.steps?.length || !streamingHookReady) {
      return undefined;
    }
    const fi = procedure.steps.find((step) => !completedSteps.has(step.id));
    const stepNumber = fi ? fi.stepNumber : procedure.steps[procedure.steps.length - 1]?.stepNumber ?? 1;
    const stepId = fi ? fi.id : procedure.steps[procedure.steps.length - 1]?.id;
    streamingStepChange({ streamId: sid, stepNumber, stepId }).catch((err) => {
      console.warn('[RTAPS streaming step_change]', err.message || err);
    });
    return undefined;
  }, [procedure, completedSteps, streamingHookReady]); // eslint-disable-line react-hooks/exhaustive-deps

  const streamingBanner =
    typeof window !== 'undefined' && isStreamingIntegrationEnabled() ? getStoredStreamId().trim() : '';


  
  // Subscribe to live predictions from the streaming ML backend.
  // Each prediction carries (step_number, workload_label). We map it
  // back to the step on this page and store BOTH:
  //   - current     : the latest smoothed level from the backend
  //   - reachedHigh : a sticky-within-step flag that latches `true`
  //                   the first time this step shows "high".
  // The backend smoother already enforces the 3 s stability gate AND
  // forces the displayed level back to "low" at each step transition.
  // The reachedHigh latch lives on the frontend so we can keep the
  // "high" guidance pinned for the rest of a step — even if the model
  // later dips back to "low" — without polluting the backend's
  // smoother semantics (the /streaming dashboard still sees the true
  // smoothed level).
  useEffect(() => {
    if (!procedure || typeof window === 'undefined') return undefined;
    const enabled = isStreamingIntegrationEnabled();
    const sid = ensureStoredStreamId(procedure.id, trainNumber).trim();
    if (!enabled || !sid || !streamingHookReady) return undefined;

    const cleanup = subscribePredictions(
      sid,
      (data) => {
        if (!data || typeof data !== 'object') return;
        const label = data.workload_label;
        const stepNum = data.step_number;
        if (!label || !VALID_WORKLOAD_LEVELS.has(label) || stepNum == null) return;
        const step = procedure.steps.find((s) => s.stepNumber === stepNum);
        if (!step) return;

        setLatestPrediction(data);
        setStepWorkloadStates((prev) => {
          const cur =
            prev[step.id] || {
              current: 'low',
              reachedHigh: false,
              reachedHighAtMs: null,
              maxHighProba: 0,
              highCount: 0,
              predCount: 0,
            };
          const isHigh = label === 'high';
          // Latch on the first "high" for this step; never clear it
          // until the step ends (whereupon the entry is dropped because
          // a fresh step starts with no key in this dict). We also record
          // WHEN the latch first fired (reachedHighAtMs) and running
          // counts so the completed-session analytics record can report
          // whether the adaptation triggered, how far into the step, and
          // how strong/sustained the high-workload signal was.
          const reachedHigh = cur.reachedHigh || isHigh;
          const reachedHighAtMs = cur.reachedHighAtMs || (isHigh ? Date.now() : null);
          const pHigh =
            data.workload_proba && typeof data.workload_proba.high === 'number'
              ? data.workload_proba.high
              : null;
          return {
            ...prev,
            [step.id]: {
              current: label,
              reachedHigh,
              reachedHighAtMs,
              maxHighProba:
                pHigh != null ? Math.max(cur.maxHighProba || 0, pHigh) : cur.maxHighProba,
              highCount: (cur.highCount || 0) + (isHigh ? 1 : 0),
              predCount: (cur.predCount || 0) + 1,
              proba: data.workload_proba || null,
              decisionTime: data.decision_time || null,
              rawLabel: data.raw_workload_label || null,
            },
          };
        });
      },
      (err) => console.warn('[RTAPS streaming SSE]', err && (err.message || err))
    );

    return cleanup;
  }, [procedure, trainNumber, streamingHookReady]);

  // Initialize step start times — only AFTER calibration completes, so the
  // first step's elapsed time starts at 0 (not at "120 s into the page mount").
  useEffect(() => {
    if (!procedure || !procedure.steps || procedure.steps.length === 0) return;
    if (!calibrationComplete) return;
    const now = new Date();
    setSessionStartTime(now);
    setStepStartTimes({ [procedure.steps[0].id]: now });
  }, [procedure, calibrationComplete]);

  useEffect(() => {
    if (!procedure || !procedure.steps) return;
    
    const interval = setInterval(() => {
      const now = new Date();
      setStepTimes(prev => {
        const updated = { ...prev }; // preserve completed steps' final times
        procedure.steps.forEach(step => {
          // Only track time for steps that have started and are not completed
          if (!completedSteps.has(step.id) && stepStartTimes[step.id]) {
            const timeSpent = Math.floor((now - stepStartTimes[step.id]) / 1000);
            updated[step.id] = timeSpent;
            // Show sub-steps when threshold is exceeded
            if (timeSpent >= step.timeThreshold && !expandedSteps.has(step.id)) {
              setExpandedSteps(prevExpanded => new Set([...prevExpanded, step.id]));
            }
          }
        });
        return updated;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [procedure, completedSteps, stepStartTimes, expandedSteps]);

  const handleStepComplete = (stepId) => {
    // Freeze final time for this step
    setStepTimes(prev => ({
      ...prev,
      [stepId]: stepStartTimes[stepId] ? Math.floor((new Date() - stepStartTimes[stepId]) / 1000) : (prev[stepId] || 0)
    }));

    setCompletedSteps(prev => {
      const newCompletedSteps = new Set([...prev, stepId]);
      
      // Check if all steps are completed
      if (procedure && procedure.steps && newCompletedSteps.size === procedure.steps.length) {
        const end = new Date();
        setSessionEndTime(end);
        setIsSessionComplete(true);
        // Lock in any dev extra seconds into the final total
        setDevExtraAtEnd(devExtraSeconds);

        // Persist analytics summary once (guard against dev double-invocation)
        if (!hasSavedAnalyticsRef.current) {
          hasSavedAnalyticsRef.current = true;
          try {
            const totalTimeSec = sessionStartTime == null
              ? 0
              : Math.floor((end - sessionStartTime) / 1000) + devExtraSeconds;
            const stepSummaries = procedure.steps.map((s) => {
              const wl = stepWorkloadStates[s.id] || {};
              const startMs = stepStartTimes[s.id] ? stepStartTimes[s.id].getTime() : null;
              // Seconds from when the operator entered the step to when the
              // model first reported "high" (i.e. when guidance was revealed).
              const timeToAdaptationSec =
                wl.reachedHighAtMs && startMs
                  ? Math.max(0, Math.round((wl.reachedHighAtMs - startMs) / 1000))
                  : null;
              return {
                stepId: s.id,
                stepNumber: s.stepNumber,
                stepTitle: s.title || null,
                timeSpentSec: (stepTimes[s.id] || 0),
                // Legacy time-threshold proxy — kept for backward compatibility
                // with sessions recorded before workload-driven adaptation.
                exceededThreshold: (stepTimes[s.id] || 0) > s.timeThreshold,
                subStepsShown: (stepTimes[s.id] || 0) > s.timeThreshold && s.subSteps && s.subSteps.length > 0,
                // ML workload-driven adaptation — what the operator actually saw.
                workloadReachedHigh: !!wl.reachedHigh,
                adaptationShown: !!wl.reachedHigh,
                finalWorkloadLevel: wl.current || (wl.reachedHigh ? 'high' : 'low'),
                timeToAdaptationSec,
                maxHighProba:
                  typeof wl.maxHighProba === 'number' ? Number(wl.maxHighProba.toFixed(3)) : null,
                highPredictionCount: wl.highCount || 0,
                predictionCount: wl.predCount || 0,
              };
            });
            const stepsWithAdaptation = stepSummaries.filter((x) => x.adaptationShown).length;
            const stepsWithPredictions = stepSummaries.filter((x) => x.predictionCount > 0).length;
            // Get current user data
            const currentUser = JSON.parse(localStorage.getItem('currentParticipant') || '{}');
            
            // Handle admin sessions
            const participantId = currentUser.role === 'admin' ? 'admin' : (currentUser.id || currentUser.username);
            const participantUsername = currentUser.role === 'admin' ? 'admin' : currentUser.username;
            
            // Save session to API (async, non-blocking)
            appendCompletedSession({
              procedureId: procedure.id,
              procedureName: procedure.name,
              participantId,
              participantUsername,
              completedAtMs: Date.now(),
              totalTimeSec,
              steps: stepSummaries,
              trainNumber: trainNumber,
              metadata: {
                // Session-level adaptation summary for the Analytics page.
                adaptationMode: streamingEnabled ? 'workload' : 'time',
                stepsWithAdaptation,
                stepsWithPredictions,
                totalSteps: stepSummaries.length,
              },
            }).catch(error => {
              console.error('Failed to save session to API:', error);
            });
          } catch (_) {
            // non-blocking
          }
        }
      }
      
      return newCompletedSteps;
    });
    
    // Find the current step index and start the next step's timer
    const currentIndex = procedure.steps.findIndex(step => step.id === stepId);
    if (currentIndex !== -1 && currentIndex < procedure.steps.length - 1) {
      const nextStep = procedure.steps[currentIndex + 1];
      setStepStartTimes(prev => ({
        ...prev,
        [nextStep.id]: new Date()
      }));
      setCurrentStepIndex(currentIndex + 1);
    }
  };

  // Resolve the workload level to display for a given step.
  //
  //   1. No prediction yet for this step (warm-up, streaming disabled,
  //      or operator just arrived on the step) → "low". The operator
  //      sees the clean view first.
  //   2. Step has reached "high" at any point (reachedHigh latch is set)
  //      → "high". This is the sticky-within-step rule: once guidance
  //      has been shown, it stays for the rest of the step. The latch
  //      is cleared automatically when the operator advances to the
  //      next step (the new step has no entry in stepWorkloadStates).
  //   3. Otherwise → the live `current` from the backend smoother
  //      (which is "low" until 3 s of model "high" arrives).
  const getStepDisplayLevel = (step) => {
    const wl = stepWorkloadStates[step.id];
    if (!wl) return 'low';
    if (wl.reachedHigh) return 'high';
    return wl.current || 'low';
  };

  const formatTime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    } else {
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
  };

  if (!procedure) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Procedure not found</h1>
          <button
            onClick={() => navigate('/')}
            className="text-blue-600 hover:text-blue-700"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Show the calibration overlay until the operator has sat through the
  // baseline period. Skips entirely if streaming integration is disabled.
  const showCalibration = streamingEnabled && !calibrationComplete;
  const streamIdForCalibration = streamingEnabled
    ? ensureStoredStreamId(procedure.id, trainNumber).trim()
    : '';

  return (
    <div className="space-y-6">
      {showCalibration && streamIdForCalibration && (
        <CalibrationScreen
          streamId={streamIdForCalibration}
          baselineDurationS={CALIBRATION_DURATION_S}
          onComplete={() => setCalibrationComplete(true)}
          onCancel={() => setCalibrationComplete(true)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/')}
          className="tablet-button bg-gray-100 text-gray-700 hover:bg-gray-200"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Dashboard
        </button>
        
        <div className="text-right">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            {procedure.name}
          </h1>
          <p className="text-gray-600">
            {procedure.description}
          </p>
          <p className="text-sm text-gray-500 mt-1">
            Train {trainNumber}
          </p>
        </div>
      </div>

      {/* Session Timer */}
      <div className="tablet-card text-center">
        {streamingBanner ? (
          <div className="mb-4 rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-sm text-sky-900 flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">
              Streaming ML: {latestPrediction ? 'live' : 'active'}
              {latestPrediction && (
                <span className="ml-2 px-2 py-0.5 rounded bg-white text-xs font-semibold uppercase border border-sky-300">
                  {latestPrediction.workload_label}
                </span>
              )}
            </span>
            <span className="font-mono text-xs text-sky-800">
              stream_id <span className="font-semibold">{streamingBanner}</span>
              {' · '}
              backend sync {streamingHookReady ? 'ready' : 'connecting…'}
              {latestPrediction && (
                <>
                  {' · '}step {latestPrediction.step_number}
                </>
              )}
            </span>
          </div>
        ) : null}
        <div className={`text-4xl font-bold mb-2 ${isSessionComplete ? 'text-green-600' : 'text-blue-600'}`}>
          {sessionStartTime == null
            ? formatTime(0)
            : isSessionComplete
              ? formatTime(Math.floor((sessionEndTime - sessionStartTime) / 1000) + devExtraAtEnd)
              : formatTime(Math.floor((new Date() - sessionStartTime) / 1000) + devExtraSeconds)
          }
        </div>
        <div className="text-gray-600">
          {isSessionComplete ? 'Total Session Time' : 'Session Elapsed Time'}
        </div>
        {isSessionComplete && (
          <div className="mt-2 text-sm text-green-600 font-medium">
            🎉 All steps completed!
          </div>
        )}
      </div>

      {/* Procedure Steps with Adaptive Feedback */}
      <div className="tablet-card">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Procedure Steps</h3>
        <div className="space-y-4">
          {(() => {
            const firstIncompleteIndex = procedure.steps.findIndex(s => !completedSteps.has(s.id));
            return procedure.steps.map((step, index) => {
              // (timeSpent was previously surfaced in the per-step right column
              // — that whole panel was removed to declutter the operator screen.)
              const isCompleted = completedSteps.has(step.id);
              const isActiveStep = !isCompleted && (firstIncompleteIndex === -1 ? false : index === firstIncompleteIndex);
              const isDisabled = !isCompleted && !isActiveStep;

              return (
              <div key={step.id} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    {/* Checkbox for step completion */}
                    <div className="flex items-center justify-center w-8 h-8 bg-blue-100 border-2 border-blue-500 rounded">
                      <input
                        type="checkbox"
                        checked={isCompleted}
                        onChange={(e) => {
                          if (isDisabled) {
                            setBlockedHintSteps(prev => new Set([...prev, step.id]));
                            return;
                          }
                          if (e.target.checked) {
                            handleStepComplete(step.id);
                            setBlockedHintSteps(prev => {
                              const next = new Set(prev);
                              next.delete(step.id);
                              return next;
                            });
                          }
                        }}
                        className={`w-6 h-6 text-blue-600 bg-white border-2 border-gray-300 rounded focus:ring-blue-500 focus:ring-2 cursor-pointer hover:border-blue-400 ${isDisabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                        style={{ minWidth: '24px', minHeight: '24px' }}
                      />
                    </div>
                    
                    <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
                      <span className="text-blue-600 font-semibold">{index + 1}</span>
                    </div>
                    
                    <div>
                      <h4 className="text-lg font-semibold text-gray-900">Step {step.stepNumber}: {step.title}</h4>
                      <p className="text-gray-600">{step.description}</p>
                      {!isCompleted && blockedHintSteps.has(step.id) && (
                        <p className="text-xs text-gray-500">Finish the current step to continue.</p>
                      )}
                    </div>
                  </div>
                  
                  {/* Removed: the per-step workload metrics panel (Current/
                      Highest/probabilities/time-on-step) that used to sit
                      in the upper-right of each step card. Operators don't
                      need to see those details — they're a distraction.
                      Trainers and admins can still inspect them on the
                      Live ML dashboard (/streaming). */}
                </div>
                
                {step.instructions && step.instructions.trim() !== '' && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
                    <h4 className="font-semibold text-blue-900 mb-1">Instructions:</h4>
                    <p className="text-blue-800 text-sm">{step.instructions}</p>
                  </div>
                )}

                {/*
                 * Workload-based instructions. Display level is resolved
                 * by getStepDisplayLevel() above:
                 *   - low    → no extra block (clean base instructions only)
                 *   - medium → key points (v4 is 2-class so dead code, kept fwd-compat)
                 *   - high   → key points AND a detailed why/what/how block
                 *
                 * Behavior:
                 *  - The step opens at "low" and only flips to "high"
                 *    after the backend smoother reports 3 consecutive
                 *    seconds of model "high".
                 *  - Once a step has reached "high", the display stays
                 *    at "high" for the rest of that step — even if the
                 *    model later drops back to "low". (Operators should
                 *    not see guidance pop in and out within one step.)
                 *  - On the next step, the latch is cleared and the
                 *    "low → 3 s of high → high" cycle restarts.
                 */}
                {useWorkloadFeedback && (() => {
                  // Only show guidance for the active step
                  if (!isActiveStep) return null;

                  // Use the current smoothed level directly — no manual
                  // override, no client-side stickiness. Operator instructions
                  // are driven entirely by the backend smoother.
                  const displayLevel = getStepDisplayLevel(step);
                  if (displayLevel === 'low') return null;

                  const mediumFb = getStepFeedback(procedure.id, step.stepNumber, 'medium');
                  const highFb =
                    displayLevel === 'high'
                      ? getStepFeedback(procedure.id, step.stepNumber, 'high')
                      : null;
                  if (!mediumFb && !highFb) return null;

                  return (
                    <div className="mt-4 space-y-3">
                      {/* Header strip — labels the type of adaptive guidance
                          being shown. Driven entirely by the ML model; no
                          manual override. */}
                      <div className="flex items-center text-xs text-gray-600">
                        <Lightbulb className="w-4 h-4 mr-2 text-yellow-600" />
                        <span className="font-medium">
                          Adaptive guidance:&nbsp;
                          {displayLevel === 'high'
                            ? 'Detailed (Medium + High)'
                            : 'Additional (Medium)'}
                        </span>
                      </div>

                      {/* Medium key points — shown for medium AND high.
                          With v4 (2-class) the model never emits "medium",
                          so this branch only fires when displayLevel === 'high'. */}
                      {mediumFb && (
                        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                          <div className="flex items-center text-yellow-800 font-medium mb-2">
                            <Lightbulb className="w-4 h-4 mr-2" />
                            <span>Additional Guidance</span>
                          </div>
                          <p className="text-sm font-semibold text-yellow-900 mb-2">Key Points:</p>
                          <ul className="list-disc list-inside space-y-1 text-sm text-yellow-800">
                            {mediumFb.content.map((point, idx) => (
                              <li key={idx}>{point}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* High block — only when displayLevel is "high". */}
                      {highFb && highFb.content && (
                        <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
                          <div className="flex items-center text-orange-800 font-medium mb-2">
                            <Lightbulb className="w-4 h-4 mr-2" />
                            <span>Detailed Explanation</span>
                          </div>
                          <div className="space-y-3">
                            <div>
                              <p className="text-sm font-semibold text-orange-900 mb-1">Why:</p>
                              <ul className="list-disc list-inside space-y-1 text-sm text-orange-800">
                                {highFb.content.why.map((point, idx) => (
                                  <li key={idx}>{point}</li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-orange-900 mb-1">What:</p>
                              <ul className="list-disc list-inside space-y-1 text-sm text-orange-800">
                                {highFb.content.what.map((point, idx) => (
                                  <li key={idx}>{point}</li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-orange-900 mb-1">How:</p>
                              <ul className="list-disc list-inside space-y-1 text-sm text-orange-800">
                                {highFb.content.how.map((point, idx) => (
                                  <li key={idx}>{point}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            );
          });
          })()}
        </div>
      </div>

      {/* Progress Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="tablet-card text-center">
          <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <CheckCircle className="w-6 h-6 text-blue-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">
            {completedSteps.size} / {procedure.steps.length}
          </h3>
          <p className="text-gray-600">Steps Completed</p>
        </div>
        
        <div className="tablet-card text-center">
          <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            {useWorkloadFeedback ? (
              <Lightbulb className="w-6 h-6 text-purple-600" />
            ) : (
              <Expand className="w-6 h-6 text-purple-600" />
            )}
          </div>
          <h3 className="text-lg font-semibold text-gray-900">
            {useWorkloadFeedback
              ? procedure.steps.filter((s) => {
                  const lvl = getStepDisplayLevel(s);
                  return lvl !== 'low';
                }).length
              : expandedSteps.size}
          </h3>
          <p className="text-gray-600">
            {useWorkloadFeedback ? 'Steps with Feedback' : 'Steps with Sub-tasks'}
          </p>
        </div>
        
        <div className="tablet-card text-center">
          <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <Clock className="w-6 h-6 text-green-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">
            {sessionStartTime == null
              ? formatTime(0)
              : isSessionComplete
                ? formatTime(Math.floor((sessionEndTime - sessionStartTime) / 1000))
                : formatTime(Math.floor((new Date() - sessionStartTime) / 1000))
            }
          </h3>
          <p className="text-gray-600">
            {isSessionComplete ? 'Total Time' : 'Elapsed Time'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default SessionView;
