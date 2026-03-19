import React from 'react';

// Platform brand hex colors for the ring (box-shadow approach)
const RING_HEX = {
  linkedin:  '#0A66C2',
  youtube:   '#FF0000',
  twitter:   '#1DA1F2',
  facebook:  '#1877F2',
  tiktok:    '#010101',
  pinterest: '#E60023',
  bluesky:   '#0085FF',
  threads:   '#101010',
  instagram: '#E1306C',
};

const AccountSelector = ({
  accounts,
  selectedAccounts,
  onToggle,
  platformIcons,
  getAvatarColor,
  onSetActive,
}) => {
  const handleClick = (account) => {
    onToggle(account.id);
    if (onSetActive) onSetActive(account.platform);
  };

  if (accounts.length === 0) {
    return (
      <div className="flex items-center gap-3 py-1">
        <p className="text-sm text-gray-400">No connected accounts yet.</p>
        <a href="/accounts" className="text-sm text-blue-600 hover:underline font-medium">
          Connect accounts →
        </a>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap gap-3 items-center">
      <span className="text-xs font-semibold text-gray-500 mr-1">Post to</span>

      {accounts.map((account) => {
        const platformInfo = platformIcons[account.platform] || {};
        const Icon = platformInfo.icon;
        const isSelected = selectedAccounts.includes(account.id);
        const displayName = account.platform_username || account.platform;
        const hex = RING_HEX[account.platform] || '#3B82F6';

        // Use box-shadow to draw the ring: 2px white gap + 2px colored ring
        const ringStyle = isSelected
          ? { boxShadow: `0 0 0 2px white, 0 0 0 4px ${hex}` }
          : {};

        return (
          <div key={account.id} className="relative group">
            <button
              onClick={() => handleClick(account)}
              className={`relative w-11 h-11 rounded-full transition-all duration-150 focus:outline-none ${
                isSelected ? 'opacity-100' : 'opacity-50 hover:opacity-80'
              }`}
              style={ringStyle}
              title={`${account.platform}: ${displayName}`}
            >
              {account.picture_url ? (
                <img
                  src={account.picture_url}
                  alt={displayName}
                  className="w-11 h-11 rounded-full object-cover"
                />
              ) : (
                <div
                  className={`w-11 h-11 rounded-full ${getAvatarColor(displayName)} flex items-center justify-center text-white text-sm font-bold`}
                >
                  {displayName.charAt(0).toUpperCase()}
                </div>
              )}

              {/* Platform icon badge */}
              {Icon && (
                <div className="absolute -bottom-0.5 -right-0.5 w-[18px] h-[18px] rounded-full bg-offwhite border border-gray-200 flex items-center justify-center shadow-sm">
                  <Icon className={`text-[10px] ${platformInfo.color}`} />
                </div>
              )}
            </button>

            {/* Hover tooltip */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 text-white text-xs rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20 shadow-lg">
              <span className="capitalize">{account.platform}</span>: {displayName}
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default AccountSelector;
