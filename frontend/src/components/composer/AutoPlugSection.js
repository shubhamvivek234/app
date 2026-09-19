import React, { useState } from 'react';
import { FaRocket, FaHeart, FaCommentDots, FaChevronDown, FaChevronUp, FaMagic } from 'react-icons/fa';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

const THRESHOLD_PRESETS = [25, 50, 100, 250];

const SAMPLE_TEMPLATES = [
  "Enjoyed this? I write a weekly breakdown on building products here: https://unravler.com",
  "If this was helpful, repost it to help others and subscribe to our free newsletter: https://unravler.com",
  "Want more frameworks like this? Grab our free guide: https://unravler.com",
];

export default function AutoPlugSection({
  autoPlug = { enabled: false, trigger_metric: 'likes', threshold: 50, content: '' },
  onChangeAutoPlug,
}) {
  const [isOpen, setIsOpen] = useState(autoPlug?.enabled || false);

  const enabled = Boolean(autoPlug?.enabled);
  const threshold = autoPlug?.threshold || 50;
  const content = autoPlug?.content || '';

  const handleToggle = (checked) => {
    onChangeAutoPlug({
      ...autoPlug,
      enabled: checked,
      threshold: threshold || 50,
      trigger_metric: 'likes',
    });
    if (checked && !isOpen) setIsOpen(true);
  };

  const handleSelectThreshold = (value) => {
    onChangeAutoPlug({
      ...autoPlug,
      threshold: value,
    });
  };

  const handleContentChange = (text) => {
    onChangeAutoPlug({
      ...autoPlug,
      content: text,
    });
  };

  const handleInsertTemplate = (template) => {
    handleContentChange(template);
  };

  return (
    <div className="rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900/60 overflow-hidden shadow-xs transition-all">
      {/* Header bar */}
      <div className="p-3.5 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-xl bg-purple-100 dark:bg-purple-950/70 text-purple-600 dark:text-purple-400 flex items-center justify-center text-sm shadow-xs">
            <FaRocket className="text-xs" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-bold text-gray-900 dark:text-slate-100">
                Viral Auto-Plug
              </h4>
              <span className="text-[10px] font-semibold text-purple-600 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/50 px-1.5 py-0.5 rounded-full border border-purple-200 dark:border-purple-800">
                Auto-Reply
              </span>
            </div>
            <p className="text-[11px] text-gray-500 dark:text-slate-400">
              Auto-drop a comment with your link when this post hits high engagement.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Switch
            checked={enabled}
            onCheckedChange={handleToggle}
            className="data-[state=checked]:bg-purple-600"
          />
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-slate-300 p-1 transition-colors"
          >
            {isOpen ? <FaChevronUp className="text-xs" /> : <FaChevronDown className="text-xs" />}
          </button>
        </div>
      </div>

      {/* Expanded settings */}
      {isOpen && (
        <div className="px-3.5 pb-4 pt-1 space-y-3.5 border-t border-slate-100 dark:border-slate-800 text-xs bg-slate-50/40 dark:bg-slate-900/20">
          <div className="space-y-1.5 pt-2">
            <label className="text-[11px] font-semibold text-gray-700 dark:text-slate-300 flex items-center justify-between">
              <span className="flex items-center gap-1">
                <FaHeart className="text-rose-500 text-[10px]" />
                Trigger Threshold
              </span>
              <span className="text-[11px] text-purple-600 dark:text-purple-400 font-mono font-bold">
                {threshold} Likes
              </span>
            </label>

            {/* Threshold buttons */}
            <div className="flex items-center gap-1.5">
              {THRESHOLD_PRESETS.map((val) => {
                const active = threshold === val;
                return (
                  <button
                    key={val}
                    type="button"
                    onClick={() => handleSelectThreshold(val)}
                    className={`flex-1 py-1 px-2 rounded-xl text-xs font-semibold transition-all border ${
                      active
                        ? 'bg-purple-600 text-white border-purple-600 shadow-xs'
                        : 'bg-white dark:bg-slate-800 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700 hover:bg-gray-100 dark:hover:bg-slate-700'
                    }`}
                  >
                    {val} Likes
                  </button>
                );
              })}
            </div>
          </div>

          {/* Plug comment text */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-semibold text-gray-700 dark:text-slate-300 flex items-center gap-1">
                <FaCommentDots className="text-indigo-500 text-[10px]" />
                Auto-Reply Content
              </label>
              <span className={`text-[10px] font-mono ${content.length > 280 ? 'text-amber-500 font-bold' : 'text-gray-400'}`}>
                {content.length} / 500
              </span>
            </div>

            <Textarea
              rows={3}
              value={content}
              onChange={(e) => handleContentChange(e.target.value)}
              placeholder="e.g. Loved this breakdown? Join 10k+ founders on my newsletter: https://..."
              className="text-xs rounded-xl border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 resize-none focus:ring-purple-500"
            />
          </div>

          {/* Quick template snippets */}
          <div className="space-y-1">
            <span className="text-[10px] font-medium text-gray-400 flex items-center gap-1">
              <FaMagic className="text-[9px] text-purple-400" />
              Quick Templates
            </span>
            <div className="flex flex-col gap-1">
              {SAMPLE_TEMPLATES.map((tmpl, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => handleInsertTemplate(tmpl)}
                  className="text-left text-[11px] text-gray-600 dark:text-slate-400 hover:text-purple-600 dark:hover:text-purple-300 truncate bg-white/70 dark:bg-slate-800/60 hover:bg-purple-50/50 p-1.5 rounded-lg border border-slate-100 dark:border-slate-800 transition-colors"
                >
                  "{tmpl}"
                </button>
              ))}
            </div>
          </div>

          {/* Educational Callout */}
          <div className="text-[11px] text-purple-900 dark:text-purple-200 bg-purple-50 dark:bg-purple-950/40 border border-purple-200/70 dark:border-purple-900/50 rounded-xl p-2.5 leading-relaxed">
            💡 <strong>Why use Auto-Plug?</strong> Social algorithms (especially on X and LinkedIn) suppress reach when external links are in the main post. Auto-plug keeps the original post clean for maximum viral distribution, then automatically posts your conversion link once high traffic is guaranteed!
          </div>
        </div>
      )}
    </div>
  );
}
