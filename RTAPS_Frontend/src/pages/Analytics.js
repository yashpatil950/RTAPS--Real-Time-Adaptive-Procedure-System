import React, { useState, useEffect, useMemo } from 'react';
import { getSummary, loadAnalytics, getAllParticipants } from '../data/analyticsStorage';
import { Activity, Timer, ListChecks, Info, Download, ChevronRight, Lightbulb } from 'lucide-react';
import { procedures } from '../data/procedures';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

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

const getProcedureName = (id) => {
  const p = procedures.find((x) => x.id === id);
  return p ? p.name : `Procedure ${id}`;
};

const dateRanges = [
  { key: '7', label: 'Last 7 days' },
  { key: '30', label: 'Last 30 days' },
  { key: 'all', label: 'All time' }
];

const getCompletedAtMs = (s) => {
  const fromTop = s.completedAt || s.completedAtMs;
  if (fromTop) return new Date(fromTop).getTime();
  if (s.metadata && (s.metadata.completedAt || s.metadata.completedAtMs)) {
    return new Date(s.metadata.completedAt || s.metadata.completedAtMs).getTime();
  }
  return 0;
};

// Did the ML model flag high workload on this step (so adaptive guidance was
// revealed)? Prefer the workload fields recorded by the live system; fall back
// to the legacy time-threshold proxy for sessions saved before workload-driven
// adaptation existed.
const stepAdapted = (st) => {
  if (typeof st.adaptationShown === 'boolean') return st.adaptationShown;
  if (typeof st.workloadReachedHigh === 'boolean') return st.workloadReachedHigh;
  return !!st.subStepsShown;
};

const WORKLOAD_BADGE = {
  high: 'bg-orange-100 text-orange-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-green-100 text-green-800',
};

const secOrDash = (v) => (v == null ? '—' : `${v}s`);

