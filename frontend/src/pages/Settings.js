import React, { useState, useRef } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { updateProfile, uploadProfilePhoto, changePassword } from '@/lib/api';
import axios from 'axios';
import { FaCamera, FaLock, FaUser, FaCrown, FaEye, FaEyeSlash, FaGoogle } from 'react-icons/fa';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const COMMON_TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "Australia/Sydney",
  "Pacific/Auckland",
];

// ─── Avatar with upload overlay ───────────────────────────────────────────────
const AvatarUpload = ({ user, onUploaded }) => {
  const inputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  // preview holds a local data-URL shown immediately while uploading.
  // It is cleared on success (so the refreshed user.picture takes over)
  // and on failure (to revert the optimistic display).
  const [preview, setPreview] = useState(null);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset input value via ref — safer than e.target in async context
    const inputEl = inputRef.current;

    if (file.size > 1 * 1024 * 1024) {
      toast.error('Image too large. Maximum size is 1 MB.');
      if (inputEl) inputEl.value = '';
      return;
    }
    if (!file.type.startsWith('image/')) {
      toast.error('Only image files are allowed.');
      if (inputEl) inputEl.value = '';
      return;
    }

    // Show local preview immediately (optimistic UI)
    const reader = new FileReader();
    reader.onload = (ev) => setPreview(ev.target.result);
    reader.readAsDataURL(file);

    setUploading(true);
    try {
      const data = await uploadProfilePhoto(file);
      // Clear the local blob preview — let the refreshed user.picture take over
      setPreview(null);
      await onUploaded(data.picture);
      toast.success('Profile photo updated');
    } catch (err) {
      const msg = err.response?.data?.detail || 'Upload failed. Please try again.';
      toast.error(msg);
      setPreview(null);
    } finally {
      setUploading(false);
      if (inputEl) inputEl.value = '';
    }
  };

  const resolvedPicture = user?.picture
    ? (user.picture.startsWith('/uploads') ? `${BACKEND_URL}${user.picture}` : user.picture)
    : null;

  // During upload show the local blob preview; afterwards show the server URL
  const avatarSrc = preview || resolvedPicture;

  const initials = (user?.name || 'U')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="relative group w-24 h-24 cursor-pointer" onClick={() => inputRef.current?.click()}>
      {/* Avatar circle */}
      {avatarSrc ? (
        <img
          src={avatarSrc}
          alt="Profile"
          className="w-24 h-24 rounded-full object-cover ring-4 ring-white shadow-md"
        />
      ) : (
        <div className="w-24 h-24 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 flex items-center justify-center text-white text-2xl font-bold ring-4 ring-white shadow-md select-none">
          {initials}
        </div>
      )}

      {/* Hover overlay */}
      <div className={`absolute inset-0 rounded-full bg-black/40 flex flex-col items-center justify-center transition-opacity ${uploading ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
        {uploading ? (
          <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
        ) : (
          <>
            <FaCamera className="text-white text-lg" />
            <span className="text-white text-[10px] mt-1 font-medium">Change</span>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFile}
      />
    </div>
  );
};

// ─── Show/hide password input ─────────────────────────────────────────────────
const PasswordInput = ({ id, placeholder, value, onChange, ...props }) => {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input
        id={id}
        type={show ? 'text' : 'password'}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        className="pr-10"
        {...props}
      />
      <button
        type="button"
        tabIndex={-1}
        onClick={() => setShow((v) => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors"
      >
        {show ? <FaEyeSlash size={14} /> : <FaEye size={14} />}
      </button>
    </div>
  );
};

// ─── Section card ─────────────────────────────────────────────────────────────
const Card = ({ icon: Icon, title, subtitle, children }) => (
  <div className="bg-offwhite rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
    <div className="px-6 pt-5 pb-4 border-b border-slate-100 flex items-center gap-3">
      <div className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center text-slate-500">
        <Icon size={14} />
      </div>
      <div>
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
    </div>
    <div className="px-6 py-5">{children}</div>
  </div>
);

// ─── Main page ────────────────────────────────────────────────────────────────
const Settings = () => {
  const { user, refreshUser, logout } = useAuth();

  // ── Profile form ──
  const [name, setName] = useState(user?.name || '');
  const [timezone, setTimezone] = useState(user?.timezone || 'UTC');
  const [savingProfile, setSavingProfile] = useState(false);

  const handleProfileSave = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSavingProfile(true);
    try {
      await updateProfile({ name: name.trim(), timezone });
      await refreshUser();
      toast.success('Profile updated');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update profile');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleAvatarUploaded = async (newPictureUrl) => {
    // Refresh the user object so the new picture URL is reflected everywhere
    try {
      await refreshUser();
    } catch (_) {
      // refreshUser failed silently — not a blocking error
    }
  };

  // ── GDPR state ──
  const [exportingData, setExportingData] = useState(false);

  // ── Password form ──
  // Guard: treat as indeterminate (null) while user is still loading,
  // so we don't flash the "Google user" panel for email users.
  const isGoogleUser = user === null ? null : !user.has_password;
  const [pwForm, setPwForm] = useState({ old: '', new: '', confirm: '' });
  const [savingPw, setSavingPw] = useState(false);

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    if (pwForm.new !== pwForm.confirm) {
      toast.error('New passwords do not match.');
      return;
    }
    if (pwForm.new.length < 8) {
      toast.error('New password must be at least 8 characters.');
      return;
    }
    setSavingPw(true);
    try {
      await changePassword({ old_password: pwForm.old, new_password: pwForm.new });
      toast.success('Password updated successfully');
      setPwForm({ old: '', new: '', confirm: '' });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to change password');
    } finally {
      setSavingPw(false);
    }
  };

  const handleExportData = async () => {
    setExportingData(true);
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/gdpr/export`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'my_socialentangler_data.json';
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Data export downloaded successfully.');
    } catch {
      toast.error('Failed to export data. Please try again.');
    } finally {
      setExportingData(false);
    }
  };

  const handleDeleteAccount = async () => {
    const confirmed = window.confirm(
      'Are you absolutely sure? This will permanently delete your account, all posts, and connected accounts. This CANNOT be undone.'
    );
    if (!confirmed) return;
    const doubleConfirmed = window.confirm('Final warning: Delete your account permanently?');
    if (!doubleConfirmed) return;
    try {
      await axios.delete(`${process.env.REACT_APP_BACKEND_URL}/api/gdpr/delete-account`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
      });
      toast.success('Account deleted. Goodbye!');
      logout();
    } catch {
      toast.error('Failed to delete account. Please contact support.');
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-2xl space-y-6">

        {/* ── Page header ── */}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Settings</h1>
          <p className="text-sm text-slate-500 mt-1">Manage your account and preferences</p>
        </div>

        {/* ── Profile card ── */}
        <Card icon={FaUser} title="Profile" subtitle="Your public profile information">
          <div className="flex items-start gap-6">
            {/* Avatar */}
            <AvatarUpload user={user} onUploaded={handleAvatarUploaded} />

            {/* Form */}
            <form onSubmit={handleProfileSave} className="flex-1 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="name" className="text-xs font-medium text-slate-600">Full Name</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  data-testid="name-input"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs font-medium text-slate-600">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={user?.email || ''}
                  disabled
                  className="bg-slate-50 text-slate-500 cursor-not-allowed"
                  data-testid="email-input"
                />
                <p className="text-[11px] text-slate-400">Email cannot be changed.</p>
              </div>

              {/* Timezone Setting */}
              <div className="space-y-1.5">
                <Label htmlFor="timezone" className="text-xs font-medium text-slate-600">Timezone</Label>
                <select
                  id="timezone"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  data-testid="timezone-select"
                >
                  {COMMON_TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>{tz}</option>
                  ))}
                </select>
                <p className="text-[11px] text-slate-400">
                  Used for scheduling posts. All times are stored in UTC and displayed in your local timezone.
                </p>
              </div>

              <div className="pt-1">
                <Button
                  type="submit"
                  disabled={savingProfile || !name.trim() || (name === user?.name && timezone === (user?.timezone || 'UTC'))}
                  size="sm"
                  data-testid="save-settings-button"
                >
                  {savingProfile ? 'Saving…' : 'Save changes'}
                </Button>
              </div>
            </form>
          </div>

          <p className="text-[11px] text-slate-400 mt-4 flex items-center gap-1">
            <FaCamera size={10} />
            Click the photo to upload a new one. Max 1 MB · JPEG, PNG, GIF, WebP.
          </p>
        </Card>

        {/* ── Password card ── */}
        <Card
          icon={FaLock}
          title="Password"
          subtitle={
            isGoogleUser === null ? 'Loading…'
            : isGoogleUser ? 'Not available for Google sign-in accounts'
            : 'Change your login password'
          }
        >
          {isGoogleUser === null ? (
            <div className="h-10 flex items-center">
              <div className="w-4 h-4 border-2 border-slate-300 border-t-slate-600 rounded-full animate-spin" />
            </div>
          ) : isGoogleUser ? (
            <div className="flex items-center gap-3 py-3 px-4 bg-slate-50 rounded-xl border border-slate-100">
              <div className="w-8 h-8 rounded-full bg-offwhite border border-slate-200 flex items-center justify-center shadow-sm">
                <FaGoogle className="text-slate-500" size={13} />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-700">Signed in with Google</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Password change isn't available for Google accounts. Manage your password at{' '}
                  <a
                    href="https://myaccount.google.com/security"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-green-600 hover:underline"
                  >
                    myaccount.google.com
                  </a>
                </p>
              </div>
            </div>
          ) : (
            <form onSubmit={handlePasswordChange} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="old-password" className="text-xs font-medium text-slate-600">Current password</Label>
                <PasswordInput
                  id="old-password"
                  placeholder="Enter current password"
                  value={pwForm.old}
                  onChange={(e) => setPwForm((p) => ({ ...p, old: e.target.value }))}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="new-password" className="text-xs font-medium text-slate-600">New password</Label>
                <PasswordInput
                  id="new-password"
                  placeholder="Min. 8 characters"
                  value={pwForm.new}
                  onChange={(e) => setPwForm((p) => ({ ...p, new: e.target.value }))}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="confirm-password" className="text-xs font-medium text-slate-600">Confirm new password</Label>
                <PasswordInput
                  id="confirm-password"
                  placeholder="Repeat new password"
                  value={pwForm.confirm}
                  onChange={(e) => setPwForm((p) => ({ ...p, confirm: e.target.value }))}
                />
              </div>

              {/* Strength hint */}
              {pwForm.new && (
                <div className="flex gap-1.5">
                  {[4, 8, 12].map((len, i) => (
                    <div
                      key={i}
                      className={`h-1 flex-1 rounded-full transition-colors ${
                        pwForm.new.length >= len
                          ? i === 0 ? 'bg-red-400' : i === 1 ? 'bg-yellow-400' : 'bg-green-500'
                          : 'bg-slate-200'
                      }`}
                    />
                  ))}
                  <span className="text-[11px] text-slate-400 ml-1">
                    {pwForm.new.length < 4 ? 'Too short' : pwForm.new.length < 8 ? 'Weak' : pwForm.new.length < 12 ? 'Good' : 'Strong'}
                  </span>
                </div>
              )}

              {pwForm.confirm && pwForm.new !== pwForm.confirm && (
                <p className="text-xs text-red-500">Passwords do not match.</p>
              )}

              <div className="pt-1">
                <Button
                  type="submit"
                  size="sm"
                  disabled={savingPw || !pwForm.old || !pwForm.new || !pwForm.confirm}
                >
                  {savingPw ? 'Updating…' : 'Update password'}
                </Button>
              </div>
            </form>
          )}
        </Card>

        {/* ── Subscription card ── */}
        <Card icon={FaCrown} title="Subscription" subtitle="Your current plan">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                  user?.subscription_status === 'active'
                    ? 'bg-green-100 text-green-700'
                    : 'bg-slate-100 text-slate-600'
                }`}>
                  {user?.subscription_status === 'active' ? 'Active' : 'Free'}
                </span>
                {user?.subscription_plan && (
                  <span className="text-sm font-medium text-slate-700 capitalize">
                    {user.subscription_plan} plan
                  </span>
                )}
              </div>
              {user?.subscription_end_date && (
                <p className="text-xs text-slate-500">
                  Renews on {new Date(user.subscription_end_date).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
        </Card>

        {/* Privacy & Data (GDPR) */}
        <div className="bg-offwhite rounded-xl border border-slate-200 p-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-1">Privacy &amp; Data</h2>
          <p className="text-sm text-slate-500 mb-5">Manage your personal data in compliance with GDPR.</p>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
              <div>
                <p className="font-medium text-slate-800 text-sm">Export My Data</p>
                <p className="text-xs text-slate-500 mt-0.5">Download all your posts, accounts, and profile data as JSON.</p>
              </div>
              <button
                onClick={handleExportData}
                disabled={exportingData}
                className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                {exportingData ? 'Preparing...' : 'Export Data'}
              </button>
            </div>
            <div className="flex items-center justify-between p-4 bg-red-50 rounded-lg border border-red-100">
              <div>
                <p className="font-medium text-red-800 text-sm">Delete Account</p>
                <p className="text-xs text-red-500 mt-0.5">Permanently delete your account and all data. Cannot be undone.</p>
              </div>
              <button
                onClick={handleDeleteAccount}
                className="px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 transition-colors"
              >
                Delete Account
              </button>
            </div>
          </div>
        </div>

      </div>
    </DashboardLayout>
  );
};

export default Settings;
