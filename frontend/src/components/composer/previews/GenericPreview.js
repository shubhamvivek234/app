import React from 'react';

const GenericPreview = ({ content, media, account, platform }) => {
  const name = account?.platform_username || 'Your Account';
  const avatar = account?.picture_url;
  const mediaArray = Array.isArray(media) ? media : (media ? [media] : []);
  const firstItem  = mediaArray[0] || null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
      <div className="p-3">
        <div className="flex items-center gap-2 mb-2">
          {avatar ? (
            <img src={avatar} alt={name} className="w-8 h-8 rounded-full object-cover" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-gray-500 flex items-center justify-center text-white text-sm font-bold">
              {name.charAt(0).toUpperCase()}
            </div>
          )}
          <div>
            <p className="text-sm font-semibold text-gray-900">{name}</p>
            <p className="text-xs text-gray-400 capitalize">{platform} · Just now</p>
          </div>
        </div>

        {content ? (
          <p className="text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">{content}</p>
        ) : (
          <p className="text-sm text-gray-300 italic">Start typing to preview…</p>
        )}

        {firstItem && (
          <div className="mt-2 rounded-lg overflow-hidden border border-gray-100 relative">
            {firstItem.type === 'video' ? (
              <video src={firstItem.url} className="w-full max-h-48 object-cover" />
            ) : (
              <img src={firstItem.url} alt="" className="w-full max-h-48 object-cover" />
            )}
            {mediaArray.length > 1 && (
              <div className="absolute top-1.5 right-1.5 bg-black/60 text-white text-[10px] font-medium px-1.5 py-0.5 rounded-full">
                +{mediaArray.length - 1} more
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default GenericPreview;
