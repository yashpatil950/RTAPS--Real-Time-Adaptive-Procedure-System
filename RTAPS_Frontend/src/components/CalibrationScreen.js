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
 * countdown + status message below. No interactive elements during the
 * count — looking elsewhere would corrupt the baseline.
 */
import React, { useEffect, useRef, useState } from 'react';
import {
  streamingCalibrationStart,
  streamingCalibrationEnd,
} from '../services/streamingApi';

const FormatSeconds = ({ seconds }) => {
  const s = Math.max(0, Math.ceil(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return (
    <span className="font-mono">
      {m.toString().padStart(2, '0')}:{r.toString().padStart(2, '0')}
    </span>
  );
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
  const startedRef = useRef(false);

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

  // Step 2 — countdown.
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

  // Step 3 — end calibration on the backend, then signal parent.
  useEffect(() => {
    if (phase !== 'ending') return;
    const end = async () => {
      try {
        const ack = await streamingCalibrationEnd(streamId);
        if (ack?.status === 'calibration_insufficient_samples') {
          setErrorMessage(
            ack.message ||
              'Not enough pupil data was collected. Restart the calibration.'
          );
          setPhase('error');
          return;
        }
        setPhase('done');
        if (onComplete) onComplete();
      } catch (err) {
        console.error('[calibration_end]', err);
        setErrorMessage(err?.message || 'Failed to end calibration.');
        setPhase('error');
      }
    };
    end();
  }, [phase, streamId, onComplete]);

  const handleRestart = () => {
    setErrorMessage('');
    setRemaining(baselineDurationS);
    startedRef.current = false;
    setPhase('starting');
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black">
      {/* Fixation cross */}
      <div className="flex items-center justify-center" style={{ minHeight: '40vh' }}>
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

      {/* Status panel */}
      <div className="mt-10 text-center text-white" style={{ maxWidth: 520 }}>
        {phase === 'starting' && (
          <>
            <p className="text-2xl font-semibold mb-2">Calibration starting…</p>
            <p className="text-gray-300">Initializing baseline collection.</p>
          </>
        )}

        {phase === 'counting' && (
          <>
            <p className="text-2xl font-semibold mb-3">
              <FormatSeconds seconds={remaining} />
            </p>
            <p className="text-lg mb-1">Please look at the cross and sit calmly.</p>
            <p className="text-gray-300 text-sm">
              We're measuring your resting pupil size before the procedure begins.
              Don't read, talk, or move — just breathe normally.
            </p>
          </>
        )}

        {phase === 'ending' && (
          <>
            <p className="text-2xl font-semibold mb-2">Finalizing baseline…</p>
            <p className="text-gray-300">Freezing reference values.</p>
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
              {onCancel && (
                <button
                  onClick={onCancel}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white text-sm font-medium"
                >
                  Skip (no baseline)
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CalibrationScreen;
