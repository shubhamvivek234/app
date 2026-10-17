"use client";

import { useState, type FormEvent } from "react";

function UserIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function EnvelopeIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect width="20" height="16" x="2" y="4" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function UnravlerBrandLogo() {
  return (
    <a className="auth-brand-logo" href="/" aria-label="Unravler.io home">
      <span className="brand-mark-shell" aria-hidden="true">
        <svg viewBox="0 0 256 256" className="brand-mark-svg" role="img" aria-label="Unravler mark">
          <path className="brand-ribbon brand-ribbon-1" d="M30 64c18-13 42-15 72-14h36c32 1 57-4 78-20 6-5 12-1 12 7v22c0 9-7 17-18 21-32 11-68 7-105 4-31-3-56 0-75 15V64Z" />
          <path className="brand-ribbon brand-ribbon-2" d="M30 106c19-14 44-15 75-13h40c31 0 52-5 72-19 6-4 11-1 11 6v23c0 9-7 17-18 20-32 11-68 7-105 4-31-3-56 0-75 15v-36Z" />
          <path className="brand-ribbon brand-ribbon-3" d="M30 148c19-14 44-15 75-13h40c31 0 52-5 72-19 6-4 11-1 11 6v23c0 9-7 17-18 20-32 11-68 7-105 4-31-3-56 0-75 15v-36Z" />
          <path className="brand-ribbon brand-ribbon-4" d="M30 191c19-14 44-15 75-13h40c31 0 52-5 72-19 6-4 11-1 11 6v23c0 10-8 20-21 25-32 13-69 6-105 3-30-3-54 2-72 20v-45Z" />
        </svg>
      </span>
      <span className="brand-wordmark-text">Unravler</span>
      <span className="brand-suffix">.io</span>
    </a>
  );
}

export interface AuthSwitchProps {
  onSignInSubmit?: (data: { username: string; password: string }) => void;
  onSignUpSubmit?: (data: { username: string; email: string; password: string }) => void;
  initialMode?: "signin" | "signup";
}

