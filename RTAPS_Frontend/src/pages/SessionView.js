import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Expand, Clock, Lightbulb } from 'lucide-react';
import { getProcedureByTrain } from '../data/procedures';
import { appendCompletedSession } from '../data/analyticsStorage';
import { getStepFeedback, getWorkloadLevel } from '../data/stepFeedback';
import {
  getStoredStreamId,
  isStreamingIntegrationEnabled,
  streamingSessionStart,
  streamingStepChange,
  streamingSessionEnd,
} from '../services/streamingApi';

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
  
  const [sessionStartTime] = useState(new Date());
  const [stepStartTimes, setStepStartTimes] = useState({});
  const [stepTimes, setStepTimes] = useState({});
  const [completedSteps, setCompletedSteps] = useState(new Set());
  const [expandedSteps, setExpandedSteps] = useState(new Set());
  const [, setCurrentStepIndex] = useState(0);
  const [sessionEndTime, setSessionEndTime] = useState(null);
  const [isSessionComplete, setIsSessionComplete] = useState(false);
  const hasSavedAnalyticsRef = useRef(false);
  const [devMode, setDevMode] = useState(() => {
    try {
      return localStorage.getItem('rtaps_dev_mode') === '1';
    } catch (_) { return false; }
  });
  const [blockedHintSteps, setBlockedHintSteps] = useState(new Set());
  const [devExtraSeconds, setDevExtraSeconds] = useState(0);
  const [devExtraAtEnd, setDevExtraAtEnd] = useState(0);
  
  // Feature flag: Use workload-based feedback (new) vs time-threshold (old)
  const [useWorkloadFeedback, setUseWorkloadFeedback] = useState(() => {
    try {
      return localStorage.getItem('rtaps_use_workload_feedback') !== '0'; // Default to true (new system)
    } catch (_) { return true; }
  });
  
  // Generate random workload probabilities for each step (for testing)
  // In production, this would come from the advanced model
  const [stepWorkloadProbabilities, setStepWorkloadProbabilities] = useState({});
  const [streamingHookReady, setStreamingHookReady] = useState(false);

  useEffect(() => {
    const enabled = typeof window !== 'undefined' && isStreamingIntegrationEnabled();
    const sid = typeof window !== 'undefined' ? getStoredStreamId().trim() : '';
    if (!enabled || !sid || !procedure) {
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
  }, [procedure?.id, trainNumber]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const enabled = typeof window !== 'undefined' && isStreamingIntegrationEnabled();
    const sid = typeof window !== 'undefined' ? getStoredStreamId().trim() : '';
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
  }, [procedure, completedSteps, streamingHookReady]);

  const streamingBanner =
    typeof window !== 'undefined' && isStreamingIntegrationEnabled() ? getStoredStreamId().trim() : '';


  // Developer-controlled explanation detail preference
  const [explanationLevel, setExplanationLevel] = useState(() => {
    try {
      const stored = localStorage.getItem('rtaps_explanation_level');
      return stored === 'low' || stored === 'high' ? stored : 'medium';
    } catch (_) {
      return 'medium';
    }
  });
  
  // Initialize random workload probabilities for each step
  useEffect(() => {
    if (procedure && procedure.steps) {
      const probabilities = {};
      procedure.steps.forEach(step => {
        // Generate random probability between 0 and 1 for testing
        probabilities[step.id] = Math.random();
      });
      setStepWorkloadProbabilities(probabilities);
    }
  }, [procedure]);

  // Initialize step start times - only start the first step
  useEffect(() => {
    if (procedure && procedure.steps && procedure.steps.length > 0) {
      const initialTimes = {};
      // Only start timer for the first step
      initialTimes[procedure.steps[0].id] = new Date();
      setStepStartTimes(initialTimes);
    }
  }, [procedure]);

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
            const totalTimeSec = Math.floor((end - sessionStartTime) / 1000) + devExtraSeconds;
            const stepSummaries = procedure.steps.map((s) => ({
              stepId: s.id,
              stepNumber: s.stepNumber,
              timeSpentSec: (stepTimes[s.id] || 0),
              exceededThreshold: (stepTimes[s.id] || 0) > s.timeThreshold,
              subStepsShown: (stepTimes[s.id] || 0) > s.timeThreshold && s.subSteps && s.subSteps.length > 0,
            }));
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

  return (
    <div className="space-y-6">
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
            <span className="font-medium">Streaming ML: active</span>
            <span className="font-mono text-xs text-sky-800">
              stream_id <span className="font-semibold">{streamingBanner}</span>
              {' · '}
              backend sync {streamingHookReady ? 'ready' : 'connecting…'}
            </span>
          </div>
        ) : null}
        <div className="flex items-center justify-between mb-2">
          <div className="text-left">
            <div className="space-y-2">
              <label className="inline-flex items-center space-x-2 text-sm text-gray-600 cursor-pointer">
                <input
                  type="checkbox"
                  checked={devMode}
                  onChange={(e) => {
                    const v = e.target.checked;
                    setDevMode(v);
                    try { localStorage.setItem('rtaps_dev_mode', v ? '1' : '0'); } catch(_){}
                  }}
                />
                <span>Developer mode</span>
              </label>
              {devMode && (
                <label className="inline-flex items-center space-x-2 text-sm text-gray-600 cursor-pointer block">
                  <input
                    type="checkbox"
                    checked={useWorkloadFeedback}
                    onChange={(e) => {
                      const v = e.target.checked;
                      setUseWorkloadFeedback(v);
                      try { localStorage.setItem('rtaps_use_workload_feedback', v ? '1' : '0'); } catch(_){}
                    }}
                  />
                  <span>Use Workload Feedback (New System)</span>
                </label>
              )}
            </div>
          </div>
          <div></div>
        </div>
        <div className={`text-4xl font-bold mb-2 ${isSessionComplete ? 'text-green-600' : 'text-blue-600'}`}>
          {isSessionComplete 
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
              const timeSpent = stepTimes[step.id] || 0;
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
                  
                  <div className="text-right">
                    {/* Clean interface - no technical details shown to user */}
                    {devMode && (
                      <div className="text-xs text-gray-500 text-right">
                        {!useWorkloadFeedback && <div>Target: {step.timeThreshold}s</div>}
                        {useWorkloadFeedback && (
                          <div>
                            Workload: {(stepWorkloadProbabilities[step.id] * 100).toFixed(1)}%
                            <button
                              onClick={() => {
                                // Generate new random workload probability
                                setStepWorkloadProbabilities(prev => ({
                                  ...prev,
                                  [step.id]: Math.random()
                                }));
                              }}
                              className="ml-2 px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded border text-gray-700"
                            >
                              New Random
                            </button>
                          </div>
                        )}
                        <div className="mt-1 flex items-center justify-end space-x-2">
                          <span className="text-gray-500">{isActiveStep ? `Time on this step: ${formatTime(timeSpent)}` : ''}</span>
                          {isActiveStep && !useWorkloadFeedback && (
                            <button
                              onClick={() => {
                                // Add +10s to active step by shifting its start time back 10s
                                setStepStartTimes(prev => {
                                  const currentStart = prev[step.id] || new Date();
                                  const shifted = new Date(currentStart.getTime() - 10000);
                                  return { ...prev, [step.id]: shifted };
                                });
                                // Immediately reflect UI and sub-step state
                                setStepTimes(prev => {
                                  const current = prev[step.id] || 0;
                                  const next = current + 10;
                                  const newTimes = { ...prev, [step.id]: next };
                                  if (next >= step.timeThreshold && !expandedSteps.has(step.id)) {
                                    setExpandedSteps(prevExp => new Set([...prevExp, step.id]));
                                  }
                                  return newTimes;
                                });
                                // Update session timer in dev mode so total reflects additions
                                setDevExtraSeconds(prev => prev + 10);
                              }}
                              className="px-2 py-1 bg-gray-100 hover:bg-gray-200 rounded border text-gray-700"
                            >
                              +10s (dev)
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                
                {step.instructions && step.instructions.trim() !== '' && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
                    <h4 className="font-semibold text-blue-900 mb-1">Instructions:</h4>
                    <p className="text-blue-800 text-sm">{step.instructions}</p>
                  </div>
                )}

                {/* NEW: Workload-based feedback system with developer-controlled detail */}
                {useWorkloadFeedback && (() => {
                  const workloadProb = stepWorkloadProbabilities[step.id] || 0;
                  const workloadLevel = getWorkloadLevel(workloadProb);

                  // Only show guidance for the active step
                  if (!isActiveStep) {
                    return null;
                  }

                  let feedback = null;
                  let effectiveDetailLevel = null;

                  if (devMode) {
                    // In dev mode, always show guidance for active step.
                    // Explanation level controls amount/detail, not visibility.
                    effectiveDetailLevel = explanationLevel === 'high' ? 'high' : 'medium';
                    feedback = getStepFeedback(procedure.id, step.stepNumber, effectiveDetailLevel);

                    // Fallback: if high detail not defined, use medium when available
                    if (!feedback && effectiveDetailLevel === 'high') {
                      effectiveDetailLevel = 'medium';
                      feedback = getStepFeedback(procedure.id, step.stepNumber, 'medium');
                    }
                  } else {
                    // For end users, keep workload-driven behavior
                    if (workloadLevel === 'low') {
                      return null;
                    }
                    effectiveDetailLevel = workloadLevel === 'high' ? 'high' : 'medium';
                    feedback = getStepFeedback(procedure.id, step.stepNumber, effectiveDetailLevel);
                  }

                  if (!feedback) {
                    return null;
                  }

                  const isHighDetail = feedback.type === 'high';
                  const detailLabel = devMode
                    ? (explanationLevel === 'low'
                      ? 'Low'
                      : explanationLevel === 'high'
                        ? 'High'
                        : 'Medium')
                    : (isHighDetail ? 'High' : 'Medium');

                  return (
                    <div className="mt-4">
                      <div
                        className={`border rounded-lg p-3 mb-3 ${
                          isHighDetail
                            ? 'bg-orange-50 border-orange-200'
                            : 'bg-yellow-50 border-yellow-200'
                        }`}
                      >
                        <div
                          className={`flex items-center justify-between font-medium mb-2 ${
                            isHighDetail ? 'text-orange-800' : 'text-yellow-800'
                          }`}
                        >
                          <div className="flex items-center">
                            <Lightbulb className="w-4 h-4 mr-2" />
                            <span>
                              {isHighDetail
                                ? 'Detailed Explanation Available'
                                : 'Additional Guidance Available'}
                            </span>
                            {devMode && (
                              <span className="ml-2 text-xs opacity-75">
                                (Workload: {(workloadProb * 100).toFixed(1)}%)
                              </span>
                            )}
                          </div>
                          <div className="ml-4 text-xs text-gray-600">
                            Detail: {detailLabel}
                          </div>
                        </div>

                        {devMode && (
                          <div className="mb-3 flex items-center justify-end text-xs text-gray-600">
                            <span className="mr-2">Explanation detail</span>
                            <div className="inline-flex rounded-md border border-gray-300 bg-white overflow-hidden">
                              {['low', 'medium', 'high'].map((level) => (
                                <button
                                  key={level}
                                  type="button"
                                  onClick={() => {
                                    setExplanationLevel(level);
                                    try {
                                      localStorage.setItem('rtaps_explanation_level', level);
                                    } catch (_) {}
                                  }}
                                  className={`px-2 py-1 font-medium text-xs ${
                                    explanationLevel === level
                                      ? 'bg-blue-600 text-white'
                                      : 'text-gray-700 hover:bg-gray-50'
                                  }`}
                                >
                                  {level.charAt(0).toUpperCase() + level.slice(1)}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {feedback.type === 'medium' && (
                          <div className="space-y-1">
                            <p className="text-sm font-semibold text-yellow-900 mb-2">Key Points:</p>
                            <ul className="list-disc list-inside space-y-1 text-sm text-yellow-800">
                              {(devMode && explanationLevel === 'low'
                                ? feedback.content.slice(0, 1)
                                : feedback.content
                              ).map((point, idx) => (
                                <li key={idx}>{point}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        
                        {feedback.type === 'high' && feedback.content && (
                          <div className="space-y-3">
                            <div>
                              <p className="text-sm font-semibold text-orange-900 mb-1">Why:</p>
                              <ul className="list-disc list-inside space-y-1 text-sm text-orange-800">
                                {feedback.content.why.map((point, idx) => (
                                  <li key={idx}>{point}</li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-orange-900 mb-1">What:</p>
                              <ul className="list-disc list-inside space-y-1 text-sm text-orange-800">
                                {feedback.content.what.map((point, idx) => (
                                  <li key={idx}>{point}</li>
                                ))}
                              </ul>
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-orange-900 mb-1">How:</p>
                              <ul className="list-disc list-inside space-y-1 text-sm text-orange-800">
                                {feedback.content.how.map((point, idx) => (
                                  <li key={idx}>{point}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()}

                {/* OLD: Time-threshold based sub-steps (legacy system) */}
                {!useWorkloadFeedback && timeSpent > step.timeThreshold && step.subSteps.length > 0 && (
                  <div className="mt-4">
                    <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 mb-3">
                      <div className="flex items-center text-purple-800 font-medium">
                        <Expand className="w-4 h-4 mr-2" />
                        <span>Additional guidance is now available to help you complete this step</span>
                      </div>
                    </div>
                    
                    <div className="ml-8 space-y-3">
                      {step.subSteps.map((subStep, subIndex) => (
                        <div key={subStep.id} className="bg-gray-50 rounded-lg p-3 border-l-4 border-purple-200">
                          <div className="flex items-start justify-between">
                            <div className="flex items-center space-x-2">
                              <div className="w-6 h-6 bg-purple-100 rounded-full flex items-center justify-center">
                                <span className="text-purple-600 text-xs font-semibold">
                                  {index + 1}.{subIndex + 1}
                                </span>
                              </div>
                              <div>
                                <h5 className="font-medium text-gray-900">{subStep.title}</h5>
                                <p className="text-gray-600 text-sm">{subStep.description}</p>
                              </div>
                            </div>
                          </div>
                          
                          {subStep.instructions && subStep.instructions.trim() !== '' && (
                            <div className="mt-2 text-sm text-gray-600">
                              <strong>Instructions:</strong> {subStep.instructions}
                            </div>
                          )}

                          {subStep.imageUrl && (
                            <div className="mt-3">
                              <img
                                src={subStep.imageUrl}
                                alt={subStep.title}
                                className="w-full max-w-md rounded border border-gray-200"
                              />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
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
              ? Object.values(stepWorkloadProbabilities).filter((prob, idx) => {
                  const step = procedure.steps[idx];
                  return step && getWorkloadLevel(prob) !== 'low';
                }).length
              : expandedSteps.size
            }
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
            {isSessionComplete 
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
