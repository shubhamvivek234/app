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
      <div className="max-w-5xl mx-auto px-4">
        {/* Page Header */}
        <div className="mb-12">
          <h1 className="text-3xl font-bold text-gray-900">Create a new post</h1>
          <p className="text-gray-500 text-sm mt-2">Choose a content type to get started</p>
        </div>

        {/* Post Type Selection Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          {postTypes.map((postType) => (
            <button
              key={postType.id}
              onClick={() => setComposerType(postType.id)}
              data-testid={`post-type-${postType.id}`}
              className="relative group bg-offwhite border border-gray-200 rounded-xl p-8 hover:border-green-400 hover:shadow-lg hover:shadow-green-400/10 transition-all duration-300 cursor-pointer focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
            >
              {/* Gradient background on hover */}
              <div className="absolute inset-0 bg-gradient-to-br from-green-50/0 to-green-50/0 group-hover:from-green-50/50 group-hover:to-green-100/30 rounded-xl transition-all duration-300 pointer-events-none" />

              <div className="relative z-10 flex flex-col items-center justify-center h-full">
                {/* Icon Container */}
                <div className="flex justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                  <div className="p-3 bg-gray-50 rounded-lg group-hover:bg-green-100 transition-colors duration-300">
                    {postType.icon}
                  </div>
                </div>

                {/* Title */}
                <h3 className="text-lg font-semibold text-gray-900 text-center mb-1 group-hover:text-green-700 transition-colors duration-300">
                  {postType.title}
                </h3>

                {/* Subtitle */}
                <p className="text-xs text-gray-500 text-center mb-6">
                  {postType.id === 'text' && 'Share thoughts & updates'}
                  {postType.id === 'image' && 'Upload photos & graphics'}
                  {postType.id === 'video' && 'Post videos & reels'}
                </p>

                {/* Platform Icons Grid */}
                <div className="w-full">
                  <p className="text-xs font-medium text-gray-600 mb-3 uppercase tracking-wider">Compatible with</p>
                  <div className="grid grid-cols-3 gap-2">
                    {postType.platforms.map((platform) => (
                      <div
                        key={platform}
                        className="flex items-center justify-center p-2 bg-gray-50 rounded-lg text-gray-600 group-hover:bg-white group-hover:text-green-600 transition-all duration-300 text-lg"
                      >
                        {platformIcons[platform]}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Connection Prompt - Enhanced */}
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              ✓
            </div>
            <p className="text-sm text-gray-700">
              Ready to post? Connect more social accounts to expand your reach.{' '}
              <button
                onClick={() => navigate('/accounts')}
                className="text-green-700 hover:text-green-800 font-semibold hover:underline transition-colors"
                data-testid="connect-accounts-link"
              >
                Add accounts now
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
