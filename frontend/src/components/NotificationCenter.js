import React, { useEffect, useRef, useState, useMemo } from 'react';
import {
  FaBell,
  FaCheckCircle,
  FaClock,
  FaExclamationTriangle,
  FaTimes,
  FaTrashAlt,
  FaExternalLinkAlt,
} from 'react-icons/fa';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import BellRingIcon from '@/components/ui/BellRingIcon';

import {
  clearAllNotifications,
  deleteNotification,
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/lib/api';
import { cn } from '@/lib/utils';

const severityIcon = {
  high: FaExclamationTriangle,
  medium: FaClock,
  low: FaCheckCircle,
};

const severityClass = {
  high: 'bg-red-50 text-red-600 ring-red-100 dark:bg-red-950/50 dark:text-red-400 dark:ring-red-900/60',
  medium: 'bg-amber-50 text-amber-600 ring-amber-100 dark:bg-amber-950/50 dark:text-amber-400 dark:ring-amber-900/60',
  low: 'bg-emerald-50 text-emerald-600 ring-emerald-100 dark:bg-emerald-950/50 dark:text-emerald-400 dark:ring-emerald-900/60',
};

const formatRelativeTime = (value) => {
  if (!value) return '';
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return '';
  const diffSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (diffSeconds < 60) return 'Just now';
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return new Date(value).toLocaleDateString([], { month: 'short', day: 'numeric' });
};

export const triggerNotificationRefresh = () => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('unravler:notification_refresh'));
  }
};

