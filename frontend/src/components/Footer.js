import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import UnravlerLogo from '@/components/UnravlerLogo';
import SupportPopup from './SupportPopup';

const Footer = () => {
  const [isSupportOpen, setIsSupportOpen] = useState(false);

  return (
    <>
      <footer className="bg-gray-50 border-t border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-8 lg:gap-12">
            {/* Column 1: Logo & Description - Spans 2 cols on desktop to push Links right */}
            <div className="col-span-2 md:col-span-1 lg:col-span-2 flex flex-col items-start">
              <div className="mb-8 -ml-2">
                <UnravlerLogo size="large" />
              </div>
              <p className="text-sm text-gray-600 mb-8 leading-relaxed max-w-sm pr-4">
                Post content to multiple social media platforms at the same time, all-in one place.
                <br />
                <span className="font-medium text-indigo-600 mt-2 inline-block">Cross posting made easy.</span>
              </p>
              <p className="text-xs text-gray-500 mt-auto">
                Copyright © 2026 - All rights reserved
              </p>
            </div>

            {/* Column 2: LINKS */}
            <div className="lg:col-start-3">
              <h3 className="text-sm font-bold text-gray-900 mb-8 uppercase tracking-wider">Links</h3>
              <ul className="space-y-4">
                <li>
                  <button
                    onClick={() => setIsSupportOpen(true)}
                    className="text-sm text-gray-600 hover:text-indigo-600 transition-colors text-left"
                  >
                    Support
                  </button>
                </li>
                <li><Link to="/#pricing" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Pricing</Link></li>
                <li><Link to="/blog" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Blog</Link></li>
                <li><Link to="/affiliates" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Affiliates</Link></li>
              </ul>
            </div>

            {/* Column 3: PLATFORMS */}
            <div>
              <h3 className="text-sm font-bold text-gray-900 mb-8 uppercase tracking-wider">Platforms</h3>
              <ul className="space-y-4">
                <li><Link to="/platforms/twitter" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Twitter/X scheduler</Link></li>
                <li><Link to="/platforms/instagram" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Instagram scheduler</Link></li>
                <li><Link to="/platforms/linkedin" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">LinkedIn scheduler</Link></li>
                <li><Link to="/platforms/facebook" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Facebook scheduler</Link></li>
                <li><Link to="/platforms/tiktok" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">TikTok scheduler</Link></li>
                <li><Link to="/platforms/youtube" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">YouTube scheduler</Link></li>
                <li><Link to="/platforms/bluesky" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Bluesky scheduler</Link></li>
                <li><Link to="/platforms/threads" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Threads scheduler</Link></li>
                <li><Link to="/platforms/pinterest" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Pinterest scheduler</Link></li>
              </ul>
            </div>

            {/* Column 4: FREE TOOLS */}
            <div>
              <h3 className="text-sm font-bold text-gray-900 mb-8 uppercase tracking-wider">Free Tools</h3>
              <ul className="space-y-4">
                <li><Link to="/tools/growth-guide" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Growth Guide</Link></li>
                <li><Link to="/tools/instagram-grid" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Instagram Grid Maker</Link></li>
                <li><Link to="/tools/carousel-splitter" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Instagram Carousel Splitter</Link></li>
                <li><Link to="/tools/handle-checker" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Instagram Handle Checker</Link></li>
                <li><Link to="/tools/tiktok-username" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">TikTok Username Checker</Link></li>
                <li><Link to="/tools/tiktok-caption" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">TikTok Caption Generator</Link></li>
                <li><Link to="/tools/linkedin-formatter" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">LinkedIn Text Formatter</Link></li>
                <li><Link to="/tools/youtube-title" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">YouTube Title Checker</Link></li>
                <li><Link to="/tools/youtube-tags" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">YouTube Tag Generator</Link></li>
              </ul>
            </div>

            {/* Column 5: RESOURCES */}
            <div>
              <h3 className="text-sm font-bold text-gray-900 mb-8 uppercase tracking-wider">Resources</h3>
              <ul className="space-y-4">
                <li><a href="/resources/social-media-image-guide" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Social Media Image Guide</a></li>
                <li><a href="/resources/social-media-video-guide" target="_blank" rel="noopener noreferrer" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Social Media Video Guide</a></li>
              </ul>
            </div>

            {/* Column 6: LEGAL */}
            <div>
              <h3 className="text-sm font-bold text-gray-900 mb-8 uppercase tracking-wider">Legal</h3>
              <ul className="space-y-4">
                <li><Link to="/terms" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Terms of services</Link></li>
                <li><Link to="/privacy" className="text-sm text-gray-600 hover:text-indigo-600 transition-colors">Privacy policy</Link></li>
              </ul>
            </div>
          </div>
        </div>
      </footer>
      <SupportPopup isOpen={isSupportOpen} onClose={() => setIsSupportOpen(false)} />
    </>
  );
};

export default Footer;
