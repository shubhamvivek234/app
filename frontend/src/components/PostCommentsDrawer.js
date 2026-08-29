import React, { useState } from 'react';
import { addPostComment, toggleCommentResolve, deletePostComment } from '@/lib/api';
import { toast } from 'sonner';
import {
  FaTimes,
  FaCommentDots,
  FaCheck,
  FaTrash,
  FaPaperPlane,
  FaReply,
} from 'react-icons/fa';

export default function PostCommentsDrawer({ isOpen, onClose, post, onCommentUpdated }) {
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!isOpen || !post) return null;

  const comments = post.comments || [];

  const handleAddComment = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;

    setSubmitting(true);
    try {
      const newComment = await addPostComment(post.id, text.trim());
      toast.success('Comment added');
      setText('');
      if (onCommentUpdated) {
        onCommentUpdated({
          ...post,
          comments: [...comments, newComment],
        });
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to add comment');
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleResolve = async (commentId) => {
    try {
      const res = await toggleCommentResolve(post.id, commentId);
      if (onCommentUpdated) {
        onCommentUpdated({
          ...post,
          comments: comments.map((c) =>
            c.id === commentId ? { ...c, resolved: res.resolved } : c
          ),
        });
      }
      toast.info(res.resolved ? 'Comment marked as resolved' : 'Comment reopened');
    } catch (err) {
      toast.error('Failed to update comment');
    }
  };

  const handleDelete = async (commentId) => {
    try {
      await deletePostComment(post.id, commentId);
      if (onCommentUpdated) {
        onCommentUpdated({
          ...post,
          comments: comments.filter((c) => c.id !== commentId),
        });
      }
      toast.success('Comment removed');
    } catch (err) {
      toast.error('Failed to delete comment');
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex justify-end">
      <div className="bg-white w-full max-w-md h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 border-b border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <FaCommentDots className="text-sm" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-gray-900">Post Feedback &amp; Comments</h3>
              <p className="text-[11px] text-gray-400">Collaborate with your team on draft revisions</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg">
            <FaTimes />
          </button>
        </div>

        {/* Post Preview Snippet */}
        <div className="p-4 bg-gray-50/70 border-b border-gray-100 text-xs text-gray-700 space-y-1">
          <span className="font-semibold text-gray-900 block truncate">Post Content:</span>
          <p className="line-clamp-2 text-gray-600">{post.content || '(No text content)'}</p>
        </div>

        {/* Comments Feed */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {comments.length === 0 ? (
            <div className="text-center py-16 text-gray-400 space-y-2">
              <FaCommentDots className="text-3xl text-gray-300 mx-auto" />
              <p className="text-xs">No feedback comments yet.</p>
              <p className="text-[11px] text-gray-400">Leave suggestions, requested image swaps, or editorial edits below.</p>
            </div>
          ) : (
            comments.map((comment) => (
              <div
                key={comment.id}
                className={`p-3.5 rounded-2xl border transition-colors ${
                  comment.resolved
                    ? 'bg-emerald-50/40 border-emerald-100 text-gray-500'
                    : 'bg-white border-gray-200 text-gray-800 shadow-2xs'
                }`}
              >
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="font-bold text-xs text-gray-900">{comment.author_name}</span>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleToggleResolve(comment.id)}
                      title={comment.resolved ? 'Reopen comment' : 'Mark as resolved'}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 ${
                        comment.resolved
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
                      }`}
                    >
                      <FaCheck className="text-[9px]" /> {comment.resolved ? 'Resolved' : 'Resolve'}
                    </button>
                    <button
                      onClick={() => handleDelete(comment.id)}
                      className="text-gray-400 hover:text-red-600 p-1"
                    >
                      <FaTrash className="text-[10px]" />
                    </button>
                  </div>
                </div>

                <p className={`text-xs leading-relaxed ${comment.resolved ? 'line-through opacity-70' : ''}`}>
                  {comment.text}
                </p>

                {comment.created_at && (
                  <span className="text-[10px] text-gray-400 mt-1 block">
                    {new Date(comment.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
              </div>
            ))
          )}
        </div>

        {/* Input Footer */}
        <form onSubmit={handleAddComment} className="p-3 border-t border-gray-100 bg-white">
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Leave feedback or suggestion..."
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="flex-1 px-3 py-2 text-xs bg-gray-50 border border-gray-200 rounded-xl outline-hidden focus:ring-2 focus:ring-indigo-500 focus:bg-white"
            />
            <button
              type="submit"
              disabled={submitting || !text.trim()}
              className="p-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl shadow-xs transition-all active:scale-95 disabled:opacity-50"
            >
              <FaPaperPlane className="text-xs" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
