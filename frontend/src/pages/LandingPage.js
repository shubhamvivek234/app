import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { FaTwitter, FaLinkedin, FaInstagram, FaCalendarAlt, FaRocket, FaMagic, FaChevronDown, FaYoutube, FaFacebook, FaTiktok } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import Footer from '@/components/Footer';

const LandingPage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [showToolsDropdown, setShowToolsDropdown] = useState(false);

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
            <div className="flex items-center">
              <div className="flex items-center space-x-2 cursor-pointer" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
                <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                  <span className="text-white font-bold text-lg">P</span>
                </div>
                <span className="text-xl font-semibold text-gray-900">post bridge</span>
              </div>
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
              <button onClick={() => scrollToSection('faq')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                FAQ
              </button>
              <button onClick={() => navigate('/blog')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                Blog
              </button>
              <div className="relative">
                <button 
                  onClick={() => setShowToolsDropdown(!showToolsDropdown)}
                  className="text-gray-600 hover:text-gray-900 text-sm font-medium flex items-center"
                >
                  Tools <FaChevronDown className="ml-1 text-xs" />
                </button>
                {showToolsDropdown && (
                  <div className="absolute top-full left-0 mt-2 w-48 bg-white rounded-md shadow-lg border border-gray-200 py-2">
                    <Link to="/tools/instagram-grid" className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">Instagram Grid Maker</Link>
                    <Link to="/tools/caption-generator" className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">Caption Generator</Link>
                    <Link to="/tools/hashtag-generator" className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">Hashtag Generator</Link>
                  </div>
                )}
              </div>
              <button onClick={() => navigate('/api')} className="text-gray-600 hover:text-gray-900 text-sm font-medium">
                API
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
      <section className="py-20 lg:py-32">
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
                <img
                  src="https://images.unsplash.com/photo-1648994517761-a35b826d5456?crop=entropy&cs=srgb&fm=jpg&q=85"
                  alt="Dashboard Preview"
                  className="w-full h-full object-cover"
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Platforms Section */}
      <section className="py-16 bg-slate-50">
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
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-3 gap-8">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FaRocket className="text-2xl text-indigo-600" />
              </div>
              <h3 className="text-2xl font-medium tracking-tight text-slate-900">
                Cross-posting made easy
              </h3>
              <p className="text-base leading-relaxed text-slate-600">
                Publish everywhere in 30 seconds, not 30 minutes. Manage all your accounts without switching platforms.
              </p>
            </div>
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FaCalendarAlt className="text-2xl text-indigo-600" />
              </div>
              <h3 className="text-2xl font-medium tracking-tight text-slate-900">
                Schedule posts effortlessly
              </h3>
              <p className="text-base leading-relaxed text-slate-600">
                Plan your content strategy ahead of time. Queue up your posts and let SocialSync handle the rest.
              </p>
            </div>
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FaMagic className="text-2xl text-indigo-600" />
              </div>
              <h3 className="text-2xl font-medium tracking-tight text-slate-900">
                AI-powered content
              </h3>
              <p className="text-base leading-relaxed text-slate-600">
                Generate engaging posts with AI assistance. Get suggestions optimized for each platform.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="py-20 bg-slate-50" id="pricing">
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

      {/* CTA Section */}
      <section className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-2xl p-12 text-center">
            <h2 className="text-3xl md:text-4xl font-semibold tracking-tight text-white mb-4">
              Ready to get started?
            </h2>
            <p className="text-lg text-white/90 mb-8 max-w-2xl mx-auto">
              Join thousands of content creators who save hours every week with SocialSync
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

      {/* Footer */}
      <footer className="border-t border-border py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center space-y-4">
            <div className="flex justify-center gap-6 text-sm text-slate-600">
              <Link to="/terms" className="hover:text-slate-900">Terms of Service</Link>
              <Link to="/privacy" className="hover:text-slate-900">Privacy Policy</Link>
              <a href="mailto:support@socialsync.com" className="hover:text-slate-900">Contact</a>
            </div>
            <p className="text-slate-600">© 2026 SocialSync. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;