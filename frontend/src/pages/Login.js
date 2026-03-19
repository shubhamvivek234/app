import React, { useState } from 'react';
import LoginV1 from './LoginV1';
import LoginV2 from './LoginV2';
import LoginV3 from './LoginV3';
import LoginV4 from './LoginV4';

/**
 * Login — randomly shows one of four login page designs each visit.
 * V1: Light split-screen with orbiting platform icons (classic design)
 * V2: Dark navy with floating social icons, stats + animations
 * V3: Netflix-red left panel + clean white right form
 * V4: Animated character mascots (eye-tracking) + white right form
 */
const Login = () => {
  // Pick once per mount — re-randomises on every page visit
  const [variant] = useState(() => {
    const r = Math.random();
    if (r < 0.25) return 'v1';
    if (r < 0.50) return 'v2';
    if (r < 0.75) return 'v3';
    return 'v4';
  });

  if (variant === 'v1') return <LoginV1 />;
  if (variant === 'v2') return <LoginV2 />;
  if (variant === 'v3') return <LoginV3 />;
  return <LoginV4 />;
};

export default Login;
