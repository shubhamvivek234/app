/**
 * BulkCSVModal — 2-step modal
 * Step 1: Download template + upload CSV
 * Step 2: Review Content table (per-row validation) + schedule/draft actions
 */
import React, { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  FaTimes, FaDownload, FaCloudUploadAlt, FaCheckCircle,
  FaExclamationTriangle, FaSpinner, FaExternalLinkAlt, FaFileCsv,
} from 'react-icons/fa';
import { SiInstagram } from 'react-icons/si';

const VALID_PLATFORMS = ['instagram', 'youtube', 'twitter', 'tiktok', 'linkedin', 'facebook', 'bluesky'];
const PLATFORM_CHAR_LIMITS = {
  instagram: 2200, facebook: 63206, twitter: 280, tiktok: 4000,
  linkedin: 3000, youtube: 5000, bluesky: 300,
};
const TITLE_LIMITS = { youtube: 100, linkedin: 150 };
// Very basic IANA format check — full list would be a large lookup
const IANA_RE = /^[A-Za-z_]+\/[A-Za-z_]+$/;
const PRIVATE_IP_RE = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)/;

// ── CSV parser ────────────────────────────────────────────────────────────────
const parseCSV = (text) => {
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split('\n');
  if (!lines.length) return { headers: [], rows: [] };

  const parseRow = (line) => {
    const cols = [];
    let cur = '';
    let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQ && line[i + 1] === '"') { cur += '"'; i++; }
        else { inQ = !inQ; }
        continue;
      }
      if (ch === ',' && !inQ) { cols.push(cur); cur = ''; continue; }
      cur += ch;
    }
    cols.push(cur);
    return cols.map((c) => c.trim());
  };

  const headers = parseRow(lines[0]).map((h) => h.toLowerCase().trim().replace(/\s+/g, '_'));
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const cols = parseRow(line);
    const obj = { _row: i };
    headers.forEach((h, j) => { obj[h] = (cols[j] || '').trim(); });
    rows.push(obj);
  }
  return { headers, rows };
};

// ── 7-Layer validation ────────────────────────────────────────────────────────
const parseDateTime = (str) => {
  if (!str) return null;
  const formats = [
    /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/,          // YYYY-MM-DD HH:mm
    /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/,        // MM/DD/YYYY HH:mm
    /^(\d{2})\/(\d{2})\/(\d{4}) (\d{1,2}):(\d{2})(AM|PM)$/i, // MM/DD/YYYY HH:mmAM/PM
    /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})$/,        // DD/MM/YYYY HH:mm
  ];
  for (const re of formats) {
    if (re.test(str.trim())) return new Date(str);
  }
  return null;
};

