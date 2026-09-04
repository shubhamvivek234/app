import React from 'react';
import { renderToString } from 'react-dom/server';
import TwitterPreview from './TwitterPreview';
import FacebookPreview from './FacebookPreview';
import InstagramPreview from './InstagramPreview';
import LinkedInPreview from './LinkedInPreview';
import PreviewPanel from './PreviewPanel';

describe('Preview components null/undefined safety', () => {
  const mockAccount = {
    id: 'acct_1',
    platform: 'twitter',
    platform_username: 'testuser',
    picture_url: null,
  };

  it('renders TwitterPreview without crash when content is undefined or empty', () => {
    expect(() => {
      renderToString(<TwitterPreview account={mockAccount} />);
    }).not.toThrow();

    expect(() => {
      renderToString(<TwitterPreview content="" account={mockAccount} />);
    }).not.toThrow();

    expect(() => {
      renderToString(<TwitterPreview content="Hello world!" account={mockAccount} />);
    }).not.toThrow();
  });

  it('renders FacebookPreview without crash when content is undefined or empty', () => {
    expect(() => {
      renderToString(<FacebookPreview account={{ ...mockAccount, platform: 'facebook' }} />);
    }).not.toThrow();

    expect(() => {
      renderToString(<FacebookPreview content="Test FB" account={{ ...mockAccount, platform: 'facebook' }} />);
    }).not.toThrow();
  });

  it('renders InstagramPreview without crash when content is undefined or empty', () => {
    expect(() => {
      renderToString(<InstagramPreview account={{ ...mockAccount, platform: 'instagram' }} />);
    }).not.toThrow();

    expect(() => {
      renderToString(<InstagramPreview content="Test IG" postFormat="Post" account={{ ...mockAccount, platform: 'instagram' }} />);
    }).not.toThrow();

    expect(() => {
      renderToString(<InstagramPreview content="Test Reel" postFormat="Reel" account={{ ...mockAccount, platform: 'instagram' }} />);
    }).not.toThrow();
  });

  it('renders LinkedInPreview without crash when content is undefined or empty', () => {
    expect(() => {
      renderToString(<LinkedInPreview account={{ ...mockAccount, platform: 'linkedin' }} />);
    }).not.toThrow();

    expect(() => {
      renderToString(<LinkedInPreview content="LinkedIn test" account={{ ...mockAccount, platform: 'linkedin' }} />);
    }).not.toThrow();
  });

  it('renders PreviewPanel for various platforms safely', () => {
    const platforms = ['twitter', 'facebook', 'instagram', 'linkedin', 'youtube', 'tiktok', 'bluesky'];
    platforms.forEach((platform) => {
      expect(() => {
        renderToString(
          <PreviewPanel
            activePlatform={platform}
            account={{ ...mockAccount, platform }}
            content={undefined}
            media={[]}
            poll={null}
          />
        );
      }).not.toThrow();
    });
  });
});
