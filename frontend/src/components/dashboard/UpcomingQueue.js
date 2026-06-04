import React from 'react';
import { FaArrowRight, FaCalendarAlt, FaClock } from 'react-icons/fa';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

import {
  countdownLabel,
  formatAbsoluteDate,
  platformLabel,
  platformPillClass,
  primaryPostTitle,
  primaryThumbnail,
} from './helpers';

const UpcomingQueue = ({ posts = [], onNavigate }) => {
  return (
    <Card className="border-slate-200 bg-white shadow-sm">
      <CardHeader className="border-b border-slate-100 pb-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Upcoming Queue</p>
            <CardTitle className="mt-2 text-xl text-slate-950">What is going out next</CardTitle>
          </div>
          <Button variant="outline" size="sm" className="border-slate-300 bg-white" onClick={() => onNavigate?.('/calendar')}>
            Open Calendar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-6">
        {posts.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm">
              <FaCalendarAlt />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900">No scheduled posts yet</h3>
            <p className="mt-2 text-sm text-slate-600">The queue is empty. Add a scheduled post to start filling the upcoming calendar.</p>
            <Button className="mt-4" onClick={() => onNavigate?.('/create-post')}>
              Schedule a Post
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {posts.map((post) => {
              const thumbnail = primaryThumbnail(post);
              return (
                <button
                  key={post.id}
                  type="button"
                  onClick={() => onNavigate?.('/calendar')}
                  className="flex w-full items-start gap-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-left transition-colors hover:border-slate-300 hover:bg-white"
                >
                  <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-slate-200">
                    {thumbnail ? (
                      <img src={thumbnail} alt="" className="h-full w-full object-cover" />
                    ) : (
                      <FaCalendarAlt className="text-slate-500" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {(post.platforms || []).map((platform) => (
                        <span key={`${post.id}-${platform}`} className={cn('inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold', platformPillClass(platform))}>
                          {platformLabel(platform)}
                        </span>
                      ))}
                      {post.post_type ? (
                        <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600">
                          {post.post_type}
                        </span>
                      ) : null}
                    </div>
                    <h3 className="mt-3 text-base font-semibold text-slate-900">{primaryPostTitle(post)}</h3>
                    <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-slate-600">
                      <span className="inline-flex items-center gap-2">
                        <FaClock className="text-slate-400" />
                        {countdownLabel(post.scheduled_time)}
                      </span>
                      <span>{formatAbsoluteDate(post.scheduled_time)}</span>
                      {post.account_labels?.length ? (
                        <span>{post.account_labels.slice(0, 2).join(', ')}{post.account_labels.length > 2 ? ` +${post.account_labels.length - 2}` : ''}</span>
                      ) : null}
                    </div>
                  </div>
                  <FaArrowRight className="mt-1 shrink-0 text-slate-400" />
                </button>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default UpcomingQueue;
