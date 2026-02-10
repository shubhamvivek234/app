import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import { FaTwitter, FaInstagram, FaLinkedin, FaFacebook, FaTiktok, FaYoutube, FaPinterest } from 'react-icons/fa';
import { Button } from '@/components/ui/button';

const CreatePost = () => {
  const navigate = useNavigate();
  const [selectedType, setSelectedType] = useState(null);

  const postTypes = [
    {
      id: 'text',
      title: 'Text Post',
      icon: (
        <svg className="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
        </svg>
      ),
      platforms: ['facebook', 'twitter', 'linkedin'],
    },
    {
      id: 'image',
      title: 'Image Post',
      icon: (
        <svg className="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      ),
      platforms: ['facebook', 'twitter', 'linkedin', 'instagram', 'pinterest'],
    },
    {
      id: 'video',
      title: 'Video Post',
      icon: (
        <svg className="w-12 h-12 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
      ),
      platforms: ['facebook', 'twitter', 'linkedin', 'youtube', 'tiktok'],
    },
  ];

  const platformIcons = {
    facebook: <FaFacebook className="text-blue-600" />,
    twitter: <FaTwitter className="text-blue-400" />,
    linkedin: <FaLinkedin className="text-blue-700" />,
    instagram: <FaInstagram className="text-pink-600" />,
    pinterest: <FaPinterest className="text-red-600" />,
    youtube: <FaYoutube className="text-red-600" />,
    tiktok: <FaTiktok className="text-gray-900" />,
  };

  const handleSelectType = (type) => {
    setSelectedType(type);
    // Navigate to the actual post creation form
    navigate(`/create/${type}`);
  };

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto">
        {/* Page Title */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Create a new post</h1>
        </div>

        {/* Post Type Selection Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {postTypes.map((type) => (
            <div
              key={type.id}
              onClick={() => handleSelectType(type.id)}
              className="bg-white border-2 border-gray-200 rounded-lg p-8 hover:border-green-500 hover:shadow-lg transition-all cursor-pointer group"
            >
              {/* Icon */}
              <div className="flex justify-center mb-4">
                {type.icon}
              </div>

              {/* Title */}
              <h3 className="text-xl font-semibold text-gray-900 text-center mb-6">
                {type.title}
              </h3>

              {/* Platform Icons */}
              <div className="flex justify-center items-center space-x-3">
                {type.platforms.map((platform) => (
                  <div key={platform} className="text-2xl">
                    {platformIcons[platform]}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Connection Prompt */}
        <div className="mt-12 text-center">
          <p className="text-gray-600">
            You can connect more accounts{' '}
            <button
              onClick={() => navigate('/accounts')}
              className="text-green-500 hover:text-green-600 font-medium underline"
            >
              here
            </button>
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default CreatePost;