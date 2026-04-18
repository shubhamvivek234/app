import React from 'react';
import { useNavigate } from 'react-router-dom';
import UnravlerLogo from '@/components/UnravlerLogo';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuth } from '@/context/AuthContext';
import { FaCreditCard, FaSignOutAlt, FaUser } from 'react-icons/fa';

const OnboardingHeader = ({ step }) => {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const steps = [1, 2, 3];

    return (
        <header className="w-full bg-offwhite border-b border-gray-100 py-4 px-6 fixed top-0 left-0 z-50">
            <div className="max-w-7xl mx-auto flex items-center justify-between">
                {/* Left: Logo */}
                <div className="w-48">
                    <UnravlerLogo />
                </div>

                {/* Center: Progress Steps */}
                <div className="hidden md:flex items-center space-x-4">
                    {steps.map((s, index) => (
                        <React.Fragment key={s}>
                            <div className="flex items-center">
                                <div
                                    className={`w-8 h-8 rounded-full flex items-center justify-center font-semibold text-sm transition-colors ${step >= s
                                            ? 'bg-green-500 text-white'
                                            : 'bg-gray-100 text-gray-400'
                                        }`}
                                >
                                    {step > s ? '✓' : s}
                                </div>
                            </div>
                            {index < steps.length - 1 && (
                                <div
                                    className={`w-16 h-1 transition-colors ${step > s ? 'bg-green-500' : 'bg-gray-100'
                                        }`}
                                ></div>
                            )}
                        </React.Fragment>
                    ))}
                </div>

                {/* Right: User Menu */}
                <div className="w-48 flex justify-end">
                    <DropdownMenu>
                        <DropdownMenuTrigger className="outline-none">
                            <Avatar className="h-9 w-9 cursor-pointer hover:ring-2 hover:ring-gray-200 transition-all">
                                <AvatarImage src={user?.picture} />
                                <AvatarFallback className="bg-indigo-100 text-indigo-600">
                                    {user?.name?.charAt(0) || 'U'}
                                </AvatarFallback>
                            </Avatar>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56">
                            <DropdownMenuLabel>
                                <div className="flex flex-col space-y-1">
                                    <p className="text-sm font-medium leading-none">{user?.name}</p>
                                    <p className="text-xs leading-none text-muted-foreground">
                                        {user?.email}
                                    </p>
                                </div>
                            </DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={() => navigate('/billing')} className="cursor-pointer">
                                <FaCreditCard className="mr-2 h-4 w-4" />
                                <span>Billing</span>
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={handleLogout} className="cursor-pointer text-red-600 focus:text-red-600">
                                <FaSignOutAlt className="mr-2 h-4 w-4" />
                                <span>Log out</span>
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </div>
        </header>
    );
};

export default OnboardingHeader;
