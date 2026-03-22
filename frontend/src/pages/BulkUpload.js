import React, { useState, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { bulkCreatePosts, downloadBulkTemplate } from '@/lib/api';
import { toast } from 'sonner';
import {
  FaFileUpload, FaDownload, FaCheckCircle, FaExclamationTriangle,
  FaTimesCircle, FaTimes, FaCloudUploadAlt, FaTable, FaExternalLinkAlt
} from 'react-icons/fa';

const AVAILABLE_PLATFORMS = ['instagram', 'twitter', 'facebook', 'linkedin', 'youtube', 'tiktok'];

// ── CSV Parser ────────────────────────────────────────────────────────────────
// Handles quoted fields (commas inside quotes), trims whitespace
const parseCSV = (text) => {
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim().split('\n');
  if (lines.length < 1) return [];

  const parseRow = (line) => {
    const cols = [];
    let cur = '';
    let inQuote = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuote && line[i + 1] === '"') { cur += '"'; i++; } // escaped quote
        else { inQuote = !inQuote; }
        continue;
      }
      if (ch === ',' && !inQuote) { cols.push(cur); cur = ''; continue; }
      cur += ch;
    }
    cols.push(cur);
    return cols.map((c) => c.trim());
  };

  const headers = parseRow(lines[0]).map((h) => h.toLowerCase().replace(/\s+/g, '_'));
  const rows = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const cols = parseRow(line);
    const obj = { _row: i };
    headers.forEach((h, j) => { obj[h] = (cols[j] || '').trim(); });
    rows.push(obj);
  }
  return rows;
};

// ── Per-row validation (client-side preview only) ─────────────────────────────
const validateRow = (row) => {
  const errors = [];
  if (!row.text) errors.push('Text is required');
  if (row.posting_time) {
    const ts = row.posting_time.trim();
    if (ts && !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(ts) && !/^\d{4}-\d{2}-\d{2}T/.test(ts)) {
      errors.push('Posting Time must be YYYY-MM-DD HH:MM');
    }
  }
  // Optional image URL check
  if (row.image_url && !row.image_url.startsWith('http')) {
    errors.push('Image URL must start with http/https');
  }
  return errors;
};

const truncate = (str, n = 55) => (!str ? '—' : str.length > n ? str.slice(0, n) + '…' : str);

