import React from 'react';
import { FaBell, FaClock, FaFolderOpen, FaLink, FaPaperPlane, FaUserShield } from 'react-icons/fa';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const WorkspacePulse = ({ summary, operations }) => {
  const stats = [
    {
      label: 'Scheduled next',
      value: summary?.scheduled_posts ?? 0,
      icon: FaClock,
      tone: 'bg-amber-100 text-amber-700',
    },
    {
      label: 'Published total',
      value: summary?.published_posts ?? 0,
      icon: FaPaperPlane,
      tone: 'bg-emerald-100 text-emerald-700',
    },
    {
      label: 'Connected accounts',
      value: summary?.connected_accounts ?? 0,
      icon: FaLink,
      tone: 'bg-blue-100 text-blue-700',
    },
    {
      label: 'Drafts waiting',
      value: summary?.draft_posts ?? 0,
      icon: FaFolderOpen,
      tone: 'bg-slate-100 text-slate-700',
    },
  ];

  const smallStats = [
    {
      label: 'Unread notifications',
      value: operations?.unread_notifications ?? 0,
      icon: FaBell,
    },
    {
      label: 'Unread inbox',
      value: operations?.unread_inbox ?? 0,
      icon: FaUserShield,
    },
  ];

  return (
    <Card className="border-slate-200 bg-white shadow-sm">
      <CardHeader className="border-b border-slate-100 pb-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Workspace Pulse</p>
        <CardTitle className="mt-2 text-xl text-slate-950">Queue, accounts, and backlog</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6 pt-6">
        <div className="grid grid-cols-2 gap-3">
          {stats.map(({ label, value, icon: Icon, tone }) => (
            <div key={label} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
              <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${tone}`}>
                <Icon />
              </div>
              <div className="mt-4 text-2xl font-semibold text-slate-950">{value}</div>
              <div className="mt-1 text-sm text-slate-600">{label}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          {smallStats.map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm text-slate-600">{label}</p>
                  <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
                </div>
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-700">
                  <Icon />
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default WorkspacePulse;
