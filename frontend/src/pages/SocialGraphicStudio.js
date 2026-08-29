import React from 'react';
import { Link } from 'react-router-dom';
import { FaArrowLeft, FaPalette, FaMagic } from 'react-icons/fa';
import DashboardLayout from '@/components/DashboardLayout';
import SocialGraphicStudio from '@/components/studio/SocialGraphicStudio';

export default function SocialGraphicStudioPage() {
  return (
    <DashboardLayout>
      <div className="max-w-[1440px] mx-auto pb-12">
        
        {/* Top Header */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1.5">
              <Link
                to="/social-tools"
                className="text-xs font-bold text-gray-500 hover:text-indigo-600 dark:text-gray-400 flex items-center gap-1.5 transition-colors"
              >
                <FaArrowLeft className="text-[10px]" />
                Back to Social Tools
              </Link>
              <span className="text-gray-300 dark:text-gray-700">•</span>
              <span className="inline-flex items-center gap-1 text-[11px] font-extrabold uppercase tracking-wider text-indigo-600 bg-indigo-50 dark:bg-indigo-950/60 dark:text-indigo-400 px-2.5 py-0.5 rounded-full">
                <FaPalette className="text-[10px]" /> Design Studio
              </span>
            </div>
            <h1 className="text-2xl font-extrabold tracking-tight text-gray-900 dark:text-white sm:text-3xl">
              Social Graphic Studio
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 max-w-xl">
              Create high-converting social graphics, quote cards, and announcement banners with custom gradients and typography without leaving your workspace.
            </p>
          </div>
        </div>

        {/* Interactive Studio Component */}
        <SocialGraphicStudio />

      </div>
    </DashboardLayout>
  );
}
