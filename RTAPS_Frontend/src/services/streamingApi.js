/**
 * Streaming backend API (eye-tracker ML pipeline).
 * Configure REACT_APP_STREAMING_API_URL (e.g. http://127.0.0.1:8000).
 */
export const STORAGE_STREAM_ID = 'rtaps_pupil_stream_id';
export const STORAGE_STREAMING_ENABLED = 'rtaps_streaming_enabled';

export function getStreamingBaseUrl() {
  const raw = process.env.REACT_APP_STREAMING_API_URL || 'http://127.0.0.1:8000';
  return raw.replace(/\/+$/, '');
}

async function streamingFetch(path, options = {}) {
  const url = `${getStreamingBaseUrl()}${path.startsWith('/') ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  if (res.status === 204) {
    return null;
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    data = { raw: text };
  }
  if (!res.ok) {
    const msg =
      typeof data?.detail === 'string'
        ? data.detail
        : data?.detail?.[0]?.msg || JSON.stringify(data) || res.statusText;
    throw new Error(msg);
  }
  return data;
}

export async function streamingHealth() {
  return streamingFetch('/health');
}

export async function streamingReady() {
  return streamingFetch('/ready');
}

/** Rich snapshot for dashboards (eye series + sliding window + prediction). */
export async function getSessionDashboard(streamId) {
  return streamingFetch(`/session/${encodeURIComponent(streamId)}/dashboard`);
}

export async function getSessionState(streamId) {
  return streamingFetch(`/session/${encodeURIComponent(streamId)}/state`);
}

export async function streamingSessionStart({ streamId, procedureId, participantId, nStepsTotal }) {
  return streamingFetch('/session/start', {
    method: 'POST',
    body: JSON.stringify({
      stream_id: streamId,
      procedure_id: procedureId,
      participant_id: participantId || undefined,
      n_steps_total: nStepsTotal ?? undefined,
    }),
  });
}

export async function streamingStepChange({ streamId, stepNumber, stepId }) {
  return streamingFetch('/session/step_change', {
    method: 'POST',
    body: JSON.stringify({
      stream_id: streamId,
      step_number: stepNumber,
      step_id: stepId ?? undefined,
    }),
  });
}

export async function streamingSessionEnd(streamId) {
  return streamingFetch('/session/end', {
    method: 'POST',
    body: JSON.stringify({ stream_id: streamId }),
  });
}

/**
 * Subscribe to prediction SSE. Returns a cleanup function.
 */
export function subscribePredictions(streamId, onMessage, onError) {
  const base = getStreamingBaseUrl();
  const url = `${base}/session/${encodeURIComponent(streamId)}/predictions/stream`;

  let closed = false;
  let es = null;
  try {
    es = new EventSource(url);
    es.onmessage = (ev) => {
      if (closed) return;
      try {
        const data = JSON.parse(ev.data);
        onMessage(data);
      } catch (e) {
        if (onError) onError(e);
      }
    };
    es.onerror = (e) => {
      if (onError) onError(e);
    };
  } catch (e) {
    if (onError) onError(e);
  }

  return () => {
    closed = true;
    if (es) {
      es.close();
    }
  };
}

export function getStoredStreamId() {
  try {
    return localStorage.getItem(STORAGE_STREAM_ID) || '';
  } catch (_) {
    return '';
  }
}

export function setStoredStreamId(id) {
  try {
    localStorage.setItem(STORAGE_STREAM_ID, id);
  } catch (_) {
    /* ignore */
  }
}

export function isStreamingIntegrationEnabled() {
  try {
    return localStorage.getItem(STORAGE_STREAMING_ENABLED) === '1';
  } catch (_) {
    return false;
  }
}

export function setStreamingIntegrationEnabled(on) {
  try {
    localStorage.setItem(STORAGE_STREAMING_ENABLED, on ? '1' : '0');
  } catch (_) {
    /* ignore */
  }
}
