import React from 'react';
import { FaRegStickyNote, FaTimes } from 'react-icons/fa';

import { cn } from '@/lib/utils';

import { NOTE_COLORS, noteColorClasses } from './calendarHelpers';

const NoteComposer = ({
  noteText,
  noteColor,
  onNoteTextChange,
  onNoteColorChange,
  onAddNote,
  savingNote,
  compact = false,
}) => (
  <div className={cn('space-y-3', compact ? 'rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-3' : 'rounded-3xl border border-slate-200 bg-white p-4')}>
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Add note</p>
      <textarea
        rows={compact ? 2 : 3}
        placeholder="Add a reminder, approval note, or client context for this day…"
        value={noteText}
        onChange={(e) => onNoteTextChange?.(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) onAddNote?.();
        }}
        className="mt-3 w-full resize-none rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition-colors placeholder:text-slate-400 focus:border-emerald-300 focus:ring-2 focus:ring-emerald-200"
      />
    </div>

    <div className="flex items-center gap-2">
      <div className="flex items-center gap-2">
        {NOTE_COLORS.map((color) => (
          <button
            key={color}
            type="button"
            onClick={() => onNoteColorChange?.(color)}
            className={cn(
              'h-5 w-5 rounded-full transition-transform',
              noteColorClasses[color].dot,
              noteColor === color ? 'scale-125 ring-2 ring-slate-400 ring-offset-2' : 'opacity-70',
            )}
            title={color}
          />
        ))}
      </div>
      <button
        type="button"
        onClick={onAddNote}
        disabled={!noteText.trim() || savingNote}
        className="ml-auto rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-600 disabled:opacity-40"
      >
        {savingNote ? 'Saving…' : 'Add Note'}
      </button>
    </div>
  </div>
);

const CalendarNotesSection = ({
  notes = [],
  compact = false,
  onDeleteNote,
  noteText,
  noteColor,
  onNoteTextChange,
  onNoteColorChange,
  onAddNote,
  savingNote = false,
}) => {
  const getNoteText = (note) => String(note?.text || note?.note || '').trim();

  if (compact) {
    if (notes.length === 0) {
      return null;
    }

    return (
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[10px] font-semibold text-emerald-700">
          <FaRegStickyNote className="text-[9px]" />
          {notes.length} note{notes.length > 1 ? 's' : ''}
        </span>
        {notes.slice(0, 2).map((note) => (
          <span
            key={note.id}
            className={cn(
              'max-w-[100px] truncate rounded-full px-2 py-1 text-[10px] font-medium',
              noteColorClasses[note.color]?.chip || noteColorClasses.green.chip,
            )}
            title={getNoteText(note)}
          >
            {getNoteText(note)}
          </span>
        ))}
        {notes.length > 2 ? (
          <span className="text-[10px] font-medium text-slate-500">+{notes.length - 2} more</span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
          <FaRegStickyNote className="text-sm" />
        </div>
        <div>
          <p className="text-sm font-semibold text-slate-900">Notes for this day</p>
          <p className="text-xs text-slate-500">Keep reminders and context close to the queue.</p>
        </div>
      </div>

      {notes.length > 0 ? (
        <div className="space-y-2">
          {notes.map((note) => (
            <div
              key={note.id}
              className={cn(
                'flex items-start justify-between gap-3 rounded-2xl border px-3 py-3 text-sm',
                noteColorClasses[note.color]?.form || noteColorClasses.green.form,
                noteColorClasses[note.color]?.border || noteColorClasses.green.border,
              )}
            >
              <span className="flex-1 leading-relaxed">{getNoteText(note)}</span>
              {onDeleteNote ? (
                <button
                  type="button"
                  onClick={(e) => onDeleteNote(note.id, e)}
                  className="mt-0.5 shrink-0 opacity-60 transition-opacity hover:opacity-100"
                  title="Delete note"
                >
                  <FaTimes className="text-xs" />
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
          No notes for this day yet.
        </div>
      )}

      {onAddNote ? (
        <NoteComposer
          compact={false}
          noteText={noteText}
          noteColor={noteColor}
          onNoteTextChange={onNoteTextChange}
          onNoteColorChange={onNoteColorChange}
          onAddNote={onAddNote}
          savingNote={savingNote}
        />
      ) : null}
    </div>
  );
};

export default CalendarNotesSection;
