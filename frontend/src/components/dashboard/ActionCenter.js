import React from 'react';
import { FaArrowRight, FaCheckCircle, FaExclamationTriangle } from 'react-icons/fa';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

import { severityPillClass } from './helpers';

const ActionCenter = ({ actionItems = [], onNavigate }) => {
  const hasItems = actionItems.length > 0;

  return (
    <Card className="flex h-full flex-col border-slate-200 bg-white shadow-sm lg:h-[520px] dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="border-b border-slate-100 pb-5 dark:border-slate-800">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Action Center</p>
            <CardTitle className="mt-2 text-2xl text-slate-950 dark:text-slate-100">What needs attention right now</CardTitle>
          </div>
          <div className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {hasItems ? `${actionItems.length} active` : 'All clear'}
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col pt-6">
        {!hasItems ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 dark:bg-emerald-900/50">
                <FaCheckCircle className="text-emerald-600 dark:text-emerald-400" />
              </div>
              <div>
                <p className="font-semibold">No urgent blockers in the workspace.</p>
                <p className="mt-1 text-sm text-emerald-800 dark:text-emerald-400/80">Connected accounts, queue, and recent activity all look healthy right now.</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
            {actionItems.map((item) => (
              <div
                key={item.id}
                className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 transition-colors hover:border-slate-300 dark:border-slate-800 dark:bg-slate-800/60 dark:hover:border-slate-700"
              >
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-amber-500 shadow-sm dark:bg-slate-900 dark:text-amber-400">
                        <FaExclamationTriangle />
                      </div>
                      <div className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide', severityPillClass(item.severity))}>
                        {item.severity}
                      </div>
                    </div>
                    <h3 className="mt-3 text-base font-semibold text-slate-900 dark:text-slate-100">{item.title}</h3>
                    <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-400">{item.message}</p>
                  </div>
                  <Button
                    variant="outline"
                    className="shrink-0 border-slate-300 bg-white text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
                    onClick={() => onNavigate?.(item.cta_path)}
                  >
                    {item.cta_label}
                    <FaArrowRight className="ml-1" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ActionCenter;
