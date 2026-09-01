/**
 * Unravler Smart Bio - Theme, Tactile Card Physics, and Effect Utilities
 * Inspired by Liinks.co high-converting physical UI and procedural backdrops.
 */

export const THEME_PRESETS = [
  {
    id: 'editorial_cream',
    name: 'Editorial Cream',
    subtitle: 'Warm parchment & luxury serif typography',
    background_type: 'gradient',
    background_color: '#FDFBF7',
    background_gradient: 'linear-gradient(135deg, #FDFBF7 0%, #F4EDE2 100%)',
    background_effect: 'grain',
    text_color: '#18181B',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(255, 255, 255, 0.85)',
    card_border: 'rgba(0, 0, 0, 0.08)',
    card_text_color: '#18181B',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#4F46E5',
    header_layout: 'classic',
  },
  {
    id: 'vantablack',
    name: 'OLED Vantablack',
    subtitle: 'Ultra-dark glass & crystal white lines',
    background_type: 'dark',
    background_color: '#09090B',
    background_gradient: 'linear-gradient(180deg, #09090B 0%, #18181B 100%)',
    background_effect: 'ambient_orbs',
    text_color: '#FAFAFA',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(24, 24, 27, 0.75)',
    card_border: 'rgba(255, 255, 255, 0.12)',
    card_text_color: '#FAFAFA',
    button_radius: 'rounded-2xl',
    font_family: 'Geist',
    accent_color: '#6366F1',
    header_layout: 'classic',
  },
  {
    id: 'liquid_aura',
    name: 'Liquid Aura Sunset',
    subtitle: 'Radiant coral, lavender & peach mesh glow',
    background_type: 'mesh',
    background_color: '#FFF1F2',
    background_gradient: 'linear-gradient(135deg, #FFE4E6 0%, #EDE9FE 50%, #FEF3C7 100%)',
    background_effect: 'mesh_glow',
    text_color: '#4C0519',
    card_style: 'tactile_convex',
    card_bg: 'rgba(255, 255, 255, 0.92)',
    card_border: 'rgba(244, 63, 94, 0.15)',
    card_text_color: '#4C0519',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#E11D48',
    header_layout: 'classic',
  },
  {
    id: 'velvet_truffle',
    name: 'Velvet Truffle & Gold',
    subtitle: 'Espresso charcoal & brushed champagne gold',
    background_type: 'dark',
    background_color: '#14110E',
    background_gradient: 'linear-gradient(180deg, #14110E 0%, #201A15 100%)',
    background_effect: 'grain',
    text_color: '#FEF3C7',
    card_style: 'tactile_convex',
    card_bg: 'rgba(38, 31, 26, 0.9)',
    card_border: 'rgba(245, 158, 11, 0.25)',
    card_text_color: '#FEF3C7',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#F59E0B',
    header_layout: 'editorial_split',
  },
  {
    id: 'tokyo_cyber',
    name: 'Tokyo Cyber Grid',
    subtitle: 'Obsidian night & glowing cyan/magenta rim',
    background_type: 'dark',
    background_color: '#05050A',
    background_gradient: 'linear-gradient(135deg, #05050A 0%, #0D081E 50%, #15002A 100%)',
    background_effect: 'ambient_orbs',
    text_color: '#00F0FF',
    card_style: 'neon_glow',
    card_bg: 'rgba(15, 10, 30, 0.85)',
    card_border: 'rgba(0, 240, 255, 0.5)',
    card_text_color: '#00F0FF',
    button_radius: 'rounded-xl',
    font_family: 'Geist',
    accent_color: '#00F0FF',
    header_layout: 'classic',
  },
  {
    id: 'matcha_washi',
    name: 'Matcha & Washi Linen',
    subtitle: 'Organic Japanese paper & deep forest green',
    background_type: 'gradient',
    background_color: '#F4F6F0',
    background_gradient: 'linear-gradient(135deg, #F4F6F0 0%, #E8ECE1 100%)',
    background_effect: 'grain',
    text_color: '#142817',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(255, 255, 255, 0.92)',
    card_border: 'rgba(88, 129, 87, 0.25)',
    card_text_color: '#142817',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#588157',
    header_layout: 'classic',
  },
  {
    id: 'ceramic_terracotta',
    name: 'Ceramic Terracotta',
    subtitle: 'Warm Spanish clay & tactile carved inset',
    background_type: 'gradient',
    background_color: '#FAF5F0',
    background_gradient: 'linear-gradient(135deg, #FAF5F0 0%, #F5EBE1 100%)',
    background_effect: 'grain',
    text_color: '#5C2414',
    card_style: 'tactile_concave',
    card_bg: 'rgba(245, 235, 225, 0.95)',
    card_border: 'rgba(194, 84, 45, 0.2)',
    card_text_color: '#5C2414',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#C2542D',
    header_layout: 'classic',
  },
  {
    id: 'emerald_glass',
    name: 'Emerald Forest Glass',
    subtitle: 'Deep botanical jade & frosted double-bezel',
    background_type: 'gradient',
    background_color: '#022C22',
    background_gradient: 'linear-gradient(135deg, #064E3B 0%, #022C22 100%)',
    background_effect: 'ambient_orbs',
    text_color: '#ECFDF5',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(6, 78, 59, 0.75)',
    card_border: 'rgba(52, 211, 153, 0.25)',
    card_text_color: '#ECFDF5',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#10B981',
    header_layout: 'classic',
  },
  {
    id: 'electric_mesh',
    name: 'Electric Indigo',
    subtitle: 'Vibrant neon glow & deep violet contrast',
    background_type: 'gradient',
    background_color: '#0F172A',
    background_gradient: 'linear-gradient(135deg, #1E1B4B 0%, #0F172A 50%, #311042 100%)',
    background_effect: 'mesh_glow',
    text_color: '#F8FAFC',
    card_style: 'soft_pill',
    card_bg: 'rgba(30, 27, 75, 0.85)',
    card_border: 'rgba(129, 140, 248, 0.3)',
    card_text_color: '#F8FAFC',
    button_radius: 'rounded-full',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#818CF8',
    header_layout: 'classic',
  },
  {
    id: 'holographic_dream',
    name: 'Holographic Dream',
    subtitle: 'Iridescent pastel gradient & frosted pills',
    background_type: 'mesh',
    background_color: '#F0F9FF',
    background_gradient: 'linear-gradient(135deg, #E0E7FF 0%, #FCE7F3 50%, #E0F2FE 100%)',
    background_effect: 'mesh_glow',
    text_color: '#1E1B4B',
    card_style: 'soft_pill',
    card_bg: 'rgba(255, 255, 255, 0.88)',
    card_border: 'rgba(167, 139, 250, 0.25)',
    card_text_color: '#1E1B4B',
    button_radius: 'rounded-full',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#8B5CF6',
    header_layout: 'classic',
  },
  {
    id: 'nordic_slate',
    name: 'Nordic Slate',
    subtitle: 'Clean Scandinavian monochrome & flat cards',
    background_type: 'gradient',
    background_color: '#F8FAFC',
    background_gradient: 'linear-gradient(180deg, #F8FAFC 0%, #E2E8F0 100%)',
    background_effect: 'none',
    text_color: '#0F172A',
    card_style: 'solid_flat',
    card_bg: '#FFFFFF',
    card_border: 'rgba(15, 23, 42, 0.08)',
    card_text_color: '#0F172A',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#0EA5E9',
    header_layout: 'classic',
  },
  {
    id: 'cyberpunk_neon',
    name: 'Cyberpunk Neon',
    subtitle: 'High energy cyan & electric brutalist shadow',
    background_type: 'dark',
    background_color: '#05050A',
    background_gradient: 'linear-gradient(135deg, #05050A 0%, #15002A 100%)',
    background_effect: 'ambient_orbs',
    text_color: '#00F0FF',
    card_style: 'hard_shadow',
    card_bg: 'rgba(20, 0, 40, 0.85)',
    card_border: 'rgba(0, 240, 255, 0.5)',
    card_text_color: '#00F0FF',
    button_radius: 'rounded-xl',
    font_family: 'Geist',
    accent_color: '#FF0055',
    header_layout: 'classic',
  },
  {
    id: 'champagne_velvet',
    name: 'Champagne & Truffle',
    subtitle: 'Warm dark truffle & soft gold leaf reflection',
    background_type: 'dark',
    background_color: '#1B1612',
    background_gradient: 'linear-gradient(180deg, #1B1612 0%, #261F19 100%)',
    background_effect: 'grain',
    text_color: '#FDF6E2',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(45, 36, 30, 0.85)',
    card_border: 'rgba(251, 191, 36, 0.25)',
    card_text_color: '#FDF6E2',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#F59E0B',
    header_layout: 'classic',
  },
  {
    id: 'tokyo_midnight',
    name: 'Tokyo Midnight Blur',
    subtitle: 'Deep sapphire & frosted cobalt glass',
    background_type: 'dark',
    background_color: '#060814',
    background_gradient: 'linear-gradient(135deg, #060814 0%, #0F172A 50%, #1E1B4B 100%)',
    background_effect: 'ambient_orbs',
    text_color: '#F0F9FF',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(15, 23, 42, 0.75)',
    card_border: 'rgba(56, 189, 248, 0.25)',
    card_text_color: '#F0F9FF',
    button_radius: 'rounded-2xl',
    font_family: 'Geist',
    accent_color: '#38BDF8',
    header_layout: 'classic',
  },
  {
    id: 'california_dusk',
    name: 'Venice Dusk',
    subtitle: 'Deep plum glow & warm apricot highlights',
    background_type: 'gradient',
    background_color: '#2E0854',
    background_gradient: 'linear-gradient(135deg, #3B0764 0%, #701A75 50%, #9A3412 100%)',
    background_effect: 'mesh_glow',
    text_color: '#FFEDD5',
    card_style: 'soft_pill',
    card_bg: 'rgba(76, 29, 149, 0.7)',
    card_border: 'rgba(253, 186, 116, 0.25)',
    card_text_color: '#FFEDD5',
    button_radius: 'rounded-full',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#FB923C',
    header_layout: 'classic',
  },
  {
    id: 'aurora_borealis',
    name: 'Nordic Aurora',
    subtitle: 'Deep arctic night & shimmering teal halo',
    background_type: 'dark',
    background_color: '#030D1A',
    background_gradient: 'linear-gradient(135deg, #030D1A 0%, #06243A 60%, #064E3B 100%)',
    background_effect: 'ambient_orbs',
    text_color: '#E0F2FE',
    card_style: 'glass_double_bezel',
    card_bg: 'rgba(6, 36, 58, 0.8)',
    card_border: 'rgba(45, 212, 191, 0.3)',
    card_text_color: '#E0F2FE',
    button_radius: 'rounded-2xl',
    font_family: 'Geist',
    accent_color: '#2DD4BF',
    header_layout: 'classic',
  },
  {
    id: 'swiss_minimal',
    name: 'Swiss Architectural',
    subtitle: 'Pure stark monochrome & sharp precision',
    background_type: 'solid',
    background_color: '#FAFAFA',
    background_gradient: 'linear-gradient(180deg, #FAFAFA 0%, #F4F4F5 100%)',
    background_effect: 'none',
    text_color: '#09090B',
    card_style: 'minimal_outline',
    card_bg: '#FFFFFF',
    card_border: '#09090B',
    card_text_color: '#09090B',
    button_radius: 'rounded-none',
    font_family: 'Geist',
    accent_color: '#09090B',
    header_layout: 'minimal',
  },
  {
    id: 'pastel_marshmallow',
    name: 'Pastel Marshmallow',
    subtitle: 'Soft baby blue, lavender & pillowed cards',
    background_type: 'mesh',
    background_color: '#F0FDF4',
    background_gradient: 'linear-gradient(135deg, #E0F2FE 0%, #F5F3FF 50%, #DCFCE7 100%)',
    background_effect: 'mesh_glow',
    text_color: '#0F172A',
    card_style: 'tactile_convex',
    card_bg: 'rgba(255, 255, 255, 0.95)',
    card_border: 'rgba(14, 165, 233, 0.15)',
    card_text_color: '#0F172A',
    button_radius: 'rounded-2xl',
    font_family: 'Plus Jakarta Sans',
    accent_color: '#0284C7',
    header_layout: 'classic',
  },
];

