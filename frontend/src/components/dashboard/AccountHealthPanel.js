import React from 'react';
import { FaArrowRight, FaLink, FaUserCircle } from 'react-icons/fa';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

import {
  compactNumber,
  formatAbsoluteDate,
  healthPillClass,
  platformLabel,
  platformPillClass,
} from './helpers';

const AccountHealthPanel = ({ accounts = [], onNavigate }) => {
  return (
    <Card className="border-slate-200 bg-white shadow-sm">
      <CardHeader className="border-b border-slate-100 pb-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Account Health</p>
            <CardTitle className="mt-2 text-xl text-slate-950">Connected account status</CardTitle>
          </div>
          <Button variant="outline" size="sm" className="border-slate-300 bg-white" onClick={() => onNavigate?.('/accounts')}>
            Manage Accounts
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-6">
        {accounts.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm">
              <FaLink />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900">No connected accounts</h3>
            <p className="mt-2 text-sm text-slate-600">Connect social accounts to activate publishing, health checks, and platform analytics.</p>
            <Button className="mt-4" onClick={() => onNavigate?.('/accounts')}>
              Connect Accounts
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {accounts.slice(0, 6).map((account) => (
              <button
                key={account.id}
                type="button"
                onClick={() => onNavigate?.('/accounts')}
                className="flex w-full items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-left transition-colors hover:border-slate-300 hover:bg-white"
              >
                <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-200">
                  {account.picture_url ? (
                    <img src={account.picture_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <FaUserCircle className="text-2xl text-slate-500" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold', platformPillClass(account.platform))}>
                      {platformLabel(account.platform)}
                    </span>
                    <span className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold', healthPillClass(account.health_state))}>
                      {account.health_state.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="mt-3 flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">{account.display_name || account.platform_username || 'Unnamed account'}</p>
                      <p className="truncate text-sm text-slate-600">@{account.platform_username || account.account_id}</p>
                    </div>
                    <FaArrowRight className="mt-1 shrink-0 text-slate-400" />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-600">
                    {account.followers_count !== null && account.followers_count !== undefined ? (
                      <span>{compactNumber(account.followers_count)} followers</span>
                    ) : null}
                    {account.posts_count !== null && account.posts_count !== undefined ? (
                      <span>{compactNumber(account.posts_count)} posts</span>
                    ) : null}
                    {account.expires_at ? <span>Expires {formatAbsoluteDate(account.expires_at)}</span> : null}
                  </div>
                  {account.health_message ? (
                    <p className="mt-2 text-xs leading-5 text-slate-600">{account.health_message}</p>
                  ) : null}
                </div>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default AccountHealthPanel;
