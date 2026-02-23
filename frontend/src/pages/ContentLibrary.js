import React, { useEffect, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getPosts, deletePost, getSocialAccounts } from '@/lib/api';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { format } from 'date-fns';
import { FaEdit, FaTrash, FaPlus, FaYoutube, FaInstagram, FaFacebook, FaTiktok, FaUser } from 'react-icons/fa';

const platformIcons = {
  youtube: <FaYoutube className="text-red-500" />,
  instagram: <FaInstagram className="text-pink-500" />,
  facebook: <FaFacebook className="text-blue-500" />,
  tiktok: <FaTiktok className="text-black" />,
};

const ContentLibrary = () => {
  const navigate = useNavigate();
  const [posts, setPosts] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all, draft, scheduled, published

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    try {
      const [postsData, accountsData] = await Promise.all([getPosts(), getSocialAccounts()]);
      setPosts(postsData);
      setAccounts(accountsData);
    } catch (error) {
      toast.error('Failed to load posts');
    } finally {
      setLoading(false);
    }
  };

  // Build a lookup map from account id -> account object
  const accountMap = accounts.reduce((acc, a) => {
    acc[a.id] = a;
    return acc;
  }, {});

  const handleDelete = async (postId) => {
    if (!window.confirm('Are you sure you want to delete this post?')) return;

    try {
      await deletePost(postId);
      setPosts(posts.filter((p) => p.id !== postId));
      toast.success('Post deleted');
    } catch (error) {
      toast.error('Failed to delete post');
    }
  };

  const filteredPosts = posts.filter((post) => {
    if (filter === 'all') return true;
    return post.status === filter;
  });

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-slate-600">Loading posts...</div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
              Content Library
            </h1>
            <p className="text-base text-slate-600 mt-1">Manage all your posts in one place</p>
          </div>
          <Button onClick={() => navigate('/create')} data-testid="create-post-button">
            <FaPlus className="mr-2" />
            Create Post
          </Button>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-2 border-b border-border">
          {[
            { id: 'all', label: 'All' },
            { id: 'draft', label: 'Drafts' },
            { id: 'scheduled', label: 'Scheduled' },
            { id: 'published', label: 'Published' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilter(tab.id)}
              data-testid={`filter-${tab.id}`}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${filter === tab.id
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-600 hover:text-slate-900'
                }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Posts List */}
        <div className="space-y-4">
          {filteredPosts.length === 0 ? (
            <div className="bg-white rounded-lg border border-border p-12 text-center">
              <p className="text-slate-600 mb-4">No posts found</p>
              <Button onClick={() => navigate('/create')} data-testid="empty-create-button">
                <FaPlus className="mr-2" />
                Create Your First Post
              </Button>
            </div>
          ) : (
            filteredPosts.map((post) => {
              const videoTitle = post.youtube_title || post.video_title || null;
              const postAccounts = (post.accounts || []).map((id) => accountMap[id]).filter(Boolean);

              return (
                <div
                  key={post.id}
                  className="bg-white rounded-lg border border-border p-6 hover:shadow-sm transition-shadow"
                  data-testid={`post-${post.id}`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1 space-y-3">
                      {/* Status + Scheduled Time */}
                      <div className="flex items-center gap-3 flex-wrap">
                        <span
                          className={`text-xs px-2 py-1 rounded-full font-medium ${post.status === 'published'
                            ? 'bg-green-100 text-green-700'
                            : post.status === 'scheduled'
                              ? 'bg-amber-100 text-amber-700'
                              : post.status === 'failed'
                                ? 'bg-red-100 text-red-700'
                                : 'bg-slate-100 text-slate-700'
                            }`}
                        >
                          {post.status}
                        </span>
                        <span className="text-sm text-slate-500">
                          {post.scheduled_time
                            ? `Scheduled for ${format(new Date(post.scheduled_time), 'MMM d, yyyy h:mm a')}`
                            : `Created ${format(new Date(post.created_at), 'MMM d, yyyy')}`}
                        </span>
                      </div>

                      {/* Video Title (if present) */}
                      {videoTitle && (
                        <p className="text-slate-900 font-semibold text-base">
                          🎬 {videoTitle}
                        </p>
                      )}

                      {/* Main Caption */}
                      {post.content && (
                        <p className="text-slate-700 text-sm line-clamp-2">{post.content}</p>
                      )}

                      {/* Platforms */}
                      <div className="flex gap-2 flex-wrap items-center">
                        {post.platforms.map((platform) => (
                          <span
                            key={platform}
                            className="flex items-center gap-1 text-xs px-2 py-1 bg-indigo-50 text-indigo-700 rounded"
                          >
                            {platformIcons[platform] || null}
                            <span className="capitalize">{platform}</span>
                          </span>
                        ))}
                      </div>

                      {/* Posted Accounts - same style as ConnectedAccounts page */}
                      {postAccounts.length > 0 && (
                        <div className="flex gap-2 flex-wrap items-center">
                          {postAccounts.map((acc) => {
                            const initial = (acc.platform_username || acc.display_name || 'U').charAt(0).toUpperCase();
                            const colors = ['bg-blue-500', 'bg-green-500', 'bg-yellow-500', 'bg-red-500', 'bg-purple-500', 'bg-pink-500', 'bg-indigo-500', 'bg-teal-500'];
                            const bgColor = colors[(acc.platform_username || 'U').charCodeAt(0) % colors.length];
                            return (
                              <div
                                key={acc.id}
                                className="flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-2 py-1 text-sm shadow-sm"
                              >
                                {acc.picture_url ? (
                                  <img src={acc.picture_url} alt={acc.platform_username} className="w-5 h-5 rounded-full object-cover" />
                                ) : (
                                  <div className={`w-5 h-5 rounded-full ${bgColor} flex items-center justify-center text-white text-xs`}>{initial}</div>
                                )}
                                <span className="text-gray-800 font-medium">{acc.platform_username || acc.display_name}</span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    {/* Action Buttons */}
                    <div className="flex gap-2 ml-4 shrink-0">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/create?edit=${post.id}`)}
                        data-testid={`edit-${post.id}`}
                      >
                        <FaEdit />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDelete(post.id)}
                        data-testid={`delete-${post.id}`}
                      >
                        <FaTrash className="text-red-600" />
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ContentLibrary;