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

const LoadingState = () => (
  <div className="space-y-3">
    {[0, 1, 2].map((index) => (
      <div key={index} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-800/60">
        <div className="h-11 w-11 shrink-0 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" />
        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex gap-2">
            <div className="h-6 w-20 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" />
            <div className="h-6 w-24 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" />
          </div>
          <div className="space-y-2">
            <div className="h-4 w-40 animate-pulse rounded bg-slate-200 dark:bg-slate-700" />
            <div className="h-4 w-32 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
          </div>
          <div className="h-3 w-48 animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
        </div>
      </div>
    ))}
  </div>
);

const AccountHealthPanel = ({ accounts = [], loading = false, error = null, onNavigate }) => {
  return (
    <Card className="flex h-full flex-col border-slate-200 bg-white shadow-sm lg:h-[560px] dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="border-b border-slate-100 pb-5 dark:border-slate-800">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Account Health</p>
            <CardTitle className="mt-2 text-xl text-slate-950 dark:text-slate-100">Connected account status</CardTitle>
          </div>
          <Button variant="outline" size="sm" className="border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700" onClick={() => onNavigate?.('/accounts')}>
            Manage Accounts
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col pt-6">
        {loading && accounts.length === 0 ? (
          <LoadingState />
        ) : error && accounts.length === 0 ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6 text-center text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
            Account health could not be refreshed right now. Stored workspace data is still available elsewhere in the dashboard.
          </div>
        ) : accounts.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center dark:border-slate-700 dark:bg-slate-800/40">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm dark:bg-slate-800 dark:text-slate-400">
              <FaLink />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900 dark:text-slate-100">No connected accounts</h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Connect social accounts to activate publishing, health checks, and platform analytics.</p>
            <Button className="mt-4" onClick={() => onNavigate?.('/accounts')}>
              Connect Accounts
            </Button>
          </div>
        ) : (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
            {accounts.map((account) => (
              <button
                key={account.id}
                type="button"
                onClick={() => onNavigate?.('/accounts')}
                className="flex w-full items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-left transition-colors hover:border-slate-300 hover:bg-white dark:border-slate-800 dark:bg-slate-800/60 dark:hover:border-slate-700 dark:hover:bg-slate-800"
              >
                <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                  {account.picture_url ? (
                    <img src={account.picture_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <FaUserCircle className="text-2xl text-slate-500 dark:text-slate-400" />
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
                      <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{account.display_name || account.platform_username || 'Unnamed account'}</p>
                      <p className="truncate text-sm text-slate-600 dark:text-slate-400">@{account.platform_username || account.account_id}</p>
                    </div>
                    <FaArrowRight className="mt-1 shrink-0 text-slate-400 dark:text-slate-500" />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-600 dark:text-slate-400">
                    {account.followers_count !== null && account.followers_count !== undefined ? (
                      <span>{compactNumber(account.followers_count)} followers</span>
                    ) : null}
                    {account.posts_count !== null && account.posts_count !== undefined ? (
                      <span>{compactNumber(account.posts_count)} posts</span>
                    ) : null}
                    {account.expires_at ? <span>Expires {formatAbsoluteDate(account.expires_at)}</span> : null}
                  </div>
                  {account.health_message ? (
                    <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-400">{account.health_message}</p>
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
