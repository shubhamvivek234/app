import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import axios from 'axios';
import { getSocialAccounts } from '@/lib/api';
import {
  FaTwitter,
  FaInstagram,
  FaLinkedin,
  FaFacebook,
  FaTiktok,
  FaYoutube,
  FaPinterest,
  FaUpload,
  FaImage,
  FaCalendarAlt,
  FaClock,
  FaChevronDown,
  FaSave,
  FaEdit,
  FaTimes,
  FaInfoCircle,
  FaSearch
} from 'react-icons/fa';
import { SiBluesky, SiThreads } from 'react-icons/si';

const CreatePostForm = () => {
  const { type } = useParams();
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  // State
  const [content, setContent] = useState('');
  const [selectedAccounts, setSelectedAccounts] = useState([]);
  const [availableAccounts, setAvailableAccounts] = useState([]);
  const [scheduledDate, setScheduledDate] = useState('');
  const [scheduledTime, setScheduledTime] = useState('14:00');
  const [isScheduleEnabled, setIsScheduleEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [uploadedMedia, setUploadedMedia] = useState(null);
  const [coverImage, setCoverImage] = useState(null);
  const [videoTitle, setVideoTitle] = useState('');

  // Platform-specific captions
  const [platformCaptions, setPlatformCaptions] = useState({});
  const [editingPlatform, setEditingPlatform] = useState(null);

  // Expanded sections
  const [expandedSections, setExpandedSections] = useState({
    platformCaptions: true,
    pastCaptions: false,
    processing: false,
    youtubeTitle: false,
    tiktokConfig: false
  });

  // Platform icons mapping
  const platformIcons = {
    facebook: { icon: FaFacebook, color: 'text-blue-600' },
    twitter: { icon: FaTwitter, color: 'text-blue-400' },
    linkedin: { icon: FaLinkedin, color: 'text-blue-700' },
    instagram: { icon: FaInstagram, color: 'text-pink-500' },
    pinterest: { icon: FaPinterest, color: 'text-red-600' },
    youtube: { icon: FaYoutube, color: 'text-red-600' },
    tiktok: { icon: FaTiktok, color: 'text-gray-900' },
    bluesky: { icon: SiBluesky, color: 'text-blue-500' },
    threads: { icon: SiThreads, color: 'text-gray-900' },
  };

  // Mock accounts for demo purposes
  const mockAccounts = [
    { id: '1', platform: 'bluesky', platform_username: 'jack friks', avatar: null },
    { id: '2', platform: 'facebook', platform_username: 'Jack friks', avatar: null },
    { id: '3', platform: 'facebook', platform_username: 'Curiosity Quench', avatar: null },
    { id: '4', platform: 'facebook', platform_username: 'Scroll less', avatar: null },
    { id: '5', platform: 'instagram', platform_username: 'jackfriks', avatar: null },
    { id: '6', platform: 'instagram', platform_username: 'curiosity.quench', avatar: null },
    { id: '7', platform: 'linkedin', platform_username: 'SocialEntangler', avatar: null },
    { id: '8', platform: 'linkedin', platform_username: 'jack friks', avatar: null },
    { id: '9', platform: 'pinterest', platform_username: 'jackfriks', avatar: null },
    { id: '10', platform: 'threads', platform_username: 'curiosity.quench', avatar: null },
    { id: '11', platform: 'tiktok', platform_username: 'jack friks', avatar: null },
    { id: '12', platform: 'tiktok', platform_username: 'Curiosity Quench', avatar: null },
    { id: '13', platform: 'twitter', platform_username: 'jackfriks', avatar: null },
    { id: '14', platform: 'twitter', platform_username: 'doofapp', avatar: null },
    { id: '15', platform: 'youtube', platform_username: 'jack friks', avatar: null },
    { id: '16', platform: 'youtube', platform_username: 'jack friks shorts', avatar: null },
  ];

  useEffect(() => {
    loadAccounts();
    // Set default date to today
    const today = new Date();
    setScheduledDate(today.toISOString().split('T')[0]);
  }, []);

  const loadAccounts = async () => {
    try {
      const accounts = await getSocialAccounts();
      // Use real accounts if available, otherwise use mock data
      setAvailableAccounts(accounts.length > 0 ? accounts : mockAccounts);
    } catch (error) {
      console.error('Failed to load accounts:', error);
      setAvailableAccounts(mockAccounts);
    }
  };

  const toggleAccountSelection = (accountId) => {
    setSelectedAccounts(prev =>
      prev.includes(accountId)
        ? prev.filter(id => id !== accountId)
        : [...prev, accountId]
    );
  };

  const handleFileUpload = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setUploadedMedia({
        file,
        url,
        type: file.type.startsWith('video/') ? 'video' : 'image',
        name: file.name
      });
      toast.success('Media uploaded successfully');
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setUploadedMedia({
        file,
        url,
        type: file.type.startsWith('video/') ? 'video' : 'image',
        name: file.name
      });
      toast.success('Media uploaded successfully');
    }
  };

  const handleDragOver = (event) => {
    event.preventDefault();
  };

  const getAvatarColor = (name) => {
    const colors = [
      'bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500',
      'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500'
    ];
    const index = (name?.charCodeAt(0) || 0) % colors.length;
    return colors[index];
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const getCharLimit = (platform) => {
    const limits = {
      twitter: 280,
      bluesky: 300,
      facebook: 2200,
      instagram: 2200,
      linkedin: 3000,
      youtube: 5000,
      tiktok: 2200,
      pinterest: 500,
      threads: 500
    };
    return limits[platform] || 400;
  };

  const handlePlatformCaptionChange = (platform, value) => {
    setPlatformCaptions(prev => ({
      ...prev,
      [platform]: value
    }));
  };

  const clearPlatformCaption = (platform) => {
    setPlatformCaptions(prev => {
      const newCaptions = { ...prev };
      delete newCaptions[platform];
      return newCaptions;
    });
    setEditingPlatform(null);
  };

  const handleSubmit = async (status) => {
    if (!content.trim() && type !== 'video') {
      toast.error('Please enter some content');
      return;
    }

    if (selectedAccounts.length === 0) {
      toast.error('Please select at least one account');
      return;
    }

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const apiUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

      // Get unique platforms from selected accounts
      const platforms = [...new Set(
        availableAccounts
          .filter(a => selectedAccounts.includes(a.id))
          .map(a => a.platform)
      )];

      let scheduledDateTime = null;
      if (isScheduleEnabled && scheduledDate && scheduledTime) {
        scheduledDateTime = new Date(`${scheduledDate}T${scheduledTime}`).toISOString();
      }

      await axios.post(
        `${apiUrl}/api/posts`,
        {
          content: content || videoTitle,
          platforms,
          scheduled_time: scheduledDateTime,
          status: status || 'draft',
          post_type: type,
          video_title: videoTitle,
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

  // Get unique platforms from selected accounts
  const getSelectedPlatforms = () => {
    return [...new Set(
      availableAccounts
        .filter(a => selectedAccounts.includes(a.id))
        .map(a => a.platform)
    )];
  };

  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 capitalize">
            Create {type} post
          </h1>
        </div>

        <div className="flex gap-6">
          {/* Main Content Area */}
          <div className="flex-1">
            {/* Account Selection */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <FaSearch className="text-xs" />
                  <span>Search & Filter</span>
                  <FaChevronDown className="text-xs" />
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <input type="checkbox" className="rounded" />
                  <span>Remember</span>
                </div>
              </div>

              {/* Account Avatars */}
              <div className="flex flex-wrap gap-1 pb-4 border-b border-gray-200">
                {availableAccounts.map((account) => {
                  const platformInfo = platformIcons[account.platform] || {};
                  const Icon = platformInfo.icon || FaFacebook;
                  const isSelected = selectedAccounts.includes(account.id);

                  return (
                    <button
                      key={account.id}
                      onClick={() => toggleAccountSelection(account.id)}
                      className={`relative group ${isSelected ? '' : 'opacity-40'}`}
                      data-testid={`account-${account.id}`}
                      title={`${account.platform_username} (${account.platform})`}
                    >
                      <div className={`w-10 h-10 rounded-full ${getAvatarColor(account.platform_username)} flex items-center justify-center text-white text-sm font-medium border-2 ${isSelected ? 'border-green-500' : 'border-transparent'}`}>
                        {account.platform_username?.charAt(0)?.toUpperCase() || 'U'}
                      </div>
                      <div className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-white border border-gray-200 flex items-center justify-center`}>
                        <Icon className={`text-[10px] ${platformInfo.color}`} />
                      </div>
                      {isSelected && account === availableAccounts.find(a => selectedAccounts[0] === a.id) && (
                        <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-green-500 text-white text-xs px-2 py-0.5 rounded whitespace-nowrap">
                          {account.platform_username}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Media Upload Area */}
            <div
              className="border-2 border-dashed border-gray-200 rounded-lg p-8 mb-4 bg-[#f5f7f5] cursor-pointer hover:border-green-400 transition-colors"
              onClick={() => fileInputRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              data-testid="media-upload-area"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={type === 'video' ? 'video/*' : type === 'image' ? 'image/*' : 'image/*,video/*'}
                onChange={handleFileUpload}
                className="hidden"
              />

              {uploadedMedia ? (
                <div className="flex flex-col items-center">
                  {uploadedMedia.type === 'video' ? (
                    <video
                      src={uploadedMedia.url}
                      className="max-h-40 rounded mb-2"
                      controls
                    />
                  ) : (
                    <img
                      src={uploadedMedia.url}
                      alt="Uploaded"
                      className="max-h-40 rounded mb-2"
                    />
                  )}
                  <div className="flex gap-2 mt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        fileInputRef.current?.click();
                      }}
                    >
                      <FaUpload className="mr-1" /> Replace Media
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        toast.info('Cover image selection coming soon');
                      }}
                    >
                      <FaImage className="mr-1" /> Set Cover Image
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <div className="w-12 h-12 rounded-lg bg-green-100 flex items-center justify-center mb-3">
                    <FaImage className="text-green-500 text-xl" />
                  </div>
                  <p className="text-gray-900 font-medium mb-1">Click to upload or drag and drop</p>
                  <p className="text-gray-500 text-sm mb-2">or hover and paste from clipboard</p>
                  <p className="text-gray-400 text-xs flex items-center gap-1">
                    {type === 'video' ? 'Video' : type === 'image' ? 'Image' : 'Media'}
                    <FaInfoCircle />
                  </p>
                </div>
              )}

              <div className="absolute right-4 top-4 text-gray-400 text-sm flex items-center gap-1 cursor-pointer hover:text-gray-600">
                <FaUpload /> Import
              </div>
            </div>

            {/* Main Caption */}
            <div className="mb-4">
              <div className="flex items-center gap-1 mb-2">
                <Label className="text-sm text-gray-600">Main Caption</Label>
                <FaInfoCircle className="text-gray-400 text-xs" />
              </div>
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Start writing your post here..."
                rows={4}
                className="resize-none bg-white border-gray-200"
                data-testid="main-caption"
              />
              <div className="flex justify-end mt-1">
                <span className="text-xs text-gray-400">{content.length}/400</span>
              </div>
            </div>

            {/* Post configurations & tools */}
            <div className="mb-4">
              <p className="text-xs text-gray-500 mb-2">Post configurations & tools</p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant={expandedSections.platformCaptions ? "default" : "outline"}
                  size="sm"
                  onClick={() => toggleSection('platformCaptions')}
                  className={expandedSections.platformCaptions ? "bg-green-500 hover:bg-green-600" : ""}
                >
                  Platform Captions
                  <FaChevronDown className={`ml-1 transition-transform ${expandedSections.platformCaptions ? 'rotate-180' : ''}`} />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleSection('pastCaptions')}
                >
                  <FaEdit className="mr-1" /> Past Captions
                  <FaChevronDown className="ml-1" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleSection('processing')}
                >
                  ⚙️ Processing
                  <FaChevronDown className="ml-1" />
                </Button>
                {type === 'video' && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleSection('youtubeTitle')}
                    >
                      <FaYoutube className="mr-1 text-red-500" /> YouTube Title
                      <FaChevronDown className="ml-1" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleSection('tiktokConfig')}
                    >
                      <FaTiktok className="mr-1" /> TikTok Config
                      <FaChevronDown className="ml-1" />
                    </Button>
                  </>
                )}
              </div>
            </div>

            {/* Platform-specific captions */}
            {expandedSections.platformCaptions && (
              <div className="space-y-4 border-t border-gray-200 pt-4">
                {getSelectedPlatforms().map((platform) => {
                  const platformInfo = platformIcons[platform] || {};
                  const Icon = platformInfo.icon || FaFacebook;
                  const hasCustomCaption = platformCaptions[platform];
                  const charLimit = getCharLimit(platform);
                  const currentLength = (hasCustomCaption || content).length;

                  return (
                    <div key={platform} className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="capitalize font-medium text-sm">{platform}</span>
                        {hasCustomCaption ? (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded">
                              Edited caption
                            </span>
                            <button
                              onClick={() => clearPlatformCaption(platform)}
                              className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
                            >
                              <FaTimes /> Clear
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400">Using main caption</span>
                            <button
                              onClick={() => setEditingPlatform(platform)}
                              className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
                            >
                              <FaEdit /> Edit
                            </button>
                          </div>
                        )}
                      </div>

                      {(hasCustomCaption || editingPlatform === platform) && (
                        <div>
                          <Textarea
                            value={platformCaptions[platform] || content}
                            onChange={(e) => handlePlatformCaptionChange(platform, e.target.value)}
                            placeholder={`Caption for ${platform}...`}
                            rows={3}
                            className="resize-none bg-white border-gray-200"
                            data-testid={`caption-${platform}`}
                          />
                          <div className="flex justify-end mt-1">
                            <span className={`text-xs ${currentLength > charLimit ? 'text-red-500' : 'text-gray-400'}`}>
                              {currentLength}/{charLimit}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                {getSelectedPlatforms().length === 0 && (
                  <p className="text-sm text-gray-500 italic">Select accounts above to customize platform-specific captions</p>
                )}
              </div>
            )}

            {/* YouTube Title (for video posts) */}
            {expandedSections.youtubeTitle && type === 'video' && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <Label className="text-sm text-gray-600 mb-2 block">YouTube Video Title</Label>
                <Input
                  value={videoTitle}
                  onChange={(e) => setVideoTitle(e.target.value)}
                  placeholder="Enter video title for YouTube..."
                  className="bg-white"
                  data-testid="youtube-title"
                />
              </div>
            )}
          </div>

          {/* Right Sidebar - Schedule */}
          <div className="w-72 flex-shrink-0">
            <div className="bg-white rounded-lg border border-gray-200 p-4 sticky top-6">
              {/* Schedule Toggle */}
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium text-gray-900">Schedule post</h3>
                <Switch
                  checked={isScheduleEnabled}
                  onCheckedChange={setIsScheduleEnabled}
                  className="data-[state=checked]:bg-green-500"
                  data-testid="schedule-toggle"
                />
              </div>

              {isScheduleEnabled && (
                <>
                  {/* Date */}
                  <div className="mb-3">
                    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200">
                      <FaCalendarAlt className="text-gray-400" />
                      <Input
                        type="date"
                        value={scheduledDate}
                        onChange={(e) => setScheduledDate(e.target.value)}
                        className="border-0 bg-transparent p-0 h-auto text-sm focus-visible:ring-0"
                        data-testid="schedule-date"
                      />
                    </div>
                  </div>

                  {/* Time */}
                  <div className="mb-4">
                    <div className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 border border-gray-200">
                      <FaClock className="text-gray-400" />
                      <Input
                        type="time"
                        value={scheduledTime}
                        onChange={(e) => setScheduledTime(e.target.value)}
                        className="border-0 bg-transparent p-0 h-auto text-sm focus-visible:ring-0"
                        data-testid="schedule-time"
                      />
                      <FaInfoCircle className="text-gray-400 text-xs" />
                    </div>
                  </div>

                  <p className="text-xs text-gray-500 mb-4">
                    Your post will be posted at {scheduledTime} in your local time.
                  </p>
                </>
              )}

              {/* Video Preview (if uploaded) */}
              {uploadedMedia && (
                <div className="mb-4">
                  {uploadedMedia.type === 'video' ? (
                    <video
                      src={uploadedMedia.url}
                      className="w-full rounded-lg"
                      controls
                    />
                  ) : (
                    <img
                      src={uploadedMedia.url}
                      alt="Preview"
                      className="w-full rounded-lg"
                    />
                  )}
                </div>
              )}

              {/* Action Buttons */}
              <div className="space-y-2">
                <Button
                  onClick={() => handleSubmit(isScheduleEnabled ? 'scheduled' : 'published')}
                  disabled={loading}
                  className="w-full bg-green-500 hover:bg-green-600"
                  data-testid="schedule-button"
                >
                  <FaCalendarAlt className="mr-2" />
                  {loading ? 'Processing...' : 'Schedule'}
                </Button>

                <Button
                  variant="outline"
                  onClick={() => handleSubmit('draft')}
                  disabled={loading}
                  className="w-full"
                  data-testid="save-draft-button"
                >
                  <FaSave className="mr-2" />
                  Save to Drafts
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default CreatePostForm;
