import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  FaInstagram, FaFacebook, FaTwitter, FaLinkedin,
  FaYoutube, FaPinterest, FaThreads, FaPlay,
} from 'react-icons/fa6';
import { SiTiktok, SiBluesky, SiMastodon } from 'react-icons/si';
import Footer from '@/components/Footer';

const GUIDE_STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
@media (max-width: 880px) {
  .vg-layout  { flex-direction: column !important; padding: 0 16px !important; }
  .vg-sidebar { display: none !important; }
}
`;

/* ── Spec Row ─────────────────────────────────────────────────────────────── */
const SpecRow = ({ k, v }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 4, fontSize: 10 }}>
    <span style={{ color: '#a8a29e', flexShrink: 0 }}>{k}</span>
    <span style={{ fontFamily: 'monospace', color: '#57534e', textAlign: 'right' }}>{v}</span>
  </div>
);

/* ── Video Aspect Box ─────────────────────────────────────────────────────── */
const VideoAspectBox = ({ pw, ph, ratioLabel, accent }) => {
  const MAX_W = 90, MAX_H = 100;
  const ratio = ph / pw;
  let bw, bh;
  if (ratio * MAX_W <= MAX_H) { bw = MAX_W; bh = Math.round(MAX_W * ratio); }
  else { bh = MAX_H; bw = Math.round(MAX_H / ratio); }
  bw = Math.max(bw, 14); bh = Math.max(bh, 14);
  return (
    <div style={{ height: MAX_H + 4, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{
        width: bw, height: bh,
        background: `${accent}14`, border: `1.5px dashed ${accent}60`,
        borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, position: 'relative',
      }}>
        <FaPlay style={{ fontSize: 10, color: `${accent}99` }} />
        <span style={{
          position: 'absolute', bottom: 2, right: 3,
          fontSize: 8, fontWeight: 700, color: accent, fontFamily: 'monospace', lineHeight: 1,
        }}>{ratioLabel}</span>
      </div>
    </div>
  );
};

/* ── Video Card ───────────────────────────────────────────────────────────── */
const VideoCard = ({ pw, ph, ratioLabel, label, dims, duration, fileSize, fps, formats, note, accent }) => (
  <div style={{
    background: '#faf9f7', border: `1px solid ${accent}28`, borderRadius: 11,
    padding: '16px 14px 14px', display: 'flex', flexDirection: 'column', gap: 10,
  }}>
    <VideoAspectBox pw={pw} ph={ph} ratioLabel={ratioLabel} accent={accent} />
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#292524', lineHeight: 1.3 }}>{label}</div>
      {dims && <div style={{ fontSize: 10, color: '#a8a29e', fontFamily: 'monospace', marginTop: 2 }}>{dims}</div>}
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, borderTop: '1px solid #e7e5e0', paddingTop: 8 }}>
      {duration && duration !== '—' && <SpecRow k="Duration" v={duration} />}
      {fileSize && fileSize !== '—' && <SpecRow k="Max size" v={fileSize} />}
      {fps && fps !== '—' && <SpecRow k="FPS" v={fps} />}
      {formats && formats !== '—' && <SpecRow k="Formats" v={formats} />}
    </div>
    {note && (
      <div style={{
        fontSize: 10, color: '#78716c', background: '#fff',
        borderRadius: 6, padding: '6px 8px', lineHeight: 1.5, border: '1px solid #f0ede8',
      }}>{note}</div>
    )}
  </div>
);

/* ── Platform Header ──────────────────────────────────────────────────────── */
const PlatformHeader = ({ icon: Icon, name, subtitle, accent, bg }) => (
  <div style={{
    background: bg || `linear-gradient(135deg, ${accent}18 0%, #faf9f7 100%)`,
    padding: '20px 24px', borderBottom: '1px solid #e7e5e0',
    display: 'flex', alignItems: 'center', gap: 14,
  }}>
    <div style={{
      width: 44, height: 44, borderRadius: 12, background: `${accent}18`,
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
    }}>
      <Icon style={{ fontSize: 22, color: accent }} />
    </div>
    <div>
      <h2 style={{
        margin: 0, fontFamily: "'Syne', sans-serif", fontSize: 20,
        fontWeight: 800, color: '#1c1917', letterSpacing: '-0.02em',
      }}>{name}</h2>
      <p style={{ margin: 0, fontSize: 12, color: '#a8a29e', marginTop: 2 }}>{subtitle}</p>
    </div>
  </div>
);

