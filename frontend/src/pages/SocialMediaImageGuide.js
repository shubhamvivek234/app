import React from 'react';
import { Link } from 'react-router-dom';
import { FaInstagram, FaFacebook, FaTwitter, FaLinkedin, FaYoutube, FaPinterest, FaThreads } from 'react-icons/fa6';
import { SiBluesky, SiTiktok } from 'react-icons/si';
import Footer from '@/components/Footer';

const SocialMediaImageGuide = () => {
  const scrollToSection = (id) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const platforms = [
    { id: 'instagram', name: 'Instagram', icon: FaInstagram, color: 'text-pink-500', bg: 'bg-pink-500' },
    { id: 'facebook', name: 'Facebook', icon: FaFacebook, color: 'text-blue-600', bg: 'bg-blue-600' },
    { id: 'twitter', name: 'Twitter/X', icon: FaTwitter, color: 'text-black', bg: 'bg-black' },
    { id: 'linkedin', name: 'LinkedIn', icon: FaLinkedin, color: 'text-blue-700', bg: 'bg-blue-700' },
    { id: 'tiktok', name: 'TikTok', icon: SiTiktok, color: 'text-black', bg: 'bg-black' },
    { id: 'youtube', name: 'YouTube', icon: FaYoutube, color: 'text-red-600', bg: 'bg-red-600' },
    { id: 'pinterest', name: 'Pinterest', icon: FaPinterest, color: 'text-red-500', bg: 'bg-red-500' },
    { id: 'threads', name: 'Threads', icon: FaThreads, color: 'text-black', bg: 'bg-black' },
    { id: 'bluesky', name: 'Bluesky', icon: SiBluesky, color: 'text-blue-400', bg: 'bg-blue-400' },
  ];

  const AspectBox = ({ width, height, label, subLabel, color = 'bg-gray-100' }) => {
    const aspectRatio = height / width;
    const isVertical = aspectRatio > 1;
    const isSquare = Math.abs(aspectRatio - 1) < 0.1;
    const boxHeight = isSquare ? 'h-16' : isVertical ? 'h-24' : 'h-12';
    return (
      <div className="flex flex-col items-center">
        <div className={`${boxHeight} ${color} rounded-lg flex items-center justify-center mb-2 shadow-sm border border-gray-200`} style={{ width: '80px' }}>
          {isSquare && <div className="w-10 h-10 bg-gray-300 rounded-sm" />}
          {isVertical && <div className="w-8 h-14 bg-gray-300 rounded-sm" />}
          {!isSquare && !isVertical && <div className="w-14 h-6 bg-gray-300 rounded-sm" />}
        </div>
        <span className="text-xs font-medium text-gray-700">{label}</span>
        {subLabel && <span className="text-xs text-gray-400">{subLabel}</span>}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-100 shadow-sm sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <Link to="/" className="flex items-center space-x-2">
              <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                <span className="text-white font-bold text-lg">C</span>
              </div>
              <span className="text-xl font-semibold text-gray-900">SocialEntangler</span>
            </Link>
            <div className="flex items-center gap-4">
              <Link to="/resources/social-media-video-guide" className="text-sm text-gray-600 hover:text-indigo-600 font-medium">
                Video Guide →
              </Link>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">Social Media Image Size Guide</h1>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">Complete image specifications for all major social media platforms. Updated for 2026.</p>
        </div>

        <div className="flex flex-wrap justify-center gap-2 mb-12">
          {platforms.map((platform) => (
            <button
              key={platform.id}
              onClick={() => scrollToSection(platform.id)}
              className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-full text-sm font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition-all shadow-sm"
            >
              {platform.icon && <platform.icon className={platform.color} />}
              {platform.name}
            </button>
          ))}
        </div>

        {/* Quick Reference Table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden mb-12">
          <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Quick Reference</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Platform</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Profile</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Cover</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Feed Post</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Story</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Link Preview</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {[
                  { platform: 'Instagram', profile: '320×320', cover: '—', feed: '1080×1350', story: '1080×1920', link: '—' },
                  { platform: 'Facebook', profile: '320×320', cover: '851×315', feed: '1080×1350', story: '1080×1920', link: '1200×630' },
                  { platform: 'Twitter/X', profile: '400×400', cover: '1500×500', feed: '1080×1350', story: '—', link: '1200×630' },
                  { platform: 'LinkedIn', profile: '400×400', cover: '1584×396', feed: '1080×1350', story: '—', link: '1200×627' },
                  { platform: 'TikTok', profile: '200×200', cover: '—', feed: '1080×1920', story: '1080×1920', link: '—' },
                  { platform: 'YouTube', profile: '800×800', cover: '2560×1440', feed: '1280×720', story: '—', link: '—' },
                  { platform: 'Pinterest', profile: '165×165', cover: '800×450', feed: '1000×1500', story: '—', link: '—' },
                  { platform: 'Threads', profile: '320×320', cover: '—', feed: 'Any', story: '—', link: '1200×600' },
                  { platform: 'Bluesky', profile: '400×400', cover: '1500×500', feed: 'Any', story: '—', link: '1200×627' },
                ].map((row, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{row.platform}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{row.profile}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{row.cover}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{row.feed}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{row.story}</td>
                    <td className="px-4 py-3 text-gray-600 font-mono text-xs">{row.link}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Instagram Section */}
        <section id="instagram" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-purple-500 via-pink-500 to-orange-400 flex items-center justify-center">
                <FaInstagram className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Instagram</h2>
                <p className="text-sm text-gray-500">Profile, Feed, Stories, Reels</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="320×320" color="bg-pink-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 320×320 pixels</p>
                  <p className="text-xs text-gray-500">Displayed at 110×110. Cropped to circle. Upload larger for best quality.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={4} height={5} label="Feed Post" subLabel="1080×1350" color="bg-pink-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1080×1350 pixels (4:5)</p>
                  <p className="text-xs text-gray-500">Best for engagement. Also supports 1080×1080 (1:1) square and 1080×566 horizontal.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={9} height={16} label="Stories" subLabel="1080×1920" color="bg-pink-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1080×1920 pixels</p>
                  <p className="text-xs text-gray-500">9:16 aspect ratio. Keep 310px from top/bottom free for UI elements.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={9} height={16} label="Reels" subLabel="1080×1920" color="bg-pink-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1080×1920 pixels</p>
                  <p className="text-xs text-gray-500">Full-screen vertical video. Thumbnail should keep 480px from top/bottom clear.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Facebook Section */}
        <section id="facebook" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center">
                <FaFacebook className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Facebook</h2>
                <p className="text-sm text-gray-500">Profile, Cover, Feed, Stories</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="320×320" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 320×320 pixels</p>
                  <p className="text-xs text-gray-500">Displayed at 196×196 on mobile. Cropped to circle.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={2.7} height={1} label="Cover" subLabel="851×315" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 851×315 pixels</p>
                  <p className="text-xs text-gray-500">For Profiles & Pages. Mobile displays at 640×360. Profile pic overlaps bottom left.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={4} height={5} label="Feed Post" subLabel="1080×1350" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1080×1350 pixels</p>
                  <p className="text-xs text-gray-500">Vertical 4:5 aspect ratio performs best. Also supports square 1080×1080.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={9} height={16} label="Stories" subLabel="1080×1920" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1080×1920 pixels</p>
                  <p className="text-xs text-gray-500">Full-screen 9:16. Keep top 250px and bottom 340px free for UI.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Twitter/X Section */}
        <section id="twitter" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-black flex items-center justify-center">
                <FaTwitter className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Twitter / X</h2>
                <p className="text-sm text-gray-500">Profile, Header, Feed</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="400×400" color="bg-gray-200" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 400×400 pixels</p>
                  <p className="text-xs text-gray-500">Max file size: 2MB. Cropped to circle for regular accounts.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={3} height={1} label="Header" subLabel="1500×500" color="bg-gray-200" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1500×500 pixels</p>
                  <p className="text-xs text-gray-500">3:1 aspect ratio. Much wider than other platforms. May crop on mobile.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={16} height={9} label="Feed Image" subLabel="1600×900" color="bg-gray-200" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1600×900 pixels</p>
                  <p className="text-xs text-gray-500">Max 4 images per tweet. Min 600px width. Supports 16:9, 1:1, 4:5, 3:4.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* LinkedIn Section */}
        <section id="linkedin" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-blue-700 flex items-center justify-center">
                <FaLinkedin className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">LinkedIn</h2>
                <p className="text-sm text-gray-500">Profile, Cover, Company Page</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="400×400" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 400×400 pixels</p>
                  <p className="text-xs text-gray-500">Max 8MB for personal profiles. Cropped to circle on personal profiles.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={4} height={1} label="Cover" subLabel="1584×396" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Personal:</span> 1584×396 pixels</p>
                  <p className="text-xs text-gray-500">4:1 aspect ratio. Different for Company Pages (1128×191). Max 8MB.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={4} height={5} label="Feed Post" subLabel="1080×1350" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1080×1350 pixels</p>
                  <p className="text-xs text-gray-500">Supports 3:1 to 4:5 aspect ratios. Min 1080px width.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* TikTok Section */}
        <section id="tiktok" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-black flex items-center justify-center">
                <SiTiktok className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">TikTok</h2>
                <p className="text-sm text-gray-500">Profile, Photo Posts</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-2 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="200×200" color="bg-gray-200" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 200×200 pixels</p>
                  <p className="text-xs text-gray-500">Min 20×20 pixels. Upload larger for sharper display on high-res screens.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={9} height={16} label="Photo Posts" subLabel="1080×1920" color="bg-gray-200" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1080×1920 pixels</p>
                  <p className="text-xs text-gray-500">9:16 vertical. Can also use 4:5 or 1:1 but may have blank space.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* YouTube Section */}
        <section id="youtube" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-red-600 flex items-center justify-center">
                <FaYoutube className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">YouTube</h2>
                <p className="text-sm text-gray-500">Channel Art, Profile, Thumbnails</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="800×800" color="bg-red-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 800×800 pixels</p>
                  <p className="text-xs text-gray-500">Displayed at 98×98. Max file size 15MB. Cropped to circle.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={16} height={9} label="Banner" subLabel="2560×1440" color="bg-red-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 2560×1440 pixels</p>
                  <p className="text-xs text-gray-500">16:9 aspect ratio. Min 2048×1152. Safe area 1546×423 for text/logos.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={16} height={9} label="Thumbnail" subLabel="1280×720" color="bg-red-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1280×720 pixels</p>
                  <p className="text-xs text-gray-500">16:9 aspect ratio. Max file size 2MB. Appears on video cards.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Pinterest Section */}
        <section id="pinterest" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-red-500 flex items-center justify-center">
                <FaPinterest className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Pinterest</h2>
                <p className="text-sm text-gray-500">Profile, Cover, Pins</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="165×165" color="bg-red-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 165×165 pixels</p>
                  <p className="text-xs text-gray-500">Cropped to circle when displayed. Smallest of all platforms.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={16} height={9} label="Cover" subLabel="800×450" color="bg-red-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 800×450 pixels</p>
                  <p className="text-xs text-gray-500">16:9 horizontal. Minimum 800×450. Shows on profile page.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={2} height={3} label="Pins" subLabel="1000×1500" color="bg-red-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1000×1500 pixels</p>
                  <p className="text-xs text-gray-500">2:3 aspect ratio. Pinterest's signature vertical format. Max 20MB (web), 1GB (app).</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Threads Section */}
        <section id="threads" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-gray-900 flex items-center justify-center">
                <FaThreads className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Threads</h2>
                <p className="text-sm text-gray-500">Profile, Posts</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-2 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="320×320" color="bg-gray-200" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 320×320 pixels</p>
                  <p className="text-xs text-gray-500">Can sync with Instagram profile photo. Cropped to circle.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={3} height={4} label="Posts" subLabel="Any" color="bg-gray-200" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">No restrictions</span></p>
                  <p className="text-xs text-gray-500">Any dimensions accepted. Up to 20 images per post. Max 8MB per image.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Bluesky Section */}
        <section id="bluesky" className="mb-16 scroll-mt-20">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-5 border-b border-gray-100 flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-blue-400 flex items-center justify-center">
                <SiBluesky className="text-2xl text-white" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Bluesky</h2>
                <p className="text-sm text-gray-500">Profile, Banner, Posts</p>
              </div>
            </div>
            <div className="p-6">
              <div className="grid md:grid-cols-3 gap-6">
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Profile" subLabel="400×400" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 400×400 pixels</p>
                  <p className="text-xs text-gray-500">1:1 aspect ratio. Cropped to circle.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={3} height={1} label="Banner" subLabel="1500×500" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">Recommended:</span> 1500×500 pixels</p>
                  <p className="text-xs text-gray-500">3:1 aspect ratio. Gets cropped to 4:1 on mobile.</p>
                </div>
                <div className="bg-gray-50 rounded-xl p-5 border border-gray-200">
                  <div className="flex justify-center mb-4"><AspectBox width={1} height={1} label="Posts" subLabel="Any" color="bg-blue-100" /></div>
                  <p className="text-sm text-gray-600 mb-2"><span className="font-semibold">No restrictions</span></p>
                  <p className="text-xs text-gray-500">Any size. Max 4 images per post, 1MB each. Displayed in original dimensions.</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Tips */}
        <div className="bg-gradient-to-r from-indigo-50 to-purple-50 rounded-2xl border border-indigo-100 p-8">
          <h3 className="text-lg font-bold text-indigo-900 mb-4">Best Practices</h3>
          <div className="grid md:grid-cols-2 gap-4 text-sm text-indigo-800">
            <div className="flex items-start gap-2"><span className="text-indigo-500 mt-0.5">✓</span><span>Always upload at 1080px width - the universal standard</span></div>
            <div className="flex items-start gap-2"><span className="text-indigo-500 mt-0.5">✓</span><span>Vertical images (4:5, 9:16) perform best on mobile</span></div>
            <div className="flex items-start gap-2"><span className="text-indigo-500 mt-0.5">✓</span><span>Use JPG or PNG - universally supported</span></div>
            <div className="flex items-start gap-2"><span className="text-indigo-500 mt-0.5">✓</span><span>Keep important content centered for profile crops</span></div>
          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
};

export default SocialMediaImageGuide;
