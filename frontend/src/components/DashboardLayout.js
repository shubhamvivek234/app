import React, { useState, useRef, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import {
  FaPlus,
  FaCalendarAlt,
  FaList,
  FaClock,
  FaCheckCircle,
  FaFileAlt,
  FaUsers,
  FaCog,
  FaKey,
  FaQuestionCircle,
  FaSignOutAlt,
  FaMagic,
  FaLayerGroup,
  FaBullhorn,
  FaHashtag,
  FaChartBar,
  FaImages,
  FaRedo,
  FaFileUpload,
  FaCheckDouble,
  FaThLarge,
  FaInbox,
  FaChevronLeft,
  FaChevronRight,
  FaMoon,
  FaSun,
  FaRegClock,
} from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import UnravlerLogo from '@/components/UnravlerLogo';
import NotificationCenter from '@/components/NotificationCenter';
import { useTheme } from '@/context/ThemeContext';

const UserMenu = ({ user, onLogout }) => {
  const [open, setOpen] = useState(false);
  const [imageError, setImageError] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Get the actual picture URL if available
  const backendUrl = process.env.REACT_APP_BACKEND_URL;
  const avatarSrc = user?.picture
    ? (user.picture.startsWith('/uploads')
        ? `${backendUrl}${user.picture}`
        : user.picture)
    : null;

  // Initials fallback
  const initials = (user?.display_name || 'U')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="relative border-l pl-4 border-gray-200 dark:border-gray-700" ref={ref}>
      <button
        onClick={() => setOpen(prev => !prev)}
        className="flex items-center gap-2 rounded-full hover:bg-gray-50 dark:hover:bg-gray-800 pr-2 transition-colors focus:outline-none"
      >
        {avatarSrc && !imageError ? (
          <img
            src={avatarSrc}
            alt={user?.display_name}
            className="w-8 h-8 rounded-full object-cover"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-green-100 text-green-700 flex items-center justify-center font-bold text-xs">
            {initials}
          </div>
        )}
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 hidden sm:block">{user?.display_name}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-48 bg-offwhite dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 py-1 z-50">
          <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-700">
            <p className="text-xs font-semibold text-gray-900 dark:text-gray-100 truncate">{user?.display_name}</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 truncate">{user?.email}</p>
          </div>
          <button
            onClick={() => { setOpen(false); onLogout(); }}
            className="w-full flex items-center gap-2 px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          >
            <FaSignOutAlt className="text-xs" />
            Logout
          </button>
        </div>
      )}
    </div>
  );
};

