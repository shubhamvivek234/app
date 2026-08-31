import React from 'react';
import { FaArrowRight, FaBell, FaCommentAlt, FaInbox } from 'react-icons/fa';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

import { formatRelativeDate, severityPillClass } from './helpers';

const RecentActivity = ({ operations, activity = [], onNavigate, now = Date.now() }) => {
  const inboxCards = [
    {
      label: 'Unread inbox',
      value: operations?.unread_inbox ?? 0,
      icon: FaInbox,
      onClick: () => onNavigate?.('/publish'),
    },
    {
      label: 'Unread comments',
      value: operations?.unread_comments ?? 0,
      icon: FaCommentAlt,
      onClick: () => onNavigate?.('/publish'),
    },
    {
      label: 'Unread DMs',
      value: operations?.unread_dms ?? 0,
      icon: FaBell,
      onClick: () => onNavigate?.('/publish'),
    },
  ];

  return (
    <Card className="flex h-full flex-col border-slate-200 bg-white shadow-sm lg:h-[540px] dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="border-b border-slate-100 pb-5 dark:border-slate-800">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Recent Activity</p>
        <CardTitle className="mt-2 text-xl text-slate-950 dark:text-slate-100">Inbox and workspace signals</CardTitle>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-6 pt-6">
        <div className="grid gap-3 md:grid-cols-3">
          {inboxCards.map(({ label, value, icon: Icon, onClick }) => (
            <button
              key={label}
              type="button"
              onClick={onClick}
              className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-left transition-colors hover:border-slate-300 hover:bg-white dark:border-slate-800 dark:bg-slate-800/60 dark:hover:border-slate-700 dark:hover:bg-slate-800"
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-slate-600 dark:text-slate-400">{label}</p>
                  <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-950 dark:text-slate-100">{value}</p>
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-slate-600 shadow-sm dark:bg-slate-700 dark:text-slate-300">
                  <Icon />
                </div>
              </div>
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {activity.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-400">
              No recent workspace notifications yet.
            </div>
          ) : activity.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate?.(item.target_path || '/dashboard')}
              className="flex w-full items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-4 text-left transition-colors hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-800/60 dark:hover:border-slate-700 dark:hover:bg-slate-800"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide', severityPillClass(item.severity))}>
                    {item.severity}
                  </span>
                  <span className="text-xs text-slate-500 dark:text-slate-400">{formatRelativeDate(item.created_at, now)}</span>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-300">{item.message}</p>
              </div>
              <FaArrowRight className="mt-1 shrink-0 text-slate-400 dark:text-slate-500" />
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default RecentActivity;