export default function AuthSwitch({
  onSignInSubmit,
  onSignUpSubmit,
  initialMode = "signin",
}: AuthSwitchProps) {
  const [isSignUp, setIsSignUp] = useState(initialMode === "signup");

  const onSubmitSignIn = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const username = (form.elements.namedItem("username") as HTMLInputElement)?.value || "";
    const password = (form.elements.namedItem("password") as HTMLInputElement)?.value || "";
    if (onSignInSubmit) {
      onSignInSubmit({ username, password });
    }
  };

  const onSubmitSignUp = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const username = (form.elements.namedItem("username") as HTMLInputElement)?.value || "";
    const email = (form.elements.namedItem("email") as HTMLInputElement)?.value || "";
    const password = (form.elements.namedItem("password") as HTMLInputElement)?.value || "";
    if (onSignUpSubmit) {
      onSignUpSubmit({ username, email, password });
    }
  };

  return (
    <div className="auth-switch">
      <style>{`
        .auth-switch,
        .auth-switch * {
          box-sizing: border-box;
        }

        .auth-switch {
          font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #FFFFFF;
          min-height: 100vh;
          width: 100vw;
          margin: 0;
          padding: 0;
          overflow: hidden;
        }

        .container {
          position: relative;
          width: 100vw;
          height: 100vh;
          min-height: 100vh;
          background: white;
          border: none;
          box-shadow: none;
          border-radius: 0;
          overflow: hidden;
        }

        .forms-container {
          position: absolute;
          width: 100%;
          height: 100%;
          top: 0;
          left: 0;
        }

        .signin-signup {
          position: absolute;
          top: 50%;
          transform: translate(-50%, -50%);
          left: 75%;
          width: 50%;
          transition: 1s 0.7s ease-in-out;
          display: grid;
          grid-template-columns: 1fr;
          z-index: 5;
        }

        form {
          display: flex;
          align-items: center;
          justify-content: center;
          flex-direction: column;
          padding: 0 5rem;
          transition: all 0.2s 0.7s;
          overflow: hidden;
          grid-column: 1 / 2;
          grid-row: 1 / 2;
        }

        form.sign-up-form {
          opacity: 0;
          z-index: 1;
          pointer-events: none;
        }

        form.sign-in-form {
          z-index: 2;
          pointer-events: all;
        }

        .auth-brand-logo {
          display: inline-flex;
          align-items: center;
          gap: 0;
          text-decoration: none;
          margin-bottom: 28px;
          color: #111111;
          transition: transform 0.2s ease;
        }

        .auth-brand-logo:hover {
          transform: translateY(-1px);
        }

        .brand-mark-shell {
          width: 38px;
          height: 46px;
          margin-right: 6px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          animation: unravlerPulseBreath 4s ease-in-out infinite;
        }

        .brand-mark-svg {
          width: 100%;
          height: 100%;
          fill: currentColor;
          display: block;
        }

        @keyframes unravlerRibbonWave {
          0%, 100% {
            transform: scaleX(0.92) translateX(-2px);
            opacity: 0.28;
          }
          50% {
            transform: scaleX(1.04) translateX(2px);
            opacity: 1;
          }
        }

        @keyframes unravlerPulseBreath {
          0%, 100% {
            transform: scale(0.98);
            opacity: 0.92;
          }
          50% {
            transform: scale(1.03);
            opacity: 1;
          }
        }

        .brand-ribbon-1 {
          animation: unravlerRibbonWave 3.2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.0s;
          transform-origin: center;
        }
        .brand-ribbon-2 {
          animation: unravlerRibbonWave 3.2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.3s;
          transform-origin: center;
        }
        .brand-ribbon-3 {
          animation: unravlerRibbonWave 3.2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.6s;
          transform-origin: center;
        }
        .brand-ribbon-4 {
          animation: unravlerRibbonWave 3.2s cubic-bezier(0.4, 0, 0.2, 1) infinite 0.9s;
          transform-origin: center;
        }

        .brand-wordmark-text {
          font-family: 'Plus Jakarta Sans', 'Inter', sans-serif;
          font-size: 28px;
          font-weight: 800;
          letter-spacing: -0.04em;
          color: #111111;
          line-height: 1;
        }

        .brand-suffix {
          font-family: 'Plus Jakarta Sans', 'Inter', sans-serif;
          font-size: 28px;
          font-weight: 800;
          letter-spacing: -0.04em;
          color: #111111;
          line-height: 1;
          position: relative;
          top: 1px;
        }

        .input-field {
          max-width: 380px;
          width: 100%;
          background-color: #f0f0f0;
          margin: 10px 0;
          height: 55px;
          border-radius: 55px;
          display: grid;
          grid-template-columns: 15% 85%;
          padding: 0 0.4rem;
          position: relative;
          transition: 0.3s;
        }

        .input-field:focus-within {
          background-color: #e8e8e8;
          box-shadow: 0 0 0 2px #0062FF;
        }

        .input-field i {
          display: flex;
          align-items: center;
          justify-content: center;
          color: #666;
          transition: 0.5s;
        }

        .input-field:focus-within i {
          color: #0062FF;
        }

        .input-field input {
          background: none;
          outline: none;
          border: none;
          line-height: 1;
          font-weight: 500;
          font-size: 1rem;
          color: #333;
          width: 100%;
        }

        .input-field input::placeholder {
          color: #aaa;
          font-weight: 400;
        }

        .btn {
          width: 150px;
          background-color: #0062FF;
          border: none;
          outline: none;
          height: 49px;
          border-radius: 49px;
          color: #fff;
          text-transform: uppercase;
          font-weight: 600;
          margin: 14px 0 10px;
          cursor: pointer;
          transition: 0.5s;
          font-size: 0.9rem;
          box-shadow: 0 4px 14px rgba(0, 98, 255, 0.28);
        }

        .btn:hover {
          background-color: #004EDB;
          transform: translateY(-2px);
          box-shadow: 0 5px 15px rgba(0, 98, 255, 0.4);
        }

        .panels-container {
          position: absolute;
          height: 100%;
          width: 100%;
          top: 0;
          left: 0;
          display: grid;
          grid-template-columns: repeat(2, 1fr);
        }

        .panel {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: space-around;
          text-align: center;
          z-index: 6;
          padding: 3rem 14% 2rem;
        }

        .left-panel {
          pointer-events: all;
        }

        .right-panel {
          pointer-events: none;
        }

        .panel .content {
          color: #fff;
          transition: transform 0.9s ease-in-out;
          transition-delay: 0.6s;
        }

        .panel h3 {
          font-weight: 600;
          line-height: 1.2;
          font-size: 1.6rem;
          margin-bottom: 10px;
          color: #FFFFFF;
        }

        .panel p {
          font-size: 0.95rem;
          padding: 0.7rem 0 1.2rem;
          line-height: 1.5;
          color: rgba(255, 255, 255, 0.92);
        }

        .btn.transparent {
          margin: 0;
          background: none;
          border: 2px solid #fff;
          width: 130px;
          height: 41px;
          font-weight: 600;
          font-size: 0.8rem;
          color: #FFFFFF;
        }

        .btn.transparent:hover {
          background: rgba(255, 255, 255, 0.15);
          transform: translateY(-2px);
        }

        .right-panel .content {
          transform: translateX(100vw);
        }

        .container.sign-up-mode:before {
          transform: translate(100%, -50%);
          right: 52%;
        }

        .container.sign-up-mode .left-panel .content {
          transform: translateX(-100vw);
        }

        .container.sign-up-mode .signin-signup {
          left: 25%;
        }

        .container.sign-up-mode form.sign-up-form {
          opacity: 1;
          z-index: 2;
          pointer-events: all;
        }

        .container.sign-up-mode form.sign-in-form {
          opacity: 0;
          z-index: 1;
          pointer-events: none;
        }

        .container.sign-up-mode .right-panel .content {
          transform: translateX(0%);
        }

        .container.sign-up-mode .left-panel {
          pointer-events: none;
        }

        .container.sign-up-mode .right-panel {
          pointer-events: all;
        }

        .container:before {
          content: "";
          position: absolute;
          height: clamp(2400px, 180vw, 3400px);
          width: clamp(2400px, 180vw, 3400px);
          top: 50%;
          right: 48%;
          transform: translateY(-50%);
          background: linear-gradient(-45deg, #0062FF 0%, #4F46E5 50%, #764ba2 100%);
          transition: 1.8s ease-in-out;
          border-radius: 50%;
          z-index: 6;
        }

        @media (max-width: 870px) {
          .container {
            min-height: 800px;
            height: 100vh;
          }
          .signin-signup {
            width: 100%;
            top: 95%;
            transform: translate(-50%, -100%);
            transition: 1s 0.8s ease-in-out;
          }
          .signin-signup,
          .container.sign-up-mode .signin-signup {
            left: 50%;
          }
          .panels-container {
            grid-template-columns: 1fr;
            grid-template-rows: 1fr 2fr 1fr;
          }
          .panel {
            flex-direction: row;
            justify-content: space-around;
            align-items: center;
            padding: 2.5rem 8%;
            grid-column: 1 / 2;
          }
          .right-panel {
            grid-row: 3 / 4;
          }
          .left-panel {
            grid-row: 1 / 2;
          }
          .panel .content {
            padding-right: 15%;
            transition: transform 0.9s ease-in-out;
            transition-delay: 0.8s;
          }
          .panel h3 {
            font-size: 1.2rem;
          }
          .panel p {
            font-size: 0.75rem;
            padding: 0.5rem 0;
          }
          .btn.transparent {
            width: 110px;
            height: 35px;
            font-size: 0.7rem;
          }
          .container:before {
            width: 1500px;
            height: 1500px;
            transform: translateX(-50%);
            left: 30%;
            bottom: 68%;
            right: initial;
            top: initial;
            transition: 2s ease-in-out;
          }
          .container.sign-up-mode:before {
            transform: translate(-50%, 100%);
            bottom: 32%;
            right: initial;
          }
          .container.sign-up-mode .left-panel .content {
            transform: translateY(-300px);
          }
          .container.sign-up-mode .right-panel .content {
            transform: translateY(0%);
          }
          .right-panel .content {
            transform: translateY(300px);
          }
          .container.sign-up-mode .signin-signup {
            top: 5%;
            transform: translate(-50%, 0);
          }
        }

        @media (max-width: 570px) {
          form {
            padding: 0 1.5rem;
          }
          .panel .content {
            padding: 0.5rem 1rem;
          }
          .panel {
            padding: 1.5rem 1rem;
          }
          .container:before {
            bottom: 72%;
            left: 50%;
          }
          .container.sign-up-mode:before {
            bottom: 28%;
            left: 50%;
          }
        }
      `}</style>

      <div className={`container ${isSignUp ? "sign-up-mode" : ""}`}>
        <div className="forms-container">
          <div className="signin-signup">
            <form onSubmit={onSubmitSignIn} className="sign-in-form">
              <UnravlerBrandLogo />
              <div className="input-field">
                <i className="input-icon">
                  <UserIcon />
                </i>
                <input
                  type="text"
                  name="username"
                  placeholder="Username"
                  autoComplete="username"
                  required
                />
              </div>
              <div className="input-field">
                <i className="input-icon">
                  <LockIcon />
                </i>
                <input
                  type="password"
                  name="password"
                  placeholder="Password"
                  autoComplete="current-password"
                  required
                />
              </div>
              <button type="submit" className="btn solid">
                Login
              </button>
            </form>

            <form onSubmit={onSubmitSignUp} className="sign-up-form">
              <UnravlerBrandLogo />
              <div className="input-field">
                <i className="input-icon">
                  <UserIcon />
                </i>
                <input
                  type="text"
                  name="username"
                  placeholder="Username"
                  autoComplete="username"
                  required
                />
              </div>
              <div className="input-field">
                <i className="input-icon">
                  <EnvelopeIcon />
                </i>
                <input
                  type="email"
                  name="email"
                  placeholder="Email"
                  autoComplete="email"
                  required
                />
              </div>
              <div className="input-field">
                <i className="input-icon">
                  <LockIcon />
                </i>
                <input
                  type="password"
                  name="password"
                  placeholder="Password"
                  autoComplete="new-password"
                  required
                />
              </div>
              <button type="submit" className="btn solid">
                Sign up
              </button>
            </form>
          </div>
        </div>

        <div className="panels-container">
          <div className="panel left-panel">
            <div className="content">
              <h3>New here?</h3>
              <p>Sign up and discover how Unravler accelerates and organizes your outreach workflows.</p>
              <button
                type="button"
                className="btn transparent"
                onClick={() => setIsSignUp(true)}
              >
                Sign up
              </button>
            </div>
          </div>
          <div className="panel right-panel">
            <div className="content">
              <h3>One of us?</h3>
              <p>Welcome back! Sign in to keep managing your outreach campaigns and conversations.</p>
              <button
                type="button"
                className="btn transparent"
                onClick={() => setIsSignUp(false)}
              >
                Sign in
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
