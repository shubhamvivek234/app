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
  FaExclamationTriangle,
  FaUsers,
  FaCog,
  FaKey,
  FaQuestionCircle,
  FaSignOutAlt,
  FaLayerGroup,
  FaBullhorn,
  FaHashtag,
  FaChartBar,
  FaImages,
  FaFileUpload,
  FaCheckDouble,
  FaThLarge,
  FaInbox,
  FaChevronLeft,
  FaChevronRight,
  FaChevronDown,
  FaChevronUp,
  FaMoon,
  FaSun,
  FaRegClock,
  FaRss,
  FaPalette,
  FaMobileAlt,
  FaLink,
  FaBolt,
} from 'react-icons/fa';
import UnravlerLogo from '@/components/UnravlerLogo';
import NotificationCenter from '@/components/NotificationCenter';
import { useTheme } from '@/context/ThemeContext';
import { canReadApprovalsWorkspace, canReadTeamWorkspace } from '@/lib/workspacePermissions';

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

  const avatarSrc = typeof user?.avatar_url === 'string' ? user.avatar_url : null;
  const resolvedDisplayName = user?.display_name || user?.name || user?.email || 'Unravler user';

  const initials = resolvedDisplayName
    .split(' ')
    .map((w) => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="relative border-l pl-4 border-gray-200 dark:border-gray-700" ref={ref}>
      <button
        onClick={() => setOpen(prev => !prev)}
        className="flex items-center gap-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 pr-2 p-1 transition-colors focus:outline-none"
      >
        {avatarSrc && !imageError ? (
          <img
            src={avatarSrc}
            alt={resolvedDisplayName}
            className="w-8 h-8 rounded-full object-cover ring-2 ring-indigo-500/20"
            onError={() => setImageError(true)}
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 flex items-center justify-center font-bold text-xs">
            {initials}
          </div>
        )}
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 hidden sm:block truncate max-w-[120px]">{resolvedDisplayName}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-52 bg-white dark:bg-gray-900 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 py-1.5 z-50 animate-in fade-in slide-in-from-top-1 duration-150">
          <div className="px-3.5 py-2 border-b border-gray-100 dark:border-gray-800">
            <p className="text-xs font-bold text-gray-900 dark:text-gray-100 truncate">{resolvedDisplayName}</p>
            <p className="text-[11px] text-gray-400 dark:text-gray-500 truncate">{user?.email}</p>
          </div>
          <Link
            to="/settings"
            onClick={() => setOpen(false)}
            className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs font-semibold text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            <FaCog className="text-xs text-gray-400" />
            Account Settings
          </Link>
          <button
            onClick={() => { setOpen(false); onLogout(); }}
            className="w-full flex items-center gap-2.5 px-3.5 py-2 text-xs font-semibold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
          >
            <FaSignOutAlt className="text-xs" />
            Logout
          </button>
        </div>
      )}
    </div>
  );
};

