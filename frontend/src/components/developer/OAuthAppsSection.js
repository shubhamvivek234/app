import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { FaPlus, FaKey, FaTrash, FaRotate, FaCopy, FaCheck, FaGlobe, FaShieldHalved } from 'react-icons/fa6';
import { getOAuthApps, createOAuthApp, rotateOAuthAppSecret, deleteOAuthApp } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from '@/components/ui/dialog';

export default function OAuthAppsSection() {
  const [apps, setApps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // New App Form State
  const [appName, setAppName] = useState('');
  const [redirectUris, setRedirectUris] = useState('');
  const [description, setDescription] = useState('');
  const [homepageUrl, setHomepageUrl] = useState('');

  // Newly Created / Rotated Secret Modal
  const [revealData, setRevealData] = useState(null);
  const [copiedId, setCopiedId] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  useEffect(() => {
    loadApps();
  }, []);

  const loadApps = async () => {
    setLoading(true);
    try {
      const data = await getOAuthApps();
      setApps(data || []);
    } catch {
      toast.error('Failed to load OAuth applications');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!appName.trim()) {
      toast.error('Please enter an application name');
      return;
    }
    const uris = redirectUris.split('\n').map((u) => u.trim()).filter(Boolean);
    if (uris.length === 0) {
      toast.error('At least one redirect URI is required');
      return;
    }

    setSubmitting(true);
    try {
      const newApp = await createOAuthApp({
        name: appName.trim(),
        redirect_uris: uris,
        description: description.trim() || undefined,
        homepage_url: homepageUrl.trim() || undefined,
      });
      setRevealData({
        title: 'OAuth Application Created',
        clientId: newApp.client_id,
        clientSecret: newApp.client_secret,
      });
      setShowCreateModal(false);
      setAppName('');
      setRedirectUris('');
      setDescription('');
      setHomepageUrl('');
      loadApps();
      toast.success('OAuth Application created successfully');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create application');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRotateSecret = async (appId, appName) => {
    if (!window.confirm(`Are you sure you want to rotate the client secret for "${appName}"? The previous secret will stop working immediately.`)) {
      return;
    }
    try {
      const updated = await rotateOAuthAppSecret(appId);
      setRevealData({
        title: `Rotated Secret for ${appName}`,
        clientId: updated.client_id,
        clientSecret: updated.client_secret,
      });
      toast.success('Secret rotated successfully');
    } catch {
      toast.error('Failed to rotate client secret');
    }
  };

  const handleDelete = async (appId, appName) => {
    if (!window.confirm(`Revoke and delete "${appName}"? Any tokens or apps relying on this integration will be invalidated.`)) {
      return;
    }
    try {
      await deleteOAuthApp(appId);
      setApps((prev) => prev.filter((a) => a.id !== appId));
      toast.success('Application revoked');
    } catch {
      toast.error('Failed to delete application');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <FaShieldHalved className="text-violet-600 dark:text-violet-400" />
            OAuth2 Applications
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Build integrations that allow other Unravler users or external platforms to authorize access to their accounts.
          </p>
        </div>
        <Button
          type="button"
          onClick={() => setShowCreateModal(true)}
          className="bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold gap-1.5 self-start sm:self-auto rounded-xl"
        >
          <FaPlus className="text-xs" />
          Create OAuth App
        </Button>
      </div>

      {loading ? (
        <div className="h-32 flex items-center justify-center text-xs text-slate-400">Loading applications...</div>
      ) : apps.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/40 p-8 text-center space-y-3">
          <div className="w-12 h-12 mx-auto rounded-2xl bg-violet-50 dark:bg-violet-950/60 text-violet-600 dark:text-violet-400 flex items-center justify-center">
            <FaGlobe className="text-xl" />
          </div>
          <p className="text-sm font-bold text-slate-800 dark:text-slate-200">No OAuth Applications Yet</p>
          <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto">
            Create an OAuth App to obtain client credentials and allow third-party systems to connect via the standard OAuth2 authorization code flow.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {apps.map((app) => (
            <div
              key={app.id}
              className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h4 className="text-sm font-bold text-slate-900 dark:text-white">{app.name}</h4>
                  {app.description && (
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2">{app.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleRotateSecret(app.id, app.name)}
                    className="p-2 text-slate-400 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/50 rounded-lg transition-colors text-xs"
                    title="Rotate Client Secret"
                  >
                    <FaRotate />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(app.id, app.name)}
                    className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/50 rounded-lg transition-colors text-xs"
                    title="Revoke Application"
                  >
                    <FaTrash />
                  </button>
                </div>
              </div>

              <div className="space-y-2 bg-slate-50 dark:bg-slate-800/60 p-3 rounded-xl">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Client ID</span>
                  <div className="flex items-center justify-between gap-2 mt-0.5">
                    <code className="text-xs font-mono text-slate-800 dark:text-slate-200 truncate">{app.client_id}</code>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(app.client_id);
                        toast.success('Client ID copied');
                      }}
                      className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xs"
                    >
                      <FaCopy />
                    </button>
                  </div>
                </div>

                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Redirect URIs</span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {app.redirect_uris?.map((uri, idx) => (
                      <span key={idx} className="text-[11px] font-mono px-2 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300">
                        {uri}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="text-[11px] text-slate-400 flex items-center justify-between">
                <span>Created {new Date(app.created_at).toLocaleDateString()}</span>
                <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Active
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <Dialog open={showCreateModal} onOpenChange={setShowCreateModal}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create OAuth Application</DialogTitle>
            <DialogDescription>
              Register a new OAuth2 client to enable delegated authentication for external tools.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreate} className="space-y-4">
            <div>
              <label className="text-xs font-bold text-slate-700 dark:text-slate-300">Application Name</label>
              <Input
                value={appName}
                onChange={(e) => setAppName(e.target.value)}
                placeholder="e.g. Acme Marketing Bot"
                className="mt-1 text-xs"
                required
              />
            </div>

            <div>
              <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                Redirect URIs (one per line)
              </label>
              <textarea
                value={redirectUris}
                onChange={(e) => setRedirectUris(e.target.value)}
                placeholder="https://example.com/oauth/callback&#10;http://localhost:3000/callback"
                className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-2.5 text-xs font-mono text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-500"
                rows={3}
                required
              />
            </div>

            <div>
              <label className="text-xs font-bold text-slate-700 dark:text-slate-300">Description (Optional)</label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What this integration does"
                className="mt-1 text-xs"
              />
            </div>

            <div>
              <label className="text-xs font-bold text-slate-700 dark:text-slate-300">Homepage URL (Optional)</label>
              <Input
                value={homepageUrl}
                onChange={(e) => setHomepageUrl(e.target.value)}
                placeholder="https://yourwebsite.com"
                className="mt-1 text-xs"
              />
            </div>

            <DialogFooter className="mt-4">
              <Button type="button" variant="ghost" onClick={() => setShowCreateModal(false)} className="text-xs">
                Cancel
              </Button>
              <Button type="submit" disabled={submitting} className="bg-violet-600 hover:bg-violet-700 text-white text-xs font-bold">
                {submitting ? 'Creating...' : 'Register App'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Secret Reveal Modal */}
      <Dialog open={Boolean(revealData)} onOpenChange={() => setRevealData(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
              <FaKey />
              {revealData?.title}
            </DialogTitle>
            <DialogDescription>
              Please copy your client credentials now. The <strong>client secret</strong> will never be shown again!
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div>
              <span className="text-xs font-bold text-slate-700 dark:text-slate-300">Client ID</span>
              <div className="flex items-center gap-2 mt-1">
                <code className="flex-1 text-xs font-mono bg-slate-100 dark:bg-slate-800 p-2.5 rounded-xl break-all">
                  {revealData?.clientId}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard.writeText(revealData?.clientId);
                    setCopiedId(true);
                    setTimeout(() => setCopiedId(false), 2000);
                  }}
                >
                  {copiedId ? <FaCheck className="text-emerald-500" /> : <FaCopy />}
                </Button>
              </div>
            </div>

            <div>
              <span className="text-xs font-bold text-slate-700 dark:text-slate-300">Client Secret</span>
              <div className="flex items-center gap-2 mt-1">
                <code className="flex-1 text-xs font-mono bg-emerald-50 dark:bg-emerald-950/50 text-emerald-800 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 p-2.5 rounded-xl break-all">
                  {revealData?.clientSecret}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    navigator.clipboard.writeText(revealData?.clientSecret);
                    setCopiedSecret(true);
                    setTimeout(() => setCopiedSecret(false), 2000);
                  }}
                >
                  {copiedSecret ? <FaCheck className="text-emerald-500" /> : <FaCopy />}
                </Button>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              onClick={() => setRevealData(null)}
              className="bg-slate-900 text-white dark:bg-white dark:text-slate-900 font-bold text-xs"
            >
              I have saved my secret
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
