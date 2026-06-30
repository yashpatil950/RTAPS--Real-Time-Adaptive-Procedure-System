// Shared eye-tracker connection classification.
//
// Both the live status badge (components/EyeTrackerStatus.js) and the
// per-session data-loss tracker (pages/SessionView.js) must agree on what
// counts as "green" (connected) vs "orange" (eyes not captured) vs "red"
// (no data). Keeping the rule here ensures the data-loss percentage reported
// in Analytics is measured against the very same green/orange/red signal the
// operator sees, instead of a second, drifting copy of the logic.

// Below this fraction of recent frames being well-detected, we treat the eye
// as "not properly captured" (camera sees frames but can't resolve the pupil).
// The per-frame confidence bar that feeds `pupil_good_recent` is set on the
// backend (Settings.connection_min_confidence, default 0.7).
export const GOOD_FRACTION_THRESHOLD = 0.5;

// Pull the two running counters the classifier compares across polls.
export function readEyeCounters(dashboard) {
  return {
    raw: dashboard?.raw_pupil_received_total ?? 0,
    acc: dashboard?.pupil_received_total ?? 0,
  };
}

// Classify the eye tracker from the previous and current dashboard snapshots.
//   'connected' — green:  frames arriving AND the eye is captured well
//   'poor'      — orange: frames arriving but the pupil isn't resolved
//   'no-data'   — red:    no frames arriving at all
//   'checking'  — gray:   first poll (no baseline to diff against yet)
//
// `prevCounters` is the { raw, acc } returned by readEyeCounters on the prior
// poll, or null/undefined on the first poll.
export function classifyEyeStatus(prevCounters, dashboard) {
  const { raw, acc } = readEyeCounters(dashboard);
  const good =
    typeof dashboard?.pupil_good_recent === 'number' ? dashboard.pupil_good_recent : null;

  if (!prevCounters) return 'checking'; // first poll: establish a baseline

  const rawRising = raw > prevCounters.raw;
  const accRising = acc > prevCounters.acc;
  if (rawRising) {
    // Frames are arriving — judge capture quality.
    if (good == null) return accRising ? 'connected' : 'poor';
    return good >= GOOD_FRACTION_THRESHOLD ? 'connected' : 'poor';
  }
  if (accRising) return 'connected'; // raw archival off, but usable frames flow
  return 'no-data'; // no frames at all
}

// Whether a status represents lost data (orange or red). 'connected' is the
// only "everything is fine" state; 'checking'/'disabled' are not counted.
export function isDataLossStatus(status) {
  return status === 'poor' || status === 'no-data' || status === 'offline';
}
