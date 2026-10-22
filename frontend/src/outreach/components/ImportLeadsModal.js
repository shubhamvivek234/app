import React, { useState, useEffect, useRef, useMemo } from 'react';
import { createImportContextSession } from './importContextSession';
import {
  FileSpreadsheet, Search, Users, MessageSquare, Upload, ArrowRight, X, AlertCircle,
  CheckCircle2, Loader2, Shield, Sparkles, Calendar, Bookmark, ExternalLink,
  Check, Filter, ChevronDown, ThumbsUp, MessageCircle, Link, UserPlus, Info,
  RotateCcw, Play, Square, RefreshCw
} from 'lucide-react';

const readImportToken = () => {
  try { return localStorage.getItem('token'); } catch { return undefined; }
};

const LINKEDIN_SOURCING_CHANNELS = {
  basic: {
    id: 'basic',
    label: 'Basic LinkedIn Search',
    shortLabel: 'Basic Search',
    directUrl: 'https://www.linkedin.com/search/results/people/',
    directLabel: 'Open LinkedIn People Search ↗',
    maxProfiles: 1000,
    maxPages: 100,
    pageSize: 10,
    capSummary: 'Max 1,000 profiles (100 pages × 10/page)',
    placeholderUrl: 'https://www.linkedin.com/search/results/people/?keywords=ceo%20software',
    listPlaceholder: 'e.g. CEOs Canada software development',
    guidance:
      'LinkedIn displays up to 100 pages of 10 profiles (1,000 max). Narrow filters (Locations, Current Company, Title) if total results exceed 1,000.',
  },
  sales_nav: {
    id: 'sales_nav',
    label: 'LinkedIn Sales Navigator',
    shortLabel: 'Sales Navigator',
    directUrl: 'https://www.linkedin.com/sales/search/people',
    directLabel: 'Open Sales Navigator ↗',
    maxProfiles: 2500,
    maxPages: 99,
    pageSize: 25,
    capSummary: 'Max 2,500 profiles (99 pages × 25/page)',
    placeholderUrl: 'https://www.linkedin.com/sales/search/people?query=(filters:List())',
    listPlaceholder: 'e.g. Marketing Agency Founders US (Changed Jobs 90d)',
    guidance:
      'Sales Navigator displays up to 99 pages of 25 profiles (2,500 max). Add filters like "Changed jobs in last 90 days" or Geography to narrow below 2,500.',
  },
  recruiter: {
    id: 'recruiter',
    label: 'LinkedIn Recruiter / Pipeline',
    shortLabel: 'Recruiter / Lite',
    directUrl: 'https://www.linkedin.com/talent/',
    directLabel: 'Open LinkedIn Recruiter ↗',
    maxProfiles: 1000,
    maxPages: 40,
    pageSize: 25,
    capSummary: 'Max 1,000 profiles (40 pages × 25/page)',
    placeholderUrl: 'https://www.linkedin.com/talent/hire/12345/discover/recruiterSearch',
    listPlaceholder: 'e.g. Java Engineers LA 5+ yrs (Grad 1990-2000)',
    graduationBatches: ['1990-2000', '2001-2005', '2006-2010', '2011-2015', '2016-2020', '2021-Present'],
    guidance:
      'LinkedIn Recruiter displays up to 40 pages of 25 profiles (1,000 max). Supports Talent Pool Search and Project Pipeline tab URLs. Use Graduation Year batches to split pools >1,000.',
  },
  connections: {
    id: 'connections',
    label: 'My Network · 1st-Degree Connections',
    shortLabel: 'My Network (1st°)',
    directUrl: 'https://www.linkedin.com/mynetwork/invite-connect/connections/',
    batchingSearchUrl: 'https://www.linkedin.com/search/results/people/?network=%5B%22F%22%5D',
    directLabel: 'Open My Network Connections ↗',
    maxProfiles: 1000,
    maxPages: 100,
    pageSize: 10,
    capSummary: 'Max 1,000 profiles (Most Recent First)',
    placeholderUrl: 'https://www.linkedin.com/mynetwork/invite-connect/connections/',
    listPlaceholder: 'e.g. My Recent 1st-Degree Connections - Canada',
    locationBatches: ['United States', 'Canada', 'United Kingdom', 'Europe', 'APAC'],
    guidance:
      'Imports up to 1,000 1st-degree connections starting from your most recently added connections at the top. For >1,000 connections, use 1st-Degree Search Batching by location.',
  },
  events: {
    id: 'events',
    label: 'LinkedIn Event Attendees',
    shortLabel: 'Event Attendees',
    directUrl: 'https://www.linkedin.com/mynetwork/network-manager/events/',
    eventsSearchUrl: 'https://www.linkedin.com/search/results/events/',
    directLabel: 'Open My Attending Events ↗',
    maxProfiles: 1000,
    maxPages: 100,
    pageSize: 10,
    capSummary: 'Max 1,000 profiles (100 pages × 10/page)',
    placeholderUrl: 'https://www.linkedin.com/search/results/people/?eventAttending=%5B%22123456789%22%5D',
    listPlaceholder: 'e.g. SaaS Growth Summit Attendees - US Founders',
    eventBatches: ['United States', 'UK & Europe', 'Founders & C-Suite', 'VP & Directors'],
    guidance:
      'LinkedIn displays up to 100 pages of 10 event attendees (1,000 max). You must click "Attend" on the LinkedIn event first to unlock its attendee list. For >1,000 attendees, filter by Location or Title.',
  },
};

const classifyLinkedInSourceUrlClient = (rawUrl, fallbackChannel = 'basic') => {
  const trimmed = (rawUrl || '').trim();
  if (!trimmed) return { ...LINKEDIN_SOURCING_CHANNELS[fallbackChannel] || LINKEDIN_SOURCING_CHANNELS.basic, detected: false };
  const lower = trimmed.toLowerCase();
  if (lower.includes('/sales/lists/people')) {
    return { ...LINKEDIN_SOURCING_CHANNELS.sales_nav, detected: true, subLabel: 'Sales Navigator Saved Lead List' };
  }
  if (lower.includes('/sales/search/people') || lower.includes('/sales/')) {
    return { ...LINKEDIN_SOURCING_CHANNELS.sales_nav, detected: true, subLabel: 'Sales Navigator People Search' };
  }
  if (lower.includes('/talent/') && lower.includes('/pipeline')) {
    return { ...LINKEDIN_SOURCING_CHANNELS.recruiter, detected: true, subLabel: 'LinkedIn Recruiter · Project Pipeline Tab' };
  }
  if (lower.includes('/talent/')) {
    return { ...LINKEDIN_SOURCING_CHANNELS.recruiter, detected: true, subLabel: 'LinkedIn Recruiter · Talent Pool Search' };
  }
  if (lower.includes('/mynetwork/invite-connect/connections')) {
    return { ...LINKEDIN_SOURCING_CHANNELS.connections, detected: true, subLabel: 'My Network · Recent 1st-Degree Connections' };
  }
  if (lower.includes('/events/') || lower.includes('/mynetwork/network-manager/events') || lower.includes('eventattending')) {
    return { ...LINKEDIN_SOURCING_CHANNELS.events, detected: true, subLabel: 'LinkedIn Event Attendees Search' };
  }
  if (lower.includes('/search/results/people')) {
    const isFirstDegreeBatch = lower.includes('%22f%22') || lower.includes('"f"') || lower.includes('network=f');
    return {
      ...LINKEDIN_SOURCING_CHANNELS.basic,
      detected: true,
      isFirstDegreeBatch,
      subLabel: isFirstDegreeBatch ? 'Basic Search · 1st-Degree Connections Batch' : 'Basic LinkedIn People Search',
    };
  }
  return { ...LINKEDIN_SOURCING_CHANNELS[fallbackChannel] || LINKEDIN_SOURCING_CHANNELS.basic, detected: false };
};