const DashboardLayout = ({ children, hideSidebar = false }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { isDarkMode, toggleDarkMode } = useTheme();

  const navigation = {
    workspace: [
      { name: 'Dashboard', path: '/dashboard', icon: FaLayerGroup },
    ],
    create: [
      { name: 'New post', path: '/create-post', icon: FaFileAlt },
      { name: 'Bulk Upload', path: '/bulk-upload', icon: FaFileUpload },
      { name: 'Hashtag Groups', path: '/hashtags', icon: FaHashtag },
      { name: 'Media Library', path: '/media-library', icon: FaImages },
      { name: 'Social Tools', path: '/social-tools', icon: FaThLarge },
      { name: 'Timeslots', path: '/timeslots', icon: FaRegClock },
    ],
    posts: [
      { name: 'Calendar', path: '/calendar', icon: FaCalendarAlt },
      { name: 'All', path: '/content-library', icon: FaList },
      { name: 'Scheduled', path: '/content-library?status=scheduled', icon: FaClock },
      { name: 'Posted', path: '/content-library?status=published', icon: FaCheckCircle },
      { name: 'Drafts', path: '/content-library?status=draft', icon: FaFileAlt },
      { name: 'Approvals', path: '/approvals', icon: FaCheckDouble },
      { name: 'Inbox', path: '/inbox', icon: FaInbox },
    ],
    configuration: [
      { name: 'Connections', path: '/accounts', icon: FaUsers },
      { name: 'Team', path: '/team', icon: FaUsers },
      { name: 'Settings', path: '/settings', icon: FaCog },
      { name: 'Api', path: '/api-keys', icon: FaKey },
    ],
    support: [
      { name: 'Support', path: '/support', icon: FaQuestionCircle },
    ],
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActive = (path) => {
    if (path.includes('?')) {
      return location.pathname + location.search === path;
    }
    return location.pathname === path;
  };

  const publishActive = isActive('/publish');
  const analyticsActive = isActive('/analytics');
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-offwhite dark:bg-gray-950">

      {/* ── Full-width top nav bar ── */}
      <header className="fixed top-0 left-0 right-0 h-14 bg-offwhite dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex items-center z-50">

        {/* Logo block — shrinks with sidebar */}
        <div className={`flex-shrink-0 flex items-center h-full transition-all duration-200 ${collapsed ? 'w-14 justify-center px-0' : 'w-64 px-4'}`}>
          {collapsed ? null : <UnravlerLogo size="default" />}
        </div>

        {/* Nav tabs */}
        <div className="flex items-center gap-1 ml-2">
          <Link
            to="/publish"
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              publishActive
                ? 'text-green-700 bg-green-50 dark:bg-green-900/20'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            <FaBullhorn className="text-sm" />
            Publish
          </Link>

          <Link
            to="/analytics"
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              analyticsActive
                ? 'text-green-700 bg-green-50 dark:bg-green-900/20'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            <FaChartBar className="text-sm" />
            Analytics
          </Link>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Right-side controls */}
        <div className="flex items-center gap-4 px-6">
          <button
            onClick={toggleDarkMode}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 transition-colors"
            title={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
          >
            {isDarkMode ? <FaSun className="text-sm" /> : <FaMoon className="text-sm" />}
          </button>
          <NotificationCenter />
          <UserMenu user={user} onLogout={handleLogout} />
        </div>
      </header>

      {/* ── Sidebar ── */}
      <div className={`fixed top-14 left-0 bottom-0 bg-offwhite dark:bg-gray-900 border-r border-gray-100 dark:border-gray-700 overflow-y-auto overflow-x-hidden transition-all duration-200 ${hideSidebar ? 'hidden' : collapsed ? 'w-14' : 'w-64'}`}>
        <div className="flex flex-col h-full py-3">

          {/* Workspace + collapse toggle */}
          <div className={`mb-1 ${collapsed ? 'px-2' : 'px-3'}`}>
            {!collapsed && <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2 mb-1.5">Workspace</p>}
            {navigation.workspace.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.path);
              return (
                <div key={item.path} className="flex items-center gap-1">
                  <Link
                    to={item.path}
                    title={collapsed ? item.name : undefined}
                    className={`flex items-center flex-1 py-2 rounded-lg text-sm font-medium transition-all ${collapsed ? 'justify-center px-2' : 'gap-2.5 px-2.5'} ${active ? 'bg-offwhite dark:bg-gray-800 text-green-700 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:bg-offwhite dark:hover:bg-gray-800 hover:text-gray-800 dark:hover:text-gray-100 hover:shadow-sm'}`}
                  >
                    <Icon className={`flex-shrink-0 ${active ? 'text-green-600' : 'text-gray-400'}`} />
                    {!collapsed && item.name}
                  </Link>
                  <button
                    onClick={() => setCollapsed(v => !v)}
                    title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                    className="w-6 h-6 flex items-center justify-center rounded-md text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 hover:bg-offwhite dark:hover:bg-gray-800 transition-all flex-shrink-0"
                  >
                    {collapsed ? <FaChevronRight className="text-[10px]" /> : <FaChevronLeft className="text-[10px]" />}
                  </button>
                </div>
              );
            })}
          </div>

          {/* Create Post Button */}
          <div className={`mb-3 ${collapsed ? 'px-2' : 'px-3'}`}>
            {collapsed ? (
              <button
                onClick={() => navigate('/create-post')}
                title="Create post"
                className="w-full flex items-center justify-center py-2 rounded-lg bg-green-500 hover:bg-green-600 text-white transition-colors shadow-sm"
              >
                <FaPlus className="text-xs" />
              </button>
            ) : (
              <button
                onClick={() => navigate('/create-post')}
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-green-500 hover:bg-green-600 text-white text-sm font-medium transition-colors shadow-sm"
                data-testid="create-post-button"
              >
                <FaPlus className="text-xs flex-shrink-0" />
                Create post
              </button>
            )}
          </div>

          {/* Nav helper */}
          {(() => {
            const NavItem = ({ item, active }) => {
              const Icon = item.icon;
              return (
                <Link
                  to={item.path}
                  title={collapsed ? item.name : undefined}
                  data-testid={`nav-${item.name.toLowerCase().replace(' ', '-')}`}
                  className={`flex items-center py-2 rounded-lg text-sm transition-all ${collapsed ? 'justify-center px-2' : 'gap-2.5 px-2.5'} ${active ? 'bg-offwhite dark:bg-gray-800 text-green-700 font-medium shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:bg-offwhite dark:hover:bg-gray-800 hover:text-gray-800 dark:hover:text-gray-100 hover:shadow-sm'}`}
                >
                  <Icon className={`flex-shrink-0 text-[13px] ${active ? 'text-green-600' : 'text-gray-400 dark:text-gray-500'}`} />
                  {!collapsed && item.name}
                </Link>
              );
            };

            return (
              <>
                {/* Create Section */}
                <div className={`mb-1 ${collapsed ? 'px-2' : 'px-3'}`}>
                  {!collapsed && <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2 mb-1.5">Create</p>}
                  <nav className="space-y-0.5">
                    {navigation.create.map(item => <NavItem key={item.path} item={item} active={isActive(item.path)} />)}
                  </nav>
                </div>

                {/* Posts Section */}
                <div className={`mb-1 ${collapsed ? 'px-2' : 'px-3'}`}>
                  {!collapsed && <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2 mb-1.5 mt-2">Posts</p>}
                  {collapsed && <div className="border-t border-gray-200 dark:border-gray-700 my-2" />}
                  <nav className="space-y-0.5">
                    {navigation.posts.map(item => <NavItem key={item.path} item={item} active={isActive(item.path)} />)}
                  </nav>
                </div>

                {/* Configuration Section */}
                <div className={`mb-1 ${collapsed ? 'px-2' : 'px-3'}`}>
                  {!collapsed && <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2 mb-1.5 mt-2">Configuration</p>}
                  {collapsed && <div className="border-t border-gray-200 dark:border-gray-700 my-2" />}
                  <nav className="space-y-0.5">
                    {navigation.configuration.map(item => <NavItem key={item.path} item={item} active={isActive(item.path)} />)}
                  </nav>
                </div>

                {/* Support + Logout */}
                <div className={`mt-auto ${collapsed ? 'px-2' : 'px-3'}`}>
                  {!collapsed && <p className="text-[10px] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2 mb-1.5">Support</p>}
                  {collapsed && <div className="border-t border-gray-200 dark:border-gray-700 my-2" />}
                  <nav className="space-y-0.5">
                    {navigation.support.map(item => <NavItem key={item.path} item={item} active={false} />)}
                  </nav>
                  <div className="mt-1">
                    <button
                      onClick={handleLogout}
                      title={collapsed ? 'Logout' : undefined}
                      data-testid="logout-button"
                      className={`w-full flex items-center py-2 rounded-lg text-sm text-gray-500 dark:text-gray-400 hover:bg-offwhite dark:hover:bg-gray-800 hover:text-gray-800 dark:hover:text-gray-100 hover:shadow-sm transition-all ${collapsed ? 'justify-center px-2' : 'gap-2.5 px-2.5'}`}
                    >
                      <FaSignOutAlt className="flex-shrink-0 text-[13px] text-gray-400 dark:text-gray-500" />
                      {!collapsed && 'Logout'}
                    </button>
                  </div>
                </div>
              </>
            );
          })()}

        </div>
      </div>

      {/* ── Main content (offset for top bar + sidebar) ── */}
      <div className={`pt-14 transition-all duration-200 ${hideSidebar ? 'ml-0' : collapsed ? 'ml-14' : 'ml-64'}`}>
        <main className={hideSidebar ? 'h-[calc(100vh-3.5rem)] overflow-hidden' : 'p-6'}>{children}</main>
      </div>

    </div>
  );
};

export default DashboardLayout;
