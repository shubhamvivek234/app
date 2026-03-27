import React, { useState } from 'react';
import { FaImage, FaVideo, FaTimes, FaCloudUploadAlt, FaMagic } from 'react-icons/fa';
import { Progress } from '@/components/ui/progress';
import { generateImage } from '@/lib/api';
import { toast } from 'sonner';

const AI_SIZES = [
  { value: '1024x1024', label: 'Square (1:1)' },
  { value: '1792x1024', label: 'Landscape (16:9)' },
  { value: '1024x1792', label: 'Portrait (9:16)' },
];

const AI_STYLES = [
  { value: 'vivid', label: 'Vivid' },
  { value: 'natural', label: 'Natural' },
];

const MediaUploader = ({ postType, uploadedMedia, uploading, uploadProgress, onFileSelect, onRemove, onAiImage, fileInputRef }) => {
  const [showAi, setShowAi] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiSize, setAiSize] = useState('1024x1024');
  const [aiStyle, setAiStyle] = useState('vivid');
  const [aiGenerating, setAiGenerating] = useState(false);

  if (postType === 'text') return null;

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) onFileSelect(file);
  };

  const handleDragOver = (e) => e.preventDefault();

  const handleInputChange = (e) => {
    const file = e.target.files?.[0];
    if (file) onFileSelect(file);
  };

  const handleGenerate = async () => {
    if (!aiPrompt.trim()) return;
    setAiGenerating(true);
    try {
      const data = await generateImage(aiPrompt.trim(), aiSize, aiStyle);
      if (onAiImage) onAiImage(data.url);
      setShowAi(false);
      setAiPrompt('');
      toast.success('Image generated!');
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to generate image');
    } finally {
      setAiGenerating(false);
    }
  };

  const accept = postType === 'video' ? 'video/*' : postType === 'mixed' ? 'image/*,video/*' : 'image/*';
  const label = postType === 'video' ? 'MP4, MOV, AVI, WebM' : postType === 'mixed' ? 'JPG, PNG, GIF, WebP, MP4, MOV' : 'JPG, PNG, GIF, WebP';
  const canAiGenerate = postType !== 'video' && postType !== 'mixed' && !uploadedMedia && !uploading;

  return (
    <div className="mb-4">
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleInputChange}
        className="hidden"
      />

      {!uploadedMedia && !uploading && (
        <>
          <div
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            className="border-2 border-dashed border-gray-200 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:border-blue-300 hover:bg-blue-50/30 transition-all group"
          >
            <div className="w-12 h-12 rounded-xl bg-gray-100 group-hover:bg-blue-100 flex items-center justify-center mb-3 transition-colors">
              {postType === 'video' ? (
                <FaVideo className="text-xl text-gray-400 group-hover:text-blue-500 transition-colors" />
              ) : postType === 'mixed' ? (
                <div className="flex items-center gap-0.5">
                  <FaImage className="text-base text-gray-400 group-hover:text-teal-500 transition-colors" />
                  <FaVideo className="text-base text-gray-400 group-hover:text-teal-500 transition-colors" />
                </div>
              ) : (
                <FaImage className="text-xl text-gray-400 group-hover:text-blue-500 transition-colors" />
              )}
            </div>
            <p className="text-sm font-medium text-gray-700">
              Drag & drop or <span className="text-blue-600">browse</span>
            </p>
            <p className="text-xs text-gray-400 mt-1">{label}</p>
          </div>

          {canAiGenerate && (
            <div className="mt-2">
              <button
                onClick={() => setShowAi((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-purple-600 hover:text-purple-800 font-medium transition-colors"
              >
                <FaMagic className="text-[10px]" />
                {showAi ? 'Hide AI generator' : 'Generate with AI'}
              </button>

              {showAi && (
                <div className="mt-2 bg-purple-50 border border-purple-100 rounded-xl p-4">
                  <p className="text-xs font-semibold text-purple-700 mb-2">AI Image Generation</p>
                  <textarea
                    value={aiPrompt}
                    onChange={(e) => setAiPrompt(e.target.value)}
                    placeholder="Describe the image you want to generate…"
                    rows={3}
                    className="w-full border border-purple-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 placeholder:text-gray-400 resize-none mb-2 bg-offwhite"
                  />
                  <div className="flex gap-2 mb-3">
                    <select
                      value={aiSize}
                      onChange={(e) => setAiSize(e.target.value)}
                      className="flex-1 text-xs border border-purple-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-purple-400 bg-offwhite"
                    >
                      {AI_SIZES.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                    <select
                      value={aiStyle}
                      onChange={(e) => setAiStyle(e.target.value)}
                      className="flex-1 text-xs border border-purple-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-purple-400 bg-offwhite"
                    >
                      {AI_STYLES.map((s) => (
                        <option key={s.value} value={s.value}>{s.label}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={handleGenerate}
                    disabled={aiGenerating || !aiPrompt.trim()}
                    className="w-full py-2 text-sm font-semibold bg-purple-600 hover:bg-purple-700 text-white rounded-lg disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
                  >
                    {aiGenerating ? (
                      <>
                        <div className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                        Generating…
                      </>
                    ) : (
                      <>
                        <FaMagic className="text-xs" />
                        Generate
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {uploading && (
        <div className="border border-gray-200 rounded-xl p-6 flex flex-col items-center gap-3">
          <FaCloudUploadAlt className="text-3xl text-blue-400 animate-pulse" />
          <p className="text-sm font-medium text-gray-700">Uploading… {uploadProgress}%</p>
          <Progress value={uploadProgress} className="w-full h-1.5" />
        </div>
      )}

      {uploadedMedia && !uploading && (
        <div className="relative rounded-xl overflow-hidden border border-gray-200 group bg-black">
          {uploadedMedia.type === 'video' ? (
            <video
              src={uploadedMedia.url}
              controls
              className="w-full max-h-64 object-contain"
            />
          ) : (
            <img
              src={uploadedMedia.url}
              alt="Preview"
              className="w-full max-h-64 object-contain"
            />
          )}
          <button
            onClick={onRemove}
            className="absolute top-2 right-2 w-7 h-7 rounded-full bg-black/60 hover:bg-black/80 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow"
          >
            <FaTimes className="text-xs" />
          </button>
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/50 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <p className="text-white text-xs truncate">{uploadedMedia.name}</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default MediaUploader;
