import React from 'react';
import { FaChartBar, FaExternalLinkAlt } from 'react-icons/fa';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { compactNumber, platformLabel } from './helpers';

const LoadingState = () => (
  <div className="space-y-6">
    <div className="rounded-2xl bg-slate-100 p-5">
      <div className="h-3 w-28 animate-pulse rounded bg-slate-200" />
      <div className="mt-4 h-10 w-20 animate-pulse rounded bg-slate-200" />
    </div>
    <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
      <div className="space-y-3">
        {[0, 1, 2].map((index) => (
          <div key={index}>
            <div className="mb-2 flex items-center justify-between">
              <div className="h-4 w-24 animate-pulse rounded bg-slate-200" />
              <div className="h-4 w-8 animate-pulse rounded bg-slate-100" />
            </div>
            <div className="h-2 rounded-full bg-slate-100">
              <div className="h-2 w-2/3 animate-pulse rounded-full bg-slate-200" />
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-6">
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map((index) => (
            <div key={index} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="h-3 w-10 animate-pulse rounded bg-slate-200" />
              <div className="mt-3 h-6 w-8 animate-pulse rounded bg-slate-200" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="h-3 w-20 animate-pulse rounded bg-slate-200" />
              <div className="mt-3 h-6 w-12 animate-pulse rounded bg-slate-200" />
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

const PerformanceSnapshot7d = ({ performance, loading = false, error = null, onNavigate }) => {
  const platformEntries = Object.entries(performance?.platform_counts || {}).sort((a, b) => b[1] - a[1]);
  const typeEntries = Object.entries(performance?.type_counts || {}).sort((a, b) => b[1] - a[1]);
  const audienceTotals = performance?.audience_totals || {};
  const audienceMetrics = [
    ['Followers', audienceTotals.followers_total],
    ['Reach', audienceTotals.reach],
    ['Impressions', audienceTotals.impressions],
    ['Profile views', audienceTotals.profile_views],
  ].filter(([, value]) => value !== undefined && value !== null);
  const maxPlatformCount = platformEntries.length ? platformEntries[0][1] : 0;
  const hasErrors = (performance?.errors || []).length > 0;

  return (
    <Card className="border-slate-200 bg-white shadow-sm">
      <CardHeader className="border-b border-slate-100 pb-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Performance Snapshot</p>
            <CardTitle className="mt-2 text-xl text-slate-950">Last 7 days</CardTitle>
          </div>
          <Button variant="outline" size="sm" className="border-slate-300 bg-white" onClick={() => onNavigate?.('/analytics')}>
            Open Analytics
            <FaExternalLinkAlt className="ml-1" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-6 pt-6">
        {loading && !performance ? (
          <LoadingState />
        ) : error && !performance ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
            The performance snapshot could not be refreshed right now. Open Analytics for deeper live metrics once the provider responses recover.
          </div>
        ) : (
          <>
        <div className="rounded-2xl bg-slate-950 p-5 text-white">
          <p className="text-sm uppercase tracking-[0.18em] text-slate-300">Published in period</p>
          <p className="mt-3 text-4xl font-semibold">{performance?.published_in_period ?? 0}</p>
        </div>

        {hasErrors ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            Some audience metrics are unavailable for one or more connected accounts. The snapshot only shows metrics the platform APIs returned successfully.
          </div>
        ) : null}

        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">Platform mix</h3>
            <div className="mt-4 space-y-3">
              {platformEntries.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
                  No published activity in the selected window yet.
                </div>
              ) : platformEntries.map(([platform, count]) => (
                <div key={platform} className="space-y-2">
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 text-sm">
                    <span className="truncate font-medium text-slate-700">{platformLabel(platform)}</span>
                    <span className="min-w-[2ch] text-right tabular-nums text-slate-500">{count}</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100">
                    <div
                      className="h-2 rounded-full bg-slate-900"
                      style={{ width: `${maxPlatformCount > 0 ? (count / maxPlatformCount) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">Content mix</h3>
              <div className="mt-4 grid grid-cols-3 gap-3">
                {typeEntries.map(([type, count]) => (
                  <div key={type} className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-center">
                    <p className="text-xs uppercase tracking-wide text-slate-500">{type}</p>
                    <p className="mt-2 text-xl font-semibold text-slate-950">{count}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-500">Audience totals</h3>
              <div className="mt-4 grid grid-cols-2 gap-3">
                {audienceMetrics.length === 0 ? (
                  <div className="col-span-2 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
                    Audience totals are not available for the connected accounts in this workspace yet.
                  </div>
                ) : audienceMetrics.map(([label, value]) => (
                  <div key={label} className="rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
                    <p className="mt-2 flex items-center gap-2 text-xl font-semibold text-slate-950">
                      <FaChartBar className="text-slate-400" />
                      {compactNumber(value)}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
          </>
        )}
      </CardContent>
    </Card>
  );
};

export default PerformanceSnapshot7d;
