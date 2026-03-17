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
  FaSearch,
  FaSmile,
  FaClipboardList,
  FaMusic,
  FaShoppingBag,
  FaMapMarkerAlt,
  FaLink,
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

  // Instagram specific state
  const [postFormat, setPostFormat] = useState('Post'); // Post, Reel, Story
  const [firstComment, setFirstComment] = useState('');
  const [location, setLocation] = useState('');
  const [shopGridLink, setShopGridLink] = useState('');

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
      const apiUrl = 'http://localhost:8001';

      // Get unique platforms from selected accounts
      const platforms = [...new Set(
        availableAccounts
          .filter(a => selectedAccounts.includes(a.id))
          .map(a => a.platform)
      )];

      let scheduledDateTime = null;
      if (isScheduleEnabled && scheduledDate && scheduledTime) {
        try {
          // Use a more robust date construction
          const [year, month, day] = scheduledDate.split('-').map(Number);
          const [hours, minutes] = scheduledTime.split(':').map(Number);
          const date = new Date(year, month - 1, day, hours, minutes);
          if (isNaN(date.getTime())) {
            throw new Error("Invalid date/time selected");
          }
          scheduledDateTime = date.toISOString();
        } catch (e) {
          console.error("Date construction error:", e);
          toast.error("Invalid date or time format");
          setLoading(false);
          return;
        }
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
        instagram_post_format: postFormat,
        instagram_first_comment: firstComment,
        instagram_location: location,
        instagram_shop_grid_link: shopGridLink,
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
          timeout: 15000,
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
            {/* Instagram Composer Area */}
            <div className="bg-white rounded-lg border border-gray-200 p-6 mb-4">
              {/* Account Avatars & Platform Icons Header */}
              <div className="flex items-center gap-4 mb-6">
                <div className="flex -space-x-2">
                  {availableAccounts
                    .filter(a => selectedAccounts.includes(a.id) && a.platform === 'instagram')
                    .map((account) => {
                      const platformInfo = platformIcons[account.platform] || {};
                      const Icon = platformInfo.icon || FaFacebook;
                      return (
                        <div key={account.id} className="relative">
                          {account.picture_url ? (
                            <img
                              src={account.picture_url}
                              alt={account.platform_username}
                              className="w-10 h-10 rounded-full object-cover border-2 border-white shadow-sm"
                            />
                          ) : (
                            <div className={`w-10 h-10 rounded-full ${getAvatarColor(account.platform_username)} flex items-center justify-center text-white text-sm font-medium border-2 border-white shadow-sm`}>
                              {account.platform_username?.charAt(0)?.toUpperCase() || 'U'}
                            </div>
                          )}
                          <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-white border border-gray-100 flex items-center justify-center shadow-sm">
                            <Icon className={`text-[10px] ${platformInfo.color}`} />
                          </div>
                        </div>
                      );
                    })}
                  {availableAccounts.filter(a => selectedAccounts.includes(a.id) && a.platform === 'instagram').length === 0 && (
                    <div className="w-10 h-10 rounded-full bg-gray-100 border-2 border-dashed border-gray-300 flex items-center justify-center text-gray-400">
                      ?
                    </div>
                  )}
                </div>
                <span className="text-sm font-medium text-gray-500">Selected Instagram Accounts</span>
              </div>

              {type === 'video' && getSelectedPlatforms().includes('instagram') ? (
                // INSTAGRAM SPECIFIC UI
                <>
                  {/* Post Type Selection */}
                  <div className="flex items-center gap-6 mb-6">
                    <FaInstagram className="text-pink-500 text-xl" />
                    <div className="flex items-center gap-4">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="postFormat"
                          value="Post"
                          checked={postFormat === 'Post'}
                          onChange={(e) => setPostFormat(e.target.value)}
                          className="text-pink-500 focus:ring-pink-500 w-4 h-4"
                        />
                        <span className="text-sm font-medium text-gray-900">Post</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="postFormat"
                          value="Reel"
                          checked={postFormat === 'Reel'}
                          onChange={(e) => setPostFormat(e.target.value)}
                          className="text-pink-500 focus:ring-pink-500 w-4 h-4"
                        />
                        <span className="text-sm font-medium text-gray-900">Reel</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="postFormat"
                          value="Story"
                          checked={postFormat === 'Story'}
                          onChange={(e) => setPostFormat(e.target.value)}
                          className="text-pink-500 focus:ring-pink-500 w-4 h-4"
                        />
                        <span className="text-sm font-medium text-gray-900">Story</span>
                      </label>
                    </div>
                  </div>

                  {/* Caption Textarea */}
                  <Textarea
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="What would you like to share?"
                    rows={1}
                    className="resize-none bg-transparent border-none focus-visible:ring-0 px-0 text-base placeholder:text-gray-400 min-h-[40px] mb-4"
                    maxLength={2200}
                  />

                  {/* Inline Media Upload (only show if no media uploaded) */}
                  {!uploadedMedia && (
                    <div
                      className="border border-dashed border-gray-300 rounded-lg p-8 mb-6 bg-transparent transition-colors hover:border-gray-400 hover:bg-gray-50 cursor-pointer flex flex-col items-center justify-center min-h-[200px] max-w-sm"
                      onClick={(e) => {
                        if (!uploading && !uploadedMedia) {
                          fileInputRef.current?.click();
                        }
                      }}
                      onDrop={handleDrop}
                      onDragOver={handleDragOver}
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
                            if (type === 'video' && mediaRawAspectRatio) {
                              const reader = new FileReader();
                              reader.addEventListener('load', () => {
                                setCropImageSrc(reader.result);
                                setShowCropper(true);
                              });
                              reader.readAsDataURL(file);
                            } else {
                              uploadCoverImageToBackend(file);
                            }
                            e.target.value = null;
                          }
                        }}
                        className="hidden"
                      />

                      {uploading ? (
                        <div className="flex flex-col items-center">
                          <p className="text-gray-900 font-medium mb-2 text-sm">Uploading...</p>
                          <div className="w-48 bg-gray-200 rounded-full h-1.5 mb-1 relative overflow-hidden">
                            <div
                              className="bg-gray-800 h-1.5 rounded-full transition-all duration-300"
                              style={{ width: `${uploadProgress}%` }}
                            ></div>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="w-10 h-10 rounded flex items-center justify-center mb-3 text-gray-400 group-hover:text-gray-500 transition-colors">
                            <FaImage className="text-2xl" />
                          </div>
                          <p className="text-gray-900 font-medium text-sm text-center">Drag & drop or<br /><span className="text-blue-600 font-normal">select a file</span></p>
                        </>
                      )}
                    </div>
                  )}
                  {uploadedMedia && (
                    // Hidden inputs still needed when media is uploaded so cover image can be triggered from right sidebar
                    <div className="hidden">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept={type === 'video' ? 'video/*' : type === 'image' ? 'image/*' : 'image/*,video/*'}
                        onChange={handleFileUpload}
                      />
                      <input
                        ref={coverImageInputRef}
                        type="file"
                        accept="image/*"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            if (type === 'video' && mediaRawAspectRatio) {
                              const reader = new FileReader();
                              reader.addEventListener('load', () => {
                                setCropImageSrc(reader.result);
                                setShowCropper(true);
                              });
                              reader.readAsDataURL(file);
                            } else {
                              uploadCoverImageToBackend(file);
                            }
                            e.target.value = null;
                          }
                        }}
                      />
                    </div>
                  )}

                  {/* Actions Toolbar */}
                  <div className="flex items-center justify-between border-y border-gray-100 py-3 mb-6">
                    <div className="flex items-center gap-4">
                      <button
                        className="w-6 h-6 rounded-full bg-slate-900 text-white flex items-center justify-center text-xs font-bold font-serif italic hover:opacity-80 transition-opacity"
                        title="Canva"
                      >
                        C
                      </button>
                      <button
                        className="text-gray-500 hover:text-gray-700 transition-colors"
                        onClick={() => fileInputRef.current?.click()}
                        title="Select Media"
                      >
                        <FaImage className="text-lg" />
                      </button>
                      <button
                        className="text-gray-500 hover:text-gray-700 transition-colors"
                        title="Emoji"
                      >
                        <FaSmile className="text-lg" />
                      </button>
                      <button
                        className="text-gray-500 hover:text-gray-700 transition-colors"
                        title="Clipboard"
                      >
                        <FaClipboardList className="text-lg" />
                      </button>
                    </div>
                    <span className="text-xs text-gray-400 font-medium bg-gray-50 px-2 py-1 rounded">
                      {2200 - content.length}
                    </span>
                  </div>

                  {/* Advanced Inputs */}
                  <div className="space-y-4 max-w-2xl">
                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <Label className="text-sm font-semibold text-gray-900">Add Stickers</Label>
                      <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" className="h-8 rounded-full px-4 text-xs font-medium border-gray-300 text-gray-700">
                          <FaMusic className="mr-2 text-gray-400" /> Music
                        </Button>
                        <Button variant="outline" size="sm" className="h-8 rounded-full px-4 text-xs font-medium border-gray-300 text-gray-700">
                          <FaShoppingBag className="mr-2 text-gray-400" /> Tag Products
                        </Button>
                        <div className="ml-auto text-blue-600 text-sm font-medium flex items-center gap-1 cursor-pointer">
                          <span className="text-xl leading-none -mt-1">⚙</span> Automatic <FaChevronDown className="text-[10px]" />
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <Label className="text-sm font-semibold text-gray-900">First Comment</Label>
                      <Input
                        placeholder="Your comment"
                        value={firstComment}
                        onChange={(e) => setFirstComment(e.target.value)}
                        className="bg-white border-gray-200"
                      />
                    </div>

                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <Label className="text-sm font-semibold text-gray-900">Location</Label>
                      <div className="relative">
                        <Input
                          placeholder="Type the location"
                          value={location}
                          onChange={(e) => setLocation(e.target.value)}
                          className="bg-white border-gray-200"
                        />
                        <FaChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none" />
                      </div>
                    </div>

                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <div className="flex items-center gap-1">
                        <Label className="text-sm font-semibold text-gray-900">Shop Grid Link</Label>
                        <FaInfoCircle className="text-gray-400 text-xs" />
                      </div>
                      <Input
                        placeholder="Website or Product URL"
                        value={shopGridLink}
                        onChange={(e) => setShopGridLink(e.target.value)}
                        className="bg-white border-gray-200"
                      />
                    </div>
                  </div>
                </>
              ) : (
                // GENERIC UI for non-video or non-instagram posts
                <div className="p-8 text-center border-2 border-dashed border-gray-200 rounded-lg text-gray-500">
                  <p>Select an Instagram account to see the Composer.</p>
                  <p className="text-sm mt-2">Currently, only the Instagram Video/Reel composer interface is fully customized.</p>
                </div>
              )}
            </div>
          </div>

          {/* Right Sidebar */}
          <div className="w-72 flex-shrink-0">
            <div className="bg-white rounded-lg border border-gray-200 p-4 sticky top-6">
              {/* Media Preview */}
              {uploadedMedia && (
                <div className="mb-4">
                  <h3 className="font-medium text-gray-900 mb-2">
                    {type === 'video' ? 'Video' : 'Image'} Preview
                  </h3>
                  <div className="relative rounded-lg overflow-hidden border border-gray-200 group bg-black">
                    {type === 'video' ? (
                      <video
                        src={uploadedMedia.url}
                        controls
                        className="w-full"
                        style={{ maxHeight: '300px' }}
                      />
                    ) : (
                      <img
                        src={uploadedMedia.url}
                        alt="Preview"
                        className="w-full object-contain"
                        style={{ maxHeight: '300px' }}
                      />
                    )}
                    <button
                      onClick={() => setUploadedMedia(null)}
                      className="absolute top-2 right-2 bg-black/50 hover:bg-black/70 text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <FaTimes className="text-xs" />
                    </button>
                  </div>
                </div>
              )}

              {/* Cover Image Display */}
              {coverImage && (
                <div className="mb-4">
                  <h3 className="font-medium text-gray-900 mb-2">Cover Image</h3>
                  <div className="relative rounded-lg overflow-hidden border border-gray-200 group">
                    <img
                      src={coverImage}
                      alt="Video Cover"
                      className="w-full object-cover"
                      style={{ aspectRatio: mediaRawAspectRatio || '16/9' }}
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
                        min={new Date().toISOString().split('T')[0]}
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
    </DashboardLayout>
  );
};

export default CreatePostForm;