export const TACTILE_CARD_STYLES = [
  { id: 'glass_double_bezel', label: 'Double-Bezel Glass (Apple)', description: 'Frosted acrylic glass with dual highlight rim' },
  { id: 'tactile_convex', label: 'Tactile Convex 3D (Pillowed)', description: 'Floats off page with top specular highlight & soft drop shadow' },
  { id: 'tactile_concave', label: 'Tactile Concave Inset (Carved)', description: 'Soft neumorphic inner shadow carved into canvas' },
  { id: 'hard_shadow', label: 'Hard Neobrutalist', description: 'Bold solid border with hard offset physical shadow' },
  { id: 'neon_glow', label: 'Cyber Glow Halo', description: 'Deep dark card with glowing ambient neon outline' },
  { id: 'soft_pill', label: 'Soft Marshmallow Pill', description: 'Rounded pill shape with diffused elevation' },
  { id: 'minimal_outline', label: 'Minimal Architectural Hairline', description: 'Ultra-clean 1px crisp outline' },
  { id: 'solid_flat', label: 'Solid Modern Flat', description: 'High-opacity modern flat surface' },
];

export const BACKGROUND_EFFECTS = [
  { id: 'none', label: 'Clean Canvas', description: 'Solid or gradient backdrop without overlays' },
  { id: 'grain', label: 'Film Grain & Washi Paper', description: 'Subtle SVG noise texture overlay for luxury physical feel' },
  { id: 'ambient_orbs', label: 'Ambient Light Orbs', description: 'Floating defocused glowing light spheres behind cards' },
  { id: 'mesh_glow', label: 'Procedural Liquid Mesh', description: 'Multi-stop fluid color blend with dynamic ambient light' },
];

