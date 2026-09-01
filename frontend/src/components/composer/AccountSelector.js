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
  loading = false,
  selectedAccounts,
  onToggle,
  platformIcons,
  getAvatarColor,
  onSetActive,
}) => {
  const handleClick = (account) => {
    onToggle(account.id);
    if (onSetActive) onSetActive(account);
  };

  if (loading && accounts.length === 0) {
    return (
      <div className="flex items-center gap-3 py-1">
        <p className="text-sm text-gray-400">Loading connected accounts...</p>
      </div>
    );
  }

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
    <div className="flex flex-wrap gap-2 sm:gap-2.5 items-center">
      <span className="text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400 mr-0.5">Post to</span>

      {accounts.map((account) => {
        const platformInfo = platformIcons[account.platform] || {};
        const Icon = platformInfo.icon;
        const isSelected = selectedAccounts.includes(account.id);
        const displayName = account.platform_username || account.platform;
        const accountTypeLabel = account.platform === 'linkedin'
          ? (account.account_type === 'organization' || account.linkedin_org_id ? 'Company Page' : 'Profile')
          : null;
        const hex = RING_HEX[account.platform] || '#3B82F6';

        // Use box-shadow to draw the ring: 2px gap + 2px colored ring
        const ringStyle = isSelected
          ? { boxShadow: `0 0 0 2px var(--bg-card, #ffffff), 0 0 0 3px ${hex}` }
          : {};

        return (
          <div key={account.id} className="relative group">
            <button
              onClick={() => handleClick(account)}
              className={`relative w-9 h-9 sm:w-10 sm:h-10 rounded-full transition-all duration-150 focus:outline-none ${
                isSelected ? 'opacity-100 scale-100' : 'opacity-40 hover:opacity-75 scale-95'
              }`}
              style={ringStyle}
              title={`${account.platform}: ${displayName}${accountTypeLabel ? ` (${accountTypeLabel})` : ''}`}
            >
              {account.picture_url ? (
                <img
                  src={account.picture_url}
                  alt={displayName}
                  className="w-full h-full rounded-full object-cover"
                />
              ) : (
                <div
                  className={`w-full h-full rounded-full ${getAvatarColor(displayName)} flex items-center justify-center text-white text-xs font-bold`}
                >
                  {displayName.charAt(0).toUpperCase()}
                </div>
              )}

              {/* Platform icon badge */}
              {Icon && (
                <div className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 flex items-center justify-center shadow-xs">
                  <Icon className={`text-[9px] ${platformInfo.color}`} />
                </div>
              )}
            </button>

            {/* Hover tooltip */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 dark:bg-slate-800 border dark:border-slate-700 text-white text-xs rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20 shadow-lg">
              <span className="capitalize">{account.platform}</span>: {displayName}
              {accountTypeLabel ? <span> · {accountTypeLabel}</span> : null}
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900 dark:border-t-slate-800" />
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default AccountSelector;
