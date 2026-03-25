import React from 'react';
import { Link } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import {
  FaArrowLeft, FaCheckCircle, FaExclamationTriangle, FaDownload,
  FaTable, FaShieldAlt, FaCalendarAlt,
} from 'react-icons/fa';

const COLUMNS = [
  {
    name: 'content',
    required: 'Conditional',
    default: '—',
    format: 'Plain text. UTF-8. At least one of content, image_urls, or video_url must be present.',
    errors: 'All three media fields empty',
    warnings: 'Exceeds platform char limit',
  },
  {
    name: 'platforms',
    required: 'Yes',
    default: '—',
    format: 'Comma-separated. Case-insensitive. instagram · youtube · twitter · tiktok · linkedin · facebook · bluesky',
    errors: 'Missing or empty · Unrecognised platform name',
    warnings: '—',
  },
  {
    name: 'accounts',
    required: 'No',
    default: 'All workspace accounts',
    format: 'Exact display name as shown on Accounts page. Comma-separated. Use "all" to target every account.',
    errors: 'Account name not found in workspace',
    warnings: 'More than 1 account per platform in same row',
  },
  {
    name: 'scheduled_time',
    required: 'No',
    default: 'Auto-queue',
    format: 'DD/Mon/YYYY HH:mm (e.g. 23/Apr/2026 10:00) or DD/MM/YYYY HH:mm (e.g. 23/04/2026 10:00). Excel-auto-converted dates accepted.',
    errors: 'Date is in the past · Unrecognisable format · More than 365 days ahead',
    warnings: 'Within 2 min of now',
  },
  {
    name: 'image_urls',
    required: 'No',
    default: '—',
    format: 'Direct URLs ending in .jpg .png .webp .gif. Separate multiple with ||. Max 10 URLs per row. Google Drive & Dropbox accepted.',
    errors: 'Invalid URL format · image_urls + video_url both present · SSRF risk (private IP)',
    warnings: "More than 10 URLs · URL doesn't end in image extension",
  },
  {
    name: 'video_url',
    required: 'No',
    default: '—',
    format: 'Single direct URL. Google Drive (<100 MB) and Dropbox direct links accepted. Cannot coexist with image_urls.',
    errors: 'Invalid URL · Both video_url + image_urls present',
    warnings: 'Google Drive video over 100 MB',
  },
  {
    name: 'title',
    required: 'No',
    default: '—',
    format: 'Plain text. Applies to YouTube (100 chars) and LinkedIn articles (150 chars) only.',
    errors: 'YouTube title over 100 chars · LinkedIn title over 150 chars',
    warnings: 'YouTube: over 70 chars cut off in search results',
  },
  {
    name: 'tags',
    required: 'No',
    default: '—',
    format: 'Comma-separated. Must be existing tags in workspace. Case-sensitive.',
    errors: '—',
    warnings: 'Tag not found in workspace — silently ignored',
  },
  {
    name: 'post_type',
    required: 'No',
    default: 'Auto-detected',
    format: 'text · image · video · carousel · reel · story',
    errors: 'reel without instagram · story without instagram or facebook · video without video_url',
    warnings: '—',
  },
];

const CHAR_LIMITS = [
  { platform: 'Instagram', limit: '2,200', truncated: '125 chars → "… more"', titleLimit: '—', titleVisible: '—' },
  { platform: 'Facebook', limit: '63,206', truncated: '477 chars → "See More"', titleLimit: '—', titleVisible: '—' },
  { platform: 'X (free)', limit: '280', truncated: 'Hard cut — post fails', titleLimit: '—', titleVisible: '—' },
  { platform: 'X (premium)', limit: '25,000', truncated: '—', titleLimit: '—', titleVisible: '—' },
  { platform: 'TikTok', limit: '4,000', truncated: '150 chars → "see more"', titleLimit: '—', titleVisible: '—' },
  { platform: 'LinkedIn', limit: '3,000', truncated: '140 chars → "See more"', titleLimit: '150 chars', titleVisible: 'Full title shown' },
  { platform: 'YouTube', limit: '5,000 (description)', truncated: '157 chars in search', titleLimit: '100 chars', titleVisible: '70 chars visible' },
];