/* ── Editorial text ───────────────────────────────────────────────────────── */
const editorialText = (text) => (
  <p style={{
    margin: '0 24px 4px', padding: '16px 0 14px', fontSize: 13,
    color: '#57534e', lineHeight: 1.75, borderBottom: '1px solid #f5f4f2',
  }}>{text}</p>
);

/* ── Pro Tip ──────────────────────────────────────────────────────────────── */
const ProTip = ({ children }) => (
  <div style={{
    margin: '0 16px 20px', background: '#f0fdf4', border: '1px solid #bbf7d0',
    borderRadius: 9, padding: '12px 14px', fontSize: 12, color: '#15803d', lineHeight: 1.65,
  }}>
    <span style={{ fontWeight: 700, marginRight: 6 }}>Pro tip:</span>{children}
  </div>
);

/* ── Info Note ────────────────────────────────────────────────────────────── */
const InfoNote = ({ children }) => (
  <div style={{
    margin: '0 16px 16px', background: '#fefce8', border: '1px solid #fde68a',
    borderRadius: 9, padding: '12px 14px', fontSize: 12, color: '#92400e', lineHeight: 1.65,
  }}>
    <span style={{ fontWeight: 700, marginRight: 6 }}>Note:</span>{children}
  </div>
);

/* ── Section wrapper ──────────────────────────────────────────────────────── */
const Section = ({ id, children }) => (
  <section id={id} style={{
    background: '#fff', borderRadius: 16, border: '1px solid #e7e5e0',
    overflow: 'hidden', marginBottom: 36, scrollMarginTop: 80,
  }}>{children}</section>
);

/* ── Spec grid ────────────────────────────────────────────────────────────── */
const SpecGrid = ({ children }) => (
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10, padding: '0 16px 16px' }}>
    {children}
  </div>
);

/* ── Sub heading ──────────────────────────────────────────────────────────── */
const SubHeading = ({ children }) => (
  <h3 style={{
    fontFamily: "'Plus Jakarta Sans', sans-serif", fontSize: 11, fontWeight: 700,
    color: '#a8a29e', margin: '18px 24px 10px', textTransform: 'uppercase', letterSpacing: '0.07em',
  }}>{children}</h3>
);

