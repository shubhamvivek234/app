import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { FaExclamationTriangle } from 'react-icons/fa';
import { useAuth } from '@/context/AuthContext';

const SubscriptionExpired = () => {
    const navigate = useNavigate();
    const { logout } = useAuth();

    const handleRenew = () => {
        navigate('/payment');
    };

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-offwhite flex flex-col justify-center py-12 sm:px-6 lg:px-8">
            <div className="sm:mx-auto sm:w-full sm:max-w-md">
                <div className="bg-offwhite py-8 px-4 shadow sm:rounded-lg sm:px-10 text-center">
                    <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-red-100 mb-4">
                        <FaExclamationTriangle className="h-6 w-6 text-red-600" />
                    </div>

                    <h2 className="text-2xl font-bold text-gray-900 mb-2">Subscription Expired</h2>
                    <p className="text-gray-600 mb-6">
                        Your subscription has ended. To continue using Unravler and accessing your dashboard, please renew your subscription.
                    </p>

                    <div className="space-y-4">
                        <Button
                            onClick={handleRenew}
                            className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                        >
                            Renew Subscription
                        </Button>

                        <Button
                            variant="outline"
                            onClick={handleLogout}
                            className="w-full flex justify-center py-2 px-4 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-offwhite hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                        >
                            Log Out
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SubscriptionExpired;
