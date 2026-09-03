import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  FaArrowRight,
  FaBars,
  FaCalendarAlt,
  FaChartLine,
  FaCheck,
  FaChevronDown,
  FaCode,
  FaFacebookF,
  FaInstagram,
  FaLinkedinIn,
  FaMagic,
  FaRegClock,
  FaTiktok,
  FaTimes,
  FaYoutube,
} from 'react-icons/fa';
import { FaThreads, FaXTwitter } from 'react-icons/fa6';
import { SiBluesky } from 'react-icons/si';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/AuthContext';
import Footer from '@/components/Footer';
import SupportPopup from '@/components/SupportPopup';
import UnravlerLogo from '@/components/UnravlerLogo';
import './LandingPage.css';

const platforms = [
  { label: 'Instagram', Icon: FaInstagram, color: '#d94b6d' },
  { label: 'LinkedIn', Icon: FaLinkedinIn, color: '#0a66c2' },
  { label: 'YouTube', Icon: FaYoutube, color: '#e3423e' },
  { label: 'TikTok', Icon: FaTiktok, color: '#141b34' },
  { label: 'X', Icon: FaXTwitter, color: '#141b34' },
  { label: 'Facebook', Icon: FaFacebookF, color: '#1877f2' },
  { label: 'Threads', Icon: FaThreads, color: '#141b34' },
  { label: 'Bluesky', Icon: SiBluesky, color: '#1688d4' },
];

const workflow = [
  {
    label: 'Build once',
    title: 'Make the post feel right before it goes anywhere.',
    body: 'Write one core idea, adapt it per channel, then keep every edit and approval in the same place.',
    icon: FaMagic,
  },
  {
    label: 'Place it precisely',
    title: 'Give every post a deliberate moment.',
    body: 'Plan your week in a calendar, fine-tune a time, and move scheduled work without losing the thread.',
    icon: FaCalendarAlt,
  },
  {
    label: 'Learn from the outcome',
    title: 'See what landed, then plan the next move.',
    body: 'Bring platform performance, publishing status, and upcoming work into one operating view.',
    icon: FaChartLine,
  },
];

const navItems = [
  ['Product', 'product'],
  ['Workflow', 'workflow'],
  ['Platforms', 'platforms'],
  ['Pricing', 'pricing'],
];

function DispatchBoard({ activeStep }) {
  const states = ['Drafting', 'Scheduled', 'Published'];
  const state = states[activeStep];

  return (
    <div className="unravler-dispatch" aria-label={`Unravler publishing board: ${state}`}>
      <div className="unravler-dispatch__topbar">
        <span className="unravler-dispatch__eyebrow">Publishing desk</span>
        <span className="unravler-dispatch__sync"><i /> Saved just now</span>
      </div>

      <div className="unravler-dispatch__body">
        <div className="unravler-dispatch__post">
          <div className="unravler-dispatch__post-meta">
            <span className="unravler-avatar">S</span>
            <span>Studio notes</span>
            <span className="unravler-dispatch__post-dot" />
            <span>{state === 'Scheduled' ? 'Friday, 10:30' : state === 'Published' ? 'Live now' : 'Ready to plan'}</span>
          </div>
          <p>Less admin. More attention on the work that deserves to be seen.</p>
          <div className="unravler-dispatch__media">
            <div className="unravler-dispatch__sun" />
            <div className="unravler-dispatch__arch unravler-dispatch__arch--one" />
            <div className="unravler-dispatch__arch unravler-dispatch__arch--two" />
            <span>Campaign image</span>
          </div>
        </div>

        <div className="unravler-dispatch__rail" aria-hidden="true">
          {states.map((item, index) => (
            <React.Fragment key={item}>
              <span className={`unravler-dispatch__node ${index <= activeStep ? 'is-active' : ''}`}>
                {index < activeStep ? <FaCheck /> : index + 1}
              </span>
              {index < states.length - 1 && <span className={`unravler-dispatch__line ${index < activeStep ? 'is-active' : ''}`} />}
            </React.Fragment>
          ))}
        </div>

        <div className="unravler-dispatch__destination">
          <span className="unravler-dispatch__eyebrow">{state}</span>
          <strong>{activeStep === 0 ? 'Shape the story' : activeStep === 1 ? 'Set for Friday' : 'The work is out'}</strong>
          <div className="unravler-dispatch__channels">
            {platforms.slice(0, 4).map(({ label, Icon, color }) => (
              <span key={label} title={label} style={{ '--channel-color': color }}><Icon /></span>
            ))}
          </div>
          <span className="unravler-dispatch__status">
            <i className={activeStep === 2 ? 'is-live' : ''} />
            {activeStep === 2 ? 'Posted to selected channels' : 'Everything stays in one flow'}
          </span>
        </div>
      </div>
    </div>
  );
}