/* ═══════════════════════════════════════════════════════════════════════════ */
/*  Main Component                                                             */
/* ═══════════════════════════════════════════════════════════════════════════ */
const SocialMediaVideoGuide = () => {
  const [activeId, setActiveId]   = useState('intro');
  const [hoveredRow, setHoveredRow] = useState(null);

  useEffect(() => {
    const ids = ['intro','quickref','instagram','facebook','twitter','linkedin',
                 'tiktok','youtube','pinterest','threads','bluesky','mastodon','tips'];
    const observer = new IntersectionObserver(
      (entries) => entries.forEach(e => { if (e.isIntersecting) setActiveId(e.target.id); }),
      { rootMargin: '-20% 0px -70% 0px' }
    );
    ids.forEach(id => { const el = document.getElementById(id); if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, []);

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
    { id: 'threads',   label: 'Threads',    Icon: FaThreads,   accent: '#000000' },
    { id: 'bluesky',   label: 'Bluesky',    Icon: SiBluesky,   accent: '#0085ff' },
    { id: 'mastodon',  label: 'Mastodon',   Icon: SiMastodon,  accent: '#6364FF' },
    { id: 'tips',      label: 'Best Practices' },
  ];

  const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });

  /* quick-ref table rows */
  const qrRows = [
    { name: 'Instagram Reels',   accent: '#E1306C', Icon: FaInstagram,  size: '300 MB',  res: '1080 × 1920', ratio: '9:16',     len: '15 min',  fmts: 'MP4, MOV' },
    { name: 'Instagram Stories',  accent: '#E1306C', Icon: FaInstagram,  size: '4 GB',    res: '1080 × 1920', ratio: '9:16',     len: '60 sec',  fmts: 'MP4, MOV, GIF' },
    { name: 'Facebook Reels',    accent: '#1877F2', Icon: FaFacebook,   size: '1 GB',    res: '1080 × 1920', ratio: '9:16',     len: '90 sec',  fmts: 'MP4, MOV, AVI, M4V' },
    { name: 'Twitter / X',       accent: '#000000', Icon: FaTwitter,    size: '512 MB',  res: '1280 × 720',  ratio: '16:9',     len: '140 sec', fmts: 'MP4, MOV, AVI, M4V' },
    { name: 'LinkedIn',          accent: '#0A66C2', Icon: FaLinkedin,   size: '200 MB',  res: '1080 × 1080', ratio: '1:1–16:9', len: '10 min',  fmts: 'MP4, MOV, AVI, M4V' },
    { name: 'TikTok',            accent: '#010101', Icon: SiTiktok,     size: '1 GB',    res: '1080 × 1920', ratio: '9:16',     len: '10 min',  fmts: 'MOV, MP4, WEBM' },
    { name: 'YouTube Shorts',    accent: '#FF0000', Icon: FaYoutube,    size: '10 GB',   res: '1080 × 1920', ratio: '9:16',     len: '3 min',   fmts: 'MOV, MP4, AVI, WEBM' },
    { name: 'Pinterest',         accent: '#E60023', Icon: FaPinterest,  size: '2 GB',    res: '1000 × 1500', ratio: '2:3',      len: '15 min',  fmts: 'MP4, MOV, AVI, M4V' },
    { name: 'Threads',           accent: '#000000', Icon: FaThreads,    size: '1 GB',    res: '1920 px wide', ratio: '9:16',    len: '5 min',   fmts: 'MP4, MOV' },
    { name: 'Bluesky',           accent: '#0085ff', Icon: SiBluesky,    size: '100 MB',  res: '—',           ratio: '9:16',     len: '3 min',   fmts: 'MP4, MOV' },
    { name: 'Mastodon',          accent: '#6364FF', Icon: SiMastodon,   size: '40 MB',   res: '—',           ratio: 'Any',      len: '—',       fmts: 'MP4, M4V, MOV, WEBM' },
  ];

  return (
    <div style={{ minHeight: '100vh', background: '#fefefb', fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
      <style>{GUIDE_STYLES}</style>

      {/* ── Navbar ─────────────────────────────────────────────────────────── */}
      <nav style={{ background: '#fefefb', borderBottom: '1px solid #e7e5e0', position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: 1120, margin: '0 auto', padding: '0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', height: 56 }}>
          <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none' }}>
            <div style={{ width: 30, height: 30, background: '#16a34a', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: '#fff', fontWeight: 800, fontSize: 15, fontFamily: "'Syne', sans-serif" }}>S</span>
            </div>
            <span style={{ fontWeight: 700, fontSize: 16, color: '#1c1917' }}>SocialEntangler</span>
          </Link>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: '#16a34a', background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 20, padding: '3px 10px', letterSpacing: '0.04em' }}>UPDATED 2026</span>
            <Link to="/resources/social-media-image-guide" style={{ fontSize: 13, color: '#78716c', textDecoration: 'none', fontWeight: 500 }}>← Image Guide</Link>
          </div>
        </div>
      </nav>

      {/* ── Layout ─────────────────────────────────────────────────────────── */}
      <div className="vg-layout" style={{ maxWidth: 1120, margin: '0 auto', padding: '32px 24px', display: 'flex', gap: 44, alignItems: 'flex-start' }}>

        {/* ── Sidebar ──────────────────────────────────────────────────────── */}
        <aside className="vg-sidebar" style={{ width: 210, flexShrink: 0, position: 'sticky', top: 70 }}>
          <div style={{ background: '#fff', border: '1px solid #e7e5e0', borderRadius: 12, padding: '14px 10px' }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em', padding: '0 6px 10px' }}>
              ON THIS PAGE
            </div>
            <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {navItems.map(({ id, label, Icon, accent }) => {
                const active = activeId === id;
                return (
                  <button key={id} onClick={() => scrollTo(id)} style={{
                    display: 'flex', flexDirection: 'row', alignItems: 'center',
                    width: '100%', gap: 9, padding: '7px 10px', borderRadius: 7,
                    fontSize: 13, fontWeight: active ? 700 : 500,
                    color: active ? '#15803d' : '#78716c',
                    background: active ? '#f0fdf4' : 'transparent',
                    cursor: 'pointer', border: 'none', textAlign: 'left',
                    fontFamily: "'Plus Jakarta Sans', sans-serif",
                    whiteSpace: 'nowrap', transition: 'background 0.12s, color 0.12s',
                  }}>
                    {Icon
                      ? <Icon style={{ fontSize: 13, color: active ? '#16a34a' : (accent || '#a8a29e'), flexShrink: 0 }} />
                      : <span style={{ width: 13, flexShrink: 0 }} />}
                    <span style={{ flex: 1 }}>{label}</span>
                  </button>
                );
              })}
            </nav>
            <div style={{ borderTop: '1px solid #f0ede8', margin: '12px 6px 4px', paddingTop: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#a8a29e', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>RELATED</div>
              <Link to="/resources/social-media-image-guide" style={{ fontSize: 12, color: '#0A66C2', textDecoration: 'none', fontWeight: 600, padding: '4px 4px', display: 'block' }}>
                Image Size Guide →
              </Link>
            </div>
          </div>
        </aside>

        {/* ── Main Content ─────────────────────────────────────────────────── */}
        <main style={{ flex: 1, minWidth: 0 }}>

          {/* ── Overview ───────────────────────────────────────────────────── */}
          <section id="intro" style={{ scrollMarginTop: 80, marginBottom: 48 }}>
            <h1 style={{ fontFamily: "'Syne', sans-serif", fontSize: 32, fontWeight: 800, color: '#1c1917', margin: '0 0 12px', letterSpacing: '-0.03em', lineHeight: 1.1 }}>
              Social Media Video Guide
            </h1>
            <p style={{ fontSize: 15, color: '#78716c', margin: '0 0 24px', lineHeight: 1.75 }}>
              Verified specs for every platform — resolutions, aspect ratios, file sizes, frame rates, and formats. Built for creators who need the right numbers without the guesswork.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
              {[
                { label: '9:16 Vertical', sub: 'Instagram · TikTok · YouTube Shorts · Threads', accent: '#E1306C' },
                { label: '16:9 Landscape', sub: 'YouTube · Twitter/X', accent: '#FF0000' },
                { label: '1:1 Square', sub: 'LinkedIn · Twitter/X', accent: '#0A66C2' },
                { label: '2:3 Portrait', sub: 'Pinterest', accent: '#E60023' },
              ].map(({ label, sub, accent }) => (
                <div key={label} style={{ background: '#fff', border: '1px solid #e7e5e0', borderRadius: 10, padding: '12px 14px' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#1c1917', fontFamily: "'Syne', sans-serif" }}>{label}</div>
                  <div style={{ fontSize: 11, color: '#a8a29e', marginTop: 4, lineHeight: 1.5 }}>{sub}</div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Quick Reference ────────────────────────────────────────────── */}
          <section id="quickref" style={{ scrollMarginTop: 80, marginBottom: 48 }}>
            <h2 style={{ fontFamily: "'Syne', sans-serif", fontSize: 19, fontWeight: 800, color: '#1c1917', margin: '0 0 14px', letterSpacing: '-0.02em' }}>
              Quick Reference
            </h2>
            <div style={{ background: '#fff', border: '1px solid #e7e5e0', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 660 }}>
                  <thead>
                    <tr>
                      {['Platform', 'Max Size', 'Resolution', 'Aspect Ratio', 'Max Length', 'Formats'].map(h => (
                        <th key={h} style={{
                          fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
                          color: '#a8a29e', padding: '12px 14px', textAlign: 'left',
                          background: '#faf9f7', whiteSpace: 'nowrap', borderBottom: '1px solid #e7e5e0',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {qrRows.map(({ name, accent, Icon, size, res, ratio, len, fmts }, i, arr) => {
                      const isLast = i === arr.length - 1;
                      const isHov  = hoveredRow === i;
                      const td = {
                        padding: '10px 14px', fontSize: 12,
                        color: isHov ? '#44403c' : '#78716c',
                        borderBottom: isLast ? 'none' : '1px solid #f5f4f2',
                        fontFamily: "'Courier New', monospace", whiteSpace: 'nowrap',
                        background: isHov ? '#faf9f7' : 'transparent',
                        transition: 'background 0.1s, color 0.1s',
                      };
                      return (
                        <tr key={i} onMouseEnter={() => setHoveredRow(i)} onMouseLeave={() => setHoveredRow(null)}>
                          <td style={{ ...td, fontFamily: "'Plus Jakarta Sans', sans-serif", fontWeight: 600, color: '#1c1917', fontSize: 13 }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ width: 24, height: 24, borderRadius: 6, background: `${accent}18`, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                <Icon style={{ fontSize: 12, color: accent }} />
                              </span>
                              {name}
                            </span>
                          </td>
                          {[size, res, ratio, len, fmts].map((val, j) => (
                            <td key={j} style={val === '—' ? { ...td, color: '#d4d0cc' } : td}>{val}</td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* ════ INSTAGRAM ════ */}
          <Section id="instagram">
            <PlatformHeader icon={FaInstagram} name="Instagram" subtitle="Reels · Stories · Feed Video · Live" accent="#E1306C" bg="linear-gradient(135deg, #fdf2f8 0%, #faf9f7 100%)" />
            {editorialText("Instagram video is dominated by vertical formats — the 9:16 frame fills the entire phone screen on Reels and Stories. Instagram aggressively recompresses uploads, so keeping your video under 25 Mbps and audio under 128 kbps before uploading prevents a second generation of quality loss. Reels can be up to 15 minutes via direct upload, but the in-app creator caps at 90 seconds.")}
            <SubHeading>Reels</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Reels" dims="1080 × 1920 px"
                duration="3 sec – 15 min" fileSize="300 MB" fps="23–60 FPS" formats="MP4, MOV" accent="#E1306C"
                note="In-app recording capped at 90 sec. Full 15 min only via direct upload." />
            </SpecGrid>
            <SubHeading>Stories</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Stories" dims="1080 × 1920 px"
                duration="Max 60 sec" fileSize="4 GB" fps="23–60 FPS" formats="MP4, MOV, GIF" accent="#E1306C"
                note="4 GB cap per 15-second segment block." />
            </SpecGrid>
            <SubHeading>Feed Video (Carousels)</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1080} ratioLabel="1:1" label="Feed — Square" dims="1080 × 1080 px"
                duration="3 sec – 60 min" fileSize="4 GB" fps="23–60 FPS" formats="MP4, MOV" accent="#E1306C" />
              <VideoCard pw={1080} ph={1350} ratioLabel="4:5" label="Feed — Portrait" dims="1080 × 1350 px"
                duration="3 sec – 60 min" fileSize="4 GB" fps="23–60 FPS" formats="MP4, MOV" accent="#E1306C"
                note="Carousel videos are NOT Reels — they don't appear in the Reels tab." />
            </SpecGrid>
            <SubHeading>Live</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1080} ratioLabel="1:1" label="Instagram Live" dims="1080 × 1080 px"
                duration="Up to 4 hrs" fileSize="—" fps="—" formats="—" accent="#E1306C"
                note="Displays as 9:16 full-screen on viewers' phones. Max session length: 4 hours." />
            </SpecGrid>
            <ProTip>
              Keep bitrate under 25 Mbps and audio under 128 kbps before uploading. Instagram compresses on ingestion — double-compression causes the blocky artifacts you see on low-quality Reels.
            </ProTip>
          </Section>

          {/* ════ FACEBOOK ════ */}
          <Section id="facebook">
            <PlatformHeader icon={FaFacebook} name="Facebook" subtitle="Feed Video · Reels · Stories" accent="#1877F2" />
            {editorialText("Facebook auto-converts any 9:16 video into a Reel — there's no way to post a vertical video as a regular feed post anymore. For horizontal content, 16:9 still works as a traditional feed post. If uploading natively, you can go up to 10 GB; third-party tools typically cap at 1 GB.")}
            <SubHeading>Reels</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Facebook Reels" dims="1080 × 1920 px"
                duration="3 sec – 90 sec" fileSize="1 GB" fps="24–60 FPS" formats="MP4, MOV, AVI, M4V" accent="#1877F2"
                note="Any 9:16 video uploaded to Facebook auto-publishes as a Reel." />
            </SpecGrid>
            <SubHeading>Feed Video</SubHeading>
            <SpecGrid>
              <VideoCard pw={1920} ph={1080} ratioLabel="16:9" label="Feed Video" dims="1080 × 1920 px"
                duration="No limit" fileSize="10 GB (native)" fps="—" formats="MP4, MOV, AVI, M4V" accent="#1877F2"
                note="Horizontal stays as a feed post. Vertical becomes a Reel automatically." />
            </SpecGrid>
            <SubHeading>Stories</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Stories" dims="1080 × 1920 px"
                duration="3 sec – 90 sec" fileSize="1 GB" fps="24–60 FPS" formats="MP4, MOV, AVI, M4V" accent="#1877F2" />
            </SpecGrid>
            <InfoNote>
              Vertical videos (9:16) posted to Facebook are always published as Reels — even if you intended them as regular feed posts. Plan your content format before uploading.
            </InfoNote>
          </Section>

          {/* ════ TWITTER/X ════ */}
          <Section id="twitter">
            <PlatformHeader icon={FaTwitter} name="Twitter / X" subtitle="In-Feed Video" accent="#000000" />
            {editorialText("Twitter/X is one of the few platforms that doesn't autoplay videos — users must click to play. This makes the thumbnail frame far more important here than anywhere else. The 140-second limit applies to standard accounts; Premium subscribers can post longer videos. Up to 4 videos can be attached per post.")}
            <SpecGrid>
              <VideoCard pw={1280} ph={720} ratioLabel="16:9" label="Landscape" dims="1280 × 720 px"
                duration="Max 140 sec" fileSize="512 MB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#000000" />
              <VideoCard pw={720} ph={1280} ratioLabel="9:16" label="Vertical" dims="720 × 1280 px"
                duration="Max 140 sec" fileSize="512 MB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#000000" />
              <VideoCard pw={1080} ph={1080} ratioLabel="1:1" label="Square" dims="1080 × 1080 px"
                duration="Max 140 sec" fileSize="512 MB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#000000" />
            </SpecGrid>
            <InfoNote>
              Videos do NOT autoplay on Twitter/X. MP4 files containing only an audio track (no video) cannot be posted. Max 4 videos per tweet. Videos with 2:1 and 3:4 ratios display fully in timeline.
            </InfoNote>
            <ProTip>
              Third-party tools raise the limit to 1 GB vs 512 MB natively — compress to H.264 MP4 at ~10 Mbps for 1080p to stay within both limits with headroom.
            </ProTip>
          </Section>

          {/* ════ LINKEDIN ════ */}
          <Section id="linkedin">
            <PlatformHeader icon={FaLinkedin} name="LinkedIn" subtitle="Feed Video" accent="#0A66C2" />
            {editorialText("LinkedIn video auto-plays silently in the feed, so your first few frames must communicate the message without sound. The 200 MB file size limit is strict — compress before uploading. LinkedIn doesn't support custom thumbnails via third-party tools, so the first frame acts as the cover image.")}
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Vertical" dims="1080 × 1920 px"
                duration="Max 10 min" fileSize="200 MB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#0A66C2" />
              <VideoCard pw={1080} ph={1080} ratioLabel="1:1" label="Square" dims="1080 × 1080 px"
                duration="Max 10 min" fileSize="200 MB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#0A66C2" />
              <VideoCard pw={1920} ph={1080} ratioLabel="16:9" label="Landscape" dims="1920 × 1080 px"
                duration="Max 10 min" fileSize="200 MB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#0A66C2" />
            </SpecGrid>
            <InfoNote>
              TikTok videos shared as links play natively within LinkedIn posts. YouTube links open YouTube instead of playing inline — keep this in mind when cross-posting.
            </InfoNote>
            <ProTip>
              Videos auto-play silently — design for muted viewing. Add captions or text overlays directly in the video file before uploading; LinkedIn's auto-caption quality varies significantly.
            </ProTip>
          </Section>

          {/* ════ TIKTOK ════ */}
          <Section id="tiktok">
            <PlatformHeader icon={SiTiktok} name="TikTok" subtitle="Feed Video · Carousels · Stories" accent="#111111" bg="linear-gradient(135deg, #f0fafa 0%, #faf9f7 100%)" />
            {editorialText("TikTok's algorithm strongly favors 9:16 vertical video — content in any other aspect ratio gets letterboxed with blurred background fill, which looks unprofessional and signals low effort. Sound is critical: TikTok actively deprioritizes silent videos. Include captions, music, or voiceover in the video file before uploading via third-party tools.")}
            <SubHeading>Feed Video</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Feed Video" dims="1080 × 1920 px"
                duration="3 sec – 10 min" fileSize="1 GB" fps="23–60 FPS" formats="MOV, MP4, WEBM" accent="#111111"
                note="Min dimensions: 360 × 360 px. Description max 150 characters." />
            </SpecGrid>
            <SubHeading>Carousels &amp; Stories</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Carousel" dims="1080 × 1920 px"
                duration="—" fileSize="—" fps="—" formats="Photo or video" accent="#111111"
                note="Up to 35 photos or videos per carousel post." />
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Stories" dims="1080 × 1920 px"
                duration="—" fileSize="—" fps="—" formats="MP4, MOV" accent="#111111" />
            </SpecGrid>
            <ProTip>
              Include sound, captions, and music in the video file before uploading — third-party tools can't add TikTok's native sounds post-upload. The "Promote" feature is disabled when posting via Buffer or similar scheduling tools.
            </ProTip>
          </Section>

          {/* ════ YOUTUBE ════ */}
          <Section id="youtube">
            <PlatformHeader icon={FaYoutube} name="YouTube" subtitle="Shorts · Standard Video" accent="#FF0000" />
            {editorialText("YouTube Shorts extended its maximum length to 3 minutes in 2024, giving creators more room to tell longer stories while staying in the Shorts feed. Standard YouTube videos have no practical file size cap — YouTube re-encodes everything regardless. Custom thumbnails must be uploaded directly on YouTube; third-party tools don't support thumbnail uploads for Shorts.")}
            <SubHeading>YouTube Shorts</SubHeading>
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="YouTube Shorts" dims="1080 × 1920 px"
                duration="Max 3 min" fileSize="10 GB" fps="—" formats="MOV, MP4, MPG, AVI, WEBM" accent="#FF0000"
                note="Custom thumbnails not supported via third-party tools — upload directly on YouTube." />
            </SpecGrid>
            <SubHeading>Standard Video</SubHeading>
            <SpecGrid>
              <VideoCard pw={1920} ph={1080} ratioLabel="16:9" label="Standard Video" dims="1920 × 1080 px"
                duration="No limit" fileSize="No limit" fps="Any" formats="MP4, MOV, AVI, WEBM" accent="#FF0000"
                note="Podcast playlist thumbnails: 1280 × 1280 (1:1), max 10 MB." />
            </SpecGrid>
            <ProTip>
              YouTube recompresses all uploads — uploading at 4K when delivering in 1080p adds upload time with no quality benefit. H.264 MP4 at your target resolution is the right choice for scheduled publishing.
            </ProTip>
          </Section>

          {/* ════ PINTEREST ════ */}
          <Section id="pinterest">
            <PlatformHeader icon={FaPinterest} name="Pinterest" subtitle="Video Pins" accent="#E60023" />
            {editorialText("Pinterest is one of the few platforms where 2:3 vertical video outperforms 9:16 — the slightly shorter format fits better in the masonry grid layout. Videos auto-play by default, but the thumbnail still matters since it displays before autoplay activates and when users scroll away. Thumbnails can be selected from video frames in Buffer.")}
            <SpecGrid>
              <VideoCard pw={1000} ph={1500} ratioLabel="2:3" label="Video Pin — 2:3" dims="1000 × 1500 px"
                duration="4 sec – 15 min" fileSize="2 GB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#E60023"
                note="Recommended format. Best fit for Pinterest's masonry grid layout." />
              <VideoCard pw={1080} ph={1080} ratioLabel="1:1" label="Video Pin — 1:1" dims="1080 × 1080 px"
                duration="4 sec – 15 min" fileSize="2 GB" fps="—" formats="MP4, MOV, AVI, M4V" accent="#E60023"
                note="Square format. Also accepted: 4:5 and 9:16 vertical." />
            </SpecGrid>
            <InfoNote>
              The thumbnail displays as a static image when the video ends (autoplay on) and before the video plays (autoplay disabled). Title is shown at the bottom of the video in the feed.
            </InfoNote>
          </Section>

          {/* ════ THREADS ════ */}
          <Section id="threads">
            <PlatformHeader icon={FaThreads} name="Threads" subtitle="Video Posts" accent="#000000" />
            {editorialText("Threads video is straightforward: one video per post, up to 5 minutes, up to 1 GB. The platform uses the same encoding standards as Instagram — 25 Mbps video bitrate and 128 kbps audio cap — which makes sense given they share infrastructure. No custom thumbnails are supported; the first frame is always the preview.")}
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Video Post" dims="Max 1920 px wide"
                duration="Max 5 min" fileSize="1 GB" fps="23–60 FPS" formats="MP4, MOV" accent="#000000"
                note="Video bitrate: 25 Mbps max. Audio: 128 kbps. 1 video per post. No custom thumbnail." />
            </SpecGrid>
            <InfoNote>
              Videos auto-play in the Threads feed. Custom thumbnails are not supported — the first frame of your video is always shown as the preview image.
            </InfoNote>
          </Section>

          {/* ════ BLUESKY ════ */}
          <Section id="bluesky">
            <PlatformHeader icon={SiBluesky} name="Bluesky" subtitle="Video Posts" accent="#0085ff" />
            {editorialText("Bluesky has strict per-video and per-day upload limits compared to other platforms — 100 MB per video and 25 videos or 10 GB per day total. This matters for brands or creators posting frequently. Videos auto-play in the feed. No custom thumbnail support currently exists.")}
            <SpecGrid>
              <VideoCard pw={1080} ph={1920} ratioLabel="9:16" label="Video Post" dims="—"
                duration="Max 3 min" fileSize="100 MB" fps="—" formats="MP4, MOV" accent="#0085ff"
                note="Daily limit: 25 videos OR 10 GB total — whichever comes first." />
            </SpecGrid>
            <InfoNote>
              Bluesky enforces a daily upload cap of 25 videos or 10 GB total. Space out video posts if you're scheduling heavy video content on this platform.
            </InfoNote>
          </Section>

          {/* ════ MASTODON ════ */}
          <Section id="mastodon">
            <PlatformHeader icon={SiMastodon} name="Mastodon" subtitle="Video Posts (mastodon.social defaults)" accent="#6364FF" />
            {editorialText("Mastodon is a federated network — video specs depend on the instance. These limits reflect mastodon.social defaults; individual instances may be stricter or more permissive. Videos are transcoded to H.264 MP4 at a 1300 kbps bitrate cap. Unlike every other platform, Mastodon does NOT autoplay videos.")}
            <SpecGrid>
              <VideoCard pw={1280} ph={720} ratioLabel="16:9" label="Video Post" dims="—"
                duration="—" fileSize="40 MB" fps="Max 60 FPS" formats="MP4, M4V, MOV, WEBM" accent="#6364FF"
                note="Transcoded to H.264 MP4 at max 1300 kbps. Videos do NOT autoplay." />
            </SpecGrid>
            <InfoNote>
              Instance-level limits vary significantly. mastodon.social enforces 40 MB; smaller private instances may allow larger files. Check your instance documentation.
            </InfoNote>
          </Section>

          {/* ════ BEST PRACTICES ════ */}
          <section id="tips" style={{ scrollMarginTop: 80, marginBottom: 48 }}>
            <h2 style={{ fontFamily: "'Syne', sans-serif", fontSize: 19, fontWeight: 800, color: '#1c1917', margin: '0 0 14px', letterSpacing: '-0.02em' }}>
              Best Practices
            </h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
              {[
                { title: 'Use MP4 + H.264', body: 'Universally supported across all platforms. H.265 is more efficient but rejected by some platforms. H.264 MP4 is the safe default for every upload.' },
                { title: '9:16 for vertical — always', body: '1080 × 1920 is the standard for Stories, Reels, TikTok, and YouTube Shorts. Uploading any other ratio gets letterboxed with ugly blurred bars.' },
                { title: 'Stay under 25 Mbps bitrate', body: 'Instagram, Threads, and TikTok enforce hard bitrate limits. Uploading above 25 Mbps triggers aggressive platform recompression and visible quality loss.' },
                { title: 'Audio: 128 kbps or lower', body: 'Instagram and Threads both cap audio at 128 kbps. Higher bitrate audio is downsampled on ingest, which can introduce distortion in speech-heavy content.' },
                { title: 'Frame rate: 24–30 FPS', body: 'Higher FPS increases file size without noticeable quality improvement for social. 60 FPS makes sense for sports and action content only.' },
                { title: 'First-frame thumbnail strategy', body: 'Most platforms use the first video frame as the default thumbnail. Design an attention-grabbing opening frame that works as a static preview image.' },
                { title: 'Design for silent viewing', body: 'LinkedIn, Facebook, and Instagram auto-play silently. Add captions or text overlays directly in the video file — platform auto-captions vary in accuracy.' },
                { title: 'Bluesky daily limits', body: '25 videos per day or 10 GB total — whichever comes first. Space out uploads if you batch-schedule video content on Bluesky.' },
              ].map(({ title, body }) => (
                <div key={title} style={{ background: '#fff', border: '1px solid #e7e5e0', borderRadius: 12, padding: '16px 18px' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#1c1917', marginBottom: 6, fontFamily: "'Syne', sans-serif" }}>{title}</div>
                  <div style={{ fontSize: 12, color: '#78716c', lineHeight: 1.65 }}>{body}</div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 16, fontSize: 11, color: '#a8a29e', textAlign: 'right', fontStyle: 'italic' }}>
              Sources: Buffer Help Center, Hootsuite Blog — March 2026
            </div>
          </section>

        </main>
      </div>
      <Footer />
    </div>
  );
};

export default SocialMediaVideoGuide;
