import React, { useEffect, useRef, useState } from 'react';
import {
  FaBell,
  FaCheckCircle,
  FaClock,
  FaExclamationTriangle,
  FaTimes,
} from 'react-icons/fa';
import { useNavigate } from 'react-router-dom';

import {
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
  high: 'bg-red-50 text-red-600 ring-red-100',
  medium: 'bg-amber-50 text-amber-600 ring-amber-100',
  low: 'bg-emerald-50 text-emerald-600 ring-emerald-100',
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

const NotificationCenter = () => {
  const [notifications, setNotifications] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);
  const navigate = useNavigate();

  const unreadCount = notifications.filter((notification) => !notification.is_read).length;

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const response = await getNotifications({ limit: 20 });
      setNotifications(Array.isArray(response) ? response : []);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
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
    } catch (error) {
      console.error('Failed to mark notifications as read', error);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen((current) => !current)}
        className="relative rounded-full p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-300"
        aria-label="Open notifications"
      >
        <FaBell className="text-lg" />
        {unreadCount > 0 && (
          <span className="absolute right-0 top-0 inline-flex min-w-[1.15rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-5 text-white ring-2 ring-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-3 w-[22rem] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50 px-4 py-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-950">Notifications</h3>
              <p className="text-xs text-slate-500">Important publishing and billing updates</p>
            </div>
            {unreadCount > 0 && (
              <span className="rounded-full bg-slate-900 px-2 py-1 text-[11px] font-medium text-white">
                {unreadCount} new
              </span>
            )}
          </div>

          <div className="max-h-[26rem] overflow-y-auto">
            {loading && notifications.length === 0 ? (
              <div className="flex h-28 items-center justify-center">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-slate-700" />
              </div>
            ) : notifications.length === 0 ? (
              <div className="px-6 py-10 text-center">
                <p className="text-sm font-medium text-slate-700">No notifications right now</p>
                <p className="mt-1 text-xs text-slate-500">Important updates will appear here.</p>
              </div>
            ) : (
              notifications.map((notification) => {
                const severity = notification.severity || 'low';
                const Icon = severityIcon[severity] || FaBell;
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
                      'group flex w-full gap-3 border-b border-slate-100 px-4 py-4 text-left transition-colors last:border-b-0 hover:bg-slate-50',
                      !notification.is_read && 'bg-emerald-50/30',
                    )}
                  >
                    <span className={cn('mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full ring-1', severityClass[severity] || severityClass.low)}>
                      <Icon className="text-sm" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-3">
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-semibold text-slate-950">
                            {notification.title || notification.type || 'Notification'}
                          </span>
                          <span className="mt-1 block text-sm leading-5 text-slate-600">
                            {notification.message}
                          </span>
                        </span>
                        <span className="shrink-0 text-[11px] text-slate-400">
                          {formatRelativeTime(notification.created_at)}
                        </span>
                      </span>
                      <span className="mt-2 flex items-center gap-2">
                        {!notification.is_read && <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />}
                        <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                          {notification.event || notification.type}
                        </span>
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
                      className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-300 opacity-0 transition hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                      title="Delete notification"
                    >
                      <FaTimes className="text-xs" />
                    </span>
                  </div>
                );
              })
            )}
          </div>

          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-3">
            <button
              type="button"
              onClick={fetchNotifications}
              className="text-xs font-medium text-slate-500 hover:text-slate-900"
            >
              Refresh
            </button>
            <button
              type="button"
              onClick={handleMarkAllRead}
              disabled={unreadCount === 0}
              className="text-xs font-medium text-slate-500 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Mark all as read
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationCenter;
