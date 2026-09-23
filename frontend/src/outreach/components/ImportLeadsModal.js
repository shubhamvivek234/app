import React, { useState, useEffect } from 'react';
import {
  FileSpreadsheet, Search, Users, MessageSquare, Upload, ArrowRight, X, AlertCircle,
  CheckCircle2, Loader2, Shield, Sparkles, Calendar, Bookmark, ExternalLink,
  Check, Filter, ChevronDown, ThumbsUp, MessageCircle
} from 'lucide-react';

export default function ImportLeadsModal({ isOpen, onClose, campaignId, onLeadsImported }) {
  // Step 1: Choose Source, Step 2: Input / Finder, Step 3: Filters & Ingest
  const [step, setStep] = useState(1);
  const [sourceType, setSourceType] = useState('finder'); // 'finder' | 'list' | 'search' | 'csv' | 'event' | 'post' | 'group'

  // Post Engager Options
  const [postUrl, setPostUrl] = useState('');
  const [pushOption, setPushOption] = useState('Only existing comments/likes');
  const [exportLikes, setExportLikes] = useState(true);
  const [exportComments, setExportComments] = useState(true);

  // Standard Search & CSV
  const [csvContent, setCsvContent] = useState('');
  const [searchUrl, setSearchUrl] = useState('');
  const [skipContacted, setSkipContacted] = useState(true);
  const [skipDNC, setSkipDNC] = useState(true);

  // Lead Finder State
  const [finderFilters, setFinderFilters] = useState({
    title: 'VP of Growth',
    industry: 'SaaS & Enterprise Software',
    company_size: '51-200',
    location: 'San Francisco, CA',
    connection_degree: '2nd',
    has_posted_recently: true,
    changed_jobs: false,
    mentioned_in_news: false,
  });
  const [finderCandidates, setFinderCandidates] = useState([]);
  const [selectedCandidates, setSelectedCandidates] = useState([]);
  const [searchingFinder, setSearchingFinder] = useState(false);
  const [finderTotal, setFinderTotal] = useState(0);

  // General State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [importResult, setImportResult] = useState(null);

  // Trigger preview when opening Lead Finder
  useEffect(() => {
    if (isOpen && sourceType === 'finder' && step === 2) {
      handleSearchFinder();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, sourceType, step]);

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

  const handleSearchFinder = async () => {
    setSearchingFinder(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/leads/finder/preview', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          ...finderFilters,
          limit: 15,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to search leads');
      setFinderCandidates(data.results || []);
      setFinderTotal(data.total_matched || 0);
      // Select all by default
      setSelectedCandidates((data.results || []).map((c) => c.id));
    } catch (err) {
      setError(err.message);
    } finally {
      setSearchingFinder(false);
    }
  };

  const toggleSelectCandidate = (id) => {
    setSelectedCandidates((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    if (selectedCandidates.length === finderCandidates.length) {
      setSelectedCandidates([]);
    } else {
      setSelectedCandidates(finderCandidates.map((c) => c.id));
    }
  };

  const handleEnrollFinderLeads = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const candidatesToEnroll = finderCandidates.filter((c) =>
        selectedCandidates.includes(c.id)
      );

      const res = await fetch('/api/v1/outreach/leads/finder/enroll', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          campaign_id: campaignId,
          leads: candidatesToEnroll,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Enrollment failed');
      setImportResult(data);
      if (onLeadsImported) onLeadsImported(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
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
      } else if (sourceType === 'post') {
        res = await fetch('/api/v1/outreach/leads/import-post-engagers', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({
            campaign_id: campaignId,
            post_url: postUrl,
            push_option: pushOption,
            export_likes: exportLikes,
            export_comments: exportComments,
            max_leads: 50,
          }),
        });
      } else {
        // search, sales_nav, event, group
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

  const resetAll = () => {
    setStep(1);
    setImportResult(null);
    setError(null);
    setSearchUrl('');
    setCsvContent('');
    setPostUrl('');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4 overflow-y-auto">
      <div
        className={`relative w-full ${
          step === 2 && sourceType === 'finder' ? 'max-w-5xl' : 'max-w-2xl'
        } rounded-2xl bg-white shadow-2xl border border-gray-100 transition-all flex flex-col max-h-[92vh]`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-600">
                LinkedIn Outbound · Ingestion Engine
              </span>
              <span className="text-[10px] bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded-full">
                Step {step} of 3
              </span>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mt-0.5">
              {step === 1 && 'Where are your leads?'}
              {step === 2 && sourceType === 'finder' && 'Interactive Lead Finder'}
              {step === 2 && sourceType === 'post' && 'Import from LinkedIn Post'}
              {step === 2 && sourceType !== 'finder' && sourceType !== 'post' && 'Provide Source URL or File'}
              {step === 3 && (importResult ? 'Import Complete' : 'Safety & Deduplication Filters')}
            </h2>
          </div>
          <button
            onClick={() => { resetAll(); onClose(); }}
            className="rounded-full p-1.5 text-gray-400 hover:bg-gray-100 transition-colors"
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
          {/* ── STEP 1: 7-Source Grid (Matching source_082s.jpg) ─────────────── */}
          {step === 1 && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500 mb-2">
                Choose how you'd like to import your prospect list into this campaign:
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {/* 1. Lead Finder (Popular) */}
                <button
                  onClick={() => { setSourceType('finder'); setStep(2); }}
                  className="text-left p-4 rounded-xl border-2 border-indigo-200 hover:border-indigo-600 hover:bg-indigo-50/20 bg-indigo-50/10 transition-all group relative"
                >
                  <div className="absolute top-3 right-3 flex items-center gap-1 bg-indigo-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-full shadow-xs">
                    <Sparkles className="h-3 w-3" />
                    Popular
                  </div>
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-indigo-600 text-white shadow-sm">
                      <Sparkles className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Lead finder</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Explore LinkedIn prospects directly in-app with 10+ filters</p>
                    </div>
                  </div>
                </button>

                {/* 2. Add from my list */}
                <button
                  onClick={() => { setSourceType('list'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-emerald-50 text-emerald-600 group-hover:bg-emerald-600 group-hover:text-white transition-colors">
                      <Bookmark className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Add from my list</h4>
                      <p className="text-xs text-gray-400 mt-0.5">Enroll prospects from your saved CRM lists</p>
                    </div>
                  </div>
                </button>

                {/* 3. LinkedIn Search */}
                <button
                  onClick={() => { setSourceType('search'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-blue-50 text-blue-600 group-hover:bg-blue-600 group-hover:text-white transition-colors">
                      <Search className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Import from LinkedIn search</h4>
                      <p className="text-xs text-gray-400 mt-0.5">Paste standard or Sales Navigator search URL</p>
                    </div>
                  </div>
                </button>

                {/* 4. CSV File */}
                <button
                  onClick={() => { setSourceType('csv'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-violet-50 text-violet-600 group-hover:bg-violet-600 group-hover:text-white transition-colors">
                      <FileSpreadsheet className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Import from CSV file</h4>
                      <p className="text-xs text-gray-400 mt-0.5">Upload .csv spreadsheet with profile links</p>
                    </div>
                  </div>
                </button>

                {/* 5. LinkedIn Event */}
                <button
                  onClick={() => { setSourceType('event'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-amber-50 text-amber-600 group-hover:bg-amber-600 group-hover:text-white transition-colors">
                      <Calendar className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Import from LinkedIn event</h4>
                      <p className="text-xs text-gray-400 mt-0.5">Capture attendees from public LinkedIn events</p>
                    </div>
                  </div>
                </button>

                {/* 6. LinkedIn Post Engagers */}
                <button
                  onClick={() => { setSourceType('post'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-pink-50 text-pink-600 group-hover:bg-pink-600 group-hover:text-white transition-colors">
                      <MessageSquare className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Import from LinkedIn post</h4>
                      <p className="text-xs text-gray-400 mt-0.5">Scrape commenters and likers from viral posts</p>
                    </div>
                  </div>
                </button>

                {/* 7. LinkedIn Group */}
                <button
                  onClick={() => { setSourceType('group'); setStep(2); }}
                  className="text-left p-4 rounded-xl border border-gray-200 hover:border-indigo-500 hover:bg-gray-50 transition-all group md:col-span-2"
                >
                  <div className="flex items-center gap-3.5">
                    <div className="p-2.5 rounded-xl bg-cyan-50 text-cyan-600 group-hover:bg-cyan-600 group-hover:text-white transition-colors">
                      <Users className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-gray-900 text-sm">Import from LinkedIn group</h4>
                      <p className="text-xs text-gray-400 mt-0.5">Extract active members from community groups you belong to</p>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 2A: Interactive Lead Finder (lead_finder_125s.jpg) ──────── */}
          {step === 2 && sourceType === 'finder' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                {/* Left Filter Bar */}
                <div className="lg:col-span-4 bg-gray-50/80 p-4 rounded-xl border border-gray-200 space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-gray-200">
                    <span className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-1.5">
                      <Filter className="h-3.5 w-3.5 text-indigo-600" />
                      Search Filters
                    </span>
                    <button
                      onClick={handleSearchFinder}
                      disabled={searchingFinder}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800"
                    >
                      {searchingFinder ? 'Filtering...' : 'Apply'}
                    </button>
                  </div>

                  {/* Title Keyword */}
                  <div>
                    <label className="text-[11px] font-semibold text-gray-600 block mb-1">Job Title</label>
                    <input
                      type="text"
                      value={finderFilters.title}
                      onChange={(e) => setFinderFilters({ ...finderFilters, title: e.target.value })}
                      placeholder="e.g. VP Sales, Growth, Founder"
                      className="w-full text-xs rounded-lg border border-gray-300 px-2.5 py-1.5 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>

                  {/* Industry */}
                  <div>
                    <label className="text-[11px] font-semibold text-gray-600 block mb-1">Industry</label>
                    <select
                      value={finderFilters.industry}
                      onChange={(e) => setFinderFilters({ ...finderFilters, industry: e.target.value })}
                      className="w-full text-xs rounded-lg border border-gray-300 px-2.5 py-1.5 focus:border-indigo-500"
                    >
                      <option value="SaaS & Enterprise Software">SaaS & Enterprise Software</option>
                      <option value="Artificial Intelligence">Artificial Intelligence</option>
                      <option value="Fintech">Fintech</option>
                      <option value="Digital Marketing">Digital Marketing</option>
                      <option value="Cybersecurity">Cybersecurity</option>
                    </select>
                  </div>

                  {/* Company Size */}
                  <div>
                    <label className="text-[11px] font-semibold text-gray-600 block mb-1">Company Headcount</label>
                    <select
                      value={finderFilters.company_size}
                      onChange={(e) => setFinderFilters({ ...finderFilters, company_size: e.target.value })}
                      className="w-full text-xs rounded-lg border border-gray-300 px-2.5 py-1.5 focus:border-indigo-500"
                    >
                      <option value="1-10">1-10 employees</option>
                      <option value="11-50">11-50 employees</option>
                      <option value="51-200">51-200 employees</option>
                      <option value="201-500">201-500 employees</option>
                      <option value="501-1000">501-1000 employees</option>
                      <option value="1000+">1000+ employees</option>
                    </select>
                  </div>

                  {/* Location */}
                  <div>
                    <label className="text-[11px] font-semibold text-gray-600 block mb-1">Location</label>
                    <input
                      type="text"
                      value={finderFilters.location}
                      onChange={(e) => setFinderFilters({ ...finderFilters, location: e.target.value })}
                      placeholder="e.g. San Francisco, London"
                      className="w-full text-xs rounded-lg border border-gray-300 px-2.5 py-1.5 focus:border-indigo-500"
                    />
                  </div>

                  {/* Connection Degree */}
                  <div>
                    <label className="text-[11px] font-semibold text-gray-600 block mb-1.5">Connection Level</label>
                    <div className="grid grid-cols-3 gap-1.5">
                      {['1st', '2nd', '3rd+'].map((deg) => (
                        <button
                          key={deg}
                          type="button"
                          onClick={() => setFinderFilters({ ...finderFilters, connection_degree: deg })}
                          className={`text-xs font-semibold py-1 rounded-md border text-center transition-all ${
                            finderFilters.connection_degree === deg
                              ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs'
                              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-100'
                          }`}
                        >
                          {deg}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Activity Toggles (Prosp parity) */}
                  <div className="pt-2 border-t border-gray-200 space-y-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500 block">
                      Activity Signals
                    </span>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={finderFilters.has_posted_recently}
                        onChange={(e) => setFinderFilters({ ...finderFilters, has_posted_recently: e.target.checked })}
                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-xs text-gray-700 font-medium">Has posted on LinkedIn</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={finderFilters.changed_jobs}
                        onChange={(e) => setFinderFilters({ ...finderFilters, changed_jobs: e.target.checked })}
                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-xs text-gray-700 font-medium">Changed jobs recently</span>
                    </label>
                  </div>

                  <button
                    onClick={handleSearchFinder}
                    disabled={searchingFinder}
                    className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 py-2 text-xs font-semibold text-white hover:bg-indigo-700 shadow-xs disabled:opacity-50"
                  >
                    {searchingFinder ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Searching...
                      </>
                    ) : (
                      <>
                        <Search className="h-3.5 w-3.5" /> Find Prospects
                      </>
                    )}
                  </button>
                </div>

                {/* Right Results Table */}
                <div className="lg:col-span-8 flex flex-col min-h-[380px]">
                  {/* Results Subheader */}
                  <div className="flex items-center justify-between pb-3 border-b border-gray-100 mb-3">
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-gray-700">
                        <input
                          type="checkbox"
                          checked={selectedCandidates.length === finderCandidates.length && finderCandidates.length > 0}
                          onChange={toggleSelectAll}
                          className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        Select All ({selectedCandidates.length}/{finderCandidates.length})
                      </label>
                    </div>
                    <span className="text-xs text-gray-500">
                      Found <strong className="text-gray-900">{finderTotal.toLocaleString()}</strong> matching leads
                    </span>
                  </div>

                  {/* Candidate List */}
                  <div className="space-y-2.5 overflow-y-auto max-h-[380px] pr-1 flex-1">
                    {searchingFinder ? (
                      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                        <Loader2 className="h-7 w-7 animate-spin text-indigo-600 mb-2" />
                        <span className="text-xs font-medium">Querying LinkedIn People Engine...</span>
                      </div>
                    ) : finderCandidates.length === 0 ? (
                      <div className="text-center py-16 text-gray-400 text-xs">
                        No prospects found. Try adjusting your search keywords or location.
                      </div>
                    ) : (
                      finderCandidates.map((cand) => (
                        <div
                          key={cand.id}
                          onClick={() => toggleSelectCandidate(cand.id)}
                          className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center justify-between ${
                            selectedCandidates.includes(cand.id)
                              ? 'border-indigo-400 bg-indigo-50/20 shadow-xs'
                              : 'border-gray-200 hover:border-gray-300 bg-white'
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <input
                              type="checkbox"
                              checked={selectedCandidates.includes(cand.id)}
                              onChange={() => {}} // handled by row onClick
                              className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                            />
                            <img
                              src={cand.avatar_url}
                              alt={cand.first_name}
                              className="h-10 w-10 rounded-full object-cover border border-gray-200"
                            />
                            <div>
                              <div className="flex items-center gap-2">
                                <h4 className="font-bold text-sm text-gray-900">
                                  {cand.first_name} {cand.last_name}
                                </h4>
                                <span className="text-[10px] font-bold px-1.5 py-0.2 bg-gray-100 text-gray-600 rounded">
                                  {cand.connection_degree}
                                </span>
                                {cand.has_posted_recently && (
                                  <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded flex items-center gap-1">
                                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                    Active Poster
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-gray-600 font-medium">
                                {cand.job_title} · <span className="text-indigo-600">{cand.company_name}</span>
                              </p>
                              <p className="text-[11px] text-gray-400">
                                {cand.location} · {cand.industry}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <a
                              href={cand.linkedin_url}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-2.5 py-1 rounded-lg border border-indigo-100"
                            >
                              View on LinkedIn <ExternalLink className="h-3 w-3" />
                            </a>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {/* Bottom Actions */}
              <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                <button
                  onClick={() => setStep(1)}
                  className="text-xs text-gray-500 hover:text-gray-800 font-medium"
                >
                  ← Change Source
                </button>
                <button
                  onClick={handleEnrollFinderLeads}
                  disabled={loading || selectedCandidates.length === 0}
                  className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 shadow-sm disabled:opacity-50 transition-all"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" /> Enrolling Prospects...
                    </>
                  ) : (
                    <>
                      Enroll {selectedCandidates.length} Selected Leads <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 2B: Specialized Post Engagers Modal (time_090s.jpg) ─────── */}
          {step === 2 && sourceType === 'post' && (
            <div className="space-y-5">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-gray-700 mb-1">
                  LinkedIn Post URL
                </label>
                <p className="text-xs text-gray-400 mb-2">
                  Paste the URL of any viral post from your account or an industry competitor:
                </p>
                <input
                  type="url"
                  value={postUrl}
                  onChange={(e) => setPostUrl(e.target.value)}
                  placeholder="https://www.linkedin.com/posts/username_post-title-activity-..."
                  className="w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 font-mono text-xs"
                />
              </div>

              {/* Push Options Dropdown */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-gray-700 mb-1.5">
                  Push Options
                </label>
                <div className="relative">
                  <select
                    value={pushOption}
                    onChange={(e) => setPushOption(e.target.value)}
                    className="w-full appearance-none rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 bg-white pr-8 font-medium text-gray-800"
                  >
                    <option value="Only existing comments/likes">Only existing comments/likes</option>
                    <option value="Push new ones too">Push new ones too (Continuous live engagers)</option>
                  </select>
                  <ChevronDown className="absolute right-3 top-3 h-4 w-4 pointer-events-none text-gray-400" />
                </div>
              </div>

              {/* Granular Toggles (Matching time_090s.jpg) */}
              <div className="rounded-xl bg-gray-50/80 p-4 border border-gray-200 space-y-3.5">
                <span className="text-[11px] font-bold uppercase tracking-wider text-gray-600 block">
                  Engagement Sourcing Channels
                </span>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-pink-100 text-pink-600">
                      <MessageCircle className="h-4 w-4" />
                    </div>
                    <div>
                      <h5 className="text-xs font-bold text-gray-800">Export Comments</h5>
                      <p className="text-[11px] text-gray-500">Capture prospects who left comments on the post</p>
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={exportComments}
                    onChange={(e) => setExportComments(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-lg bg-blue-100 text-blue-600">
                      <ThumbsUp className="h-4 w-4" />
                    </div>
                    <div>
                      <h5 className="text-xs font-bold text-gray-800">Export Likes</h5>
                      <p className="text-[11px] text-gray-500">Capture prospects who reacted or liked the post</p>
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={exportLikes}
                    onChange={(e) => setExportLikes(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="flex justify-between items-center pt-2">
                <button onClick={() => setStep(1)} className="text-xs text-gray-500 hover:text-gray-800 font-medium">
                  ← Back to Sources
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!postUrl.trim() || (!exportLikes && !exportComments)}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 shadow-sm"
                >
                  Next: Safety Filters <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 2C: Standard CSV Upload ─────────────────────────────────── */}
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
                  ← Back
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 2D: Search / Event / Group URL Input ────────────────────── */}
          {step === 2 && sourceType !== 'finder' && sourceType !== 'post' && sourceType !== 'csv' && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-gray-700">
                  {sourceType === 'event'
                    ? 'LinkedIn Event URL'
                    : sourceType === 'group'
                    ? 'LinkedIn Group URL'
                    : 'LinkedIn Search Results URL'}
                </label>
                <input
                  type="url"
                  value={searchUrl}
                  onChange={(e) => setSearchUrl(e.target.value)}
                  placeholder={
                    sourceType === 'event'
                      ? 'https://www.linkedin.com/events/tech-summit-2026/...'
                      : sourceType === 'group'
                      ? 'https://www.linkedin.com/groups/12345/...'
                      : 'https://www.linkedin.com/search/results/people/?keywords=...'
                  }
                  className="mt-1.5 w-full rounded-xl border border-gray-300 px-3.5 py-2.5 text-sm focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="flex justify-between pt-2">
                <button onClick={() => setStep(1)} className="text-xs text-gray-500 hover:text-gray-800">
                  ← Back
                </button>
                <button
                  onClick={() => setStep(3)}
                  disabled={!searchUrl.trim()}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  Next: Safety Filters <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 3: Safety & Ingest Confirmation ─────────────────────────── */}
          {step === 3 && !importResult && (
            <div className="space-y-5">
              <div className="rounded-xl bg-gray-50 p-4 border border-gray-100 space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-1.5">
                  <Shield className="h-4 w-4 text-indigo-600" />
                  Contact Safety & Deduplication Engine
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
                    <p className="text-xs text-gray-500">Automatically suppresses leads listed on your exclusion CRM.</p>
                  </div>
                </label>
              </div>

              <div className="flex justify-between items-center pt-2">
                <button onClick={() => setStep(2)} className="text-xs text-gray-500 hover:text-gray-800">
                  ← Back to Source
                </button>
                <button
                  onClick={handleExecuteImport}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-50 shadow-sm"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" /> Ingesting & Deduplicating...
                    </>
                  ) : (
                    'Confirm & Ingest Leads'
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ── Import Completed Banner ──────────────────────────────────────── */}
          {importResult && (
            <div className="space-y-5 text-center py-4">
              <div className="h-14 w-14 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto border border-emerald-100">
                <CheckCircle2 className="h-8 w-8" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-gray-900">Leads Successfully Enrolled!</h3>
                <p className="text-xs text-gray-500 mt-1">
                  Your prospects are loaded into the campaign queue and ready for outbound sequence dispatch.
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3 max-w-md mx-auto">
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-100">
                  <span className="text-lg font-bold text-emerald-600">
                    {importResult.enrolled ?? importResult.imported_count ?? 0}
                  </span>
                  <p className="text-[11px] text-gray-500 font-medium mt-0.5">Enrolled</p>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-100">
                  <span className="text-lg font-bold text-gray-700">{importResult.duplicates_count ?? 0}</span>
                  <p className="text-[11px] text-gray-500 font-medium mt-0.5">Duplicates</p>
                </div>
                <div className="p-3 rounded-xl bg-gray-50 border border-gray-100">
                  <span className="text-lg font-bold text-gray-700">{importResult.skipped_count ?? 0}</span>
                  <p className="text-[11px] text-gray-500 font-medium mt-0.5">Skipped (Safety)</p>
                </div>
              </div>

              <div className="pt-2">
                <button
                  onClick={() => { resetAll(); onClose(); }}
                  className="rounded-xl bg-gray-900 px-6 py-2.5 text-xs font-bold text-white hover:bg-black shadow-sm"
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
