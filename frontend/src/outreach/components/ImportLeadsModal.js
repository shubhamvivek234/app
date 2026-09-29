import React, { useState } from 'react';
import {
  FileSpreadsheet, Search, Users, MessageSquare, Upload, ArrowRight, X, AlertCircle,
  CheckCircle2, Loader2, Shield, Sparkles, Calendar, Bookmark, ExternalLink,
  Check, Filter, ChevronDown, ThumbsUp, MessageCircle, Link, UserPlus, Info
} from 'lucide-react';

export default function ImportLeadsModal({ isOpen, onClose, campaignId, onLeadsImported }) {
  // Step 1: Choose Source, Step 2: Input / URLs / CSV, Step 3: Preview & Deduplication, Step 4: Complete
  const [step, setStep] = useState(1);
  const [sourceType, setSourceType] = useState('urls'); // 'urls' | 'csv'

  // Input states
  const [urlsText, setUrlsText] = useState('');
  const [csvContent, setCsvContent] = useState('');
  const [csvFileName, setCsvFileName] = useState('');
  const [defaultFirstName, setDefaultFirstName] = useState('');
  const [defaultCompanyName, setDefaultCompanyName] = useState('');
  const [requireName, setRequireName] = useState(true);
  const [skipContacted, setSkipContacted] = useState(true);

  // Preview & Ingest state
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewResult, setPreviewResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [importResult, setImportResult] = useState(null);

  if (!isOpen) return null;

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError('CSV files must be smaller than 5 MB.');
      return;
    }
    setCsvFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      setCsvContent(event.target.result);
      setError(null);
    };
    reader.onerror = () => setError('Could not read the CSV file. Please try again.');
    reader.readAsText(file);
  };

  const handleRunPreview = async () => {
    if (!campaignId) {
      setError('Select a campaign before previewing contacts.');
      return;
    }
    const rawText = sourceType === 'urls' ? urlsText.trim() : csvContent.trim();
    if (!rawText) {
      setError(sourceType === 'urls' ? 'Please paste at least one LinkedIn profile URL.' : 'Please upload or paste CSV content.');
      return;
    }

    setPreviewLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/leads/preview', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          campaign_id: campaignId,
          source_type: sourceType === 'urls' ? 'pasted_urls' : 'csv',
          raw_text: rawText,
          default_first_name: defaultFirstName.trim() || null,
          default_company_name: defaultCompanyName.trim() || null,
          skip_already_contacted: skipContacted,
          skip_do_not_contact: true,
          require_name: requireName,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to preview leads.');
      }
      setPreviewResult(data);
      setStep(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleExecuteImport = async () => {
    if (!campaignId) {
      setError('Select a campaign before importing contacts.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      let res;

      if (sourceType === 'urls') {
        res = await fetch('/api/v1/outreach/leads/import-urls', {
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
            skip_already_contacted: skipContacted,
            skip_do_not_contact: true,
            require_name: requireName,
            consent_basis: 'user_provided',
          }),
        });
      } else {
        res = await fetch('/api/v1/outreach/leads/import-csv', {
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
            skip_already_contacted: skipContacted,
            skip_do_not_contact: true,
            consent_basis: 'user_provided',
          }),
        });
      }

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Import failed.');
      }

      setImportResult(data);
      if (onLeadsImported) onLeadsImported(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const resetAll = () => {
    setStep(1);
    setSourceType('urls');
    setUrlsText('');
    setCsvContent('');
    setCsvFileName('');
    setDefaultFirstName('');
    setDefaultCompanyName('');
    setPreviewResult(null);
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
                step === 2 ? (sourceType === 'urls' ? 'Paste LinkedIn Profile URLs' : 'Upload CSV Spreadsheet') :
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
                  onClick={() => { setSourceType('urls'); setStep(2); }}
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
                  onClick={() => { setSourceType('csv'); setStep(2); }}
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

                {/* 3. LinkedIn Search / Sales Nav (DISABLED - SAFETY) */}
                <div className="p-4 rounded-xl border border-gray-200 bg-gray-50/70 opacity-60 relative">
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
                    Scraping disabled
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-gray-200 text-gray-500">
                      <Search className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-700 text-sm">LinkedIn Search & Sales Nav</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Automated search extraction requires legal approval</p>
                    </div>
                  </div>
                </div>

                {/* 4. Lead Finder (DISABLED - REQUIRES PARTNER APPROVAL) */}
                <div className="p-4 rounded-xl border border-gray-200 bg-gray-50/70 opacity-60 relative">
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
                    Partner API required
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-gray-200 text-gray-500">
                      <Sparkles className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-700 text-sm">Interactive Lead Finder</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Direct prospect exploration requires official LinkedIn Partner API</p>
                    </div>
                  </div>
                </div>

                {/* 5. LinkedIn Event (DISABLED) */}
                <div className="p-4 rounded-xl border border-gray-200 bg-gray-50/70 opacity-60 relative">
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
                    Scraping disabled
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-gray-200 text-gray-500">
                      <Calendar className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-700 text-sm">LinkedIn Event attendees</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Automated attendee harvesting disabled for account safety</p>
                    </div>
                  </div>
                </div>

                {/* 6. Post Engagers (DISABLED) */}
                <div className="p-4 rounded-xl border border-gray-200 bg-gray-50/70 opacity-60 relative">
                  <div className="absolute top-3 right-3 text-[10px] font-semibold text-gray-500 bg-gray-200 px-2 py-0.5 rounded-full">
                    Scraping disabled
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-gray-200 text-gray-500">
                      <MessageSquare className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-700 text-sm">LinkedIn Post Engagers</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Commenter/liker scraping disabled for account safety</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ── STEP 2: Input / Configuration ───────────────────────────────────── */}
          {step === 2 && sourceType === 'urls' && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-gray-700 mb-1">
                  Paste LinkedIn Profile URLs (One per line)
                </label>
                <p className="text-xs text-gray-500 mb-2">
                  Format per line: <code className="bg-gray-100 px-1 py-0.5 rounded text-gray-800">https://linkedin.com/in/username, First, Last, Company</code> or simply <code className="bg-gray-100 px-1 py-0.5 rounded text-gray-800">https://linkedin.com/in/username</code>
                </p>
                <textarea
                  rows={7}
                  value={urlsText}
                  onChange={(e) => setUrlsText(e.target.value)}
                  placeholder={`https://www.linkedin.com/in/williamhgates, Bill Gates, Breakthrough Energy\nhttps://linkedin.com/in/satyanadella, Satya, Nadella, Microsoft\nhttps://linkedin.com/in/sundarpichai, Sundar Pichai`}
                  className="w-full rounded-xl border border-gray-300 p-3 font-mono text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 bg-gray-50/50"
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
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium cursor-pointer"
                >
                  ← Back to Sources
                </button>
                <button
                  type="button"
                  onClick={handleRunPreview}
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
                    onChange={(e) => setDefaultCompanyName(e.target.value)}
                    placeholder="e.g. Tech"
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-xs focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
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

          {/* ── STEP 3: Preview Table & Deduplication Filter ─────────────────────── */}
          {step === 3 && !importResult && previewResult && (
            <div className="space-y-4">
              {/* Summary Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200">
                  <span className="text-xl font-bold text-emerald-700">{previewResult.valid_count}</span>
                  <p className="text-[11px] font-semibold text-emerald-800">Valid to Enroll</p>
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

              {/* Row-Level Preview Table */}
              <div className="border border-gray-200 rounded-xl overflow-hidden">
                <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between text-xs font-semibold text-gray-700">
                  <span>Row Verification Preview (Showing {Math.min(previewResult.rows.length, 50)} of {previewResult.total_submitted})</span>
                  <span className="text-gray-500 font-normal">Identical DNC & deduplication rules enforced</span>
                </div>
                <div className="max-h-56 overflow-y-auto divide-y divide-gray-100 text-xs">
                  {previewResult.rows.length === 0 ? (
                    <div className="p-4 text-center text-gray-400">No leads parsed from source.</div>
                  ) : (
                    previewResult.rows.slice(0, 50).map((row) => (
                      <div key={row.row_number} className="p-2.5 flex items-center justify-between hover:bg-gray-50/70">
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          <span className="font-mono text-[11px] text-gray-400 w-5">#{row.row_number}</span>
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="font-medium text-gray-900 truncate">
                                {row.first_name || row.last_name ? `${row.first_name} ${row.last_name}`.trim() : (row.vanity_name || 'No name')}
                              </span>
                              {row.company_name && (
                                <span className="text-gray-400 text-[11px]">· {row.company_name}</span>
                              )}
                            </div>
                            <span className="text-[11px] text-gray-500 truncate block font-mono">
                              {row.linkedin_url || row.raw_url}
                            </span>
                          </div>
                        </div>

                        <div className="shrink-0 ml-3">
                          {row.status === 'valid' ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-200">
                              <Check className="h-3 w-3" /> Valid
                            </span>
                          ) : (
                            <span
                              title={row.error_reason}
                              className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-bold text-red-700 border border-red-200"
                            >
                              <AlertCircle className="h-3 w-3" /> {row.error_reason || 'Rejected'}
                            </span>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Safety & Dedup Controls */}
              <div className="rounded-xl bg-gray-50 p-3.5 border border-gray-200 space-y-2 text-xs">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={skipContacted}
                    onChange={(e) => setSkipContacted(e.target.checked)}
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div>
                    <span className="font-semibold text-gray-800">Skip leads already contacted in another campaign</span>
                    <span className="text-gray-500 block text-[11px]">Prevents duplicate touches across separate campaigns in this workspace.</span>
                  </div>
                </label>

                <div className="flex items-center gap-2 pt-1 border-t border-gray-200/60 text-gray-500 text-[11px]">
                  <Shield className="h-3.5 w-3.5 text-indigo-600 shrink-0" />
                  <span>Do-Not-Contact exclusion is always active. No profile data is invented or fabricated.</span>
                </div>
              </div>

              {/* Bottom Actions */}
              <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium cursor-pointer"
                >
                  ← Edit Source Input
                </button>
                <button
                  type="button"
                  onClick={handleExecuteImport}
                  disabled={loading || previewResult.valid_count === 0}
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
                    ? `Successfully attached ${importResult.imported_count} leads to your outreach campaign.`
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