export const HEADER_LAYOUTS = [
  { id: 'classic', label: 'Classic Centered', description: 'Centered avatar, verified badge, bio, and social dock' },
  { id: 'banner', label: 'Banner Cover Photo', description: 'Full-bleed cover photo with overlapping profile avatar' },
  { id: 'editorial_split', label: 'Editorial Horizontal Split', description: 'Asymmetric portrait on left with bio on right' },
  { id: 'minimal', label: 'Minimalist Monograph', description: 'Text-first title headline with micro avatar' },
];

/**
 * Computes exact inline styles and Tailwind classes for a card or button.
 * Respects fine-tuned slider percentages (corner radius, border width, shadow depth, soft/solid shadow)
 */
export const getTactileCardStyles = (cardStyle, theme = {}, isFeatured = false, blockOverrides = {}) => {
  const bg = blockOverrides.has_custom_bg
    ? blockOverrides.card_bg
    : (theme.card_bg || blockOverrides.card_bg || 'rgba(255, 255, 255, 0.85)');
  const border = blockOverrides.has_custom_border
    ? blockOverrides.card_border
    : (theme.card_border || blockOverrides.card_border || 'rgba(0, 0, 0, 0.08)');
  const textColor = blockOverrides.has_custom_text_color
    ? blockOverrides.card_text_color
    : (theme.card_text_color || blockOverrides.card_text_color || theme.text_color || '#18181B');
  const accent = theme.accent_color || '#6366F1';

  // Dynamic slider values
  const cornerPct = theme.card_corner_radius !== undefined ? Number(theme.card_corner_radius) : 20;
  const borderPct = theme.card_border_width !== undefined ? Number(theme.card_border_width) : 0;
  const shadowPct = theme.card_shadow_depth !== undefined ? Number(theme.card_shadow_depth) : 100;
  const shadowType = theme.card_shadow_type || 'soft'; // 'soft' | 'solid'
  const isTactile = theme.tactile_blocks ?? true;

  // Calculate dynamic border-radius (0% = 0px, 50% = 18px, 100% = 9999px)
  let borderRadiusStyle = `${Math.round((cornerPct / 100) * 36)}px`;
  if (cornerPct >= 95) borderRadiusStyle = '9999px';

  // Calculate dynamic border width (0% = 0px, 100% = 3px)
  let borderWidthStyle = `${((borderPct / 100) * 3).toFixed(1)}px`;
  if (borderPct === 0 && !cardStyle?.includes('outline') && !cardStyle?.includes('hard')) {
    borderWidthStyle = '1px';
  }

  // Calculate dynamic box shadow
  let customShadow = '0 4px 12px -2px rgba(0, 0, 0, 0.05)';
  let backdropBlur = 'backdrop-blur-md';
  let extraClasses = '';

  if (shadowPct === 0) {
    customShadow = 'none';
  } else if (shadowType === 'solid') {
    const depth = Math.max(1, Math.round((shadowPct / 100) * 8));
    customShadow = `${depth}px ${depth}px 0px rgba(0, 0, 0, 0.85)`;
  } else {
    // Soft shadow depth scale
    const blurDepth = Math.round((shadowPct / 100) * 28);
    const yOffset = Math.round((shadowPct / 100) * 14);
    const opacity = (0.05 + (shadowPct / 100) * 0.15).toFixed(2);

    if (isTactile) {
      switch (cardStyle) {
        case 'tactile_convex':
          customShadow = `inset 0 1px 1px rgba(255, 255, 255, 0.6), 0 ${yOffset}px ${blurDepth}px -4px rgba(0, 0, 0, ${opacity})`;
          break;
        case 'tactile_concave':
          customShadow = `inset 0 2px 6px rgba(0, 0, 0, ${opacity}), inset 0 -1px 2px rgba(255, 255, 255, 0.3)`;
          break;
        case 'neon_glow':
          customShadow = `0 0 ${Math.round((shadowPct / 100) * 24)}px ${accent}45, inset 0 0 10px ${accent}25`;
          break;
        case 'glass_double_bezel':
          customShadow = `inset 0 1px 0 0 rgba(255, 255, 255, 0.4), 0 ${yOffset}px ${blurDepth}px -4px rgba(0, 0, 0, ${opacity})`;
          backdropBlur = 'backdrop-blur-xl';
          break;
        case 'soft_pill':
          customShadow = `0 ${yOffset}px ${blurDepth}px -6px rgba(0, 0, 0, ${opacity})`;
          break;
        default:
          customShadow = `0 ${yOffset}px ${blurDepth}px rgba(0, 0, 0, ${opacity})`;
          break;
      }
    } else {
      customShadow = `0 ${yOffset}px ${blurDepth}px rgba(0, 0, 0, ${opacity})`;
    }
  }

  // Animation handling
  if (isFeatured || blockOverrides.animation === 'pulse') {
    extraClasses += ' ring-2 ring-amber-400/90 shadow-amber-400/20 animate-pulse-subtle';
  } else if (blockOverrides.animation === 'bounce') {
    extraClasses += ' animate-bounce';
  } else if (blockOverrides.animation === 'wiggle') {
    extraClasses += ' hover:animate-wiggle';
  } else if (blockOverrides.animation === 'glow') {
    extraClasses += ' ring-2 ring-indigo-500/80 shadow-indigo-500/30';
  }

  return {
    style: {
      backgroundColor: bg,
      borderColor: border,
      borderWidth: borderWidthStyle,
      borderStyle: 'solid',
      color: textColor,
      borderRadius: borderRadiusStyle,
      boxShadow: customShadow,
    },
    className: `${backdropBlur} ${extraClasses}`,
  };
};

