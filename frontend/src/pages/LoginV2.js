import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { toast } from 'sonner';
import SocialEntanglerLogo from '@/components/SocialEntanglerLogo';

/* ─────────────────────────────────────────────────────────────────────────
   12 floating social icons — spread across the wider left panel
   anim: which keyframe variant (A–E) for unique X+Y movement paths
───────────────────────────────────────────────────────────────────────── */
const FLOATING_ICONS = [
  {
    key: 'instagram', left: '78%', top: '58%', size: 66, delay: 0, dur: 12, anim: 'A',
    bg: 'linear-gradient(135deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888)',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
      </svg>
    ),
  },
  {
    key: 'tiktok', left: '55%', top: '12%', size: 58, delay: 1.5, dur: 14, anim: 'B',
    bg: '#010101',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/>
      </svg>
    ),
  },
  {
    key: 'facebook', left: '38%', top: '10%', size: 62, delay: 0.6, dur: 11, anim: 'C',
    bg: '#1877F2',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
      </svg>
    ),
  },
  {
    key: 'linkedin', left: '57%', top: '62%', size: 56, delay: 2.2, dur: 13, anim: 'D',
    bg: '#0A66C2',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
      </svg>
    ),
  },
  {
    key: 'youtube', left: '72%', top: '18%', size: 64, delay: 0.9, dur: 15, anim: 'E',
    bg: '#FF0000',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
      </svg>
    ),
  },
  {
    key: 'twitter', left: '12%', top: '40%', size: 54, delay: 3.0, dur: 12, anim: 'A',
    bg: '#000000',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747l7.73-8.835L1.254 2.25H8.08l4.259 5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
      </svg>
    ),
  },
  {
    key: 'pinterest', left: '50%', top: '84%', size: 52, delay: 1.8, dur: 13, anim: 'B',
    bg: '#E60023',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M12 0C5.373 0 0 5.372 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738a.36.36 0 0 1 .083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.632-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12S18.627 0 12 0z"/>
      </svg>
    ),
  },
  {
    key: 'threads', left: '83%', top: '78%', size: 50, delay: 2.5, dur: 11, anim: 'C',
    bg: '#000000',
    icon: (
      <svg viewBox="0 0 192 192" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M141.537 88.9883C140.71 88.5919 139.87 88.2104 139.019 87.8451C137.537 60.5382 122.616 44.905 97.5619 44.745C97.4484 44.7443 97.3355 44.7443 97.222 44.7443C82.2364 44.7443 69.7731 51.1409 62.102 62.7807L75.881 72.2328C81.6116 63.5383 90.6052 61.6848 97.2286 61.6848C97.3051 61.6848 97.3819 61.6848 97.4576 61.6855C105.707 61.7381 111.932 64.1366 115.961 68.814C118.893 72.2193 120.854 76.925 121.825 82.8638C114.511 81.6207 106.601 81.2385 98.145 81.7233C74.3247 83.0954 59.0111 96.9879 60.0396 116.292C60.5615 126.084 65.4397 134.508 73.775 140.011C80.8224 144.663 89.899 146.938 99.3323 146.423C111.79 145.74 121.563 140.987 128.381 132.296C133.559 125.696 136.834 117.143 138.28 106.366C144.217 109.949 148.617 114.664 151.047 120.332C155.179 129.967 155.42 145.8 142.501 158.708C131.106 170.092 117.398 175.007 96.6133 175.157C73.6011 174.989 56.1351 167.632 44.6922 153.033C33.7935 139.033 28.1044 118.537 27.8963 92C28.1044 65.4632 33.7935 44.9671 44.6922 30.967C56.1351 16.3678 73.6011 9.01089 96.6133 8.84281C119.788 9.01781 137.635 16.4166 149.376 30.8579C155.143 37.9449 159.546 46.8629 162.446 57.3413L178.678 52.9477C175.176 40.3395 169.739 29.3821 162.317 20.1597C147.658 2.32969 126.723 -6.46191e-05 96.6388 -6.46191e-05H96.5863C66.5723 0.00786337 45.9509 9.02855 31.7667 26.8876C18.8327 43.3034 12.1437 67.2629 11.9341 91.9981L11.9341 92.0019C12.1437 116.737 18.8327 140.697 31.7667 157.113C45.9509 174.972 66.5723 183.992 96.5863 184H96.6388C123.31 183.827 142.759 176.811 158.858 160.768C179.992 139.706 179.322 113.871 172.702 98.5375C168.556 89.0019 160.441 81.4083 148.809 76.5156L141.537 88.9883ZM98.4405 129.507C88.0005 130.095 77.1544 125.409 76.6196 115.372C76.2232 107.93 82.0106 99.635 99.8271 98.6074C101.799 98.4962 103.738 98.4418 105.646 98.4418C111.447 98.4418 116.881 99.0026 121.812 100.027C119.895 123.853 110.937 128.946 98.4405 129.507Z"/>
      </svg>
    ),
  },
  /* ── 4 new icons ── */
  {
    key: 'whatsapp', left: '33%', top: '46%', size: 58, delay: 1.1, dur: 14, anim: 'D',
    bg: '#25D366',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
      </svg>
    ),
  },
  {
    key: 'snapchat', left: '65%', top: '38%', size: 54, delay: 3.5, dur: 13, anim: 'E',
    bg: '#FFFC00',
    icon: (
      <svg viewBox="0 0 24 24" fill="#000" style={{ width: '55%', height: '55%' }}>
        <path d="M12.206.793c.99 0 4.347.276 5.93 3.821.529 1.193.403 3.219.299 4.847l-.003.06c-.012.18-.022.345-.03.51.075.045.203.09.401.09.3-.016.659-.12 1.033-.301.165-.088.344-.104.464-.104.182 0 .359.029.509.09.45.149.734.479.734.838.015.449-.39.839-1.213 1.168-.089.029-.209.075-.344.119-.45.135-1.139.36-1.333.81-.09.224-.061.524.12.868l.015.015c.06.136 1.526 3.475 4.791 4.014.255.044.435.27.42.509 0 .075-.015.149-.045.225-.24.569-1.273.988-3.146 1.271-.059.091-.12.375-.164.57-.029.179-.074.36-.134.553-.076.271-.27.405-.555.405h-.03c-.135 0-.313-.031-.538-.074-.36-.075-.765-.135-1.273-.135-.3 0-.599.015-.913.074-.6.104-1.123.464-1.723.884-.853.599-1.826 1.288-3.294 1.288-.06 0-.119-.015-.18-.015h-.149c-1.468 0-2.427-.675-3.279-1.288-.599-.42-1.107-.779-1.707-.884-.314-.045-.629-.074-.928-.074-.54 0-.958.089-1.288.149-.195.045-.36.074-.51.074-.42 0-.523-.224-.583-.42-.061-.192-.09-.389-.135-.567-.046-.181-.105-.494-.166-.57-1.918-.222-2.95-.642-3.189-1.226-.031-.063-.052-.15-.055-.225-.015-.243.165-.465.42-.509 3.264-.54 4.73-3.879 4.791-4.02l.016-.029c.18-.345.224-.645.119-.869-.195-.434-.884-.658-1.332-.809-.121-.029-.24-.074-.346-.119-1.107-.435-1.257-.9-1.197-1.169.09-.479.674-.793 1.168-.793.135 0 .27.029.405.074.42.194.826.299 1.168.299.234 0 .384-.06.465-.105l-.046-.569c-.098-1.626-.225-3.651.304-4.837C7.392 1.077 10.739.807 11.729.807l.419-.015h.06z"/>
      </svg>
    ),
  },
  {
    key: 'reddit', left: '86%', top: '8%', size: 56, delay: 0.3, dur: 12, anim: 'A',
    bg: '#FF4500',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z"/>
      </svg>
    ),
  },
  {
    key: 'bluesky', left: '27%', top: '26%', size: 52, delay: 2.8, dur: 11, anim: 'B',
    bg: '#0085FF',
    icon: (
      <svg viewBox="0 0 24 24" fill="white" style={{ width: '55%', height: '55%' }}>
        <path d="M12 10.8c-1.087-2.114-4.046-6.053-6.798-7.995C2.566.944 1.561 1.266.902 1.565.139 1.908 0 3.08 0 3.768c0 .69.378 5.65.624 6.479.815 2.736 3.713 3.66 6.383 3.364.144-.016.288-.032.43-.048-.144.016-.288.048-.43.08-2.685.578-5.115 2.139-4.934 5.195.128 2.182 1.665 3.162 3.358 3.162 1.693 0 4.148-1.115 5.571-2.613.443-.473.715-.765.998-1.388.283.623.555.915.998 1.388 1.423 1.498 3.878 2.613 5.571 2.613 1.693 0 3.23-.98 3.358-3.162.181-3.056-2.249-4.617-4.934-5.195-.142-.032-.286-.064-.43-.08.142.016.286.032.43.048 2.67.296 5.568-.628 6.383-3.364.246-.829.624-5.789.624-6.479 0-.688-.139-1.86-.902-2.203-.659-.299-1.664-.621-4.3 1.24C16.046 4.748 13.087 8.687 12 10.8z"/>
      </svg>
    ),
  },
];

