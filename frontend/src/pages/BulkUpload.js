import React, { useState, useRef, useCallback } from 'react';
import { Link } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { bulkCreatePosts, downloadBulkTemplate } from '@/lib/api';
import { toast } from 'sonner';
import {
  FaFileUpload, FaDownload, FaCheckCircle, FaExclamationTriangle,
  FaTimesCircle, FaTimes, FaCloudUploadAlt, FaTable,
} from 'react-icons/fa';

const PLATFORM_VALID = new Set([
  'instagram', 'twitter', 'facebook', 'linkedin', 'youtube',
  'tiktok', 'pinterest', 'threads', 'bluesky', 'reddit', 'snapchat',
]);

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
  if (!row.content) errors.push('content required');
  if (!row.platforms) {
    errors.push('platforms required');
  } else {
    const platforms = row.platforms.split('|').map((p) => p.trim().toLowerCase());
    const invalid = platforms.filter((p) => p && !PLATFORM_VALID.has(p));
    if (invalid.length) errors.push(`unknown platform: ${invalid.join(', ')}`);
  }
  if (row.scheduled_time) {
    const ts = row.scheduled_time.trim();
    if (ts && !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(ts) && !/^\d{4}-\d{2}-\d{2}T/.test(ts)) {
      errors.push('scheduled_time must be YYYY-MM-DD HH:MM');
    }
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
    className={`border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center gap-4 transition-colors ${
      dragging ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-offwhite hover:border-gray-300'
    }`}
  >
    <FaCloudUploadAlt className={`text-5xl ${dragging ? 'text-green-400' : 'text-gray-300'}`} />
    <div className="text-center">
      <p className="text-sm font-semibold text-gray-600">
        {dragging ? 'Drop your CSV here' : 'Drag & drop a CSV file here'}
      </p>
      <p className="text-xs text-gray-400 mt-0.5">Only .csv files accepted</p>
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
  <div className="overflow-x-auto rounded-xl border border-gray-200">
    <table className="w-full text-sm min-w-[700px]">
      <thead>
        <tr className="bg-offwhite border-b border-gray-200">
          {['#', 'Content', 'Platforms', 'Scheduled Time', 'Post Type', 'Status'].map((h) => (
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
                <span title={row.content}>{truncate(row.content)}</span>
              </td>
              <td className="px-4 py-2.5 text-xs text-gray-600">
                {row.platforms
                  ? row.platforms.split('|').map((p) => p.trim()).join(', ')
                  : <span className="text-red-400 italic">missing</span>}
              </td>
              <td className="px-4 py-2.5 text-xs text-gray-500">
                {row.scheduled_time || <span className="text-gray-300">draft</span>}
              </td>
              <td className="px-4 py-2.5 text-xs text-gray-500">
                {row.post_type || 'text'}
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
  <div className="bg-offwhite rounded-xl border border-gray-200 p-6 space-y-4">
    <div className="flex items-center gap-3">
      {result.created > 0 ? (
        <FaCheckCircle className="text-green-500 text-2xl flex-shrink-0" />
      ) : (
        <FaTimesCircle className="text-red-400 text-2xl flex-shrink-0" />
      )}
      <div>
        <p className="text-base font-semibold text-gray-900">Import complete</p>
        <p className="text-sm text-gray-500 mt-0.5">
          {result.created > 0
            ? `${result.created} post${result.created !== 1 ? 's' : ''} created successfully`
            : 'No posts were created'}
          {result.skipped > 0 && ` · ${result.skipped} row${result.skipped !== 1 ? 's' : ''} skipped`}
        </p>
      </div>
    </div>

    {result.errors?.length > 0 && (
      <div className="bg-red-50 rounded-lg p-3 space-y-1">
        <p className="text-xs font-semibold text-red-600 mb-2">Row errors:</p>
        {result.errors.map((e, i) => (
          <p key={i} className="text-xs text-red-600">
            <span className="font-mono font-semibold">Row {e.row}:</span> {e.message}
          </p>
        ))}
      </div>
    )}

    <div className="flex items-center gap-3 pt-1">
      {result.created > 0 && (
        <Link
          to="/content"
          className="px-4 py-2 text-xs font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors"
        >
          View in Content Library
        </Link>
      )}
      <button
        onClick={onReset}
        className="px-4 py-2 text-xs font-semibold text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg transition-colors"
      >
        Upload Another File
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

  const fileInputRef = useRef(null);

  const processFile = useCallback((file) => {
    if (!file) return;
    if (!file.name.endsWith('.csv')) {
      toast.error('Please upload a .csv file');
      return;
    }
    setFileName(file.name);
    setResult(null);

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = parseCSV(e.target.result);
        if (!parsed.length) {
          toast.error('CSV is empty or has no data rows');
          return;
        }
        setRows(parsed);
        setRowErrors(parsed.map(validateRow));
      } catch {
        toast.error('Failed to parse CSV — check the file format');
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
    if (!validRows.length) return;
    setImporting(true);
    try {
      // Strip internal _row key before sending
      const payload = validRows.map(({ _row, ...rest }) => rest);
      const res = await bulkCreatePosts(payload);
      setResult(res);
      toast.success(`${res.created} post${res.created !== 1 ? 's' : ''} imported`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Import failed');
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
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <FaFileUpload className="text-green-500" />
              Bulk Upload
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Import multiple posts at once from a CSV file.
            </p>
          </div>
          <button
            onClick={downloadBulkTemplate}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold border border-gray-200 text-gray-600 hover:bg-gray-50 rounded-lg transition-colors"
          >
            <FaDownload className="text-xs" />
            Download Template
          </button>
        </div>

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileInput}
        />

        {/* Result card */}
        {result && (
          <div className="mb-6">
            <ResultCard result={result} onReset={handleReset} />
          </div>
        )}

        {/* Drop zone — shown when no file loaded or after reset */}
        {!result && rows.length === 0 && (
          <DropZone
            dragging={dragging}
            onFile={() => fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          />
        )}

        {/* Preview — shown when rows are parsed */}
        {!result && rows.length > 0 && (
          <div className="space-y-4">
            {/* File info bar */}
            <div className="flex items-center justify-between bg-offwhite rounded-xl border border-gray-200 px-4 py-3">
              <div className="flex items-center gap-3">
                <FaTable className="text-green-500 text-sm" />
                <div>
                  <p className="text-sm font-semibold text-gray-800">{fileName}</p>
                  <p className="text-xs text-gray-400">
                    {rows.length} row{rows.length !== 1 ? 's' : ''} parsed ·{' '}
                    <span className="text-green-600 font-medium">{validRows.length} valid</span>
                    {errorCount > 0 && (
                      <span className="text-red-500 font-medium"> · {errorCount} error{errorCount !== 1 ? 's' : ''}</span>
                    )}
                  </p>
                </div>
              </div>
              <button
                onClick={handleReset}
                className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition-colors"
                title="Clear"
              >
                <FaTimes />
              </button>
            </div>

            {/* Preview table */}
            <PreviewTable rows={rows} rowErrors={rowErrors} />

            {/* CSV column guide */}
            <div className="bg-blue-50 rounded-xl border border-blue-100 px-4 py-3 text-xs text-blue-700">
              <span className="font-semibold">Column guide:</span>{' '}
              <span className="font-mono">content</span> (required) ·{' '}
              <span className="font-mono">platforms</span> (pipe-separated: instagram|twitter) ·{' '}
              <span className="font-mono">scheduled_time</span> (YYYY-MM-DD HH:MM UTC, blank = draft) ·{' '}
              <span className="font-mono">post_type</span> (text/image/video) ·{' '}
              <span className="font-mono">media_urls</span> (pipe-separated) ·{' '}
              <span className="font-mono">instagram_first_comment</span>
            </div>

            {/* Import + clear buttons */}
            <div className="flex items-center gap-3">
              <button
                onClick={handleImport}
                disabled={!validRows.length || importing}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold bg-green-500 hover:bg-green-600 text-white rounded-lg transition-colors disabled:opacity-50"
              >
                <FaFileUpload className="text-xs" />
                {importing
                  ? 'Importing…'
                  : `Import ${validRows.length} Valid Post${validRows.length !== 1 ? 's' : ''}`}
              </button>
              <button
                onClick={handleReset}
                className="px-4 py-2.5 text-sm font-medium text-gray-500 hover:text-gray-700 rounded-lg transition-colors"
              >
                Clear
              </button>
              {errorCount > 0 && (
                <p className="text-xs text-red-500 ml-auto">
                  {errorCount} row{errorCount !== 1 ? 's' : ''} with errors will be skipped
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
