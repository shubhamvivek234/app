import React from 'react';
import FacebookPreview from './FacebookPreview';
import InstagramPreview from './InstagramPreview';
import TwitterPreview from './TwitterPreview';
import LinkedInPreview from './LinkedInPreview';
import YouTubePreview from './YouTubePreview';
import TikTokPreview from './TikTokPreview';
import GenericPreview from './GenericPreview';

/**
 * PreviewPanel — renders the preview for a SINGLE active platform.
 * Props:
 *   activePlatform  – string ('facebook' | 'instagram' | ...)
 *   account         – the social account object for that platform
 *   content         – caption string for that platform
 *   media           – uploaded media object { url, type } or null
 *   videoTitle      – YouTube video title
 *   postFormat      – Instagram post format ('Post' | 'Reel' | 'Story')
 */
const PreviewPanel = ({
  activePlatform,
  account,
  content,
  media,
  videoTitle,
  postFormat,
}) => {
  if (!activePlatform) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="w-14 h-14 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <svg className="w-6 h-6 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
        </div>
        <p className="text-sm font-medium text-gray-400">Select an account above</p>
        <p className="text-xs text-gray-300 mt-1">Preview will appear here</p>
      </div>
    );
  }

  let Preview;
  switch (activePlatform) {
    case 'facebook':  Preview = FacebookPreview;  break;
    case 'instagram': Preview = InstagramPreview; break;
    case 'twitter':   Preview = TwitterPreview;   break;
    case 'linkedin':  Preview = LinkedInPreview;  break;
    case 'youtube':   Preview = YouTubePreview;   break;
    case 'tiktok':    Preview = TikTokPreview;    break;
    default:          Preview = GenericPreview;
  }

  return (
    <Preview
      content={content}
      media={media}
      account={account}
      platform={activePlatform}
      videoTitle={videoTitle}
      postFormat={postFormat}
    />
  );
};

export default PreviewPanel;
