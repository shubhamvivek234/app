import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaCalendarAlt, FaPlus, FaRedo, FaSignal, FaSyncAlt } from 'react-icons/fa';
import { toast } from 'sonner';

import DashboardLayout from '@/components/DashboardLayout';
import BrandMarkLoader from '@/components/BrandMarkLoader';
import ActionCenter from '@/components/dashboard/ActionCenter';
import WorkspacePulse from '@/components/dashboard/WorkspacePulse';
import UpcomingQueue from '@/components/dashboard/UpcomingQueue';
import AccountHealthPanel from '@/components/dashboard/AccountHealthPanel';
import PerformanceSnapshot7d from '@/components/dashboard/PerformanceSnapshot7d';
import RecentActivity from '@/components/dashboard/RecentActivity';
import RecentWins from '@/components/dashboard/RecentWins';
import { Button } from '@/components/ui/button';
import { getDashboardOverview } from '@/lib/api';
import { usePostStatusStream } from '@/hooks/usePostStatusStream';
import { useAuth } from '@/context/AuthContext';
import { formatRelativeDate } from '@/components/dashboard/helpers';

const DASHBOARD_WINDOW_DAYS = 7;
const CORE_SECTIONS = ['core', 'queue', 'wins', 'activity'];
const SECONDARY_SECTIONS = ['health', 'performance'];
const DASHBOARD_SECTION_FIELDS = {
  core: ['summary', 'operations', 'action_items', 'refreshed_at'],
  queue: ['upcoming_posts'],
  wins: ['recent_published'],
  activity: ['activity'],
  health: ['account_health'],
  performance: ['performance_7d'],
};
const STREAM_REFRESH_STATUSES = new Set(['queued', 'scheduled', 'processing', 'published', 'failed', 'partial', 'cancelled']);