function SignalPanel() {
  const bars = [42, 68, 51, 84, 63, 91, 72, 100];

  return (
    <div className="unravler-signal-panel" aria-label="Analytics product preview">
      <div className="unravler-signal-panel__header">
        <div>
          <span>Performance overview</span>
          <strong>What your work is doing</strong>
        </div>
        <span className="unravler-signal-panel__period">Last 30 days <FaChevronDown /></span>
      </div>
      <div className="unravler-signal-panel__metrics">
        <div><small>Engagement</small><b>4.8%</b><em>+0.9%</em></div>
        <div><small>Published</small><b>24</b><em>On track</em></div>
        <div><small>Best channel</small><b>Instagram</b><em>Most saves</em></div>
      </div>
      <div className="unravler-signal-panel__chart">
        <div className="unravler-signal-panel__chart-label"><span>Audience response</span><b>↑ steady</b></div>
        <div className="unravler-signal-panel__bars">
          {bars.map((height, index) => <i key={index} style={{ '--bar-height': `${height}%` }} />)}
        </div>
      </div>
    </div>
  );
}

const LandingPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const rootRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isSupportOpen, setIsSupportOpen] = useState(false);
  const [activeStep, setActiveStep] = useState(0);

  const getStarted = () => navigate(user ? '/dashboard' : '/signup');
  const scrollToSection = (sectionId) => {
    setMenuOpen(false);
    document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  useEffect(() => {
    if (!location.hash) return undefined;
    const timeoutId = window.setTimeout(() => {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 80);
    return () => window.clearTimeout(timeoutId);
  }, [location.hash]);

  useEffect(() => {
    let frameId = 0;
    const updateProgress = () => {
      const scrollableHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = scrollableHeight > 0 ? Math.min(window.scrollY / scrollableHeight, 1) : 0;
      rootRef.current?.style.setProperty('--unravler-scroll-progress', progress.toFixed(3));
      frameId = 0;
    };
    const onScroll = () => {
      if (!frameId) frameId = window.requestAnimationFrame(updateProgress);
    };
    updateProgress();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (frameId) window.cancelAnimationFrame(frameId);
    };
  }, []);

  useEffect(() => {
    const sections = document.querySelectorAll('[data-workflow-index]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) setActiveStep(Number(entry.target.dataset.workflowIndex));
      });
    }, { rootMargin: '-38% 0px -42% 0px', threshold: 0 });
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={rootRef} className="unravler-landing min-h-screen">
      <div className="unravler-landing__progress" aria-hidden="true" />
      <nav className="unravler-nav" aria-label="Primary navigation">
        <div className="unravler-nav__inner">
          <button className="unravler-nav__brand" onClick={() => scrollToSection('hero')} aria-label="Back to top">
            <UnravlerLogo size="default" />
          </button>
          <div className="unravler-nav__links">
            {navItems.map(([label, target]) => <button key={target} onClick={() => scrollToSection(target)}>{label}</button>)}
            <button onClick={() => navigate('/developers')}>Developers</button>
          </div>
          <div className="unravler-nav__actions">
            <button className="unravler-nav__login" onClick={() => navigate(user ? '/dashboard' : '/login')}>
              {user ? 'Open workspace' : 'Sign in'}
            </button>
            <Button onClick={getStarted} className="unravler-nav__cta">{user ? 'Dashboard' : 'Start free'}</Button>
          </div>
          <button className="unravler-nav__menu" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen} aria-label="Toggle menu">
            {menuOpen ? <FaTimes /> : <FaBars />}
          </button>
        </div>
        {menuOpen && (
          <div className="unravler-nav__mobile-links">
            {navItems.map(([label, target]) => <button key={target} onClick={() => scrollToSection(target)}>{label}</button>)}
            <button onClick={() => navigate('/developers')}>Developers</button>
            <button onClick={() => setIsSupportOpen(true)}>Support</button>
          </div>
        )}
      </nav>

      <main>
        <section id="hero" className="unravler-hero">
          <div className="unravler-shell unravler-hero__grid">
            <div className="unravler-hero__copy">
              <p className="unravler-kicker"><span /> Your social publishing room</p>
              <h1>Make the work.<br />Keep the rhythm.</h1>
              <p className="unravler-hero__lede">
                Unravler gives teams and creators one calm place to create, approve, schedule, and understand social content.
              </p>
              <div className="unravler-hero__actions">
                <Button size="lg" onClick={getStarted} data-testid="hero-cta-button" className="unravler-primary-cta">
                  {user ? 'Open your workspace' : 'Start creating'} <FaArrowRight />
                </Button>
                <button className="unravler-text-cta" onClick={() => scrollToSection('workflow')}>See how it works <span>↓</span></button>
              </div>
              <div className="unravler-hero__note"><FaCheck /> No credit card required to begin</div>
            </div>
            <div className="unravler-hero__visual">
              <div className="unravler-hero__orbit unravler-hero__orbit--outer" />
              <div className="unravler-hero__orbit unravler-hero__orbit--inner" />
              <DispatchBoard activeStep={activeStep} />
              <div className="unravler-hero__float unravler-hero__float--calendar"><FaCalendarAlt /><span>Fri</span><b>12</b></div>
              <div className="unravler-hero__float unravler-hero__float--status"><i /> All channels ready</div>
            </div>
          </div>
          <div className="unravler-hero__tally unravler-shell">
            <span>One workspace</span><i />
            <span>Clear approvals</span><i />
            <span>Purposeful reporting</span>
          </div>
        </section>

        <section id="product" className="unravler-intro-section">
          <div className="unravler-shell unravler-intro-section__grid">
            <p className="unravler-kicker"><span /> Built for the full cycle</p>
            <h2>Social work is not a stack of posts. It is a sequence.</h2>
            <p>Each handoff has a home: the first thought, the approval, the calendar slot, the final result. Unravler lets you move through that sequence without rebuilding the context every time.</p>
          </div>
        </section>

        <section id="workflow" className="unravler-workflow">
          <div className="unravler-shell unravler-workflow__layout">
            <div className="unravler-workflow__aside">
              <p className="unravler-kicker"><span /> A working rhythm</p>
              <h2>Built around the way publishing actually happens.</h2>
              <p>Scroll through the flow. The dispatch board above moves with the stage you are in.</p>
              <div className="unravler-workflow__aside-mark"><FaRegClock /> A better pace for every channel</div>
            </div>
            <div className="unravler-workflow__stages">
              {workflow.map(({ label, title, body, icon: Icon }, index) => (
                <article key={label} data-workflow-index={index} className={`unravler-workflow__stage ${index === activeStep ? 'is-active' : ''}`}>
                  <div className="unravler-workflow__stage-number">0{index + 1}</div>
                  <div className="unravler-workflow__stage-icon"><Icon /></div>
                  <div>
                    <p>{label}</p>
                    <h3>{title}</h3>
                    <span>{body}</span>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section id="platforms" className="unravler-platforms">
          <div className="unravler-shell">
            <div className="unravler-platforms__heading">
              <div>
                <p className="unravler-kicker"><span /> Publish where people are</p>
                <h2>One idea, considered for every channel.</h2>
              </div>
              <p>Connect the accounts your work depends on, then select exactly where each post should go.</p>
            </div>
            <div className="unravler-platforms__rail">
              {platforms.map(({ label, Icon, color }) => (
                <div key={label} className="unravler-platform" style={{ '--platform-color': color }}>
                  <Icon /><span>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="unravler-signal-section">
          <div className="unravler-shell unravler-signal-section__grid">
            <div>
              <p className="unravler-kicker"><span /> A clearer signal</p>
              <h2>Finish the loop with the numbers that matter.</h2>
              <p>See your content performance without turning the workspace into a reporting project. Export a concise view when the conversation needs to leave the room.</p>
              <button className="unravler-text-cta" onClick={() => navigate('/signup')}>Explore the analytics workspace <FaArrowRight /></button>
            </div>
            <SignalPanel />
          </div>
        </section>

        <section id="pricing" className="unravler-pricing">
          <div className="unravler-shell">
            <div className="unravler-pricing__heading">
              <p className="unravler-kicker"><span /> Start when you are ready</p>
              <h2>Simple plans for a steadier publishing habit.</h2>
            </div>
            <div className="unravler-pricing__grid">
              <article className="unravler-price-card">
                <div><span>Monthly</span><b>₹500 <small>/ month</small></b></div>
                <p>For consistent creators building their own rhythm.</p>
                <ul><li><FaCheck /> Connect up to 3 social accounts</li><li><FaCheck /> Create and schedule posts</li><li><FaCheck /> AI writing support</li></ul>
                <Button onClick={getStarted} data-testid="pricing-monthly-button" className="unravler-price-card__button">Choose monthly</Button>
              </article>
              <article className="unravler-price-card unravler-price-card--featured">
                <div><span>Yearly <em>Best value</em></span><b>₹3,000 <small>/ year</small></b></div>
                <p>For a calmer year of planned, connected work.</p>
                <ul><li><FaCheck /> Everything in monthly</li><li><FaCheck /> Save 50% across the year</li><li><FaCheck /> Priority support</li></ul>
                <Button onClick={getStarted} data-testid="pricing-yearly-button" className="unravler-price-card__button">Choose yearly</Button>
              </article>
            </div>
          </div>
        </section>

        <section id="developers" className="unravler-developers">
          <div className="unravler-shell unravler-developers__inner">
            <div>
              <p className="unravler-kicker"><span /> For teams that build</p>
              <h2>Let your assistant help manage the rhythm.</h2>
              <p>Use Unravler through its developer tools and MCP connection for content operations that begin in a conversation.</p>
            </div>
            <div className="unravler-developers__console">
              <div><i /><i /><i /><span>unravler.mcp</span></div>
              <p><b>›</b> Schedule the approved launch posts for next week.</p>
              <p className="unravler-developers__response"><b>↳</b> Three posts scheduled. I kept the selected channels and timezone.</p>
            </div>
            <Button onClick={() => navigate('/developers')} className="unravler-developers__cta">Developer guide <FaCode /></Button>
          </div>
        </section>

        <section id="faq" className="unravler-faq unravler-shell">
          <div><p className="unravler-kicker"><span /> Good to know</p><h2>Questions, answered plainly.</h2></div>
          <div className="unravler-faq__list">
            <details><summary>Can I cancel whenever I need to?<FaChevronDown /></summary><p>Yes. Your access continues through the end of the billing period, and you can manage your subscription from billing.</p></details>
            <details><summary>Can I manage more than one account?<FaChevronDown /></summary><p>Yes. Connect the social accounts included with your plan, then choose the exact accounts for each post.</p></details>
            <details><summary>Can a team review work before it is scheduled?<FaChevronDown /></summary><p>Yes. Use the approval workflow to keep drafts, feedback, and final scheduling decisions in one place.</p></details>
          </div>
        </section>

        <section className="unravler-final">
          <div className="unravler-shell unravler-final__inner">
            <p>Bring order to the work behind your social presence.</p>
            <h2>Make the next post<br />the easy one.</h2>
            <Button size="lg" onClick={getStarted} data-testid="final-cta-button" className="unravler-final__cta">Start with Unravler <FaArrowRight /></Button>
            <button onClick={() => setIsSupportOpen(true)}>Questions? Talk to us.</button>
          </div>
        </section>
      </main>
      <Footer />
      <SupportPopup isOpen={isSupportOpen} onClose={() => setIsSupportOpen(false)} />
    </div>
  );
};

export default LandingPage;
