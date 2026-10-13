import { useCallback, useEffect, useRef, useState } from 'react';

export default function useCampaignReadiness(campaignId, payload, enabled) {
  const body = JSON.stringify(payload);
  const token = localStorage.getItem('token') || '';
  const key = JSON.stringify([campaignId, body, token]);
  const current = useRef(key);
  current.current = key;
  const generation = useRef(0);
  const controller = useRef(null);
  const [result, setResult] = useState(null);

  const refresh = useCallback(async (targetId = campaignId, values = null) => {
    if (!targetId || targetId === 'new' || targetId === 'new_campaign') return null;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const request = ++generation.current;
    const valid = () => !abort.signal.aborted && current.current === key
      && generation.current === request && (localStorage.getItem('token') || '') === token;
    setResult({ key, data: null, loading: true, error: '' });
    try {
      const response = await fetch(`/api/v1/outreach/campaigns/${targetId}/preflight`, {
        method: 'POST', credentials: 'include', signal: abort.signal,
        headers: { 'Content-Type': 'application/json', Authorization: token ? `Bearer ${token}` : '' },
        body: values ? JSON.stringify(values) : body,
      });
      const data = await response.json().catch(() => ({}));
      if (!valid()) return null;
      if (!response.ok || data.campaign_id !== targetId || typeof data.can_launch !== 'boolean'
          || !Array.isArray(data.checklist) || !Array.isArray(data.blockers)) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Launch checklist could not be verified.');
      }
      setResult({ key, data, loading: false, error: '' });
      return data;
    } catch (error) {
      if (valid()) setResult({ key, data: null, loading: false, error: error.message || 'Launch checklist could not be verified.' });
      return null;
    }
  }, [campaignId, body, key, token]);

  useEffect(() => {
    if (enabled) refresh();
    return () => { generation.current += 1; controller.current?.abort(); };
  }, [enabled, refresh]);

  const visible = result?.key === key ? result : null;
  return { data: visible?.data || null, loading: visible?.loading || false,
    error: visible?.error || '', refresh };
}
