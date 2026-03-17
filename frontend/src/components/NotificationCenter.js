import React, { useState, useEffect, useRef } from 'react';
import { FaBell, FaCheckCircle, FaExclamationCircle } from 'react-icons/fa';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
};

const NotificationCenter = () => {
    const [notifications, setNotifications] = useState([]);
    const [isOpen, setIsOpen] = useState(false);
    const [unreadCount, setUnreadCount] = useState(0);
    const dropdownRef = useRef(null);

    const fetchNotifications = async () => {
        try {
            const response = await axios.get(`${API}/notifications?limit=20`, {
                headers: getAuthHeaders(),
            });
            setNotifications(response.data);
            setUnreadCount(response.data.filter(n => !n.is_read).length);
        } catch (error) {
            console.error('Failed to fetch notifications:', error);
        }
    };

    useEffect(() => {
        fetchNotifications();
        // Poll every 30 seconds for new notifications
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

    const handleMarkAsRead = async (id) => {
        try {
            await axios.patch(`${API}/notifications/${id}/read`, {}, {
                headers: getAuthHeaders(),
            });
            setNotifications(notifications.map(n =>
                n.id === id ? { ...n, is_read: true } : n
            ));
            setUnreadCount(prev => Math.max(0, prev - 1));
        } catch (error) {
            console.error('Failed to mark notification as read', error);
        }
    };

    const handleDelete = async (id, e) => {
        e.stopPropagation(); // Prevent triggering mark as read
        try {
            await axios.delete(`${API}/notifications/${id}`, {
                headers: getAuthHeaders(),
            });
            setNotifications(notifications.filter(n => n.id !== id));
            // Re-calculate unread count simply
            if (!notifications.find(n => n.id === id)?.is_read) {
                setUnreadCount(prev => Math.max(0, prev - 1));
            }
        } catch (error) {
            console.error('Failed to delete notification', error);
        }
    };

    const toggleDropdown = () => setIsOpen(!isOpen);

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                onClick={toggleDropdown}
                className="relative p-2 text-gray-500 hover:text-green-500 transition-colors focus:outline-none"
            >
                <FaBell className="text-xl" />
                {unreadCount > 0 && (
                    <span className="absolute top-0 right-0 inline-flex items-center justify-center px-1.5 py-0.5 text-xs font-bold leading-none text-white transform translate-x-1/4 -translate-y-1/4 bg-red-500 rounded-full">
                        {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                )}
            </button>

            {isOpen && (
                <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden z-50">
                    <div className="p-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                        <h3 className="font-bold text-gray-800">Notifications</h3>
                        {unreadCount > 0 && (
                            <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">{unreadCount} New</span>
                        )}
                    </div>

                    <div className="max-h-96 overflow-y-auto">
                        {notifications.length === 0 ? (
                            <div className="p-6 text-center text-gray-500 text-sm">
                                No notifications right now.
                            </div>
                        ) : (
                            notifications.map((notification) => (
                                <div
                                    key={notification.id}
                                    onClick={() => !notification.is_read && handleMarkAsRead(notification.id)}
                                    className={`p-4 border-b border-gray-50 cursor-pointer transition-colors relative group
                    ${notification.is_read ? 'bg-white opacity-70' : 'bg-green-50/30 hover:bg-green-50'}`}
                                >
                                    <div className="flex items-start gap-3 w-full pr-4">
                                        <div className="mt-1 flex-shrink-0">
                                            {notification.type === 'success' ? (
                                                <FaCheckCircle className="text-green-500 text-lg" />
                                            ) : (
                                                <FaExclamationCircle className="text-red-500 text-lg" />
                                            )}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <p className={`text-sm ${notification.is_read ? 'text-gray-600' : 'text-gray-800 font-medium'}`}>
                                                {notification.message}
                                            </p>
                                            <p className="text-xs text-gray-400 mt-1">
                                                {new Date(notification.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Delete button appears on hover */}
                                    <button
                                        onClick={(e) => handleDelete(notification.id, e)}
                                        className="absolute top-4 right-4 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                                        title="Delete Notification"
                                    >
                                        ×
                                    </button>

                                    {!notification.is_read && (
                                        <div className="absolute top-5 right-4 w-2 h-2 bg-green-500 rounded-full"></div>
                                    )}
                                </div>
                            ))
                        )}
                    </div>
                    <div className="p-3 bg-gray-50 border-t border-gray-100 text-center">
                        <button
                            onClick={() => {
                                notifications.filter(n => !n.is_read).forEach(n => handleMarkAsRead(n.id));
                            }}
                            className="text-xs text-gray-500 hover:text-green-600 font-medium"
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
