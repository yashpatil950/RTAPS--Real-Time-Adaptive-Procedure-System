import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Activity,
  ArrowLeft,
  Brain,
  Eye,
  Layers,
  ListTree,
  Radio,
  RefreshCw,
  Server,
  SlidersHorizontal,
  Wifi,
} from 'lucide-react';
import {
  Line,
  LineChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  BarChart,
  Bar,
  Cell,
} from 'recharts';
import {
  getSessionDashboard,
  getStoredStreamId,
  getStreamingBaseUrl,
  isStreamingIntegrationEnabled,
  setStoredStreamId,
  streamingReady,
  subscribePredictions,
  setStreamingIntegrationEnabled,
} from '../services/streamingApi';

// v4 sensor-only feature set — matches Streaming_Backend feature_extractor.FEATURE_NAMES
// and ML Algorithm 07c_train_rf_pnorm.py FEATURE_COLS.
const FEATURE_ORDER = [
  'pupil_pcps_mean',
  'pupil_diam_slope',
  'blink_rate_30s',
  'fixation_dur_mean_ms',
  'fixation_dispersion_mean',
];

const PROCEDURE_NAMES = {
  1: 'Centrifuge',
  2: 'Column flushing',
  3: 'Pressure testing',
};

function formatNum(v, decimals = 3) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) {
    return '—';
  }
  return Number(v).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Fixed-height slot — inner content swaps without resizing the shell. */
function Panel({ title, icon: Icon, children, className = '', rightSlot }) {
  return (
    <div className={`tablet-card flex flex-col min-h-[260px] ${className}`}>
      <div className="flex items-center justify-between gap-2 pb-3 border-b border-gray-100 shrink-0">
        <div className="flex items-center gap-2 min-h-[28px]">
          {Icon ? <Icon className="w-5 h-5 text-slate-600" /> : null}
          <h3 className="text-sm font-semibold text-gray-800 tracking-tight">{title}</h3>
        </div>
        {rightSlot}
      </div>
      <div className="flex-1 pt-4 min-h-0">{children}</div>
    </div>
  );
}

function StableValue({ label, value, sub }) {
  return (
    <div className="bg-slate-50 rounded-lg px-3 py-2 border border-slate-100">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{label}</div>
      <div className="text-lg font-semibold text-slate-900 tabular-nums leading-tight min-h-[1.75rem] flex items-center">
        {value}
      </div>
      {sub ? <div className="text-xs text-slate-500 mt-0.5">{sub}</div> : null}
    </div>
  );
}

