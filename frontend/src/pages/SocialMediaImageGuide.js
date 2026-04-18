import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { FaInstagram, FaFacebook, FaTwitter, FaLinkedin, FaYoutube, FaPinterest, FaThreads } from 'react-icons/fa6';
import { SiBluesky, SiTiktok } from 'react-icons/si';
import Footer from '@/components/Footer';

/* ─── Fonts + global styles ─────────────────────────────────────────── */
const GUIDE_STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

.img-guide * { box-sizing: border-box; }

.ig-sidebar-nav {
  display: flex !important;
  flex-direction: column !important;
  gap: 2px;
}

.img-guide-nav-btn {
  display: flex !important; align-items: center; gap: 9px;
  width: 100% !important; padding: 7px 10px; border-radius: 7px;
  font-size: 13px; font-weight: 500; color: #78716c;
  cursor: pointer; border: none; background: none; text-align: left;
  font-family: 'Plus Jakarta Sans', sans-serif;
  transition: background 0.12s, color 0.12s;
  white-space: nowrap;
}
.img-guide-nav-btn:hover { background: #f5f4f2; color: #1c1917; }
.img-guide-nav-btn.active { background: #f0fdf4; color: #15803d; font-weight: 700; }

.ig-section { background: #fff; border-radius: 16px; border: 1px solid #e7e5e0; overflow: hidden; margin-bottom: 36px; scroll-margin-top: 80px; }

.ig-specs-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 12px; padding: 0 24px 24px; }

.ig-spec-card {
  background: #faf9f7; border: 1px solid #e7e5e0; border-radius: 11px;
  padding: 18px 14px 14px; display: flex; flex-direction: column; gap: 14px;
}

.ig-qt th {
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  color: #a8a29e; padding: 11px 14px; text-align: left; background: #faf9f7; white-space: nowrap;
}
.ig-qt td {
  padding: 10px 14px; font-size: 12px; color: #57534e; border-bottom: 1px solid #f5f4f2;
  font-family: 'Courier New', monospace;
}
.ig-qt tr:last-child td { border-bottom: none; }
.ig-qt td:first-child { font-family: 'Plus Jakarta Sans', sans-serif; font-weight: 600; color: #1c1917; font-size: 13px; }
.ig-qt tr:hover td { background: #faf9f7; }

.ig-concept-card { background: #fff; border: 1px solid #e7e5e0; border-radius: 12px; padding: 20px; flex: 1; min-width: 0; }

@media (max-width: 880px) {
  .ig-layout { flex-direction: column !important; padding: 0 16px !important; }
  .ig-sidebar { display: none !important; }
  .ig-specs-grid { grid-template-columns: repeat(2, 1fr) !important; }
}
`;

/* ─── AspectBox: renders a true-proportional frame ─────────────────── */
// pw/ph = actual pixel dimensions (used to compute exact ratio)
// label = card label, dims = dimension string, accent = brand color
const AspectBox = ({ pw, ph, label, dims, accent, ratioLabel }) => {
  const MAX_W = 100; // max width of the visual box
  const MAX_H = 108; // max height of the visual box
  const ratio = ph / pw;
  // Scale to fit within MAX_W × MAX_H while preserving ratio
  let boxW, boxH;
  if (ratio * MAX_W <= MAX_H) {
    boxW = MAX_W;
    boxH = Math.round(MAX_W * ratio);
  } else {
    boxH = MAX_H;
    boxW = Math.round(MAX_H / ratio);
  }
  // Enforce minimum visible size
  boxW = Math.max(boxW, 14);
  boxH = Math.max(boxH, 14);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      {/* Fixed-height container so all cards align regardless of orientation */}
      <div style={{ height: MAX_H + 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{
          width: boxW, height: boxH,
          background: `${accent}14`,
          border: `1.5px dashed ${accent}60`,
          borderRadius: 4,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 9, fontWeight: 700, color: accent, letterSpacing: '0.03em', fontFamily: 'monospace', lineHeight: 1 }}>
            {ratioLabel || `${pw}:${ph}`}
          </span>
        </div>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#292524', lineHeight: 1.3 }}>{label}</div>
        <div style={{ fontSize: 10, color: '#a8a29e', fontFamily: 'monospace', marginTop: 2 }}>{dims}</div>
      </div>
    </div>
  );
};

/* ─── ProTip callout ────────────────────────────────────────────────── */
const ProTip = ({ children }) => (
  <div style={{
    background: '#fffbeb', border: '1px solid #fde68a',
    borderLeft: '4px solid #f59e0b', borderRadius: 8,
    padding: '12px 16px', margin: '4px 24px 24px',
    fontSize: 13, color: '#78350f', lineHeight: 1.65,
  }}>
    <span style={{ fontWeight: 700, color: '#b45309' }}>💡 Pro Tip: </span>
    {children}
  </div>
);

/* ─── Section header ────────────────────────────────────────────────── */
const PlatformHeader = ({ icon: Icon, name, subtitle, accent, bg }) => (
  <div style={{
    display: 'flex', alignItems: 'center', gap: 16,
    padding: '20px 24px',
    background: bg || `${accent}0a`,
    borderBottom: `1px solid ${accent}22`,
  }}>
    <div style={{
      width: 46, height: 46, borderRadius: 11,
      background: accent, flexShrink: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: `0 4px 14px ${accent}44`,
    }}>
      <Icon style={{ color: '#fff', fontSize: 21 }} />
    </div>
    <div>
      <h2 style={{ margin: 0, fontSize: 21, fontWeight: 800, color: '#1c1917', fontFamily: "'Syne', sans-serif", letterSpacing: '-0.02em' }}>{name}</h2>
      <p style={{ margin: 0, fontSize: 12, color: '#78716c', marginTop: 2 }}>{subtitle}</p>
    </div>
  </div>
);

/* ─── Individual spec card ──────────────────────────────────────────── */
// pw/ph = actual pixel dimensions; ratioLabel = human-readable ratio string
const SpecCard = ({ pw, ph, ratioLabel, label, dims, accent, title, note }) => (
  <div style={{
    background: '#faf9f7', border: '1px solid #e7e5e0', borderRadius: 11,
    padding: '18px 14px 14px', display: 'flex', flexDirection: 'column', gap: 14,
    borderTop: `3px solid ${accent}55`,
  }}>
    <div style={{ display: 'flex', justifyContent: 'center' }}>
      <AspectBox pw={pw} ph={ph} ratioLabel={ratioLabel} label={label} dims={dims} accent={accent} />
    </div>
    <div>
      <div style={{ fontSize: 12, fontWeight: 700, color: '#1c1917', marginBottom: 4, lineHeight: 1.3 }}>{title}</div>
      <div style={{ fontSize: 11.5, color: '#78716c', lineHeight: 1.6 }}>{note}</div>
    </div>
  </div>
);

/* ─── Main component ────────────────────────────────────────────────── */
const SocialMediaImageGuide = () => {
  const [activeId, setActiveId] = useState('intro');
  const [hoveredRow, setHoveredRow] = useState(null);

  useEffect(() => {
    const ids = ['intro', 'quickref', 'instagram', 'facebook', 'twitter', 'linkedin', 'tiktok', 'youtube', 'pinterest', 'threads', 'bluesky', 'tips'];
    const observer = new IntersectionObserver(
      (entries) => entries.forEach(e => { if (e.isIntersecting) setActiveId(e.target.id); }),
      { rootMargin: '-20% 0px -70% 0px' }
    );
    ids.forEach(id => { const el = document.getElementById(id); if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, []);

  const scrollTo = id => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const navItems = [
    { id: 'intro',     label: 'Overview' },
    { id: 'quickref',  label: 'Quick Reference' },
    { id: 'instagram', label: 'Instagram',  Icon: FaInstagram, accent: '#E1306C' },
    { id: 'facebook',  label: 'Facebook',   Icon: FaFacebook,  accent: '#1877F2' },
    { id: 'twitter',   label: 'Twitter / X', Icon: FaTwitter,  accent: '#000000' },
    { id: 'linkedin',  label: 'LinkedIn',   Icon: FaLinkedin,  accent: '#0A66C2' },
    { id: 'tiktok',    label: 'TikTok',     Icon: SiTiktok,    accent: '#111111' },
    { id: 'youtube',   label: 'YouTube',    Icon: FaYoutube,   accent: '#FF0000' },
    { id: 'pinterest', label: 'Pinterest',  Icon: FaPinterest, accent: '#E60023' },
    { id: 'threads',   label: 'Threads',    Icon: FaThreads,   accent: '#111111' },
    { id: 'bluesky',   label: 'Bluesky',    Icon: SiBluesky,   accent: '#0085FF' },
    { id: 'tips',      label: 'Best Practices' },
  ];

  const editorialText = (text) => (
    <p style={{ fontSize: 14, color: '#57534e', lineHeight: 1.75, margin: '16px 24px 0', fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
      {text}
    </p>
  );

  return (
    <div className="img-guide" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", background: '#faf9f6', minHeight: '100vh' }}>
      <style>{GUIDE_STYLES}</style>

      {/* ── Sticky top nav ──────────────────────────────────────────── */}
      <nav style={{ background: '#fff', borderBottom: '1px solid #e7e5e0', position: 'sticky', top: 0, zIndex: 100, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
        <div style={{ maxWidth: 1260, margin: '0 auto', padding: '0 24px', height: 54, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}>
            <div style={{ width: 28, height: 28, background: '#16a34a', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: '#fff', fontWeight: 800, fontSize: 13, fontFamily: "'Syne', sans-serif" }}>S</span>
            </div>
            <span style={{ fontSize: 15, fontWeight: 700, color: '#1c1917', fontFamily: "'Syne', sans-serif" }}>Unravler</span>
          </Link>
          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <span style={{ fontSize: 10.5, fontWeight: 700, color: '#15803d', background: '#f0fdf4', padding: '3px 10px', borderRadius: 20, border: '1px solid #bbf7d0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Updated 2026
            </span>
            <Link to="/resources/social-media-video-guide" style={{ fontSize: 13, color: '#78716c', textDecoration: 'none', fontWeight: 600 }}>
              Video Guide →
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Two-column layout ───────────────────────────────────────── */}
      <div className="ig-layout" style={{ maxWidth: 1260, margin: '0 auto', padding: '0 24px', display: 'flex', gap: 44, alignItems: 'flex-start' }}>

        {/* ── Sidebar ─────────────────────────────────────────────── */}
        <aside className="ig-sidebar" style={{ width: 210, flexShrink: 0, position: 'sticky', top: 70, paddingTop: 36, paddingBottom: 40 }}>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#c4bfba', marginBottom: 6, paddingLeft: 10 }}>
            On this page
          </div>
          <nav className="ig-sidebar-nav" style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
            {navItems.map(({ id, label, Icon, accent }) => (
              <button
                key={id}
                className={`img-guide-nav-btn${activeId === id ? ' active' : ''}`}
                onClick={() => scrollTo(id)}
                style={{
                  display: 'flex', flexDirection: 'row', alignItems: 'center',
                  width: '100%', gap: 9, padding: '7px 10px', borderRadius: 7,
                  fontSize: 13, fontWeight: activeId === id ? 700 : 500,
                  color: activeId === id ? '#15803d' : '#78716c',
                  background: activeId === id ? '#f0fdf4' : 'transparent',
                  border: 'none', cursor: 'pointer', textAlign: 'left',
                  fontFamily: "'Plus Jakarta Sans', sans-serif",
                  whiteSpace: 'nowrap', boxSizing: 'border-box',
                }}
              >
                {Icon && (
                  <Icon style={{ fontSize: 13, color: activeId === id ? '#15803d' : (accent || '#a8a29e'), opacity: activeId === id ? 1 : 0.7, flexShrink: 0 }} />
                )}
                <span style={{ flex: 1 }}>{label}</span>
              </button>
            ))}
          </nav>

          <div style={{ marginTop: 32, paddingLeft: 10, paddingRight: 6 }}>
            <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#c4bfba', marginBottom: 10 }}>
              Related
            </div>
            <Link to="/resources/social-media-video-guide" style={{ fontSize: 12, color: '#0A66C2', textDecoration: 'none', fontWeight: 600, display: 'block', lineHeight: 1.5 }}>
              Video Size Guide →
            </Link>
          </div>
        </aside>

        {/* ── Main content ────────────────────────────────────────── */}
        <main style={{ flex: 1, minWidth: 0, paddingTop: 44, paddingBottom: 80 }}>

          {/* Hero */}
          <section id="intro" style={{ scrollMarginTop: 80, marginBottom: 52 }}>
            <h1 style={{
              fontFamily: "'Syne', sans-serif",
              fontSize: 'clamp(30px, 5vw, 50px)',
              fontWeight: 800, color: '#1c1917',
              lineHeight: 1.08, letterSpacing: '-0.03em',
              margin: '0 0 16px',
            }}>
              Social Media<br />
              <span style={{ color: '#16a34a' }}>Image Size Guide</span>
            </h1>
            <p style={{ fontSize: 16, color: '#78716c', lineHeight: 1.75, margin: '0 0 32px', maxWidth: 600 }}>
              Getting dimensions right is one of those details that quietly separates professional accounts from amateur ones.
              Blurry profile photos, stretched cover images, and awkward crops all erode credibility.
              This guide covers every image format for every major platform — updated for 2026.
            </p>

            {/* Key concepts */}
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
              <div className="ig-concept-card">
                <div style={{ fontSize: 22, marginBottom: 10 }}>📐</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#1c1917', marginBottom: 5 }}>What is Aspect Ratio?</div>
                <div style={{ fontSize: 13, color: '#78716c', lineHeight: 1.65 }}>
                  The relationship between width and height, written as <strong>width:height</strong>. A&nbsp;1:1 is a perfect square. A&nbsp;9:16 is tall vertical.
                  A&nbsp;16:9 is wide horizontal. Aspect ratio determines <em>shape</em>; resolution determines <em>sharpness</em>.
                </div>
              </div>
              <div className="ig-concept-card">
                <div style={{ fontSize: 22, marginBottom: 10 }}>🔬</div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#1c1917', marginBottom: 5 }}>What are Pixels?</div>
                <div style={{ fontSize: 13, color: '#78716c', lineHeight: 1.65 }}>
                  The unit of digital image resolution, written as <strong>width × height</strong>. More pixels means a sharper image.
                  Uploading at <strong>1080px wide</strong> is the universal safe minimum across every platform in this guide.
                </div>
              </div>
            </div>
          </section>

          {/* Quick reference table */}
          <section id="quickref" style={{ scrollMarginTop: 80, marginBottom: 48 }}>
            <h2 style={{ fontFamily: "'Syne', sans-serif", fontSize: 19, fontWeight: 800, color: '#1c1917', margin: '0 0 14px', letterSpacing: '-0.02em' }}>
              Quick Reference
            </h2>
            <div style={{ background: '#fff', border: '1px solid #e7e5e0', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 600 }}>
                  <thead>
                    <tr>
                      {['Platform', 'Profile Photo', 'Cover / Banner', 'Best Feed Post', 'Story / Reel', 'Link Preview'].map(h => (
                        <th key={h} style={{
                          fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
                          color: '#a8a29e', padding: '12px 14px', textAlign: 'left',
                          background: '#faf9f7', whiteSpace: 'nowrap',
                          borderBottom: '1px solid #e7e5e0',
                        }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { name: 'Instagram',   accent: '#E1306C', Icon: FaInstagram,  profile: '320 × 320',    cover: '—',           feed: '1080 × 1350',      story: '1080 × 1920', link: '—' },
                      { name: 'Facebook',    accent: '#1877F2', Icon: FaFacebook,   profile: '320 × 320',    cover: '851 × 315',   feed: '1080 × 1350',      story: '1080 × 1920', link: '1200 × 630' },
                      { name: 'Twitter / X', accent: '#000000', Icon: FaTwitter,    profile: '400 × 400',    cover: '1500 × 500',  feed: '1600 × 900',       story: '—',           link: '1200 × 628' },
                      { name: 'LinkedIn',    accent: '#0A66C2', Icon: FaLinkedin,   profile: '400 × 400',    cover: '1584 × 396',  feed: '1080 × 1350',      story: '—',           link: '1200 × 627' },
                      { name: 'TikTok',      accent: '#010101', Icon: SiTiktok,     profile: '200 × 200',    cover: '—',           feed: '1080 × 1920',      story: '1080 × 1920', link: '—' },
                      { name: 'YouTube',     accent: '#FF0000', Icon: FaYoutube,    profile: '800 × 800',    cover: '2560 × 1440', feed: '1280 × 720',       story: '—',           link: '—' },
                      { name: 'Pinterest',   accent: '#E60023', Icon: FaPinterest,  profile: '165 × 165',    cover: '800 × 450',   feed: '1000 × 1500',      story: '—',           link: '—' },
                      { name: 'Threads',     accent: '#000000', Icon: FaThreads,    profile: '320 × 320',    cover: '—',           feed: 'Any (4:5 rec.)',   story: '—',           link: '1200 × 600' },
                      { name: 'Bluesky',     accent: '#0085ff', Icon: SiBluesky,    profile: '400 × 400',    cover: '1500 × 500',  feed: 'Any (4:3 rec.)',   story: '—',           link: '1200 × 627' },
                    ].map(({ name, accent, Icon, profile, cover, feed, story, link }, i, arr) => {
                      const isLast = i === arr.length - 1;
                      const isHovered = hoveredRow === i;
                      const tdBase = {
                        padding: '10px 14px',
                        fontSize: 12,
                        color: isHovered ? '#44403c' : '#78716c',
                        borderBottom: isLast ? 'none' : '1px solid #f5f4f2',
                        fontFamily: "'Courier New', monospace",
                        whiteSpace: 'nowrap',
                        background: isHovered ? '#faf9f7' : 'transparent',
                        transition: 'background 0.1s, color 0.1s',
                      };
                      const tdDash = { ...tdBase, color: '#d4d0cc', letterSpacing: 0 };
                      return (
                        <tr
                          key={i}
                          onMouseEnter={() => setHoveredRow(i)}
                          onMouseLeave={() => setHoveredRow(null)}
                        >
                          <td style={{
                            ...tdBase,
                            fontFamily: "'Plus Jakarta Sans', sans-serif",
                            fontWeight: 600,
                            color: '#1c1917',
                            fontSize: 13,
                          }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                              <span style={{
                                width: 24, height: 24, borderRadius: 6,
                                background: `${accent}18`,
                                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                flexShrink: 0,
                              }}>
                                <Icon style={{ fontSize: 12, color: accent }} />
                              </span>
                              {name}
                            </span>
                          </td>
                          {[profile, cover, feed, story, link].map((val, j) => (
                            <td key={j} style={val === '—' ? tdDash : tdBase}>{val}</td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* ══ INSTAGRAM ══════════════════════════════════════════════ */}
          <section id="instagram" className="ig-section">
            <PlatformHeader icon={FaInstagram} name="Instagram" subtitle="Profile · Feed · Stories · Reels · Carousels" accent="#E1306C" bg="linear-gradient(135deg, #fdf2f8 0%, #faf9f7 100%)" />
            {editorialText(
              'Instagram is the most image-forward platform, which means image quality and cropping matter more here than anywhere else. In January 2025, Instagram shifted its default profile grid from 1:1 square thumbnails to 3:4 vertical — so tall images now show more of themselves when someone visits your profile. For Reels and Stories, 9:16 is the only format that fills the screen; anything else gets letterboxed.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={320} ph={320} ratioLabel="1:1" label="Profile" dims="320×320 px" accent="#E1306C"
                title="320 × 320 pixels"
                note="Displayed at 110×110. Cropped to circle — keep faces and logos centered, away from corners. Upload larger (800×800) for sharper display on retina screens." />
              <SpecCard pw={1080} ph={1350} ratioLabel="4:5" label="Feed Post" dims="1080×1350 px" accent="#E1306C"
                title="1080 × 1350 px · 4:5"
                note="The sweet spot. Takes the most screen space in the feed. Also supports 1:1 square (1080×1080) and 1.91:1 horizontal (1080×566)." />
              <SpecCard pw={1080} ph={1440} ratioLabel="3:4" label="Grid Thumbnail" dims="1080×1440 px" accent="#E1306C"
                title="1080 × 1440 px · 3:4"
                note="New 2025 tall grid. Profile thumbnails are now cropped at 3:4. Design posts to look intentional in this crop, not just as an afterthought." />
              <SpecCard pw={1080} ph={1920} ratioLabel="9:16" label="Stories & Reels" dims="1080×1920 px" accent="#E1306C"
                title="1080 × 1920 px · 9:16"
                note="Full-screen vertical. The top 310px and bottom 310px are covered by UI overlays (profile name, reactions). Keep key content in the safe center zone." />
            </div>
            <ProTip>
              Upload images at exactly 1080px wide. Instagram recompresses anything larger, and smaller images look blurry on retina displays.
              For carousel posts, every slide must use the same aspect ratio — mixing square and vertical in one carousel is not supported.
            </ProTip>
          </section>

          {/* ══ FACEBOOK ═══════════════════════════════════════════════ */}
          <section id="facebook" className="ig-section">
            <PlatformHeader icon={FaFacebook} name="Facebook" subtitle="Profile · Cover · Feed · Stories · Events · Groups" accent="#1877F2" />
            {editorialText(
              'Facebook has more image types than any other platform — profiles, pages, groups, events, and ads all have different specs. The platform renders images differently on desktop versus mobile, so designing to the safe area is critical for cover photos. Profile pictures are cropped into circles, so important content must stay away from the corners.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={320} ph={320} ratioLabel="1:1" label="Profile" dims="320×320 px" accent="#1877F2"
                title="320 × 320 pixels"
                note="Displayed at 196×196 on desktop, 36×36 in the news feed. Cropped to circle. Important content should stay in the center 65% of the frame." />
              <SpecCard pw={851} ph={315} ratioLabel="2.7:1" label="Cover Photo" dims="851×315 px" accent="#1877F2"
                title="851 × 315 px · 2.7:1"
                note="For profiles and pages. Mobile shows 640×360. Your profile picture overlaps the bottom-left corner on desktop — don't place text there." />
              <SpecCard pw={1080} ph={1350} ratioLabel="4:5" label="Feed Post" dims="1080×1350 px" accent="#1877F2"
                title="1080 × 1350 px · 4:5"
                note="Vertical 4:5 gets the most screen space and performs best for reach. Square 1080×1080 is also reliable. Minimum 600px width." />
              <SpecCard pw={1080} ph={1920} ratioLabel="9:16" label="Stories" dims="1080×1920 px" accent="#1877F2"
                title="1080 × 1920 px · 9:16"
                note="Keep top 250px and bottom 340px clear. Those areas are covered by the profile info overlay and the reply bar respectively." />
              <SpecCard pw={1200} ph={630} ratioLabel="1.9:1" label="Link Preview" dims="1200×630 px" accent="#1877F2"
                title="1200 × 630 px · OG image"
                note="Set via Open Graph meta tags. This image appears whenever a link is shared. Min 600×314 but 1200×630 looks sharpest on high-DPI screens." />
              <SpecCard pw={1640} ph={856} ratioLabel="1.9:1" label="Group Cover" dims="1640×856 px" accent="#1877F2"
                title="1640 × 856 px (Groups)"
                note="Groups have a unique wider cover format. Event covers use 1920×1005. Both are separate from personal profile and page covers." />
            </div>
            <ProTip>
              Design Facebook cover photos with your key content in the centered 60% of the image. Mobile crops the sides and bottom significantly.
              A 820×360 master canvas with the subject in the center works well across both desktop (851×315) and mobile (640×360) renderings.
            </ProTip>
          </section>

          {/* ══ TWITTER/X ══════════════════════════════════════════════ */}
          <section id="twitter" className="ig-section">
            <PlatformHeader icon={FaTwitter} name="Twitter / X" subtitle="Profile · Header · Feed Posts · Link Cards" accent="#000000" bg="linear-gradient(135deg, #f8f8f8 0%, #faf9f7 100%)" />
            {editorialText(
              'Twitter/X has a unique challenge: images in the timeline are cropped to a 2:1 horizontal strip by default — the full image only appears on click. The header photo uses an extreme 3:1 ratio that renders very differently on desktop vs. mobile, so keep all text and logos vertically centered and never extend them to the edges.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={400} ph={400} ratioLabel="1:1" label="Profile" dims="400×400 px" accent="#000000"
                title="400 × 400 pixels"
                note="Max 2MB. JPG or PNG. Cropped to circle for regular accounts. Business accounts can have square display. Keep subject in center 75%." />
              <SpecCard pw={1500} ph={500} ratioLabel="3:1" label="Header Image" dims="1500×500 px" accent="#000000"
                title="1500 × 500 px · 3:1"
                note="Far wider than any other platform. Displayed at 600×200 on mobile. Keep all important content in the center 60% horizontally and 50% vertically." />
              <SpecCard pw={1600} ph={900} ratioLabel="16:9" label="Feed Image" dims="1600×900 px" accent="#000000"
                title="1600 × 900 px · 16:9"
                note="Attach up to 4 images per tweet. Supports 16:9, 1:1, 4:5, 3:4. When 4 are attached, they display in a 2×2 grid with each image cropped to fit." />
              <SpecCard pw={1200} ph={628} ratioLabel="1.9:1" label="Link Card" dims="1200×628 px" accent="#000000"
                title="1200 × 628 px · OG image"
                note="Requires Twitter Card meta tags. The summary_large_image type shows a prominent banner. Without it, only a small thumbnail appears next to the link." />
            </div>
            <ProTip>
              For images that need to look good in the timeline preview, place your subject in the center of the frame.
              Twitter/X auto-crops to a 2:1 ratio in the feed but shows the full image on expand — design for both states simultaneously.
            </ProTip>
          </section>

          {/* ══ LINKEDIN ═══════════════════════════════════════════════ */}
          <section id="linkedin" className="ig-section">
            <PlatformHeader icon={FaLinkedin} name="LinkedIn" subtitle="Personal Profile · Company Page · Posts · Articles" accent="#0A66C2" />
            {editorialText(
              'LinkedIn has two completely different sets of dimensions: one for personal profiles and one for company pages. Cover photo aspect ratios differ dramatically — personal is 4:1, company page is nearly 6:1. The platform also differs from others in that document-style "carousel" posts (uploaded as PDFs) consistently get 3× more organic reach than image posts.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={400} ph={400} ratioLabel="1:1" label="Profile Photo" dims="400×400 px" accent="#0A66C2"
                title="400 × 400 pixels (min)"
                note="Max 8MB. Displayed at 400×400 on profile, 48×48 in posts. Cropped to circle. A high-contrast headshot with a plain background works best." />
              <SpecCard pw={1584} ph={396} ratioLabel="4:1" label="Personal Cover" dims="1584×396 px" accent="#0A66C2"
                title="1584 × 396 px · 4:1"
                note="Max 8MB. Your profile photo overlaps the left side on desktop — avoid putting text on the left 15%. Keep important content in the center 70%." />
              <SpecCard pw={1128} ph={191} ratioLabel="6:1" label="Company Cover" dims="1128×191 px" accent="#0A66C2"
                title="1128 × 191 px · 6:1"
                note="Extremely wide. Use a brand color sweep with your logo centered. No room for dense text at this ratio. Max 4MB." />
              <SpecCard pw={1080} ph={1350} ratioLabel="4:5" label="Feed Post" dims="1080×1350 px" accent="#0A66C2"
                title="1080 × 1350 px · 4:5"
                note="LinkedIn supports 3:1 to 4:5. Vertical 4:5 takes the most feed space on mobile. Square 1:1 is safest for multi-image carousels." />
              <SpecCard pw={1200} ph={627} ratioLabel="1.9:1" label="Link Preview" dims="1200×627 px" accent="#0A66C2"
                title="1200 × 627 px · OG image"
                note="Shows as a landscape banner when sharing blog posts or landing pages. Controlled via og:image meta tag. Title text is overlaid below the image." />
              <SpecCard pw={300} ph={300} ratioLabel="1:1" label="Company Logo" dims="300×300 px" accent="#0A66C2"
                title="300 × 300 pixels (min)"
                note="Max 4MB. Appears on company page, search results, and alongside posts. Displayed as a circle on some views — keep the logo centered." />
            </div>
            <ProTip>
              LinkedIn documents uploaded natively as PDFs display as swipeable carousels and get dramatically more reach than static image posts.
              Use 1:1 slides at 1080×1080 for maximum visual consistency across the carousel.
            </ProTip>
          </section>

          {/* ══ TIKTOK ═════════════════════════════════════════════════ */}
          <section id="tiktok" className="ig-section">
            <PlatformHeader icon={SiTiktok} name="TikTok" subtitle="Profile · Photo Carousels · Video Thumbnails" accent="#111111" bg="linear-gradient(135deg, #f0fafa 0%, #faf9f7 100%)" />
            {editorialText(
              'TikTok is a vertical-only platform — 9:16 is the only format that fills the screen without black bars. Beyond video, TikTok supports photo carousels of up to 35 images, which have become increasingly popular for tutorials, outfit inspiration, and multi-step content. Both formats must be vertical to avoid blank space at the sides.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={200} ph={200} ratioLabel="1:1" label="Profile Photo" dims="200×200 px" accent="#111111"
                title="200 × 200 pixels (rec.)"
                note="Minimum accepted size is 20×20. Upload at least 200×200 for quality. Cropped to circle. Animated GIFs are supported for profile photos." />
              <SpecCard pw={1080} ph={1920} ratioLabel="9:16" label="Photo Posts" dims="1080×1920 px" accent="#EE1D52"
                title="1080 × 1920 px · 9:16"
                note="The only format that fills the screen completely. 4:5 is accepted but shows black bars. Up to 35 photos per carousel post." />
              <SpecCard pw={1080} ph={1920} ratioLabel="9:16" label="Video Cover" dims="1080×1920 px" accent="#69C9D0"
                title="1080 × 1920 px · thumbnail"
                note="The first frame or a custom image shown in your profile grid. Keep text above center — the bottom 200px is covered by the caption in the feed view." />
            </div>
            <ProTip>
              TikTok crops video thumbnails aggressively in the profile grid. Set a custom cover image on every video to control your grid aesthetic.
              The guaranteed safe zone is the center 80% of the frame — avoid the top and bottom 10% for any text or key visual elements.
            </ProTip>
          </section>

          {/* ══ YOUTUBE ════════════════════════════════════════════════ */}
          <section id="youtube" className="ig-section">
            <PlatformHeader icon={FaYoutube} name="YouTube" subtitle="Channel Art · Profile · Thumbnails · Community Posts" accent="#FF0000" bg="linear-gradient(135deg, #fff5f5 0%, #faf9f7 100%)" />
            {editorialText(
              'YouTube\'s channel banner is unique because it renders at completely different sizes across devices. The 2560×1440 upload appears as a 2560×423 strip on TV, full dimensions on desktop, and just 1546×423 centered on tablets. Design for the guaranteed center safe zone. Thumbnails are arguably your most impactful image — they directly drive click-through rates on every surface YouTube shows your video.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={800} ph={800} ratioLabel="1:1" label="Profile Photo" dims="800×800 px" accent="#FF0000"
                title="800 × 800 pixels"
                note="Max 15MB. Displayed at 98×98 on channel page, 36×36 in comments. Cropped to circle. Use a high-contrast headshot or a bold logo on a solid background." />
              <SpecCard pw={2560} ph={1440} ratioLabel="16:9" label="Channel Banner" dims="2560×1440 px" accent="#FF0000"
                title="2560 × 1440 px · 16:9"
                note="Min 2048×1152. Max 6MB. The center 1546×423px safe zone is the only portion guaranteed to show on all devices. Keep all text and logos inside it." />
              <SpecCard pw={1280} ph={720} ratioLabel="16:9" label="Thumbnail" dims="1280×720 px" accent="#FF0000"
                title="1280 × 720 px · 16:9"
                note="Max 2MB — JPG, PNG, or GIF. High contrast, expressive faces, bold text (under 6 words), and a clear focal point are the proven formula for higher CTR." />
              <SpecCard pw={1080} ph={1080} ratioLabel="1:1" label="Community Post" dims="Any · 1:1 rec." accent="#FF0000"
                title="Square recommended"
                note="Community tab posts support any image but 1:1 square displays most consistently. Used for polls, announcements, and behind-the-scenes updates." />
            </div>
            <ProTip>
              Design your banner in layers: text and logo strictly inside the center 1546×423px safe zone, decorative fill extending to 2560px wide.
              The areas outside the safe zone only show on desktop at full resolution — they get cropped on TV, tablet, and mobile.
            </ProTip>
          </section>

          {/* ══ PINTEREST ══════════════════════════════════════════════ */}
          <section id="pinterest" className="ig-section">
            <PlatformHeader icon={FaPinterest} name="Pinterest" subtitle="Profile · Cover · Pins · Idea Pins" accent="#E60023" bg="linear-gradient(135deg, #fff5f5 0%, #faf9f7 100%)" />
            {editorialText(
              'Pinterest is one of the few platforms where vertical images have a real algorithmic advantage — and where getting the ratio wrong actively hurts your distribution. The algorithm limits reach for images shorter than 2:3, and also for images taller than 1500px. The 1000×1500 pin at exactly 2:3 is the safest choice. Low-resolution images under 600px wide are also deprioritized.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={165} ph={165} ratioLabel="1:1" label="Profile Photo" dims="165×165 px" accent="#E60023"
                title="165 × 165 pixels"
                note="The smallest profile photo of any platform. Upload at 400×400 for sharp display — Pinterest will scale it down. Cropped to circle." />
              <SpecCard pw={800} ph={450} ratioLabel="16:9" label="Profile Cover" dims="800×450 px" accent="#E60023"
                title="800 × 450 px · 16:9"
                note="Min 800×450. Shows on your profile page. If none is set, Pinterest shows a collage of your boards. Upload at 1600×900 for retina quality." />
              <SpecCard pw={1000} ph={1500} ratioLabel="2:3" label="Standard Pin" dims="1000×1500 px" accent="#E60023"
                title="1000 × 1500 px · 2:3"
                note="Pinterest's signature vertical format. Max 20MB (web), 1GB (app). The algorithm rewards this exact ratio. Avoid going taller than 1500px or wider than 1:1." />
              <SpecCard pw={1000} ph={1000} ratioLabel="1:1" label="Square Pin" dims="1000×1000 px" accent="#E60023"
                title="1000 × 1000 px · 1:1"
                note="Alternate square format. Supported but gets less visual prominence than vertical pins in the masonry grid. Horizontal pins are heavily penalized." />
            </div>
            <ProTip>
              Pinterest's algorithm actively demotes images taller than 1500px — even though the platform technically accepts them.
              Also: adding a brief text overlay title to your pin images (not just the description) increases saves by up to 30%.
            </ProTip>
          </section>

          {/* ══ THREADS ════════════════════════════════════════════════ */}
          <section id="threads" className="ig-section">
            <PlatformHeader icon={FaThreads} name="Threads" subtitle="Profile · Posts · Link Previews" accent="#111111" bg="linear-gradient(135deg, #f8f8f8 0%, #faf9f7 100%)" />
            {editorialText(
              'Threads is the most relaxed platform for image specs — almost any size is accepted, and dimensions are not strictly enforced. Profile photos sync from Instagram by default, so there is rarely a need to upload separately. Posts support up to 20 images in any combination of sizes, including a unique "pinch" gesture on mobile that blends two adjacent photos together at their edges.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={320} ph={320} ratioLabel="1:1" label="Profile Photo" dims="320×320 px" accent="#000000"
                title="320 × 320 pixels"
                note="Syncs automatically from Instagram. Can be updated independently. Cropped to circle. Max 8MB. Upload at 800×800 for sharp retina rendering." />
              <SpecCard pw={1080} ph={1350} ratioLabel="4:5" label="Post Images" dims="Any · 4:5 rec." accent="#000000"
                title="Any dimensions · up to 20"
                note="Up to 20 images per post, max 8MB each. Vertical 4:5 looks most natural in the feed scroll. Square 1:1 works well for multi-image post grids." />
              <SpecCard pw={1200} ph={600} ratioLabel="2:1" label="Link Preview" dims="1200×600 px" accent="#000000"
                title="1200 × 600 px · 2:1"
                note="Slightly wider ratio than Twitter and Facebook OG images. Set via og:image tag. Shown as a horizontal card below linked text." />
            </div>
            <ProTip>
              Because Threads shares your Instagram profile, optimizing your Instagram profile photo automatically optimizes Threads.
              For post images, Threads renders a 4:5 crop in the feed by default — keep your subject centered to survive that automatic crop.
            </ProTip>
          </section>

          {/* ══ BLUESKY ════════════════════════════════════════════════ */}
          <section id="bluesky" className="ig-section">
            <PlatformHeader icon={SiBluesky} name="Bluesky" subtitle="Profile · Banner · Posts · Link Cards" accent="#0085FF" />
            {editorialText(
              'Bluesky is a newer decentralized social platform without official image dimension documentation. These specs are derived from community testing and observed platform behavior. The interface closely resembles early Twitter: circular profile photo, wide banner, up to 4 images per post. Unlike Instagram, Bluesky preserves original aspect ratios in posts — images are not cropped to a fixed ratio.'
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, padding: '0 16px 20px' }}>
              <SpecCard pw={400} ph={400} ratioLabel="1:1" label="Profile Photo" dims="400×400 px" accent="#0085FF"
                title="400 × 400 px (rec.)"
                note="Based on platform behavior — no official spec. Cropped to circle. Max 1MB per image. JPG or PNG. Upload at 400×400 minimum for sharp display." />
              <SpecCard pw={1500} ph={500} ratioLabel="3:1" label="Banner" dims="1500×500 px" accent="#0085FF"
                title="1500 × 500 px · 3:1"
                note="Cropped to approximately 4:1 on mobile. Keep important content in the center 50% of the image. Visually similar to Twitter/X's header image." />
              <SpecCard pw={1080} ph={810} ratioLabel="4:3" label="Post Images" dims="Any · max 1MB" accent="#0085FF"
                title="Any size · up to 4 images"
                note="Images display in their original aspect ratio — no forced crop. Shown in a 2×2 grid when 4 are attached. Max 1MB per image — compress before uploading." />
              <SpecCard pw={1200} ph={627} ratioLabel="1.9:1" label="Link Card" dims="1200×627 px" accent="#0085FF"
                title="1200 × 627 px · OG image"
                note="Shown prominently when sharing links. Uses og:image tag. If no OG image is set, the link card shows only as a text snippet with the domain name." />
            </div>
            <ProTip>
              Bluesky's 1MB image limit is strict and smaller than every other platform. Compress images with Squoosh or TinyPNG before uploading.
              A 1080×1080 JPG at 85% quality is typically 200–400KB — well within limits with no visible quality loss.
            </ProTip>
          </section>

          {/* ══ BEST PRACTICES ═════════════════════════════════════════ */}
          <section id="tips" style={{ scrollMarginTop: 80 }}>
            <h2 style={{ fontFamily: "'Syne', sans-serif", fontSize: 19, fontWeight: 800, color: '#1c1917', margin: '0 0 18px', letterSpacing: '-0.02em' }}>
              Best Practices
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(270px, 1fr))', gap: 12 }}>
              {[
                { icon: '📏', title: '1080px is the universal width', body: 'Every major platform renders feed images at 1080px wide. Upload at exactly this width — larger gets compressed, smaller gets upscaled and looks blurry on retina screens.' },
                { icon: '📱', title: 'Design vertical-first', body: 'Vertical formats (4:5, 9:16) take 30–40% more screen space on mobile. On mobile-first platforms like Instagram, TikTok, and Threads, vertical always outperforms horizontal.' },
                { icon: '⭕', title: 'Account for the circle crop', body: 'Instagram, Facebook, Twitter, LinkedIn, YouTube, and Bluesky all crop profile photos into circles. Keep faces and logos in the center 70% of the uploaded square.' },
                { icon: '🗂️', title: 'JPG for photos, PNG for graphics', body: 'JPG compresses photography with minimal visible loss. PNG preserves sharp edges for logos and type. Never save a screenshot or graphic as JPG — banding will appear.' },
                { icon: '🎨', title: 'Always export in RGB', body: 'Social platforms only support RGB color mode. CMYK images (print-ready files) will render with washed-out colors. Export in RGB from Photoshop, Figma, or Canva.' },
                { icon: '🔄', title: 'Start from a high-res master', body: 'Create one master image at 3000×3000px or larger, then export resized versions for each platform. Never upscale a small source file — the quality loss is permanent.' },
              ].map((tip, i) => (
                <div key={i} style={{ background: '#fff', border: '1px solid #e7e5e0', borderRadius: 12, padding: '18px 16px', display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                  <div style={{ fontSize: 20, flexShrink: 0, marginTop: 1 }}>{tip.icon}</div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#1c1917', marginBottom: 4, fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{tip.title}</div>
                    <div style={{ fontSize: 13, color: '#78716c', lineHeight: 1.65 }}>{tip.body}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

        </main>
      </div>

      <Footer />
    </div>
  );
};

export default SocialMediaImageGuide;
