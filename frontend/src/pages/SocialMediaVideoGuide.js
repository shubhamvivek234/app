import React from 'react';
import { Link } from 'react-router-dom';
import Footer from '@/components/Footer';

const SocialMediaVideoGuide = () => {
  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="min-h-screen bg-offwhite">
      <nav className="bg-offwhite border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <Link to="/" className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                <span className="text-white font-bold text-lg">C</span>
              </div>
              <span className="text-xl font-semibold text-gray-900">SocialEntangler</span>
            </Link>
            <div className="flex items-center gap-4">
              <Link to="/resources/social-media-image-guide" className="text-sm text-gray-600 hover:text-indigo-600">
                ← Image Guide
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">Social Media Video Size Guide</h1>
          <p className="text-lg text-gray-600 mb-6">Complete video specifications for all major social media platforms - Updated March 2026</p>
          
          {/* Quick Navigation */}
          <div className="flex flex-wrap gap-2 mb-8">
            {['instagram', 'facebook', 'twitter', 'linkedin', 'tiktok', 'youtube', 'pinterest', 'threads', 'bluesky', 'mastodon'].map((platform) => (
              <button
                key={platform}
                onClick={() => scrollToSection(platform)}
                className="px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-600 transition-colors capitalize"
              >
                {platform}
              </button>
            ))}
          </div>
        </div>

        {/* Quick Reference Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-12">
          <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Quick Reference</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Platform</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Max Size</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Resolution</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Aspect Ratio</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Max Length</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Formats</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {[
                  { platform: 'Instagram Reels', size: '300MB', res: '1080×1920', ratio: '9:16', length: '15 min', formats: 'MP4, MOV' },
                  { platform: 'Instagram Stories', size: '4GB', res: '1080×1920', ratio: '9:16', length: '60 sec', formats: 'MP4, MOV, GIF' },
                  { platform: 'Facebook Reels', size: '1GB', res: '1080×1920', ratio: '9:16', length: '90 sec', formats: 'MP4, MOV, AVI, M4V' },
                  { platform: 'Twitter/X', size: '1GB', res: '1280×720', ratio: '16:9', length: '140 sec', formats: 'MP4, MOV, AVI, M4V' },
                  { platform: 'LinkedIn', size: '200MB', res: '1080×1080', ratio: '1:1-16:9', length: '10 min', formats: 'MP4, MOV, AVI, M4V' },
                  { platform: 'TikTok', size: '1GB', res: '1080×1920', ratio: '9:16', length: '10 min', formats: 'MOV, MP4, WEBM' },
                  { platform: 'YouTube Shorts', size: '10GB', res: '1080×1920', ratio: '9:16', length: '3 min', formats: 'MOV, MP4, MPG, AVI, WEBM' },
                  { platform: 'Pinterest', size: '2GB', res: '1000×1500', ratio: '2:3', length: '15 min', formats: 'MP4, MOV, AVI, M4V' },
                  { platform: 'Threads', size: '1GB', res: '1920 width', ratio: '9:16', length: '5 min', formats: 'MP4, MOV' },
                  { platform: 'Bluesky', size: '100MB', res: '—', ratio: '9:16', length: '3 min', formats: 'MP4, MOV' },
                ].map((row, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{row.platform}</td>
                    <td className="px-4 py-3 text-gray-600">{row.size}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{row.res}</td>
                    <td className="px-4 py-3 text-gray-600">{row.ratio}</td>
                    <td className="px-4 py-3 text-gray-600">{row.length}</td>
                    <td className="px-4 py-3 text-gray-600 text-xs">{row.formats}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Section 1: Instagram Video */}
        <section id="instagram" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-purple-500 to-pink-500 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">Instagram Video</h2>
            </div>
            <div className="p-6 space-y-8">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Instagram Reels</h3>
                <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Size</p>
                    <p className="font-mono text-gray-900">1080 × 1920</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                    <p className="font-mono text-gray-900">300 MB</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Max Length</p>
                    <p className="font-mono text-gray-900">3 sec - 15 min</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Frame Rate</p>
                    <p className="font-mono text-gray-900">23-60 FPS</p>
                  </div>
                </div>
                <p className="text-sm text-gray-600 mt-4">Format: MP4, MOV • Video Bitrate: Below 25 Mbps • Audio Bitrate: Below 128 kbps</p>
              </div>

              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Instagram Stories</h3>
                <div className="grid md:grid-cols-3 gap-4">
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Size</p>
                    <p className="font-mono text-gray-900">1080 × 1920</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Max Length</p>
                    <p className="font-mono text-gray-900">60 seconds</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                    <p className="font-mono text-gray-900">4 GB</p>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Instagram Feed (Carousels)</h3>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-2">Size: 1080 × 1080 or 1080 × 1350 pixels • Aspect Ratio: 9:16</p>
                  <p className="text-sm text-gray-500 mb-2">Max Length: 3 sec to 60 min • Max File Size: 4 GB</p>
                  <p className="text-xs text-gray-400">Note: Carousel videos are NOT Reels - they don't appear in Reels tab</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: Facebook Video */}
        <section id="facebook" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">Facebook Video</h2>
            </div>
            <div className="p-6 space-y-6">
              <div className="grid md:grid-cols-3 gap-4">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Feed Video Size</p>
                  <p className="font-mono text-gray-900">1080 × 1920</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                  <p className="font-mono text-gray-900">1 GB</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Format</p>
                  <p className="font-mono text-gray-900">MP4, MOV, AVI, M4V</p>
                </div>
              </div>
              <div className="bg-yellow-50 border border-yellow-100 rounded-lg p-4">
                <p className="text-sm text-yellow-800">Any video with 9:16 aspect ratio uploaded to Facebook is automatically published as a Reel.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Section 3: Twitter/X Video */}
        <section id="twitter" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-black to-gray-800 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">Twitter/X Video</h2>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Landscape</p>
                  <p className="font-mono text-gray-900">1280 × 720</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Vertical</p>
                  <p className="font-mono text-gray-900">720 × 1280</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Square</p>
                  <p className="font-mono text-gray-900">1080 × 1080</p>
                </div>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600">Max Length: 140 seconds (standard) • Max File Size: 512 MB (native) / 1 GB (via Buffer)</p>
                <p className="text-xs text-gray-500 mt-2">Note: Videos do not autoplay - users must click to play. Max 4 videos per tweet.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Section 4: LinkedIn Video */}
        <section id="linkedin" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-700 to-blue-800 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">LinkedIn Video</h2>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Aspect Ratio</p>
                  <p className="font-mono text-gray-900">9:16 to 16:9</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max Length</p>
                  <p className="font-mono text-gray-900">10 minutes</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                  <p className="font-mono text-gray-900">75 KB - 200 MB</p>
                </div>
              </div>
              <p className="text-sm text-gray-600">Format: MP4, MOV, AVI, M4V • Videos auto-play in feed • Custom thumbnails not supported</p>
            </div>
          </div>
        </section>

        {/* Section 5: TikTok Video */}
        <section id="tiktok" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-black via-gray-900 to-pink-500 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">TikTok Video</h2>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Size</p>
                  <p className="font-mono text-gray-900">1080 × 1920</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Aspect Ratio</p>
                  <p className="font-mono text-gray-900">9:16</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max Length</p>
                  <p className="font-mono text-gray-900">3 sec - 10 min</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                  <p className="font-mono text-gray-900">1 GB</p>
                </div>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600">Format: MOV, MP4, WEBM • Frame Rate: 23-60 FPS • Min Dimensions: 360 × 360 pixels</p>
                <p className="text-xs text-gray-500 mt-2">Description Max: 150 characters • Videos auto-play in feed</p>
              </div>
            </div>
          </div>
        </section>

        {/* Section 6: YouTube Shorts */}
        <section id="youtube" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-red-600 to-red-700 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">YouTube Video</h2>
            </div>
            <div className="p-6 space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">YouTube Shorts</h3>
                <div className="grid md:grid-cols-3 gap-4">
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Max Length</p>
                    <p className="font-mono text-gray-900">3 minutes</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                    <p className="font-mono text-gray-900">10 GB</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4">
                    <p className="text-sm text-gray-500 mb-1">Aspect Ratio</p>
                    <p className="font-mono text-gray-900">9:16</p>
                  </div>
                </div>
              </div>
              <div className="bg-yellow-50 border border-yellow-100 rounded-lg p-4">
                <p className="text-sm text-yellow-800">Custom thumbnails are not supported through Buffer - must be uploaded directly on YouTube.</p>
              </div>
            </div>
          </div>
        </section>

        {/* Section 7: Pinterest Video */}
        <section id="pinterest" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-red-500 to-red-600 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">Pinterest Video</h2>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Recommended Size</p>
                  <p className="font-mono text-gray-900">1000 × 1500</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max Length</p>
                  <p className="font-mono text-gray-900">4 sec - 15 min</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                  <p className="font-mono text-gray-900">2 GB</p>
                </div>
              </div>
              <p className="text-sm text-gray-600">Aspect Ratio: 1:1 (square) or 2:3, 4:5, 9:16 (vertical) • Videos auto-play by default</p>
            </div>
          </div>
        </section>

        {/* Section 8: Threads Video */}
        <section id="threads" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-gray-800 to-gray-900 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">Threads Video</h2>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max Width</p>
                  <p className="font-mono text-gray-900">1920 pixels</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max Length</p>
                  <p className="font-mono text-gray-900">5 minutes</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                  <p className="font-mono text-gray-900">1 GB</p>
                </div>
              </div>
              <p className="text-sm text-gray-600">Format: MP4, MOV • Frame Rate: 23-60 FPS • Video Bitrate: 25 Mbps max • Custom thumbnails not supported</p>
            </div>
          </div>
        </section>

        {/* Section 9: Bluesky Video */}
        <section id="bluesky" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-blue-400 to-blue-600 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">Bluesky Video</h2>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max Length</p>
                  <p className="font-mono text-gray-900">3 minutes</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                  <p className="font-mono text-gray-900">100 MB</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Daily Limit</p>
                  <p className="font-mono text-gray-900">25 videos or 10 GB</p>
                </div>
              </div>
              <p className="text-sm text-gray-600">Format: MP4, MOV • Videos auto-play in feed • Custom thumbnails not supported</p>
            </div>
          </div>
        </section>

        {/* Section 10: Mastodon Video */}
        <section id="mastodon" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="bg-gradient-to-r from-purple-600 to-purple-700 px-6 py-4">
              <h2 className="text-xl font-semibold text-white">Mastodon Video</h2>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-4 mb-6">
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Max File Size</p>
                  <p className="font-mono text-gray-900">40 MB</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Format</p>
                  <p className="font-mono text-gray-900">MP4, M4V, MOV, WebM</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-4">
                  <p className="text-sm text-gray-500 mb-1">Frame Rate</p>
                  <p className="font-mono text-gray-900">Max 60 FPS</p>
                </div>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-sm text-gray-600">Videos transcoded to H.264 MP4 with max bitrate 1300 kbps</p>
                <p className="text-xs text-gray-500 mt-2">Note: Videos do NOT auto-play in feed • Custom thumbnails not supported</p>
              </div>
            </div>
          </div>
        </section>

        {/* General Tips */}
        <div className="bg-indigo-50 rounded-xl border border-indigo-100 p-6">
          <h3 className="text-lg font-semibold text-indigo-900 mb-4">General Tips for Video</h3>
          <ul className="space-y-2 text-sm text-indigo-800">
            <li>• Always use MP4 with H.264 codec - universally supported across all platforms</li>
            <li>• 1080 × 1920 for vertical video - standard for Stories, Reels, TikTok, and Shorts</li>
            <li>• Keep videos under 25 Mbps bitrate - some platforms compress aggressively</li>
            <li>• Audio bitrate 128 kbps or lower - Instagram and Threads enforce this limit</li>
            <li>• Frame rate 24-30 FPS is sufficient - higher increases file size without noticeable quality improvement</li>
            <li>• Custom thumbnails must be selected from video frames on most platforms via Buffer</li>
            <li>• Bluesky has daily limits - 25 videos per day or 10 GB total, whichever comes first</li>
          </ul>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default SocialMediaVideoGuide;
