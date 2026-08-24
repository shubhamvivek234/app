import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import SignupV1 from './SignupV1';
import SignupV2 from './SignupV2';
import SignupV3 from './SignupV3';
import SignupV4 from './SignupV4';

const getAssignedVariant = (overrideParam) => {
  if (overrideParam && ['1', '2', '3', '4'].includes(overrideParam)) {
    return parseInt(overrideParam, 10);
  }

  try {
    const stored = sessionStorage.getItem('auth_ui_variant');
    if (stored && ['1', '2', '3', '4'].includes(stored)) {
      return parseInt(stored, 10);
    }
  } catch (_) {}

  // Randomly assign 1, 2, 3, or 4
  const randomVariant = Math.floor(Math.random() * 4) + 1;
  try {
    sessionStorage.setItem('auth_ui_variant', String(randomVariant));
  } catch (_) {}
  return randomVariant;
};

const Signup = () => {
  const [searchParams] = useSearchParams();
  const override = searchParams.get('v') || searchParams.get('variant');

  const variant = useMemo(() => getAssignedVariant(override), [override]);

  switch (variant) {
    case 2:
      return <SignupV2 />;
    case 3:
      return <SignupV3 />;
    case 4:
      return <SignupV4 />;
    case 1:
    default:
      return <SignupV1 />;
  }
};

export default Signup;
