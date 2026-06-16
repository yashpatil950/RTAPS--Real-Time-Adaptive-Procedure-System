import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Database, Download, Trash2, RefreshCw, HardDrive, Cloud, Info, AlertTriangle } from 'lucide-react';
import { listRawSessions, rawSessionDownloadUrl, deleteRawSession, getStreamingBaseUrl } from '../services/streamingApi';

const PROCEDURE_NAMES = { 1: 'Centrifuge', 2: 'Column Flushing', 3: 'Pressure Testing' };

const procName = (id) => PROCEDURE_NAMES[id] || (id != null ? `Procedure ${id}` : '—');

const fmtBytes = (b) => {
  if (!b && b !== 0) return '—';
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / (1024 * 1024)).toFixed(2)} MB`;
};

const fmtDuration = (s) => {
  if (s == null) return '—';
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
};

const fmtDate = (epochSec) => {
  if (!epochSec) return '—';
  return new Date(epochSec * 1000).toLocaleString();
};

const RawData = () => {
  const [data, setData] = useState({ storage: null, bucket: null, count: 0, sessions: [] });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyKey, setBusyKey] = useState(null);

  const load = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await listRawSessions();
      setData(res || { storage: null, bucket: null, count: 0, sessions: [] });
    } catch (e) {
      console.error('Error loading raw sessions:', e);
      setError(
        `Could not reach the streaming backend at ${getStreamingBaseUrl()}. ` +
          'Make sure it is running and raw-data archival is enabled.'
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const totals = useMemo(() => {
    const s = data.sessions || [];
    return {
      count: s.length,
      bytes: s.reduce((a, x) => a + (x.size_bytes || 0), 0),
      pupil: s.reduce((a, x) => a + (x.n_pupil || 0), 0),
    };
  }, [data.sessions]);

  const handleDelete = async (key) => {
    if (!window.confirm('Permanently delete this raw recording? This cannot be undone.')) return;
    try {
      setBusyKey(key);
      await deleteRawSession(key);
      await load();
    } catch (e) {
      console.error('Error deleting raw session:', e);
      setError('Failed to delete that recording. Please try again.');
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            <Database className="w-7 h-7 text-slate-700" /> Raw Eye-Tracking Data
          </h1>
          <p className="text-gray-600 mt-1">
            Full pupil, blink, and fixation streams archived per procedure, for future analysis and model development.
          </p>
        </div>
        <button
          onClick={load}
          className="inline-flex items-center gap-2 border rounded-lg px-3 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Storage backend banner */}
      <div className="bg-white rounded-lg shadow p-4 flex flex-wrap items-center gap-x-6 gap-y-2">
        <span className="inline-flex items-center gap-2 text-sm">
          {data.storage === 's3' ? (
            <Cloud className="w-4 h-4 text-sky-600" />
          ) : (
            <HardDrive className="w-4 h-4 text-slate-500" />
          )}
          <span className="text-gray-600">Storage:</span>
          <span className="font-medium text-gray-900">
            {data.storage === 's3' ? `Amazon S3 (${data.bucket || 'bucket'})` : data.storage === 'local' ? 'Backend local disk' : '—'}
          </span>
        </span>
        <span className="text-sm text-gray-600">Recordings: <span className="font-medium text-gray-900">{totals.count}</span></span>
        <span className="text-sm text-gray-600">Total size: <span className="font-medium text-gray-900">{fmtBytes(totals.bytes)}</span></span>
        <span className="text-sm text-gray-600">Pupil samples: <span className="font-medium text-gray-900">{totals.pupil.toLocaleString()}</span></span>
        {data.storage === 'local' && (
          <span className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
            <Info className="w-3.5 h-3.5" /> Stored on the backend disk. Set RAW_DATA_S3_BUCKET to archive to S3.
          </span>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Archived Sessions</h2>

        {isLoading ? (
          <div className="text-center py-10">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-3" />
            <p className="text-gray-600">Loading raw sessions...</p>
          </div>
        ) : (data.sessions || []).length === 0 ? (
          <div className="text-gray-600">No raw recordings yet. They are saved automatically when a procedure ends.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="text-gray-600 border-b border-gray-200">
                  <th className="px-3 py-2 whitespace-nowrap">Recorded</th>
                  <th className="px-3 py-2 whitespace-nowrap">Participant</th>
                  <th className="px-3 py-2 whitespace-nowrap">Procedure</th>
                  <th className="px-3 py-2 whitespace-nowrap">Mode</th>
                  <th className="px-3 py-2 whitespace-nowrap">Duration</th>
                  <th className="px-3 py-2 whitespace-nowrap">Pupil</th>
                  <th className="px-3 py-2 whitespace-nowrap">Blinks</th>
                  <th className="px-3 py-2 whitespace-nowrap">Fixations</th>
                  <th className="px-3 py-2 whitespace-nowrap">Size</th>
                  <th className="px-3 py-2 whitespace-nowrap">Stream ID</th>
                  <th className="px-3 py-2 whitespace-nowrap text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(data.sessions || []).map((s) => {
                  const adaptive = s.mode !== 'non-adaptive';
                  return (
                    <tr key={s.key} className="border-t border-gray-200">
                      <td className="px-3 py-3 text-gray-700 whitespace-nowrap">{fmtDate(s.persisted_at)}</td>
                      <td className="px-3 py-3 text-gray-700 whitespace-nowrap">{s.participant_id || '—'}</td>
                      <td className="px-3 py-3 text-gray-700 whitespace-nowrap">{procName(s.procedure_id)}</td>
                      <td className="px-3 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${adaptive ? 'bg-blue-100 text-blue-800' : 'bg-gray-200 text-gray-700'}`}>
                          {adaptive ? 'Adaptive' : 'Non-adaptive'}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-gray-700 whitespace-nowrap">{fmtDuration(s.duration_s)}</td>
                      <td className="px-3 py-3 text-gray-700 tabular-nums">{(s.n_pupil || 0).toLocaleString()}</td>
                      <td className="px-3 py-3 text-gray-700 tabular-nums">{s.n_blinks ?? 0}</td>
                      <td className="px-3 py-3 text-gray-700 tabular-nums">{s.n_fixations ?? 0}</td>
                      <td className="px-3 py-3 text-gray-700 whitespace-nowrap">
                        {fmtBytes(s.size_bytes)}
                        {s.truncated && (
                          <span className="ml-1 text-amber-600" title="Sample cap reached; recording was truncated">⚠</span>
                        )}
                      </td>
                      <td className="px-3 py-3 text-gray-500 font-mono text-xs max-w-[12rem] truncate" title={s.stream_id}>{s.stream_id}</td>
                      <td className="px-3 py-3 whitespace-nowrap text-right">
                        <div className="inline-flex items-center gap-2">
                          <a
                            href={rawSessionDownloadUrl(s.key)}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 border rounded px-2 py-1 bg-gray-100 hover:bg-gray-200 text-gray-700"
                            title="Download raw file (.json.gz)"
                          >
                            <Download className="w-4 h-4" />
                          </a>
                          <button
                            onClick={() => handleDelete(s.key)}
                            disabled={busyKey === s.key}
                            className="inline-flex items-center gap-1 border border-red-200 rounded px-2 py-1 bg-red-50 hover:bg-red-100 text-red-700 disabled:opacity-50"
                            title="Delete recording"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-xs text-gray-400 mt-4">
          Each file is a gzip-compressed JSON document containing the session metadata, step changes, and the full pupil / blink /
          fixation streams. Download and decompress for offline analysis.
        </p>
      </div>
    </div>
  );
};

export default RawData;
