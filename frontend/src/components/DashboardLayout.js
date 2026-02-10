import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { FaHome, FaPlus, FaCalendarAlt, FaFolder, FaLink, FaCreditCard, FaCog, FaSignOutAlt } from 'react-icons/fa';
import { Button } from '@/components/ui/button';

const DashboardLayout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const navigation = [
    { name: 'Dashboard', path: '/dashboard', icon: FaHome },
    { name: 'Create Post', path: '/create', icon: FaPlus },
    { name: 'Calendar', path: '/calendar', icon: FaCalendarAlt },
    { name: 'Content Library', path: '/content', icon: FaFolder },
    { name: 'Connected Accounts', path: '/accounts', icon: FaLink },
    { name: 'Billing', path: '/billing', icon: FaCreditCard },
    { name: 'Settings', path: '/settings', icon: FaCog },
  ];

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Sidebar */}
      <div className="fixed inset-y-0 left-0 w-64 bg-white border-r border-border">
        <div className="flex flex-col h-full">
          <div className="p-6 border-b border-border">
            <h1 className="text-2xl font-semibold text-slate-900">SocialSync</h1>
            <p className="text-sm text-slate-600 mt-1">{user?.email}</p>
          </div>
          <nav className="flex-1 p-4 space-y-1">
            {navigation.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  data-testid={`nav-${item.name.toLowerCase().replace(' ', '-')}`}
                  className={`flex items-center gap-3 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-indigo-50 text-indigo-600'
                      : 'text-slate-700 hover:bg-slate-100'
                  }`}
                >
                  <Icon className="text-lg" />
                  {item.name}
                </Link>
              );
            })}
          </nav>
          <div className="p-4 border-t border-border">
            <Button
              variant="ghost"
              className="w-full justify-start gap-3"
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
      <div className="ml-64">
        <main className="p-8">{children}</main>
      </div>
    </div>
  );
};

export default DashboardLayout;