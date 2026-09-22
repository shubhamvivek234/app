import React, { useState, useEffect, useRef } from 'react';
import { Mic, Square, Play, Trash2, CheckCircle2, Shield, Upload, Sparkles, Volume2, RefreshCw, AlertCircle } from 'lucide-react';

export default function OutreachVoice() {
  const [voices, setVoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [voiceName, setVoiceName] = useState('');
  const [isCloning, setIsCloning] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [activeTab, setActiveTab] = useState('record'); // 'record' | 'upload'
  
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

  const fetchVoices = async () => {
    setLoading(true);
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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVoices();
    return () => {
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startRecording = async () => {
    setErrorMsg('');
    setAudioBlob(null);
    setAudioUrl(null);
    setRecordingSeconds(0);
    audioChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
      setErrorMsg("Could not access your microphone. Please allow microphone permissions or upload an audio file.");
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

  const handleDeleteVoice = async (voiceId) => {
    if (!window.confirm('Are you sure you want to delete this cloned voice?')) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/v1/outreach/voice/${voiceId}`, {
        method: 'DELETE',
        headers: { Authorization: token ? `Bearer ${token}` : '' },
      });
      if (res.ok) {
        fetchVoices();
      }
    } catch (err) {
      console.error('Delete failed:', err);
    }
  };

  const handleGeneratePreview = async () => {
    if (!previewVoice) return;
    setPreviewLoading(true);
    try {
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
        const snd = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
        previewAudioRef.current = snd;
        setIsPlayingPreview(true);
        snd.onended = () => setIsPlayingPreview(false);
        await snd.play();
      }
    } catch (err) {
      console.error('Preview failed:', err);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-neutral-50/50 p-8">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header matching Prosp Part 3 Image 2 */}
        <div>
          <span className="text-xs font-bold tracking-widest text-indigo-600 uppercase">
            Voice Cloner
          </span>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">
            Send voice notes in your own voice
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Record 30 seconds once. We copy your voice. Then every lead can get a voice note from you.
          </p>
        </div>

        {/* 2-Column Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Script & Recording Studio */}
          <div className="lg:col-span-7 bg-white rounded-2xl border border-gray-200/80 p-7 shadow-sm space-y-6">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                Read This Out Loud
              </span>
              <div className="flex items-center gap-1 bg-gray-100 p-0.5 rounded-lg text-xs font-medium text-gray-600">
                <button
                  onClick={() => setActiveTab('record')}
                  className={`px-2.5 py-1 rounded-md transition-all ${
                    activeTab === 'record' ? 'bg-white shadow-xs text-indigo-600 font-semibold' : ''
                  }`}
                >
                  Record Mic
                </button>
                <button
                  onClick={() => setActiveTab('upload')}
                  className={`px-2.5 py-1 rounded-md transition-all ${
                    activeTab === 'upload' ? 'bg-white shadow-xs text-indigo-600 font-semibold' : ''
                  }`}
                >
                  Upload Audio
                </button>
              </div>
            </div>

            {/* Script Card */}
            <div className="bg-stone-50/80 border border-stone-200/70 rounded-2xl p-6 text-sm text-gray-800 space-y-4">
              <div>
                <h4 className="font-semibold text-gray-900 mb-2">Sample outreach message</h4>
                <p className="leading-relaxed">
                  Hey{' '}
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-indigo-100/90 text-indigo-700 border border-indigo-200/60 mx-1">
                    First name
                  </span>
                  . Saw you're also based in London and in the marketing space as well. I work with a
                  ton of marketers doing lead gen and have a few ideas I think would work great for{' '}
                  <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-indigo-100/90 text-indigo-700 border border-indigo-200/60 mx-1">
                    Company name
                  </span>
                  .
                </p>
                <p className="text-xs text-gray-400 italic mt-2.5">
                  Where you see a chip, say a real name out loud. It teaches the clone how you say names.
                </p>
              </div>

              <div className="pt-2 border-t border-stone-200/60">
                <h4 className="font-semibold text-gray-900 mb-1.5">Then a few natural lines</h4>
                <div className="space-y-1 text-gray-600">
                  <p>Hey, how are you doing?</p>
                  <p>I saw you were in the marketing industry so I thought I would connect here.</p>
                  <p>Hey, remember me? We met at the conference last year.</p>
                </div>
              </div>
            </div>

            {/* Recording Controls */}
            {activeTab === 'record' ? (
              <div className="flex flex-col items-center justify-center py-6 text-center space-y-3">
                <button
                  type="button"
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={isCloning}
                  className={`w-18 h-18 rounded-full flex items-center justify-center transition-all duration-300 shadow-md ${
                    isRecording
                      ? 'bg-rose-500 hover:bg-rose-600 text-white animate-pulse ring-8 ring-rose-100'
                      : 'bg-indigo-600 hover:bg-indigo-700 text-white hover:scale-105 active:scale-95'
                  }`}
                >
                  {isRecording ? <Square className="w-6 h-6" /> : <Mic className="w-7 h-7" />}
                </button>

                <div className="space-y-1">
                  <p className="font-semibold text-gray-900 text-base">
                    {isRecording ? `Recording... (${recordingSeconds}/30s)` : 'Record 30 seconds'}
                  </p>
                  <p className="text-xs text-gray-500">
                    {isRecording
                      ? 'Speak clearly into your microphone reading the script above'
                      : 'Tap the mic and read the script above.'}
                  </p>
                </div>

                {errorMsg && (
                  <p className="text-xs text-rose-600 flex items-center gap-1 mt-2">
                    <AlertCircle className="w-3.5 h-3.5" />
                    {errorMsg}
                  </p>
                )}
              </div>
            ) : (
              <div className="py-6 border-2 border-dashed border-gray-200 rounded-xl text-center space-y-3 p-4">
                <Upload className="w-8 h-8 text-gray-400 mx-auto" />
                <div>
                  <label className="cursor-pointer text-sm font-semibold text-indigo-600 hover:text-indigo-500">
                    Choose an audio file
                    <input
                      type="file"
                      accept="audio/*"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>
                  <p className="text-xs text-gray-500 mt-1">WAV, MP3, or M4A up to 25MB</p>
                </div>
              </div>
            )}

            {/* Audio Preview & Save Section */}
            {audioUrl && (
              <div className="bg-indigo-50/50 border border-indigo-100 rounded-xl p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-indigo-900">Recorded Sample Audio</span>
                  <audio controls src={audioUrl} className="h-8 max-w-[240px]" />
                </div>

                <div className="flex items-center gap-3">
                  <input
                    type="text"
                    placeholder="Name this voice (e.g. Shubham - Primary Outbound)"
                    value={voiceName}
                    onChange={(e) => setVoiceName(e.target.value)}
                    className="flex-1 px-3.5 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600"
                  />
                  <button
                    onClick={handleCreateClone}
                    disabled={isCloning || !voiceName.trim()}
                    className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 transition-colors whitespace-nowrap"
                  >
                    {isCloning ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Cloning...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        Save & Clone Voice
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
            <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-bold text-gray-900 text-base">Your voices</h3>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-gray-100 text-gray-600">
                  {voices.length}/5 voices
                </span>
              </div>
              <p className="text-xs text-gray-500 leading-relaxed">
                One voice can speak for several senders, but each sender has exactly one voice.
              </p>

              {loading ? (
                <div className="py-8 text-center text-gray-400 text-sm">Loading voices...</div>
              ) : voices.length === 0 ? (
                <div className="py-8 text-center bg-gray-50/60 rounded-xl border border-dashed border-gray-200 text-gray-400 text-sm">
                  No voices yet. Record one on the left.
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {voices.map((v) => (
                    <div key={v.id} className="py-3 flex items-center justify-between group">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{v.name}</p>
                        <p className="text-xs text-gray-400">
                          {v.assigned_account_ids?.length || 0} assigned senders
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setPreviewVoice(v)}
                          title="Preview personalized voice note"
                          className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-md hover:bg-gray-100 transition-colors"
                        >
                          <Volume2 className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteVoice(v.id)}
                          title="Delete voice profile"
                          className="p-1.5 text-gray-400 hover:text-rose-600 rounded-md hover:bg-gray-100 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Tips for best results Card */}
            <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-sm space-y-4">
              <h3 className="font-bold text-gray-900 text-base">Tips for best results</h3>
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
            <div className="bg-indigo-50/60 border border-indigo-100/90 rounded-2xl p-4 flex items-center gap-3">
              <Shield className="w-5 h-5 text-indigo-600 shrink-0" />
              <p className="text-xs text-indigo-900 font-medium leading-relaxed">
                Your recording stays private. We never share it.
              </p>
            </div>
          </div>
        </div>

        {/* Dynamic Voice Note Preview Modal */}
        {previewVoice && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-5 border border-gray-100">
              <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                <div className="flex items-center gap-2">
                  <Volume2 className="w-5 h-5 text-indigo-600" />
                  <h3 className="font-bold text-gray-900">
                    Voice Note Preview ({previewVoice.name})
                  </h3>
                </div>
                <button
                  onClick={() => setPreviewVoice(null)}
                  className="text-gray-400 hover:text-gray-600 text-sm font-medium"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-4 text-xs">
                <div>
                  <label className="block text-gray-700 font-medium mb-1">
                    Template Script with Tokens:
                  </label>
                  <textarea
                    rows={3}
                    value={previewScript}
                    onChange={(e) => setPreviewScript(e.target.value)}
                    className="w-full p-2.5 border border-gray-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-gray-500 mb-1">Lead First Name:</label>
                    <input
                      type="text"
                      value={leadFirstName}
                      onChange={(e) => setLeadFirstName(e.target.value)}
                      className="w-full p-2 border border-gray-300 rounded-lg"
                    />
                  </div>
                  <div>
                    <label className="block text-gray-500 mb-1">Lead Company:</label>
                    <input
                      type="text"
                      value={leadCompany}
                      onChange={(e) => setLeadCompany(e.target.value)}
                      className="w-full p-2 border border-gray-300 rounded-lg"
                    />
                  </div>
                </div>

                <div className="bg-stone-50 p-3 rounded-lg border border-stone-200 text-gray-700">
                  <span className="font-semibold text-gray-900 block mb-1">Personalized Result:</span>
                  {previewScript
                    .replace(/\{\{first_name\}\}/g, leadFirstName)
                    .replace(/\{\{company_name\}\}/g, leadCompany)}
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  onClick={() => setPreviewVoice(null)}
                  className="px-4 py-2 border border-gray-200 text-gray-600 rounded-lg text-xs font-medium hover:bg-gray-50"
                >
                  Close
                </button>
                <button
                  onClick={handleGeneratePreview}
                  disabled={previewLoading}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2"
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
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
