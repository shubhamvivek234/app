import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { FaTwitter, FaLinkedin, FaInstagram, FaCalendarAlt, FaRocket, FaMagic, FaChevronDown, FaYoutube, FaFacebook, FaTiktok } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';

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
      {/* Navigation */}
      <nav className="border-b border-border backdrop-blur-md bg-white/80 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="text-2xl font-semibold text-slate-900">SocialSync</div>
            <div className="flex gap-3">
              <Button
                variant="ghost"
                onClick={() => navigate('/login')}
                data-testid="login-button"
              >
                Login
              </Button>
              <Button
                onClick={() => navigate('/signup')}
                data-testid="signup-button"
              >
                Get Started
              </Button>
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