const Analytics = () => {
  const [currentUser, setCurrentUser] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [summary, setSummary] = useState({ total: 0, avgTimeSec: 0, byProcedure: {} });
  const [analytics, setAnalytics] = useState({ sessions: [] });
  const [participants, setParticipants] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const userData = localStorage.getItem('currentParticipant');
    if (userData) {
      const user = JSON.parse(userData);
      setCurrentUser(user);
      setIsAdmin(user.role === 'admin');
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const [summaryData, analyticsData] = await Promise.all([
          getSummary(),
          loadAnalytics()
        ]);
        setSummary(summaryData || { total: 0, avgTimeSec: 0, byProcedure: {} });
        setAnalytics(analyticsData || { sessions: [] });
        if (isAdmin) {
          const participantsData = await getAllParticipants();
          setParticipants(participantsData || []);
        } else {
          setParticipants([]);
        }
      } catch (e) {
        console.error('Error loading analytics:', e);
        setError('Failed to load analytics data. Please try again.');
      } finally {
        setIsLoading(false);
      }
    };
    if (currentUser) {
      loadData();
    }
  }, [currentUser, isAdmin]);

  const [selectedProcedureId, setSelectedProcedureId] = useState('all');
  const [selectedRange, setSelectedRange] = useState('all');
  const [selectedUserId, setSelectedUserId] = useState('all');

  const filteredSessions = useMemo(() => {
    const now = Date.now();
    const minTime = selectedRange === 'all' ? 0 : now - parseInt(selectedRange, 10) * 24 * 60 * 60 * 1000;
    return (analytics.sessions || []).filter((s) => {
      const t = getCompletedAtMs(s);
      const inRange = t >= minTime;
      const procOk = selectedProcedureId === 'all' || s.procedureId === Number(selectedProcedureId);
      const userOk = !isAdmin || selectedUserId === 'all' || s.participantId === selectedUserId;
      return inRange && procOk && userOk;
    });
  }, [analytics.sessions, selectedProcedureId, selectedRange, selectedUserId, isAdmin]);

  const [selectedSessionIds, setSelectedSessionIds] = useState(new Set());
  useEffect(() => {
    setSelectedSessionIds(new Set(filteredSessions.map((s) => s.id || s.sessionId)));
  }, [filteredSessions]);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;
  useEffect(() => {
    // Reset to first page when filters change
    setCurrentPage(1);
  }, [selectedProcedureId, selectedRange, selectedUserId, isAdmin]);

  const selectedSessions = useMemo(() => {
    if (!selectedSessionIds || selectedSessionIds.size === 0) return [];
    const idSet = selectedSessionIds;
    return filteredSessions.filter((s) => idSet.has(s.id || s.sessionId));
  }, [filteredSessions, selectedSessionIds]);

  const avgTimeByStepData = useMemo(() => {
    if (selectedProcedureId === 'all') return [];
    const sessions = selectedSessions.filter((s) => s.procedureId === Number(selectedProcedureId));
    const stepsMap = new Map();
    sessions.forEach((s) => {
      (s.steps || []).forEach((st) => {
        const key = st.stepNumber;
        const cur = stepsMap.get(key) || { total: 0, count: 0 };
        cur.total += st.timeSpentSec || 0;
        cur.count += 1;
        stepsMap.set(key, cur);
      });
    });
    return Array.from(stepsMap.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([stepNumber, v]) => ({ step: `Step ${stepNumber}`, seconds: v.count ? Math.round(v.total / v.count) : 0 }));
  }, [selectedSessions, selectedProcedureId]);

  // Per-step rate at which the ML model flagged high workload (and adaptive
  // guidance was shown). This is the workload-driven view; the legacy
  // time-threshold rate is still available per-step via stepAdapted's fallback.
  const adaptationRateByStepData = useMemo(() => {
    if (selectedProcedureId === 'all') return [];
    const sessions = selectedSessions.filter((s) => s.procedureId === Number(selectedProcedureId));
    const stepsMap = new Map();
    sessions.forEach((s) => {
      (s.steps || []).forEach((st) => {
        const key = st.stepNumber;
        const cur = stepsMap.get(key) || { adapted: 0, count: 0 };
        cur.count += 1;
        if (stepAdapted(st)) cur.adapted += 1;
        stepsMap.set(key, cur);
      });
    });
    return Array.from(stepsMap.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([stepNumber, v]) => ({ step: `Step ${stepNumber}`, rate: v.count ? Math.round((100 * v.adapted) / v.count) : 0 }));
  }, [selectedSessions, selectedProcedureId]);

  // Sessions the operator can expand to see a per-step workload/time breakdown.
  const [expandedSessionIds, setExpandedSessionIds] = useState(new Set());
  const toggleSessionExpanded = (key) => {
    setExpandedSessionIds((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  // Overall adaptation rate across the currently filtered sessions: of all the
  // steps performed, what fraction triggered high-workload adaptive guidance.
  const adaptationOverall = useMemo(() => {
    let steps = 0;
    let adapted = 0;
    filteredSessions.forEach((s) => {
      (s.steps || []).forEach((st) => {
        steps += 1;
        if (stepAdapted(st)) adapted += 1;
      });
    });
    return { steps, adapted, ratePct: steps ? Math.round((100 * adapted) / steps) : 0 };
  }, [filteredSessions]);

  const handleExportCSV = () => {
    const headers = [
      'SessionId', 'CompletedAt', 'Participant', 'Procedure', 'Train', 'TotalTimeSec',
      'StepNumber', 'StepTitle', 'TimeSpentSec',
      'WorkloadHigh', 'AdaptationShown', 'FinalWorkloadLevel', 'TimeToAdaptationSec',
      'MaxHighProba', 'HighPredictionCount', 'PredictionCount',
      'ExceededThreshold(legacy)', 'SubStepsShown(legacy)',
    ];
    const rows = [];
    selectedSessions.forEach((s) => {
      (s.steps || []).forEach((st) => {
        rows.push([
          s.id || s.sessionId,
          new Date(getCompletedAtMs(s)).toISOString(),
          s.participantUsername || s.participantId || '',
          s.procedureName || getProcedureName(s.procedureId),
          s.trainNumber ? `Train ${s.trainNumber}` : 'N/A',
          s.totalTimeSec || 0,
          st.stepNumber,
          (st.stepTitle || '').replace(/,/g, ' '),
          st.timeSpentSec || 0,
          st.workloadReachedHigh ? 'yes' : 'no',
          stepAdapted(st) ? 'yes' : 'no',
          st.finalWorkloadLevel || '',
          st.timeToAdaptationSec == null ? '' : st.timeToAdaptationSec,
          st.maxHighProba == null ? '' : st.maxHighProba,
          st.highPredictionCount == null ? '' : st.highPredictionCount,
          st.predictionCount == null ? '' : st.predictionCount,
          st.exceededThreshold ? 'yes' : 'no',
          st.subStepsShown ? 'yes' : 'no',
        ]);
      });
    });
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'rtaps_analytics.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const sortedSessions = useMemo(() => {
    if (isAdmin) {
      return filteredSessions.slice().reverse();
    }
    return filteredSessions.slice().sort((a, b) => getCompletedAtMs(b) - getCompletedAtMs(a));
  }, [filteredSessions, isAdmin]);

  const totalPages = Math.max(1, Math.ceil(sortedSessions.length / pageSize));
  const paginatedSessions = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedSessions.slice(start, start + pageSize);
  }, [sortedSessions, currentPage]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading analytics...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="text-red-600 mb-4">
            <Info className="h-12 w-12 mx-auto mb-2" />
            <p className="text-lg font-medium">Error Loading Analytics</p>
            <p className="text-sm text-gray-600 mt-2">{error}</p>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Analytics</h1>
        <p className="text-lg text-gray-600">{isAdmin ? 'High-level insights from all sessions' : 'Your completed sessions'}</p>
      </div>

      <div className="bg-white rounded-lg shadow p-4">
        <div className={`grid grid-cols-1 gap-4 ${isAdmin ? 'md:grid-cols-4' : 'md:grid-cols-3'}`}>
          <div className="pr-2">
            <label className="block text-sm text-gray-600 mb-1">Procedure</label>
            <select
              value={selectedProcedureId}
              onChange={(e) => setSelectedProcedureId(e.target.value)}
              className="w-full border rounded px-3 py-2"
            >
              <option value="all">All procedures</option>
              {procedures.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          <div className="pr-2">
            <label className="block text-sm text-gray-600 mb-1">Date Range</label>
            <select
              value={selectedRange}
              onChange={(e) => setSelectedRange(e.target.value)}
              className="w-full border rounded px-3 py-2"
            >
              {dateRanges.map((r) => (
                <option key={r.key} value={r.key}>{r.label}</option>
              ))}
            </select>
          </div>
          {isAdmin && (
            <div className="pr-2">
              <label className="block text-sm text-gray-600 mb-1">User</label>
              <select
                value={selectedUserId}
                onChange={(e) => setSelectedUserId(e.target.value)}
                className="w-full border rounded px-3 py-2"
              >
                <option value="all">All users</option>
                {(participants || []).map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.username} ({user.id})
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex items-end pr-2">
            <button onClick={handleExportCSV} className="w-full flex items-center justify-center border rounded px-3 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700">
              <span className="mr-2">Export CSV</span>
              <Download className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <Activity className="w-6 h-6 text-blue-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">{summary.total}</h3>
          <p className="text-gray-600">Procedures Completed</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <Timer className="w-6 h-6 text-green-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">{formatTime(summary.avgTimeSec || 0)}</h3>
          <p className="text-gray-600">Average Total Time</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <ListChecks className="w-6 h-6 text-purple-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">{Object.keys(summary.byProcedure || {}).length}</h3>
          <p className="text-gray-600">Procedures Types Used</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6 text-center">
          <div className="w-12 h-12 bg-orange-100 rounded-lg flex items-center justify-center mx-auto mb-3">
            <Lightbulb className="w-6 h-6 text-orange-600" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">{adaptationOverall.ratePct}%</h3>
          <p className="text-gray-600">High-Workload Adaptation Rate</p>
          <p className="text-xs text-gray-400 mt-1">{adaptationOverall.adapted} / {adaptationOverall.steps} steps (filtered)</p>
        </div>
      </div>

      {selectedProcedureId !== 'all' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3">Average Time by Step(s)</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={avgTimeByStepData} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="step" />
                  <YAxis />
                  <Tooltip formatter={(v) => formatTime(v)} />
                  <Bar dataKey="seconds" fill="#3b82f6" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-3">High-Workload Adaptation Rate by Step(%)</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={adaptationRateByStepData} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="step" />
                  <YAxis unit="%" />
                  <Tooltip formatter={(v) => `${v}%`} />
                  <Bar dataKey="rate" fill="#f97316" />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Percent of sessions where the model flagged <span className="font-medium text-orange-700">high workload</span> on
              this step and adaptive guidance was shown.
            </p>
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Recent Sessions</h2>
        </div>

        {filteredSessions.length === 0 ? (
          <div className="text-gray-600">No completed sessions yet.</div>
        ) : (
          <div className="w-[90%] mx-auto pl-2">
            <table className="min-w-full w-full text-left table-fixed">
              <thead>
                <tr className="text-gray-600 text-sm">
                  <th className="py-2 pr-4 w-8">
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={selectedSessionIds.size > 0 && selectedSessionIds.size === filteredSessions.length}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedSessionIds(new Set(filteredSessions.map((s) => s.id || s.sessionId)));
                        } else {
                          setSelectedSessionIds(new Set());
                        }
                      }}
                    />
                  </th>
                  <th className="py-2 pr-16 w-60">Completed</th>
                  {isAdmin && <th className="py-2 pr-16 w-60">Participant</th>}
                  <th className="py-2 pr-16 w-60">Procedure</th>
                  <th className="py-2 pr-16 w-40">Train</th>
                  <th className="py-2 pr-16 w-60">Total Time</th>
                  <th className="py-2 pr-16">
                    <div className="relative inline-flex items-center space-x-1 group cursor-default">
                      <span>Steps</span>
                      <Info className="w-4 h-4 text-gray-400" />
                      <span
                        role="tooltip"
                        className="invisible group-hover:visible absolute left-0 top-full mt-2 w-64 text-xs text-gray-800 bg-white border border-gray-200 rounded-md shadow p-2 z-10"
                      >
                        Total main steps defined for the selected procedure. Sub-steps are not counted.
                      </span>
                    </div>
                  </th>
                  <th className="py-2 pr-16">
                    <div className="relative inline-flex items-center space-x-1 group cursor-default">
                      <span>Adaptations</span>
                      <Info className="w-4 h-4 text-gray-400" />
                      <span
                        role="tooltip"
                        className="invisible group-hover:visible absolute left-0 top-full mt-2 w-72 text-xs text-gray-800 bg-white border border-gray-200 rounded-md shadow p-2 z-10"
                      >
                        Main steps where the ML model flagged high workload and adaptive guidance was shown, out of total steps. Expand a row for the per-step breakdown.
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {paginatedSessions.map((s) => {
                  const key = s.id || s.sessionId;
                  const steps = s.steps || [];
                  const guidanceCount = steps.filter((x) => stepAdapted(x)).length;
                  const guidanceRate = steps.length ? Math.round((100 * guidanceCount) / steps.length) : 0;
                  const isExpanded = expandedSessionIds.has(key);
                  const colCount = isAdmin ? 8 : 7;
                  return (
                    <React.Fragment key={key}>
                      <tr className="border-t border-gray-200">
                        <td className="py-2 pr-4">
                          <input
                            type="checkbox"
                            checked={selectedSessionIds.has(key)}
                            onChange={(e) => {
                              setSelectedSessionIds((prev) => {
                                const next = new Set(prev);
                                if (e.target.checked) next.add(key); else next.delete(key);
                                return next;
                              });
                            }}
                          />
                        </td>
                        <td className="py-2 pr-4 text-gray-700">
                          <button
                            type="button"
                            onClick={() => toggleSessionExpanded(key)}
                            className="inline-flex items-center gap-1 hover:text-blue-700"
                            aria-expanded={isExpanded}
                            title="Show per-step breakdown"
                          >
                            <ChevronRight className={`w-4 h-4 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                            <span>{new Date(getCompletedAtMs(s)).toLocaleString()}</span>
                          </button>
                        </td>
                        {isAdmin && (
                          <td className="py-2 pr-4 text-gray-700 truncate">
                            <span className="inline-flex max-w-[8rem] items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 truncate">
                              {s.participantUsername || s.participantId || 'Unknown'}
                            </span>
                          </td>
                        )}
                        <td className="py-2 pr-4 text-gray-700">{s.procedureName || getProcedureName(s.procedureId)}</td>
                        <td className="py-2 pr-4 text-gray-700">
                          {s.trainNumber ? (
                            <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                              Train {s.trainNumber}
                            </span>
                          ) : (
                            <span className="text-gray-400 text-xs">N/A</span>
                          )}
                        </td>
                        <td className="py-2 pr-4 text-gray-700">{formatTime(s.totalTimeSec || 0)}</td>
                        <td className="py-2 pr-4 text-gray-700">{steps.length}</td>
                        <td className="py-2 pr-4 text-gray-700">
                          <span className={`font-medium ${guidanceCount > 0 ? 'text-orange-700' : 'text-gray-500'}`}>
                            {guidanceCount}/{steps.length}
                          </span>
                          <span className="text-gray-400 text-xs ml-1">({guidanceRate}%)</span>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-gray-50 border-t border-gray-100">
                          <td className="py-3 px-4" colSpan={colCount}>
                            {steps.length === 0 ? (
                              <div className="text-xs text-gray-500">No step detail recorded for this session.</div>
                            ) : (
                              <table className="w-full text-xs">
                                <thead>
                                  <tr className="text-gray-500">
                                    <th className="text-left py-1 pr-4">Step</th>
                                    <th className="text-left py-1 pr-4">Title</th>
                                    <th className="text-left py-1 pr-4">Time</th>
                                    <th className="text-left py-1 pr-4">Workload</th>
                                    <th className="text-left py-1 pr-4">Adapted</th>
                                    <th className="text-left py-1 pr-4">Time → adaptation</th>
                                    <th className="text-left py-1 pr-4">Peak P(high)</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {steps.slice().sort((a, b) => (a.stepNumber || 0) - (b.stepNumber || 0)).map((st) => {
                                    const adapted = stepAdapted(st);
                                    const lvl = st.finalWorkloadLevel || (st.workloadReachedHigh ? 'high' : 'low');
                                    return (
                                      <tr key={st.stepId || st.stepNumber} className="border-t border-gray-200">
                                        <td className="py-1 pr-4 text-gray-700">Step {st.stepNumber}</td>
                                        <td className="py-1 pr-4 text-gray-600 max-w-[16rem] truncate">{st.stepTitle || '—'}</td>
                                        <td className="py-1 pr-4 text-gray-700">{formatTime(st.timeSpentSec || 0)}</td>
                                        <td className="py-1 pr-4">
                                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full font-medium ${WORKLOAD_BADGE[lvl] || WORKLOAD_BADGE.low}`}>
                                            {lvl}
                                          </span>
                                        </td>
                                        <td className="py-1 pr-4">
                                          {adapted ? (
                                            <span className="text-orange-700 font-medium">Yes</span>
                                          ) : (
                                            <span className="text-gray-400">No</span>
                                          )}
                                        </td>
                                        <td className="py-1 pr-4 text-gray-700">{secOrDash(st.timeToAdaptationSec)}</td>
                                        <td className="py-1 pr-4 text-gray-700">
                                          {st.maxHighProba == null ? '—' : `${Math.round(st.maxHighProba * 100)}%`}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
            <div className="flex items-center justify-between mt-4">
              <div className="text-sm text-gray-600">
                Page {currentPage} of {totalPages}
              </div>
              <div className="space-x-2">
                <button
                  className="px-3 py-1 border rounded disabled:opacity-50"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                >
                  Previous
                </button>
                <button
                  className="px-3 py-1 border rounded disabled:opacity-50"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Analytics;