// ── Status badge ──────────────────────────────────────────────────────────────
const StatusBadge = ({ errors }) => {
  if (!errors.length) {
    return (
      <span className="flex items-center gap-1 text-green-600 text-xs font-medium">
        <FaCheckCircle /> Valid
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-red-500 text-xs font-medium" title={errors.join('\n')}>
      <FaExclamationTriangle /> {errors[0]}{errors.length > 1 ? ` (+${errors.length - 1})` : ''}
    </span>
  );
};

// ── Drop zone ─────────────────────────────────────────────────────────────────
const DropZone = ({ onFile, dragging, onDragOver, onDragLeave, onDrop }) => (
  <div
    onDragOver={onDragOver}
    onDragLeave={onDragLeave}
    onDrop={onDrop}
    className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center gap-4 transition-colors mt-6 ${
      dragging ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-offwhite hover:border-gray-300'
    }`}
  >
    <FaCloudUploadAlt className={`text-5xl ${dragging ? 'text-green-400' : 'text-gray-300'}`} />
    <div className="text-center">
      <p className="text-sm font-semibold text-gray-600">
        {dragging ? 'Drop your CSV here' : 'Drag & drop a CSV file here'}
      </p>
      <p className="text-xs text-gray-400 mt-0.5">We will parse Text, Image URL, Tags, and Posting Time</p>
    </div>
    <button
      onClick={onFile}
      className="px-5 py-2 text-sm font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
    >
      Browse File
    </button>
  </div>
);

// ── Preview table ─────────────────────────────────────────────────────────────
const PreviewTable = ({ rows, rowErrors }) => (
  <div className="overflow-x-auto rounded-xl border border-gray-200 mt-4">
    <table className="w-full text-sm min-w-[700px]">
      <thead>
        <tr className="bg-offwhite border-b border-gray-200">
          {['#', 'Text', 'Image URL', 'Tags', 'Posting Time', 'Status'].map((h) => (
            <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 whitespace-nowrap">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => {
          const errs = rowErrors[i] || [];
          const hasError = errs.length > 0;
          return (
            <tr
              key={i}
              className={`border-b border-gray-50 last:border-0 ${hasError ? 'bg-red-50/40' : 'bg-offwhite'}`}
            >
              <td className="px-4 py-2.5 text-xs text-gray-400 font-mono">{row._row}</td>
              <td className="px-4 py-2.5 text-xs text-gray-700 max-w-[200px]">
                <span title={row.text}>{truncate(row.text)}</span>
              </td>
              <td className="px-4 py-2.5 text-xs text-gray-600 max-w-[150px]">
                <span title={row.image_url}>{truncate(row.image_url, 30)}</span>
              </td>
              <td className="px-4 py-2.5 text-xs text-gray-500">
                {row.tags || <span className="text-gray-300">—</span>}
              </td>
              <td className="px-4 py-2.5 text-xs text-gray-500">
                {row.posting_time || <span className="text-gray-300">draft</span>}
              </td>
              <td className="px-4 py-2.5">
                <StatusBadge errors={errs} />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

// ── Result card ───────────────────────────────────────────────────────────────
const ResultCard = ({ result, onReset }) => (
  <div className="bg-offwhite rounded-xl border border-gray-200 p-6 space-y-4 shadow-sm mt-6">
    <div className="flex items-center gap-3">
      {result.created > 0 ? (
        <FaCheckCircle className="text-green-500 text-2xl flex-shrink-0" />
      ) : (
        <FaTimesCircle className="text-red-400 text-2xl flex-shrink-0" />
      )}
      <div>
        <p className="text-base font-semibold text-gray-900">Bulk Import Complete</p>
        <p className="text-sm text-gray-500 mt-0.5">
          {result.created > 0
            ? `${result.created} post${result.created !== 1 ? 's' : ''} successfully queued for automation.`
            : 'No posts were imported.'}
          {result.skipped > 0 && ` · ${result.skipped} row${result.skipped !== 1 ? 's' : ''} skipped`}
        </p>
      </div>
    </div>

    {result.errors?.length > 0 && (
      <div className="bg-red-50 rounded-lg p-4 space-y-1.5 border border-red-100">
        <p className="text-xs font-semibold text-red-600 mb-2 uppercase tracking-wide">Validation Issues & Errors:</p>
        {result.errors.map((e, i) => (
          <p key={i} className="text-xs text-red-600 flex items-start">
            <span className="font-mono font-bold mr-2 w-12 shrink-0">Row {e.row}:</span> 
            <span>{e.message}</span>
          </p>
        ))}
      </div>
    )}

    <div className="flex items-center gap-3 pt-2">
      {result.created > 0 && (
        <Link
          to="/content"
          className="px-4 py-2 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors shadow-sm"
        >
          View in Content Library
        </Link>
      )}
      <button
        onClick={onReset}
        className="px-4 py-2 text-xs font-semibold text-gray-600 hover:text-gray-800 border border-gray-200 bg-white hover:bg-gray-50 rounded-lg transition-colors shadow-sm"
      >
        Upload Another CSV
      </button>
    </div>
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────
const BulkUpload = () => {
  const [rows, setRows] = useState([]);
  const [rowErrors, setRowErrors] = useState([]);
  const [fileName, setFileName] = useState('');
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [selectedPlatforms, setSelectedPlatforms] = useState([]);

  const fileInputRef = useRef(null);

  const togglePlatform = (platform) => {
    setSelectedPlatforms(prev => 
      prev.includes(platform) ? prev.filter(p => p !== platform) : [...prev, platform]
    );
  };

  const processFile = useCallback((file) => {
    if (!file) return;
    if (!file.name.endsWith('.csv')) {
      toast.error('Please upload a .csv file format');
      return;
    }
    setFileName(file.name);
    setResult(null);

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = parseCSV(e.target.result);
        if (!parsed.length) {
          toast.error('CSV appears to be empty or has no data rows');
          return;
        }
        setRows(parsed);
        setRowErrors(parsed.map(validateRow));
      } catch {
        toast.error('Failed to parse CSV file. Ensure it accurately matches the template format.');
      }
    };
    reader.readAsText(file);
  }, []);

  const handleFileInput = (e) => {
    processFile(e.target.files?.[0]);
    e.target.value = '';
  };

  const handleDragOver = (e) => { e.preventDefault(); setDragging(true); };
  const handleDragLeave = (e) => { e.preventDefault(); setDragging(false); };
  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    processFile(e.dataTransfer.files?.[0]);
  };

  const validRows = rows.filter((_, i) => (rowErrors[i] || []).length === 0);
  const errorCount = rows.length - validRows.length;

  const handleImport = async () => {
    if (!selectedPlatforms.length) {
      toast.error('Please select at least one platform to publish to.');
      return;
    }
    if (!validRows.length) return;
    
    setImporting(true);
    try {
      // Map strictly to backend JSON expectation
      const postsForBackend = validRows.map(row => {
        let content = row.text || '';
        if (row.tags) {
          const formattedTags = row.tags
            .split(',')
            .map(t => t.trim())
            .filter(t => t.length > 0)
            .map(t => t.startsWith('#') ? t : `#${t}`)
            .join(' ');
          
          if (formattedTags) {
            content = `${content}\n\n${formattedTags}`;
          }
        }
        const scheduledTime = row.posting_time ? (row.posting_time.includes('T') ? row.posting_time : row.posting_time.replace(' ', 'T') + ':00Z') : null;

        return {
          content,
          scheduled_time: scheduledTime,
          media_urls: row.image_url ? [row.image_url] : []
        };
      });

      const payload = {
        platforms: selectedPlatforms,
        posts: postsForBackend
      };

      const res = await bulkCreatePosts(payload);
      setResult(res);
      toast.success(`${res.created} posts successfully queued via Bulk Upload`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'CSV Data Transmission failed - Check structure');
    } finally {
      setImporting(false);
    }
  };

  const handleReset = () => {
    setRows([]);
    setRowErrors([]);
    setFileName('');
    setResult(null);
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto pb-12">
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <FaFileUpload className="text-green-500" />
              Bulk Upload via CSV
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Easily import hundreds of posts at once. Ensure your file matches our native mapping template.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <a 
              href="https://support.buffer.com/article/926-how-to-upload-posts-in-bulk-to-buffer" 
              target="_blank" 
              rel="noreferrer"
              className="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
            >
              Guide to Bulk Uploading <FaExternalLinkAlt className="text-[10px]" />
            </a>
            <button
              onClick={async () => {
                try {
                  const blob = await downloadBulkTemplate();
                  const url = window.URL.createObjectURL(new Blob([blob]));
                  const link = document.createElement('a');
                  link.href = url;
                  link.setAttribute('download', 'bulk_upload_template.csv');
                  document.body.appendChild(link);
                  link.click();
                  link.remove();
                } catch (e) {
                  toast.error("Failed to download CSV template");
                }
              }}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 rounded-lg transition-colors shadow-sm"
            >
              <FaDownload className="text-xs" />
              Download Template
            </button>
          </div>
        </div>

        {/* Global Platform Selection (Common settings) */}
        {!result && (
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Bulk Schedule Settings (Common for all uploads)</h3>
            <p className="text-xs text-gray-500 mb-4">Select the platforms that all rows within your uploaded CSV will be synced to.</p>
            <div className="flex flex-wrap items-center gap-2">
              {AVAILABLE_PLATFORMS.map(platform => {
                const isSelected = selectedPlatforms.includes(platform);
                return (
                  <button
                    key={platform}
                    onClick={() => togglePlatform(platform)}
                    className={`px-4 py-2 rounded-full text-xs font-semibold capitalize transition-all border ${
                      isSelected 
                        ? 'bg-green-500 text-white border-green-500 shadow-sm' 
                        : 'bg-offwhite text-gray-600 border-gray-200 hover:bg-gray-50 hover:border-gray-300'
                    }`}
                  >
                    {platform}
                  </button>
                )
              })}
            </div>
            {selectedPlatforms.length === 0 && (
              <p className="text-xs text-red-500 mt-3 flex items-center gap-1 font-medium">
                <FaExclamationTriangle /> You must select at least one platform before importing.
              </p>
            )}
          </div>
        )}

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileInput}
        />

        {/* Import Results Output */}
        {result && <ResultCard result={result} onReset={handleReset} />}

        {/* Drop zone */}
        {!result && rows.length === 0 && (
          <DropZone
            dragging={dragging}
            onFile={() => fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          />
        )}

        {/* Parse Preview Container */}
        {!result && rows.length > 0 && (
          <div className="mt-8 space-y-4">
            {/* File info bar */}
            <div className="flex items-center justify-between bg-white rounded-xl border border-gray-200 px-5 py-4 shadow-sm">
              <div className="flex items-center gap-3">
                <FaTable className="text-green-500 text-lg" />
                <div>
                  <p className="text-sm font-semibold text-gray-800">{fileName}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {rows.length} row{rows.length !== 1 ? 's' : ''} parsed ·{' '}
                    <span className="text-green-600 font-semibold">{validRows.length} valid</span>
                    {errorCount > 0 && (
                      <span className="text-red-500 font-semibold"> · {errorCount} error{errorCount !== 1 ? 's' : ''}</span>
                    )}
                  </p>
                </div>
              </div>
              <button
                onClick={handleReset}
                className="p-2 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors border border-transparent hover:border-red-100"
                title="Discard CSV"
              >
                <FaTimes />
              </button>
            </div>

            <PreviewTable rows={rows} rowErrors={rowErrors} />

            <div className="bg-blue-50 rounded-xl border border-blue-100 px-5 py-3 text-xs text-blue-700 leading-relaxed shadow-sm">
              <span className="font-semibold block mb-1">Row Column Verification:</span>
              <span className="font-mono bg-white px-1 py-0.5 rounded border border-blue-200">Text</span> (Required content text) ·{' '}
              <span className="font-mono bg-white px-1 py-0.5 rounded border border-blue-200">Image URL</span> (Optional direct web image link) ·{' '}
              <span className="font-mono bg-white px-1 py-0.5 rounded border border-blue-200">Tags</span> (Optional comma separated keywords) ·{' '}
              <span className="font-mono bg-white px-1 py-0.5 rounded border border-blue-200">Posting Time</span> (YYYY-MM-DD HH:MM format)
            </div>

            {/* Bottom Actions */}
            <div className="flex items-center gap-4 mt-6 p-5 bg-white rounded-xl border border-gray-200 shadow-sm">
              <button
                onClick={handleImport}
                disabled={!validRows.length || importing || selectedPlatforms.length === 0}
                className="flex items-center justify-center gap-2 px-6 py-3 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow"
              >
                <FaFileUpload className="text-sm" />
                {importing
                  ? 'Transmitting to Server...'
                  : `Schedule ${validRows.length} Mapped Post${validRows.length !== 1 ? 's' : ''}`}
              </button>
              <button
                onClick={handleReset}
                className="px-6 py-3 text-sm font-semibold text-gray-500 hover:text-gray-800 rounded-xl transition-colors bg-offwhite hover:bg-gray-100 border border-transparent hover:border-gray-200"
              >
                Cancel Process
              </button>
              
              {errorCount > 0 && (
                <p className="text-xs font-semibold text-red-500 ml-auto flex items-center gap-1.5 bg-red-50 px-3 py-1.5 rounded-lg border border-red-100">
                  <FaExclamationTriangle /> {errorCount} unresolvable row{errorCount !== 1 ? 's' : ''} will be ignored
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default BulkUpload;
