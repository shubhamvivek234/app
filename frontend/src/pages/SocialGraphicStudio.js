import React from 'react';
import { Link } from 'react-router-dom';
import { FaArrowLeft, FaPalette, FaBolt } from 'react-icons/fa';
import DashboardLayout from '@/components/DashboardLayout';
import SocialGraphicStudio from '@/components/studio/SocialGraphicStudio';

export default function SocialGraphicStudioPage() {
  return (
    <DashboardLayout>
      <div className="min-h-[100dvh] bg-[#FAF9F6] dark:bg-[#0C0A09] text-gray-900 dark:text-gray-100 py-8 px-4 sm:px-6 lg:px-10 transition-colors relative font-sans">
        {/* Subtle Ambient Grid Backdrop */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:24px_24px] opacity-40" />

        <div className="max-w-[1440px] mx-auto relative z-10 space-y-8">
          {/* Top Studio Header */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-gray-200/80 dark:border-zinc-800/80">
            <div>
              <div className="flex items-center gap-2 mb-2.5 flex-wrap">
                <Link
                  to="/social-tools"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-500 hover:text-indigo-600 dark:text-gray-400 dark:hover:text-indigo-400 transition-colors"
                >
                  <FaArrowLeft className="text-[10px]" />
                  <span>Social Tools</span>
                </Link>
                <span className="text-gray-300 dark:text-gray-700">•</span>
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-pink-500/10 border border-pink-500/20 text-pink-700 dark:text-pink-300 text-xs font-semibold tracking-wide">
                  <span className="w-1.5 h-1.5 rounded-full bg-pink-500 animate-pulse" />
                  Visual & Document Studio
                </div>
                <span className="text-gray-300 dark:text-gray-700 hidden sm:inline">•</span>
                <div className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 text-[11px] font-bold">
                  12 Card Archetypes
                </div>
                <div className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 text-[11px] font-bold">
                  Multi-Page PDF Carousels
                </div>
              </div>
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-gray-900 dark:text-white">
                Social Graphic Studio
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 max-w-2xl leading-relaxed">
                Design agency-grade social graphics, X/Twitter quote shots, big stat highlights, neo-brutalist drops, and multi-slide LinkedIn PDF carousels in seconds.
              </p>
            </div>

            {/* Quick Links / Badges */}
            <div className="flex items-center gap-2 self-start md:self-auto">
              <Link
                to="/viral-studio"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-white dark:bg-zinc-900 border border-gray-200/80 dark:border-zinc-800 text-gray-700 dark:text-gray-300 hover:border-amber-300 hover:text-amber-600 shadow-2xs transition-all cursor-pointer"
              >
                <FaBolt className="text-amber-500 text-xs" />
                <span>Viral Hook Vault</span>
              </Link>
            </div>
          </div>

          {/* Interactive Studio Component */}
          <SocialGraphicStudio />
        </div>
      </div>
    </DashboardLayout>
  );
}

