import React, { useState, useEffect } from 'react';
import { getBrandVoice, saveBrandVoice } from '@/lib/api';
import { toast } from 'sonner';
import { FaRobot, FaSave, FaPlus, FaTimes, FaLightbulb } from 'react-icons/fa';

export default function BrandVoiceSettings() {
  const [brandName, setBrandName] = useState('');
  const [tone, setTone] = useState('');
  const [targetAudience, setTargetAudience] = useState('');
  const [mission, setMission] = useState('');
  const [formattingRules, setFormattingRules] = useState('');
  const [customGuidelines, setCustomGuidelines] = useState('');
  const [bannedWords, setBannedWords] = useState([]);
  const [newBannedWord, setNewBannedWord] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const fetchVoice = async () => {
      try {
        setLoading(true);
        const data = await getBrandVoice();
        if (data) {
          setBrandName(data.brand_name || '');
          setTone(data.tone || '');
          setTargetAudience(data.target_audience || '');
          setMission(data.mission || '');
          setFormattingRules(data.formatting_rules || '');
          setCustomGuidelines(data.custom_guidelines || '');
          setBannedWords(data.banned_words || []);
        }
      } catch (err) {
        toast.error('Failed to load Brand Voice');
      } finally {
        setLoading(false);
      }
    };
    fetchVoice();
  }, []);

  const handleAddBannedWord = (e) => {
    e.preventDefault();
    const word = newBannedWord.trim();
    if (!word) return;
    if (bannedWords.includes(word)) {
      toast.info('Word already in banned list');
      return;
    }
    setBannedWords([...bannedWords, word]);
    setNewBannedWord('');
  };

  const handleRemoveBannedWord = (word) => {
    setBannedWords(bannedWords.filter((w) => w !== word));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await saveBrandVoice({
        brand_name: brandName,
        tone: tone || undefined,
        target_audience: targetAudience || undefined,
        mission: mission || undefined,
        formatting_rules: formattingRules || undefined,
        custom_guidelines: customGuidelines || undefined,
        banned_words: bannedWords,
      });
      toast.success('Brand Voice & AI Persona guidelines saved!');
    } catch (err) {
      toast.error('Failed to save brand voice');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-8 text-center text-gray-400 text-sm">Loading Brand Voice guidelines...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <FaRobot className="text-indigo-600" /> Brand Voice &amp; AI Persona Vault
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Define your company personality, prohibited words, and styling rules. All AI captions and RSS rewrites will automatically match this voice.
          </p>
        </div>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
              Brand / Company Name
            </label>
            <input
              type="text"
              placeholder="e.g. Unravler Cloud"
              value={brandName}
              onChange={(e) => setBrandName(e.target.value)}
              className="w-full px-3.5 py-2 text-xs border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
              Default Tone of Voice
            </label>
            <input
              type="text"
              placeholder="e.g. Authoritative yet witty, concise, friendly"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="w-full px-3.5 py-2 text-xs border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
              Target Audience
            </label>
            <input
              type="text"
              placeholder="e.g. Tech founders, social media marketers, Gen-Z creators"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              className="w-full px-3.5 py-2 text-xs border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
              Company Mission / Value Proposition
            </label>
            <input
              type="text"
              placeholder="e.g. Helping digital agencies scale social media publishing effortlessly"
              value={mission}
              onChange={(e) => setMission(e.target.value)}
              className="w-full px-3.5 py-2 text-xs border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Formatting Rules */}
        <div>
          <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
            Formatting &amp; Post Structure Rules
          </label>
          <textarea
            rows={2}
            placeholder="e.g. Always use 1-2 line breaks between points. Never use more than 2 emojis. End with an engaging question."
            value={formattingRules}
            onChange={(e) => setFormattingRules(e.target.value)}
            className="w-full px-3.5 py-2 text-xs border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* Banned Words / Jargon */}
        <div>
          <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
            Banned Words &amp; Jargon (AI will never use these)
          </label>
          <div className="flex items-center gap-2 mb-2">
            <input
              type="text"
              placeholder="Add word or phrase (e.g. synergy, cheap)..."
              value={newBannedWord}
              onChange={(e) => setNewBannedWord(e.target.value)}
              className="flex-1 px-3 py-1.5 text-xs border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="button"
              onClick={handleAddBannedWord}
              className="px-3.5 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-800 text-xs font-bold rounded-xl flex items-center gap-1"
            >
              <FaPlus className="text-[10px]" /> Add
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {bannedWords.map((word) => (
              <span
                key={word}
                className="inline-flex items-center gap-1.5 text-xs bg-rose-50 border border-rose-100 text-rose-700 px-2.5 py-1 rounded-lg"
              >
                {word}
                <button
                  type="button"
                  onClick={() => handleRemoveBannedWord(word)}
                  className="text-rose-400 hover:text-rose-700 p-0.5"
                >
                  <FaTimes className="text-[9px]" />
                </button>
              </span>
            ))}
            {bannedWords.length === 0 && (
              <span className="text-xs text-gray-400">No banned words added yet.</span>
            )}
          </div>
        </div>

        <div className="pt-3 border-t border-gray-100 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl shadow-xs transition-all active:scale-95 flex items-center gap-2 disabled:opacity-50"
          >
            <FaSave /> {saving ? 'Saving...' : 'Save Brand Guidelines'}
          </button>
        </div>
      </form>
    </div>
  );
}
