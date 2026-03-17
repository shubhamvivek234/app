import React, { useState, useRef } from 'react';
import { FaTimes, FaMinus, FaPaperPlane, FaPaperclip, FaExpandAlt } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { sendSupportRequest } from '@/lib/api';
import { toast } from 'sonner';

const SupportPopup = ({ isOpen, onClose }) => {
  const [cc, setCc] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const fileInputRef = useRef(null);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    const formData = new FormData();
    formData.append('to', 'support@socialentangler.com');
    formData.append('cc', cc);
    formData.append('subject', subject);
    formData.append('body', body);
    if (file) {
      formData.append('attachment', file);
    }

    try {
      await sendSupportRequest(formData);
      toast.success('Support request sent successfully!');
      setBody('');
      setCc('');
      setSubject('');
      setFile(null);
      onClose();
    } catch (error) {
      console.error('Failed to send support request:', error);
      toast.error('Failed to send request. Please try again or email us directly.');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  if (isMinimized) {
    return (
      <div className="fixed bottom-0 right-8 z-50 bg-white border border-gray-200 rounded-t-lg shadow-lg w-72">
        <div
          className="bg-slate-100 text-slate-800 px-4 py-2 rounded-t-lg flex justify-between items-center cursor-pointer border-b border-gray-200"
          onClick={() => setIsMinimized(false)}
        >
          <span className="font-medium text-sm">New Message</span>
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); setIsMinimized(false); }}
              className="text-slate-500 hover:bg-gray-200 p-1 rounded"
            >
              <FaExpandAlt size={12} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onClose(); }}
              className="text-slate-500 hover:bg-gray-200 p-1 rounded"
            >
              <FaTimes size={12} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-0 right-4 md:right-8 z-50 bg-white border border-gray-200 rounded-t-lg shadow-2xl w-full max-w-[500px] flex flex-col h-[600px]">
      {/* Header */}
      <div className="bg-[#f2f6fc] text-slate-800 px-4 py-3 rounded-t-lg flex justify-between items-center select-none cursor-pointer border-b border-gray-200" onClick={() => setIsMinimized(true)}>
        <span className="font-medium text-sm">New Message</span>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); setIsMinimized(true); }}
            className="text-slate-600 hover:bg-gray-200 p-1 rounded transition-colors"
          >
            <FaMinus size={12} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onClose(); }}
            className="text-slate-600 hover:bg-gray-200 p-1 rounded transition-colors"
          >
            <FaTimes size={14} />
          </button>
        </div>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex-1 flex flex-col overflow-hidden">

        {/* To Field */}
        <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-2">
          <span className="text-gray-500 text-sm w-12 shrink-0">To</span>
          <div className="flex-1">
            <span className="text-sm text-gray-800">support@socialentangler.com</span>
          </div>
          <div className="flex gap-2 text-sm text-gray-500">
            <span className="cursor-pointer hover:text-gray-800">Cc</span>
            <span className="cursor-pointer hover:text-gray-800">Bcc</span>
          </div>
        </div>

        {/* CC Field - only show if user types or by default for now let's just show it to match 'Cc Bcc' UI hint, or hidden? 
            The user request said "Cc section", let's keep it visible or implied. 
            For Gmail style, often it appears on click. Let's make it simpler: Just an input if they want.
        */}
        <div className="px-4 py-2 border-b border-gray-100 flex items-center gap-2">
          <input
            type="email"
            value={cc}
            onChange={(e) => setCc(e.target.value)}
            className="w-full outline-none text-sm placeholder:text-gray-500"
            placeholder="Cc"
          />
        </div>

        {/* Subject Field */}
        <div className="px-4 py-2 border-b border-gray-100">
          <input
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="w-full outline-none text-sm font-medium placeholder:text-gray-500"
            placeholder="Subject"
            required
          />
        </div>

        {/* Body Field */}
        <div className="flex-1 p-4 overflow-y-auto">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="w-full h-full resize-none outline-none text-slate-800 placeholder:text-gray-400 text-sm leading-relaxed"
            required
            autoFocus
          />
        </div>

        {/* Footer Actions */}
        <div className="p-4 flex justify-between items-center mt-auto border-t border-gray-100 bg-white">
          <div className="flex items-center gap-2">
            <Button
              type="submit"
              disabled={loading}
              className="bg-[#0b57d0] hover:bg-[#0b57d0]/90 text-white rounded-full px-6 py-2 h-9 text-sm font-medium flex items-center gap-2 shadow-sm"
            >
              {loading ? 'Sending...' : 'Send'}
            </Button>

            <div className="relative">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="text-gray-500 hover:bg-gray-100 p-2 rounded-full transition-colors"
                title="Attach files"
              >
                <FaPaperclip size={18} />
              </button>
            </div>
          </div>

          <div>
            {file && (
              <div className="flex items-center gap-2 bg-gray-100 px-3 py-1 rounded-full text-xs text-gray-700 max-w-[150px] truncate">
                <FaPaperclip size={10} />
                {file.name}
                <button onClick={() => setFile(null)} className="ml-1 hover:text-red-500"><FaTimes /></button>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => { setBody(''); setCc(''); setSubject(''); setFile(null); }}
            className="text-gray-400 hover:text-gray-600 p-2"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" /><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" /></svg>
          </button>
        </div>
      </form>
    </div>
  );
};

export default SupportPopup;
