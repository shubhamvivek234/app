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

  // null = closed, 'text' | 'image' | 'video' | 'mixed' = composer open for that type
  const [composerType, setComposerType] = useState(null);

  const postTypes = [
    {
      id: 'text',
      title: 'Text Post',
      subtitle: 'Share thoughts & updates',
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
      subtitle: 'Upload photos & graphics',
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
      subtitle: 'Post videos & reels',
      icon: (
        <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <rect x="2" y="4" width="16" height="12" rx="2" strokeWidth={1.5} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M22 8l-4 2v4l4 2V8z" />
        </svg>
      ),
      platforms: ['facebook', 'twitter', 'linkedin', 'youtube', 'tiktok', 'instagram', 'pinterest', 'threads'],
    },
    {
      id: 'mixed',
      title: 'Mixed Media',
      subtitle: 'Post images & videos together',
      icon: (
        <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          {/* Image frame (slightly offset back) */}
          <rect x="2" y="5" width="14" height="11" rx="2" strokeWidth={1.5} opacity="0.6" />
          <circle cx="6" cy="9" r="1.2" strokeWidth={1.5} opacity="0.6" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 13l-4-4-5 5" opacity="0.6" />
          {/* Video camera (overlapping front) */}
          <rect x="7" y="9" width="11" height="8" rx="1.5" strokeWidth={1.5} />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M22 11l-3 1.5v3L22 17v-6z" />
        </svg>
      ),
      platforms: ['facebook', 'instagram', 'threads'],
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
      <div className="max-w-5xl mx-auto px-4">
        {/* Page Header */}
        <div className="mb-12">
          <h1 className="text-3xl font-bold text-gray-900">Create a new post</h1>
          <p className="text-gray-500 text-sm mt-2">Choose a content type to get started</p>
        </div>

        {/* Post Type Selection Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-12">
          {postTypes.map((postType) => {
            const colorConfigs = {
              text:  { border: 'hover:border-blue-400',   shadow: 'hover:shadow-blue-400/20',   bg: 'group-hover:from-blue-50/60 group-hover:to-blue-100/40',     icon: 'group-hover:bg-blue-100 group-hover:text-blue-600',     title: 'group-hover:text-blue-700',   platform: 'group-hover:text-blue-500',   ring: 'focus:ring-blue-500' },
              image: { border: 'hover:border-purple-400', shadow: 'hover:shadow-purple-400/20', bg: 'group-hover:from-purple-50/60 group-hover:to-pink-100/40',   icon: 'group-hover:bg-purple-100 group-hover:text-purple-600', title: 'group-hover:text-purple-700', platform: 'group-hover:text-purple-500', ring: 'focus:ring-purple-500' },
              video: { border: 'hover:border-orange-400', shadow: 'hover:shadow-orange-400/20', bg: 'group-hover:from-orange-50/60 group-hover:to-red-100/40',    icon: 'group-hover:bg-orange-100 group-hover:text-orange-600', title: 'group-hover:text-orange-700', platform: 'group-hover:text-orange-500', ring: 'focus:ring-orange-500' },
              mixed: { border: 'hover:border-teal-400',   shadow: 'hover:shadow-teal-400/20',   bg: 'group-hover:from-teal-50/60 group-hover:to-cyan-100/40',     icon: 'group-hover:bg-teal-100 group-hover:text-teal-600',     title: 'group-hover:text-teal-700',   platform: 'group-hover:text-teal-500',   ring: 'focus:ring-teal-500' },
            };
            const colors = colorConfigs[postType.id];

            return (
              <button
                key={postType.id}
                onClick={() => setComposerType(postType.id)}
                data-testid={`post-type-${postType.id}`}
                className={`relative group bg-offwhite border border-gray-200 rounded-xl p-8 ${colors.border} hover:shadow-lg ${colors.shadow} transition-all duration-300 cursor-pointer focus:outline-none focus:ring-2 ${colors.ring} focus:ring-offset-2`}
              >
                {/* Gradient background on hover */}
                <div className={`absolute inset-0 bg-gradient-to-br from-transparent to-transparent ${colors.bg} rounded-xl transition-all duration-300 pointer-events-none`} />

                <div className="relative z-10 flex flex-col items-center justify-center h-full">
                  {/* Icon Container */}
                  <div className="flex justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                    <div className={`p-3 bg-gray-50 rounded-lg transition-colors duration-300 ${colors.icon}`}>
                      {postType.icon}
                    </div>
                  </div>

                  {/* Title */}
                  <h3 className={`text-lg font-semibold text-gray-900 text-center mb-1 transition-colors duration-300 ${colors.title}`}>
                    {postType.title}
                  </h3>

                  {/* Subtitle */}
                  <p className="text-xs text-gray-500 text-center mb-6">
                    {postType.subtitle}
                  </p>

                  {/* Platform Icons Grid */}
                  <div className="w-full">
                    <p className="text-xs font-medium text-gray-600 mb-3 uppercase tracking-wider">Compatible with</p>
                    <div className="grid grid-cols-3 gap-2">
                      {postType.platforms.map((platform) => (
                        <div
                          key={platform}
                          className={`flex items-center justify-center p-2 bg-gray-50 rounded-lg text-gray-600 group-hover:bg-white transition-all duration-300 text-lg ${colors.platform}`}
                        >
                          {platformIcons[platform]}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Connection Prompt - Colorful gradient banner */}
        <div className="bg-gradient-to-r from-blue-50 via-purple-50 via-pink-50 to-orange-50 border border-pink-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-sm">
              ✦
            </div>
            <p className="text-sm text-gray-700">
              Ready to post? Connect more social accounts to expand your reach.{' '}
              <button
                onClick={() => navigate('/accounts')}
                className="bg-gradient-to-r from-purple-600 to-pink-600 bg-clip-text text-transparent font-semibold hover:from-purple-700 hover:to-pink-700 transition-all"
                data-testid="connect-accounts-link"
              >
                Add accounts now →
              </button>
            </p>
          </div>
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
