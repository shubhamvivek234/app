import React, { useState } from 'react';
import { exportBrandedReport, scheduleReport } from '@/lib/api';
import { toast } from 'sonner';
import { FaFilePdf, FaEnvelope, FaTimes, FaDownload, FaCalendarCheck } from 'react-icons/fa';

export default function ExportReportModal({ isOpen, onClose }) {
  const [agencyName, setAgencyName] = useState('Premier Social Agency');
  const [clientName, setClientName] = useState('Acme Corp');
  const [logoUrl, setLogoUrl] = useState('');
  const [notes, setNotes] = useState('Monthly social media growth & engagement executive report.');
  const [activeTab, setActiveTab] = useState('export'); // 'export' | 'schedule'
  const [recipientEmail, setRecipientEmail] = useState('');
  const [frequency, setFrequency] = useState('monthly');
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleExportPDF = async () => {
    setLoading(true);
    try {
      const data = await exportBrandedReport({
        agency_name: agencyName,
        client_name: clientName,
        logo_url: logoUrl || undefined,
        notes: notes || undefined,
      });

      // Open a printable summary window
      const printWindow = window.open('', '_blank');
      if (printWindow) {
        printWindow.document.write(`
          <!DOCTYPE html>
          <html>
            <head>
              <title>${clientName} — Social Media Executive Report</title>
              <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 40px; color: #0f172a; max-width: 800px; margin: auto; }
                .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 20px; margin-bottom: 30px; }
                .title { font-size: 24px; font-weight: 800; color: #1e1b4b; }
                .subtitle { font-size: 13px; color: #64748b; margin-top: 4px; }
                .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 30px; }
                .metric-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; }
                .metric-label { font-size: 11px; text-transform: uppercase; font-weight: 700; color: #64748b; }
                .metric-val { font-size: 28px; font-weight: 800; color: #4338ca; margin-top: 4px; }
                .section-title { font-size: 16px; font-weight: 700; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; margin-bottom: 12px; }
                .post-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; margin-bottom: 10px; font-size: 13px; }
                .footer { margin-top: 40px; font-size: 11px; color: #94a3b8; text-align: center; border-top: 1px solid #f1f5f9; padding-top: 16px; }
                @media print { body { padding: 0; } }
              </style>
            </head>
            <body>
              <div class="header">
                <div>
                  <div class="title">${clientName} — Executive Performance Report</div>
                  <div class="subtitle">Prepared by ${agencyName} • ${data.start_date} to ${data.end_date}</div>
                </div>
                ${logoUrl ? `<img src="${logoUrl}" style="height: 48px; object-fit: contain;" />` : ''}
              </div>

              <div class="metrics-grid">
                <div class="metric-card">
                  <div class="metric-label">Published Posts</div>
                  <div class="metric-val">${data.metrics.total_published_posts}</div>
                </div>
                <div class="metric-card">
                  <div class="metric-label">Estimated Reach</div>
                  <div class="metric-val">${data.metrics.estimated_impressions.toLocaleString()}</div>
                </div>
                <div class="metric-card">
                  <div class="metric-label">Avg Engagement</div>
                  <div class="metric-val">${data.metrics.estimated_engagement_rate}</div>
                </div>
              </div>

              ${notes ? `<div style="background: #f1f5f9; padding: 12px 16px; border-radius: 8px; font-size: 13px; color: #334155; margin-bottom: 24px;"><strong>Executive Summary:</strong> ${notes}</div>` : ''}

              <div class="section-title">Top Performing Content</div>
              ${data.top_posts.map(p => `
                <div class="post-card">
                  <strong>${p.platforms.join(', ').toUpperCase()}</strong>: ${p.content}
                </div>
              `).join('')}

              <div class="footer">
                Report generated via Unravler Platform on ${new Date().toLocaleDateString()}
              </div>
              <script>window.print();</script>
            </body>
          </html>
        `);
        printWindow.document.close();
      }
      toast.success('Executive PDF report generated!');
      onClose();
    } catch (err) {
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
    } catch (err) {
      toast.error('Failed to save report schedule');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-3xl max-w-lg w-full p-6 shadow-xl border border-gray-100 dark:border-gray-800 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-rose-50 dark:bg-rose-950/50 text-rose-600 dark:text-rose-400 flex items-center justify-center">
              <FaFilePdf className="text-sm" />
            </div>
            <h3 className="text-base font-bold text-gray-900 dark:text-white">Executive PDF &amp; Email Reports</h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-lg">
            <FaTimes />
          </button>
        </div>

        {/* Tab switch */}
        <div className="flex border-b border-gray-100 dark:border-gray-800 mb-4">
          <button
            onClick={() => setActiveTab('export')}
            className={`pb-2 px-3 text-xs font-bold border-b-2 transition-colors ${
              activeTab === 'export'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            Export Branded PDF
          </button>
          <button
            onClick={() => setActiveTab('schedule')}
            className={`pb-2 px-3 text-xs font-bold border-b-2 transition-colors ${
              activeTab === 'schedule'
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            Automated Email Schedule
          </button>
        </div>

        {activeTab === 'export' ? (
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
                <FaDownload className="text-xs" /> {loading ? 'Generating...' : 'Print / Download PDF'}
              </button>
            </div>
          </div>
        ) : (
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
                className="w-full px-3 py-2 text-xs border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
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
