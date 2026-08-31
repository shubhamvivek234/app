import React from 'react';
import { format } from 'date-fns';
import { FaLayerGroup, FaRegClock } from 'react-icons/fa';

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

import CalendarNotesSection from './CalendarNotesSection';
import CalendarPostChip from './CalendarPostChip';
import {
  formatScheduledDateTime,
  getPostScheduledTimeZone,
  getAccountLabel,
  getPostMediaMeta,
  getPostPlatforms,
  PLATFORM_LABELS,
} from './calendarHelpers';

const DayAgendaPanel = ({
  day,
  open,
  posts = [],
  notes = [],
  getPostDisplayAccounts,
  noteText,
  noteColor,
  onNoteTextChange,
  onNoteColorChange,
  onAddNote,
  onDeleteNote,
  savingNote,
  onClose,
}) => (
  <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose?.(); }}>
    <DialogContent motionPreset="centered" className="max-w-5xl overflow-hidden border-slate-200 p-0 sm:rounded-[28px] dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-slate-100 bg-slate-50/70 px-5 py-5 sm:px-6 dark:border-slate-800 dark:bg-slate-900/80">
        <DialogHeader className="space-y-0 text-left">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
            <div>
              <span className="inline-flex rounded-full bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300">
                Day agenda
              </span>
              <DialogTitle className="mt-3 text-2xl font-semibold tracking-tight text-slate-950 dark:text-slate-100">
                {day ? format(day, 'EEEE, MMMM d, yyyy') : 'Day details'}
              </DialogTitle>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
                Review the queue, add context, and keep the schedule aligned before publish time.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left shadow-sm dark:border-slate-800 dark:bg-slate-800/60">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">In this day</div>
              <div className="mt-2 text-lg font-semibold text-slate-900 dark:text-slate-100">{posts.length} post{posts.length === 1 ? '' : 's'}</div>
              <div className="text-sm text-slate-500 dark:text-slate-400">{notes.length} note{notes.length === 1 ? '' : 's'}</div>
            </div>
          </div>
        </DialogHeader>
      </div>

      <div className="grid max-h-[78vh] gap-0 overflow-hidden lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <div className="overflow-y-auto px-5 py-5 sm:px-6 sm:py-6">
          {posts.length > 0 ? (
            <div className="space-y-5">
              {posts.map((post) => {
                const postAccounts = getPostDisplayAccounts(post);
                const platformLabels = getPostPlatforms(post).map((platform) => PLATFORM_LABELS[platform] || platform);
                const media = getPostMediaMeta(post);
                const scheduledTimeZone = getPostScheduledTimeZone(post);

                return (
                  <div key={post.id} className="rounded-[28px] border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-800 dark:bg-slate-800/40">
                    <CalendarPostChip post={post} accounts={postAccounts} compact={false} expandedVariant="agenda" onClick={() => {}} />
                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-left text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <div className="flex items-start gap-2">
                          <FaRegClock className="mt-0.5 text-slate-400 dark:text-slate-500" />
                          <div>
                            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">Scheduled</div>
                            <div className="mt-1 text-slate-900 dark:text-slate-100">{formatScheduledDateTime(post?.scheduled_time, scheduledTimeZone, { includeTimeZone: true })}</div>
                          </div>
                        </div>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-left text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <div className="flex items-start gap-2">
                          <FaLayerGroup className="mt-0.5 text-slate-400 dark:text-slate-500" />
                          <div>
                            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">Media</div>
                            <div className="mt-1 text-slate-900 dark:text-slate-100">{media.label}</div>
                          </div>
                        </div>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-left text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">Accounts</div>
                        <div className="mt-1 text-slate-900 dark:text-slate-100">
                          {postAccounts.length > 0
                            ? postAccounts.map((account) => getAccountLabel(account)).join(', ')
                            : 'No account info'}
                        </div>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-left text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">Platforms</div>
                        <div className="mt-1 text-slate-900 dark:text-slate-100">
                          {platformLabels.length > 0 ? platformLabels.join(', ') : 'No platform info'}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center dark:border-slate-700 dark:bg-slate-800/40">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">No scheduled posts for this day</h3>
              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-400">
                Use the notes panel to keep reminders here, or add a post from the composer when this slot becomes active.
              </p>
            </div>
          )}
        </div>

        <div className="border-t border-slate-100 bg-slate-50/70 px-5 py-5 lg:border-l lg:border-t-0 lg:px-6 lg:py-6 dark:border-slate-800 dark:bg-slate-900/60">
          <CalendarNotesSection
            notes={notes}
            noteText={noteText}
            noteColor={noteColor}
            onNoteTextChange={onNoteTextChange}
            onNoteColorChange={onNoteColorChange}
            onAddNote={onAddNote}
            onDeleteNote={onDeleteNote}
            savingNote={savingNote}
          />
        </div>
      </div>
    </DialogContent>
  </Dialog>
);

export default DayAgendaPanel;
