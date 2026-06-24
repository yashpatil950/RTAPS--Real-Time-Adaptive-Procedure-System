import React, { useState, useEffect, useRef } from 'react';
import { Eye, EyeOff } from 'lucide-react';
import {
  isStreamingIntegrationEnabled,
  getStoredStreamId,
  getSessionDashboard,
  streamingReady,
} from '../services/streamingApi';

// How often to re-check the eye tracker. Pupil frames stream at ~120 Hz, so the
// backend's counters rise every poll while the tracker is live.
const POLL_MS = 3000;
// Below this fraction of recent frames being well-detected, we treat the eye as
// "not properly captured" (camera can see frames but can't resolve the pupil).
const GOOD_FRACTION_THRESHOLD = 0.5;

const STYLES = {
  connected: { dot: 'bg-green-500', cls: 'bg-green-50 border-green-200 text-green-700', label: 'Connected' },
  poor: { dot: 'bg-orange-500', cls: 'bg-orange-50 border-orange-200 text-orange-700', label: 'Eyes not captured' },
  'no-data': { dot: 'bg-red-500', cls: 'bg-red-50 border-red-200 text-red-700', label: 'No eye data' },
  offline: { dot: 'bg-red-500', cls: 'bg-red-50 border-red-200 text-red-700', label: 'Disconnected' },
  disabled: { dot: 'bg-gray-400', cls: 'bg-gray-50 border-gray-200 text-gray-500', label: 'Off' },
  checking: { dot: 'bg-gray-400 animate-pulse', cls: 'bg-gray-50 border-gray-200 text-gray-500', label: 'Checking…' },
};

// Small badge showing the eye tracker's live state:
//   green  — frames arriving AND the eye is being captured well
//   orange — frames arriving but the camera isn't resolving the pupil
//            (low detection confidence); the device can't "see" the eye properly
//   red    — no frames arriving, or the backend is unreachable
//   gray   — streaming integration is off in this browser
const EyeTrackerStatus = () => {
  const [status, setStatus] = useState('checking');
  const prev = useRef({ raw: null, acc: null });

  useEffect(() => {
    if (typeof window === 'undefined' || !isStreamingIntegrationEnabled()) {
      setStatus('disabled');
      return undefined;
    }
    let cancelled = false;

    const tick = async () => {
      const sid = getStoredStreamId().trim();
      try {
        if (!sid) {
          await streamingReady(); // backend reachable but no stream bound yet
          if (!cancelled) setStatus('no-data');
          return;
        }
        const d = await getSessionDashboard(sid);
        const raw = d?.raw_pupil_received_total ?? 0;
        const acc = d?.pupil_received_total ?? 0;
        const good = typeof d?.pupil_good_recent === 'number' ? d.pupil_good_recent : null;

        const pr = prev.current;
        prev.current = { raw, acc };
        if (pr.raw == null) {
          if (!cancelled) setStatus('checking'); // first poll: establish a baseline
          return;
        }
        const rawRising = raw > pr.raw;
        const accRising = acc > pr.acc;
        let next;
        if (rawRising) {
          // Frames are arriving — judge capture quality.
          if (good == null) next = accRising ? 'connected' : 'poor';
          else next = good >= GOOD_FRACTION_THRESHOLD ? 'connected' : 'poor';
        } else if (accRising) {
          next = 'connected'; // raw archival off, but usable frames are flowing
        } else {
          next = 'no-data'; // no frames at all
        }
        if (!cancelled) setStatus(next);
      } catch (_) {
        try {
          await streamingReady();
          if (!cancelled) setStatus('no-data');
        } catch (__) {
          if (!cancelled) setStatus('offline');
        }
      }
    };

    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const s = STYLES[status] || STYLES.checking;
  const Icon = status === 'connected' || status === 'poor' ? Eye : EyeOff;
  return (
    <div
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${s.cls}`}
      title="Eye tracker connection and eye-capture quality"
    >
      <span className={`w-2 h-2 rounded-full ${s.dot}`} />
      <Icon className="w-3.5 h-3.5" />
      <span className="whitespace-nowrap">Eye tracker: {s.label}</span>
    </div>
  );
};

export default EyeTrackerStatus;
