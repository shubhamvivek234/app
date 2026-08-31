import React from 'react';
import { FaArrowRight, FaCheckCircle } from 'react-icons/fa';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

import {
  formatAbsoluteDate,
  formatRelativeDate,
  platformLabel,
  platformPillClass,
  primaryPostTitle,
  primaryThumbnail,
  secondaryPostPreview,
} from './helpers';

const RecentWins = ({ posts = [], onNavigate, now = Date.now() }) => {
  return (
    <Card className="flex h-full flex-col border-slate-200 bg-white shadow-sm lg:h-[520px] dark:border-slate-800 dark:bg-slate-900">
      <CardHeader className="border-b border-slate-100 pb-5 dark:border-slate-800">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Recent Wins</p>
            <CardTitle className="mt-2 text-xl text-slate-950 dark:text-slate-100">What just shipped successfully</CardTitle>
          </div>
          <Button variant="outline" size="sm" className="border-slate-300 bg-white dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700" onClick={() => onNavigate?.('/content-library')}>
            Open Content Library
          </Button>
        </div>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col pt-6">
        {posts.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center dark:border-slate-700 dark:bg-slate-800/40">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm dark:bg-slate-800 dark:text-slate-400">
              <FaCheckCircle />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900 dark:text-slate-100">No recent published posts yet</h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Once posts are published, they will show up here with timing and platform context.</p>
            <Button className="mt-4" onClick={() => onNavigate?.('/create-post')}>
              Create a Post
            </Button>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              {posts.map((post) => {
                const thumbnail = primaryThumbnail(post);
                return (
                  <button
                    key={post.id}
                    type="button"
                    onClick={() => onNavigate?.('/content-library')}
                    className="group rounded-3xl border border-slate-200 bg-slate-50/80 p-4 text-left transition-all hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white dark:border-slate-800 dark:bg-slate-800/60 dark:hover:border-slate-700 dark:hover:bg-slate-800"
                  >
                    <div className="aspect-[4/3] overflow-hidden rounded-2xl bg-slate-200 dark:bg-slate-700">
                      {thumbnail ? (
                        <img src={thumbnail} alt="" className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]" />
                      ) : (
                        <div className="flex h-full items-center justify-center text-slate-400 dark:text-slate-500">
                          <FaCheckCircle className="text-2xl" />
                        </div>
                      )}
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {(post.platforms || []).slice(0, 2).map((platform) => (
                        <span key={`${post.id}-${platform}`} className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold', platformPillClass(platform))}>
                          {platformLabel(platform)}
                        </span>
                      ))}
                      {post.platforms?.length > 2 ? (
                        <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                          +{post.platforms.length - 2}
                        </span>
                      ) : null}
                    </div>
                    <h3 className="mt-4 text-base font-semibold text-slate-900 dark:text-slate-100">{primaryPostTitle(post)}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">{secondaryPostPreview(post)}</p>
                    <div className="mt-4 flex items-center justify-between gap-3 text-xs text-slate-500 dark:text-slate-400">
                      <div>
                        <div>{formatRelativeDate(post.published_at, now)}</div>
                        <div className="mt-1">{formatAbsoluteDate(post.published_at)}</div>
                      </div>
                      <FaArrowRight className="text-slate-400 dark:text-slate-500" />
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default RecentWins;
