import React, { useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { createPost, generateContent } from '@/lib/api';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { FaTwitter, FaLinkedin, FaInstagram, FaMagic } from 'react-icons/fa';
import { useAuth } from '@/context/AuthContext';

const CreatePost = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [content, setContent] = useState('');
  const [platforms, setPlatforms] = useState([]);
  const [scheduledTime, setScheduledTime] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [showAiDialog, setShowAiDialog] = useState(false);

  const platformOptions = [
    { id: 'twitter', name: 'Twitter/X', icon: FaTwitter, color: 'text-blue-400' },
    { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: 'text-pink-500' },
    { id: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, color: 'text-blue-600' },
  ];

  const togglePlatform = (platformId) => {
    if (platforms.includes(platformId)) {
      setPlatforms(platforms.filter((p) => p !== platformId));
    } else {
      setPlatforms([...platforms, platformId]);
    }
  };

  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) {
      toast.error('Please enter a prompt');
      return;
    }

    setAiLoading(true);
    try {
      const response = await generateContent(aiPrompt);
      setContent(response.content);
      setShowAiDialog(false);
      setAiPrompt('');
      toast.success('Content generated!');
    } catch (error) {
      toast.error('Failed to generate content');
    } finally {
      setAiLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!content.trim()) {
      toast.error('Please enter post content');
      return;
    }

    if (platforms.length === 0) {
      toast.error('Please select at least one platform');
      return;
    }

    if (scheduledTime && user?.subscription_status !== 'active') {
      toast.error('Scheduling requires an active subscription');
      return;
    }

    setLoading(true);
    try {
      await createPost({
        content,
        platforms,
        scheduled_time: scheduledTime || null,
      });
      toast.success(scheduledTime ? 'Post scheduled successfully!' : 'Post created as draft!');
      navigate('/content');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create post');
    } finally {
      setLoading(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Create Post</h1>
          <p className="text-base text-slate-600 mt-1">
            Compose and schedule your social media content
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Content Area */}
          <div className="bg-white rounded-lg border border-border p-6 space-y-4">
            <div className="flex justify-between items-center">
              <Label htmlFor="content" className="text-base font-medium">
                Post Content
              </Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setShowAiDialog(!showAiDialog)}
                data-testid="ai-generate-button"
              >
                <FaMagic className="mr-2" />
                AI Generate
              </Button>
            </div>

            {showAiDialog && (
              <div className="p-4 bg-indigo-50 rounded-lg border border-indigo-200 space-y-3" data-testid="ai-dialog">
                <Input
                  placeholder="E.g., Write a post about productivity tips for entrepreneurs"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  data-testid="ai-prompt-input"
                />
                <Button
                  type="button"
                  size="sm"
                  onClick={handleAiGenerate}
                  disabled={aiLoading}
                  data-testid="ai-submit-button"
                >
                  {aiLoading ? 'Generating...' : 'Generate'}
                </Button>
              </div>
            )}

            <Textarea
              id="content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Write your post here..."
              className="min-h-[200px] resize-none"
              data-testid="post-content-textarea"
            />
            <div className="text-sm text-slate-500">{content.length} characters</div>
          </div>

          {/* Platform Selection */}
          <div className="bg-white rounded-lg border border-border p-6 space-y-4">
            <Label className="text-base font-medium">Select Platforms</Label>
            <div className="grid grid-cols-3 gap-4">
              {platformOptions.map((platform) => {
                const Icon = platform.icon;
                const isSelected = platforms.includes(platform.id);
                return (
                  <button
                    key={platform.id}
                    type="button"
                    onClick={() => togglePlatform(platform.id)}
                    data-testid={`platform-${platform.id}`}
                    className={`p-4 rounded-lg border-2 transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50'
                        : 'border-border hover:border-slate-300'
                    }`}
                  >
                    <Icon className={`text-3xl ${platform.color} mx-auto mb-2`} />
                    <p className="text-sm font-medium text-slate-900">{platform.name}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Schedule */}
          <div className="bg-white rounded-lg border border-border p-6 space-y-4">
            <div>
              <Label htmlFor="schedule" className="text-base font-medium">
                Schedule Post (Optional)
              </Label>
              {user?.subscription_status !== 'active' && (
                <p className="text-sm text-amber-600 mt-1">
                  Upgrade to a paid plan to schedule posts
                </p>
              )}
            </div>
            <Input
              id="schedule"
              type="datetime-local"
              value={scheduledTime}
              onChange={(e) => setScheduledTime(e.target.value)}
              disabled={user?.subscription_status !== 'active'}
              data-testid="schedule-input"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <Button
              type="submit"
              disabled={loading}
              data-testid="submit-post-button"
            >
              {loading ? 'Creating...' : scheduledTime ? 'Schedule Post' : 'Save as Draft'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/dashboard')}
              data-testid="cancel-button"
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </DashboardLayout>
  );
};

export default CreatePost;