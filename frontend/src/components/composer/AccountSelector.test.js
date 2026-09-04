import React from 'react';
import { renderToString } from 'react-dom/server';
import AccountSelector from './AccountSelector';
import PlatformEditor from './PlatformEditor';
import { FaTwitter, FaInstagram } from 'react-icons/fa';

describe('AccountSelector and PlatformEditor rendering tests', () => {
  const mockAccounts = [
    {
      id: '1',
      platform: 'twitter',
      platform_username: 'tw_user',
      picture_url: 'https://example.com/pic.png',
    },
    {
      id: '2',
      platform: 'instagram',
      platform_username: 'ig_user',
      picture_url: null,
    },
  ];

  const platformIcons = {
    twitter: { icon: FaTwitter, color: 'text-sky-500' },
    instagram: { icon: FaInstagram, color: 'text-pink-500' },
  };

  const getAvatarColor = () => 'bg-blue-500';

  it('renders AccountSelector with connected accounts cleanly', () => {
    const html = renderToString(
      <AccountSelector
        accounts={mockAccounts}
        loading={false}
        selectedAccounts={['1']}
        onToggle={() => {}}
        platformIcons={platformIcons}
        getAvatarColor={getAvatarColor}
      />
    );
    expect(html).toContain('Post to');
    expect(html).toContain('tw_user');
    expect(html).toContain('ig_user');
  });

  it('renders PlatformEditor with null content and various platforms without throwing', () => {
    expect(() => {
      renderToString(
        <PlatformEditor
          platform="twitter"
          title="Twitter / X"
          postType="universal"
          content={undefined}
          onContentChange={() => {}}
          media={[]}
          isExpanded={true}
        />
      );
    }).not.toThrow();

    expect(() => {
      renderToString(
        <PlatformEditor
          platform="instagram"
          title="Instagram"
          postType="universal"
          content=""
          onContentChange={() => {}}
          media={[]}
          isExpanded={true}
        />
      );
    }).not.toThrow();
  });
});
