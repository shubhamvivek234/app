import React from 'react';
import { Link } from 'react-router-dom';
import { FaArrowLeft, FaPalette, FaBolt } from 'react-icons/fa';
import DashboardLayout from '@/components/DashboardLayout';
import SocialGraphicStudio from '@/components/studio/SocialGraphicStudio';

export default function SocialGraphicStudioPage() {
  return (
    <DashboardLayout>
      <div className="min-h-[100dvh] bg-[#F7F7F7] dark:bg-[#0C0A09] text-[#222222] dark:text-gray-100 py-8 px-4 sm:px-6 lg:px-10 transition-colors relative font-sans">
        {/* Subtle Ambient Grid Backdrop */}
        <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:24px_24px] opacity-30" />

        <div className="max-w-[1440px] mx-auto relative z-10 space-y-7">
          {/* Top Studio Header — Airbnb Design Language */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 pb-6 border-b border-[#EBEBEB] dark:border-zinc-800">
            <div>
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <Link
                  to="/social-tools"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#6A6A6A] hover:text-[#222222] dark:text-gray-400 dark:hover:text-white transition-colors"
                >
                  <FaArrowLeft className="text-[10px]" />
                  <span>Social Tools</span>
                </Link>
                <span className="text-[#DDDDDD] dark:text-zinc-700">•</span>
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FFF1F4] dark:bg-[#FF385C]/10 border border-[#FF385C]/20 text-[#FF385C] text-xs font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#FF385C] animate-pulse" />
                  Visual & Document Studio
                </div>
                <span className="text-[#DDDDDD] dark:text-zinc-700 hidden sm:inline">•</span>
                <div className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white dark:bg-zinc-800 border border-[#EBEBEB] dark:border-zinc-700 text-[#222222] dark:text-gray-200 text-xs font-semibold shadow-2xs">
                  <span className="text-[#FF385C]">★</span>
                  <span>Superhost Creator Edition</span>
                </div>
                <div className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-gray-100 dark:bg-zinc-800 text-[#6A6A6A] dark:text-gray-400 text-[11px] font-semibold">
                  12 Archetypes · PDF Carousels
                </div>
              </div>
              <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-[#222222] dark:text-white">
                Social Graphic Studio
              </h1>
              <p className="text-sm text-[#6A6A6A] dark:text-gray-400 mt-1 max-w-2xl leading-relaxed">
                Design hospitality-grade social graphics, authentic quote cards, verified stat callouts, and multi-slide LinkedIn PDF carousels in seconds.
              </p>
            </div>

            {/* Quick Links / Badges */}
            <div className="flex items-center gap-2 self-start md:self-auto">
              <Link
                to="/viral-studio"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full text-xs font-semibold bg-white dark:bg-zinc-900 border border-[#DDDDDD] dark:border-zinc-800 text-[#222222] dark:text-gray-200 hover:border-[#FF385C] hover:text-[#FF385C] shadow-sm transition-all cursor-pointer"
              >
                <FaBolt className="text-[#FF385C] text-xs" />
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

