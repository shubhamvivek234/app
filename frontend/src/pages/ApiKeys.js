import React, { useState, useEffect } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getApiKeys, createApiKey, deleteApiKey } from '@/lib/api';
import { toast } from 'sonner';
import { FaKey, FaTrash, FaCopy } from 'react-icons/fa';

const ApiKeys = () => {
    const [keys, setKeys] = useState([]);
    const [loading, setLoading] = useState(true);
    const [newKeyName, setNewKeyName] = useState('');
    const [generating, setGenerating] = useState(false);
    const [generatedKey, setGeneratedKey] = useState(null);

    useEffect(() => {
        fetchKeys();
    }, []);

    const fetchKeys = async () => {
        try {
            const data = await getApiKeys();
            setKeys(data);
        } catch (error) {
            toast.error('Failed to fetch API keys');
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        if (!newKeyName.trim()) return;

        setGenerating(true);
        try {
            const data = await createApiKey(newKeyName);
            setGeneratedKey(data.api_key);
            setNewKeyName('');
            fetchKeys();
            toast.success('API Key generated successfully');
        } catch (error) {
            toast.error('Failed to generate API key');
        } finally {
            setGenerating(false);
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm('Are you sure you want to revoke this API key? External agents using it will lose access.')) return;

        try {
            await deleteApiKey(id);
            setKeys(keys.filter(k => k.id !== id));
            toast.success('API Key revoked');
        } catch (error) {
            toast.error('Failed to revoke API key');
        }
    };

    const copyToClipboard = (text) => {
        navigator.clipboard.writeText(text);
        toast.success('Copied to clipboard');
    };

    return (
        <DashboardLayout>
            <div className="max-w-4xl space-y-8">
                <div>
                    <h1 className="text-3xl font-semibold tracking-tight text-slate-900">API Keys</h1>
                    <p className="text-base text-slate-600 mt-1">Manage your keys for external AI agents and integrations</p>
                </div>

                {generatedKey && (
                    <div className="bg-green-50 border border-green-200 rounded-lg p-6 space-y-4">
                        <h2 className="text-lg font-semibold text-green-900">New API Key Generated</h2>
                        <p className="text-sm text-green-700">
                            Copy this key and save it somewhere safe. For security reasons, <strong>it will never be shown again</strong>.
                        </p>
                        <div className="flex gap-2">
                            <code className="flex-1 bg-white border border-green-200 p-2 rounded text-sm font-mono truncate lg:whitespace-normal">
                                {generatedKey}
                            </code>
                            <Button onClick={() => copyToClipboard(generatedKey)} variant="outline" size="sm" className="bg-white">
                                <FaCopy className="mr-2" /> Copy
                            </Button>
                        </div>
                        <Button onClick={() => setGeneratedKey(null)} variant="link" className="text-green-700 p-0 h-auto font-medium">
                            I've saved the key
                        </Button>
                    </div>
                )}

                <div className="bg-white rounded-lg border border-border p-6 shadow-sm">
                    <h2 className="text-xl font-semibold text-slate-900 mb-6 font-primary">Generate New Key</h2>
                    <form onSubmit={handleCreate} className="flex gap-4 items-end">
                        <div className="flex-1 space-y-2">
                            <Label htmlFor="keyName">Key Name (e.g., OpenClaw Agent)</Label>
                            <Input
                                id="keyName"
                                placeholder="Give your key a name..."
                                value={newKeyName}
                                onChange={(e) => setNewKeyName(e.target.value)}
                            />
                        </div>
                        <Button type="submit" disabled={generating || !newKeyName.trim()}>
                            {generating ? 'Generating...' : 'Generate Key'}
                        </Button>
                    </form>
                </div>

                <div className="bg-white rounded-lg border border-border overflow-hidden shadow-sm">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-slate-50 border-b border-border">
                                <th className="px-6 py-4 text-sm font-semibold text-slate-900">Name</th>
                                <th className="px-6 py-4 text-sm font-semibold text-slate-900">Created</th>
                                <th className="px-6 py-4 text-sm font-semibold text-slate-900">Last Used</th>
                                <th className="px-6 py-4 text-sm font-semibold text-slate-900 text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {loading ? (
                                <tr><td colSpan="4" className="px-6 py-8 text-center text-slate-500">Loading keys...</td></tr>
                            ) : keys.length === 0 ? (
                                <tr><td colSpan="4" className="px-6 py-8 text-center text-slate-500">No API keys generated yet.</td></tr>
                            ) : (
                                keys.map((key) => (
                                    <tr key={key.id} className="hover:bg-slate-50/50 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="flex items-center gap-3">
                                                <div className="p-2 bg-slate-100 rounded text-slate-600">
                                                    <FaKey size={12} />
                                                </div>
                                                <span className="font-medium text-slate-900">{key.name}</span>
                                            </div>
                                        </td>
                                        <td className="px-6 py-4 text-sm text-slate-600">
                                            {new Date(key.created_at).toLocaleDateString()}
                                        </td>
                                        <td className="px-6 py-4 text-sm text-slate-600">
                                            {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <Button onClick={() => handleDelete(key.id)} variant="ghost" size="icon" className="text-slate-400 hover:text-red-600">
                                                <FaTrash />
                                            </Button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
                    <h2 className="text-lg font-semibold text-blue-900 mb-2">Ready to connect OpenClaw?</h2>
                    <p className="text-sm text-blue-700 mb-4">
                        Download our skill definition and follow the setup guide to start scheduling posts with your AI agent.
                    </p>
                    <div className="flex gap-4">
                        <Button variant="outline" className="bg-white border-blue-200 text-blue-700" onClick={() => window.location.href = '/agent-docs'}>
                            View Setup Guide
                        </Button>
                    </div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default ApiKeys;
