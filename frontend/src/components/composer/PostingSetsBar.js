import React, { useState, useEffect } from 'react';
import { FaBookmark, FaPlus, FaCheck, FaTrash, FaEllipsisH, FaLayerGroup } from 'react-icons/fa';
import { toast } from 'sonner';
import { getPostingSets, createPostingSet, deletePostingSet, updatePostingSet } from '@/lib/api';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const COLOR_MAP = {
  indigo: 'bg-indigo-500 text-white border-indigo-600',
  blue: 'bg-blue-500 text-white border-blue-600',
  emerald: 'bg-emerald-500 text-white border-emerald-600',
  purple: 'bg-purple-500 text-white border-purple-600',
  amber: 'bg-amber-500 text-white border-amber-600',
  rose: 'bg-rose-500 text-white border-rose-600',
};

const DOT_COLOR_MAP = {
  indigo: 'bg-indigo-500',
  blue: 'bg-blue-500',
  emerald: 'bg-emerald-500',
  purple: 'bg-purple-500',
  amber: 'bg-amber-500',
  rose: 'bg-rose-500',
};

export default function PostingSetsBar({
  accounts = [],
  selectedAccounts = [],
  onSelectAccounts,
}) {
  const [sets, setSets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [setName, setSetName] = useState('');
  const [setColor, setSetColor] = useState('indigo');
  const [saving, setSaving] = useState(false);
  const [activeMenuId, setActiveMenuId] = useState(null);

  const fetchSets = async () => {
    try {
      setLoading(true);
      const data = await getPostingSets();
      setSets(Array.isArray(data) ? data : []);
    } catch (err) {
      // Silently handle if not supported or network blip
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSets();
  }, []);

  const handleSaveSet = async (e) => {
    e?.preventDefault();
    if (!setName.trim()) {
      toast.error('Please enter a set name');
      return;
    }
    if (selectedAccounts.length === 0) {
      toast.error('Select at least one account to save into this set');
      return;
    }
    try {
      setSaving(true);
      const newSet = await createPostingSet({
        name: setName.trim(),
        account_ids: selectedAccounts,
        color: setColor,
      });
      setSets((prev) => [...prev, newSet]);
      toast.success(`Posting Set "${newSet.name}" saved!`);
      setSetName('');
      setModalOpen(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to save posting set');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSet = async (setId, e) => {
    e?.stopPropagation();
    try {
      await deletePostingSet(setId);
      setSets((prev) => prev.filter((s) => s.id !== setId));
      toast.success('Posting set deleted');
      setActiveMenuId(null);
    } catch (err) {
      toast.error('Failed to delete posting set');
    }
  };

  const isAllSelected = accounts.length > 0 && selectedAccounts.length === accounts.length;

  const handleSelectAll = () => {
    if (isAllSelected) {
      onSelectAccounts([]);
    } else {
      onSelectAccounts(accounts.map((a) => a.id));
    }
  };

  const handleSelectSet = (set) => {
    // Only select accounts that exist in current connected accounts
    const existingIds = new Set(accounts.map((a) => a.id));
    const matchingIds = set.account_ids.filter((id) => existingIds.has(id));
    if (matchingIds.length === 0) {
      toast.error('None of the accounts in this set are currently connected');
      return;
    }
    onSelectAccounts(matchingIds);
  };

  const isSetSelected = (set) => {
    if (selectedAccounts.length === 0) return false;
    const setIds = new Set(set.account_ids);
    if (setIds.size !== selectedAccounts.length) return false;
    return selectedAccounts.every((id) => setIds.has(id));
  };

  if (accounts.length < 2) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 pt-1 pb-2 border-b border-gray-100 dark:border-slate-800 text-xs">
      <div className="flex items-center gap-1 text-[11px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider pr-1">
        <FaLayerGroup className="text-[10px]" />
        <span>Sets</span>
      </div>

      {/* Select All pill */}
      <button
        type="button"
        onClick={handleSelectAll}
        className={`px-2.5 py-1 rounded-full font-medium transition-all duration-150 border ${
          isAllSelected
            ? 'bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900 dark:border-white shadow-xs'
            : 'bg-gray-50 dark:bg-slate-800/80 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700 hover:bg-gray-100 dark:hover:bg-slate-700'
        }`}
      >
        All ({accounts.length})
      </button>

      {/* Saved sets pills */}
      {sets.map((set) => {
        const selected = isSetSelected(set);
        const dotColor = DOT_COLOR_MAP[set.color] || DOT_COLOR_MAP.indigo;

        return (
          <div key={set.id} className="relative group/pill flex items-center">
            <button
              type="button"
              onClick={() => handleSelectSet(set)}
              className={`flex items-center gap-1.5 pl-2.5 pr-2 py-1 rounded-full font-medium transition-all duration-150 border ${
                selected
                  ? 'bg-indigo-50 border-indigo-300 text-indigo-700 dark:bg-indigo-950/50 dark:border-indigo-600 dark:text-indigo-200 shadow-xs ring-1 ring-indigo-400/30'
                  : 'bg-gray-50 dark:bg-slate-800/80 text-gray-600 dark:text-slate-300 border-gray-200 dark:border-slate-700 hover:border-gray-300 dark:hover:border-slate-600'
              }`}
              title={`${set.name} (${set.account_ids.length} accounts)`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
              <span className="truncate max-w-[120px]">{set.name}</span>
              <span className="text-[10px] text-gray-400 dark:text-gray-500 font-mono">
                {set.account_ids.length}
              </span>
            </button>

            {/* Quick delete / menu icon */}
            <button
              type="button"
              onClick={(e) => handleDeleteSet(set.id, e)}
              className="opacity-0 group-hover/pill:opacity-100 ml-0.5 p-1 text-gray-400 hover:text-red-500 transition-opacity"
              title="Delete set"
            >
              <FaTrash className="text-[9px]" />
            </button>
          </div>
        );
      })}

      {/* Save current selection as set */}
      {selectedAccounts.length > 1 && (
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="flex items-center gap-1 px-2.5 py-1 rounded-full font-medium text-blue-600 dark:text-blue-400 bg-blue-50/70 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900/60 hover:bg-blue-100/70 transition-colors"
          title="Save the currently selected accounts as a quick-select set"
        >
          <FaBookmark className="text-[9px]" />
          <span>Save as Set</span>
        </button>
      )}

      {/* Modal: Save Posting Set */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-md bg-white dark:bg-slate-900 text-gray-900 dark:text-gray-100 rounded-2xl p-5 border border-slate-200 dark:border-slate-800">
          <DialogHeader>
            <DialogTitle className="text-base font-bold flex items-center gap-2">
              <FaBookmark className="text-blue-500" /> Save as Posting Set
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2 text-sm">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Create a 1-click preset for these <strong>{selectedAccounts.length}</strong> selected accounts.
            </p>
            <div>
              <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 block mb-1">
                Set Name
              </label>
              <Input
                placeholder="e.g. Personal Brand, Tech Outlets, B2B Channels"
                value={setName}
                onChange={(e) => setSetName(e.target.value)}
                autoFocus
                className="h-9 rounded-xl text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 dark:text-gray-300 block mb-1">
                Color Tag
              </label>
              <div className="flex gap-2 pt-1">
                {Object.keys(DOT_COLOR_MAP).map((colorKey) => (
                  <button
                    key={colorKey}
                    type="button"
                    onClick={() => setSetColor(colorKey)}
                    className={`w-6 h-6 rounded-full ${DOT_COLOR_MAP[colorKey]} flex items-center justify-center transition-transform ${
                      setColor === colorKey ? 'ring-2 ring-offset-2 ring-black dark:ring-white scale-110' : 'opacity-80 hover:opacity-100'
                    }`}
                  >
                    {setColor === colorKey && <FaCheck className="text-white text-[10px]" />}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter className="gap-2 pt-2">
            <Button variant="ghost" size="sm" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSaveSet} disabled={saving || !setName.trim()}>
              {saving ? 'Saving...' : 'Save Set'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