const DashboardLayout = ({ children, hideSidebar = false, noPadding = false }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { isDarkMode, toggleDarkMode } = useTheme();
  const [collapsed, setCollapsed] = useState(false);

  const isCalendarOrPostRoute = location.pathname.startsWith('/calendar') || location.pathname.startsWith('/content-library');
  const [calendarExpanded, setCalendarExpanded] = useState(true);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') {
        const targetTag = e.target?.tagName?.toLowerCase();
        if (targetTag !== 'input' && targetTag !== 'textarea') {
          e.preventDefault();
          navigate('/create-post');
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [navigate]);

  const calendarSubItems = [
    { name: 'Calendar Grid', path: '/calendar', icon: FaCalendarAlt },
    { name: 'All Posts', path: '/content-library', icon: FaList },
    { name: 'Scheduled', path: '/content-library?status=scheduled', icon: FaClock },
    { name: 'Posted / Published', path: '/content-library?status=published', icon: FaCheckCircle },
    { name: 'Drafts', path: '/content-library?status=draft', icon: FaFileAlt },
    { name: 'Failed Posts', path: '/content-library?status=failed', icon: FaExclamationTriangle },
  ];

  const navigation = {
    overview: [
      { name: 'Dashboard', path: '/dashboard', icon: FaLayerGroup, badge: 'Live', badgeBg: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300' },
    ],
    growth: [
      { name: 'Viral Studio', path: '/viral-studio', icon: FaBolt, badge: 'Hooks & AI', badgeBg: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300' },
      { name: 'Smart Bio', path: '/link-in-bio', icon: FaMobileAlt, badge: 'Bio Hub', badgeBg: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300' },
      { name: 'Social Tools', path: '/social-tools', icon: FaThLarge, badge: 'Hub', badgeBg: 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300' },
      { name: 'Graphic Studio', path: '/social-graphic-studio', icon: FaPalette, badge: 'PDF & Visuals', badgeBg: 'bg-pink-50 text-pink-700 dark:bg-pink-950/50 dark:text-pink-300' },
      { name: 'Media Library', path: '/media-library', icon: FaImages },
      { name: 'Bulk Upload', path: '/bulk-upload', icon: FaFileUpload },
      { name: 'RSS Auto-Post', path: '/rss-feeds', icon: FaRss },
      { name: 'Hashtags', path: '/hashtags', icon: FaHashtag },
      { name: 'Timeslots', path: '/timeslots', icon: FaRegClock },
    ],
    workflow: [
      { name: 'Client Approvals', path: '/approvals', icon: FaCheckDouble, badge: 'Review', badgeBg: 'bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300' },
      { name: 'Social Inbox', path: '/inbox', icon: FaInbox },
    ],
    configuration: [
      { name: 'Connected Accounts', path: '/accounts', icon: FaUsers },
      { name: 'Team Members', path: '/team', icon: FaUsers },
      { name: 'Settings', path: '/settings', icon: FaCog },
      { name: 'Developers & API', path: '/developers', icon: FaKey },
    ],
    support: [
      { name: 'Help & Support', path: '/support', icon: FaQuestionCircle },
    ],
  };

  const filteredNavigation = {
    ...navigation,
    workflow: navigation.workflow.filter((item) => (
      item.path !== '/approvals' || canReadApprovalsWorkspace(user)
    )),
    configuration: navigation.configuration.filter((item) => (
      item.path !== '/team' || canReadTeamWorkspace(user)
    )),
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActive = (path) => {
    if (path.includes('?')) {
      return (location.pathname + location.search) === path;
    }
    return location.pathname === path && !location.search;
  };

  const publishActive = isActive('/publish');
  const analyticsActive = isActive('/analytics');
  const canNavigateHome = user?.subscription_status === 'active';
  const resolvedOrgName = user?.workspace_name || user?.display_name || 'My Workspace';

  return (
    <div className="min-h-screen bg-gray-50/50 dark:bg-gray-950">

      <header className="fixed top-0 left-0 right-0 h-14 bg-white dark:bg-gray-900 border-b border-gray-200/80 dark:border-gray-800 flex items-center z-50 shadow-2xs">

        <div className={`flex-shrink-0 flex items-center h-full transition-all duration-200 ${collapsed ? 'w-16 justify-center px-0' : 'w-64 px-4'}`}>
          {collapsed ? (
            <button
              onClick={() => navigate('/dashboard')}
              className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-purple-600 text-white font-extrabold flex items-center justify-center text-sm shadow-xs"
            >
              ✦
            </button>
          ) : canNavigateHome ? (
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="flex items-center rounded-md focus:outline-none"
              title="Go to dashboard"
            >
              <UnravlerLogo size="default" />
            </button>
          ) : (
            <UnravlerLogo size="default" />
          )}
        </div>

        <div className="flex items-center gap-1.5 ml-2">
          <Link
            to="/publish"
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
              publishActive
                ? 'text-indigo-700 bg-indigo-50 dark:bg-indigo-950/60 dark:text-indigo-300 dark:border dark:border-indigo-800/50 shadow-2xs'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800/80'
            }`}
          >
            <FaBullhorn className="text-xs" />
            Publish
          </Link>

          <Link
            to="/analytics"
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
              analyticsActive
                ? 'text-indigo-700 bg-indigo-50 dark:bg-indigo-950/60 dark:text-indigo-300 dark:border dark:border-indigo-800/50 shadow-2xs'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800/80'
            }`}
          >
            <FaChartBar className="text-xs" />
            Analytics & Reports
          </Link>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-3 px-6">
          <button
            onClick={toggleDarkMode}
            className="p-2 rounded-xl text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 transition-colors"
            title={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
          >
            {isDarkMode ? <FaSun className="text-sm text-amber-400" /> : <FaMoon className="text-sm" />}
          </button>
          <NotificationCenter />
          <UserMenu user={user} onLogout={handleLogout} />
        </div>
      </header>

      <div className={`fixed top-14 left-0 bottom-0 bg-white dark:bg-gray-900 border-r border-gray-200/80 dark:border-gray-800 overflow-y-auto overflow-x-hidden transition-all duration-200 flex flex-col z-40 ${hideSidebar ? 'hidden' : collapsed ? 'w-16' : 'w-64'}`}>
        
        <div className={`pt-3.5 pb-2 ${collapsed ? 'px-2 flex justify-center' : 'px-3.5'}`}>
          {collapsed ? (
            <button
              onClick={() => setCollapsed(false)}
              title="Expand Sidebar"
              className="w-10 h-10 rounded-xl bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 flex items-center justify-center hover:bg-indigo-50 dark:hover:bg-indigo-950 transition-colors"
            >
              <FaChevronRight className="text-xs" />
            </button>
          ) : (
            <div className="flex items-center justify-between p-2 rounded-xl bg-gray-50/80 dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/60">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-indigo-600 to-purple-600 text-white font-extrabold text-xs flex items-center justify-center flex-shrink-0 shadow-2xs">
                  {resolvedOrgName.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-gray-900 dark:text-white truncate leading-tight">{resolvedOrgName}</p>
                  <p className="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    {user?.subscription_tier ? `${user.subscription_tier.toUpperCase()} Plan` : 'Active Workspace'}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setCollapsed(true)}
                title="Collapse Sidebar"
                className="w-6 h-6 flex items-center justify-center rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-200/60 dark:hover:bg-gray-700 transition-colors flex-shrink-0"
              >
                <FaChevronLeft className="text-[10px]" />
              </button>
            </div>
          )}
        </div>

        <div className={`py-1.5 ${collapsed ? 'px-2' : 'px-3.5'}`}>
          <button
            onClick={() => navigate('/create-post')}
            data-testid="create-post-button"
            title="Create new post (⌘N)"
            className={`w-full group flex items-center rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold shadow-sm shadow-indigo-500/20 hover:shadow-indigo-500/30 active:scale-[0.98] transition-all ${
              collapsed ? 'justify-center py-2.5' : 'justify-between px-3.5 py-2.5 text-xs'
            }`}
          >
            <span className="flex items-center gap-2">
              <FaPlus className="text-xs flex-shrink-0" />
              {!collapsed && 'Create New Post'}
            </span>
            {!collapsed && (
              <kbd className="text-[9px] font-mono bg-white/20 px-1.5 py-0.5 rounded text-white/90">⌘N</kbd>
            )}
          </button>
        </div>

        <div className="flex-1 px-3 py-2 space-y-4 overflow-y-auto">
          <div>
            {!collapsed && (
              <p className="text-[10px] font-extrabold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2.5 mb-1.5">
                Overview & Calendar
              </p>
            )}
            <nav className="space-y-1">
              <Link
                to="/dashboard"
                title={collapsed ? 'Dashboard' : undefined}
                data-testid="nav-dashboard"
                className={`flex items-center rounded-xl text-xs font-semibold transition-all ${
                  collapsed ? 'justify-center p-2.5' : 'justify-between px-3 py-2'
                } ${
                  isActive('/dashboard')
                    ? 'bg-indigo-50/80 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 shadow-2xs font-bold border border-indigo-100/80 dark:border-indigo-900/40'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100/70 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <FaLayerGroup className={`flex-shrink-0 text-sm ${isActive('/dashboard') ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400 dark:text-gray-500'}`} />
                  {!collapsed && <span className="truncate">Dashboard</span>}
                </div>
                {!collapsed && (
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                    Live
                  </span>
                )}
              </Link>

              {collapsed ? (
                <Link
                  to="/calendar"
                  title="Master Calendar"
                  data-testid="nav-master-calendar"
                  className={`flex items-center justify-center p-2.5 rounded-xl text-xs font-semibold transition-all ${
                    isCalendarOrPostRoute
                      ? 'bg-indigo-50/80 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-bold'
                      : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                  }`}
                >
                  <FaCalendarAlt className="text-sm text-indigo-600 dark:text-indigo-400" />
                </Link>
              ) : (
                <div className={`rounded-xl border transition-all ${
                  isCalendarOrPostRoute
                    ? 'border-indigo-200/80 dark:border-indigo-900/60 bg-indigo-50/30 dark:bg-indigo-950/20'
                    : 'border-transparent'
                }`}>
                  <button
                    type="button"
                    onClick={() => setCalendarExpanded((prev) => !prev)}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-bold text-gray-700 dark:text-gray-200 hover:bg-gray-100/60 dark:hover:bg-gray-800/60 transition-colors"
                  >
                    <span className="flex items-center gap-2.5">
                      <FaCalendarAlt className={`text-sm ${isCalendarOrPostRoute ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-500'}`} />
                      Master Calendar
                    </span>
                    <span className="text-[10px] text-gray-400">
                      {calendarExpanded ? <FaChevronUp /> : <FaChevronDown />}
                    </span>
                  </button>

                  {calendarExpanded && (
                    <div className="pl-3 pr-1.5 pb-1.5 pt-0.5 space-y-0.5">
                      {calendarSubItems.map((sub) => {
                        const Icon = sub.icon;
                        const active = isActive(sub.path);
                        return (
                          <Link
                            key={sub.path}
                            to={sub.path}
                            className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all ${
                              active
                                ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-300 font-bold shadow-2xs border border-indigo-100 dark:border-indigo-900/50'
                                : 'text-gray-600 dark:text-gray-400 hover:bg-white/60 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-white'
                            }`}
                          >
                            <span className="flex items-center gap-2 truncate">
                              <Icon className={`text-xs flex-shrink-0 ${active ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400'}`} />
                              <span className="truncate">{sub.name}</span>
                            </span>
                            {sub.path.includes('status=failed') && (
                              <span className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
                            )}
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </nav>
          </div>

          <div>
            {!collapsed && (
              <p className="text-[10px] font-extrabold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2.5 mb-1.5">
                Growth & Tools
              </p>
            )}
            {collapsed && <div className="border-t border-gray-100 dark:border-gray-800 my-2" />}
            <nav className="space-y-0.5">
              {filteredNavigation.growth.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    title={collapsed ? item.name : undefined}
                    data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, '-')}`}
                    className={`flex items-center rounded-xl text-xs font-semibold transition-all ${
                      collapsed ? 'justify-center p-2.5' : 'justify-between px-3 py-2'
                    } ${
                      active
                        ? 'bg-indigo-50/80 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 shadow-2xs font-bold border border-indigo-100/80 dark:border-indigo-900/40'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100/70 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-white'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon className={`flex-shrink-0 text-sm ${active ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400 dark:text-gray-500'}`} />
                      {!collapsed && <span className="truncate">{item.name}</span>}
                    </div>
                    {!collapsed && item.badge && (
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${item.badgeBg || 'bg-gray-100 text-gray-600'}`}>
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div>
            {!collapsed && (
              <p className="text-[10px] font-extrabold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2.5 mb-1.5">
                Workflow & Inbox
              </p>
            )}
            {collapsed && <div className="border-t border-gray-100 dark:border-gray-800 my-2" />}
            <nav className="space-y-0.5">
              {filteredNavigation.workflow.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    title={collapsed ? item.name : undefined}
                    data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, '-')}`}
                    className={`flex items-center rounded-xl text-xs font-semibold transition-all ${
                      collapsed ? 'justify-center p-2.5' : 'justify-between px-3 py-2'
                    } ${
                      active
                        ? 'bg-indigo-50/80 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 shadow-2xs font-bold border border-indigo-100/80 dark:border-indigo-900/40'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100/70 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-white'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon className={`flex-shrink-0 text-sm ${active ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400 dark:text-gray-500'}`} />
                      {!collapsed && <span className="truncate">{item.name}</span>}
                    </div>
                    {!collapsed && item.badge && (
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${item.badgeBg || 'bg-gray-100 text-gray-600'}`}>
                        {item.badge}
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div>
            {!collapsed && (
              <p className="text-[10px] font-extrabold uppercase tracking-widest text-gray-400 dark:text-gray-500 px-2.5 mb-1.5">
                Configuration
              </p>
            )}
            {collapsed && <div className="border-t border-gray-100 dark:border-gray-800 my-2" />}
            <nav className="space-y-0.5">
              {filteredNavigation.configuration.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    title={collapsed ? item.name : undefined}
                    data-testid={`nav-${item.name.toLowerCase().replace(/\s+/g, '-')}`}
                    className={`flex items-center rounded-xl text-xs font-semibold transition-all ${
                      collapsed ? 'justify-center p-2.5' : 'justify-between px-3 py-2'
                    } ${
                      active
                        ? 'bg-indigo-50/80 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 shadow-2xs font-bold border border-indigo-100/80 dark:border-indigo-900/40'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100/70 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-white'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon className={`flex-shrink-0 text-sm ${active ? 'text-indigo-600 dark:text-indigo-400' : 'text-gray-400 dark:text-gray-500'}`} />
                      {!collapsed && <span className="truncate">{item.name}</span>}
                    </div>
                  </Link>
                );
              })}
            </nav>
          </div>
        </div>

        <div className={`mt-auto border-t border-gray-100 dark:border-gray-800 p-3 bg-gray-50/40 dark:bg-gray-900/60 ${collapsed ? 'px-2' : 'px-3'}`}>
          <Link
            to="/support"
            title={collapsed ? 'Help & Support' : undefined}
            className={`flex items-center rounded-xl text-xs font-semibold text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white transition-all ${
              collapsed ? 'justify-center p-2' : 'gap-2.5 px-3 py-2'
            }`}
          >
            <FaQuestionCircle className="text-gray-400 text-sm flex-shrink-0" />
            {!collapsed && 'Help & Support'}
          </Link>
          <button
            onClick={handleLogout}
            title={collapsed ? 'Logout' : undefined}
            data-testid="logout-button"
            className={`w-full flex items-center rounded-xl text-xs font-semibold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-all ${
              collapsed ? 'justify-center p-2 mt-1' : 'gap-2.5 px-3 py-2 mt-1'
            }`}
          >
            <FaSignOutAlt className="text-red-500 text-sm flex-shrink-0" />
            {!collapsed && 'Sign Out'}
          </button>
        </div>

      </div>

      <div className={`pt-14 transition-all duration-200 ${hideSidebar ? 'ml-0' : collapsed ? 'ml-16' : 'ml-64'}`}>
        <main className={hideSidebar || noPadding ? 'h-[calc(100vh-3.5rem)] overflow-hidden' : 'p-6'}>{children}</main>
      </div>

    </div>
  );
};

export default DashboardLayout;
