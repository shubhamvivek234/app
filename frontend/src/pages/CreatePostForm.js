import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import axios from 'axios';
import { FaTwitter, FaInstagram, FaLinkedin, FaFacebook, FaTiktok, FaYoutube, FaPinterest, FaMagic } from 'react-icons/fa';

const CreatePostForm = () => {
  const { type } = useParams();
  const navigate = useNavigate();
  const [content, setContent] = useState('');
  const [platforms, setPlatforms] = useState([]);
  const [scheduledTime, setScheduledTime] = useState('');
  const [loading, setLoading] = useState(false);
  const [showAiDialog, setShowAiDialog] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiLoading, setAiLoading] = useState(false);

  const platformOptions = [
    { id: 'twitter', name: 'Twitter/X', icon: FaTwitter, color: 'text-blue-400' },
    { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: 'text-pink-500' },
    { id: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, color: 'text-blue-600' },
    { id: 'facebook', name: 'Facebook', icon: FaFacebook, color: 'text-blue-700' },
    { id: 'youtube', name: 'YouTube', icon: FaYoutube, color: 'text-red-600' },
    { id: 'tiktok', name: 'TikTok', icon: FaTiktok, color: 'text-gray-900' },
    { id: 'pinterest', name: 'Pinterest', icon: FaPinterest, color: 'text-red-600' },
  ];

  const togglePlatform = (platformId) => {
    setPlatforms(prev =>
      prev.includes(platformId)
        ? prev.filter(p => p !== platformId)
        : [...prev, platformId]
    );
  };

  const handleGenerateAI = async () => {
    if (!aiPrompt.trim()) {
      toast.error('Please enter a prompt');
      return;
    }

    setAiLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      const response = await axios.post(
        `${apiUrl}/api/ai/generate-content`,
        {
          prompt: aiPrompt,
          platform: platforms[0] || 'twitter',
        },
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      setContent(response.data.content);
      setShowAiDialog(false);
      toast.success('Content generated!');
    } catch (error) {
      console.error('AI generation error:', error);
      toast.error('Failed to generate content');
    } finally {
      setAiLoading(false);
    }
  };

  const handleSubmit = async (status) => {
    if (!content.trim()) {
      toast.error('Please enter some content');
      return;
    }

    if (platforms.length === 0) {
      toast.error('Please select at least one platform');
      return;
    }

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      await axios.post(
        `${apiUrl}/api/posts`,
        {
          content,
          platforms,
          scheduled_time: scheduledTime || null,
          status: status || 'draft',
          post_type: type,
        },
        {
          headers: { Authorization: `Bearer ${token}` },
          withCredentials: true,
        }
      );

      toast.success(`Post ${status === 'scheduled' ? 'scheduled' : 'saved as draft'}!`);
      navigate('/content');
    } catch (error) {
      console.error('Error creating post:', error);
      toast.error('Failed to create post');
    } finally {
      setLoading(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900 capitalize">{type} Post</h1>
        </div>

        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-6">
          {/* Platform Selection */}
          <div>
            <Label className="text-base font-medium mb-3 block">Select Platforms</Label>
            <div className="flex flex-wrap gap-3">
              {platformOptions.map((platform) => {
                const Icon = platform.icon;
                const isSelected = platforms.includes(platform.id);
                return (
                  <button
                    key={platform.id}
                    onClick={() => togglePlatform(platform.id)}
                    className={`flex items-center space-x-2 px-4 py-2 rounded-lg border-2 transition-all ${
                      isSelected
                        ? 'border-green-500 bg-green-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <Icon className={`text-xl ${platform.color}`} />
                    <span className="text-sm font-medium">{platform.name}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Content */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <Label className="text-base font-medium">Content</Label>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAiDialog(true)}
                className="text-purple-600 border-purple-300 hover:bg-purple-50"
              >
                <FaMagic className="mr-2" />
                Generate with AI
              </Button>
            </div>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="What do you want to share?"
              rows={8}
              className="resize-none"
            />
            <p className="text-sm text-gray-500 mt-2">{content.length} characters</p>
          </div>

          {/* Schedule */}
          <div>
            <Label className="text-base font-medium mb-3 block">Schedule (Optional)</Label>
            <Input
              type="datetime-local"
              value={scheduledTime}
              onChange={(e) => setScheduledTime(e.target.value)}
              className="max-w-sm"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center space-x-4 pt-4">
            <Button
              onClick={() => handleSubmit('draft')}
              variant="outline"
              disabled={loading}
            >
              Save as Draft
            </Button>
            <Button
              onClick={() => handleSubmit(scheduledTime ? 'scheduled' : 'published')}
              disabled={loading}
              className="bg-green-500 hover:bg-green-600"
            >
              {loading ? 'Posting...' : scheduledTime ? 'Schedule Post' : 'Post Now'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => navigate('/create')}
            >
              Cancel
            </Button>
          </div>
        </div>
      </div>

      {/* AI Dialog */}
      {showAiDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-xl font-semibold mb-4">Generate Content with AI</h3>
            <Textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="Describe what you want to post about..."
              rows={4}
            />
            <div className="flex items-center space-x-3 mt-4">
              <Button
                onClick={handleGenerateAI}
                disabled={aiLoading}
                className="bg-purple-600 hover:bg-purple-700"
              >
                {aiLoading ? 'Generating...' : 'Generate'}
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowAiDialog(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}
    </DashboardLayout>
  );
};

export default CreatePostForm;