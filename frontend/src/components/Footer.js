import React from 'react';
import { Link } from 'react-router-dom';

const Footer = () => {
  return (
    <footer className="bg-gray-50 border-t border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8">
          {/* Column 1: Logo & Description */}
          <div className="md:col-span-1">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                <span className="text-white font-bold text-lg">P</span>
              </div>
              <span className="text-xl font-semibold text-gray-900">post bridge</span>
            </div>
            <p className="text-sm text-gray-600 mb-4">
              Post content to multiple social media platforms at the same time, all-in one place. Cross posting made easy.
            </p>
            <p className="text-xs text-gray-500">
              Copyright © 2026 - All rights reserved
            </p>
          </div>

          {/* Column 2: LINKS */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase">Links</h3>
            <ul className="space-y-2">
              <li><Link to="/support" className="text-sm text-gray-600 hover:text-gray-900">Support</Link></li>
              <li><Link to="/pricing" className="text-sm text-gray-600 hover:text-gray-900">Pricing</Link></li>
              <li><Link to="/blog" className="text-sm text-gray-600 hover:text-gray-900">Blog</Link></li>
              <li><Link to="/affiliates" className="text-sm text-gray-600 hover:text-gray-900">Affiliates</Link></li>
            </ul>
          </div>

          {/* Column 3: PLATFORMS */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase">Platforms</h3>
            <ul className="space-y-2">
              <li><Link to="/platforms/twitter" className="text-sm text-gray-600 hover:text-gray-900">Twitter/X scheduler</Link></li>
              <li><Link to="/platforms/instagram" className="text-sm text-gray-600 hover:text-gray-900">Instagram scheduler</Link></li>
              <li><Link to="/platforms/linkedin" className="text-sm text-gray-600 hover:text-gray-900">LinkedIn scheduler</Link></li>
              <li><Link to="/platforms/facebook" className="text-sm text-gray-600 hover:text-gray-900">Facebook scheduler</Link></li>
              <li><Link to="/platforms/tiktok" className="text-sm text-gray-600 hover:text-gray-900">TikTok scheduler</Link></li>
              <li><Link to="/platforms/youtube" className="text-sm text-gray-600 hover:text-gray-900">YouTube scheduler</Link></li>
              <li><Link to="/platforms/bluesky" className="text-sm text-gray-600 hover:text-gray-900">Bluesky scheduler</Link></li>
              <li><Link to="/platforms/threads" className="text-sm text-gray-600 hover:text-gray-900">Threads scheduler</Link></li>
              <li><Link to="/platforms/pinterest" className="text-sm text-gray-600 hover:text-gray-900">Pinterest scheduler</Link></li>
            </ul>
          </div>

          {/* Column 4: FREE TOOLS */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase">Free Tools</h3>
            <ul className="space-y-2">
              <li><Link to="/tools/growth-guide" className="text-sm text-gray-600 hover:text-gray-900">Growth Guide</Link></li>
              <li><Link to="/tools/instagram-grid" className="text-sm text-gray-600 hover:text-gray-900">Instagram Grid Maker</Link></li>
              <li><Link to="/tools/carousel-splitter" className="text-sm text-gray-600 hover:text-gray-900">Instagram Carousel Splitter</Link></li>
              <li><Link to="/tools/handle-checker" className="text-sm text-gray-600 hover:text-gray-900">Instagram Handle Checker</Link></li>
              <li><Link to="/tools/tiktok-username" className="text-sm text-gray-600 hover:text-gray-900">TikTok Username Checker</Link></li>
              <li><Link to="/tools/tiktok-caption" className="text-sm text-gray-600 hover:text-gray-900">TikTok Caption Generator</Link></li>
              <li><Link to="/tools/linkedin-formatter" className="text-sm text-gray-600 hover:text-gray-900">LinkedIn Text Formatter</Link></li>
              <li><Link to="/tools/youtube-title" className="text-sm text-gray-600 hover:text-gray-900">YouTube Title Checker</Link></li>
              <li><Link to="/tools/youtube-tags" className="text-sm text-gray-600 hover:text-gray-900">YouTube Tag Generator</Link></li>
            </ul>
          </div>

          {/* Column 5: LEGAL */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-4 uppercase">Legal</h3>
            <ul className="space-y-2">
              <li><Link to="/terms" className="text-sm text-gray-600 hover:text-gray-900">Terms of services</Link></li>
              <li><Link to="/privacy" className="text-sm text-gray-600 hover:text-gray-900">Privacy policy</Link></li>
            </ul>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