const VALIDATION_LAYERS = [
  { layer: '1 · File', checks: 'File is .csv · encoding is UTF-8 or UTF-16 · size <10 MB · row count within plan limit · required column headers present', when: 'On file upload' },
  { layer: '2 · Structure', checks: 'At least one of content / image_urls / video_url present · image_urls and video_url not both present · platforms not empty · no completely empty rows', when: 'Per row, no DB' },
  { layer: '3 · Platform', checks: 'Platform names valid · post_type compatible with platforms · Instagram requires image or video · content length within each platform\'s limit', when: 'Per row, no DB' },
  { layer: '4 · Content', checks: 'Title within limit for YouTube / LinkedIn · tags format', when: 'Per row, no DB' },
  { layer: '5 · DateTime', checks: 'Date in DD/Mon/YYYY HH:mm (e.g. 23/Apr/2026 10:00) or DD/MM/YYYY HH:mm (e.g. 23/04/2026 10:00) · not in the past · not >365 days ahead', when: 'Per row, no DB' },
  { layer: '6 · URLs', checks: 'Valid URL format · ends in image extension (or Google Drive / Dropbox pattern) · max 10 images · no localhost / 169.254.x.x / private IP (SSRF)', when: 'Per row, no network' },
  { layer: '7 · Schedule', checks: 'Account names exist in workspace · daily platform posting limit not exceeded for any day · scheduling conflict within 30-min window for same account', when: 'Per row, DB call' },
];

const Section = ({ icon: Icon, title, children }) => (
  <div className="mb-10">
    <div className="flex items-center gap-2.5 mb-4">
      <div className="w-8 h-8 rounded-lg bg-green-100 flex items-center justify-center">
        <Icon className="text-green-600 text-sm" />
      </div>
      <h2 className="text-base font-bold text-gray-900">{title}</h2>
    </div>
    {children}
  </div>
);

