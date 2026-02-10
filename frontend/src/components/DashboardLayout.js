import React from 'react';
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
  FaLayerGroup
} from 'react-icons/fa';
import { Button } from '@/components/ui/button';

const DashboardLayout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const navigation = {
    workspace: [
      { name: 'main', path: '/dashboard', icon: FaLayerGroup },
    ],
    create: [
      { name: 'New post', path: '/create', icon: FaFileAlt },
      { name: 'Studio', path: '/studio', icon: FaMagic },
      { name: 'Bulk tools', path: '/bulk', icon: FaLayerGroup },
    ],
    posts: [
      { name: 'Calendar', path: '/calendar', icon: FaCalendarAlt },
      { name: 'All', path: '/content', icon: FaList },
      { name: 'Scheduled', path: '/content?status=scheduled', icon: FaClock },
      { name: 'Posted', path: '/content?status=published', icon: FaCheckCircle },
      { name: 'Drafts', path: '/content?status=draft', icon: FaFileAlt },
    ],
    configuration: [
      { name: 'Connections', path: '/accounts', icon: FaUsers },
      { name: 'Settings', path: '/settings', icon: FaCog },
      { name: 'API Keys', path: '/api-keys', icon: FaKey },
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

  return (
    <div className="min-h-screen bg-[#f5f7f5]">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-56 bg-white border-r border-gray-200">
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-green-500 rounded-full flex items-center justify-center">
                <span className="text-white text-xs font-bold">P</span>
              </div>
              <span className="text-lg font-semibold text-gray-900">post bridge</span>
            </div>
          </div>

          {/* Workspace */}
          <div className="px-3 py-2">
            <p className="text-xs text-gray-500 px-2 mb-1">Workspace</p>
            {navigation.workspace.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm text-gray-600 hover:text-gray-900"
                >
                  <Icon className="text-sm" />
                  {item.name}
                </Link>
              );
            })}
          </div>

          {/* Create Post Button */}
          <div className="px-3 py-2">
            <Button
              onClick={() => navigate('/create')}
              className="w-full bg-green-500 hover:bg-green-600 text-white justify-start gap-2"
              data-testid="create-post-button"
            >
              <FaPlus className="text-sm" />
              Create post
            </Button>
          </div>

          {/* Create Section */}
          <div className="px-3 py-2">
            <p className="text-xs text-gray-500 px-2 mb-1">Create</p>
            <nav className="space-y-0.5">
              {navigation.create.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    data-testid={`nav-${item.name.toLowerCase().replace(' ', '-')}`}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
                      active
                        ? 'bg-green-50 text-green-700'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <Icon className="text-sm" />
                    {item.name}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Posts Section */}
          <div className="px-3 py-2">
            <p className="text-xs text-gray-500 px-2 mb-1">Posts</p>
            <nav className="space-y-0.5">
              {navigation.posts.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    data-testid={`nav-${item.name.toLowerCase().replace(' ', '-')}`}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
                      active
                        ? 'bg-green-50 text-green-700'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <Icon className="text-sm" />
                    {item.name}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Configuration Section */}
          <div className="px-3 py-2">
            <p className="text-xs text-gray-500 px-2 mb-1">Configuration</p>
            <nav className="space-y-0.5">
              {navigation.configuration.map((item) => {
                const Icon = item.icon;
                const active = isActive(item.path);
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    data-testid={`nav-${item.name.toLowerCase().replace(' ', '-')}`}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded text-sm transition-colors ${
                      active
                        ? 'bg-green-50 text-green-700'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <Icon className="text-sm" />
                    {item.name}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Support Section */}
          <div className="px-3 py-2 mt-auto">
            <p className="text-xs text-gray-500 px-2 mb-1">Support</p>
            <nav className="space-y-0.5">
              {navigation.support.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className="flex items-center gap-2 px-2 py-1.5 rounded text-sm text-gray-600 hover:bg-gray-50"
                  >
                    <Icon className="text-sm" />
                    {item.name}
                  </Link>
                );
              })}
            </nav>
          </div>

          {/* Logout */}
          <div className="p-3 border-t border-gray-100">
            <Button
              variant="ghost"
              className="w-full justify-start gap-2 text-gray-600 hover:text-gray-900"
              onClick={handleLogout}
              data-testid="logout-button"
            >
              <FaSignOutAlt />
              Logout
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="ml-56">
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
};

export default DashboardLayout;