const validateRow = (row, headers) => {
  const errors = [];
  const warnings = [];

  // Layer 2 — Structure
  const hasContent = row.content;
  const hasImages = row.image_urls;
  const hasVideo = row.video_url;
  if (!hasContent && !hasImages && !hasVideo) errors.push('At least one of content, image_urls, or video_url is required');
  if (hasImages && hasVideo) errors.push('Cannot have both image_urls and video_url in the same row');
  if (!row.platforms) errors.push('platforms is required');

  // Layer 3 — Platform
  const platforms = (row.platforms || '').toLowerCase().split(',').map((p) => p.trim()).filter(Boolean);
  for (const p of platforms) {
    if (!VALID_PLATFORMS.includes(p)) errors.push(`Unknown platform: "${p}"`);
  }
  if (row.post_type === 'reel' && !platforms.includes('instagram')) {
    errors.push('post_type "reel" requires instagram');
  }
  if (row.post_type === 'story' && !platforms.some((p) => ['instagram', 'facebook'].includes(p))) {
    errors.push('post_type "story" requires instagram or facebook');
  }

  // Layer 4 — Content char limits
  if (row.content) {
    for (const p of platforms) {
      const limit = PLATFORM_CHAR_LIMITS[p];
      if (limit && row.content.length > limit) {
        errors.push(`Content exceeds ${p} limit (${row.content.length}/${limit} chars)`);
      }
    }
    if (platforms.includes('instagram') && row.content.length > 125) {
      warnings.push('Instagram: content over 125 chars will be hidden behind "more"');
    }
    if (platforms.includes('linkedin') && row.content.length > 140) {
      warnings.push('LinkedIn: content over 140 chars collapses to "See more"');
    }
  }
  if (row.title) {
    if (platforms.includes('youtube') && row.title.length > TITLE_LIMITS.youtube) {
      errors.push(`YouTube title exceeds 100 chars (${row.title.length})`);
    }
    if (platforms.includes('linkedin') && row.title.length > TITLE_LIMITS.linkedin) {
      errors.push(`LinkedIn title exceeds 150 chars (${row.title.length})`);
    }
  }

  // Layer 5 — DateTime
  if (row.scheduled_time) {
    const dt = parseDateTime(row.scheduled_time);
    if (!dt || isNaN(dt.getTime())) {
      errors.push('Unrecognisable scheduled_time format — use YYYY-MM-DD HH:mm');
    } else {
      const now = new Date();
      if (dt < now) errors.push('scheduled_time is in the past');
      const maxFuture = new Date(now.getTime() + 365 * 24 * 60 * 60 * 1000);
      if (dt > maxFuture) errors.push('scheduled_time is more than 365 days ahead');
      const twoMin = new Date(now.getTime() + 2 * 60 * 1000);
      if (dt > now && dt < twoMin) warnings.push('scheduled_time is within 2 minutes of now');
    }
  }
  if (row.timezone && !IANA_RE.test(row.timezone)) {
    errors.push(`Invalid timezone format: "${row.timezone}" — use IANA string e.g. America/New_York`);
  }

  // Layer 6 — URLs (format only, no network)
  if (row.image_urls) {
    const urls = row.image_urls.split('||').map((u) => u.trim());
    if (urls.length > 10) errors.push('image_urls: max 10 URLs per row');
    for (const u of urls) {
      if (!u.startsWith('http')) errors.push(`Invalid image URL: "${u.slice(0, 40)}"`);
      else if (PRIVATE_IP_RE.test(u.replace(/^https?:\/\//, ''))) errors.push('image_url targets a private/internal address (SSRF risk)');
      else if (!/\.(jpg|jpeg|png|webp|gif)(\?.*)?$/i.test(u) &&
               !/drive\.google\.com|dropbox\.com/i.test(u)) {
        warnings.push(`URL may not be a direct image link: "${u.slice(0, 40)}"`);
      }
    }
  }
  if (row.video_url) {
    if (!row.video_url.startsWith('http')) errors.push('Invalid video_url');
    else if (PRIVATE_IP_RE.test(row.video_url.replace(/^https?:\/\//, ''))) errors.push('video_url targets a private/internal address (SSRF risk)');
  }

  return { errors, warnings };
};

const truncate = (s, n = 50) => (!s ? '—' : s.length > n ? s.slice(0, n) + '…' : s);

// ── Status icon ───────────────────────────────────────────────────────────────
const RowStatus = ({ errors, warnings }) => {
  if (errors.length) return <FaExclamationTriangle className="text-red-500 text-sm" title={errors.join('\n')} />;
  if (warnings.length) return <FaExclamationTriangle className="text-amber-400 text-sm" title={warnings.join('\n')} />;
  return <FaCheckCircle className="text-green-500 text-sm" />;
};

// ── Main Modal ────────────────────────────────────────────────────────────────
const BulkCSVModal = ({ onClose }) => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1 = upload, 2 = review
  const [dragging, setDragging] = useState(false);
  const [rows, setRows] = useState([]);
  const [rowResults, setRowResults] = useState([]); // [{errors, warnings}]
  const [fileName, setFileName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef(null);

  const processFile = useCallback((file) => {
    if (!file) return;
    if (!file.name.endsWith('.csv')) { toast.error('Please upload a .csv file'); return; }
    if (file.size > 10 * 1024 * 1024) { toast.error('CSV file must be under 10 MB'); return; }

    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const { headers, rows: parsed } = parseCSV(e.target.result);
        if (!parsed.length) { toast.error('CSV has no data rows'); return; }

        // Check required headers present (layers 1 check client side)
        const required = ['content', 'platforms'];
        const missingHeaders = required.filter((h) => !headers.includes(h) && !headers.some((hh) => hh === h));
        if (missingHeaders.length) {
          const guessOld = headers.some((h) => h === 'text' || h === 'image_url');
          if (guessOld) {
            toast.error('CSV uses old column names. Download the new template — columns are: content, platforms, accounts, scheduled_time, timezone, image_urls, video_url, title, tags, post_type');
            return;
          }
        }

        const results = parsed.map((row) => validateRow(row, headers));
        setRows(parsed);
        setRowResults(results);
        setStep(2);
      } catch {
        toast.error('Failed to parse CSV. Ensure it is UTF-8 encoded and matches the template.');
      }
    };
    reader.readAsText(file);
  }, []);

  const validRows = rows.filter((_, i) => rowResults[i]?.errors?.length === 0);
  const errorCount = rows.length - validRows.length;
  const warningCount = rowResults.filter((r) => r.warnings?.length > 0 && r.errors?.length === 0).length;

  const handleSubmit = async (asDraft) => {
    if (!validRows.length) { toast.error('No valid rows to schedule'); return; }
    setSubmitting(true);
    try {
      const token = localStorage.getItem('token');
      const postsPayload = validRows.map((row) => {
        let scheduledTime = null;
        if (row.scheduled_time) {
          const dt = parseDateTime(row.scheduled_time);
          if (dt) scheduledTime = dt.toISOString();
        }
        return {
          content: row.content || '',
          platforms: row.platforms.toLowerCase().split(',').map((p) => p.trim()),
          accounts: row.accounts || 'all',
          scheduled_time: scheduledTime,
          timezone: row.timezone || 'UTC',
          image_urls: row.image_urls ? row.image_urls.split('||').map((u) => u.trim()) : [],
          video_url: row.video_url || null,
          title: row.title || null,
          tags: row.tags ? row.tags.split(',').map((t) => t.trim()) : [],
          post_type: row.post_type || null,
          status: asDraft ? 'draft' : 'scheduled',
        };
      });

      const res = await fetch(
        `${process.env.REACT_APP_BACKEND_URL}/api/v1/bulk/csv-schedule`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ posts: postsPayload }),
        }
      );
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Server error');

      toast.success(
        asDraft
          ? `${data.created} post${data.created !== 1 ? 's' : ''} saved as drafts`
          : `${data.created} post${data.created !== 1 ? 's' : ''} scheduled`
      );
      onClose();
      navigate('/content');
    } catch (err) {
      toast.error(err.message || 'Import failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const downloadTemplate = () => {
    const cols = 'content,platforms,accounts,scheduled_time,timezone,image_urls,video_url,title,tags,post_type';
    const example = '"Hello world! First post via CSV","instagram,twitter","all","2025-06-01 10:00","Asia/Kolkata","","","","social,marketing","text"';
    const csv = [cols, example].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'socialentangler_bulk_template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">

        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-green-600">
              <FaFileCsv className="text-lg" />
              <span className="text-gray-400 text-sm">→</span>
              <SiInstagram className="text-lg" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">
                {step === 1 ? 'Import Your Posts' : 'Review Content'}
              </h2>
              {step === 2 && (
                <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-3">
                  <span className="flex items-center gap-1 text-green-600">
                    <FaCheckCircle className="text-[10px]" /> {validRows.length} valid post{validRows.length !== 1 ? 's' : ''}
                  </span>
                  {errorCount > 0 && (
                    <span className="flex items-center gap-1 text-red-500">
                      <FaExclamationTriangle className="text-[10px]" /> {errorCount} with errors
                    </span>
                  )}
                  {warningCount > 0 && (
                    <span className="flex items-center gap-1 text-amber-500">
                      <FaExclamationTriangle className="text-[10px]" /> {warningCount} with warnings
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
            <FaTimes />
          </button>
        </div>

        {/* Step 1 — Upload */}
        {step === 1 && (
          <div className="p-6 space-y-5 overflow-y-auto">
            {/* Prepare CSV section */}
            <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
              <h3 className="text-sm font-semibold text-gray-900 mb-1">1. Prepare your CSV file</h3>
              <p className="text-xs text-gray-500 mb-3 leading-relaxed">
                Make sure your CSV file is in the correct format: <strong>content, platforms, accounts, scheduled_time, timezone, image_urls, video_url, title, tags, post_type</strong>.
                Download our template to get started, and check our{' '}
                <button
                  onClick={() => { onClose(); navigate('/bulk-upload-guide'); }}
                  className="text-blue-600 hover:underline"
                >
                  guide
                </button>
                {' '}if you need help.
              </p>

              {/* Template preview mini-table */}
              <div className="overflow-x-auto rounded-lg border border-gray-200 mb-3 bg-white">
                <table className="text-[10px] min-w-[400px]">
                  <thead>
                    <tr className="bg-gray-50">
                      {['content', 'platforms', 'accounts', 'scheduled_time', '…'].map((h) => (
                        <th key={h} className="px-2 py-1.5 text-left font-semibold text-gray-500 border-b border-gray-200">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[1, 2, 3].map((r) => (
                      <tr key={r} className="border-b border-gray-100 last:border-0">
                        {[1, 2, 3, 4, 5].map((c) => (
                          <td key={c} className="px-2 py-1.5 text-gray-300">—</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <button
                onClick={downloadTemplate}
                className="flex items-center gap-2 px-4 py-2 text-xs font-semibold border border-gray-300 bg-white hover:bg-gray-50 text-gray-700 rounded-lg transition-colors shadow-sm"
              >
                <FaDownload className="text-[10px]" />
                Download CSV Template
              </button>
            </div>

            {/* Upload CSV section */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-3">2. Upload your CSV file</h3>
              <div
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => { e.preventDefault(); setDragging(false); processFile(e.dataTransfer.files?.[0]); }}
                className={`border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center gap-3 transition-colors cursor-pointer ${
                  dragging ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-offwhite hover:border-green-300'
                }`}
                onClick={() => fileInputRef.current?.click()}
              >
                <FaCloudUploadAlt className={`text-3xl ${dragging ? 'text-green-400' : 'text-gray-300'}`} />
                <p className="text-sm font-medium text-gray-500">
                  {dragging ? 'Drop your CSV here' : 'Drag and drop your CSV file here or'}
                </p>
                <button
                  onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                  className="px-4 py-1.5 text-xs font-semibold bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg transition-colors shadow-sm"
                >
                  <FaCloudUploadAlt className="inline mr-1.5" /> Upload file
                </button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => { processFile(e.target.files?.[0]); e.target.value = ''; }}
              />
            </div>
          </div>
        )}

        {/* Step 2 — Review */}
        {step === 2 && (
          <>
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="overflow-x-auto rounded-xl border border-gray-200">
                <table className="w-full text-sm min-w-[580px]">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      {['#', 'Content', 'Image', 'Platforms', 'Scheduled Time', 'Status'].map((h) => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 whitespace-nowrap">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => {
                      const { errors, warnings } = rowResults[i] || { errors: [], warnings: [] };
                      const hasError = errors.length > 0;
                      return (
                        <tr
                          key={i}
                          className={`border-b border-gray-50 last:border-0 ${hasError ? 'bg-red-50/40' : 'bg-white'}`}
                        >
                          <td className="px-4 py-3 text-xs text-gray-400 font-mono">{row._row}</td>
                          <td className="px-4 py-3 text-xs text-gray-700 max-w-[180px]">
                            <span title={row.content}>{truncate(row.content)}</span>
                          </td>
                          <td className="px-4 py-3">
                            {row.image_urls ? (
                              <div className="w-8 h-8 bg-gray-100 rounded border border-gray-200 flex items-center justify-center">
                                <FaFileCsv className="text-gray-400 text-xs" />
                              </div>
                            ) : (
                              <span className="text-gray-300 text-xs">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500 capitalize">
                            {truncate(row.platforms, 25)}
                          </td>
                          <td className="px-4 py-3 text-xs text-gray-500">
                            {row.scheduled_time || <span className="text-gray-300 italic">Add to Queue</span>}
                          </td>
                          <td className="px-4 py-3">
                            <RowStatus errors={errors} warnings={warnings} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {errorCount > 0 && (
                <p className="text-xs text-gray-500 mt-3 bg-gray-50 rounded-lg px-4 py-2.5 border border-gray-200">
                  <FaExclamationTriangle className="inline text-amber-400 mr-1.5" />
                  <strong>{errorCount}</strong> row{errorCount !== 1 ? 's' : ''} with errors will be skipped.
                  {' '}<strong>{validRows.length}</strong> valid row{validRows.length !== 1 ? 's' : ''} will be imported.
                </p>
              )}
            </div>

            {/* Step 2 footer */}
            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between gap-3">
              <button
                onClick={() => { setStep(1); setRows([]); setRowResults([]); }}
                className="text-xs font-medium text-gray-400 hover:text-gray-600 transition-colors"
              >
                ← Upload different file
              </button>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => handleSubmit(true)}
                  disabled={submitting || !validRows.length}
                  className="px-5 py-2.5 text-xs font-semibold border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submitting ? <FaSpinner className="animate-spin inline mr-1.5" /> : null}
                  Save as Drafts
                </button>
                <button
                  onClick={() => handleSubmit(false)}
                  disabled={submitting || !validRows.length}
                  className="px-5 py-2.5 text-xs font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow"
                >
                  {submitting ? <FaSpinner className="animate-spin inline mr-1.5" /> : null}
                  Schedule Posts
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default BulkCSVModal;
