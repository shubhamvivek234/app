import React, { useState, useCallback } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { createPost, generateContent } from '@/lib/api';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { FaTwitter, FaLinkedin, FaInstagram, FaMagic, FaVideo, FaImage, FaFileAlt } from 'react-icons/fa';
import { useAuth } from '@/context/AuthContext';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const CreatePost = () => {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [postType, setPostType] = useState('text'); // text, image, video
  const [content, setContent] = useState('');
  const [platforms, setPlatforms] = useState([]);
  const [scheduledTime, setScheduledTime] = useState('');
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [showAiDialog, setShowAiDialog] = useState(false);
  
  // Media state
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [videoUrl, setVideoUrl] = useState('');
  const [coverImageUrl, setCoverImageUrl] = useState('');
  const [videoTitle, setVideoTitle] = useState('');
  const [uploading, setUploading] = useState(false);

  const platformOptions = [
    { id: 'twitter', name: 'Twitter/X', icon: FaTwitter, color: 'text-blue-400' },
    { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: 'text-pink-500' },
    { id: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, color: 'text-blue-600' },
  ];

  const onDrop = useCallback(async (acceptedFiles) => {
    setUploading(true);
    const newFiles = [];

    for (const file of acceptedFiles) {
      try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await axios.post(`${BACKEND_URL}/api/upload`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
            Authorization: `Bearer ${token}`,
          },
        });

        newFiles.push({
          name: file.name,
          url: response.data.url,
          type: file.type,
        });

        // Auto-set URLs based on post type
        if (postType === 'video' && file.type.startsWith('video/')) {
          setVideoUrl(response.data.url);
        }
      } catch (error) {
        toast.error(`Failed to upload ${file.name}`);
      }
    }

    setUploadedFiles([...uploadedFiles, ...newFiles]);
    setUploading(false);
    toast.success(`Uploaded ${newFiles.length} file(s)`);
  }, [uploadedFiles, token, postType]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: postType === 'video' 
      ? { 'video/*': ['.mp4', '.mov', '.avi'] }
      : { 'image/*': ['.png', '.jpg', '.jpeg', '.gif'] },
    multiple: postType !== 'video',
  });

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
      const postData = {
        content,
        post_type: postType,
        platforms,
        scheduled_time: scheduledTime || null,
      };

      // Add media based on post type
      if (postType === 'image') {
        postData.media_urls = uploadedFiles.map(f => f.url);
      } else if (postType === 'video') {
        postData.video_url = videoUrl;
        postData.cover_image_url = coverImageUrl;
        postData.video_title = videoTitle;
      }

      await createPost(postData);
      toast.success(scheduledTime ? 'Post scheduled successfully!' : 'Post created as draft!');
      navigate('/content');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create post');
    } finally {
      setLoading(false);
    }
  };

  const removeFile = (index) => {
    setUploadedFiles(uploadedFiles.filter((_, i) => i !== index));
  };

  return (
    <DashboardLayout>
      <div className=\"max-w-4xl mx-auto space-y-8\">
        {/* Header */}
        <div>
          <h1 className=\"text-3xl font-semibold tracking-tight text-slate-900\">Create Post</h1>
          <p className=\"text-base text-slate-600 mt-1\">
            Compose and schedule your social media content
          </p>
        </div>

        <form onSubmit={handleSubmit} className=\"space-y-6\">
          {/* Post Type Selector */}
          <div className=\"bg-white rounded-lg border border-border p-6 space-y-4\">
            <Label className=\"text-base font-medium\">Post Type</Label>
            <div className=\"grid grid-cols-3 gap-4\">
              {[
                { id: 'text', name: 'Text', icon: FaFileAlt },
                { id: 'image', name: 'Image', icon: FaImage },
                { id: 'video', name: 'Video', icon: FaVideo },
              ].map((type) => {
                const Icon = type.icon;
                const isSelected = postType === type.id;
                return (
                  <button
                    key={type.id}
                    type=\"button\"
                    onClick={() => setPostType(type.id)}
                    data-testid={`post-type-${type.id}`}
                    className={`p-4 rounded-lg border-2 transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50'
                        : 'border-border hover:border-slate-300'
                    }`}
                  >
                    <Icon className=\"text-2xl text-indigo-600 mx-auto mb-2\" />
                    <p className=\"text-sm font-medium text-slate-900\">{type.name}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Content Area */}
          <div className=\"bg-white rounded-lg border border-border p-6 space-y-4\">
            <div className=\"flex justify-between items-center\">
              <Label htmlFor=\"content\" className=\"text-base font-medium\">
                Post Content
              </Label>
              <Button
                type=\"button\"
                variant=\"outline\"
                size=\"sm\"
                onClick={() => setShowAiDialog(!showAiDialog)}
                data-testid=\"ai-generate-button\"
              >
                <FaMagic className=\"mr-2\" />
                AI Generate
              </Button>
            </div>

            {showAiDialog && (
              <div className=\"p-4 bg-indigo-50 rounded-lg border border-indigo-200 space-y-3\" data-testid=\"ai-dialog\">
                <Input
                  placeholder=\"E.g., Write a post about productivity tips for entrepreneurs\"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  data-testid=\"ai-prompt-input\"
                />
                <Button
                  type=\"button\"
                  size=\"sm\"
                  onClick={handleAiGenerate}
                  disabled={aiLoading}
                  data-testid=\"ai-submit-button\"
                >
                  {aiLoading ? 'Generating...' : 'Generate'}
                </Button>
              </div>
            )}

            <Textarea
              id=\"content\"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder=\"Write your post here...\"
              className=\"min-h-[200px] resize-none\"
              data-testid=\"post-content-textarea\"
            />
            <div className=\"text-sm text-slate-500\">{content.length} characters</div>
          </div>

          {/* Video Title (for video posts) */}
          {postType === 'video' && (
            <div className=\"bg-white rounded-lg border border-border p-6 space-y-4\">
              <Label htmlFor=\"video-title\" className=\"text-base font-medium\">
                Video Title (Optional)
              </Label>
              <Input
                id=\"video-title\"
                value={videoTitle}
                onChange={(e) => setVideoTitle(e.target.value)}
                placeholder=\"Enter video title\"
                data-testid=\"video-title-input\"
              />
            </div>
          )}

          {/* Media Upload */}
          {(postType === 'image' || postType === 'video') && (
            <div className=\"bg-white rounded-lg border border-border p-6 space-y-4\">
              <Label className=\"text-base font-medium\">
                {postType === 'video' ? 'Upload Video' : 'Upload Images'}
              </Label>
              
              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                  isDragActive ? 'border-indigo-600 bg-indigo-50' : 'border-border hover:border-slate-300'
                }`}
                data-testid=\"dropzone\"
              >
                <input {...getInputProps()} />
                {uploading ? (
                  <div className=\"text-slate-600\">Uploading...</div>
                ) : isDragActive ? (
                  <div className=\"text-indigo-600\">Drop files here...</div>
                ) : (
                  <div className=\"space-y-2\">
                    <div className=\"text-slate-600\">
                      Drag & drop {postType === 'video' ? 'video' : 'images'} here, or click to select
                    </div>
                    <div className=\"text-sm text-slate-500\">
                      {postType === 'video' ? 'MP4, MOV, AVI' : 'PNG, JPG, JPEG, GIF'}
                    </div>
                  </div>
                )}
              </div>

              {/* Uploaded Files */}
              {uploadedFiles.length > 0 && (
                <div className=\"space-y-2\">
                  <Label className=\"text-sm font-medium\">Uploaded Files</Label>
                  {uploadedFiles.map((file, index) => (
                    <div
                      key={index}
                      className=\"flex items-center justify-between p-3 bg-slate-50 rounded-md\"
                      data-testid={`uploaded-file-${index}`}
                    >
                      <span className=\"text-sm text-slate-700\">{file.name}</span>
                      <button
                        type=\"button\"
                        onClick={() => removeFile(index)}
                        className=\"text-red-600 hover:text-red-700\"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Cover Image for Video */}
              {postType === 'video' && (
                <div className=\"space-y-2\">
                  <Label htmlFor=\"cover-image\">Cover Image URL (Optional)</Label>
                  <Input
                    id=\"cover-image\"
                    value={coverImageUrl}
                    onChange={(e) => setCoverImageUrl(e.target.value)}
                    placeholder=\"Enter cover image URL\"
                    data-testid=\"cover-image-input\"
                  />
                </div>
              )}
            </div>
          )}

          {/* Platform Selection */}
          <div className=\"bg-white rounded-lg border border-border p-6 space-y-4\">
            <Label className=\"text-base font-medium\">Select Platforms</Label>
            <div className=\"grid grid-cols-3 gap-4\">
              {platformOptions.map((platform) => {
                const Icon = platform.icon;
                const isSelected = platforms.includes(platform.id);
                return (
                  <button
                    key={platform.id}
                    type=\"button\"
                    onClick={() => togglePlatform(platform.id)}
                    data-testid={`platform-${platform.id}`}
                    className={`p-4 rounded-lg border-2 transition-all ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-50'
                        : 'border-border hover:border-slate-300'
                    }`}
                  >
                    <Icon className={`text-3xl ${platform.color} mx-auto mb-2`} />
                    <p className=\"text-sm font-medium text-slate-900\">{platform.name}</p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Schedule */}
          <div className=\"bg-white rounded-lg border border-border p-6 space-y-4\">
            <div>
              <Label htmlFor=\"schedule\" className=\"text-base font-medium\">
                Schedule Post (Optional)
              </Label>
              {user?.subscription_status !== 'active' && (
                <p className=\"text-sm text-amber-600 mt-1\">
                  Upgrade to a paid plan to schedule posts
                </p>
              )}
            </div>
            <Input
              id=\"schedule\"
              type=\"datetime-local\"
              value={scheduledTime}
              onChange={(e) => setScheduledTime(e.target.value)}
              disabled={user?.subscription_status !== 'active'}
              data-testid=\"schedule-input\"
            />
          </div>

          {/* Actions */}
          <div className=\"flex gap-3\">
            <Button
              type=\"submit\"
              disabled={loading}
              data-testid=\"submit-post-button\"
            >
              {loading ? 'Creating...' : scheduledTime ? 'Schedule Post' : 'Save as Draft'}
            </Button>
            <Button
              type=\"button\"
              variant=\"outline\"
              onClick={() => navigate('/dashboard')}
              data-testid=\"cancel-button\"
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
