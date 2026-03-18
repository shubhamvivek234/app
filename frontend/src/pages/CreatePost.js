import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import CreatePostForm from '@/pages/CreatePostForm';
import {
  FaTwitter,
  FaInstagram,
  FaLinkedin,
  FaFacebook,
  FaTiktok,
  FaYoutube,
  FaPinterest
} from 'react-icons/fa';
import { SiBluesky, SiThreads } from 'react-icons/si';

const CreatePost = () => {
  const navigate = useNavigate();

  // null = closed, 'text' | 'image' | 'video' = composer open for that type
  const [composerType, setComposerType] = useState(null);

  const postTypes = [
    {
      id: 'text',
      title: 'Text Post',
      icon: (
        <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h7" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 5h18M3 5v2M3 5v-2M21 5v2M21 5v-2" />
        </svg>
      ),
      platforms: ['facebook', 'twitter', 'linkedin', 'threads', 'bluesky'],
    },
    {
      id: 'image',
      title: 'Image Post',
      icon: (
        <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth={1.5} />
          <circle cx="8.5" cy="8.5" r="1.5" strokeWidth={1.5} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 15l-5-5L5 21" />
        </svg>
      ),
      platforms: ['facebook', 'twitter', 'linkedin', 'instagram', 'pinterest', 'tiktok', 'threads'],
    },
    {
      id: 'video',
      title: 'Video Post',
      icon: (
        <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <rect x="2" y="4" width="16" height="12" rx="2" strokeWidth={1.5} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M22 8l-4 2v4l4 2V8z" />
        </svg>
      ),
      platforms: ['facebook', 'twitter', 'linkedin', 'youtube', 'tiktok', 'instagram', 'pinterest', 'threads'],
    },
  ];

  const platformIcons = {
    facebook:  <FaFacebook  className="text-gray-500" />,
    twitter:   <FaTwitter   className="text-gray-500" />,
    linkedin:  <FaLinkedin  className="text-gray-500" />,
    instagram: <FaInstagram className="text-gray-500" />,
    pinterest: <FaPinterest className="text-gray-500" />,
    youtube:   <FaYoutube   className="text-gray-500" />,
    tiktok:    <FaTiktok    className="text-gray-500" />,
    bluesky:   <SiBluesky   className="text-gray-500" />,
    threads:   <SiThreads   className="text-gray-500" />,
  };

  return (
    <DashboardLayout>
      <div className="max-w-4xl mx-auto">
        {/* Page Title */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Create a new post</h1>
        </div>

        {/* Post Type Selection Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {postTypes.map((postType) => (
            <div
              key={postType.id}
              onClick={() => setComposerType(postType.id)}
              data-testid={`post-type-${postType.id}`}
              className="bg-white border-2 border-dashed border-gray-200 rounded-lg p-6 hover:border-green-400 hover:bg-green-50/30 transition-all cursor-pointer group min-h-[200px] flex flex-col items-center justify-center"
            >
              {/* Icon */}
              <div className="flex justify-center mb-4 group-hover:scale-105 transition-transform">
                {postType.icon}
              </div>

              {/* Title */}
              <h3 className="text-lg font-medium text-gray-900 text-center mb-6">
                {postType.title}
              </h3>

              {/* Platform Icons */}
              <div className="flex justify-center items-center gap-2 flex-wrap">
                {postType.platforms.map((platform) => (
                  <div key={platform} className="text-lg">
                    {platformIcons[platform]}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Connection Prompt */}
        <div className="mt-8">
          <p className="text-sm text-gray-600 flex items-center gap-1">
            <span className="w-4 h-4 rounded-full bg-green-500 flex items-center justify-center text-white text-xs">i</span>
            You can connect more accounts{' '}
            <button
              onClick={() => navigate('/accounts')}
              className="text-green-600 hover:text-green-700 font-medium underline"
              data-testid="connect-accounts-link"
            >
              here
            </button>
          </p>
        </div>
      </div>

      {/* ── Composer modal (88% of screen) ──────────────────────────────────── */}
      {composerType && (
        <CreatePostForm
          postTypeOverride={composerType}
          asModal={true}
          onClose={() => setComposerType(null)}
        />
      )}
    </DashboardLayout>
  );
};

export default CreatePost;