export default function StreamingDashboard() {
  const location = useLocation();
  const [streamId, setStreamId] = useState(() => getStoredStreamId());
  const [pollMs, setPollMs] = useState(400);
  const [integrateSessions, setIntegrateSessions] = useState(() => isStreamingIntegrationEnabled());

  const [backendReady, setBackendReady] = useState(null);
  const [dash, setDash] = useState(null);
  const [pred, setPred] = useState(null);
  const [sseOk, setSseOk] = useState(null);
  const [lastError, setLastError] = useState('');
  const [tick, setTick] = useState(0);

  const persistStreamId = useCallback(() => {
    setStoredStreamId(streamId.trim());
  }, [streamId]);

  useEffect(() => {
    setStreamId(getStoredStreamId());
  }, [location.pathname]);

  const toggleIntegration = (v) => {
    setIntegrateSessions(v);
    setStreamingIntegrationEnabled(v);
  };

  // Poll /ready
  useEffect(() => {
    let cancelled = false;
    const ping = async () => {
      try {
        const r = await streamingReady();
        if (!cancelled) {
          setBackendReady(r);
          setLastError('');
        }
      } catch (e) {
        if (!cancelled) {
          setBackendReady(null);
          setLastError(String(e.message || e));
        }
      }
    };
    ping();
    const id = setInterval(ping, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [tick]);

  // Poll dashboard
  useEffect(() => {
    if (!streamId.trim()) {
      setDash(null);
      setPred(null);
      return undefined;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const d = await getSessionDashboard(streamId.trim());
        if (!cancelled) {
          setDash(d);
          if (d?.last_prediction) {
            const { qa: _qa, ...rest } = d.last_prediction;
            setPred(rest);
          } else {
            setPred(null);
          }
          setLastError('');
        }
      } catch (e) {
        if (!cancelled) {
          setDash(null);
          setLastError(String(e.message || e));
        }
      }
    };
    load();
    const id = setInterval(load, pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [streamId, pollMs]);

  // SSE predictions
  useEffect(() => {
    if (!streamId.trim()) {
      setSseOk(null);
      return undefined;
    }
    setSseOk(true);
    const unsub = subscribePredictions(
      streamId.trim(),
      (data) => {
        const { qa: _qa, ...rest } = data || {};
        setPred(rest);
        setSseOk(true);
      },
      () => setSseOk(false)
    );
    return () => {
      unsub();
    };
  }, [streamId]);

  const extras = backendReady?.extras || {};
  const serverPipe = dash?.server_pipeline || {};
  const latestByEye = dash?.latest_pupil_by_eye || {};

  const chartE0 = useMemo(
    () => (dash?.pupil_series_eye0 || []).map((p) => ({ t: p.t, mm: p.mm })),
    [dash]
  );
  const chartE1 = useMemo(
    () => (dash?.pupil_series_eye1 || []).map((p) => ({ t: p.t, mm: p.mm })),
    [dash]
  );

  const probaBars = useMemo(() => {
    const p = pred?.workload_proba || {};
    return [
      { name: 'Low', key: 'low', value: p.low ?? 0, fill: '#22c55e' },
      { name: 'Medium', key: 'medium', value: p.medium ?? 0, fill: '#eab308' },
      { name: 'High', key: 'high', value: p.high ?? 0, fill: '#ef4444' },
    ];
  }, [pred]);

  /** Procedure / step / session duration come from predictions once inference runs.
   *  Until then the dashboard snapshot already exposes UI-synced fields from `/session/start`
   *  and `/session/step_change`; session duration matches backend: latest_pupil_t − session_started_at.
   */
  const sessionContext = useMemo(() => {
    const procedureId = pred?.procedure_id ?? dash?.procedure_id ?? null;
    const stepNumber = pred?.step_number ?? dash?.step_number ?? null;
    let cumulativeSessionTimeS = pred?.cumulative_session_time_s;
    if (cumulativeSessionTimeS == null && dash?.latest_pupil_t != null && dash?.session_started_at != null) {
      cumulativeSessionTimeS = dash.latest_pupil_t - dash.session_started_at;
    }
    return { procedureId, stepNumber, cumulativeSessionTimeS };
  }, [dash, pred]);

  const windowProgress = useMemo(() => {
    const win = dash?.sliding_window || {};
    const sp = dash?.server_pipeline || {};
    const ex = backendReady?.extras || {};
    const end = win.end_timestamp;
    const start = win.start_timestamp;
    if (end == null || start == null || !Number.isFinite(end - start)) {
      return { pct: 0, label: 'Waiting for pupil stream…' };
    }
    const span = end - start;
    const target = sp.window_len_s || ex.window_len_s || 10;
    const pct = Math.min(100, Math.max(0, (span / target) * 100));
    return { pct, label: `${span.toFixed(2)}s of data in buffer (target ${target}s window)` };
  }, [dash, backendReady]);

  const baselineProgress = useMemo(() => {
    const baselinePhase = dash?.baseline_phase || {};
    const sp = dash?.server_pipeline || {};
    const ex = backendReady?.extras || {};
    const total = sp.baseline_duration_s || ex.baseline_duration_s || 60;
    const rem = baselinePhase.seconds_remaining_estimate;
    if (baselinePhase.ready) {
      return { pct: 100, label: 'Baseline locked' };
    }
    if (rem == null || rem === undefined) {
      return { pct: 0, label: 'Collecting baseline…' };
    }
    const done = Math.max(0, total - rem);
    const pct = Math.min(100, (done / total) * 100);
    return { pct, label: `~${rem.toFixed(0)}s remaining (first ${total}s)` };
  }, [dash, backendReady]);

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="w-4 h-4" />
            Dashboard
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Live streaming &amp; ML</h1>
            <p className="text-sm text-slate-500 mt-1">
              Eye-tracking ingress, causal window, baseline, and workload model — stable layout panel.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${
              backendReady ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-rose-50 text-rose-800 border-rose-200'
            }`}
          >
            <Server className="w-3.5 h-3.5" />
            Backend {backendReady ? 'reachable' : 'offline'}
          </span>
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border ${
              sseOk ? 'bg-sky-50 text-sky-800 border-sky-200' : 'bg-slate-50 text-slate-600 border-slate-200'
            }`}
          >
            <Radio className="w-3.5 h-3.5" />
            SSE {streamId.trim() ? (sseOk === false ? 'reconnect…' : 'live') : 'idle'}
          </span>
          <button
            type="button"
            onClick={() => setTick((t) => t + 1)}
            className="tablet-button bg-slate-100 text-slate-700 hover:bg-slate-200 py-2 px-4 text-sm"
          >
            <RefreshCw className="w-4 h-4 inline mr-1" />
            Check connection
          </button>
        </div>
      </div>

      {lastError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong>Notice:</strong> {lastError}
        </div>
      ) : null}

      {/* Controls — fixed area */}
      <div className="tablet-card">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
              Stream ID (must match Pupil bridge)
            </label>
            <input
              className="tablet-input font-mono text-base"
              value={streamId}
              onChange={(e) => setStreamId(e.target.value)}
              placeholder="e.g. S232_T002 — or open a procedure session to auto-fill"
            />
          </div>
          <div className="w-32">
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
              Poll ms
            </label>
            <input
              type="number"
              min={200}
              max={5000}
              step={100}
              className="tablet-input text-base"
              value={pollMs}
              onChange={(e) => setPollMs(Number(e.target.value) || 400)}
            />
          </div>
          <button
            type="button"
            onClick={persistStreamId}
            className="tablet-button bg-blue-600 text-white hover:bg-blue-700"
          >
            Save stream ID
          </button>
          <label className="inline-flex items-center gap-2 text-sm text-slate-700 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={integrateSessions}
              onChange={(e) => toggleIntegration(e.target.checked)}
            />
            Sync procedure UI → backend
          </label>
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Opening <code className="bg-slate-100 px-1 rounded">/session/…</code> saves a stream ID like{' '}
          <code className="bg-slate-100 px-1 rounded">RTAPS_…_P1_T1</code> so this page and the backend stay in sync. Use the same ID
          for <code className="bg-slate-100 px-1 rounded">pupil_capture_bridge.py --stream_id</code>, or set it manually above.
        </p>
        <p className="text-xs text-slate-500 mt-2 font-mono break-all">
          API base: <span className="text-slate-700">{getStreamingBaseUrl()}</span>
        </p>
      </div>

      {/* Architecture */}
      <Panel title="Pipeline architecture" icon={Activity}>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 text-xs">
          <div className="lg:col-span-3 rounded-xl bg-gradient-to-br from-violet-50 to-white border border-violet-100 p-4 min-h-[120px]">
            <div className="font-semibold text-violet-900 flex items-center gap-2 mb-2">
              <Eye className="w-4 h-4" />
              Pupil Capture
            </div>
            <p className="text-violet-800/90 leading-snug">
              ZMQ network API →{' '}
              <code className="bg-violet-100/80 px-1 rounded">pupil_capture_bridge.py</code> batches HTTP POSTs
              (<code>pupil</code>, <code>blinks</code>, <code>fixations</code>).
            </p>
          </div>
          <div className="lg:col-span-1 flex items-center justify-center text-slate-300 text-xl">→</div>
          <div className="lg:col-span-4 rounded-xl bg-gradient-to-br from-sky-50 to-white border border-sky-100 p-4 min-h-[120px]">
            <div className="font-semibold text-sky-900 flex items-center gap-2 mb-2">
              <Server className="w-4 h-4" />
              Streaming backend
            </div>
            <ul className="text-sky-900/85 space-y-1 list-disc list-inside">
              <li>
                Sliding causal window{' '}
                <span className="tabular-nums font-semibold">{serverPipe.window_len_s ?? extras.window_len_s ?? '10'}s</span>
              </li>
              <li>
                Stride{' '}
                <span className="tabular-nums font-semibold">{serverPipe.stride_s ?? extras.stride_s ?? '1'}s</span> inference
              </li>
              <li>Blink tracking-loss filter &amp; fixation duration</li>
              <li>
                Session context from RTAPS: <code className="bg-sky-100 px-1 rounded">procedure_id</code>,{' '}
                <code className="bg-sky-100 px-1 rounded">step_number</code>
              </li>
            </ul>
          </div>
          <div className="lg:col-span-1 flex items-center justify-center text-slate-300 text-xl">→</div>
          <div className="lg:col-span-3 rounded-xl bg-gradient-to-br from-emerald-50 to-white border border-emerald-100 p-4 min-h-[120px]">
            <div className="font-semibold text-emerald-900 flex items-center gap-2 mb-2">
              <Brain className="w-4 h-4" />
              ML model (8 features)
            </div>
            <p className="text-emerald-900/85 leading-snug mb-2">
              In-process HistGradientBoosting on the same columns as offline training (<code>X_FEATURES.md</code>).
            </p>
            <p className="text-emerald-800/80">
              Inference mode:{' '}
              <span className="font-semibold">{extras.inference_mode || 'local'}</span>
            </p>
          </div>
        </div>

        {/* Window + baseline gauges — fixed heights */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div className="border border-slate-200 rounded-lg p-3 bg-white min-h-[100px]">
            <div className="flex items-center justify-between text-xs font-medium text-slate-600 mb-2">
              <span className="flex items-center gap-1">
                <SlidersHorizontal className="w-3.5 h-3.5" /> Baseline phase (cold start)
              </span>
              <span className="tabular-nums text-slate-500">{baselineProgress.label}</span>
            </div>
            <div className="h-3 w-full rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-indigo-500 transition-[width] duration-300"
                style={{ width: `${baselineProgress.pct}%` }}
              />
            </div>
          </div>
          <div className="border border-slate-200 rounded-lg p-3 bg-white min-h-[100px]">
            <div className="flex items-center justify-between text-xs font-medium text-slate-600 mb-2">
              <span className="flex items-center gap-1">
                <Wifi className="w-3.5 h-3.5" /> Rolling feature window span
              </span>
              <span className="tabular-nums text-slate-500">{windowProgress.label}</span>
            </div>
            <div className="h-3 w-full rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-cyan-500 transition-[width] duration-300"
                style={{ width: `${windowProgress.pct}%` }}
              />
            </div>
          </div>
        </div>
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        {/* Eye device */}
        <div className="xl:col-span-5 space-y-4">
          <Panel
            title="Eye tracker → buffer (live)"
            icon={Eye}
            rightSlot={
              dash?.baseline_ready ? (
                <span className="text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
                  Baseline ready
                </span>
              ) : (
                <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">
                  Warming up
                </span>
              )
            }
          >
            <div className="grid grid-cols-2 gap-2 mb-4">
              <StableValue
                label="Right eye ø (mm)"
                value={latestByEye['0'] ? formatNum(latestByEye['0'].diameter_mm, 2) : '—'}
                sub={
                  latestByEye['0'] ? `${(latestByEye['0'].confidence * 100).toFixed(0)}% conf` : 'no sample'
                }
              />
              <StableValue
                label="Left eye ø (mm)"
                value={latestByEye['1'] ? formatNum(latestByEye['1'].diameter_mm, 2) : '—'}
                sub={
                  latestByEye['1'] ? `${(latestByEye['1'].confidence * 100).toFixed(0)}% conf` : 'no sample'
                }
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-4 text-center">
              <div className="bg-slate-50 rounded-lg py-2 border border-slate-100">
                <div className="text-[10px] uppercase text-slate-500">Pupil samples</div>
                <div className="text-xl font-bold tabular-nums text-slate-800">{dash?.pupil_samples_buffered ?? '—'}</div>
                <div className="text-[9px] text-slate-400">total {dash?.pupil_received_total ?? '—'}</div>
              </div>
              <div className="bg-slate-50 rounded-lg py-2 border border-slate-100">
                <div className="text-[10px] uppercase text-slate-500">Blinks</div>
                <div className="text-xl font-bold tabular-nums text-slate-800">{dash?.blinks_buffered ?? '—'}</div>
                <div className="text-[9px] text-slate-400">total {dash?.blinks_received_total ?? '—'}</div>
              </div>
              <div className="bg-slate-50 rounded-lg py-2 border border-slate-100">
                <div className="text-[10px] uppercase text-slate-500">Fixations</div>
                <div className="text-xl font-bold tabular-nums text-slate-800">{dash?.fixations_buffered ?? '—'}</div>
                <div className="text-[9px] text-slate-400">total {dash?.fixations_received_total ?? '—'}</div>
              </div>
            </div>

            {/* Fixation-received warning — appears if no fixations have been
                received yet, helping the operator catch a disabled Pupil Capture
                plugin or a stopped bridge. */}
            {dash && dash.pupil_received_total > 0 && (dash.fixations_received_total ?? 0) === 0 && (
              <div className="mt-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
                ⚠ No fixations received yet (pupil samples are flowing).
                Check <strong>Pupil Capture → Plugin Manager → Online Fixation Detector</strong> is enabled.
              </div>
            )}

            <div className="h-[200px] w-full grid grid-cols-1 gap-2">
              <div className="h-[94px] min-h-[94px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartE0} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="t" tick={false} height={14} stroke="#cbd5e1" />
                    <YAxis domain={['auto', 'auto']} width={36} stroke="#cbd5e1" fontSize={10} />
                    <Tooltip formatter={(val) => [formatNum(val, 2), 'mm']} labelFormatter={(t) => `t=${t}`} />
                    <Line type="monotone" dataKey="mm" stroke="#6366f1" dot={false} strokeWidth={2} name="Eye 0" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="h-[94px] min-h-[94px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartE1} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="t" tick={false} height={14} stroke="#cbd5e1" />
                    <YAxis domain={['auto', 'auto']} width={36} stroke="#cbd5e1" fontSize={10} />
                    <Tooltip formatter={(val) => [formatNum(val, 2), 'mm']} labelFormatter={(t) => `t=${t}`} />
                    <Line type="monotone" dataKey="mm" stroke="#06b6d4" dot={false} strokeWidth={2} name="Eye 1" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Panel>
        </div>

        {/* Model output + inputs (procedure / step / time are task inputs echoed on predictions for traceability) */}
        <div className="xl:col-span-7 space-y-4">
          <Panel
            title="Session & task inputs"
            icon={ListTree}
            rightSlot={
              <span className="text-[10px] text-slate-500 max-w-[14rem] text-right leading-snug">
                From RTAPS UI + clock; same values as three rows in the feature vector
              </span>
            }
          >
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <StableValue
                label="Procedure"
                value={
                  sessionContext.procedureId != null
                    ? PROCEDURE_NAMES[sessionContext.procedureId] || `#${sessionContext.procedureId}`
                    : '—'
                }
              />
              <StableValue label="Step #" value={sessionContext.stepNumber != null ? sessionContext.stepNumber : '—'} />
              <StableValue
                label="Session time"
                sub="cumulative_session_time_s"
                value={
                  sessionContext.cumulativeSessionTimeS != null
                    ? `${formatNum(sessionContext.cumulativeSessionTimeS, 1)} s`
                    : '—'
                }
              />
            </div>
          </Panel>

          <Panel
            title="Model output (streaming)"
            icon={Brain}
            rightSlot={
              !pred ? (
                <span className="text-xs text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">Awaiting predictions</span>
              ) : pred?.is_valid_window === false ? (
                <span className="text-xs text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full">Weak window</span>
              ) : (
                <span className="text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">Valid window</span>
              )
            }
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex flex-col justify-center items-center rounded-xl bg-slate-900 text-white p-6 min-h-[180px]">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-400 mb-3">Workload</div>
                <div className="text-4xl font-black tracking-tight min-h-[2.5rem] flex items-center justify-center capitalize">
                  {pred?.workload_label || '—'}
                </div>
                <div className="text-xs text-slate-400 mt-2 font-mono">
                  {pred?.decision_time != null ? `decision pupil_t=${formatNum(pred.decision_time)}` : 'awaiting SSE / poll'}
                </div>
                {pred?.notes ? (
                  <div className="text-[11px] text-amber-300 mt-3 text-center max-w-sm">{pred.notes}</div>
                ) : null}
              </div>

              <div className="h-[200px] min-h-[200px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart layout="vertical" data={probaBars} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal />
                    <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} fontSize={10} />
                    <YAxis type="category" dataKey="name" width={72} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v) => `${(Number(v) * 100).toFixed(1)}%`} />
                    <ReferenceLine x={0} stroke="#cbd5e1" />
                    <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={28}>
                      {probaBars.map((e, i) => (
                        <Cell key={i} fill={e.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="mt-4">
              <StableValue
                label="Inference"
                value={pred?.inference_source || extras.inference_mode || '—'}
                sub={`${extras.window_len_s ?? ''}s win / ${extras.stride_s ?? ''}s stride`}
              />
            </div>
          </Panel>

          <Panel title="Features sent to the model (8)" icon={Layers}>
            <div className="rounded-lg border border-slate-100 overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 uppercase tracking-wide border-b border-slate-100">
                    <th className="text-left py-2 px-3 font-medium w-[40%]">Feature</th>
                    <th className="text-right py-2 px-3 font-medium">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {FEATURE_ORDER.map((name) => (
                    <tr key={name} className="border-b border-slate-50 hover:bg-slate-50/50">
                      <td className="py-2 px-3 font-mono text-slate-600">{name}</td>
                      <td className="py-2 px-3 font-mono text-right tabular-nums text-slate-900 font-semibold min-w-[120px]">
                        {pred?.feature_values?.[name] !== undefined
                          ? String(pred.feature_values[name])
                          : name === 'procedure_id' && sessionContext.procedureId != null
                            ? String(sessionContext.procedureId)
                            : name === 'step_number' && sessionContext.stepNumber != null
                              ? String(sessionContext.stepNumber)
                              : name === 'cumulative_session_time_s' &&
                                  sessionContext.cumulativeSessionTimeS != null
                                ? String(formatNum(sessionContext.cumulativeSessionTimeS, 3))
                                : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
