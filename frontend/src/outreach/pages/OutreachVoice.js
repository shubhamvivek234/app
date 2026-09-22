import React, { useState, useEffect, useRef } from 'react';
import {
  Mic,
  Square,
  Play,
  Pause,
  Trash2,
  CheckCircle2,
  Shield,
  Upload,
  Sparkles,
  Volume2,
  RefreshCw,
  AlertCircle,
  Users,
  ChevronDown,
  Check,
  RotateCcw,
} from 'lucide-react';

export default function OutreachVoice() {
  const [voices, setVoices] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [voiceName, setVoiceName] = useState('');
  const [isCloning, setIsCloning] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [activeTab, setActiveTab] = useState('record'); // 'record' | 'upload'
  const [activeAssignVoiceId, setActiveAssignVoiceId] = useState(null);

  // Audio preview modal
  const [previewVoice, setPreviewVoice] = useState(null);
  const [previewScript, setPreviewScript] = useState('Hey {{first_name}}, saw you are also leading growth at {{company_name}} and wanted to reach out!');
  const [leadFirstName, setLeadFirstName] = useState('Sarah');
  const [leadCompany, setLeadCompany] = useState('Acme Inc');
  const [isPlayingPreview, setIsPlayingPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const timerIntervalRef = useRef(null);
  const previewAudioRef = useRef(null);
  const audioContextRef = useRef(null);
  const maxVolumeRef = useRef(0);

  const fetchVoices = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/voice', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setVoices(data.voices || []);
      }
    } catch (err) {
      console.error('Failed to load voice profiles:', err);
    }
  };

  const fetchAccounts = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/accounts', {
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        const data = await res.json();
        setAccounts(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error('Failed to load accounts:', err);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchVoices(), fetchAccounts()]);
      setLoading(false);
    };
    init();

    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
      if (previewAudioRef.current) previewAudioRef.current.pause();
      if (audioContextRef.current) audioContextRef.current.close().catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startRecording = async () => {
    setErrorMsg('');
    setAudioBlob(null);
    setAudioUrl(null);
    setRecordingSeconds(0);
    audioChunksRef.current = [];
    maxVolumeRef.current = 0;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Audio analysis for volume / silence detection
      try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        audioContextRef.current = audioCtx;
        const source = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        const checkVolume = () => {
          if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') return;
          analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
          const avg = sum / dataArray.length;
          if (avg > maxVolumeRef.current) maxVolumeRef.current = avg;
          requestAnimationFrame(checkVolume);
        };
        requestAnimationFrame(checkVolume);
      } catch (audioCtxErr) {
        console.warn('AudioContext volume analysis not supported:', audioCtxErr);
      }

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));
        stream.getTracks().forEach((track) => track.stop());

        // Check if user was silent or spoke too quietly
        if (maxVolumeRef.current < 2 && recordingSeconds < 5) {
          setErrorMsg("We couldn't hear you. Sit closer to the mic and read the script out loud.");
        }
      };

      mediaRecorder.start(250);
      setIsRecording(true);

      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 30) {
            stopRecording();
            return 30;
          }
          return prev + 1;
        });
      }, 1000);
    } catch (err) {
      console.error('Microphone access denied or error:', err);
      setErrorMsg("We couldn't access your microphone. Please enable mic permissions or upload an audio file.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    setIsRecording(false);
  };

  const resetRecording = () => {
    setAudioBlob(null);
    setAudioUrl(null);
    setRecordingSeconds(0);
    setErrorMsg('');
  };

  const handleFileUpload = (e) => {
    setErrorMsg('');
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) {
      setErrorMsg('Audio file is too large (max 25MB).');
      return;
    }
    setAudioBlob(file);
    setAudioUrl(URL.createObjectURL(file));
  };

  const handleCreateClone = async () => {
    if (!audioBlob) {
      setErrorMsg('Please record or upload a sample first.');
      return;
    }
    if (!voiceName.trim()) {
      setErrorMsg('Please enter a name for this voice.');
      return;
    }

    setIsCloning(true);
    setErrorMsg('');

    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'sample.wav');
      formData.append('name', voiceName.trim());

      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/voice/clone', {
        method: 'POST',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to clone voice');
      }

      setVoiceName('');
      setAudioBlob(null);
      setAudioUrl(null);
      setRecordingSeconds(0);
      await fetchVoices();
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setIsCloning(false);
    }
  };

  const handleAssignSender = async (voiceId, accountId) => {
    try {
      const token = localStorage.getItem('token');
      const targetVoice = voices.find((v) => v.id === voiceId);
      if (!targetVoice) return;

      const currentAssigned = targetVoice.assigned_account_ids || [];
      const isAlreadyAssigned = currentAssigned.includes(accountId);
      const newAssigned = isAlreadyAssigned
        ? currentAssigned.filter((id) => id !== accountId)
        : [...currentAssigned, accountId];

      const res = await fetch(`/api/v1/outreach/voice/${voiceId}/assign`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({ account_ids: newAssigned }),
      });

      if (res.ok) {
        await fetchVoices();
      }
    } catch (err) {
      console.error('Failed to assign account to voice:', err);
    }
  };

  const handleDeleteVoice = async (voiceId) => {
    if (!window.confirm('Are you sure you want to delete this cloned voice?')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/voice/${voiceId}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        await fetchVoices();
      }
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  const handleGeneratePreview = async () => {
    if (!previewVoice) return;
    setPreviewLoading(true);
    try {
      if (previewAudioRef.current) {
        previewAudioRef.current.pause();
        previewAudioRef.current = null;
      }
      const token = localStorage.getItem('token');
      const res = await fetch('/api/v1/outreach/voice/preview', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: token ? `Bearer ${token}` : '',
        },
        body: JSON.stringify({
          voice_id: previewVoice.elevenlabs_voice_id || previewVoice.id,
          template_text: previewScript,
          lead_sample: {
            first_name: leadFirstName,
            company_name: leadCompany,
          },
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const mime = data.media_type || 'audio/wav';
        const snd = new Audio(`data:${mime};base64,${data.audio_base64}`);
        previewAudioRef.current = snd;
        setIsPlayingPreview(true);
        snd.onended = () => setIsPlayingPreview(false);
        snd.onerror = () => setIsPlayingPreview(false);
        await snd.play();
      }
    } catch (err) {
      console.error('Preview failed:', err);
    } finally {
      setPreviewLoading(false);
    }
  };

  const stopPreviewAudio = () => {
    if (previewAudioRef.current) {
      previewAudioRef.current.pause();
      previewAudioRef.current = null;
    }
    setIsPlayingPreview(false);
  };

  return (
    <div className="min-h-screen bg-[#faf9f6]/60 p-8 font-sans selection:bg-indigo-500 selection:text-white">
      <div className="max-w-6xl mx-auto space-y-7">
        {/* Header matching Prosp Part 3 Image 2 */}
        <div>
          <span className="text-[11px] font-bold tracking-widest text-indigo-600 uppercase">
            Voice Cloner
          </span>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">
            Send voice notes in your own voice
          </h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Record 30 seconds once. We copy your voice. Then every lead can get a voice note from you.
          </p>
        </div>

        {/* 2-Column Forensic Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-7 items-start">
          {/* Left Column: Script & Recording Studio */}
          <div className="lg:col-span-7 bg-white rounded-2xl border border-gray-200/80 p-7 shadow-xs space-y-6">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                Read This Out Loud
              </span>
              <div className="flex items-center gap-1 bg-gray-100 p-0.5 rounded-lg text-xs font-medium text-gray-600">
                <button
                  onClick={() => { setActiveTab('record'); resetRecording(); }}
                  className={`px-2.5 py-1 rounded-md transition-all text-xs ${
                    activeTab === 'record' ? 'bg-white shadow-xs text-indigo-600 font-semibold' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Record mic
                </button>
                <button
                  onClick={() => { setActiveTab('upload'); resetRecording(); }}
                  className={`px-2.5 py-1 rounded-md transition-all text-xs ${
                    activeTab === 'upload' ? 'bg-white shadow-xs text-indigo-600 font-semibold' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Upload sample
                </button>
              </div>
            </div>

            {/* Script Card matching Prosp bg tint and chips */}
            <div className="bg-[#f9f8f5] border border-stone-200/60 rounded-2xl p-6 text-xs text-gray-800 space-y-4">
              <div>
                <h4 className="font-bold text-gray-900 text-xs mb-2">Sample outreach message</h4>
                <p className="leading-relaxed text-gray-700">
                  hey{' '}
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-[#eef0fd] text-[#4f46e5] border border-indigo-200/40 mx-0.5">
                    First name
                  </span>
                  . Saw you&apos;re also based in London and in the marketing space as well. I work with a
                  ton of marketers doing lead gen and have a few ideas I think would work great for{' '}
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-[#eef0fd] text-[#4f46e5] border border-indigo-200/40 mx-0.5">
                    Company name
                  </span>
                  .
                </p>
                <p className="text-[11px] text-gray-400 italic mt-2.5">
                  Where you see a chip, say a real name out loud. It teaches the clone how you say names.
                </p>
              </div>

              <div className="pt-3 border-t border-stone-200/60">
                <h4 className="font-bold text-gray-900 text-xs mb-2">Then a few natural lines</h4>
                <div className="space-y-1.5 text-gray-600 text-xs">
                  <p>Hey, how are you doing?</p>
                  <p>I saw you were in the marketing industry so I thought I would connect here.</p>
                  <p>Hey, remember me? We met at the conference last year.</p>
                </div>
              </div>
            </div>

            {/* Recording Controls */}
            {activeTab === 'record' ? (
              <div className="flex flex-col items-center justify-center py-4 text-center space-y-3">
                <div className="relative">
                  <button
                    type="button"
                    onClick={isRecording ? stopRecording : startRecording}
                    disabled={isCloning}
                    className={`w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300 shadow-md ${
                      isRecording
                        ? 'bg-rose-500 hover:bg-rose-600 text-white animate-pulse ring-8 ring-rose-100'
                        : 'bg-[#4f46e5] hover:bg-indigo-700 text-white hover:scale-105 active:scale-95'
                    }`}
                    title={isRecording ? 'Stop recording' : 'Start recording'}
                  >
                    {isRecording ? <Square className="w-5 h-5" /> : <Mic className="w-6 h-6" />}
                  </button>
                  {isRecording && (
                    <span className="absolute -top-1 -right-1 flex h-4 w-4">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-4 w-4 bg-rose-500 text-[9px] text-white font-bold items-center justify-center">
                        •
                      </span>
                    </span>
                  )}
                </div>

                <div className="space-y-1">
                  <p className="font-bold text-gray-900 text-sm">
                    {isRecording ? `Recording... (${recordingSeconds}/30s)` : 'Record 30 seconds'}
                  </p>
                  <p className="text-xs text-gray-400">
                    {isRecording
                      ? 'Speak clearly into your microphone reading the script above'
                      : 'Tap the mic and read the script above.'}
                  </p>
                </div>

                {errorMsg && (
                  <p className="text-xs text-rose-600 flex items-center justify-center gap-1.5 mt-2 bg-rose-50 px-3 py-1.5 rounded-lg border border-rose-200/60 max-w-md">
                    <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                    <span>{errorMsg}</span>
                  </p>
                )}
              </div>
            ) : (
              <div className="py-6 border-2 border-dashed border-gray-200 rounded-xl text-center space-y-3 p-4">
                <Upload className="w-8 h-8 text-gray-400 mx-auto" />
                <div>
                  <label className="cursor-pointer text-xs font-semibold text-indigo-600 hover:text-indigo-500">
                    Choose an audio file
                    <input
                      type="file"
                      accept="audio/*"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>
                  <p className="text-[11px] text-gray-400 mt-1">WAV, MP3, or M4A up to 25MB</p>
                </div>
              </div>
            )}

            {/* Audio Preview & Save Section */}
            {audioUrl && (
              <div className="bg-indigo-50/50 border border-indigo-100 rounded-2xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-semibold text-indigo-900">
                    <Volume2 className="w-4 h-4 text-indigo-600" />
                    <span>Recorded voice sample ({recordingSeconds}s)</span>
                  </div>
                  <button
                    onClick={resetRecording}
                    className="flex items-center gap-1 text-[11px] text-gray-500 hover:text-gray-700 bg-white px-2 py-1 rounded-md border border-gray-200 shadow-2xs"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Re-record
                  </button>
                </div>

                <audio controls src={audioUrl} className="w-full h-8" />

                <div className="flex items-center gap-2.5 pt-1">
                  <input
                    type="text"
                    placeholder="Name this voice (e.g. Primary Outbound Voice)"
                    value={voiceName}
                    onChange={(e) => setVoiceName(e.target.value)}
                    className="flex-1 px-3 py-2 text-xs border border-gray-300 rounded-xl bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600"
                  />
                  <button
                    onClick={handleCreateClone}
                    disabled={isCloning || !voiceName.trim()}
                    className="px-4 py-2 bg-[#4f46e5] text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 transition-colors whitespace-nowrap shadow-xs"
                  >
                    {isCloning ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Cloning voice...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3.5 h-3.5" />
                        Save &amp; Clone Voice
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Your Voices & Best Practice Cards */}
          <div className="lg:col-span-5 space-y-5">
            {/* Your Voices Card */}
            <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-gray-900 text-sm">Your voices</h3>
                <span className="text-xs text-gray-400 font-medium">
                  {voices.length}/5 voices
                </span>
              </div>
              <p className="text-xs text-gray-500 leading-relaxed">
                One voice can speak for several senders, but each sender has exactly one voice.
              </p>

              {loading ? (
                <div className="py-8 text-center text-gray-400 text-xs">Loading voices...</div>
              ) : voices.length === 0 ? (
                <div className="py-8 text-center bg-gray-50/60 rounded-xl border border-dashed border-gray-200 text-gray-400 text-xs">
                  No voices yet. Record one on the left.
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {voices.map((v) => {
                    const isAssigning = activeAssignVoiceId === v.id;
                    const assignedAccounts = accounts.filter((a) =>
                      v.assigned_account_ids?.includes(a.id)
                    );

                    return (
                      <div key={v.id} className="py-3.5 space-y-2">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-xs font-bold text-gray-900">{v.name}</p>
                            <p className="text-[11px] text-gray-400">
                              {assignedAccounts.length === 0
                                ? 'No sender assigned'
                                : `${assignedAccounts.length} assigned sender${
                                    assignedAccounts.length === 1 ? '' : 's'
                                  }`}
                            </p>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => setPreviewVoice(v)}
                              title="Test voice personalization"
                              className="px-2 py-1 text-xs font-semibold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors flex items-center gap-1"
                            >
                              <Volume2 className="w-3.5 h-3.5" />
                              Preview
                            </button>
                            <button
                              onClick={() => handleDeleteVoice(v.id)}
                              title="Delete voice profile"
                              className="p-1.5 text-gray-400 hover:text-rose-600 rounded-lg hover:bg-gray-100 transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>

                        {/* Sender Account Assignment Selector */}
                        <div className="relative">
                          <button
                            onClick={() =>
                              setActiveAssignVoiceId((curr) => (curr === v.id ? null : v.id))
                            }
                            className="w-full flex items-center justify-between px-3 py-1.5 text-xs bg-gray-50 hover:bg-gray-100/80 border border-gray-200/80 rounded-xl transition-colors text-left"
                          >
                            <span className="flex items-center gap-1.5 text-gray-700 truncate">
                              <Users className="w-3 h-3 text-gray-400 shrink-0" />
                              {assignedAccounts.length === 0
                                ? 'Assign to connected sender...'
                                : assignedAccounts.map((a) => a.account_name || 'Account').join(', ')}
                            </span>
                            <ChevronDown className="w-3 h-3 text-gray-400 shrink-0 ml-1" />
                          </button>

                          {isAssigning && (
                            <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg p-1.5 z-20 space-y-1">
                              {accounts.length === 0 ? (
                                <p className="text-[11px] text-gray-400 p-2 text-center">
                                  No connected accounts yet. Connect one in Settings.
                                </p>
                              ) : (
                                accounts.map((acc) => {
                                  const isAssigned = v.assigned_account_ids?.includes(acc.id);
                                  return (
                                    <button
                                      key={acc.id}
                                      onClick={() => handleAssignSender(v.id, acc.id)}
                                      className="w-full flex items-center justify-between px-2.5 py-1.5 text-xs rounded-lg hover:bg-gray-50 transition-colors text-left"
                                    >
                                      <span className="text-gray-800 font-medium truncate">
                                        {acc.account_name || 'LinkedIn Account'}
                                      </span>
                                      {isAssigned && (
                                        <Check className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                                      )}
                                    </button>
                                  );
                                })
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Tips for best results Card */}
            <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-xs space-y-3.5">
              <h3 className="font-bold text-gray-900 text-sm">Tips for best results</h3>
              <ul className="space-y-2.5 text-xs text-gray-600">
                <li className="flex items-start gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                  <span>Record yourself for at least 30 seconds</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                  <span>Speak naturally, as if you are having a conversation</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                  <span>Use words and phrases that match your usual speaking style</span>
                </li>
                <li className="flex items-start gap-2.5">
                  <CheckCircle2 className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                  <span>Read all the sample text below</span>
                </li>
              </ul>
            </div>

            {/* Privacy Shield Banner */}
            <div className="bg-indigo-50/50 border border-indigo-100/70 rounded-2xl p-4 flex items-center gap-3">
              <Shield className="w-5 h-5 text-indigo-600 shrink-0" />
              <p className="text-xs text-indigo-900/90 font-medium leading-relaxed">
                Your recording stays private. We never share it.
              </p>
            </div>
          </div>
        </div>

        {/* Dynamic Voice Note Preview Modal */}
        {previewVoice && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-5 border border-gray-100 animate-in fade-in zoom-in-95 duration-200">
              <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                <div className="flex items-center gap-2">
                  <Volume2 className="w-5 h-5 text-indigo-600" />
                  <h3 className="font-bold text-gray-900 text-sm">
                    Voice Note Preview ({previewVoice.name})
                  </h3>
                </div>
                <button
                  onClick={() => { stopPreviewAudio(); setPreviewVoice(null); }}
                  className="text-gray-400 hover:text-gray-600 text-sm font-medium p-1"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-4 text-xs">
                <div>
                  <label className="block text-gray-700 font-semibold mb-1">
                    Template Script with Personalization Tokens:
                  </label>
                  <textarea
                    rows={3}
                    value={previewScript}
                    onChange={(e) => setPreviewScript(e.target.value)}
                    className="w-full p-2.5 border border-gray-200 rounded-xl text-xs font-mono focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 resize-none bg-stone-50/50"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-gray-500 mb-1">Lead First Name:</label>
                    <input
                      type="text"
                      value={leadFirstName}
                      onChange={(e) => setLeadFirstName(e.target.value)}
                      className="w-full p-2 border border-gray-200 rounded-xl text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-gray-500 mb-1">Lead Company:</label>
                    <input
                      type="text"
                      value={leadCompany}
                      onChange={(e) => setLeadCompany(e.target.value)}
                      className="w-full p-2 border border-gray-200 rounded-xl text-xs"
                    />
                  </div>
                </div>

                <div className="bg-[#f9f8f5] p-3.5 rounded-xl border border-stone-200/70 text-gray-700">
                  <span className="font-bold text-gray-900 block mb-1">Personalized Spoken Output:</span>
                  <p className="italic text-gray-600">
                    &ldquo;
                    {previewScript
                      .replace(/\{\{first_name\}\}/g, leadFirstName)
                      .replace(/\{\{company_name\}\}/g, leadCompany)}
                    &rdquo;
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2 border-t border-gray-100">
                <button
                  onClick={() => { stopPreviewAudio(); setPreviewVoice(null); }}
                  className="px-4 py-2 border border-gray-200 text-gray-600 rounded-xl text-xs font-semibold hover:bg-gray-50"
                >
                  Close
                </button>
                {isPlayingPreview ? (
                  <button
                    onClick={stopPreviewAudio}
                    className="px-4 py-2 bg-rose-600 text-white rounded-xl text-xs font-semibold hover:bg-rose-700 flex items-center gap-2 shadow-xs"
                  >
                    <Pause className="w-3.5 h-3.5" />
                    Stop Audio
                  </button>
                ) : (
                  <button
                    onClick={handleGeneratePreview}
                    disabled={previewLoading}
                    className="px-4 py-2 bg-[#4f46e5] text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 shadow-xs"
                  >
                    {previewLoading ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        Synthesizing...
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5" />
                        Play Personalized Note
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
