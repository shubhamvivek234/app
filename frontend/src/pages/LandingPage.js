import React, { useState, useEffect } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { FaTwitter, FaLinkedin, FaInstagram, FaCalendarAlt, FaRocket, FaMagic, FaChevronDown, FaYoutube, FaFacebook, FaTiktok } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import Footer from '@/components/Footer';
import SupportPopup from '@/components/SupportPopup';
import SocialEntanglerLogo from '@/components/SocialEntanglerLogo';

const LandingPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const [showToolsDropdown, setShowToolsDropdown] = useState(false);
  const [isSupportOpen, setIsSupportOpen] = useState(false);

  useEffect(() => {
    if (location.hash) {
      const sectionId = location.hash.replace('#', '');
      const element = document.getElementById(sectionId);
      if (element) {
        setTimeout(() => {
          element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 100);
      }
    }
  }, [location]);

  const scrollToSection = (sectionId) => {
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="min-h-screen bg-white">
      {/* New Navigation Header */}
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            {/* Logo */}
            <div className="flex items-center cursor-pointer" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
              <SocialEntanglerLogo size="large" />
            </div>

            {/* Navigation Menu */}
            <div className="hidden md:flex items-center space-x-8">
              <button onClick={() => scrollToSection('pricing')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                Pricing
              </button>
              <button onClick={() => scrollToSection('reviews')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                Reviews
              </button>
              <button onClick={() => scrollToSection('features')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                Features
              </button>
              <button onClick={() => scrollToSection('platforms')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                Platforms
              </button>
              <button onClick={() => navigate('/agent-docs')} className="text-indigo-600 hover:text-indigo-700 text-sm font-semibold">
                Connect with AI Agent
              </button>
              <button onClick={() => scrollToSection('faq')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                FAQ
              </button>
              <button onClick={() => setIsSupportOpen(true)} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                Support
              </button>
            </div>

            {/* User Profile or Auth Buttons */}
            <div className="flex items-center space-x-4">
              {user ? (
                <div className="flex items-center space-x-3 bg-gray-100 rounded-full px-4 py-2 cursor-pointer" onClick={() => navigate('/dashboard')}>
                  <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                    <span className="text-white text-sm font-semibold">{user.name?.charAt(0) || 'U'}</span>
                  </div>
                  <span className="text-sm font-medium text-gray-900">{user.name}</span>
                </div>
              ) : (
                <>
                  <Button variant="ghost" onClick={() => navigate('/login')} className="text-gray-600">
                    Login
                  </Button>
                  <Button onClick={() => navigate('/signup')} className="bg-green-500 hover:bg-green-600">
                    Get Started
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section id="hero" className="py-20 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="space-y-8">
              <div>
                <h1 className="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight text-slate-900 leading-tight">
                  Post to all your social accounts from one dashboard
                </h1>
              </div>
              <p className="text-lg leading-relaxed text-slate-600">
                Schedule and publish content across Twitter, Instagram, and LinkedIn simultaneously. Save hours every week with AI-powered content creation.
              </p>
              <div className="flex gap-4">
                <Button
                  size="lg"
                  onClick={() => navigate('/signup')}
                  data-testid="hero-cta-button"
                  className="text-base px-8"
                >
                  Try it for free
                </Button>
              </div>
              <div className="flex items-center gap-3 text-sm text-slate-500">
                <div className="flex -space-x-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-400 to-purple-400 border-2 border-white"
                    />
                  ))}
                </div>
                <span>Used by 1,000+ content creators</span>
              </div>
            </div>
            <div className="relative">
              <div className="aspect-video rounded-lg overflow-hidden shadow-xl border border-border">
                <iframe
                  className="w-full h-full"
                  src="https://www.youtube.com/embed/M7lc1UVf-VE?rel=0"
                  title="SocialEntangler Demo"
                  frameBorder="0"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                ></iframe>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section - Post-Bridge Inspired */}
      <section className="py-10 border-y border-gray-100 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row justify-center items-center gap-8 md:gap-16 text-center">
            <div>
              <p className="text-3xl font-bold text-slate-900">1,400+</p>
              <p className="text-sm text-slate-500 uppercase tracking-wide">Happy Users</p>
            </div>
            <div className="hidden md:block w-px h-12 bg-gray-200"></div>
            <div>
              <p className="text-3xl font-bold text-slate-900">50k+</p>
              <p className="text-sm text-slate-500 uppercase tracking-wide">Posts Published</p>
            </div>
            <div className="hidden md:block w-px h-12 bg-gray-200"></div>
            <div>
              <p className="text-3xl font-bold text-slate-900">10+</p>
              <p className="text-sm text-slate-500 uppercase tracking-wide">Platforms Supported</p>
            </div>
          </div>
        </div>
      </section>

      {/* How it Works Section */}
      <section className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-slate-900 mb-4">
              From idea to published in minutes
            </h2>
            <p className="text-lg text-slate-600">
              A simple workflow designed for content creators
            </p>
          </div>
          <div className="grid md:grid-cols-3 gap-8 relative">
            {/* Connecting Line (Desktop) */}
            <div className="hidden md:block absolute top-12 left-[16%] right-[16%] h-0.5 bg-gradient-to-r from-indigo-200 via-purple-200 to-pink-200 -z-10"></div>

            {/* Step 1 */}
            <div className="relative text-center bg-white p-6">
              <div className="w-24 h-24 mx-auto bg-indigo-50 rounded-full flex items-center justify-center mb-6 border-4 border-white shadow-sm">
                <span className="text-3xl font-bold text-indigo-600">1</span>
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">Connect</h3>
              <p className="text-slate-600">Link your social media profiles. We support all major platforms including Instagram, TikTok, and YouTube.</p>
            </div>

            {/* Step 2 */}
            <div className="relative text-center bg-white p-6">
              <div className="w-24 h-24 mx-auto bg-purple-50 rounded-full flex items-center justify-center mb-6 border-4 border-white shadow-sm">
                <span className="text-3xl font-bold text-purple-600">2</span>
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">Create</h3>
              <p className="text-slate-600">Upload your videos or images. Use our AI tools to generate engaging captions and hashtags instantly.</p>
            </div>

            {/* Step 3 */}
            <div className="relative text-center bg-white p-6">
              <div className="w-24 h-24 mx-auto bg-pink-50 rounded-full flex items-center justify-center mb-6 border-4 border-white shadow-sm">
                <span className="text-3xl font-bold text-pink-600">3</span>
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">Schedule</h3>
              <p className="text-slate-600">Choose a time or let us pick the best time to post. Sit back and watch your engagement grow.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Platforms Section */}
      <section id="platforms" className="py-16 bg-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-slate-900 mb-4">
              Post to all platforms instantly
            </h2>
            <p className="text-base leading-relaxed text-slate-600">
              Connect your social media accounts and publish everywhere with a single click
            </p>
          </div>
          <div className="flex justify-center items-center gap-8 flex-wrap">
            <div className="flex items-center gap-3 px-6 py-4 bg-white rounded-lg border border-border shadow-sm">
              <FaTwitter className="text-3xl text-blue-400" />
              <span className="font-medium text-slate-900">Twitter/X</span>
            </div>
            <div className="flex items-center gap-3 px-6 py-4 bg-white rounded-lg border border-border shadow-sm">
              <FaInstagram className="text-3xl text-pink-500" />
              <span className="font-medium text-slate-900">Instagram</span>
            </div>
            <div className="flex items-center gap-3 px-6 py-4 bg-white rounded-lg border border-border shadow-sm">
              <FaLinkedin className="text-3xl text-blue-600" />
              <span className="font-medium text-slate-900">LinkedIn</span>
            </div>
            <div className="flex items-center gap-3 px-6 py-4 bg-white rounded-lg border border-border shadow-sm">
              <FaFacebook className="text-3xl text-blue-600" />
              <span className="font-medium text-slate-900">Facebook</span>
            </div>
            <div className="flex items-center gap-3 px-6 py-4 bg-white rounded-lg border border-border shadow-sm">
              <FaYoutube className="text-3xl text-red-600" />
              <span className="font-medium text-slate-900">YouTube</span>
            </div>
            <div className="flex items-center gap-3 px-6 py-4 bg-white rounded-lg border border-border shadow-sm">
              <FaTiktok className="text-3xl text-black" />
              <span className="font-medium text-slate-900">TikTok</span>
            </div>
          </div>
        </div>
      </section>

      {/* Detailed Features Section (Zig-Zag) */}
      <section id="features" className="py-20 overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-24">

          {/* Feature 1 */}
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
            <div className="space-y-6">
              <div className="w-12 h-12 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FaRocket className="text-2xl text-indigo-600" />
              </div>
              <h3 className="text-3xl font-bold tracking-tight text-slate-900">
                Manage everything in one place
              </h3>
              <p className="text-lg text-slate-600 leading-relaxed">
                Stop switching between tabs. View, edit, and schedule posts for all your accounts from a single, intuitive dashboard.
                Streamline your workflow and save hours of manual work every week.
              </p>
              <ul className="space-y-3">
                {['Single Upload Interface', 'Unified Content Calendar', 'Drag & Drop Scheduling'].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-slate-700">
                    <div className="w-2 h-2 rounded-full bg-indigo-500"></div>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="relative">
              <div
                className="rounded-2xl overflow-hidden shadow-xl border border-gray-100 bg-slate-50 relative aspect-square flex items-center justify-center p-8"
              >
                {/* Central Dashboard Hub */}
                <div className="w-full max-w-sm bg-white rounded-xl shadow-lg border border-gray-200 p-4 z-10 relative">
                  <div className="flex items-center gap-2 mb-4 border-b border-gray-100 pb-2">
                    <div className="w-3 h-3 rounded-full bg-red-400"></div>
                    <div className="w-3 h-3 rounded-full bg-yellow-400"></div>
                    <div className="w-3 h-3 rounded-full bg-green-400"></div>
                  </div>
                  <div className="space-y-3">
                    <div className="h-4 bg-gray-100 rounded w-3/4"></div>
                    <div className="h-24 bg-indigo-50 rounded-lg flex items-center justify-center border-2 border-dashed border-indigo-200">
                      <span className="text-xs text-indigo-400 font-medium">Drag & Drop Content</span>
                    </div>
                    <div className="flex gap-2">
                      <div className="h-8 bg-gray-100 rounded w-1/3"></div>
                      <div className="h-8 bg-indigo-600 rounded w-1/3"></div>
                    </div>
                  </div>

                  {/* Floating Connection Lines (Implied by proximity) */}
                </div>

                {/* Floating Social Icons with Animation */}
                <div className="absolute top-12 left-12 animate-bounce duration-[3000ms] shadow-lg rounded-full p-3 bg-white border border-gray-100 z-20">
                  <FaTwitter className="text-2xl text-blue-400" />
                </div>
                <div className="absolute top-20 right-12 animate-bounce delay-700 duration-[4000ms] shadow-lg rounded-full p-3 bg-white border border-gray-100 z-20">
                  <FaInstagram className="text-2xl text-pink-500" />
                </div>
                <div className="absolute bottom-24 left-16 animate-bounce delay-1000 duration-[3500ms] shadow-lg rounded-full p-3 bg-white border border-gray-100 z-20">
                  <FaLinkedin className="text-2xl text-blue-700" />
                </div>
                <div className="absolute bottom-12 right-20 animate-bounce delay-500 duration-[4500ms] shadow-lg rounded-full p-3 bg-white border border-gray-100 z-20">
                  <FaYoutube className="text-2xl text-red-600" />
                </div>

                {/* Background Decor */}
                <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/50 via-purple-50/50 to-pink-50/50 z-0"></div>
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[120%] bg-white/30 rounded-full blur-3xl -z-10"></div>
              </div>
            </div>
          </div>

          {/* Feature 2 */}
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
            <div className="order-2 lg:order-1 relative">
              <div className="aspect-square bg-gradient-to-br from-purple-50 to-pink-50 rounded-2xl border border-purple-100 p-8 flex items-center justify-center shadow-lg relative overflow-hidden">
                {/* Floating Elements (Background) */}
                <div className="absolute top-10 left-10 text-purple-200 animate-pulse">
                  <FaMagic className="text-4xl" />
                </div>
                <div className="absolute bottom-10 right-10 text-pink-200 animate-bounce duration-[3000ms]">
                  <FaRocket className="text-3xl" />
                </div>

                {/* Main Card: Magic Editor */}
                <div className="w-full max-w-sm bg-white rounded-xl shadow-xl border border-purple-100 p-6 z-10 relative">
                  <div className="flex items-center justify-between mb-4 border-b border-gray-50 pb-2">
                    <span className="text-xs font-semibold text-purple-600 uppercase tracking-wider">AI Assistant</span>
                    <div className="flex gap-1">
                      <div className="w-2 h-2 rounded-full bg-gray-200"></div>
                      <div className="w-2 h-2 rounded-full bg-gray-200"></div>
                    </div>
                  </div>

                  {/* Typed Text Simulation */}
                  <div className="space-y-3">
                    <div className="h-2 bg-gray-100 rounded w-full"></div>
                    <div className="h-2 bg-gray-100 rounded w-5/6"></div>
                    <div className="h-2 bg-gray-100 rounded w-4/6"></div>
                  </div>

                  {/* Magic Transformation Effect */}
                  <div className="my-4 flex justify-center">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 flex items-center justify-center shadow-lg animate-pulse">
                      <FaMagic className="text-white text-lg" />
                    </div>
                  </div>

                  {/* Polished Result */}
                  <div className="bg-purple-50 rounded-lg p-3 border border-purple-100">
                    <div className="space-y-2">
                      <div className="h-2 bg-purple-200 rounded w-full"></div>
                      <div className="h-2 bg-purple-200 rounded w-11/12"></div>
                    </div>
                  </div>
                </div>

                {/* Decor */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[140%] h-[140%] bg-white/20 rounded-full blur-3xl -z-10"></div>
              </div>
            </div>
            <div className="order-1 lg:order-2 space-y-6">
              <div className="w-12 h-12 rounded-lg bg-purple-100 flex items-center justify-center">
                <FaMagic className="text-2xl text-purple-600" />
              </div>
              <h3 className="text-3xl font-bold tracking-tight text-slate-900">
                AI that writes like you
              </h3>
              <p className="text-lg text-slate-600 leading-relaxed">
                Struggling with writer's block? Our AI analyzes your content and suggests engaging captions and trending hashtags tailored to each platform's audience.
              </p>
              <ul className="space-y-3">
                {['Smart Caption Generator', 'Hashtag Recommendations', 'Tone of Voice Customization'].map((item, i) => (
                  <li key={i} className="flex items-center gap-3 text-slate-700">
                    <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>

        </div>
      </section>

      {/* Reviews Section */}
      <section id="reviews" className="py-20 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-slate-900 mb-4">
              Loved by creators worldwide
            </h2>
            <p className="text-lg text-slate-600">
              Join thousands of users who trust SocialEntangler to manage their social presence
            </p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {/* Review 1 */}
            <div className="bg-white p-8 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center gap-1 text-yellow-400 mb-4">
                {[...Array(5)].map((_, i) => (
                  <FaRocket key={i} className="text-sm" />
                ))}
              </div>
              <p className="text-slate-700 mb-6 leading-relaxed">
                "SocialEntangler has completely transformed how I manage my social media. I used to spend hours copy-pasting content, now it takes seconds."
              </p>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 font-bold">
                  JS
                </div>
                <div>
                  <h4 className="font-semibold text-slate-900">James Smith</h4>
                  <p className="text-sm text-slate-500">Content Creator</p>
                </div>
              </div>
            </div>

            {/* Review 2 */}
            <div className="bg-white p-8 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center gap-1 text-yellow-400 mb-4">
                {[...Array(5)].map((_, i) => (
                  <FaRocket key={i} className="text-sm" />
                ))}
              </div>
              <p className="text-slate-700 mb-6 leading-relaxed">
                "The AI content generation is a game changer. It helps me come up with captions that actually convert. Highly recommended!"
              </p>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-pink-100 flex items-center justify-center text-pink-600 font-bold">
                  SJ
                </div>
                <div>
                  <h4 className="font-semibold text-slate-900">Sarah Johnson</h4>
                  <p className="text-sm text-slate-500">Digital Marketer</p>
                </div>
              </div>
            </div>

            {/* Review 3 */}
            <div className="bg-white p-8 rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex items-center gap-1 text-yellow-400 mb-4">
                {[...Array(5)].map((_, i) => (
                  <FaRocket key={i} className="text-sm" />
                ))}
              </div>
              <p className="text-slate-700 mb-6 leading-relaxed">
                "Best value for money in the market. The ability to schedule months of content in advance is incredible."
              </p>
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center text-green-600 font-bold">
                  MR
                </div>
                <div>
                  <h4 className="font-semibold text-slate-900">Mike Ross</h4>
                  <p className="text-sm text-slate-500">Agency Owner</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-20 bg-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-slate-900 mb-4">
              Simple, transparent pricing
            </h2>
            <p className="text-base leading-relaxed text-slate-600">
              Start free, upgrade when you're ready
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
            <div className="bg-white rounded-lg border border-border p-8 space-y-6">
              <div>
                <h3 className="text-2xl font-semibold text-slate-900">Monthly</h3>
                <div className="mt-4 flex items-baseline">
                  <span className="text-4xl font-semibold text-slate-900">₹500</span>
                  <span className="ml-2 text-slate-600">/month</span>
                </div>
              </div>
              <ul className="space-y-3">
                <li className="flex items-center gap-2 text-slate-600">
                  <span className="w-5 h-5 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 text-xs">✓</span>
                  Connect 3 social accounts
                </li>
                <li className="flex items-center gap-2 text-slate-600">
                  <span className="w-5 h-5 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 text-xs">✓</span>
                  Unlimited posts
                </li>
                <li className="flex items-center gap-2 text-slate-600">
                  <span className="w-5 h-5 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 text-xs">✓</span>
                  Schedule posts
                </li>
                <li className="flex items-center gap-2 text-slate-600">
                  <span className="w-5 h-5 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 text-xs">✓</span>
                  AI content generation
                </li>
              </ul>
              <Button
                className="w-full"
                onClick={() => navigate('/signup')}
                data-testid="pricing-monthly-button"
              >
                Get Started
              </Button>
            </div>
            <div className="bg-indigo-600 text-white rounded-lg border border-indigo-700 p-8 space-y-6 relative">
              <div className="absolute -top-3 right-8 bg-rose-500 text-white text-xs font-medium px-3 py-1 rounded-full">
                Best Value
              </div>
              <div>
                <h3 className="text-2xl font-semibold">Yearly</h3>
                <div className="mt-4 flex items-baseline">
                  <span className="text-4xl font-semibold">₹3,000</span>
                  <span className="ml-2 text-indigo-200">/year</span>
                </div>
                <p className="text-sm text-indigo-200 mt-2">Save ₹3,000 per year</p>
              </div>
              <ul className="space-y-3">
                <li className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center text-xs">✓</span>
                  Everything in Monthly
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center text-xs">✓</span>
                  50% discount
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center text-xs">✓</span>
                  Priority support
                </li>
                <li className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center text-xs">✓</span>
                  Early access to features
                </li>
              </ul>
              <Button
                className="w-full bg-white text-indigo-600 hover:bg-gray-100"
                onClick={() => navigate('/signup')}
                data-testid="pricing-yearly-button"
              >
                Get Started
              </Button>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section id="faq" className="py-20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-slate-900 mb-4">
              Frequently asked questions
            </h2>
            <p className="text-lg text-slate-600">
              Everything you need to know about SocialEntangler
            </p>
          </div>
          <div className="space-y-6">
            <div className="border border-gray-200 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-slate-900 mb-2">Can I cancel my subscription anytime?</h3>
              <p className="text-slate-600">Yes, you can cancel your subscription at any time. You will continue to have access until the end of your billing period.</p>
            </div>
            <div className="border border-gray-200 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-slate-900 mb-2">Do you offer a free trial?</h3>
              <p className="text-slate-600">Yes, we offer a 7-day free trial on all paid plans. No credit card required to start.</p>
            </div>
            <div className="border border-gray-200 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-slate-900 mb-2">What platforms do you support?</h3>
              <p className="text-slate-600">We currently support Twitter/X, Instagram, and LinkedIn. We are working on adding more platforms soon.</p>
            </div>
            <div className="border border-gray-200 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-slate-900 mb-2">Can I manage multiple accounts?</h3>
              <p className="text-slate-600">Yes, depending on your plan you can manage multiple accounts for each platform.</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl p-12 text-center">
            <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-white mb-4">
              Ready to get started?
            </h2>
            <p className="text-lg text-white/90 mb-8 max-w-2xl mx-auto">
              Join thousands of content creators who save hours every week with SocialEntangler
            </p>
            <Button
              size="lg"
              className="bg-white text-indigo-600 hover:bg-gray-100"
              onClick={() => navigate('/signup')}
              data-testid="final-cta-button"
            >
              Start Free Trial
            </Button>
          </div>
        </div>
      </section>

      <Footer />
      <SupportPopup isOpen={isSupportOpen} onClose={() => setIsSupportOpen(false)} />
    </div>
  );
};

export default LandingPage;