const BulkUploadGuide = () => (
  <DashboardLayout>
    <div className="max-w-4xl mx-auto pb-16">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Link
          to="/bulk-upload"
          className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
        >
          <FaArrowLeft />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Bulk Upload Guide</h1>
          <p className="text-sm text-gray-500 mt-1">
            Everything you need to know to import posts via CSV into SocialEntangler.
          </p>
        </div>
      </div>

      {/* Quick start */}
      <div className="bg-green-50 border border-green-200 rounded-2xl p-6 mb-10">
        <h2 className="text-sm font-bold text-green-800 mb-3">Quick Start</h2>
        <ol className="space-y-2 text-sm text-green-700">
          {[
            'Go to Bulk Upload → Bulk Upload via CSV',
            'Click "Download CSV Template" and open the file in Excel or Google Sheets',
            'Fill in your posts row by row — only content and platforms are required',
            'Save as .csv (UTF-8) and upload it in the modal',
            'Review the validation results and click "Schedule Posts"',
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="w-5 h-5 rounded-full bg-green-600 text-white text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </span>
              {step}
            </li>
          ))}
        </ol>
      </div>

      {/* CSV Column Reference */}
      <Section icon={FaTable} title="CSV Column Reference">
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-xs min-w-[700px]">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {['Column', 'Required', 'Default if blank', 'Format & accepted values', 'Errors (blocks import)', 'Warnings'].map((h) => (
                  <th key={h} className="px-3 py-3 text-left font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COLUMNS.map((col, i) => (
                <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 transition-colors">
                  <td className="px-3 py-3 font-mono font-bold text-green-700">{col.name}</td>
                  <td className={`px-3 py-3 font-semibold ${col.required === 'Yes' ? 'text-red-500' : col.required === 'Conditional' ? 'text-amber-500' : 'text-gray-400'}`}>
                    {col.required}
                  </td>
                  <td className="px-3 py-3 text-gray-500 italic">{col.default}</td>
                  <td className="px-3 py-3 text-gray-600 max-w-[200px] leading-relaxed">{col.format}</td>
                  <td className="px-3 py-3 text-red-500 leading-relaxed">{col.errors}</td>
                  <td className="px-3 py-3 text-amber-600 leading-relaxed">{col.warnings}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* Character limits */}
      <Section icon={FaShieldAlt} title="Content Character Limits by Platform">
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-xs min-w-[500px]">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {['Platform', 'Content hard limit', 'Truncated in feed at', 'Title hard limit', 'Title visible in search'].map((h) => (
                  <th key={h} className="px-3 py-3 text-left font-semibold text-gray-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CHAR_LIMITS.map((row, i) => (
                <tr key={i} className="border-b border-gray-50 last:border-0">
                  <td className="px-3 py-3 font-semibold text-gray-800">{row.platform}</td>
                  <td className="px-3 py-3 text-gray-600">{row.limit}</td>
                  <td className="px-3 py-3 text-gray-500">{row.truncated}</td>
                  <td className="px-3 py-3 text-gray-500">{row.titleLimit}</td>
                  <td className="px-3 py-3 text-gray-500">{row.titleVisible}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* Validation layers */}
      <Section icon={FaShieldAlt} title="Validation Layers — Order of Execution">
        <div className="space-y-3">
          {VALIDATION_LAYERS.map((v, i) => (
            <div key={i} className="flex gap-4 bg-white rounded-xl border border-gray-200 px-5 py-4">
              <div className="w-28 flex-shrink-0">
                <span className="text-xs font-bold text-gray-800">{v.layer}</span>
              </div>
              <div className="flex-1 text-xs text-gray-600 leading-relaxed">{v.checks}</div>
              <div className="w-32 flex-shrink-0 text-right">
                <span className="text-[10px] font-medium text-gray-400 bg-gray-50 px-2 py-1 rounded-lg border border-gray-100">
                  {v.when}
                </span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-4 bg-blue-50 rounded-xl px-4 py-3 border border-blue-100">
          <strong className="text-blue-700">Note:</strong> Rows with errors (layers 1–7) are shown in the Review Content screen but are <strong>skipped</strong> during scheduling.
          Rows with only warnings are imported normally.
        </p>
      </Section>

      {/* DateTime formats */}
      <Section icon={FaCalendarAlt} title="Accepted Date/Time Formats">
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-3">
            <p className="text-xs font-mono font-bold text-green-700 mb-2">DD/Mon/YYYY HH:mm</p>
            <div className="flex flex-col gap-1">
              {['23/Apr/2026 10:00', '26/Sep/2026 14:30'].map((ex) => (
                <span key={ex} className="text-[11px] font-mono text-green-800">{ex}</span>
              ))}
            </div>
          </div>
          <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-3">
            <p className="text-xs font-mono font-bold text-green-700 mb-2">DD/MM/YYYY HH:mm</p>
            <div className="flex flex-col gap-1">
              {['23/04/2026 10:00', '26/09/2026 14:30'].map((ex) => (
                <span key={ex} className="text-[11px] font-mono text-green-800">{ex}</span>
              ))}
            </div>
            <p className="text-[10px] text-green-600 mt-1.5">Excel auto-converted format</p>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-3 bg-blue-50 rounded-xl px-4 py-3 border border-blue-100">
          <strong className="text-blue-700">Month abbreviations (DD/Mon format):</strong> Jan · Feb · Mar · Apr · May · Jun · Jul · Aug · Sep · Oct · Nov · Dec (case-insensitive)
        </p>
      </Section>

      {/* Pro tips */}
      <div className="bg-gray-50 rounded-2xl border border-gray-200 p-6">
        <h2 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
          <FaCheckCircle className="text-green-500" /> Pro Tips
        </h2>
        <ul className="space-y-2 text-xs text-gray-600">
          {[
            'Use Google Sheets to build your CSV — it handles commas and special characters automatically',
            'Wrap any field containing commas or quotes in double-quotes: "Hello, world!"',
            'Leave scheduled_time blank to auto-queue posts to your next available timeslot',
            'Use || to separate multiple image URLs in a single row: https://img1.jpg||https://img2.jpg',
            'Test with a small CSV (5 rows) first to verify your format before uploading hundreds of rows',
            'Rows with errors are skipped — rows with only warnings are imported normally',
          ].map((tip, i) => (
            <li key={i} className="flex items-start gap-2">
              <FaCheckCircle className="text-green-400 text-[10px] mt-0.5 flex-shrink-0" />
              {tip}
            </li>
          ))}
        </ul>
      </div>

      {/* CTA */}
      <div className="mt-8 flex items-center gap-4">
        <Link
          to="/bulk-upload"
          onClick={() => {}}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-bold bg-green-500 hover:bg-green-600 text-white rounded-xl transition-colors shadow"
        >
          Start Bulk Upload
        </Link>
        <a
          href="#"
          onClick={(e) => e.preventDefault()}
          className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 rounded-xl transition-colors shadow-sm"
        >
          <FaDownload className="text-xs" /> Download Template
        </a>
      </div>
    </div>
  </DashboardLayout>
);

export default BulkUploadGuide;
