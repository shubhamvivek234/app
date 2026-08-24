import React, { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import LoginV1 from './LoginV1';
import LoginV2 from './LoginV2';
import LoginV3 from './LoginV3';
import LoginV4 from './LoginV4';

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

const Login = () => {
  const [searchParams] = useSearchParams();
  const override = searchParams.get('v') || searchParams.get('variant');

  const variant = useMemo(() => getAssignedVariant(override), [override]);

  switch (variant) {
    case 2:
      return <LoginV2 />;
    case 3:
      return <LoginV3 />;
    case 4:
      return <LoginV4 />;
    case 1:
    default:
      return <LoginV1 />;
  }
};

export default Login;
