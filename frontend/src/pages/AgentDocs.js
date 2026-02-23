import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { FaTerminal, FaRobot, FaExternalLinkAlt, FaDownload } from 'react-icons/fa';
import SocialEntanglerLogo from '@/components/SocialEntanglerLogo';

const AgentDocs = () => {
    const navigate = useNavigate();

    const skillJson = {
        "name": "SocialEntangler",
        "description": "Manage social media posts and media uploads",
        "tools": [
            {
                "name": "channels:list",
                "description": "List all connected social media channels",
                "endpoint": "/api/agent/channels",
                "method": "GET"
            },
            {
                "name": "upload",
                "description": "Upload a media file (image/video)",
                "endpoint": "/api/agent/upload",
                "method": "POST",
                "parameters": {
                    "file": "FormFile"
                }
            },
            {
                "name": "posts:create",
                "description": "Create and schedule a new social media post",
                "endpoint": "/api/agent/posts",
                "method": "POST",
                "parameters": {
                    "channel_id": "string",
                    "content": "string",
                    "media_urls": "string (comma-separated)",
                    "scheduled_at": "string (ISO date, optional)"
                }
            }
        ]
    };

    return (
        <div className="min-h-screen bg-white">
            {/* Mini Header */}
            <nav className="bg-white border-b border-gray-100 py-4 sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex justify-between items-center">
                    <div className="cursor-pointer" onClick={() => navigate('/')}>
                        <SocialEntanglerLogo />
                    </div>
                    <div className="flex gap-4 items-center">
                        <Button variant="ghost" className="text-gray-600" onClick={() => navigate('/')}>Back to Home</Button>
                        <Button onClick={() => navigate('/signup')}>Get Started</Button>
                    </div>
                </div>
            </nav>

            <div className="max-w-4xl mx-auto px-4 py-12 space-y-12">
                <div className="space-y-4">
                    <div className="inline-flex items-center gap-2 px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-xs font-semibold uppercase tracking-wider">
                        <FaRobot /> AI Agent Integration
                    </div>
                    <h1 className="text-4xl font-bold text-slate-900 tracking-tight">Connect with OpenClaw</h1>
                    <p className="text-lg text-slate-600 leading-relaxed max-w-2xl">
                        Give your AI agent the power to manage your social media presence. Use OpenClaw to schedule posts, upload media, and list your connected channels automatically.
                    </p>
                </div>

                <section className="space-y-6">
                    <h2 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold">1</span>
                        Get your API Key
                    </h2>
                    <div className="bg-slate-50 rounded-xl p-6 border border-slate-200">
                        <p className="text-slate-700 mb-4 font-medium">
                            First, log in to your SocialEntangler account and navigate to the <strong>API Keys</strong> section in your dashboard to generate a secret key.
                        </p>
                        <Button onClick={() => navigate('/api-keys')} className="bg-indigo-600 hover:bg-indigo-700">Go to API Keys</Button>
                    </div>
                </section>

                <section className="space-y-6">
                    <h2 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold">2</span>
                        Configure Environment
                    </h2>
                    <p className="text-slate-700 leading-relaxed">
                        Export the following environment variables to your OpenClaw agent environment. This allows the agent to authenticate and locate our API.
                    </p>
                    <div className="relative group">
                        <pre className="bg-slate-900 text-indigo-300 p-6 rounded-xl font-mono text-sm overflow-x-auto shadow-lg border border-slate-800">
                            <code>{`export SOCIALENTANGLER_API_KEY="your_api_key_here"
export SOCIALENTANGLER_API_URL="${window.location.protocol}//${window.location.host}"`}</code>
                        </pre>
                    </div>
                </section>

                <section className="space-y-6">
                    <h2 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-900 text-white text-sm font-bold">3</span>
                        Add the Skill Manifest
                    </h2>
                    <p className="text-slate-700 leading-relaxed">
                        Register SocialEntangler as a skill in your OpenClaw agent by providing this JSON manifest.
                        This tells the agent exactly how to interact with our Headless Social API tools.
                    </p>
                    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div className="bg-slate-50 px-4 py-2 border-b border-slate-200 flex justify-between items-center text-xs text-slate-500 font-mono">
                            <span className="font-semibold uppercase">skill.json</span>
                            <button onClick={() => {
                                navigator.clipboard.writeText(JSON.stringify(skillJson, null, 2));
                                alert('Copied to clipboard!');
                            }} className="hover:text-slate-900 flex items-center gap-1 font-medium transition-colors">
                                <FaDownload /> Copy JSON
                            </button>
                        </div>
                        <pre className="p-6 text-sm text-slate-800 font-mono overflow-auto max-h-96 bg-gray-50 leading-relaxed">
                            {JSON.stringify(skillJson, null, 2)}
                        </pre>
                    </div>
                </section>

                <section className="py-8 border-t border-slate-100">
                    <div className="bg-indigo-600 rounded-2xl p-8 text-center text-white shadow-xl shadow-indigo-100">
                        <h3 className="text-xl font-bold mb-2 text-white font-primary">Need help with integration?</h3>
                        <p className="text-indigo-100 mb-6 max-w-md mx-auto leading-relaxed">
                            Our support team is ready to assist you with custom agent configurations or advanced automation needs.
                        </p>
                        <Button variant="outline" className="bg-white text-indigo-600 border-white hover:bg-slate-100 px-8 py-2 h-auto text-base font-semibold" onClick={() => navigate('/support')}>
                            Get Professional Support
                        </Button>
                    </div>
                </section>
            </div>
        </div>
    );
};

export default AgentDocs;
