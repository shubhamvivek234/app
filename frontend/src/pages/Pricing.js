import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FaCheck,
  FaTimes,
  FaArrowRight,
  FaMagic,
  FaBolt,
  FaShieldAlt,
  FaQuestionCircle,
  FaChevronDown,
  FaVideo,
  FaCode,
  FaUsers,
  FaLayerGroup,
} from 'react-icons/fa';
import { FaXTwitter } from 'react-icons/fa6';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import Footer from '@/components/Footer';
import UnravlerLogo from '@/components/UnravlerLogo';

const Pricing = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [billingCycle, setBillingCycle] = useState('annual'); // 'monthly' | 'annual'
  const [openFaq, setOpenFaq] = useState(null);

  const toggleFaq = (index) => {
    setOpenFaq(openFaq === index ? null : index);
  };

  const handleSelectPlan = (planId) => {
    if (user) {
      navigate(`/billing?plan=${planId}&cycle=${billingCycle}`);
    } else {
      navigate(`/signup?plan=${planId}&cycle=${billingCycle}`);
    }
  };

  const PLANS = [
    {
      id: 'starter',
      name: 'Starter',
      badge: 'For Solo Creators',
      tagline: 'Ideal for independent creators, podcasters, and personal brands.',
      monthlyPrice: 19,
      annualPrice: 16,
      annualBilled: 192,
      popular: false,
      buttonText: 'Get Started with Starter',
      buttonVariant: 'outline',
      specs: [
        { label: 'Social Accounts', val: '6 connected channels' },
        { label: 'General Social Posts', val: '150 posts / month' },
        { label: 'AI Video Clipping', val: '30 source mins (~12 shorts)' },
        { label: 'AI Text Generations', val: '100 generations / month' },
        { label: 'AI FLUX Images', val: '30 banner graphics / month' },
        { label: 'Smart Bio & CRM', val: '2 bio pages · 500 contacts' },
        { label: 'Cloud Storage', val: '10 GB (250 MB max file)' },
        { label: 'Developer API & CLI', val: '60 req/min (10k calls/mo)' },
      ],
      twitterSafeguard: {
        total: '60 tweets / month',
        links: 'Max 15 link tweets',
        daily: '5 tweets / 24 hours',
        byok: '$5/mo add-on',
      },
      highlights: [
        'Multi-platform scheduling (8+ networks)',
        'Full calendar & post queue view',
        'Burned-in animated ASS subtitles',
        'Audience CRM & deals pipeline',
        '2 active RSS auto-post feeds',
        'Remote MCP server (/mcp/:apiKey)',
        'Standard email support',
      ],
    },
    {
      id: 'pro',
      name: 'Pro',
      badge: 'Most Popular',
      tagline: 'The ultimate engine for growing brands, startups, and high-output creators.',
      monthlyPrice: 45,
      annualPrice: 39,
      annualBilled: 468,
      popular: true,
      buttonText: 'Start with Pro',
      buttonVariant: 'primary',
      specs: [
        { label: 'Social Accounts', val: '18 channels (3 full brands)' },
        { label: 'General Social Posts', val: 'Unlimited scheduled posts' },
        { label: 'AI Video Clipping', val: '120 source mins (~45 shorts)' },
        { label: 'AI Text Generations', val: '500 generations / month' },
        { label: 'AI FLUX Images', val: '150 banner graphics / month' },
        { label: 'Smart Bio & CRM', val: '5 bio pages · 5,000 contacts' },
        { label: 'Cloud Storage', val: '50 GB (1 GB max file)' },
        { label: 'Developer API & CLI', val: '180 req/min (50k calls/mo)' },
      ],
      twitterSafeguard: {
        total: '180 tweets / month',
        links: 'Max 40 link tweets',
        daily: '12 tweets / 24 hours',
        byok: '$5/mo add-on',
      },
      highlights: [
        'Everything in Starter, plus:',
        'Unlimited posts to LinkedIn, IG, TikTok, YouTube, Threads',
        'Custom Domain for Smart Bio (links.yourbrand.com)',
        'Staggered cross-posting & anti-bot offsets',
        'Global Auto-Plugs (auto-comment on viral posts)',
        '10 RSS feeds with custom AI prompt templates',
        '3 Team member collaboration seats',
        '10 Scoped webhooks with HMAC signatures',
      ],
    },
    {
      id: 'agency',
      name: 'Agency / Scale',
      badge: 'For Agencies & Devs',
      tagline: 'Designed for marketing agencies, media houses, and autonomous AI fleets.',
      monthlyPrice: 110,
      annualPrice: 99,
      annualBilled: 1188,
      popular: false,
      buttonText: 'Scale with Agency',
      buttonVariant: 'outline',
      specs: [
        { label: 'Social Accounts', val: '50 channels (8–10 brands)' },
        { label: 'General Social Posts', val: 'Unlimited posts & threads' },
        { label: 'AI Video Clipping', val: '400 source mins (~150 shorts)' },
        { label: 'AI Text Generations', val: '2,000 generations / month' },
        { label: 'AI FLUX Images', val: '500 banner graphics / month' },
        { label: 'Smart Bio & CRM', val: 'Unlimited pages · 50k contacts' },
        { label: 'Cloud Storage', val: '250 GB (2 GB max file)' },
        { label: 'Developer API & CLI', val: '600 req/min (250k calls/mo)' },
      ],
      twitterSafeguard: {
        total: '500 tweets / month',
        links: 'Max 120 link tweets',
        daily: '30 tweets / 24 hours',
        byok: 'Included Free (Unlimited)',
      },
      highlights: [
        'Everything in Pro, plus:',
        'Client Review Approval Portals (white-labeled)',
        'Twitter BYOK Included (use client keys for $0 fee)',
        'Unlimited RSS Auto-Post feeds (5-minute sync)',
        '10 Team member seats with role permissions',
        'Unlimited webhooks with event replays',
        'Dedicated MCP agent pooling for Claude & Cursor',
        'Priority 1-hour SLA & dedicated Slack channel',
      ],
    },
  ];

  const ADD_ONS = [
    {
      name: 'Twitter Link Booster Pack',
      price: '$15',
      unit: 'for 50 link posts',
      desc: 'Never expires. Covers additional link/URL tweets beyond your monthly plan allotment.',
      icon: FaXTwitter,
    },
    {
      name: 'Twitter BYOK (Bring Your Own Key)',
      price: '$5',
      unit: '/ month',
      desc: 'Plug in your personal X Developer API keys for unlimited tweets with zero per-link limits (Included free in Agency).',
      icon: FaCode,
    },
    {
      name: 'Extra Social Channel Pack',
      price: '$18',
      unit: 'for 5 extra channels / mo',
      desc: 'Add 5 additional connected channels ($4/ch individual) to any active subscription.',
      icon: FaLayerGroup,
    },
    {
      name: 'AI Video Clipping Booster',
      price: '$12',
      unit: 'for 100 extra minutes',
      desc: 'Never expires. Adds 100 minutes of long-form video processing and viral subtitle rendering.',
      icon: FaVideo,
    },
    {
      name: 'Extra Team Member Seat',
      price: '$8',
      unit: '/ user / month',
      desc: 'Add collaborators with custom role-based permissions (Editor, Viewer, Client, Admin).',
      icon: FaUsers,
    },
  ];

  const FAQS = [
    {
      q: 'Does Unravler offer a free trial or money-back guarantee?',
      a: 'Yes! Every paid plan comes with a 100% risk-free 7-day money-back guarantee. You can connect your accounts, schedule posts, generate AI media, and clip videos. If Unravler isn’t the right fit, cancel within 7 days for an immediate full refund.',
    },
    {
      q: 'Why are there specific limits for Twitter / X and links?',
      a: 'Under X’s official pay-per-use developer API, standard posts cost $0.015 while posts containing links/URLs cost $0.20 per tweet (13.3x more). To keep our monthly plans affordable rather than charging an expensive per-channel surcharge like other tools, we set clear monthly post and link-tweet caps. If you need unlimited tweets, you can connect your own X Developer keys via BYOK for just $5/mo (or free on Agency).',
    },
    {
      q: 'What is Twitter BYOK (Bring Your Own Key)?',
      a: 'BYOK lets you enter your own Twitter Developer App credentials in Settings. When enabled, your tweets are dispatched through your personal X API quota, completely bypassing Unravler’s Twitter caps at zero extra cost to us.',
    },
    {
      q: 'How does the AI Video Clipper work?',
      a: 'Simply paste any YouTube link or upload an MP4/MOV video. Unravler’s background Celery workers parse the timed transcript, calculate viral engagement hooks, crop the video into a 9:16 vertical frame, burn styled animated subtitles, and create ready-to-publish drafts for Instagram Reels, YouTube Shorts, and TikTok.',
    },
    {
      q: 'Can I switch between monthly and annual billing, or upgrade anytime?',
      a: 'Absolutely. You can upgrade, downgrade, or switch between annual and monthly billing at any time from your Billing settings. Prorated credits are automatically calculated and applied.',
    },
    {
      q: 'What payment methods do you support?',
      a: 'We accept all major Credit and Debit cards (Visa, MasterCard, American Express) via Stripe for international customers, and Razorpay (UPI, NetBanking, Cards) for Indian customers.',
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 antialiased selection:bg-indigo-500 selection:text-white">
      {/* Top Navigation */}
      <header className="sticky top-0 z-40 backdrop-blur-md bg-white/80 dark:bg-slate-950/80 border-b border-slate-200/80 dark:border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <button onClick={() => navigate('/')} className="flex items-center gap-2 text-left focus:outline-none">
              <UnravlerLogo className="h-8 w-auto" />
            </button>
            <nav className="hidden md:flex items-center gap-5 text-sm font-medium text-slate-600 dark:text-slate-300">
              <button onClick={() => navigate('/#product')} className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">Product</button>
              <button onClick={() => navigate('/#workflow')} className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">Workflow</button>
              <button onClick={() => navigate('/#platforms')} className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">Platforms</button>
              <span className="text-indigo-600 dark:text-indigo-400 font-semibold">Pricing</span>
              <button onClick={() => navigate('/developers')} className="hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors">Developers</button>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {user ? (
              <Button onClick={() => navigate('/dashboard')} className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-xl">
                Go to Dashboard
              </Button>
            ) : (
              <>
                <button
                  onClick={() => navigate('/login')}
                  className="text-sm font-medium text-slate-700 dark:text-slate-200 hover:text-indigo-600 dark:hover:text-indigo-400 px-3 py-1.5 transition-colors"
                >
                  Sign in
                </button>
                <Button
                  onClick={() => navigate('/signup')}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-xl shadow-sm hover:shadow transition-all"
                >
                  Get Started
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="pt-16 pb-12 px-4 sm:px-6 lg:px-8 text-center max-w-4xl mx-auto">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/80 mb-6">
          <FaMagic className="text-indigo-500" />
          <span>Transparent, Value-Packed Pricing</span>
        </div>
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-slate-900 dark:text-white mb-6">
          Simple, Predictable Plans for <br className="hidden sm:inline" />
          <span className="bg-clip-text text-transparent bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500">
            Creators, Brands & Agencies.
          </span>
        </h1>
        <p className="text-lg sm:text-xl text-slate-600 dark:text-slate-300 max-w-2xl mx-auto mb-10 leading-relaxed">
          Publish to 8+ networks, automate viral video clipping, build smart bio pages, and scale with autonomous AI agents. All in one place.
        </p>

        {/* Billing Toggle Switch */}
        <div className="inline-flex items-center p-1.5 bg-slate-200/80 dark:bg-slate-800/80 rounded-2xl border border-slate-300/60 dark:border-slate-700/60 shadow-inner">
          <button
            type="button"
            onClick={() => setBillingCycle('monthly')}
            className={`px-5 py-2 text-sm font-semibold rounded-xl transition-all ${
              billingCycle === 'monthly'
                ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            Monthly Billing
          </button>
          <button
            type="button"
            onClick={() => setBillingCycle('annual')}
            className={`px-5 py-2 text-sm font-semibold rounded-xl flex items-center gap-2 transition-all ${
              billingCycle === 'annual'
                ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            <span>Annual Billing</span>
            <span className="bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 text-[11px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider">
              Save up to 16%
            </span>
          </button>
        </div>
      </section>

      {/* Plan Cards Grid */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch">
          {PLANS.map((plan) => {
            const price = billingCycle === 'annual' ? plan.annualPrice : plan.monthlyPrice;
            return (
              <div
                key={plan.id}
                className={`relative flex flex-col rounded-3xl p-8 transition-all ${
                  plan.popular
                    ? 'bg-white dark:bg-slate-900 border-2 border-indigo-600 shadow-2xl shadow-indigo-500/10 dark:shadow-indigo-950/50 scale-100 lg:-translate-y-2'
                    : 'bg-white dark:bg-slate-900/70 border border-slate-200 dark:border-slate-800 shadow-lg hover:shadow-xl hover:border-slate-300 dark:hover:border-slate-700'
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-4 py-1 bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-xs font-bold uppercase tracking-wider rounded-full shadow-md flex items-center gap-1.5">
                    <FaBolt className="text-amber-300" />
                    <span>{plan.badge}</span>
                  </div>
                )}

                <div className="mb-6">
                  {!plan.popular && (
                    <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 mb-3">
                      {plan.badge}
                    </span>
                  )}
                  <h3 className="text-2xl font-bold text-slate-900 dark:text-white">{plan.name}</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 min-h-[32px]">{plan.tagline}</p>
                </div>

                {/* Price Display */}
                <div className="mb-6 pb-6 border-b border-slate-100 dark:border-slate-800">
                  <div className="flex items-baseline gap-1">
                    <span className="text-4xl sm:text-5xl font-extrabold text-slate-900 dark:text-white">
                      ${price}
                    </span>
                    <span className="text-slate-500 text-sm font-medium">/ month</span>
                  </div>
                  {billingCycle === 'annual' ? (
                    <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium mt-1">
                      Billed annually (${plan.annualBilled}/year)
                    </p>
                  ) : (
                    <p className="text-xs text-slate-400 font-medium mt-1">
                      Billed monthly · Cancel anytime
                    </p>
                  )}
                </div>

                {/* Core Specifications Table */}
                <div className="mb-6 space-y-2.5 text-xs">
                  {plan.specs.map((s, idx) => (
                    <div key={idx} className="flex items-center justify-between text-slate-700 dark:text-slate-300 py-0.5">
                      <span className="text-slate-500 dark:text-slate-400">{s.label}:</span>
                      <span className="font-semibold text-slate-900 dark:text-slate-100">{s.val}</span>
                    </div>
                  ))}
                </div>

                {/* Dedicated Twitter/X Cost Protection Safeguard Box */}
                <div className="mb-6 p-3.5 bg-slate-50 dark:bg-slate-800/60 rounded-2xl border border-slate-200/80 dark:border-slate-700/80">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-1.5 text-xs font-bold text-slate-900 dark:text-slate-100">
                      <FaXTwitter className="text-slate-900 dark:text-white text-sm" />
                      <span>Twitter / X Limits</span>
                    </div>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Per Month</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-600 dark:text-slate-300">
                    <div>
                      <span className="text-slate-400 block text-[10px]">Total Tweets:</span>
                      <span className="font-bold text-slate-800 dark:text-slate-200">{plan.twitterSafeguard.total}</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Link Tweets:</span>
                      <span className="font-bold text-indigo-600 dark:text-indigo-400">{plan.twitterSafeguard.links}</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Daily Rate:</span>
                      <span className="font-medium text-slate-700 dark:text-slate-300">{plan.twitterSafeguard.daily}</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-[10px]">Custom Keys:</span>
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">{plan.twitterSafeguard.byok}</span>
                    </div>
                  </div>
                </div>

                {/* Feature Bullets */}
                <div className="flex-1 mb-8">
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">Included Capabilities</p>
                  <ul className="space-y-2.5 text-xs text-slate-600 dark:text-slate-300">
                    {plan.highlights.map((h, i) => (
                      <li key={i} className="flex items-start gap-2.5">
                        <FaCheck className="text-emerald-500 mt-0.5 flex-shrink-0 text-xs" />
                        <span>{h}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Call to Action Button */}
                <Button
                  onClick={() => handleSelectPlan(plan.id)}
                  className={`w-full py-3.5 px-4 rounded-xl text-sm font-semibold transition-all shadow-sm ${
                    plan.popular
                      ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/25 hover:shadow-indigo-600/40 hover:-translate-y-0.5'
                      : 'bg-slate-900 hover:bg-slate-800 dark:bg-slate-100 dark:hover:bg-white text-white dark:text-slate-900 hover:-translate-y-0.5'
                  }`}
                >
                  {plan.buttonText} <FaArrowRight className="ml-2 text-xs" />
                </Button>
              </div>
            );
          })}
        </div>
      </section>

      {/* Add-ons & Boosters Section */}
      <section className="bg-white dark:bg-slate-900/60 border-y border-slate-200 dark:border-slate-800 py-16 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-3xl mx-auto mb-12">
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-2 block">
              Modular Scaling
            </span>
            <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white">
              Power Add-Ons & Usage Boosters
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-400 mt-2">
              Need extra video minutes, higher link volume, or custom API keys? Add modules whenever you need without upgrading your base plan.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {ADD_ONS.map((addon, index) => {
              const Icon = addon.icon;
              return (
                <div
                  key={index}
                  className="p-6 rounded-2xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex flex-col justify-between hover:border-indigo-300 dark:hover:border-indigo-800 transition-all"
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div className="h-10 w-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/80 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-lg">
                        <Icon />
                      </div>
                      <div className="text-right">
                        <span className="text-xl font-extrabold text-slate-900 dark:text-white">{addon.price}</span>
                        <span className="text-xs text-slate-500 font-medium block">{addon.unit}</span>
                      </div>
                    </div>
                    <h4 className="text-base font-bold text-slate-900 dark:text-white mb-1.5">{addon.name}</h4>
                    <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{addon.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Feature Comparison Matrix */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="text-center max-w-3xl mx-auto mb-14">
          <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 mb-2 block">
            Complete Feature Breakdown
          </span>
          <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white">
            Compare Plan Capabilities Side-by-Side
          </h2>
        </div>

        <div className="overflow-x-auto rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/80 text-slate-900 dark:text-white">
                <th className="p-4 sm:p-5 font-bold text-sm">Feature</th>
                <th className="p-4 sm:p-5 font-bold text-sm w-1/4">Starter ($19 · $16/mo)</th>
                <th className="p-4 sm:p-5 font-bold text-sm w-1/4 text-indigo-600 dark:text-indigo-400">Pro ($45 · $39/mo)</th>
                <th className="p-4 sm:p-5 font-bold text-sm w-1/4">Agency ($110 · $99/mo)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Connected Social Channels</td>
                <td className="p-4">6 accounts</td>
                <td className="p-4 font-semibold text-indigo-600 dark:text-indigo-400">18 accounts</td>
                <td className="p-4 font-semibold">50 accounts</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Supported Platforms</td>
                <td className="p-4" colSpan={3}>Twitter/X, LinkedIn, Instagram, TikTok, YouTube, Threads, Facebook, Bluesky, Pinterest, Reddit</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Non-Twitter Social Posts</td>
                <td className="p-4">150 / month</td>
                <td className="p-4 font-semibold text-emerald-600">Unlimited</td>
                <td className="p-4 font-semibold text-emerald-600">Unlimited</td>
              </tr>
              <tr className="bg-indigo-50/30 dark:bg-indigo-950/20">
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Twitter / X Total Tweets</td>
                <td className="p-4">60 / month</td>
                <td className="p-4 font-semibold text-indigo-600 dark:text-indigo-400">180 / month</td>
                <td className="p-4 font-semibold">500 / month</td>
              </tr>
              <tr className="bg-indigo-50/30 dark:bg-indigo-950/20">
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Twitter / X Link Tweets (URLs)</td>
                <td className="p-4">Max 15 / month</td>
                <td className="p-4 font-semibold text-indigo-600 dark:text-indigo-400">Max 40 / month</td>
                <td className="p-4 font-semibold">Max 120 / month</td>
              </tr>
              <tr className="bg-indigo-50/30 dark:bg-indigo-950/20">
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Twitter Custom Keys (BYOK)</td>
                <td className="p-4">$5/mo add-on</td>
                <td className="p-4">$5/mo add-on</td>
                <td className="p-4 font-semibold text-emerald-600">Included Free (Unlimited)</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">AI Video Clipping (Shorts)</td>
                <td className="p-4">30 source mins (~12 clips)</td>
                <td className="p-4 font-semibold text-indigo-600 dark:text-indigo-400">120 source mins (~45 clips)</td>
                <td className="p-4 font-semibold">400 source mins (~150 clips)</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">AI Copywriting & Repurposing</td>
                <td className="p-4">100 generations</td>
                <td className="p-4 font-semibold">500 generations</td>
                <td className="p-4 font-semibold">2,000 generations</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">AI Image Generation (FLUX)</td>
                <td className="p-4">30 images / mo</td>
                <td className="p-4 font-semibold">150 images / mo</td>
                <td className="p-4 font-semibold">500 images / mo</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Smart Bio Pages</td>
                <td className="p-4">2 pages (White-label)</td>
                <td className="p-4 font-semibold">5 pages (Custom Domain)</td>
                <td className="p-4 font-semibold">Unlimited</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Audience CRM & Leads Hub</td>
                <td className="p-4">500 contacts</td>
                <td className="p-4 font-semibold">5,000 contacts</td>
                <td className="p-4 font-semibold">50,000 contacts</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Deals Pipeline (Kanban)</td>
                <td className="p-4">Unlimited deals</td>
                <td className="p-4 font-semibold">Unlimited deals</td>
                <td className="p-4 font-semibold">Multi-brand pipelines</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Staggered Posting & Auto-Plugs</td>
                <td className="p-4"><FaTimes className="text-slate-300" /></td>
                <td className="p-4 font-semibold text-emerald-600"><FaCheck /></td>
                <td className="p-4 font-semibold text-emerald-600"><FaCheck /></td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">RSS Auto-Post Feeds</td>
                <td className="p-4">2 feeds (Hourly)</td>
                <td className="p-4 font-semibold">10 feeds (15-min sync)</td>
                <td className="p-4 font-semibold">Unlimited feeds (5-min sync)</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Team Collaboration Seats</td>
                <td className="p-4">1 user (Solo)</td>
                <td className="p-4 font-semibold">3 team seats</td>
                <td className="p-4 font-semibold">10 team seats</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Client Approval Portals</td>
                <td className="p-4"><FaTimes className="text-slate-300" /></td>
                <td className="p-4"><FaTimes className="text-slate-300" /></td>
                <td className="p-4 font-semibold text-emerald-600"><FaCheck /> Included</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Developer API / CLI Rate Limit</td>
                <td className="p-4">60 req/min (10k/mo)</td>
                <td className="p-4 font-semibold">180 req/min (50k/mo)</td>
                <td className="p-4 font-semibold">600 req/min (250k/mo)</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Remote MCP Server (/mcp/:apiKey)</td>
                <td className="p-4">Full access</td>
                <td className="p-4 font-semibold">Streaming agent pool</td>
                <td className="p-4 font-semibold">Dedicated agent pool</td>
              </tr>
              <tr>
                <td className="p-4 font-semibold text-slate-900 dark:text-white">Money-Back Guarantee</td>
                <td className="p-4 font-semibold text-emerald-600" colSpan={3}>7-Day 100% Risk-Free Refund Guarantee</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-4xl mx-auto border-t border-slate-200 dark:border-slate-800">
        <div className="text-center mb-12">
          <div className="h-10 w-10 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto mb-3 text-lg">
            <FaQuestionCircle />
          </div>
          <h2 className="text-3xl font-extrabold text-slate-900 dark:text-white">Frequently Asked Questions</h2>
          <p className="text-sm text-slate-500 mt-2">Everything you need to know about Unravler billing, plans, and features.</p>
        </div>

        <div className="space-y-4">
          {FAQS.map((faq, idx) => (
            <div
              key={idx}
              className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden transition-all"
            >
              <button
                type="button"
                onClick={() => toggleFaq(idx)}
                className="w-full text-left p-5 flex items-center justify-between text-sm sm:text-base font-bold text-slate-900 dark:text-white focus:outline-none"
              >
                <span>{faq.q}</span>
                <FaChevronDown
                  className={`text-slate-400 text-xs transition-transform duration-200 ${
                    openFaq === idx ? 'rotate-180 text-indigo-600' : ''
                  }`}
                />
              </button>
              {openFaq === idx && (
                <div className="px-5 pb-5 text-xs sm:text-sm text-slate-600 dark:text-slate-300 leading-relaxed border-t border-slate-100 dark:border-slate-800/80 pt-3">
                  {faq.a}
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Bottom CTA Banner */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 max-w-5xl mx-auto text-center">
        <div className="bg-gradient-to-br from-indigo-600 via-indigo-700 to-purple-800 rounded-3xl p-10 sm:p-14 text-white shadow-2xl shadow-indigo-600/20 relative overflow-hidden">
          <div className="relative z-10 max-w-2xl mx-auto">
            <h3 className="text-3xl sm:text-4xl font-extrabold tracking-tight mb-4">
              Ready to unify and automate your social workflow?
            </h3>
            <p className="text-indigo-100 text-sm sm:text-base mb-8">
              Join creators, brands, and agencies scaling their content across 8+ platforms with autonomous AI workflows.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Button
                onClick={() => navigate('/signup')}
                className="w-full sm:w-auto bg-white text-indigo-700 hover:bg-indigo-50 font-bold px-8 py-3.5 rounded-xl shadow-lg hover:shadow-xl transition-all"
              >
                Get Started Now <FaArrowRight className="ml-2 text-xs" />
              </Button>
              <Button
                onClick={() => navigate('/developers')}
                variant="outline"
                className="w-full sm:w-auto border-white/40 text-white hover:bg-white/10 font-semibold px-6 py-3.5 rounded-xl transition-all"
              >
                Explore Developer API
              </Button>
            </div>
            <p className="text-indigo-200 text-xs mt-6 flex items-center justify-center gap-2">
              <FaShieldAlt className="text-emerald-300" />
              <span>Includes 7-day 100% money-back guarantee · No lock-in</span>
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <Footer />
    </div>
  );
};

export default Pricing;