const NotificationCenter = () => {
  const [notifications, setNotifications] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('all');
  const dropdownRef = useRef(null);
  const navigate = useNavigate();

  const unreadCount = notifications.filter((notification) => !notification.is_read).length;

  // Dynamically update browser tab title to alert the user of new notifications
  useEffect(() => {
    const originalTitle = 'Unravler';
    if (unreadCount > 0) {
      document.title = `(${unreadCount}) Unravler`;
    } else {
      document.title = originalTitle;
    }
    return () => {
      document.title = originalTitle;
    };
  }, [unreadCount]);

  const filteredNotifications = useMemo(() => {
    if (activeTab === 'unread') {
      return notifications.filter((n) => !n.is_read);
    }
    if (activeTab === 'publishing') {
      return notifications.filter((n) => (n.event || n.type || '').startsWith('post.'));
    }
    if (activeTab === 'system') {
      return notifications.filter((n) => !(n.event || n.type || '').startsWith('post.'));
    }
    return notifications;
  }, [notifications, activeTab]);

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const response = await getNotifications({ limit: 50 });
      setNotifications(Array.isArray(response) ? response : []);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 12000);

    const handleWindowSync = () => {
      if (document.visibilityState === 'visible') {
        fetchNotifications();
      }
    };

    const handleCustomRefresh = () => {
      fetchNotifications();
    };

    window.addEventListener('focus', handleWindowSync);
    window.addEventListener('visibilitychange', handleWindowSync);
    window.addEventListener('unravler:notification_refresh', handleCustomRefresh);

    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', handleWindowSync);
      window.removeEventListener('visibilitychange', handleWindowSync);
      window.removeEventListener('unravler:notification_refresh', handleCustomRefresh);
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNotificationClick = async (notification) => {
    if (!notification.is_read) {
      try {
        await markNotificationRead(notification.id);
        setNotifications((current) => current.map((item) => (
          item.id === notification.id ? { ...item, is_read: true } : item
        )));
      } catch (error) {
        console.error('Failed to mark notification as read', error);
      }
    }

    if (notification.target_path) {
      setIsOpen(false);
      navigate(notification.target_path);
    }
  };

  const handleDelete = async (notificationId, event) => {
    event.stopPropagation();
    try {
      await deleteNotification(notificationId);
      setNotifications((current) => current.filter((item) => item.id !== notificationId));
    } catch (error) {
      console.error('Failed to delete notification', error);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((current) => current.map((item) => ({ ...item, is_read: true })));
      toast.success('All notifications marked as read');
    } catch (error) {
      console.error('Failed to mark notifications as read', error);
      toast.error('Failed to mark all as read');
    }
  };

  const handleClearAll = async () => {
    try {
      await clearAllNotifications();
      setNotifications([]);
      toast.success('All notifications cleared');
    } catch (error) {
      console.error('Failed to clear notifications', error);
      toast.error('Failed to clear notifications');
    }
  };

  const getQuickActionLabel = (event) => {
    if (event === 'post.failed' || event === 'post.dlq') return 'View post';
    if (event === 'account.reconnect_required') return 'Reconnect';
    if (event === 'billing.failed' || event === 'subscription.expiring') return 'Billing';
    if (event?.startsWith('approval.')) return 'Review';
    return null;
  };

  return (
    <div className="relative flex items-center justify-center" ref={dropdownRef}>
      {/* 
        The notification bell button visibly transforms when there are unread notifications:
        - Calm neutral gray wireframe when 0 unread
        - Luminous active amber pod, solid filled bell, sound waves, and pulsing radar beacon when > 0 unread
      */}
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className={cn(
          "relative w-9 h-9 flex items-center justify-center rounded-xl transition-all duration-200 focus:outline-none group",
          unreadCount > 0
            ? "text-amber-500 bg-amber-50/90 hover:bg-amber-100/90 dark:text-amber-400 dark:bg-amber-950/40 dark:hover:bg-amber-900/50 ring-1 ring-amber-400/50 dark:ring-amber-500/40 shadow-xs"
            : "text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
        )}
        aria-label={unreadCount > 0 ? `Open notifications (${unreadCount} unread)` : "Open notifications"}
        title={unreadCount > 0 ? `${unreadCount} unread notification${unreadCount > 1 ? 's' : ''}` : "Notifications"}
      >
        <BellRingIcon
          size={18}
          hasUnread={unreadCount > 0}
          className={cn(
            "transition-transform group-hover:scale-105",
            unreadCount > 0 ? "text-amber-500 dark:text-amber-400" : "text-gray-500 dark:text-gray-400"
          )}
        />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 flex h-4 min-w-[1rem] items-center justify-center pointer-events-none">
            {/* Ping radar ripple animation */}
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75" />
            {/* Solid badge with counter */}
            <span className="relative inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-rose-500 px-1 text-[9px] font-extrabold leading-none text-white ring-2 ring-white dark:ring-gray-900 shadow-sm">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2.5 z-50 w-[24rem] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10 dark:border-slate-800 dark:bg-slate-900 dark:shadow-black/50 animate-in fade-in slide-in-from-top-1 duration-150">
          
          {/* Header */}
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/90">
            <div>
              <h3 className="text-sm font-bold text-slate-950 dark:text-slate-100">Notifications</h3>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Publishing, account & billing updates</p>
            </div>
            {unreadCount > 0 ? (
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                {unreadCount} new
              </span>
            ) : (
              <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">All clear</span>
            )}
          </div>

          {/* Category Filter Tabs */}
          <div className="flex items-center gap-1 border-b border-slate-100 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
            {[
              { id: 'all', label: 'All' },
              { id: 'unread', label: `Unread (${unreadCount})` },
              { id: 'publishing', label: 'Publishing' },
              { id: 'system', label: 'System' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  'rounded-lg px-2.5 py-1 text-xs font-semibold transition-all',
                  activeTab === tab.id
                    ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 shadow-2xs'
                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800/80'
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* List Area */}
          <div className="max-h-[26rem] overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
            {loading && notifications.length === 0 ? (
              <div className="flex h-32 items-center justify-center">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-indigo-600 dark:border-slate-800 dark:border-t-indigo-400" />
              </div>
            ) : filteredNotifications.length === 0 ? (
              <div className="px-6 py-12 text-center">
                <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800 text-slate-400">
                  <FaBell className="text-sm" />
                </div>
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  {activeTab === 'unread' ? 'No unread notifications' : 'No notifications right now'}
                </p>
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  {activeTab === 'unread' ? 'You are all caught up!' : 'Real-time updates will appear here.'}
                </p>
              </div>
            ) : (
              filteredNotifications.map((notification) => {
                const severity = notification.severity || 'low';
                const Icon = severityIcon[severity] || FaBell;
                const quickAction = getQuickActionLabel(notification.event || notification.type);

                return (
                  <div
                    key={notification.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleNotificationClick(notification)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        handleNotificationClick(notification);
                      }
                    }}
                    className={cn(
                      'group flex w-full gap-3 px-4 py-3.5 text-left transition-colors hover:bg-slate-50/80 dark:hover:bg-slate-800/60',
                      !notification.is_read
                        ? 'bg-indigo-50/20 dark:bg-indigo-950/20'
                        : 'bg-white dark:bg-slate-900',
                    )}
                  >
                    <span className={cn('mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ring-1', severityClass[severity] || severityClass.low)}>
                      <Icon className="text-xs" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-2">
                        <span className="min-w-0">
                          <span className="block truncate text-xs font-bold text-slate-900 dark:text-slate-100">
                            {notification.title || notification.type || 'Notification'}
                          </span>
                          <span className="mt-0.5 block text-xs leading-4 text-slate-600 dark:text-slate-400 line-clamp-2">
                            {notification.message}
                          </span>
                        </span>
                        <span className="shrink-0 text-[10px] font-medium text-slate-400 dark:text-slate-500">
                          {formatRelativeTime(notification.created_at)}
                        </span>
                      </span>

                      <span className="mt-2 flex items-center justify-between">
                        <span className="flex items-center gap-1.5">
                          {!notification.is_read && <span className="h-1.5 w-1.5 rounded-full bg-indigo-600 dark:bg-indigo-400" />}
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                            {(notification.event || notification.type || '').replace('.', ' ')}
                          </span>
                        </span>

                        {quickAction && (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600 dark:text-indigo-400 hover:underline">
                            {quickAction}
                            <FaExternalLinkAlt className="text-[9px]" />
                          </span>
                        )}
                      </span>
                    </span>

                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(event) => handleDelete(notification.id, event)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          handleDelete(notification.id, event);
                        }
                      }}
                      className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-slate-300 dark:text-slate-600 opacity-0 transition hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-950/50 dark:hover:text-red-400 group-hover:opacity-100"
                      title="Delete notification"
                    >
                      <FaTimes className="text-xs" />
                    </span>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/80 px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900/90">
            <button
              type="button"
              onClick={handleClearAll}
              disabled={notifications.length === 0}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
            >
              <FaTrashAlt className="text-[10px]" />
              Clear all
            </button>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={fetchNotifications}
                className="text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 transition-colors"
              >
                Refresh
              </button>
              <button
                type="button"
                onClick={handleMarkAllRead}
                disabled={unreadCount === 0}
                className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
              >
                Mark all as read
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationCenter;