/**
 * Computes profile avatar styles based on General Styles sliders
 */
export const getProfileAvatarStyles = (theme = {}) => {
  const sizePct = theme.profile_picture_size !== undefined ? Number(theme.profile_picture_size) : 50;
  const shadowPct = theme.profile_picture_shadow !== undefined ? Number(theme.profile_picture_shadow) : 0;
  const borderPct = theme.profile_picture_border !== undefined ? Number(theme.profile_picture_border) : 0;

  // Size in px: 0% = 52px, 50% = 84px, 100% = 124px
  const sizePx = Math.round(52 + (sizePct / 100) * 72);
  const borderWidthPx = Math.round((borderPct / 100) * 6);
  const shadowBlur = Math.round((shadowPct / 100) * 24);
  const shadowOpacity = (0.1 + (shadowPct / 100) * 0.25).toFixed(2);

  return {
    width: `${sizePx}px`,
    height: `${sizePx}px`,
    borderWidth: borderWidthPx > 0 ? `${borderWidthPx}px` : undefined,
    borderColor: borderWidthPx > 0 ? (theme.card_border || 'rgba(255,255,255,0.8)') : undefined,
    borderStyle: borderWidthPx > 0 ? 'solid' : undefined,
    boxShadow: shadowPct > 0 ? `0 8px ${shadowBlur}px rgba(0,0,0,${shadowOpacity})` : undefined,
  };
};

/**
 * Computes spacing gap between blocks from Spacing slider %
 */
export const getBlockSpacingPx = (theme = {}) => {
  const spacingPct = theme.card_spacing !== undefined ? Number(theme.card_spacing) : 33;
  // 0% = 6px, 50% = 14px, 100% = 26px
  return Math.round(6 + (spacingPct / 100) * 20);
};

/**
 * Computes social icon size from slider %
 */
export const getSocialIconSizePx = (theme = {}) => {
  const sizePct = theme.social_icon_size !== undefined ? Number(theme.social_icon_size) : 0;
  // 0% = 18px, 50% = 24px, 100% = 32px
  return Math.round(18 + (sizePct / 100) * 14);
};