export default function ImportLeadsModal({ isOpen, onClose, campaignId, onLeadsImported }) {
  const scope = useMemo(() => ({ isOpen, campaignId, token: readImportToken(), invalid: false }), [isOpen, campaignId]);
  const currentScopeRef = useRef(scope);
  currentScopeRef.current = scope;
  const [sessionHeld, setSessionHeld] = useState(false);
  const [readyScope, setReadyScope] = useState(null);
  const isScopeCurrent = () => {
    if (!scope.isOpen || currentScopeRef.current !== scope || scope.invalid) return false;
    if (scope.token === undefined || readImportToken() !== scope.token) {
      scope.invalid = true;
      setSessionHeld(true);
      return false;
    }
    return true;
  };
  const serverSession = () => {
    if (!scope.serverSession) scope.serverSession = createImportContextSession({
      campaignId, isCurrent: isScopeCurrent,
      headers: scope.token ? { Authorization: `Bearer ${scope.token}` } : {},
      onHold: () => { if (currentScopeRef.current === scope) { scope.invalid = true; setSessionHeld(true); } },
    });
    return scope.serverSession;
  };
  const scopedFetch = (...args) => serverSession().request(...args);
  useEffect(() => {
    currentScopeRef.current = scope;
    setSessionHeld(false);
    setReadyScope(null);
    if (scope.isOpen) isScopeCurrent();
    if (scope.isOpen && isScopeCurrent()) serverSession().bootstrap()
      .then(() => { if (isScopeCurrent()) setReadyScope(scope); }).catch(() => {});
    const check = () => {
      if (scope.isOpen && isScopeCurrent()) serverSession().verify().catch(() => {});
    };
    window.addEventListener('focus', check);
    window.addEventListener('storage', check);
    return () => {
      if (currentScopeRef.current === scope) currentScopeRef.current = null;
      window.removeEventListener('focus', check);
      window.removeEventListener('storage', check);
    };
    // Opening scope is immutable until close or campaign change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);
  // Step 1: Choose Source, Step 2: Input / URLs / CSV / Search / CRM, Step 3: Preview & Deduplication, Step 4: Complete
  const [step, setStep] = useState(1);
  const [sourceType, setSourceType] = useState('urls'); // 'urls' | 'csv' | 'search' | 'crm'
  const [sourceHint, setSourceHint] = useState('');
  const [crmLeads, setCrmLeads] = useState([]);
  const [crmEngageLists, setCrmEngageLists] = useState([]);
  const [crmSelectedListId, setCrmSelectedListId] = useState('');
  const [crmLoading, setCrmLoading] = useState(false);
  const [crmSearch, setCrmSearch] = useState('');
  const [crmLocationFilter, setCrmLocationFilter] = useState('');
  const [crmCompanySizeFilter, setCrmCompanySizeFilter] = useState('');
  const [crmConnectionDegree, setCrmConnectionDegree] = useState('');
  const [crmPostedRecently, setCrmPostedRecently] = useState(false);
  const [crmSelectedUrls, setCrmSelectedUrls] = useState([]);

  // Input states
  const [urlsText, setUrlsText] = useState('');
  const [csvContent, setCsvContent] = useState('');
  const [csvFileName, setCsvFileName] = useState('');
  const [defaultFirstName, setDefaultFirstName] = useState('');
  const [defaultCompanyName, setDefaultCompanyName] = useState('');
  const [importListName, setImportListName] = useState('');
  const [requireName, setRequireName] = useState(true);
  const [skipContacted, setSkipContacted] = useState(true);

  // Search extraction state
  const [searchUrl, setSearchUrl] = useState('');
  const [searchChannel, setSearchChannel] = useState('basic'); // 'basic' | 'sales_nav' | 'recruiter' | 'connections'
  const [selectedGradBatch, setSelectedGradBatch] = useState('');
  const [selectedLocationBatch, setSelectedLocationBatch] = useState('');
  const [selectedSenderId, setSelectedSenderId] = useState('');
  const [targetCount, setTargetCount] = useState(100);
  const [accounts, setAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [activeJob, setActiveJob] = useState(null);
  const [crawlLoading, setCrawlLoading] = useState(false);
  const [cancelingCrawl, setCancelingCrawl] = useState(false);
  const pollTimerRef = useRef(null);
  const jobScopeRef = useRef(campaignId);
  jobScopeRef.current = campaignId;
  const openRef = useRef(isOpen);
  openRef.current = isOpen;
  const importGenerationRef = useRef(0);
  const previewGenerationRef = useRef(0);

  // Preview & Ingest state
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult] = useState(null);
  const [stagedRows, setStagedRows] = useState([]);
  const [hasEdits, setHasEdits] = useState(false);
  const [reviewRequired, setReviewRequired] = useState(false);
  const [icpTitleFilter, setIcpTitleFilter] = useState('');
  const [icpLocationFilter, setIcpLocationFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sourceCapabilities, setSourceCapabilities] = useState(null);
  const [sourceCapabilityError, setSourceCapabilityError] = useState('');
  const basicSource = sourceCapabilities?.sources?.find((source) => source?.type === 'basic');
  const searchAvailable = basicSource?.collection_available === true && basicSource?.parser_supported === true;
  const searchUnavailableReason = sourceCapabilityError || basicSource?.reason || 'Checking search availability…';
  useEffect(() => {
    if (!isOpen) return undefined;
    const controller = new AbortController();
    setSourceCapabilities(null); setSourceCapabilityError('');
    const token = scope.token;
    const loadCapabilities = async () => {
      const response = await scopedFetch('/api/v1/outreach/leads/import-sources', {
        credentials: 'include', headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: controller.signal,
      });
      const body = await response.json();
      if (!isScopeCurrent()) return;
      if (!response.ok || body?.contract_version !== 1 || !Array.isArray(body.sources)
          || !body.sources.some((source) => source?.type === 'basic')
          || body.sources.some((source) => !source || typeof source.type !== 'string'
            || typeof source.collection_available !== 'boolean' || typeof source.parser_supported !== 'boolean' || typeof source.reason !== 'string')) {
        throw new Error('Search availability could not be confirmed. CSV and public profile imports remain available.');
      }
      if (isScopeCurrent() && !controller.signal.aborted) setSourceCapabilities(body);
    };
    loadCapabilities().catch(() => {
      if (isScopeCurrent() && !controller.signal.aborted) setSourceCapabilityError('Search availability could not be confirmed. CSV and public profile imports remain available.');
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, campaignId]);
  const [importResult, setImportResult] = useState(null);
  useEffect(() => {
    importGenerationRef.current += 1;
    previewGenerationRef.current += 1;
    setLoading(false);
    setPreviewLoading(false);
    setPreviewResult(null); setStagedRows([]); setHasEdits(false); setReviewRequired(false); setImportResult(null); setStep(1);
    setUrlsText(''); setCsvContent(''); setCsvFileName('');
    setDefaultFirstName(''); setDefaultCompanyName(''); setImportListName('');
    setSearchUrl(''); setSearchChannel('basic'); setSelectedGradBatch(''); setSelectedLocationBatch('');
    setSelectedSenderId(''); setAccounts([]); setActiveJob(null);
    setCrawlLoading(false); setCancelingCrawl(false); setError(null);
    return () => { importGenerationRef.current += 1; };
  }, [isOpen, campaignId]);


  useEffect(() => {
    if (!isOpen || !campaignId) return undefined;
    let current = true;
    setActiveJob(null);
    let savedReceiptId;
    try { savedReceiptId = sessionStorage.getItem(`unravler.import-receipt.${campaignId}`); } catch { savedReceiptId = null; }
    if (savedReceiptId) {
      const token = scope.token;
      scopedFetch(`/api/v1/outreach/leads/import-receipts/${encodeURIComponent(savedReceiptId)}?campaign_id=${encodeURIComponent(campaignId)}`, {
        credentials: 'include', headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).then(async (response) => {
        if (!response.ok) return;
        const receipt = await response.json();
        if (!isScopeCurrent() || !current) return;
        try { sessionStorage.removeItem(`unravler.import-receipt.${campaignId}`); } catch {}
        setImportResult(receipt);
        setStep(4);
      }).catch(() => {});
    }
    let saved;
    try { saved = sessionStorage.getItem(`unravler.search-job.${campaignId}`); } catch { return undefined; }
    if (!saved) return undefined;
    setActiveJob({ id: saved, campaign_id: campaignId, status: 'checking' });
    setSourceType('search'); setStep(2);
    const token = scope.token;
    scopedFetch(`/api/v1/outreach/leads/import-jobs/${encodeURIComponent(saved)}`, {
      credentials: 'include', headers: token ? { Authorization: `Bearer ${token}` } : {},
    }).then(async (response) => {
      if (!response.ok) throw new Error('Could not recover search status. Reopen the importer to try again.');
      const job = await response.json();
      if (!isScopeCurrent()) return;
      if (job.id !== saved || job.campaign_id !== campaignId) throw new Error('Search job context changed.');
      if (current && isScopeCurrent()) {
        setActiveJob((prior) => {
          if (!current || !isScopeCurrent() || prior?.id !== saved || jobScopeRef.current !== campaignId) return prior;
          return ['stopped', 'completed', 'failed'].includes(prior.status) ? prior : job;
        });
        setSourceType('search'); setStep(2);
      }
    }).catch((failure) => { if (current && isScopeCurrent()) setError(failure.message); });
    return () => { current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, campaignId]);

  useEffect(() => {
    if (!isOpen) return;
    const fetchAccounts = async () => {
      setAccountsLoading(true);
      try {
        const token = scope.token;
        const res = await scopedFetch('/api/v1/outreach/accounts', {
          credentials: 'include',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = await res.json();
          if (!isScopeCurrent()) return;
          const active = (Array.isArray(data) ? data : data.accounts || []).filter(
            (a) => a.status === 'active' && !a.is_deleted
          );
          setAccounts(active);
          if (active.length > 0) {
            setSelectedSenderId((prev) => prev || active[0].id);
          }
        }
      } catch (e) {
        // quiet fallback
      } finally {
        if (isScopeCurrent()) setAccountsLoading(false);
      }
    };
    fetchAccounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, campaignId]);

  const activeJobId = activeJob?.id;
  const activeJobStatus = activeJob?.status;

  useEffect(() => {
    if (!isOpen || !activeJobId) {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      return;
    }
    if (!['queued', 'crawling', 'checking'].includes(activeJobStatus)) {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      return;
    }

    let current = true;
    const poll = async () => {
      try {
        const token = scope.token;
        const res = await scopedFetch(`/api/v1/outreach/leads/import-jobs/${activeJobId}`, {
          credentials: 'include',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const updated = await res.json();
          if (!isScopeCurrent()) return;
          if (updated.id !== activeJobId || updated.campaign_id !== campaignId) throw new Error('Search job context changed.');
          if (current && isScopeCurrent()) setActiveJob((prior) => {
            if (!current || !isScopeCurrent() || prior?.id !== activeJobId || jobScopeRef.current !== campaignId) return prior;
            // A read started before cancellation cannot undo its confirmed terminal record.
            if (['stopped', 'completed', 'failed'].includes(prior.status)) return prior;
            return updated;
          });
        } else {
          if (current && isScopeCurrent()) setError('Search status is unavailable. Cancellation is not confirmed; monitoring continues.');
        }
      } catch (err) {
        if (current && isScopeCurrent()) setError('Search status is unavailable. Cancellation is not confirmed; monitoring continues.');
      }
    };

    pollTimerRef.current = setInterval(poll, 2000);
    return () => {
      current = false;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, activeJobId, activeJobStatus, campaignId]);

  if (!isOpen) return null;
  if (sessionHeld) return (
    <div role="dialog" aria-modal="true" aria-label="Import paused" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-w-md rounded-xl bg-white p-6">
        <p>Sign-in changed, or the workspace/import result could not be confirmed. Close and reopen the importer before reviewing or importing contacts.</p>
        <p className="mt-3 text-sm text-gray-600">Some rows may already be saved. Check the original campaign before retrying.</p>
        <button type="button" onClick={onClose} className="mt-4 rounded-lg border px-4 py-2">Close importer</button>
      </div>
    </div>
  );
  if (readyScope !== scope) return (
    <div role="dialog" aria-modal="true" aria-label="Checking import workspace" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="rounded-xl bg-white p-6"><p>Checking the import workspace…</p>
        <button type="button" onClick={onClose} className="mt-4 rounded-lg border px-4 py-2">Close importer</button></div>
    </div>
  );

  const handleFileUpload = (e) => {
    if (!isScopeCurrent()) return;
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError('CSV files must be smaller than 5 MB.');
      return;
    }
    setCsvFileName(file.name);
    const generation = ++previewGenerationRef.current;
    const isCurrent = () => isScopeCurrent() && openRef.current && jobScopeRef.current === campaignId && previewGenerationRef.current === generation;
    const reader = new FileReader();
    reader.onload = async (event) => {
      if (!isCurrent()) return;
      try { await serverSession().verify(); } catch { return; }
      if (!isCurrent()) return;
      setCsvContent(event.target.result);
      setError(null);
    };
    reader.onerror = () => { if (isCurrent()) setError('Could not read the CSV file. Please try again.'); };
    reader.readAsText(file);
  };

  const loadCrmLeads = async (engageListId = '') => {
    if (!isScopeCurrent()) return;
    setCrmLoading(true);
    setError(null);
    try {
      const token = scope.token;
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      if (engageListId) {
        const res = await scopedFetch(`/api/v1/outreach/engage/lists/${engageListId}/contacts`, {
          credentials: 'include',
          headers,
        });
        if (res.ok && isScopeCurrent()) {
          const data = await res.json();
          const contacts = (Array.isArray(data) ? data : data.contacts || []).filter((c) => c.linkedin_url);
          setCrmLeads(contacts);
          setCrmSelectedUrls(contacts.map((c) => c.linkedin_url));
        }
      } else {
        const [leadsRes, listsRes] = await Promise.all([
          scopedFetch('/api/v1/outreach/leads?limit=100', { credentials: 'include', headers }),
          scopedFetch('/api/v1/outreach/engage/lists', { credentials: 'include', headers }),
        ]);
        if (!isScopeCurrent()) return;
        if (listsRes.ok) {
          const listsData = await listsRes.json().catch(() => []);
          setCrmEngageLists(Array.isArray(listsData) ? listsData : []);
        }
        if (leadsRes.ok) {
          const leadsData = await leadsRes.json().catch(() => ({}));
          const rows = (Array.isArray(leadsData) ? leadsData : leadsData.leads || []).filter(
            (l) => l.linkedin_url && l.campaign_id !== campaignId
          );
          setCrmLeads(rows);
          setCrmSelectedUrls(rows.map((l) => l.linkedin_url));
        }
      }
    } catch (_) {
      // fallback quietly
    } finally {
      if (isScopeCurrent()) setCrmLoading(false);
    }
  };

  const handleRunPreview = async (overrideUrlsText) => {
    if (!isScopeCurrent()) return;
    if (!campaignId) {
      setError('Select a campaign before previewing contacts.');
      return;
    }
    const effectiveSource = typeof overrideUrlsText === 'string' ? 'urls' : sourceType;
    const rawText =
      typeof overrideUrlsText === 'string'
        ? overrideUrlsText.trim()
        : effectiveSource === 'urls'
        ? urlsText.trim()
        : csvContent.trim();
    if (!rawText) {
      setError(effectiveSource === 'urls' ? 'Please paste at least one LinkedIn profile URL.' : 'Please upload or paste CSV content.');
      return;
    }

    setPreviewLoading(true);
    setError(null);
    const generation = ++previewGenerationRef.current;
    const isCurrent = () => isScopeCurrent() && openRef.current && jobScopeRef.current === campaignId && previewGenerationRef.current === generation;
    try {
      const token = scope.token;
      const res = await scopedFetch('/api/v1/outreach/leads/preview', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          campaign_id: campaignId,
          source_type: effectiveSource === 'urls' ? 'pasted_urls' : 'csv',
          raw_text: rawText,
          default_first_name: defaultFirstName.trim() || null,
          default_company_name: defaultCompanyName.trim() || null,
          skip_already_contacted: skipContacted,
          skip_do_not_contact: true,
          require_name: requireName,
        }),
      });

      const data = await res.json();
      if (!isScopeCurrent()) return;
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to preview leads.');
      }
      if (!isCurrent()) return;
      setPreviewResult(data);
      setStagedRows(data.rows || []);
      setHasEdits(false);
      setReviewRequired(false);
      setStep(3);
    } catch (err) {
      if (isCurrent()) setError(err.message);
    } finally {
      if (isCurrent()) setPreviewLoading(false);
    }
  };

  const handleNameChange = (rowNumber, newName) => {
    if (!isScopeCurrent()) return;
    setStagedRows((prev) =>
      prev.map((r) => {
        if (r.row_number === rowNumber) {
          return {
            ...r,
            cleaned_first_name: newName,
            first_name: newName,
            is_custom_edited: true,
          };
        }
        return r;
      })
    );
    setHasEdits(true);
    // Search-job commits revalidate their original staged records on the server.
    // Direct CSV/profile edits use the separate preview-staged contract.
    setReviewRequired(sourceType !== 'search');
  };

  const handleRevertName = (rowNumber) => {
    const original = stagedRows.find((row) => row.row_number === rowNumber)?.raw_first_name || '';
    handleNameChange(rowNumber, original);
  };

  const evaluateRowIcp = (row) => {
    const titleTokens = icpTitleFilter.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean);
    const locTokens = icpLocationFilter.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean);
    if (!titleTokens.length && !locTokens.length) return { active: false, matches: true, reason: '' };
    if (titleTokens.length) {
      const hay = `${row.job_title || ''} ${row.headline || ''} ${row.company_name || ''}`.toLowerCase();
      if (!titleTokens.some((tok) => hay.includes(tok))) {
        return { active: true, matches: false, reason: 'Wrong job title' };
      }
    }
    if (locTokens.length) {
      const locHay = `${row.location || ''} ${row.country_code || ''} ${row.company_location || ''}`.toLowerCase();
      if (!locTokens.some((tok) => locHay.includes(tok))) {
        return { active: true, matches: false, reason: 'Location mismatch' };
      }
    }
    return { active: true, matches: true, reason: 'Matches ICP' };
  };

  const handleRemoveStagedRow = (rowNumber) => {
    if (!isScopeCurrent()) return;
    setStagedRows((prev) => {
      const next = prev.filter((r) => r.row_number !== rowNumber);
      const validRemaining = next.filter((r) => r.status === 'valid').length;
      setPreviewResult((prior) => prior ? {
        ...prior,
        valid_count: validRemaining,
        total_submitted: next.length,
        rows: next,
      } : prior);
      return next;
    });
    setHasEdits(true);
  };

  const handleRemoveNonMatchingIcp = () => {
    if (!isScopeCurrent()) return;
    setStagedRows((prev) => {
      const next = prev.filter((r) => evaluateRowIcp(r).matches);
      const validRemaining = next.filter((r) => r.status === 'valid').length;
      setPreviewResult((prior) => prior ? {
        ...prior,
        valid_count: validRemaining,
        total_submitted: next.length,
        rows: next,
      } : prior);
      return next;
    });
    setHasEdits(true);
  };

  const handleValidateChanges = async () => {
    if (!isScopeCurrent()) return;
    if (previewLoading || loading || sourceType === 'search') return;
    setPreviewLoading(true); setError(null);
    const generation = ++previewGenerationRef.current;
    const isCurrent = () => isScopeCurrent() && openRef.current && jobScopeRef.current === campaignId && previewGenerationRef.current === generation;
    try {
      const token = scope.token;
      const response = await scopedFetch('/api/v1/outreach/leads/preview-staged', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json', Authorization: token ? `Bearer ${token}` : '' },
        body: JSON.stringify({ campaign_id: campaignId, leads: stagedRows, require_name: requireName,
          skip_already_contacted: skipContacted, skip_do_not_contact: true }),
      });
      const body = await response.json();
      if (!isScopeCurrent()) return;
      if (!response.ok) throw new Error(body.detail || 'Could not validate the edited contacts.');
      if (!isCurrent()) return;
      setPreviewResult(body); setStagedRows(body.rows || []); setReviewRequired(false);
    } catch (failure) {
      if (isCurrent()) setError(failure.message || 'Could not validate the edited contacts.');
    } finally {
      if (isCurrent()) setPreviewLoading(false);
    }
  };

  const handleStartSearchCrawl = async () => {
    if (!isScopeCurrent()) return;
    if (!searchAvailable) { setError(searchUnavailableReason); return; }
    if (!campaignId) {
      setError('Select a campaign before importing contacts.');
      return;
    }
    if (!searchUrl.trim()) {
      setError('Please enter a valid LinkedIn search or Sales Navigator URL.');
      return;
    }
    if (!selectedSenderId) {
      setError('Please select a sender account to perform this search extraction.');
      return;
    }

    setCrawlLoading(true);
    setError(null);
    try {
      const token = scope.token;
      const classified = classifyLinkedInSourceUrlClient(searchUrl.trim(), searchChannel);
      const effectiveSearchType = classified.id || searchChannel || 'basic';
      const maxAllowed = classified.maxProfiles || (effectiveSearchType === 'sales_nav' ? 2500 : 1000);
      const clampedLeads = Math.max(1, Math.min(Number(targetCount) || 100, maxAllowed));
      const res = await scopedFetch('/api/v1/outreach/leads/import-search', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          campaign_id: campaignId,
          search_url: searchUrl.trim(),
          search_type: effectiveSearchType,
          sender_account_id: selectedSenderId,
          max_leads: clampedLeads,
          ...(importListName.trim() ? { list_name: importListName.trim() } : {}),
        }),
      });
      const data = await res.json();
      if (!isScopeCurrent()) return;
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to start search import.');
      }
      setActiveJob(data);
      try { sessionStorage.setItem(`unravler.search-job.${campaignId}`, data.id); }
      catch { setError('Search started, but this browser cannot remember it after reload. Keep this importer open.'); }
    } catch (err) {
      if (isScopeCurrent()) setError(err.message);
    } finally {
      if (isScopeCurrent()) setCrawlLoading(false);
    }
  };

  const handleCancelCrawl = async () => {
    if (!isScopeCurrent()) return;
    if (!activeJob?.id || cancelingCrawl) return;
    const jobId = activeJob.id;
    setCancelingCrawl(true); setError(null);
    try {
      const token = scope.token;
      const response = await scopedFetch(`/api/v1/outreach/leads/import-jobs/${jobId}/cancel`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || 'Cancellation was not confirmed. Monitoring continues.');
      // Confirm the full current server record; a successful POST alone is not a local stop.
      const statusResponse = await scopedFetch(`/api/v1/outreach/leads/import-jobs/${jobId}`, {
        credentials: 'include', headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (!statusResponse.ok) throw new Error('Cancellation was requested, but its outcome is not confirmed. Monitoring continues.');
      const job = await statusResponse.json();
      if (!isScopeCurrent()) return;
      if (job.id !== jobId || job.campaign_id !== campaignId) throw new Error('Search job context changed.');
      setActiveJob((prior) => isScopeCurrent() && prior?.id === jobId && jobScopeRef.current === campaignId ? job : prior);
      if (!['stopped', 'completed', 'failed'].includes(job.status)) setError('Cancellation is not confirmed yet. Monitoring continues.');
    } catch (err) {
      if (isScopeCurrent()) setError(err.message || 'Cancellation was not confirmed. Monitoring continues.');
    } finally {
      if (isScopeCurrent()) setCancelingCrawl(false);
    }
  };

  const handleReviewStagedLeads = async () => {
    if (!isScopeCurrent()) return;
    if (!activeJob?.id) return;
    setPreviewLoading(true);
    setError(null);
    try {
      const token = scope.token;
      const res = await scopedFetch(`/api/v1/outreach/leads/import-jobs/${activeJob.id}/staged`, {
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const data = await res.json();
      if (!isScopeCurrent()) return;
      if (!res.ok) throw new Error(data.detail || 'Could not load staged leads.');
      const leads = data.leads || [];
      const rows = leads.map((l, idx) => ({
        row_number: idx + 1,
        id: l.id,
        first_name: l.first_name,
        cleaned_first_name: l.first_name,
        raw_first_name: l.first_name,
        last_name: l.last_name || '',
        company_name: l.company_name || '',
        linkedin_url: l.linkedin_url || '',
        raw_url: l.linkedin_url || '',
        vanity_name: l.identifiers?.vanity_name,
        status: 'valid',
      }));
      setStagedRows(rows);
      setPreviewResult({
        total_submitted: (activeJob.leads_imported || 0) + (activeJob.duplicates_skipped || 0) + (activeJob.dnc_suppressed || 0) + (activeJob.unresolvable_skipped || 0),
        valid_count: rows.length,
        duplicate_count: activeJob.duplicates_skipped || 0,
        contacted_count: 0,
        dnc_count: activeJob.dnc_suppressed || 0,
        invalid_count: activeJob.unresolvable_skipped || 0,
        rows,
      });
      setStep(3);
    } catch (err) {
      if (isScopeCurrent()) setError(err.message);
    } finally {
      if (isScopeCurrent()) setPreviewLoading(false);
    }
  };

  const handleExecuteImport = async () => {
    if (!isScopeCurrent()) return;
    if (reviewRequired || previewLoading) { setError('Validate the changed contacts before confirming this import.'); return; }
    if (sourceType === 'search' && !searchAvailable) { setError(searchUnavailableReason); return; }
    if (!campaignId) {
      setError('Select a campaign before importing contacts.');
      return;
    }
    setLoading(true);
    setError(null);
    const importGeneration = ++importGenerationRef.current;
    try {
      const token = scope.token;
      let res;

      if (sourceType === 'search' && activeJob) {
        const nameOverrides = {};
        stagedRows.forEach((r) => {
          if (r.is_custom_edited && typeof r.cleaned_first_name === 'string') {
            nameOverrides[r.id] = r.cleaned_first_name;
          }
        });
        let enrolled = 0;
        let rejected = 0;
        for (let offset = 0; offset < stagedRows.length; offset += 1000) {
          if (!isScopeCurrent() || !openRef.current || jobScopeRef.current !== campaignId || importGenerationRef.current !== importGeneration) return;
          const batch = stagedRows.slice(offset, offset + 1000);
          res = await scopedFetch(`/api/v1/outreach/leads/import-jobs/${activeJob.id}/commit`, {
            method: 'POST', credentials: 'include',
            headers: { 'Content-Type': 'application/json', Authorization: token ? `Bearer ${token}` : '' },
            body: JSON.stringify({ selected_lead_ids: batch.map((row) => row.id),
              ...(importListName.trim() ? { list_name: importListName.trim() } : {}),
              name_overrides: Object.fromEntries(batch.filter((row) => Object.prototype.hasOwnProperty.call(nameOverrides, row.id))
                .map((row) => [row.id, nameOverrides[row.id]])) }),
          });
          const data = await res.json();
          if (!isScopeCurrent()) return;
          if (!res.ok) throw new Error(data.detail || 'Import interrupted.');
          if (!isScopeCurrent() || !openRef.current || jobScopeRef.current !== campaignId || importGenerationRef.current !== importGeneration) return;
          enrolled += data.enrolled_count || 0;
          rejected += (data.rejections || []).length;
          if (onLeadsImported) onLeadsImported(data);
        }
        setImportResult({
          imported_count: enrolled, attempt_only: true,
          duplicates_count: activeJob.duplicates_skipped || 0,
          skipped_count: rejected + (activeJob.dnc_suppressed || 0) + (activeJob.unresolvable_skipped || 0),
        });
        return;
      }

      const requestId = (typeof globalThis.crypto?.randomUUID === 'function')
        ? globalThis.crypto.randomUUID()
        : `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
      try { sessionStorage.setItem(`unravler.import-receipt.${campaignId}`, requestId); } catch {}

      if (hasEdits) {
        res = await scopedFetch('/api/v1/outreach/leads/import-staged', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({
            campaign_id: campaignId,
            leads: stagedRows,
            list_name: importListName.trim() || null,
            skip_already_contacted: skipContacted,
            skip_do_not_contact: true,
            require_name: requireName,
            consent_basis: 'user_provided',
            request_id: requestId,
          }),
        });
      } else if (sourceType === 'urls') {
        res = await scopedFetch('/api/v1/outreach/leads/import-urls', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({
            campaign_id: campaignId,
            urls_text: urlsText,
            default_first_name: defaultFirstName.trim() || null,
            default_company_name: defaultCompanyName.trim() || null,
            list_name: importListName.trim() || null,
            skip_already_contacted: skipContacted,
            skip_do_not_contact: true,
            require_name: requireName,
            consent_basis: 'user_provided',
            request_id: requestId,
          }),
        });
      } else {
        res = await scopedFetch('/api/v1/outreach/leads/import-csv', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({
            campaign_id: campaignId,
            csv_text: csvContent,
            default_first_name: defaultFirstName.trim() || null,
            default_company_name: defaultCompanyName.trim() || null,
            list_name: importListName.trim() || null,
            skip_already_contacted: skipContacted,
            skip_do_not_contact: true,
            require_name: requireName,
            consent_basis: 'user_provided',
            request_id: requestId,
          }),
        });
      }

      const data = await res.json();
      if (!isScopeCurrent()) return;
      if (!res.ok) {
        try { sessionStorage.removeItem(`unravler.import-receipt.${campaignId}`); } catch {}
        throw new Error(data.detail || 'Import failed.');
      }
      try { sessionStorage.removeItem(`unravler.import-receipt.${campaignId}`); } catch {}
      if (!isScopeCurrent() || !openRef.current || jobScopeRef.current !== campaignId || importGenerationRef.current !== importGeneration) return;
      setImportResult(data);
      if (onLeadsImported) onLeadsImported(data);
    } catch (err) {
      if (isScopeCurrent() && importGenerationRef.current === importGeneration) {
        setError(sourceType === 'search'
          ? `${err.message || 'Import interrupted.'} Some rows may already be saved. Review or retry the same staged rows to finish.`
          : err.message);
      }
    } finally {
      if (isScopeCurrent() && importGenerationRef.current === importGeneration) setLoading(false);
    }
  };

  const resetAll = () => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setStep(1);
    setSourceType('urls');
    setUrlsText('');
    setCsvContent('');
    setCsvFileName('');
    setDefaultFirstName('');
    setDefaultCompanyName('');
    setImportListName('');
    setSearchUrl('');
    setActiveJob(null);
    setPreviewResult(null);
    setStagedRows([]);
    setHasEdits(false);
    setReviewRequired(false);
    setImportResult(null);
    setError(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-3xl rounded-2xl bg-white shadow-2xl border border-gray-100 transition-all flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-600">
                LinkedIn Outbound · Lead Intake Engine
              </span>
              <span className="text-[10px] bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded-full">
                {importResult ? 'Complete' : `Step ${step} of 3`}
              </span>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mt-0.5">
              {importResult ? 'Import Results' : (
                step === 1 ? 'Choose Lead Sourcing Method' :
                step === 2 ? (
                  sourceType === 'urls' ? 'Paste LinkedIn Profile URLs' :
                  sourceType === 'csv' ? 'Upload CSV Spreadsheet' :
                  activeJob ? 'Infusing Leads from Search URL' : 'LinkedIn & Sales Nav Lead Infusion'
                ) :
                'Validation Preview & Deduplication'
              )}
            </h2>
          </div>
          <button
            onClick={() => { resetAll(); onClose(); }}
            className="rounded-full p-1.5 text-gray-400 hover:bg-gray-100 transition-colors"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mx-6 mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 border border-red-200">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1">
          {/* ── STEP 1: Sourcing Choices ────────────────────────────────────────── */}
          {step === 1 && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">
                Select your prospect intake channel. In accordance with safety policies, automated scraping is disabled and verified manual imports are supported:
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {/* 1. Paste LinkedIn Profile URLs (ACTIVE) */}
                <button
                  type="button"
                  onClick={() => { setSourceHint(''); setSourceType('urls'); setStep(2); }}
                  className="text-left p-4 rounded-xl border-2 border-indigo-500 bg-indigo-50/20 hover:bg-indigo-50/40 transition-all group relative cursor-pointer"
                >
                  <div className="absolute top-3 right-3 flex items-center gap-1 bg-indigo-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-full shadow-xs">
                    <Check className="h-3 w-3" /> Recommended
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-indigo-600 text-white shadow-sm">
                      <Link className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Paste LinkedIn profile URLs</h4>
                      <p className="text-xs text-gray-600 mt-0.5">Quickly paste profile links with optional names and titles</p>
                    </div>
                  </div>
                </button>

                {/* 2. CSV File (ACTIVE) */}
                <button
                  type="button"
                  onClick={() => { setSourceHint(''); setSourceType('csv'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group cursor-pointer"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-violet-100 text-violet-700 group-hover:bg-violet-600 group-hover:text-white transition-colors">
                      <FileSpreadsheet className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Import from CSV file</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Upload a .csv spreadsheet with custom columns & tags</p>
                    </div>
                  </div>
                </button>

                {/* Search uses the same availability contract as API/workers. */}
                <button
                  type="button"
                  disabled={!searchAvailable}
                  onClick={() => { setSourceHint(''); setSourceType('search'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group cursor-pointer relative"
                >
                  <div className="absolute top-3 right-3 flex items-center gap-1 bg-emerald-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-full shadow-xs">
                    <Info className="h-3 w-3" /> {searchAvailable ? 'Search import' : 'Unavailable'}
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-indigo-100 text-indigo-700 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                      <Search className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">LinkedIn & Sales Nav Search</h4>
                      <p className="text-xs text-gray-500 mt-0.5">{searchAvailable ? 'Review supported search results before enrolling contacts' : searchUnavailableReason}</p>
                    </div>
                  </div>
                </button>

                {/* 4. Interactive Lead Finder / Workspace CRM & Engage Lists */}
                <button
                  type="button"
                  onClick={() => {
                    setSourceHint('');
                    setSourceType('crm');
                    setCrmSelectedListId('');
                    setStep(2);
                    loadCrmLeads('');
                  }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group relative cursor-pointer"
                >
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-full">
                    Workspace CRM & Lists
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-amber-100 text-amber-700 group-hover:bg-amber-600 group-hover:text-white transition-colors">
                      <Sparkles className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Interactive Lead Finder</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Select prospects from your Workspace CRM or Engage Warm-Up Lists</p>
                    </div>
                  </div>
                </button>

                {/* 5. LinkedIn Event (Manual URL Import with Event Attendance Rule & Batching) */}
                <button
                  type="button"
                  onClick={() => { setSourceHint('event'); setSearchChannel('events'); setSourceType('urls'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group relative cursor-pointer"
                >
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-sky-800 bg-sky-50 border border-sky-200 px-2 py-0.5 rounded-full">
                    100p × 10 · Max 1,000
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-sky-100 text-sky-700 group-hover:bg-sky-600 group-hover:text-white transition-colors">
                      <Calendar className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">LinkedIn Event attendees</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Click &apos;Attend&apos; on any LinkedIn Event to unlock up to 1,000 attendees</p>
                    </div>
                  </div>
                </button>

                {/* 6. Post Engagers (Manual URL Import with Scraping disabled notice) */}
                <button
                  type="button"
                  onClick={() => { setSourceHint('post'); setSourceType('urls'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group relative cursor-pointer"
                >
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-gray-600 bg-gray-100 border border-gray-200 px-2 py-0.5 rounded-full">
                    Scraping disabled · Paste URLs
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-rose-100 text-rose-700 group-hover:bg-rose-600 group-hover:text-white transition-colors">
                      <MessageSquare className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">LinkedIn Post Engagers</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Commenter/liker scraping disabled for safety — click to paste engager URLs</p>
                    </div>
                  </div>
                </button>

                {/* 7. LinkedIn Recruiter / Recruiter Lite & Pipeline */}
                <button
                  type="button"
                  onClick={() => {
                    setSourceHint('recruiter');
                    setSearchChannel('recruiter');
                    setSourceType('urls');
                    setStep(2);
                  }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group relative cursor-pointer"
                >
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-teal-800 bg-teal-50 border border-teal-200 px-2 py-0.5 rounded-full">
                    40p × 25 · Max 1,000
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-teal-100 text-teal-700 group-hover:bg-teal-600 group-hover:text-white transition-colors">
                      <Bookmark className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">LinkedIn Recruiter & Pipeline</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Talent Pool search, Project Pipeline tab & Graduation Year batching</p>
                    </div>
                  </div>
                </button>

                {/* 8. My Network · Recent 1st-Degree Connections */}
                <button
                  type="button"
                  onClick={() => {
                    setSourceHint('connections');
                    setSearchChannel('connections');
                    setSourceType('crm');
                    setCrmConnectionDegree('1st');
                    setCrmSelectedListId('');
                    setStep(2);
                    loadCrmLeads('');
                  }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group relative cursor-pointer"
                >
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                    Recent 1,000 · 1st°
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-emerald-100 text-emerald-700 group-hover:bg-emerald-600 group-hover:text-white transition-colors">
                      <Users className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">My Network · 1st-Degree Connections</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Add recent 1st-degree connections (top 1,000) or batch >1,000 by location</p>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 2: Input / Configuration ───────────────────────────────────── */}
          {step === 2 && sourceType === 'urls' && (
            <div className="space-y-4">
              {sourceHint && (sourceHint === 'event' || sourceHint === 'post') && (
                <div className="rounded-xl border border-sky-200 bg-sky-50/80 p-3 text-xs text-sky-900">
                  <strong>{sourceHint === 'event' ? 'LinkedIn Event Attendees:' : 'LinkedIn Post Engagers:'}</strong> Automated scraping is disabled for account safety. Paste your exported {sourceHint === 'event' ? 'event attendee' : 'post engager'} LinkedIn profile URLs below (one per line) to validate and enroll them.
                </div>
              )}

              {/* Dripify 4-Channel LinkedIn Sourcing Guide & Direct Links */}
              <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3.5 space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {Object.values(LINKEDIN_SOURCING_CHANNELS).map((ch) => (
                      <button
                        key={ch.id}
                        type="button"
                        onClick={() => setSearchChannel(ch.id)}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-colors cursor-pointer ${
                          searchChannel === ch.id
                            ? 'bg-indigo-600 text-white shadow-2xs'
                            : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
                        }`}
                      >
                        {ch.shortLabel}
                      </button>
                    ))}
                  </div>
                  <a
                    href={(LINKEDIN_SOURCING_CHANNELS[searchChannel] || LINKEDIN_SOURCING_CHANNELS.basic).directUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-lg bg-[#0A66C2] px-2.5 py-1 text-[11px] font-bold text-white hover:bg-[#004182] transition-colors"
                  >
                    {(LINKEDIN_SOURCING_CHANNELS[searchChannel] || LINKEDIN_SOURCING_CHANNELS.basic).directLabel}
                  </a>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-indigo-950">
                  <span>{(LINKEDIN_SOURCING_CHANNELS[searchChannel] || LINKEDIN_SOURCING_CHANNELS.basic).guidance}</span>
                  <span className="shrink-0 rounded-full bg-indigo-100 px-2.5 py-0.5 font-bold text-indigo-800">
                    {(LINKEDIN_SOURCING_CHANNELS[searchChannel] || LINKEDIN_SOURCING_CHANNELS.basic).capSummary}
                  </span>
                </div>

                {/* Recruiter Graduation Year Batching Helper (Video 3: vthZrZVpv_g) */}
                {searchChannel === 'recruiter' && (
                  <div className="pt-2 border-t border-indigo-200/60 space-y-1.5">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-bold text-teal-900">
                        Recruiter &gt;1,000 Pool Split · Graduation Year Batching:
                      </span>
                      <span className="text-gray-500">40 pages × 25 profiles = 1,000 max per batch</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {LINKEDIN_SOURCING_CHANNELS.recruiter.graduationBatches.map((batch) => (
                        <button
                          key={batch}
                          type="button"
                          onClick={() => {
                            setSelectedGradBatch(batch);
                            setImportListName((prev) => {
                              const base = prev.replace(/\s*\(Grad [^)]+\)\s*$/, '').trim() || 'Recruiter Candidates';
                              return `${base} (Grad ${batch})`;
                            });
                          }}
                          className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border cursor-pointer transition-colors ${
                            selectedGradBatch === batch
                              ? 'bg-teal-600 text-white border-teal-600'
                              : 'bg-white text-teal-800 border-teal-200 hover:bg-teal-50'
                          }`}
                        >
                          Grad {batch}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* My Network >1,000 1st-Degree Connections Batching Helper (Video 4: lSzIo2t-8E4) */}
                {searchChannel === 'connections' && (
                  <div className="pt-2 border-t border-indigo-200/60 space-y-1.5">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                      <span className="font-bold text-emerald-900">
                        Have &gt;1,000 1st-Degree Connections? Split into Location Batches:
                      </span>
                      <a
                        href={LINKEDIN_SOURCING_CHANNELS.connections.batchingSearchUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-bold text-emerald-700 hover:text-emerald-900 underline"
                      >
                        Open LinkedIn Search Pre-Filtered to 1st-Degree ↗
                      </a>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {LINKEDIN_SOURCING_CHANNELS.connections.locationBatches.map((loc) => (
                        <button
                          key={loc}
                          type="button"
                          onClick={() => {
                            setSelectedLocationBatch(loc);
                            setImportListName(`My Connections - ${loc}`);
                          }}
                          className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border cursor-pointer transition-colors ${
                            selectedLocationBatch === loc
                              ? 'bg-emerald-600 text-white border-emerald-600'
                              : 'bg-white text-emerald-800 border-emerald-200 hover:bg-emerald-50'
                          }`}
                        >
                          1st° · {loc}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* LinkedIn Event Attendees >1,000 Split & Attendance Rule Helper (Video 6: OrWYt0ZNB-g) */}
                {searchChannel === 'events' && (
                  <div className="pt-2 border-t border-indigo-200/60 space-y-1.5">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                      <span className="font-bold text-sky-900">
                        Step 1: Click &ldquo;Attend&rdquo; on the LinkedIn Event first · Step 2: Open Attendees &amp; Filter if &gt;1,000:
                      </span>
                      <a
                        href={LINKEDIN_SOURCING_CHANNELS.events.eventsSearchUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-bold text-sky-700 hover:text-sky-900 underline"
                      >
                        Find Upcoming LinkedIn Events ↗
                      </a>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {LINKEDIN_SOURCING_CHANNELS.events.eventBatches.map((batch) => (
                        <button
                          key={batch}
                          type="button"
                          onClick={() => {
                            setSelectedLocationBatch(batch);
                            setImportListName(`Event Attendees - ${batch}`);
                          }}
                          className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border cursor-pointer transition-colors ${
                            selectedLocationBatch === batch
                              ? 'bg-sky-600 text-white border-sky-600'
                              : 'bg-white text-sky-800 border-sky-200 hover:bg-sky-50'
                          }`}
                        >
                          Event · {batch}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div>
                <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                  <label className="block text-xs font-bold uppercase tracking-wider text-gray-700">
                    Paste LinkedIn Profile URLs (One per line)
                  </label>
                  <span className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-md">
                    Supports Standard (/in/), Sales Navigator (/sales/lead/) &amp; Recruiter (/talent/profile/) URLs
                  </span>
                </div>
                <p className="text-xs text-gray-500 mb-2">
                  Right-click &ldquo;Copy Link Address&rdquo; from Regular Search, Sales Navigator, Recruiter, or a Profile page. Format: <code className="bg-gray-100 px-1 py-0.5 rounded text-gray-800">URL, First, Last, Company</code> or <code className="bg-gray-100 px-1 py-0.5 rounded text-gray-800">URL</code>
                </p>
                <textarea
                  rows={6}
                  disabled={previewLoading}
                  value={urlsText}
                  onChange={(e) => setUrlsText(e.target.value)}
                  placeholder={`https://www.linkedin.com/in/williamhgates, Bill Gates, Breakthrough Energy\nhttps://www.linkedin.com/sales/lead/ACwAAB12345, Satya, Nadella, Microsoft\nhttps://www.linkedin.com/talent/profile/ACwAAC67890, Sundar Pichai`}
                  className="w-full rounded-xl border border-gray-300 p-3 font-mono text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-gray-50/50"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-gray-700 mb-1">
                  Lead List Name / Cohort Tag (Optional)
                </label>
                <input
                  type="text"
                  value={importListName}
                  disabled={previewLoading}
                  onChange={(e) => setImportListName(e.target.value)}
                  placeholder={(LINKEDIN_SOURCING_CHANNELS[searchChannel] || LINKEDIN_SOURCING_CHANNELS.basic).listPlaceholder}
                  aria-label="Lead list name"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                    Fallback First Name (Optional)
                  </label>
                  <input
                    type="text"
                    value={defaultFirstName}
                    disabled={previewLoading}
                    onChange={(e) => setDefaultFirstName(e.target.value)}
                    placeholder="e.g. there, Colleague, Founder"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                  <span className="text-[10px] text-gray-400 mt-0.5 block">Applied when a profile line does not specify a name.</span>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                    Fallback Company (Optional)
                  </label>
                  <input
                    type="text"
                    value={defaultCompanyName}
                    disabled={previewLoading}
                    onChange={(e) => setDefaultCompanyName(e.target.value)}
                    placeholder="e.g. Your Company"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                  <span className="text-[10px] text-gray-400 mt-0.5 block">Applied when a line does not specify a company.</span>
                </div>
              </div>

              <div className="pt-2 flex items-center justify-between border-t border-gray-100">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={requireName}
                    disabled={previewLoading}
                    onChange={(e) => setRequireName(e.target.checked)}
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-xs font-medium text-gray-700">Require name for outreach personalization</span>
                </label>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  disabled={previewLoading}
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium cursor-pointer"
                >
                  ← Back to Sources
                </button>
                <button
                  type="button"
                  onClick={() => handleRunPreview()}
                  disabled={previewLoading || !urlsText.trim()}
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {previewLoading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Validating Leads...
                    </>
                  ) : (
                    <>
                      Validate & Preview <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {step === 2 && sourceType === 'crm' && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700">
                    Select Prospects from Workspace CRM or Engage Lists
                  </h4>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Pick existing leads or warm-up cohort contacts to validate and enroll into this campaign.
                  </p>
                </div>
                {crmEngageLists.length > 0 && (
                  <select
                    value={crmSelectedListId}
                    onChange={(e) => {
                      const nextListId = e.target.value;
                      setCrmSelectedListId(nextListId);
                      loadCrmLeads(nextListId);
                    }}
                    className="rounded-lg border border-gray-300 px-2.5 py-1.5 text-xs bg-white text-gray-700"
                  >
                    <option value="">All Workspace Leads</option>
                    {crmEngageLists.map((lst) => (
                      <option key={lst.id} value={lst.id}>
                        Engage List: {lst.name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div className="flex items-center justify-between gap-2">
                <input
                  type="text"
                  value={crmSearch}
                  onChange={(e) => setCrmSearch(e.target.value)}
                  placeholder="Filter by name, company, headline, industry, or LinkedIn URL..."
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs"
                />
                <button
                  type="button"
                  onClick={() => setCrmSelectedUrls(crmLeads.map((l) => l.linkedin_url).filter(Boolean))}
                  className="px-2.5 py-1.5 rounded-lg border border-gray-200 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  Select All
                </button>
                <button
                  type="button"
                  onClick={() => setCrmSelectedUrls([])}
                  className="px-2.5 py-1.5 rounded-lg border border-gray-200 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  Clear
                </button>
              </div>

              {/* Prosp Lead Finder ICP Filters + Dripify My Network 1st-Degree Quick Preset */}
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3 space-y-2 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Users className="h-4 w-4 text-emerald-700 shrink-0" />
                    <span className="font-bold text-emerald-950">
                      My Network · Recent 1st-Degree Connections (Up to 1,000)
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setCrmConnectionDegree('1st');
                        const firstDegreeSorted = [...crmLeads]
                          .filter((l) => {
                            const deg = String(l.connection_degree || l.custom_variables?.connection_degree || (l.is_connected ? '1st' : '')).toLowerCase();
                            return !deg || deg.includes('1st');
                          })
                          .sort((a, b) => {
                            const ta = new Date(a.accepted_at || a.connected_at || a.created_at || 0).getTime();
                            const tb = new Date(b.accepted_at || b.connected_at || b.created_at || 0).getTime();
                            return tb - ta;
                          })
                          .slice(0, 1000);
                        setCrmSelectedUrls(firstDegreeSorted.map((l) => l.linkedin_url).filter(Boolean));
                        if (!importListName.trim()) {
                          setImportListName('My Recent 1st-Degree Connections');
                        }
                      }}
                      className="px-2.5 py-1 rounded-lg bg-emerald-600 text-white font-bold text-[11px] hover:bg-emerald-700 cursor-pointer"
                    >
                      Select Recent 1st° (Max 1,000)
                    </button>
                    <a
                      href={LINKEDIN_SOURCING_CHANNELS.connections.directUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-lg border border-emerald-300 bg-white px-2.5 py-1 text-[11px] font-bold text-emerald-800 hover:bg-emerald-50"
                    >
                      Open My Network ↗
                    </a>
                    <a
                      href={LINKEDIN_SOURCING_CHANNELS.connections.batchingSearchUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-lg border border-emerald-300 bg-white px-2.5 py-1 text-[11px] font-bold text-emerald-800 hover:bg-emerald-50"
                    >
                      &gt;1,000 Connections Search Filter ↗
                    </a>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-[11px] text-emerald-800 font-medium">Location Batch Presets (&gt;1,000 1st°):</span>
                  {LINKEDIN_SOURCING_CHANNELS.connections.locationBatches.map((loc) => (
                    <button
                      key={loc}
                      type="button"
                      onClick={() => {
                        setCrmConnectionDegree('1st');
                        setCrmLocationFilter(loc);
                        setImportListName(`My Connections - ${loc}`);
                      }}
                      className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border cursor-pointer transition-colors ${
                        crmLocationFilter === loc && crmConnectionDegree === '1st'
                          ? 'bg-emerald-600 text-white border-emerald-600'
                          : 'bg-white text-emerald-800 border-emerald-200 hover:bg-emerald-100/50'
                      }`}
                    >
                      1st° · {loc}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 bg-gray-50/70 p-2.5 rounded-xl border border-gray-200/70">
                <input
                  type="text"
                  value={crmLocationFilter}
                  onChange={(e) => setCrmLocationFilter(e.target.value)}
                  placeholder="Location (e.g. United States, UK)..."
                  aria-label="Filter by location"
                  className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700"
                />
                <select
                  value={crmCompanySizeFilter}
                  onChange={(e) => setCrmCompanySizeFilter(e.target.value)}
                  aria-label="Filter by company size"
                  className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700"
                >
                  <option value="">All Company Sizes</option>
                  <option value="Self-employed">Self-employed</option>
                  <option value="1-10">1-10 employees</option>
                  <option value="11-50">11-50 employees</option>
                  <option value="51-200">51-200 employees</option>
                  <option value="200+">200+ employees</option>
                </select>
                <select
                  value={crmConnectionDegree}
                  onChange={(e) => setCrmConnectionDegree(e.target.value)}
                  aria-label="Filter by connection degree"
                  className="rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs text-gray-700"
                >
                  <option value="">All Connection Degrees</option>
                  <option value="1st">1st degree</option>
                  <option value="2nd">2nd degree</option>
                  <option value="3rd">3rd+ degree</option>
                </select>
                <label className="inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-gray-200 bg-white text-xs text-gray-700 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={crmPostedRecently}
                    onChange={(e) => setCrmPostedRecently(e.target.checked)}
                    className="rounded border-gray-300 text-indigo-600"
                  />
                  <span className="truncate">Posted on LinkedIn recently</span>
                </label>
              </div>

              <div className="border border-gray-200 rounded-xl max-h-56 overflow-y-auto divide-y divide-gray-100 text-xs">
                {crmLoading ? (
                  <div className="p-6 text-center text-gray-400 flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading workspace contacts...
                  </div>
                ) : crmLeads.length === 0 ? (
                  <div className="p-6 text-center text-gray-500 space-y-2">
                    <p>No existing workspace leads found outside this campaign.</p>
                    <button
                      type="button"
                      onClick={() => { setSourceType('urls'); }}
                      className="text-indigo-600 font-semibold hover:underline"
                    >
                      Paste LinkedIn profile URLs instead →
                    </button>
                  </div>
                ) : (
                  crmLeads
                    .filter((l) => {
                      if (crmSearch.trim()) {
                        const q = crmSearch.toLowerCase();
                        const matchText =
                          (l.first_name || '').toLowerCase().includes(q) ||
                          (l.last_name || '').toLowerCase().includes(q) ||
                          (l.full_name || '').toLowerCase().includes(q) ||
                          (l.company_name || '').toLowerCase().includes(q) ||
                          (l.job_title || '').toLowerCase().includes(q) ||
                          (l.headline || '').toLowerCase().includes(q) ||
                          (l.industry || '').toLowerCase().includes(q) ||
                          (l.linkedin_url || '').toLowerCase().includes(q);
                        if (!matchText) return false;
                      }
                      if (crmLocationFilter.trim()) {
                        const locQ = crmLocationFilter.toLowerCase();
                        const leadLoc = (l.location || l.custom_variables?.location || '').toLowerCase();
                        if (!leadLoc.includes(locQ)) return false;
                      }
                      if (crmCompanySizeFilter) {
                        const leadSize = String(l.company_size || l.custom_variables?.company_size || '').toLowerCase();
                        if (leadSize && !leadSize.includes(crmCompanySizeFilter.toLowerCase())) return false;
                      }
                      if (crmConnectionDegree) {
                        const leadDegree = String(
                          l.connection_degree ||
                          l.custom_variables?.connection_degree ||
                          (l.is_connected ? '1st' : '')
                        ).toLowerCase();
                        if (leadDegree && !leadDegree.includes(crmConnectionDegree.toLowerCase())) return false;
                      }
                      if (crmPostedRecently) {
                        const hasRecentPost = Boolean(
                          l.recent_post ||
                          l.last_engaged_at ||
                          l.custom_variables?.recent_post ||
                          l.custom_variables?.posted_recently
                        );
                        if (!hasRecentPost && (l.recent_post !== undefined || l.custom_variables?.recent_post !== undefined)) {
                          return false;
                        }
                      }
                      return true;
                    })
                    .map((lead, idx) => {
                      const url = lead.linkedin_url;
                      const checked = crmSelectedUrls.includes(url);
                      const fullName =
                        lead.full_name ||
                        `${lead.first_name || ''} ${lead.last_name || ''}`.trim() ||
                        lead.vanity_name ||
                        'Unnamed Lead';
                      return (
                        <label
                          key={lead.id || url || idx}
                          className="flex items-center justify-between gap-3 p-2.5 hover:bg-gray-50 cursor-pointer"
                        >
                          <div className="flex items-center gap-2.5 min-w-0">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  setCrmSelectedUrls((prev) => [...new Set([...prev, url])]);
                                } else {
                                  setCrmSelectedUrls((prev) => prev.filter((u) => u !== url));
                                }
                              }}
                              className="rounded border-gray-300 text-indigo-600"
                            />
                            <div className="min-w-0">
                              <div className="font-semibold text-gray-900 truncate">
                                {fullName}
                                {lead.job_title || lead.headline ? (
                                  <span className="text-gray-500 font-normal"> · {lead.job_title || lead.headline}</span>
                                ) : null}
                                {lead.company_name ? (
                                  <span className="text-gray-400 font-normal"> @ {lead.company_name}</span>
                                ) : null}
                              </div>
                              <div className="flex items-center gap-2 text-[11px] text-gray-500">
                                <span className="font-mono truncate">{url}</span>
                                {lead.location ? (
                                  <span className="text-gray-400 truncate">• {lead.location}</span>
                                ) : null}
                              </div>
                            </div>
                          </div>
                          {url && (
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              title="Open LinkedIn profile in new tab"
                              className="shrink-0 inline-flex items-center justify-center px-2 py-1 rounded-md bg-[#0A66C2]/10 text-[#0A66C2] hover:bg-[#0A66C2]/20 font-bold text-[10px] transition-colors"
                            >
                              in ↗
                            </a>
                          )}
                        </label>
                      );
                    })
                )}
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  disabled={previewLoading}
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium cursor-pointer"
                >
                  ← Back to Sources
                </button>
                <button
                  type="button"
                  disabled={previewLoading || crmSelectedUrls.length === 0}
                  onClick={() => {
                    const selectedRows = crmLeads.filter((l) => crmSelectedUrls.includes(l.linkedin_url));
                    const formatted = selectedRows
                      .map((l) => {
                        const first = l.first_name || (l.full_name ? l.full_name.split(' ')[0] : '');
                        const last = l.last_name || (l.full_name ? l.full_name.split(' ').slice(1).join(' ') : '');
                        return [l.linkedin_url, first, last, l.company_name || '', l.job_title || l.headline || '']
                          .filter(Boolean)
                          .join(', ');
                      })
                      .join('\n');
                    setUrlsText(formatted);
                    setSourceType('urls');
                    handleRunPreview(formatted);
                  }}
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  Validate & Preview ({crmSelectedUrls.length}) <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}

          {step === 2 && sourceType === 'csv' && (
            <div className="space-y-4">
              <div className="border-2 border-dashed border-gray-300 rounded-2xl p-6 text-center hover:border-indigo-500 bg-gray-50/50 transition-colors">
                <Upload className="h-8 w-8 mx-auto text-gray-400 mb-2" />
                <p className="text-sm font-semibold text-gray-800">
                  {csvFileName ? `Selected: ${csvFileName}` : 'Upload your CSV spreadsheet'}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  Automatic column discovery for LinkedIn URL, First Name, Last Name, Company, and Title.
                </p>
                <input
                  type="file"
                  accept=".csv"
                  disabled={previewLoading}
                  onChange={handleFileUpload}
                  className="mt-3 block w-full text-xs text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                <div>
                  <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                    Fallback First Name (Optional)
                  </label>
                  <input
                    type="text"
                    value={defaultFirstName}
                    disabled={previewLoading}
                    onChange={(e) => setDefaultFirstName(e.target.value)}
                    placeholder="e.g. there"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-gray-600 mb-1">
                    Fallback Company (Optional)
                  </label>
                  <input
                    type="text"
                    value={defaultCompanyName}
                    disabled={previewLoading}
                    onChange={(e) => setDefaultCompanyName(e.target.value)}
                    placeholder="e.g. Tech"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <label className="flex items-center gap-2 text-xs font-medium text-gray-700">
                <input type="checkbox" checked={requireName} disabled={previewLoading}
                  onChange={(e) => setRequireName(e.target.checked)} className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
                Require name for outreach personalization
              </label>
              <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  disabled={previewLoading}
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium cursor-pointer"
                >
                  ← Back to Sources
                </button>
                <button
                  type="button"
                  onClick={handleRunPreview}
                  disabled={previewLoading || !csvContent.trim()}
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {previewLoading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Validating CSV...
                    </>
                  ) : (
                    <>
                      Validate & Preview <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 2: LinkedIn Search & Sales Nav ─────────────────────────────── */}
          {step === 2 && sourceType === 'search' && (
            <div className="space-y-4">
              {!searchAvailable && <p role="status" className="rounded-xl bg-amber-50 p-3 text-xs text-amber-800">{searchUnavailableReason} Saved search records can be inspected; enrollment remains unavailable.</p>}
              {!activeJob ? (
                <>
                  {/* Dripify 4-Channel LinkedIn Search Source Tabs & Direct Links */}
                  {(() => {
                    const activeCh = classifyLinkedInSourceUrlClient(searchUrl, searchChannel);
                    const maxCap = activeCh.maxProfiles || 1000;
                    const presetCounts = maxCap === 2500 ? [50, 100, 250, 500, 1000, 2500] : [50, 100, 250, 500, 1000];
                    return (
                      <>
                        <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3.5 space-y-2.5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {Object.values(LINKEDIN_SOURCING_CHANNELS).map((ch) => (
                                <button
                                  key={ch.id}
                                  type="button"
                                  onClick={() => {
                                    setSearchChannel(ch.id);
                                    if (targetCount > ch.maxProfiles) {
                                      setTargetCount(ch.maxProfiles);
                                    }
                                  }}
                                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-colors cursor-pointer ${
                                    activeCh.id === ch.id
                                      ? 'bg-indigo-600 text-white shadow-2xs'
                                      : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-50'
                                  }`}
                                >
                                  {ch.shortLabel}
                                </button>
                              ))}
                            </div>
                            <a
                              href={activeCh.directUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 rounded-lg bg-[#0A66C2] px-2.5 py-1 text-[11px] font-bold text-white hover:bg-[#004182] transition-colors"
                            >
                              {activeCh.directLabel}
                            </a>
                          </div>

                          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-indigo-950">
                            <span>{activeCh.guidance}</span>
                            <span className="shrink-0 rounded-full bg-indigo-100 px-2.5 py-0.5 font-bold text-indigo-800">
                              {activeCh.capSummary}
                            </span>
                          </div>

                          {activeCh.id === 'recruiter' && (
                            <div className="pt-2 border-t border-indigo-200/60 space-y-1.5">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-bold text-teal-900">
                                  Recruiter &gt;1,000 Pool Split · Graduation Year Batching:
                                </span>
                                <span className="text-gray-500">40 pages × 25 profiles = 1,000 max per batch</span>
                              </div>
                              <div className="flex flex-wrap items-center gap-1.5">
                                {LINKEDIN_SOURCING_CHANNELS.recruiter.graduationBatches.map((batch) => (
                                  <button
                                    key={batch}
                                    type="button"
                                    onClick={() => {
                                      setSelectedGradBatch(batch);
                                      setTargetCount(1000);
                                      setImportListName((prev) => {
                                        const base = prev.replace(/\s*\(Grad [^)]+\)\s*$/, '').trim() || 'Recruiter Candidates';
                                        return `${base} (Grad ${batch})`;
                                      });
                                    }}
                                    className={`px-2 py-0.5 rounded-md text-[11px] font-semibold border cursor-pointer transition-colors ${
                                      selectedGradBatch === batch
                                        ? 'bg-teal-600 text-white border-teal-600'
                                        : 'bg-white text-teal-800 border-teal-200 hover:bg-teal-50'
                                    }`}
                                  >
                                    Grad {batch}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          {activeCh.id === 'connections' && (
                            <div className="pt-2 border-t border-indigo-200/60 space-y-1.5">
                              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                                <span className="font-bold text-emerald-900">
                                  Have &gt;1,000 1st-Degree Connections? Filter by Location in LinkedIn Search:
                                </span>
                                <a
                                  href={LINKEDIN_SOURCING_CHANNELS.connections.batchingSearchUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 font-bold text-emerald-700 hover:text-emerald-900 underline"
                                >
                                  Open LinkedIn Search Pre-Filtered to 1st-Degree ↗
                                </a>
                              </div>
                            </div>
                          )}
                        </div>

                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <label className="block text-xs font-bold uppercase tracking-wider text-gray-700">
                              LinkedIn Search, Sales Navigator, Recruiter, or My Network URL
                            </label>
                            {activeCh.detected && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800">
                                <Check className="h-3 w-3" /> Detected: {activeCh.subLabel || activeCh.label} (Max {maxCap.toLocaleString()})
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-500 mb-2">
                            Only a supported source can collect contacts. Unsupported filters are rejected.
                          </p>
                          <input
                            type="url"
                            value={searchUrl}
                            onChange={(e) => {
                              const val = e.target.value;
                              setSearchUrl(val);
                              const det = classifyLinkedInSourceUrlClient(val, searchChannel);
                              if (det.detected && det.id !== searchChannel) {
                                setSearchChannel(det.id);
                              }
                            }}
                            placeholder={activeCh.placeholderUrl}
                            className="w-full rounded-xl border border-gray-300 p-3 font-mono text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-gray-50/50"
                          />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                          <div>
                            <label className="block text-[11px] font-semibold text-gray-700 mb-1">
                              Crawling Sender Account <span className="text-red-500">*</span>
                            </label>
                            {accountsLoading ? (
                              <div className="p-2 text-xs text-gray-400 flex items-center gap-1.5">
                                <Loader2 className="h-3 w-3 animate-spin" /> Loading senders...
                              </div>
                            ) : accounts.length === 0 ? (
                              <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
                                No active sender accounts found. Connect a sender in Settings first.
                              </div>
                            ) : (
                              <select
                                value={selectedSenderId}
                                onChange={(e) => setSelectedSenderId(e.target.value)}
                                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-white"
                              >
                                {accounts.map((acc) => (
                                  <option key={acc.id} value={acc.id}>
                                    {acc.account_name || acc.linkedin_urn || acc.id} {acc.premium_product ? `(${acc.premium_product})` : ''}
                                  </option>
                                ))}
                              </select>
                            )}
                            <span className="text-[10px] text-gray-400 mt-0.5 block">
                              Crawl executes page-by-page ({activeCh.pageSize} profiles/page, up to {activeCh.maxPages} pages) through this sender's dedicated static IP.
                            </span>
                          </div>

                          <div>
                            <label className="block text-[11px] font-semibold text-gray-700 mb-1">
                              Target Leads to Infuse (Max {maxCap.toLocaleString()})
                            </label>
                            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                              {presetCounts.map((count) => (
                                <button
                                  key={count}
                                  type="button"
                                  onClick={() => setTargetCount(count)}
                                  className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-colors ${
                                    Number(targetCount) === count
                                      ? 'bg-indigo-600 text-white shadow-xs'
                                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                  }`}
                                >
                                  {count === maxCap ? `Max (${count})` : count}
                                </button>
                              ))}
                              <input
                                type="number"
                                min={1}
                                max={maxCap}
                                value={targetCount}
                                onChange={(e) => {
                                  const raw = Number(e.target.value);
                                  if (!Number.isNaN(raw)) {
                                    setTargetCount(Math.max(1, Math.min(raw, maxCap)));
                                  }
                                }}
                                aria-label="Custom target lead count"
                                className="w-20 rounded-lg border border-gray-300 px-2 py-1 text-xs font-semibold text-gray-800"
                              />
                            </div>
                            <span className="text-[10px] text-gray-400 mt-1 block">
                              Collection limits depend on the supported source contract ({activeCh.capSummary}).
                            </span>
                          </div>
                        </div>

                        <div>
                          <label className="block text-[11px] font-semibold text-gray-700 mb-1">
                            Lead List Name / Cohort Tag (Optional)
                          </label>
                          <input
                            type="text"
                            value={importListName}
                            onChange={(e) => setImportListName(e.target.value)}
                            placeholder={activeCh.listPlaceholder}
                            aria-label="Search lead list name"
                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-white"
                          />
                        </div>
                      </>
                    );
                  })()}

                  <div className="rounded-xl bg-indigo-50/50 p-3.5 border border-indigo-100 space-y-1.5 text-xs">
                    <div className="flex items-center gap-2 text-indigo-900 font-semibold">
                      <Shield className="h-4 w-4 text-indigo-600 shrink-0" />
                      <span>Search collection and enrollment are separate checks</span>
                    </div>
                    <p className="text-gray-600 text-[11px] leading-relaxed">
                      Searches are crawled one page at a time with adaptive delays. Prospects land in a <strong>Staged Review</strong> where you inspect deduplications, Do-Not-Contact skips, and cleaned names before enrolling them into your sequence.
                    </p>
                  </div>

                  <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                    <button
                      type="button"
                      onClick={() => setStep(1)}
                      className="text-xs text-gray-500 hover:text-gray-800 font-medium cursor-pointer"
                    >
                      ← Back to Sources
                    </button>
                    <button
                      type="button"
                      onClick={handleStartSearchCrawl}
                      disabled={!searchAvailable || crawlLoading || !searchUrl.trim() || !selectedSenderId}
                      className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 shadow-sm disabled:opacity-50 cursor-pointer"
                    >
                      {crawlLoading ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Starting Infusion...
                        </>
                      ) : (
                        <>
                          <Play className="h-3.5 w-3.5 fill-white" /> Start Lead Infusion
                        </>
                      )}
                    </button>
                  </div>
                </>
              ) : (
                /* Active Search Crawl Monitor */
                <div className="space-y-4">
                  <div className="rounded-2xl border border-gray-200 bg-gray-50/60 p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {activeJob.status === 'crawling' || activeJob.status === 'queued' ? (
                          <div className="h-9 w-9 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center">
                            <Loader2 className="h-5 w-5 animate-spin" />
                          </div>
                        ) : activeJob.status === 'completed' ? (
                          <div className="h-9 w-9 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center">
                            <CheckCircle2 className="h-5 w-5" />
                          </div>
                        ) : (
                          <div className="h-9 w-9 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center">
                            <AlertCircle className="h-5 w-5" />
                          </div>
                        )}
                        <div>
                          <h4 className="font-bold text-gray-900 text-sm">
                            {activeJob.status === 'crawling' ? 'Scanning LinkedIn Search Results...' :
                             activeJob.status === 'queued' ? 'Initializing Dedicated Proxy Session...' :
                             activeJob.status === 'completed' ? 'Search Lead Extraction Completed' :
                             activeJob.status === 'stopped' ? 'Search Extraction Stopped' :
                             activeJob.status === 'failed' ? 'Search Extraction Failed' : 'Checking Search Status...'}
                          </h4>
                          <p className="text-xs text-gray-500 mt-0.5 font-mono truncate max-w-md">
                            {activeJob.search_url}
                          </p>
                        </div>
                      </div>

                      <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${
                        activeJob.status === 'crawling' ? 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse' :
                        activeJob.status === 'completed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                        'bg-amber-50 text-amber-700 border-amber-200'
                      }`}>
                        {activeJob.status}
                      </span>
                    </div>

                    {/* Progress Bar */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs font-semibold text-gray-700">
                        <span>Progress: {activeJob.leads_imported || 0} of {activeJob.target_count || 100} leads staged</span>
                        <span>
                          {Math.round(((activeJob.leads_imported || 0) / (activeJob.target_count || 100)) * 100)}%
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                        <div
                          className="bg-indigo-600 h-2 rounded-full transition-all duration-500 ease-out"
                          style={{
                            width: `${Math.min(100, Math.round(((activeJob.leads_imported || 0) / (activeJob.target_count || 100)) * 100))}%`,
                          }}
                        />
                      </div>
                    </div>

                    {/* Metric Cards Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                      <div className="p-3 rounded-xl bg-white border border-gray-200 shadow-xs">
                        <span className="text-lg font-bold text-emerald-600">{activeJob.leads_imported || 0}</span>
                        <p className="text-[11px] font-semibold text-gray-600">Leads Staged</p>
                      </div>
                      <div className="p-3 rounded-xl bg-white border border-gray-200 shadow-xs">
                        <span className="text-lg font-bold text-amber-600">{activeJob.duplicates_skipped || 0}</span>
                        <p className="text-[11px] font-semibold text-gray-600">Duplicates Skipped</p>
                      </div>
                      <div className="p-3 rounded-xl bg-white border border-gray-200 shadow-xs">
                        <span className="text-lg font-bold text-red-600">
                          {(activeJob.dnc_suppressed || 0) + (activeJob.withdrawn_cooldown_skipped || 0)}
                        </span>
                        <p className="text-[11px] font-semibold text-gray-600">DNC / Cooldown</p>
                      </div>
                      <div className="p-3 rounded-xl bg-white border border-gray-200 shadow-xs">
                        <span className="text-lg font-bold text-indigo-600">{activeJob.pages_scanned || 0}</span>
                        <p className="text-[11px] font-semibold text-gray-600">Pages Scanned</p>
                      </div>
                    </div>

                    {/* Error / Stop reason notification if any */}
                    {activeJob.user_error_message && (
                      <div className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-800 border border-amber-200">
                        <AlertCircle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                        <div>
                          <p className="font-semibold">Crawl Alert: {activeJob.stop_reason || 'Stopped'}</p>
                          <p className="mt-0.5 text-amber-700">{activeJob.user_error_message}</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Crawl Control Buttons */}
                  <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                    <div className="flex items-center gap-2">
                      {(activeJob.status === 'crawling' || activeJob.status === 'queued') ? (
                        <button
                          type="button"
                          onClick={handleCancelCrawl}
                          disabled={cancelingCrawl}
                          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-gray-300 text-xs font-medium text-gray-700 hover:bg-gray-100 cursor-pointer"
                        >
                          <Square className="h-3 w-3 fill-gray-500" /> {cancelingCrawl ? 'Requesting stop…' : 'Stop Crawl'}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setActiveJob(null)}
                          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-gray-300 text-xs font-medium text-gray-700 hover:bg-gray-100 cursor-pointer"
                        >
                          <RefreshCw className="h-3 w-3" /> New Search
                        </button>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={handleReviewStagedLeads}
                      disabled={previewLoading || (activeJob.leads_imported || 0) === 0}
                      className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 shadow-sm disabled:opacity-50 cursor-pointer"
                    >
                      {previewLoading ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading Staged Leads...
                        </>
                      ) : (
                        <>
                          Review {activeJob.leads_imported || 0} Staged Leads <ArrowRight className="h-3.5 w-3.5" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── STEP 3: Preview Table & Deduplication Filter ─────────────────────── */}
          {step === 3 && !importResult && previewResult && (
            <div className="space-y-4">
              {sourceType === 'search' && !searchAvailable && (
                <p role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  {searchUnavailableReason} Saved rows are unverified and cannot be enrolled.
                </p>
              )}
              {/* Summary Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200">
                  <span className="text-xl font-bold text-emerald-700">{previewResult.valid_count}</span>
                  <p className="text-[11px] font-semibold text-emerald-800">{sourceType === 'search' && !searchAvailable ? 'Saved for review' : 'Valid to Enroll'}</p>
                </div>
                <div className="p-3 rounded-xl bg-amber-50 border border-amber-200">
                  <span className="text-xl font-bold text-amber-700">
                    {previewResult.duplicate_count + previewResult.contacted_count}
                  </span>
                  <p className="text-[11px] font-semibold text-amber-800">Duplicates / Contacted</p>
                </div>
                <div className="p-3 rounded-xl bg-red-50 border border-red-200">
                  <span className="text-xl font-bold text-red-700">{previewResult.dnc_count}</span>
                  <p className="text-[11px] font-semibold text-red-800">Do-Not-Contact</p>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <span className="text-xl font-bold text-gray-700">{previewResult.invalid_count}</span>
                  <p className="text-[11px] font-semibold text-gray-600">Invalid URL / Name</p>
                </div>
              </div>

              {/* ICP Filter Match Verification Bar (Dripify Lead Verification Parity) */}
              <div className="p-3.5 rounded-xl bg-indigo-50/50 border border-indigo-100 space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h4 className="text-xs font-bold text-indigo-950">ICP Filter Match Verification</h4>
                    <p className="text-[11px] text-indigo-800/80">
                      Filter imported rows against target job titles or locations and remove non-matching leads in 1 click.
                    </p>
                  </div>
                  {(icpTitleFilter.trim() || icpLocationFilter.trim()) && (() => {
                    const nonMatchingCount = stagedRows.filter((r) => !evaluateRowIcp(r).matches).length;
                    return nonMatchingCount > 0 ? (
                      <button
                        type="button"
                        onClick={handleRemoveNonMatchingIcp}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 px-3 py-1.5 text-[11px] font-bold text-white shadow-2xs transition-colors cursor-pointer"
                      >
                        <X className="h-3.5 w-3.5" />
                        Remove non-matching leads ({nonMatchingCount})
                      </button>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                        <Check className="h-3 w-3" /> All {stagedRows.length} leads match ICP
                      </span>
                    );
                  })()}
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={icpTitleFilter}
                    onChange={(e) => setIcpTitleFilter(e.target.value)}
                    placeholder="Target job titles (e.g. Marketing, VP, Founder)"
                    aria-label="Target job title ICP filter"
                    className="rounded-lg border border-indigo-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none"
                  />
                  <input
                    type="text"
                    value={icpLocationFilter}
                    onChange={(e) => setIcpLocationFilter(e.target.value)}
                    placeholder="Target locations (e.g. United States, London)"
                    aria-label="Target location ICP filter"
                    className="rounded-lg border border-indigo-200 bg-white px-2.5 py-1.5 text-xs text-gray-800 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Row-Level Preview Table */}
              <div className="border border-gray-200 rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between text-xs font-semibold text-gray-700">
                  <span>Row Verification Preview (Showing {Math.min(stagedRows.length, 50)} of {previewResult.total_submitted})</span>
                  <div className="flex items-center gap-3">
                    {stagedRows.some((r) => r.status !== 'valid') && (
                      <button
                        type="button"
                        onClick={() => {
                          const rejected = stagedRows.filter((r) => r.status !== 'valid');
                          const csvLines = ['row_number,first_name,last_name,company_name,linkedin_url,rejection_code,error_reason'];
                          rejected.forEach((r) => {
                            const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
                            csvLines.push([
                              r.row_number,
                              esc(r.cleaned_first_name ?? r.first_name ?? ''),
                              esc(r.last_name ?? ''),
                              esc(r.company_name ?? ''),
                              esc(r.linkedin_url || r.raw_url || ''),
                              esc(r.rejection_code || ''),
                              esc(r.error_reason || 'Rejected'),
                            ].join(','));
                          });
                          const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8' });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = 'rejected-leads.csv';
                          document.body.appendChild(a);
                          a.click();
                          a.remove();
                          setTimeout(() => URL.revokeObjectURL(url), 1000);
                        }}
                        className="text-indigo-600 hover:text-indigo-800 underline font-semibold cursor-pointer"
                      >
                        Download Rejected Rows CSV
                      </button>
                    )}
                    <span className="text-gray-500 font-normal">Identical DNC & deduplication rules enforced</span>
                  </div>
                </div>
                <div className="max-h-60 overflow-y-auto divide-y divide-gray-100 text-xs">
                  {stagedRows.length === 0 ? (
                    <div className="p-4 text-center text-gray-400">No leads parsed from source.</div>
                  ) : (
                    stagedRows.slice(0, 50).map((row) => {
                      const currentName = row.cleaned_first_name ?? row.first_name ?? '';
                      const rawName = row.raw_first_name || '';
                      const isModified = rawName && currentName !== rawName;

                      return (
                        <div key={row.row_number} className="p-2.5 flex items-center justify-between gap-3 hover:bg-gray-50/70">
                          <div className="flex items-center gap-2.5 min-w-0 flex-1">
                            <span className="font-mono text-[11px] text-gray-400 w-5">#{row.row_number}</span>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-medium text-gray-900 truncate">
                                  {currentName || row.last_name ? `${currentName} ${row.last_name || ''}`.trim() : (row.vanity_name || 'No name')}
                                </span>
                                {(row.status === 'valid' || row.rejection_code === 'missing_name') && (
                                  <div className="flex items-center gap-1">
                                    <input
                                      type="text"
                                      value={currentName}
                                      aria-label={`First name for lead #${row.row_number}`}
                                      disabled={loading || previewLoading}
                                      onChange={(e) => handleNameChange(row.row_number, e.target.value)}
                                      placeholder="First name"
                                      className="px-1.5 py-0.5 border border-gray-300 rounded text-xs font-medium text-gray-900 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 w-24 bg-white"
                                    />
                                    {isModified && (
                                      <button
                                        type="button"
                                        onClick={() => handleRevertName(row.row_number)}
                                        title={`Revert to original: ${rawName}`}
                                        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] text-gray-600 hover:text-indigo-600 bg-gray-100 hover:bg-indigo-50 rounded border border-gray-200 transition-colors cursor-pointer"
                                      >
                                        <RotateCcw className="h-2.5 w-2.5" /> Revert
                                      </button>
                                    )}
                                  </div>
                                )}
                                {row.company_name && (
                                  <span className="text-gray-400 text-[11px]">· {row.company_name}</span>
                                )}
                              </div>
                              <span className="text-[11px] text-gray-500 truncate block font-mono mt-0.5">
                                {row.linkedin_url || row.raw_url}
                              </span>
                            </div>
                          </div>

                          <div className="shrink-0 ml-2 flex items-center gap-1.5">
                            {(() => {
                              const icp = evaluateRowIcp(row);
                              if (!icp.active) return null;
                              return icp.matches ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-bold text-indigo-700 border border-indigo-200">
                                  Matches ICP
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-bold text-rose-700 border border-rose-200">
                                  {icp.reason}
                                </span>
                              );
                            })()}
                            {row.status === 'valid' ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                                <Check className="h-3 w-3" /> {sourceType === 'search' && !searchAvailable ? 'Unverified' : 'Valid'}
                              </span>
                            ) : (
                              <span
                                title={row.error_reason}
                                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold border ${
                                  row.rejection_code === 'do_not_contact'
                                    ? 'bg-red-50 text-red-700 border-red-200'
                                    : row.rejection_code?.startsWith('duplicate')
                                    ? 'bg-amber-50 text-amber-700 border-amber-200'
                                    : 'bg-gray-100 text-gray-700 border-gray-200'
                                }`}
                              >
                                <AlertCircle className="h-3 w-3" /> {row.error_reason || 'Rejected'}
                              </span>
                            )}
                            <button
                              type="button"
                              onClick={() => handleRemoveStagedRow(row.row_number)}
                              title="Remove row from import"
                              aria-label={`Remove lead #${row.row_number}`}
                              className="p-1 rounded text-gray-400 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Safety & Dedup Controls */}
              <div className="rounded-xl bg-gray-50 p-3.5 border border-gray-200 space-y-2.5 text-xs">
                <div>
                  <label className="block text-[11px] font-bold text-gray-800 mb-1">
                    Assign to Contact List / Cohort Tag <span className="text-gray-400 font-normal">(Optional — preserves exact capitalization)</span>
                  </label>
                  <input
                    type="text"
                    value={importListName}
                    disabled={loading || previewLoading}
                    onChange={(e) => setImportListName(e.target.value)}
                    placeholder="e.g. AppSumo, ClientAmp, Dream 50 SaaS Founders..."
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs text-gray-900 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                <label className="flex items-center gap-2.5 cursor-pointer pt-1 border-t border-gray-200/60">
                  <input
                    type="checkbox"
                    checked={skipContacted}
                    disabled={loading || previewLoading || sourceType === 'search'}
                    onChange={(e) => { setSkipContacted(e.target.checked); setHasEdits(true); setReviewRequired(true); }}
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div>
                    <span className="font-semibold text-gray-800">Skip leads already contacted in another campaign</span>
                    <span className="text-gray-500 block text-[11px]">{sourceType === 'search'
                      ? 'Staged search enrollment always rechecks contacted and excluded leads on the server.'
                      : 'Prevents duplicate touches across separate campaigns in this workspace.'}</span>
                  </div>
                </label>

                <div className="flex items-center gap-2 pt-1 border-t border-gray-200/60 text-gray-500 text-[11px]">
                  <Shield className="h-3.5 w-3.5 text-indigo-600 shrink-0" />
                  <span>Do-Not-Contact exclusion is always active. No profile data is invented or fabricated.</span>
                </div>
              </div>

              {/* Bottom Actions */}
              {reviewRequired && (
                <div role="status" className="flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                  <span>Names or exclusions changed. Validate Changes to refresh the contact counts before importing.</span>
                  <button type="button" disabled={previewLoading || loading} onClick={handleValidateChanges}
                    className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-2 font-semibold disabled:opacity-50">
                    {previewLoading ? 'Validating…' : 'Validate Changes'}
                  </button>
                </div>
              )}
              <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => { previewGenerationRef.current += 1; setPreviewLoading(false); setStep(2); }}
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium cursor-pointer"
                >
                  ← Edit Source Input
                </button>
                <button
                  type="button"
                  onClick={handleExecuteImport}
                  disabled={loading || previewLoading || reviewRequired || (sourceType === 'search' && !searchAvailable) || previewResult.valid_count === 0}
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Ingesting {previewResult.valid_count} Leads...
                    </>
                  ) : (
                    <>
                      Confirm & Ingest {previewResult.valid_count} Valid Leads <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 4: Import Complete ─────────────────────────────────────────── */}
          {importResult && (
            <div className="space-y-5 text-center py-4">
              <div className="h-14 w-14 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto border border-emerald-100">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900">Lead Intake Complete</h3>
                <p className="text-xs text-gray-500 mt-1">
                  {importResult.imported_count > 0
                    ? importResult.attempt_only ? `${importResult.imported_count} leads saved in this attempt to your outreach campaign.`
                      : `Successfully attached ${importResult.imported_count} leads to your outreach campaign.`
                    : 'No new leads were added. All submitted records were either duplicates or excluded by safety rules.'}
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3 max-w-md mx-auto">
                <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200">
                  <span className="text-lg font-bold text-emerald-700">{importResult.imported_count ?? 0}</span>
                  <p className="text-[11px] text-emerald-800 font-semibold mt-0.5">Enrolled</p>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <span className="text-lg font-bold text-gray-700">{importResult.duplicates_count ?? 0}</span>
                  <p className="text-[11px] text-gray-500 font-medium mt-0.5">Duplicates</p>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-200">
                  <span className="text-lg font-bold text-gray-700">{importResult.skipped_count ?? 0}</span>
                  <p className="text-[11px] text-gray-500 font-medium mt-0.5">Skipped (Safety/DNC)</p>
                </div>
              </div>

              {/* Rejections breakdown if any */}
              {importResult.rejections && importResult.rejections.length > 0 && (
                <div className="text-left max-w-lg mx-auto border border-gray-200 rounded-xl overflow-hidden text-xs">
                  <div className="px-3.5 py-2 bg-gray-50 font-semibold text-gray-700 border-b border-gray-200">
                    Excluded Leads Summary ({importResult.rejections.length})
                  </div>
                  <div className="max-h-36 overflow-y-auto divide-y divide-gray-100 p-1">
                    {importResult.rejections.slice(0, 20).map((rej, idx) => (
                      <div key={idx} className="p-2 flex items-center justify-between">
                        <span className="font-mono text-[11px] text-gray-600 truncate max-w-[240px]">
                          {rej.linkedin_url}
                        </span>
                        <span className="text-[10px] text-red-600 font-medium bg-red-50 px-2 py-0.5 rounded-full">
                          {rej.reason}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => { resetAll(); onClose(); }}
                  className="rounded-xl bg-gray-900 px-6 py-2.5 text-xs font-bold text-white hover:bg-black shadow-sm cursor-pointer"
                >
                  Done
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
