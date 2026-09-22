import React, { useState } from 'react';
import { FileSpreadsheet, Search, Users, MessageSquare, Upload, ArrowRight, X, AlertCircle, CheckCircle2, Loader2, Shield } from 'lucide-react';

export default function ImportLeadsModal({ isOpen, onClose, campaignId, onLeadsImported }) {
  const [step, setStep] = useState(1); // 1: Choose Source, 2: Upload/Input, 3: Filters & Ingest
  const [sourceType, setSourceType] = useState('csv'); // 'csv' | 'search' | 'sales_nav' | 'post'
  const [csvContent, setCsvContent] = useState('');
  const [searchUrl, setSearchUrl] = useState('');
  const [skipContacted, setSkipContacted] = useState(true);
  const [skipDNC, setSkipDNC] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [importResult, setImportResult] = useState(null);

  if (!isOpen) return null;

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      setCsvContent(event.target.result);
      setStep(3);
    };
    reader.readAsText(file);
  };

  const handleExecuteImport = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      let res;
      if (sourceType === 'csv') {
        res = await fetch('/api/v1/outreach/leads/import-csv', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({
            campaign_id: campaignId,
            csv_text: csvContent,
            skip_already_contacted: skipContacted,
            skip_do_not_contact: skipDNC,
          }),
        });
      } else {
        res = await fetch('/api/v1/outreach/leads/import-search', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({
            campaign_id: campaignId,
            search_url: searchUrl,
            search_type: sourceType,
          }),
        });
      }

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Import failed');
      }

      setImportResult(data);
      if (onLeadsImported) onLeadsImported(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl border border-gray-100 transition-all">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-gray-100 mb-6">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-600">
              Import Contacts · Step {step}/3
            </span>
            <h2 className="text-xl font-bold text-gray-900 mt-0.5">
              {step === 1 && 'Where are your leads?'}
              {step === 2 && 'Provide Lead Source'}
              {step === 3 && (importResult ? 'Import Complete' : 'Safety & Deduplication Filters')}
            </h2>
          </div>
          <button onClick={onClose} className="rounded-full p-1 text-gray-400 hover:bg-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 border border-red-200">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Step 1: Source Selection Grid */}
        {step === 1 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            <button
              onClick={() => { setSourceType('csv'); setStep(2); }}
              className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/10 transition-all group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-indigo-50 text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                  <FileSpreadsheet className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900 text-sm">Upload a CSV file</h4>
                  <p className="text-xs text-gray-400 mt-0.5">Add profiles from any spreadsheet</p>
                </div>
              </div>
            </button>

            <button
              onClick={() => { setSourceType('search'); setStep(2); }}
              className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/10 transition-all group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-blue-50 text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-colors">
                  <Search className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900 text-sm">Basic LinkedIn search</h4>
                  <p className="text-xs text-gray-400 mt-0.5">Paste free search results URL</p>
                </div>
              </div>
            </button>

            <button
              onClick={() => { setSourceType('sales_nav'); setStep(2); }}
              className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/10 transition-all group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-amber-50 text-amber-600 group-hover:bg-amber-600 group-hover:text-white transition-colors">
                  <Users className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900 text-sm">Sales Navigator search</h4>
                  <p className="text-xs text-gray-400 mt-0.5">Transfer from Sales Nav panels</p>
                </div>
              </div>
            </button>

            <button
              onClick={() => { setSourceType('post'); setStep(2); }}
              className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-indigo-50/10 transition-all group"
            >
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-emerald-50 text-emerald-600 group-hover:bg-emerald-600 group-hover:text-white transition-colors">
                  <MessageSquare className="h-5 w-5" />
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900 text-sm">LinkedIn post engagers</h4>
                  <p className="text-xs text-gray-400 mt-0.5">People who liked or commented</p>
                </div>
              </div>
            </button>
          </div>
        )}

        {/* Step 2: Upload CSV or Enter URL */}
        {step === 2 && sourceType === 'csv' && (
          <div className="space-y-4">
            <div className="border-2 border-dashed border-gray-300 rounded-2xl p-8 text-center hover:border-indigo-500 bg-gray-50/50 transition-colors">
              <Upload className="h-8 w-8 mx-auto text-gray-400 mb-3" />
              <p className="text-sm font-semibold text-gray-700">Upload your CSV spreadsheet</p>
              <p className="text-xs text-gray-400 mt-1">Supports auto-detection of LinkedIn URL, Name, Company, and Title</p>
              <input
                type="file"
                accept=".csv"
                onChange={handleFileUpload}
                className="mt-4 block w-full text-xs text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer"
              />
            </div>
            <div className="flex justify-between pt-2">
              <button onClick={() => setStep(1)} className="text-xs text-gray-500 hover:text-gray-800">
                Back
              </button>
            </div>
          </div>
        )}

        {step === 2 && sourceType !== 'csv' && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-gray-700">
                {sourceType === 'post' ? 'LinkedIn Post URL' : 'LinkedIn Search Results URL'}
              </label>
              <input
                type="url"
                value={searchUrl}
                onChange={(e) => setSearchUrl(e.target.value)}
                placeholder="https://www.linkedin.com/search/results/people/?keywords=..."
                className="mt-1.5 w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="flex justify-between pt-2">
              <button onClick={() => setStep(1)} className="text-xs text-gray-500 hover:text-gray-800">
                Back
              </button>
              <button
                onClick={() => setStep(3)}
                disabled={!searchUrl.trim()}
                className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                Next: Filters <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Filters & Final Ingest */}
        {step === 3 && !importResult && (
          <div className="space-y-5">
            <div className="rounded-xl bg-gray-50 p-4 border border-gray-100 space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-1.5">
                <Shield className="h-4 w-4 text-indigo-600" />
                Contact Safety & Deduplication
              </h4>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={skipContacted}
                  onChange={(e) => setSkipContacted(e.target.checked)}
                  className="mt-1 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-800">Skip people already contacted</span>
                  <p className="text-xs text-gray-500">Excludes leads who received a message across any of your campaigns.</p>
                </div>
              </label>

              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={skipDNC}
                  onChange={(e) => setSkipDNC(e.target.checked)}
                  className="mt-1 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                <div>
                  <span className="text-sm font-medium text-gray-800">Enforce Do-Not-Contact list</span>
                  <p className="text-xs text-gray-500">Automatically filter out blacklisted executive profiles.</p>
                </div>
              </label>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button onClick={() => setStep(2)} className="text-xs text-gray-500 hover:text-gray-800">
                Back
              </button>
              <button
                onClick={handleExecuteImport}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-sm"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Import Leads
              </button>
            </div>
          </div>
        )}

        {/* Step 3 Success State */}
        {importResult && (
          <div className="text-center py-6">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-3">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <h3 className="font-bold text-gray-900 text-lg">Leads Enrolled Successfully!</h3>
            <div className="mt-4 grid grid-cols-3 gap-3 max-w-sm mx-auto text-center">
              <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-100">
                <span className="block text-xl font-bold text-emerald-700">{importResult.imported_count}</span>
                <span className="text-xs text-emerald-600 font-medium">Imported</span>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl border border-gray-200">
                <span className="block text-xl font-bold text-gray-700">{importResult.duplicates_count}</span>
                <span className="text-xs text-gray-500 font-medium">Duplicates</span>
              </div>
              <div className="p-3 bg-gray-50 rounded-xl border border-gray-200">
                <span className="block text-xl font-bold text-gray-700">{importResult.skipped_count}</span>
                <span className="text-xs text-gray-500 font-medium">Skipped/DNC</span>
              </div>
            </div>
            <button
              onClick={onClose}
              className="mt-6 inline-flex items-center rounded-xl bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              View in CRM
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