const mergeDashboardPayload = (previous, next) => {
  const merged = { ...(previous || {}) };
  const sectionsReturned = Object.prototype.hasOwnProperty.call(next || {}, 'sections_returned')
    ? (Array.isArray(next?.sections_returned) ? next.sections_returned : [])
    : Object.keys(DASHBOARD_SECTION_FIELDS);

  sectionsReturned.forEach((section) => {
    (DASHBOARD_SECTION_FIELDS[section] || []).forEach((field) => {
      if (Object.prototype.hasOwnProperty.call(next, field)) {
        merged[field] = next[field];
      }
    });
  });

  if (Object.prototype.hasOwnProperty.call(next || {}, 'refreshed_at')) {
    merged.refreshed_at = next.refreshed_at;
  }

  merged.sections_returned = Array.from(
    new Set([...(previous?.sections_returned || []), ...sectionsReturned])
  );

  const nextSectionErrors = next?.section_errors || {};
  const clearedErrors = { ...(previous?.section_errors || {}), ...nextSectionErrors };
  sectionsReturned.forEach((section) => {
    delete clearedErrors[section];
  });
  if (Object.keys(clearedErrors).length > 0) {
    merged.section_errors = clearedErrors;
  } else {
    delete merged.section_errors;
  }

  return merged;
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [panelLoading, setPanelLoading] = useState({
    health: true,
    performance: true,
  });
  const [relativeTimeTick, setRelativeTimeTick] = useState(() => Date.now());
  const refreshTimerRef = useRef(null);
  const deferredPanelLoadRef = useRef(null);

  const loadDashboardSections = useCallback(async (sections, { refresh = false, silent = false } = {}) => {
    try {
      const data = await getDashboardOverview({ days: DASHBOARD_WINDOW_DAYS, refresh, sections });
      setDashboard((previous) => mergeDashboardPayload(previous, data));
      return data;
    } catch (error) {
      if (!silent) {
        toast.error('Failed to load dashboard overview');
      }
      throw error;
    }
  }, []);

  const loadDeferredPanels = useCallback(async ({ refresh = false, silent = true } = {}) => {
    setPanelLoading({
      health: true,
      performance: true,
    });
    try {
      await loadDashboardSections(SECONDARY_SECTIONS, { refresh, silent });
    } finally {
      setPanelLoading({
        health: false,
        performance: false,
      });
    }
  }, [loadDashboardSections]);

  useEffect(() => {
    let cancelled = false;

    const runInitialLoad = async () => {
      setLoading(true);
      try {
        await loadDashboardSections(CORE_SECTIONS, { refresh: false });
        if (cancelled) return;
        setLoading(false);
        deferredPanelLoadRef.current = setTimeout(() => {
          void loadDeferredPanels({ refresh: false, silent: true });
        }, 0);
      } catch (_error) {
        if (cancelled) return;
        setLoading(false);
      }
    };

    void runInitialLoad();
    return () => {
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current);
      }
      if (deferredPanelLoadRef.current) {
        clearTimeout(deferredPanelLoadRef.current);
      }
      cancelled = true;
    };
  }, [loadDashboardSections, loadDeferredPanels]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setRelativeTimeTick(Date.now());
    }, 30000);
    return () => clearInterval(intervalId);
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await loadDashboardSections(CORE_SECTIONS, { refresh: true });
      await loadDeferredPanels({ refresh: true, silent: true });
    } finally {
      setRefreshing(false);
    }
  }, [loadDashboardSections, loadDeferredPanels]);

  const scheduleBackgroundRefresh = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
    }
    refreshTimerRef.current = setTimeout(() => {
      void loadDashboardSections(['core', 'queue', 'wins'], { refresh: false, silent: true });
    }, 1200);
  }, [loadDashboardSections]);

  const handlePostUpdate = useCallback((update) => {
    const postId = update?.post_id;
    const status = update?.status;

    if (!postId || !STREAM_REFRESH_STATUSES.has(status)) {
      return;
    }

    setDashboard((prev) => {
      if (!prev) return prev;
      const shouldPruneUpcoming = ['published', 'failed', 'partial', 'cancelled'].includes(status);
      if (!shouldPruneUpcoming) return prev;
      const upcomingPosts = prev.upcoming_posts || [];
      if (!upcomingPosts.some((post) => post.id === postId)) {
        return prev;
      }
      return {
        ...prev,
        upcoming_posts: upcomingPosts.filter((post) => post.id !== postId),
      };
    });

    scheduleBackgroundRefresh();
  }, [scheduleBackgroundRefresh]);

  usePostStatusStream(handlePostUpdate);

  const headerStats = useMemo(() => {
    if (!dashboard?.summary) return [];
    return [
      { label: 'Total posts', value: dashboard.summary.total_posts ?? 0 },
      { label: 'Needs attention', value: dashboard.action_items?.length ?? 0 },
      { label: 'Upcoming queue', value: dashboard.summary.scheduled_posts ?? 0 },
      { label: 'Connected accounts', value: dashboard.summary.connected_accounts ?? 0 },
    ];
  }, [dashboard]);

  const headlineName = user?.display_name || user?.email?.split('@')?.[0] || 'there';

  if (loading && !dashboard) {
    return (
      <DashboardLayout>
        <BrandMarkLoader overlay />
      </DashboardLayout>
    );
  }

  if (!dashboard) {
    return (
      <DashboardLayout>
        <div className="mx-auto max-w-3xl rounded-3xl border border-slate-200 bg-white p-10 shadow-sm">
          <h1 className="text-2xl font-semibold text-slate-950">Dashboard unavailable</h1>
          <p className="mt-3 text-slate-600">The control center could not be loaded right now. Retry the request and keep the rest of the workspace untouched.</p>
          <Button className="mt-6" onClick={handleRefresh}>
            <FaRedo className="mr-2" />
            Retry
          </Button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <section className="overflow-hidden rounded-[28px] border border-slate-800 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white shadow-xl">
          <div className="grid gap-8 px-6 py-7 lg:grid-cols-[1.2fr_0.8fr] lg:px-8">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-200">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  Dashboard
                </span>
                <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-slate-300">
                  <FaSignal className="text-emerald-400" />
                  Updated {formatRelativeDate(dashboard.refreshed_at, relativeTimeTick)}
                </span>
              </div>
              <h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">
                Operational view for {headlineName}
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300 sm:text-base">
                See what needs attention, what is going out next, which accounts are unhealthy, and how the workspace performed over the last {DASHBOARD_WINDOW_DAYS} days.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Button className="bg-white text-slate-950 hover:bg-slate-100" onClick={() => navigate('/create-post')} data-testid="create-post-button">
                  <FaPlus className="mr-2" />
                  Create Post
                </Button>
                <Button variant="outline" className="border-white/20 bg-white/5 text-white hover:bg-white/10" onClick={() => navigate('/calendar')}>
                  <FaCalendarAlt className="mr-2" />
                  Open Calendar
                </Button>
                <Button
                  variant="outline"
                  className="border-white/20 bg-white/5 text-white hover:bg-white/10"
                  onClick={handleRefresh}
                  disabled={refreshing}
                >
                  <FaSyncAlt className={`mr-2 ${refreshing ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 self-end">
              {headerStats.map((item) => (
                <div key={item.label} className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm">
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-300">{item.label}</p>
                  <p className="mt-3 text-3xl font-semibold text-white">{item.value}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="grid gap-8 xl:grid-cols-[1.35fr_0.85fr]">
          <ActionCenter actionItems={dashboard.action_items} onNavigate={navigate} />
          <WorkspacePulse summary={dashboard.summary} operations={dashboard.operations} />
        </div>

        <div className="grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
          <UpcomingQueue posts={dashboard.upcoming_posts} onNavigate={navigate} now={relativeTimeTick} />
          <AccountHealthPanel
            accounts={dashboard.account_health}
            loading={panelLoading.health}
            error={dashboard.section_errors?.health}
            onNavigate={navigate}
          />
        </div>

        <div className="grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
          <PerformanceSnapshot7d
            performance={dashboard.performance_7d}
            loading={panelLoading.performance}
            error={dashboard.section_errors?.performance}
            onNavigate={navigate}
          />
          <RecentActivity
            operations={dashboard.operations}
            activity={dashboard.activity}
            onNavigate={navigate}
            now={relativeTimeTick}
          />
        </div>

        <RecentWins posts={dashboard.recent_published} onNavigate={navigate} now={relativeTimeTick} />
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;
