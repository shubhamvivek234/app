import React, { useState } from 'react';
import SignupV1 from './SignupV1';
import SignupV2 from './SignupV2';
import SignupV4 from './SignupV4';

const Signup = () => {
  const [variant] = useState(() => {
    const r = Math.random();
    if (r < 0.333) return 'v1';
    if (r < 0.666) return 'v2';
    return 'v4';
  });

  if (variant === 'v1') return <SignupV1 />;
  if (variant === 'v2') return <SignupV2 />;
  return <SignupV4 />;
};

export default Signup;
