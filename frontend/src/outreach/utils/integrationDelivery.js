const TERMINAL = new Set(['delivered', 'failed', 'cancelled', 'review_required', 'held_received', 'review_completed', 'dead_letter', 'unavailable']);

function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      reject(new DOMException('Cancelled', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort();
  });
}

export async function requestIntegrationTest(url, {
  signal, headers = {}, onQueued = () => {}, fetchImpl = fetch, intervalMs = 2000, maxPolls = 30,
} = {}) {
  const options = { credentials: 'include', headers, signal };
  const requestId = crypto.randomUUID();
  let response;
  let queued;
  try {
    response = await fetchImpl(url, { ...options, method: 'POST', headers: { ...headers, 'Idempotency-Key': requestId } });
    queued = await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    const uncertain = new Error('Could not confirm the request; it may still be queued.');
    uncertain.requestId = requestId;
    throw uncertain;
  }
  if (!response.ok || queued.status !== 'queued' || !queued.delivery_id) {
    throw new Error('The test could not be queued.');
  }
  onQueued();
  for (let i = 0; i < maxPolls; i += 1) {
    if (signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    try {
      const status = await fetchImpl(`/api/v1/outreach/integrations/deliveries/${encodeURIComponent(queued.delivery_id)}/status`, options);
      if (!status.ok) break;
      const result = await status.json();
      if (TERMINAL.has(result.status)) return result;
    } catch (error) {
      if (error.name === 'AbortError') throw error;
      break; // Losing status access does not prove a queued request failed.
    }
    if (i + 1 < maxPolls) await pause(intervalMs, signal);
  }
  return { id: queued.delivery_id, status: 'pending' };
}

export function integrationTestMessage(result) {
  if (result.status === 'review_completed') return {
    level: 'info', text: 'Operator review applied the saved delivery receipt. The connection remains paused.',
  };
  if (result.status === 'delivered') return { level: 'success', text: `Test delivered (HTTP ${result.status_code}).` };
  if (['review_required', 'held_received'].includes(result.status)) {
    return { level: 'warning', text: 'The delivery outcome needs review. It will not be resent automatically.' };
  }
  if (result.status === 'cancelled') return { level: 'info', text: 'Test cancelled because the connection or permission changed.' };
  if (['failed', 'dead_letter'].includes(result.status)) return { level: 'error', text: 'The destination did not confirm delivery.' };
  return { level: 'info', text: 'Delivery is still pending; success has not been confirmed.' };
}
