/**
 * CalibrationScreen — full-page modal shown BEFORE the procedure begins.
 *
 * Why: the ML pipeline needs a per-participant pupil baseline. Without an
 * explicit "rest" period, the first 120 s of streaming captures task work
 * (not rest), corrupting every subsequent PCPS value. This screen makes the
 * operator sit calmly looking at a fixation cross for the configured baseline
 * duration (default 120 s) while the backend accumulates pupil samples.
 *
 * Flow:
 *   1. Component mounts → POST /session/calibration_start
 *   2. Countdown timer ticks down from `baselineDurationS`
 *   3. When the timer hits 0 → POST /session/calibration_end and call
 *      props.onComplete(); the parent (SessionView) now starts the procedure
 *      from step 1.
 *   4. If the user cancels (rare) → props.onCancel().
 *
 * Visual: black background, large white fixation cross in the center,
 * prominent countdown + status message below.
 *
 * Bug-fixes vs. the first draft:
 *   - `onComplete` was being recreated on every parent re-render. The
 *     "step 3" effect had `onComplete` in its dep array, so every parent
 *     re-render during the `await streamingCalibrationEnd()` would re-fire
 *     the effect, calling the backend a second time and ending up in
 *     'error' state. → Now `onComplete` is held in a ref + a `endedRef`
 *     guard ensures end() runs exactly once.
 *   - The countdown only showed `MM:SS` of remaining time. Now it shows the
 *     full progress: a giant MM:SS countdown, an "X / Y seconds collected"
 *     line, and a progress bar.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  streamingCalibrationStart,
  streamingCalibrationEnd,
} from '../services/streamingApi';

const fmt = (s) => {
  const x = Math.max(0, Math.ceil(s));
  const m = Math.floor(x / 60);
  const r = x % 60;
  return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`;
};

const CalibrationScreen = ({
  streamId,
  baselineDurationS = 120,
  onComplete,
  onCancel,
}) => {
  const [phase, setPhase] = useState('starting'); // starting | counting | ending | done | error
  const [remaining, setRemaining] = useState(baselineDurationS);
  const [errorMessage, setErrorMessage] = useState('');

  // Refs so we don't re-trigger effects on parent re-renders.
  const startedRef = useRef(false);
  const endedRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  const onCancelRef = useRef(onCancel);
  useEffect(() => { onCompleteRef.current = onComplete; }, [onComplete]);
  useEffect(() => { onCancelRef.current = onCancel; }, [onCancel]);

  // Step 1 — start calibration on the backend exactly once.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    const begin = async () => {
      try {
        await streamingCalibrationStart(streamId);
        setPhase('counting');
      } catch (err) {
        console.error('[calibration_start]', err);
        setErrorMessage(err?.message || 'Failed to start calibration with the backend.');
        setPhase('error');
      }
    };
    begin();
  }, [streamId]);

  // Step 2 — countdown ticks once per second while in 'counting' phase.
  useEffect(() => {
    if (phase !== 'counting') return undefined;
    const interval = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearInterval(interval);
          setPhase('ending');
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [phase]);

  // Step 3 — end calibration on the backend, then signal parent (ONCE).
  useEffect(() => {
    if (phase !== 'ending') return;
    if (endedRef.current) return;
    endedRef.current = true;
    const end = async () => {
      try {
        const ack = await streamingCalibrationEnd(streamId);
        if (ack?.status === 'calibration_insufficient_samples') {
          setErrorMessage(
            ack.message ||
              'Calibration ended but no pupil data was received. Verify that ' +
              'Pupil Capture is running and the bridge is forwarding samples.'
          );
          setPhase('error');
          // Re-arm so a Restart can retry end() after a re-collection.
          endedRef.current = false;
          return;
        }
        setPhase('done');
        if (onCompleteRef.current) onCompleteRef.current();
      } catch (err) {
        console.error('[calibration_end]', err);
        setErrorMessage(err?.message || 'Failed to end calibration on the backend.');
        setPhase('error');
        endedRef.current = false;
      }
    };
    end();
  }, [phase, streamId]); // onComplete intentionally excluded — handled by ref

  const handleRestart = () => {
    setErrorMessage('');
    setRemaining(baselineDurationS);
    startedRef.current = false;
    endedRef.current = false;
    setPhase('starting');
  };

  const handleSkip = () => {
    // Operator explicitly skipping calibration → still signal parent so the
    // procedure proceeds. The model will run with a missing/poor baseline.
    if (onCancelRef.current) onCancelRef.current();
  };

  // Progress numbers (always available, even before counting starts).
  const elapsed = Math.max(0, baselineDurationS - remaining);
  const progressPct = Math.max(0, Math.min(100, (elapsed / baselineDurationS) * 100));

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black">
      {/* Fixation cross */}
      <div className="flex items-center justify-center" style={{ minHeight: '32vh' }}>
        <div
          aria-hidden="true"
          style={{
            color: 'white',
            fontWeight: 200,
            fontSize: 'clamp(120px, 18vw, 240px)',
            lineHeight: 1,
            userSelect: 'none',
          }}
        >
          +
        </div>
      </div>

      {/* Giant countdown */}
      {(phase === 'counting' || phase === 'starting' || phase === 'ending') && (
        <div className="text-white text-center" style={{ marginTop: 24 }}>
          <div
            style={{
              fontFamily: 'monospace',
              fontWeight: 700,
              fontSize: 'clamp(48px, 8vw, 96px)',
              lineHeight: 1,
              letterSpacing: '0.04em',
            }}
            aria-live="polite"
          >
            {fmt(remaining)}
          </div>
          <div className="mt-2 text-gray-300 font-mono text-sm">
            {elapsed} / {baselineDurationS} seconds collected
          </div>
          {/* Progress bar */}
          <div
            className="mx-auto mt-4 bg-gray-800 rounded-full overflow-hidden"
            style={{ width: 'min(80vw, 480px)', height: 6 }}
          >
            <div
              className="bg-blue-500 transition-all duration-200"
              style={{ width: `${progressPct}%`, height: '100%' }}
            />
          </div>
        </div>
      )}

      {/* Status text */}
      <div className="mt-8 text-center text-white" style={{ maxWidth: 560, padding: '0 16px' }}>
        {phase === 'starting' && (
          <>
            <p className="text-xl font-semibold mb-1">Calibration starting…</p>
            <p className="text-gray-300 text-sm">Connecting to the eye-tracking backend.</p>
          </>
        )}

        {phase === 'counting' && (
          <>
            <p className="text-lg mb-1">Please look at the cross and sit calmly.</p>
            <p className="text-gray-300 text-sm">
              We're measuring your resting pupil size before the procedure begins.
              Don't read, talk, or move — just breathe normally.
            </p>
          </>
        )}

        {phase === 'ending' && (
          <>
            <p className="text-xl font-semibold mb-1">Finalizing baseline…</p>
            <p className="text-gray-300 text-sm">Freezing the reference values.</p>
          </>
        )}

        {phase === 'done' && (
          <>
            <p className="text-2xl font-semibold mb-2 text-green-300">Calibration complete ✓</p>
            <p className="text-gray-300">Starting the procedure…</p>
          </>
        )}

        {phase === 'error' && (
          <div className="bg-red-900/50 border border-red-500 rounded-lg p-4">
            <p className="text-xl font-semibold mb-2 text-red-200">Calibration error</p>
            <p className="text-red-100 text-sm mb-4">{errorMessage}</p>
            <div className="flex justify-center gap-2">
              <button
                onClick={handleRestart}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-white text-sm font-medium"
              >
                Restart calibration
              </button>
              <button
                onClick={handleSkip}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white text-sm font-medium"
              >
                Continue without baseline
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CalibrationScreen;