/* ─────────────────────────────────────────────────────────────────────────
   LoginV2 — Dark navy OneUp-inspired design
───────────────────────────────────────────────────────────────────────── */
const LoginV2 = () => {
  const navigate = useNavigate();
  const { login, loginWithGoogle } = useAuth();
  const [formData, setFormData] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);

  useEffect(() => {
    const link = document.createElement('link');
    link.href = 'https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap';
    link.rel = 'stylesheet';
    document.head.appendChild(link);
    return () => { try { document.head.removeChild(link); } catch (_) {} };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    try {
      await login(formData.email, formData.password);
      toast.success('Welcome back!');
    } catch (error) {
      let msg = 'Login failed';
      if (error.code) {
        switch (error.code) {
          case 'auth/invalid-email':    msg = 'Invalid email address.'; break;
          case 'auth/user-disabled':    msg = 'User account is disabled.'; break;
          case 'auth/user-not-found':   msg = 'No account found with this email.'; break;
          case 'auth/wrong-password':   msg = 'Incorrect password.'; break;
          default:                      msg = error.message;
        }
      }
      toast.error(msg);
      setLoading(false);
    }
  };

  const handleGoogleLogin = async () => {
    try {
      setLoading(true);
      await loginWithGoogle();
      toast.success('Welcome back!');
    } catch (_) {
      setLoading(false);
    }
  };

  /* Map anim key → css animation name */
  const animName = { A: 'lv2floatA', B: 'lv2floatB', C: 'lv2floatC', D: 'lv2floatD', E: 'lv2floatE' };

  return (
    <div className="lv2-root">
      <style>{`
        .lv2-root {
          font-family: 'Plus Jakarta Sans', sans-serif;
          min-height: 100vh;
          display: flex;
          overflow: hidden;
          position: fixed;
          inset: 0;
          z-index: 50;
        }
        .lv2-root *, .lv2-root *::before, .lv2-root *::after { box-sizing: border-box; }

        /* ══════════════════════════════════════════════════════════════
           LEFT PANEL — wider (70%), lighter navy (#1a3055)
        ══════════════════════════════════════════════════════════════ */
        .lv2-left {
          flex: 0 0 70%;
          position: relative;
          background: #1a3055;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          padding: 44px 56px;
        }

        /* Subtle dot-grid */
        .lv2-left::before {
          content: '';
          position: absolute;
          inset: 0;
          background-image: radial-gradient(circle, rgba(255,255,255,0.06) 1px, transparent 1px);
          background-size: 34px 34px;
          pointer-events: none;
        }

        /* Soft indigo glow */
        .lv2-left::after {
          content: '';
          position: absolute;
          top: 40%;
          left: 40%;
          width: 700px;
          height: 700px;
          background: radial-gradient(circle, rgba(99,102,241,0.14) 0%, transparent 65%);
          pointer-events: none;
          transform: translate(-50%, -50%);
        }

        /* ══════════════════════════════════════════════════════════════
           FLOATING ICONS — 5 unique X+Y animation paths, slow motion
        ══════════════════════════════════════════════════════════════ */
        .lv2-icon {
          position: absolute;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 10px 36px rgba(0,0,0,0.35), 0 2px 10px rgba(0,0,0,0.25);
          z-index: 20;
          cursor: default;
          transition: transform 0.4s ease, box-shadow 0.4s ease;
        }
        .lv2-icon:hover {
          box-shadow: 0 16px 48px rgba(0,0,0,0.5);
          filter: brightness(1.12);
        }

        /* Snapchat ghost blinking black ↔ white */
        .lv2-snap-icon {
          color: #ffffff;
        }
        @keyframes snapBlink {
          0%, 45%  { background: #000000 !important; color: #ffffff; }
          50%, 95% { background: #ffffff !important; color: #000000; }
          100%     { background: #000000 !important; color: #ffffff; }
        }

        /* Path A: drifts right-up then left-down */
        @keyframes lv2floatA {
          0%   { transform: translate(0px,   0px);  }
          20%  { transform: translate(12px, -18px); }
          45%  { transform: translate(18px,  -8px); }
          65%  { transform: translate(7px,  -22px); }
          85%  { transform: translate(-5px, -12px); }
          100% { transform: translate(0px,   0px);  }
        }
        /* Path B: drifts left-up */
        @keyframes lv2floatB {
          0%   { transform: translate(0px,   0px);  }
          25%  { transform: translate(-14px,-16px); }
          50%  { transform: translate(-8px, -24px); }
          75%  { transform: translate(-18px, -9px); }
          100% { transform: translate(0px,   0px);  }
        }
        /* Path C: wider right sweep */
        @keyframes lv2floatC {
          0%   { transform: translate(0px,   0px);  }
          30%  { transform: translate(20px, -10px); }
          55%  { transform: translate(10px, -22px); }
          78%  { transform: translate(22px,  -6px); }
          100% { transform: translate(0px,   0px);  }
        }
        /* Path D: gentle left drift */
        @keyframes lv2floatD {
          0%   { transform: translate(0px,   0px);  }
          22%  { transform: translate(-10px,-20px); }
          48%  { transform: translate(-20px,-10px); }
          72%  { transform: translate(-5px, -26px); }
          100% { transform: translate(0px,   0px);  }
        }
        /* Path E: diagonal up-right big arc */
        @keyframes lv2floatE {
          0%   { transform: translate(0px,   0px);  }
          33%  { transform: translate(16px, -14px); }
          58%  { transform: translate(24px, -24px); }
          82%  { transform: translate(10px,  -8px); }
          100% { transform: translate(0px,   0px);  }
        }

        /* ══════════════════════════════════════════════════════════════
           LEFT CONTENT
        ══════════════════════════════════════════════════════════════ */
        .lv2-top-logo {
          position: relative;
          z-index: 10;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .lv2-headline-wrap {
          position: relative;
          z-index: 10;
          margin-bottom: 32px;
        }

        .lv2-eyebrow {
          font-size: 11px;
          font-weight: 600;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: rgba(165,180,252,0.85);
          margin-bottom: 14px;
        }

        .lv2-headline {
          font-family: 'Sora', sans-serif;
          font-size: 40px;
          font-weight: 700;
          line-height: 1.18;
          letter-spacing: -0.8px;
          color: #fff;
          margin-bottom: 18px;
        }
        .lv2-headline span {
          background: linear-gradient(90deg, #818cf8, #c084fc);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }

        .lv2-subtext {
          font-size: 15.5px;
          color: rgba(255,255,255,0.48);
          line-height: 1.65;
          max-width: 440px;
        }

        .lv2-stats {
          display: flex;
          gap: 16px;
          position: relative;
          z-index: 10;
          flex-wrap: wrap;
        }
        .lv2-stat {
          background: rgba(255,255,255,0.07);
          border: 1px solid rgba(255,255,255,0.12);
          border-radius: 12px;
          padding: 12px 20px;
          backdrop-filter: blur(10px);
        }
        .lv2-stat-num {
          font-family: 'Sora', sans-serif;
          font-size: 22px;
          font-weight: 700;
          color: #fff;
          line-height: 1;
        }
        .lv2-stat-label {
          font-size: 11px;
          color: rgba(255,255,255,0.42);
          margin-top: 3px;
          font-weight: 500;
          letter-spacing: 0.03em;
        }

        /* Connection lines */
        .lv2-lines {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
          z-index: 3;
        }
        @keyframes dashMove { to { stroke-dashoffset: -150; } }

        /* Back button */
        .lv2-back {
          font-size: 13px;
          font-weight: 500;
          color: rgba(255,255,255,0.48);
          display: flex;
          align-items: center;
          gap: 6px;
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
          transition: color .2s;
        }
        .lv2-back:hover { color: rgba(255,255,255,0.9); }

        /* ══════════════════════════════════════════════════════════════
           RIGHT PANEL — narrower (30%), pure white background
        ══════════════════════════════════════════════════════════════ */
        .lv2-right {
          flex: 0 0 30%;
          background: #ffffff;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 28px 24px;
          position: relative;
          overflow-y: auto;
        }

        .lv2-form-card {
          width: 100%;
          max-width: 320px;
        }

        .lv2-form-logo {
          margin-bottom: 24px;
          display: flex;
          align-items: center;
        }

        .lv2-form-title {
          font-family: 'Sora', sans-serif;
          font-size: 22px;
          font-weight: 700;
          color: #0a1628;
          margin-bottom: 4px;
          letter-spacing: -0.4px;
        }
        .lv2-form-sub {
          font-size: 13px;
          color: #8a96b0;
          margin-bottom: 24px;
        }

        /* Google button */
        .lv2-google-btn {
          width: 100%;
          padding: 10px 14px;
          background: #fff;
          border: 1.5px solid #e2e8f0;
          border-radius: 10px;
          color: #1a1a2e;
          font-family: inherit;
          font-size: 13.5px;
          font-weight: 500;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: border-color .2s, box-shadow .2s;
          margin-bottom: 16px;
        }
        .lv2-google-btn:hover {
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99,102,241,0.1);
        }

        /* Divider */
        .lv2-divider {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 16px;
          color: #b0bbc9;
          font-size: 11px;
          letter-spacing: .06em;
          text-transform: uppercase;
        }
        .lv2-divider::before, .lv2-divider::after {
          content: '';
          flex: 1;
          height: 1px;
          background: #e8eef6;
        }

        /* Fields */
        .lv2-field { margin-bottom: 12px; }
        .lv2-label {
          display: block;
          font-size: 12px;
          font-weight: 600;
          color: #4a5568;
          margin-bottom: 5px;
        }
        .lv2-input-wrap { position: relative; }
        .lv2-input {
          width: 100%;
          padding: 10px 12px;
          border: 1.5px solid #e2e8f0;
          border-radius: 9px;
          color: #0a1628;
          font-family: inherit;
          font-size: 13.5px;
          outline: none;
          transition: border-color .2s, box-shadow .2s;
          background: #fafbff;
        }
        .lv2-input:focus {
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99,102,241,0.12);
          background: #fff;
        }
        .lv2-input::placeholder { color: #b0bbc9; }
        .lv2-pw-toggle {
          position: absolute;
          right: 10px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          cursor: pointer;
          color: #8a96b0;
          padding: 0;
          display: flex;
          align-items: center;
        }

        .lv2-forgot {
          font-size: 11.5px;
          color: #6366f1;
          text-decoration: none;
          font-weight: 500;
        }
        .lv2-forgot:hover { text-decoration: underline; }

        /* Submit */
        .lv2-submit {
          width: 100%;
          padding: 12px;
          background: linear-gradient(135deg, #4f46e5, #7c3aed);
          border: none;
          border-radius: 10px;
          color: #fff;
          font-family: inherit;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          margin-top: 16px;
          transition: opacity .2s, transform .15s, box-shadow .2s;
          box-shadow: 0 4px 14px rgba(79,70,229,0.38);
        }
        .lv2-submit:hover:not(:disabled) {
          opacity: .92;
          transform: translateY(-1px);
          box-shadow: 0 6px 20px rgba(79,70,229,0.48);
        }
        .lv2-submit:disabled { opacity: 0.65; cursor: not-allowed; }

        .lv2-signup-line {
          text-align: center;
          font-size: 12.5px;
          color: #8a96b0;
          margin-top: 14px;
        }
        .lv2-signup-line a {
          color: #6366f1;
          text-decoration: none;
          font-weight: 600;
        }
        .lv2-signup-line a:hover { text-decoration: underline; }

        @media (max-width: 900px) {
          .lv2-left { display: none; }
          .lv2-right { flex: 1; }
        }
      `}</style>

      {/* ══════════════ LEFT PANEL ══════════════ */}
      <div className="lv2-left">
        {/* Animated dashed connection lines */}
        <svg className="lv2-lines" viewBox="0 0 900 800" preserveAspectRatio="none">
          {[
            [36, 64,  198, 208],
            [198, 208, 342, 80],
            [342, 80,  513, 496],
            [513, 496, 648, 144],
            [108, 320, 198, 208],
            [198, 208, 297, 576],
            [648, 144, 774, 624],
            [297, 208, 585, 304],
          ].map(([x1, y1, x2, y2], i) => (
            <line key={i} x1={x1} y1={y1} x2={x2} y2={y2}
              stroke="rgba(129,140,248,0.1)" strokeWidth="1.5"
              strokeDasharray="12 9"
              style={{ animation: `dashMove ${6 + i * 0.8}s linear infinite` }}
            />
          ))}
        </svg>

        {/* Floating icons */}
        {FLOATING_ICONS.map((ic) => (
          <div
            key={ic.key}
            className="lv2-icon"
            style={{
              left: ic.left,
              top: ic.top,
              width: ic.size,
              height: ic.size,
              background: ic.bg,
              animation: `${animName[ic.anim]} ${ic.dur}s ease-in-out ${ic.delay}s infinite`,
            }}
          >
            {ic.icon}
          </div>
        ))}

        {/* Top bar */}
        <div className="lv2-top-logo">
          <SocialEntanglerLogo />
          <button className="lv2-back" onClick={() => navigate('/')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12" /><polyline points="12 19 5 12 12 5" />
            </svg>
            Back to home
          </button>
        </div>

        {/* Push headline toward center */}
        <div style={{ flex: 1, minHeight: 60 }} />

        {/* Headline block */}
        <div className="lv2-headline-wrap">
          <p className="lv2-eyebrow">✦ All-in-one social media platform</p>
          <h1 className="lv2-headline">
            Schedule smarter.<br />
            <span>Grow faster.</span>
          </h1>
          <p className="lv2-subtext">
            Join thousands of creators and brands who trust SocialEntangle to plan, publish,
            and analyze content across every platform — from one beautiful dashboard.
          </p>
        </div>

        {/* Stats row */}
        <div className="lv2-stats">
          {[
            { num: '10K+', label: 'Active users' },
            { num: '1M+',  label: 'Posts scheduled' },
            { num: '12',   label: 'Platforms supported' },
          ].map(({ num, label }) => (
            <div key={label} className="lv2-stat">
              <div className="lv2-stat-num">{num}</div>
              <div className="lv2-stat-label">{label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ══════════════ RIGHT PANEL ══════════════ */}
      <div className="lv2-right">
        <div className="lv2-form-card">
          <div className="lv2-form-logo">
            <SocialEntanglerLogo />
          </div>

          <h2 className="lv2-form-title">Login</h2>
          <p className="lv2-form-sub">Welcome back! Good to see you again.</p>

          {/* Google — at top */}
          <button className="lv2-google-btn" onClick={handleGoogleLogin} disabled={loading} style={{ marginBottom: 0 }}>
            <svg width="17" height="17" viewBox="0 0 48 48">
              <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.2l6.7-6.7C35.7 2.5 30.2 0 24 0 14.7 0 6.7 5.5 2.7 13.5l7.8 6C12.5 13.1 17.8 9.5 24 9.5z" />
              <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.5 2.9-2.2 5.4-4.7 7.1l7.4 5.7c4.3-4 6.1-9.9 6.1-16.8z" />
              <path fill="#FBBC05" d="M10.5 28.5a14.9 14.9 0 010-9.1l-7.8-6A24 24 0 000 24c0 3.9.9 7.5 2.7 10.6l7.8-6.1z" />
              <path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.5l-7.4-5.7c-2 1.4-4.6 2.2-7.8 2.2-6.2 0-11.5-3.6-13.5-9l-7.8 6C6.7 42.5 14.7 48 24 48z" />
            </svg>
            Continue with Google
          </button>

          <div className="lv2-divider" style={{ marginTop: 14, marginBottom: 14 }}>or</div>

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="lv2-field">
              <label className="lv2-label" htmlFor="lv2-email">Email*</label>
              <div className="lv2-input-wrap">
                <input
                  id="lv2-email"
                  type="email"
                  className="lv2-input"
                  placeholder="name@company.com"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                />
              </div>
            </div>

            <div className="lv2-field">
              <label className="lv2-label" htmlFor="lv2-pw">Password*</label>
              <div className="lv2-input-wrap">
                <input
                  id="lv2-pw"
                  type={showPw ? 'text' : 'password'}
                  className="lv2-input"
                  placeholder="Enter at least 8 characters"
                  required
                  style={{ paddingRight: '36px' }}
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                />
                <button type="button" className="lv2-pw-toggle" onClick={() => setShowPw(v => !v)}>
                  {showPw ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                  ) : (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                  )}
                </button>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 5 }}>
                <Link to="/forgot-password" className="lv2-forgot">Forgot password</Link>
                <Link to="/signup" className="lv2-forgot">Create account</Link>
              </div>
            </div>

            <button type="submit" className="lv2-submit" disabled={loading}>
              {loading ? 'Signing in…' : 'Log In'}
            </button>
          </form>


          <p className="lv2-signup-line">
            No account? <Link to="/signup">Sign up free</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginV2;
