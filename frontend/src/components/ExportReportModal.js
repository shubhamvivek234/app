import React, { useState } from 'react';
import { exportBrandedReport, exportAnalyticsCSV, scheduleReport } from '@/lib/api';
import { toast } from 'sonner';
import { FaFilePdf, FaFileCsv, FaTimes, FaDownload, FaCalendarCheck, FaChartBar, FaTable } from 'react-icons/fa';

export default function ExportReportModal({ isOpen, onClose, defaultTab = 'csv' }) {
  const [agencyName, setAgencyName] = useState('Premier Social Agency');
  const [clientName, setClientName] = useState('Acme Corp');
  const [logoUrl, setLogoUrl] = useState('');
  const [notes, setNotes] = useState('Monthly social media growth & engagement executive report.');
  const [activeTab, setActiveTab] = useState(defaultTab); // 'csv' | 'pdf' | 'schedule'
  const [recipientEmail, setRecipientEmail] = useState('');
  const [frequency, setFrequency] = useState('monthly');
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  // 1-Click CSV Spreadsheet Download
  const handleExportCSV = async () => {
    setLoading(true);
    try {
      const data = await exportAnalyticsCSV();
      if (!data.rows || data.rows.length === 0) {
        toast.info('No published post data found to export.');
        return;
      }

      const headers = ['Post ID', 'Published Date', 'Platforms', 'Caption', 'Likes', 'Comments', 'Shares', 'Views', 'Total Engagement', 'Engagement Rate'];
      const csvLines = [headers.join(',')];

      data.rows.forEach((r) => {
        const cleanContent = (r.content || '').replace(/"/g, '""').replace(/\r?\n/g, ' ');
        csvLines.push([
          `"${r.post_id || ''}"`,
          `"${r.published_at || ''}"`,
          `"${r.platforms || ''}"`,
          `"${cleanContent}"`,
          r.likes ?? 0,
          r.comments ?? 0,
          r.shares ?? 0,
          r.views ?? 0,
          r.total_engagement ?? 0,
          `"${r.engagement_rate || '0.0%'}"`,
        ].join(','));
      });

      const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', `unravler_analytics_${new Date().toISOString().slice(0, 10)}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      toast.success(`Exported ${data.rows.length} posts to CSV!`);
      onClose();
    } catch {
      toast.error('Failed to export CSV report');
    } finally {
      setLoading(false);
    }
  };

  // Popup-blocker-safe Executive PDF Report Generator
  const handleExportPDF = async () => {
    setLoading(true);
    try {
      const data = await exportBrandedReport({
        agency_name: agencyName,
        client_name: clientName,
        logo_url: logoUrl || undefined,
        notes: notes || undefined,
      });

      const metrics = data.metrics || {};
      const channels = data.channels || [];
      const topPosts = data.top_posts || [];

      const reportHtml = `
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset="utf-8" />
            <title>${clientName} — Social Media Executive Report</title>
            <style>
              @page { size: A4; margin: 20mm; }
              body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 24px; color: #0f172a; max-width: 820px; margin: auto; }
              .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 20px; margin-bottom: 24px; }
              .title { font-size: 24px; font-weight: 800; color: #1e1b4b; }
              .subtitle { font-size: 13px; color: #64748b; margin-top: 4px; }
              .metrics-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
              .metric-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px; }
              .metric-label { font-size: 11px; text-transform: uppercase; font-weight: 700; color: #64748b; }
              .metric-val { font-size: 22px; font-weight: 800; color: #4338ca; margin-top: 4px; }
              .section-title { font-size: 15px; font-weight: 700; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; margin-top: 24px; margin-bottom: 12px; color: #0f172a; }
              .post-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; font-size: 13px; }
              .post-meta { display: flex; gap: 16px; margin-top: 6px; font-size: 12px; color: #64748b; }
              .badge { display: inline-block; background: #e0e7ff; color: #4338ca; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; text-transform: uppercase; }
              .channels-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
              .channel-chip { background: #f1f5f9; padding: 4px 10px; border-radius: 8px; font-size: 12px; font-weight: 600; color: #334155; }
              .footer { margin-top: 36px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #f1f5f9; padding-top: 16px; }
              @media print { body { padding: 0; } }
            </style>
          </head>
          <body>
            <div class="header">
              <div>
                <div class="title">${clientName} — Executive Social Report</div>
                <div class="subtitle">Prepared by ${agencyName} • ${data.start_date} to ${data.end_date}</div>
              </div>
              ${logoUrl ? `<img src="${logoUrl}" style="max-height: 48px; object-fit: contain;" />` : ''}
            </div>

            <div class="metrics-grid">
              <div class="metric-card">
                <div class="metric-label">Published Posts</div>
                <div class="metric-val">${metrics.total_published_posts ?? 0}</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Connected Channels</div>
                <div class="metric-val">${channels.length}</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Total Impressions</div>
                <div class="metric-val">${(metrics.estimated_impressions || 0).toLocaleString()}</div>
              </div>
              <div class="metric-card">
                <div class="metric-label">Avg Engagement Rate</div>
                <div class="metric-val">${metrics.estimated_engagement_rate || '0.0%'}</div>
              </div>
            </div>

            ${channels.length > 0 ? `
              <div class="section-title">Active Publishing Channels</div>
              <div class="channels-row">
                ${channels.map(c => `
                  <div class="channel-chip">${c.platform?.toUpperCase()}: @${c.account_name || 'connected'}</div>
                `).join('')}
              </div>
            ` : ''}

            ${notes ? `
              <div style="background: #f1f5f9; padding: 12px 16px; border-radius: 10px; font-size: 13px; color: #334155; margin-bottom: 20px;">
                <strong>Executive Summary:</strong> ${notes}
              </div>
            ` : ''}

            <div class="section-title">Top Performing Content</div>
            ${topPosts.length > 0 ? topPosts.map(p => `
              <div class="post-card">
                <div><span class="badge">${(p.platforms || []).join(', ') || 'Social'}</span> <span style="margin-left: 8px;">${p.content || '(no caption)'}</span></div>
                <div class="post-meta">
                  <span>❤️ ${p.metrics?.likes ?? 0} Likes</span>
                  <span>💬 ${p.metrics?.comments ?? 0} Comments</span>
                  <span>🔄 ${p.metrics?.shares ?? 0} Shares</span>
                  <span>👁️ ${p.metrics?.views ?? 0} Views</span>
                </div>
              </div>
            `).join('') : '<p style="color: #94a3b8; font-size: 13px;">No published posts found in the reporting window.</p>'}

            <div class="footer">
              Generated via Unravler Social Intelligence • ${new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}
            </div>
          </body>
        </html>
      `;

      // Use an invisible iframe to print safely without popup blocker issues
      const iframe = document.createElement('iframe');
      iframe.style.position = 'fixed';
      iframe.style.right = '0';
      iframe.style.bottom = '0';
      iframe.style.width = '0';
      iframe.style.height = '0';
      iframe.style.border = '0';
      document.body.appendChild(iframe);

      const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
      iframeDoc.open();
      iframeDoc.write(reportHtml);
      iframeDoc.close();

      setTimeout(() => {
        iframe.contentWindow.focus();
        iframe.contentWindow.print();
        setTimeout(() => {
          if (document.body.contains(iframe)) {
            document.body.removeChild(iframe);
          }
        }, 2000);
      }, 300);

      toast.success('Executive PDF ready to print / save!');
      onClose();
    } catch {
      toast.error('Failed to generate report');
    } finally {
      setLoading(false);
    }
  };

  const handleSchedule = async (e) => {
    e.preventDefault();
    if (!recipientEmail) {
      toast.error('Please enter a recipient email');
      return;
    }
    setLoading(true);
    try {
      await scheduleReport({
        recipient_email: recipientEmail,
        client_name: clientName,
        frequency,
        include_top_posts: true,
      });
      toast.success(`Automated ${frequency} report scheduled for ${recipientEmail}!`);
      onClose();
    } catch {
      toast.error('Failed to save report schedule');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-gray-100 dark:border-gray-800 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
              <FaChartBar className="text-sm" />
            </div>
            <div>
              <h3 className="text-base font-bold text-gray-900 dark:text-white">Export &amp; Share Reports</h3>
              <p className="text-[11px] text-gray-500 dark:text-gray-400">Export raw CSV tables or branded executive PDF sheets</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
            <FaTimes />
          </button>
        </div>

        {/* Tab switch */}
        <div className="flex border-b border-gray-100 dark:border-gray-800 mb-5">
          <button
            onClick={() => setActiveTab('csv')}
            className={`pb-2.5 px-3 text-xs font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'csv'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            <FaFileCsv className="text-xs" /> Export CSV Table
          </button>
          <button
            onClick={() => setActiveTab('pdf')}
            className={`pb-2.5 px-3 text-xs font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'pdf'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            <FaFilePdf className="text-xs" /> Branded PDF Report
          </button>
          <button
            onClick={() => setActiveTab('schedule')}
            className={`pb-2.5 px-3 text-xs font-bold border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'schedule'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            <FaCalendarCheck className="text-xs" /> Automated Email
          </button>
        </div>

        {activeTab === 'csv' && (
          <div className="space-y-4">
            <div className="p-4 rounded-2xl bg-gray-50 dark:bg-gray-800/60 border border-gray-200/80 dark:border-gray-800 text-xs">
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
                  <FaTable className="text-base" />
                </div>
                <div>
                  <h4 className="font-bold text-gray-900 dark:text-white">Raw Post-Level Spreadsheet</h4>
                  <p className="text-gray-500 dark:text-gray-400 mt-1 leading-relaxed text-[11px]">
                    Download a comprehensive CSV file with post ID, publication date, connected social networks, caption text, likes, comments, shares, views, and engagement rates for spreadsheet analysis in Excel or Google Sheets.
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleExportCSV}
                disabled={loading}
                className="px-5 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-xs transition-all active:scale-95 flex items-center gap-1.5 disabled:opacity-50"
              >
                <FaDownload className="text-xs" /> {loading ? 'Preparing CSV...' : 'Download CSV Spreadsheet'}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'pdf' && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Agency Name</label>
                <input
                  type="text"
                  value={agencyName}
                  onChange={(e) => setAgencyName(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Client Name</label>
                <input
                  type="text"
                  value={clientName}
                  onChange={(e) => setClientName(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Agency Logo URL (Optional)</label>
              <input
                type="url"
                placeholder="https://.../logo.png"
                value={logoUrl}
                onChange={(e) => setLogoUrl(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Executive Summary Notes</label>
              <textarea
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl"
              >
                Cancel
              </button>
              <button
                onClick={handleExportPDF}
                disabled={loading}
                className="px-5 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-xs transition-all active:scale-95 flex items-center gap-1.5 disabled:opacity-50"
              >
                <FaDownload className="text-xs" /> {loading ? 'Generating...' : 'Print / Save PDF'}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'schedule' && (
          <form onSubmit={handleSchedule} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Client Recipient Email *</label>
              <input
                type="email"
                required
                placeholder="client@company.com"
                value={recipientEmail}
                onChange={(e) => setRecipientEmail(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">Frequency</label>
              <select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
                className="w-full px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
              >
                <option value="weekly">Weekly (Every Monday morning)</option>
                <option value="monthly">Monthly (1st of every month)</option>
              </select>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-5 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-xs transition-all active:scale-95 flex items-center gap-1.5 disabled:opacity-50"
              >
                <FaCalendarCheck /> {loading ? 'Saving...' : 'Set Automated Schedule'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
