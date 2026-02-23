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
import Cropper from 'react-easy-crop';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { getSocialAccounts, uploadMedia } from '@/lib/api';
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
  const coverImageInputRef = useRef(null);

  // State
  const [content, setContent] = useState('');
  const [selectedAccounts, setSelectedAccounts] = useState([]);
  const [availableAccounts, setAvailableAccounts] = useState([]);
  const [scheduledDate, setScheduledDate] = useState('');
  const [scheduledTime, setScheduledTime] = useState('14:00');
  const [isScheduleEnabled, setIsScheduleEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadedMedia, setUploadedMedia] = useState(null);
  const [coverImage, setCoverImage] = useState(null);
  const [coverImageUploading, setCoverImageUploading] = useState(false);
  const [coverImageProgress, setCoverImageProgress] = useState(0);
  const [mediaAspectRatio, setMediaAspectRatio] = useState(null);
  const [mediaRawAspectRatio, setMediaRawAspectRatio] = useState(null);

  // YouTube Specific State
  const [videoTitle, setVideoTitle] = useState('');
  const [showYoutubeTitle, setShowYoutubeTitle] = useState(false);
  const [youtubePrivacy, setYoutubePrivacy] = useState('public');

  // Sync state
  const [syncCaptions, setSyncCaptions] = useState(false);

  // Cropper State
  const [showCropper, setShowCropper] = useState(false);
  const [cropImageSrc, setCropImageSrc] = useState(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [croppedAreaPixels, setCroppedAreaPixels] = useState(null);

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

  useEffect(() => {
    loadAccounts();
    // Set default date to today
    const today = new Date();
    setScheduledDate(today.toISOString().split('T')[0]);
  }, []);

  const loadAccounts = async () => {
    try {
      const accounts = await getSocialAccounts();
      setAvailableAccounts(accounts);
    } catch (error) {
      console.error('Failed to load accounts:', error);
      setAvailableAccounts([]);
    }
  };

  const toggleAccountSelection = (accountId) => {
    setSelectedAccounts(prev =>
      prev.includes(accountId)
        ? prev.filter(id => id !== accountId)
        : [...prev, accountId]
    );
  };

  const uploadToBackend = async (file) => {
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);
    setMediaAspectRatio(null); // Reset ratio when a new upload starts

    try {
      const response = await uploadMedia(file, (progressEvent) => {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setUploadProgress(progress);
      });

      if (response.success) {
        // Backend returns a relative url like /uploads/filename.ext
        const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
        const fullUrl = `${backendUrl}${response.url}`;

        setUploadedMedia({
          file,
          url: fullUrl,
          type: file.type.startsWith('video/') ? 'video' : 'image',
          name: file.name
        });
        toast.success('Media uploaded successfully');
      } else {
        throw new Error('Upload failed on server');
      }
    } catch (error) {
      console.error("Upload error:", error);
      toast.error("Failed to upload media");
    } finally {
      setUploading(false);
    }
  };

  const uploadCoverImageToBackend = async (file) => {
    if (!file) return;

    setCoverImageUploading(true);
    setCoverImageProgress(0);

    try {
      const response = await uploadMedia(file, (progressEvent) => {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setCoverImageProgress(progress);
      });

      if (response.success) {
        const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
        const fullUrl = `${backendUrl}${response.url}`;

        setCoverImage(fullUrl);
        toast.success('Cover image uploaded successfully');
      } else {
        throw new Error('Upload failed on server');
      }
    } catch (error) {
      console.error("Cover image upload error:", error);
      toast.error("Failed to upload cover image");
    } finally {
      setCoverImageUploading(false);
    }
  };

  const onCropComplete = (croppedArea, croppedAreaPixels) => {
    setCroppedAreaPixels(croppedAreaPixels);
  };

  const createImage = (url) =>
    new Promise((resolve, reject) => {
      const image = new Image();
      image.addEventListener('load', () => resolve(image));
      image.addEventListener('error', (error) => reject(error));
      image.setAttribute('crossOrigin', 'anonymous'); // needed to avoid cross-origin issues on CodeSandbox
      image.src = url;
    });

  const getCroppedImg = async (imageSrc, pixelCrop) => {
    const image = await createImage(imageSrc);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    if (!ctx) {
      return null;
    }

    // set canvas size to match the bounding box
    canvas.width = image.width;
    canvas.height = image.height;

    // draw image
    ctx.drawImage(image, 0, 0);

    const croppedCanvas = document.createElement('canvas');
    const croppedCtx = croppedCanvas.getContext('2d');

    if (!croppedCtx) {
      return null;
    }

    // Set the size of the cropped canvas
    croppedCanvas.width = pixelCrop.width;
    croppedCanvas.height = pixelCrop.height;

    // Draw the cropped image onto the new canvas
    croppedCtx.drawImage(
      canvas,
      pixelCrop.x,
      pixelCrop.y,
      pixelCrop.width,
      pixelCrop.height,
      0,
      0,
      pixelCrop.width,
      pixelCrop.height
    );

    // As Base64 string
    // return croppedCanvas.toDataURL('image/jpeg');

    // As a blob
    return new Promise((resolve, reject) => {
      croppedCanvas.toBlob((file) => {
        if (file) {
          file.name = 'cropped_cover.jpg';
          resolve(file);
        } else {
          reject(new Error('Canvas is empty'));
        }
      }, 'image/jpeg');
    });
  };

  const handleApplyCrop = async () => {
    try {
      const croppedBlob = await getCroppedImg(cropImageSrc, croppedAreaPixels);
      setShowCropper(false);
      setCropImageSrc(null);
      // Create a file object from blob
      const file = new File([croppedBlob], "cover_image.jpg", { type: "image/jpeg" });
      uploadCoverImageToBackend(file);
    } catch (e) {
      console.error(e);
      toast.error('Failed to crop image');
    }
  };

  const handleFileUpload = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      uploadToBackend(file);
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) {
      uploadToBackend(file);
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
      const apiUrl = process.env.REACT_APP_BACKEND_URL || '';

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

      const postData = {
        content: content,
        platforms,
        accounts: selectedAccounts,
        scheduled_time: scheduledDateTime,
        status: status === 'published' ? 'scheduled' : (status || 'draft'),
        post_type: type,
        cover_image: coverImage,
        media_urls: uploadedMedia ? [uploadedMedia.url] : [],
        youtube_title: videoTitle,
        youtube_privacy: youtubePrivacy,
      };

      if (!syncCaptions && Object.keys(platformCaptions).length > 0) {
        postData.platform_specific_content = platformCaptions;
      }

      // Ensure immediate publishing works by setting time to now if 'published'
      if (status === 'published') {
        postData.scheduled_time = new Date().toISOString();
        postData.status = 'scheduled'; // The scheduler picks it up immediately
      }

      await axios.post(
        `${apiUrl}/api/posts`,
        postData,
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

  // Display Aspect Ratio helper
  const calculateAspectRatio = (width, height) => {
    const gcd = (a, b) => b === 0 ? a : gcd(b, a % b);
    const divisor = gcd(width, height);
    if (divisor === 0) return `${width}x${height}`;
    const ratioX = width / divisor;
    const ratioY = height / divisor;

    // For common resolutions that don't divide cleanly to standard ratios
    if (ratioX > 50 || ratioY > 50) {
      const floatRatio = (width / height).toFixed(2);
      return `${width}x${height} (${floatRatio}:1)`;
    }

    return `${width}x${height} (${ratioX}:${ratioY})`;
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
                      {account.picture_url ? (
                        <img
                          src={account.picture_url}
                          alt={account.platform_username}
                          className={`w-10 h-10 rounded-full object-cover border-2 ${isSelected ? 'border-green-500' : 'border-transparent'}`}
                        />
                      ) : (
                        <div className={`w-10 h-10 rounded-full ${getAvatarColor(account.platform_username)} flex items-center justify-center text-white text-sm font-medium border-2 ${isSelected ? 'border-green-500' : 'border-transparent'}`}>
                          {account.platform_username?.charAt(0)?.toUpperCase() || 'U'}
                        </div>
                      )}
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
              onClick={() => !uploading && fileInputRef.current?.click()}
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
              <input
                ref={coverImageInputRef}
                type="file"
                accept="image/*"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    // check if we have the video ratio
                    if (type === 'video' && mediaRawAspectRatio) {
                      // read file to data url to pass to cropper
                      const reader = new FileReader();
                      reader.addEventListener('load', () => {
                        setCropImageSrc(reader.result);
                        setShowCropper(true);
                      });
                      reader.readAsDataURL(file);
                    } else {
                      // Fallback or not a video post
                      uploadCoverImageToBackend(file);
                    }
                    e.target.value = null; // reset so same file can be selected again
                  }
                }}
                className="hidden"
              />

              {uploading ? (
                <div className="flex flex-col items-center">
                  <div className="w-12 h-12 rounded-lg bg-green-100 flex items-center justify-center mb-3 animate-pulse">
                    <FaUpload className="text-green-500 text-xl" />
                  </div>
                  <p className="text-gray-900 font-medium mb-2">Uploading...</p>
                  <div className="w-64 bg-gray-200 rounded-full h-2.5 mb-1 relative overflow-hidden">
                    <div
                      className="bg-green-500 h-2.5 rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    ></div>
                  </div>
                  <span className="text-xs text-gray-500">{Math.round(uploadProgress)}%</span>
                </div>
              ) : uploadedMedia ? (
                <div className="flex flex-col items-center">
                  {uploadedMedia.type === 'video' ? (
                    <video
                      src={uploadedMedia.url}
                      className="max-h-64 rounded mb-2"
                      controls
                      onLoadedMetadata={(e) => {
                        const { videoWidth, videoHeight } = e.target;
                        if (videoWidth && videoHeight) {
                          setMediaAspectRatio(calculateAspectRatio(videoWidth, videoHeight));
                          setMediaRawAspectRatio(videoWidth / videoHeight);
                        }
                      }}
                    />
                  ) : (
                    <img
                      src={uploadedMedia.url}
                      alt="Uploaded"
                      className="max-h-64 rounded mb-2"
                      onLoad={(e) => {
                        const { naturalWidth, naturalHeight } = e.target;
                        if (naturalWidth && naturalHeight) {
                          setMediaAspectRatio(calculateAspectRatio(naturalWidth, naturalHeight));
                          setMediaRawAspectRatio(naturalWidth / naturalHeight);
                        }
                      }}
                    />
                  )}
                  {mediaAspectRatio && (
                    <div className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-md mb-2">
                      Dimensions: {mediaAspectRatio}
                    </div>
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
                    {type === 'video' && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          coverImageInputRef.current?.click();
                        }}
                        disabled={coverImageUploading || !mediaRawAspectRatio}
                        title={!mediaRawAspectRatio ? "Upload video first to set aspect ratio" : "Upload Cover Image"}
                      >
                        <FaImage className="mr-1" />
                        {coverImageUploading ? `Uploading ${coverImageProgress}%` : coverImage ? 'Change Cover' : 'Upload Cover'}
                      </Button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <div className="w-12 h-12 rounded-lg bg-green-100 flex items-center justify-center mb-3 group-hover:bg-green-200 transition-colors">
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

              {!uploadedMedia && !uploading && (
                <div className="absolute right-4 top-4 text-gray-400 text-sm flex items-center gap-1 cursor-pointer hover:text-gray-600">
                  <FaUpload /> Import
                </div>
              )}
            </div>

            {/* Main Caption */}
            <div className="mb-4">
              <div className="relative flex items-center mb-2">
                <div className="flex items-center gap-1">
                  <Label className="text-sm text-gray-600 font-bold">Main Caption / Description</Label>
                  <FaInfoCircle className="text-gray-400 text-xs" title="This will be used as the default description or caption across platforms" />
                </div>
                <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="syncCaptions"
                    checked={syncCaptions}
                    onChange={(e) => {
                      setSyncCaptions(e.target.checked);
                      if (e.target.checked && expandedSections.platformCaptions) {
                        toggleSection('platformCaptions');
                      }
                    }}
                    className="rounded border-gray-300 text-green-500 focus:ring-green-500"
                  />
                  <Label htmlFor="syncCaptions" className="text-sm text-gray-600 cursor-pointer font-medium">
                    Apply to all selected platforms
                  </Label>
                </div>
              </div>
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Start writing your description here..."
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
                  onClick={() => !syncCaptions && toggleSection('platformCaptions')}
                  className={expandedSections.platformCaptions ? "bg-green-500 hover:bg-green-600" : ""}
                  disabled={syncCaptions}
                  title={syncCaptions ? "Disable 'Apply to all' to edit platform captions" : ""}
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
              <div className="space-y-6 border-t border-gray-200 pt-4 mt-6">
                {getSelectedPlatforms().map((platform) => {
                  const platformInfo = platformIcons[platform] || {};
                  const Icon = platformInfo.icon || FaFacebook;
                  const hasCustomCaption = platformCaptions.hasOwnProperty(platform);
                  const charLimit = getCharLimit(platform);
                  const currentText = hasCustomCaption ? platformCaptions[platform] : content;
                  const currentLength = currentText.length;

                  const platformLabels = {
                    youtube: "YouTube Description",
                    instagram: "Instagram Caption",
                    facebook: "Facebook Caption",
                    twitter: "X (Twitter) Post",
                    linkedin: "LinkedIn Post",
                    tiktok: "TikTok Caption",
                    pinterest: "Pinterest Description",
                  };
                  const label = platformLabels[platform] || `${platform} Caption`;

                  return (
                    <div key={platform} className="mb-4">
                      <div className="flex items-center gap-1 mb-2">
                        <Icon className={`text-md ${platformInfo.color} mr-1`} />
                        <Label className="text-sm font-medium text-gray-700 capitalize">{label}</Label>
                        <FaInfoCircle className="text-gray-400 text-xs ml-1" />
                      </div>
                      <Textarea
                        value={currentText}
                        onChange={(e) => handlePlatformCaptionChange(platform, e.target.value)}
                        placeholder={`Start writing your ${label.toLowerCase()} here...`}
                        rows={4}
                        className="resize-none bg-white border-gray-200"
                        data-testid={`caption-${platform}`}
                      />
                      <div className="flex justify-between items-center mt-1">
                        <div>
                          {hasCustomCaption ? (
                            <button
                              onClick={() => clearPlatformCaption(platform)}
                              className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"
                            >
                              <FaTimes /> Reset to Main Caption
                            </button>
                          ) : (
                            <span className="text-xs text-gray-400 italic">Syncing with Main Caption</span>
                          )}
                        </div>
                        <span className={`text-xs ${currentLength > charLimit ? 'text-red-500' : 'text-gray-400'}`}>
                          {currentLength}/{charLimit}
                        </span>
                      </div>

                      {/* YouTube Specific Settings */}
                      {platform === 'youtube' && type === 'video' && (
                        <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                          <div className="flex flex-col gap-4">
                            <div>
                              <div className="flex gap-2">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setShowYoutubeTitle(!showYoutubeTitle)}
                                  className="bg-white"
                                >
                                  <FaYoutube className="mr-2 text-red-500" />
                                  {showYoutubeTitle ? 'Hide Video Title' : 'Add Video Title'}
                                  <FaChevronDown className={`ml-2 transition-transform ${showYoutubeTitle ? 'rotate-180' : ''}`} />
                                </Button>
                                <div className="flex items-center gap-2">
                                  <Label className="text-sm text-gray-600 font-medium whitespace-nowrap">Privacy:</Label>
                                  <select
                                    value={youtubePrivacy}
                                    onChange={(e) => setYoutubePrivacy(e.target.value)}
                                    className="text-sm border border-gray-200 rounded-md bg-white p-1.5 focus:ring-green-500 focus:border-green-500"
                                  >
                                    <option value="public">Public</option>
                                    <option value="private">Private</option>
                                    <option value="unlisted">Unlisted</option>
                                  </select>
                                </div>
                              </div>

                              {showYoutubeTitle && (
                                <div className="mt-4">
                                  <Label className="text-sm text-gray-600 mb-1 block">Title (Required)</Label>
                                  <Input
                                    value={videoTitle}
                                    onChange={(e) => setVideoTitle(e.target.value)}
                                    placeholder="We Tried the World's Spiciest Pepper!"
                                    className="bg-white"
                                  />
                                  <div className="flex justify-end mt-1">
                                    <span className={`text-xs ${videoTitle.length > 100 ? 'text-red-500' : 'text-gray-400'}`}>
                                      {videoTitle.length}/100
                                    </span>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}

                    </div>
                  );
                })}

                {getSelectedPlatforms().length === 0 && (
                  <p className="text-sm text-gray-500 italic pb-2">Select accounts above to customize platform-specific captions.</p>
                )}
              </div>
            )}


          </div>

          {/* Right Sidebar */}
          <div className="w-72 flex-shrink-0">
            <div className="bg-white rounded-lg border border-gray-200 p-4 sticky top-6">

              {/* Cover Image Display */}
              {coverImage && (
                <div className="mb-4">
                  <h3 className="font-medium text-gray-900 mb-2">Cover Image</h3>
                  <div className="relative rounded-lg overflow-hidden border border-gray-200 group">
                    <img
                      src={coverImage}
                      alt="Video Cover"
                      className="w-full aspect-video object-cover"
                    />
                    <button
                      onClick={() => setCoverImage(null)}
                      className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <FaTimes className="text-xs" />
                    </button>
                  </div>
                </div>
              )}

              {/* Schedule Toggle */}
              <div className="flex items-center justify-between mb-4 border-t border-gray-200 pt-4">
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

              {/* End of Schedule Section */}

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

        {/* Cropping Modal */}
        <Dialog open={showCropper} onOpenChange={setShowCropper}>
          <DialogContent className="max-w-3xl h-[80vh] flex flex-col">
            <DialogHeader>
              <DialogTitle>Crop Cover Image to match Video</DialogTitle>
            </DialogHeader>
            <div className="flex-1 relative bg-gray-900 rounded-md overflow-hidden min-h-0">
              {cropImageSrc && (
                <Cropper
                  image={cropImageSrc}
                  crop={crop}
                  zoom={zoom}
                  aspect={mediaRawAspectRatio || 16 / 9}
                  onCropChange={setCrop}
                  onCropComplete={onCropComplete}
                  onZoomChange={setZoom}
                  objectFit="contain"
                />
              )}
            </div>
            <div className="pt-4 flex justify-between items-center shrink-0 border-t mt-2">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-500">Zoom:</span>
                <input
                  type="range"
                  value={zoom}
                  min={1}
                  max={3}
                  step={0.1}
                  aria-labelledby="Zoom"
                  onChange={(e) => setZoom(e.target.value)}
                  className="w-32"
                />
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setShowCropper(false)}>Cancel</Button>
                <Button onClick={handleApplyCrop} className="bg-green-500 hover:bg-green-600">Crop & Upload</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout >
  );
};

export default CreatePostForm;
