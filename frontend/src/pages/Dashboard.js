import React, { useEffect, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getStats, getPosts, getFailedPosts, retryFailedPost } from '@/lib/api';
import { useNavigate } from 'react-router-dom';
import { FaPlus, FaCalendarAlt, FaCheckCircle, FaLink, FaExclamationTriangle, FaRedo } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { format } from 'date-fns';

const Dashboard = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [recentPosts, setRecentPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failedPosts, setFailedPosts] = useState([]);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [statsData, postsData, failedData] = await Promise.all([
        getStats(),
        getPosts(),
        getFailedPosts().catch(() => []),
      ]);
      setStats(statsData);
      setRecentPosts(postsData.slice(0, 5));
      setFailedPosts(failedData);
    } catch (error) {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async (postId) => {
    try {
      await retryFailedPost(postId);
      toast.success('Post queued for retry');
      fetchData();
    } catch (error) {
      toast.error('Failed to retry post');
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-slate-600">Loading...</div>
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
              Dashboard
            </h1>
            <p className="text-base text-slate-600 mt-1">Welcome back! Here's your overview.</p>
          </div>
          <Button onClick={() => navigate('/create')} data-testid="create-post-button">
            <FaPlus className="mr-2" />
            Create Post
          </Button>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-white rounded-lg border border-border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">Total Posts</p>
                <p className="text-3xl font-semibold text-slate-900 mt-2">{stats?.total_posts || 0}</p>
              </div>
              <div className="w-12 h-12 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FaCalendarAlt className="text-xl text-indigo-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">Scheduled</p>
                <p className="text-3xl font-semibold text-slate-900 mt-2">{stats?.scheduled_posts || 0}</p>
              </div>
              <div className="w-12 h-12 rounded-lg bg-amber-100 flex items-center justify-center">
                <FaCalendarAlt className="text-xl text-amber-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">Published</p>
                <p className="text-3xl font-semibold text-slate-900 mt-2">{stats?.published_posts || 0}</p>
              </div>
              <div className="w-12 h-12 rounded-lg bg-green-100 flex items-center justify-center">
                <FaCheckCircle className="text-xl text-green-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-border p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-600">Connected Accounts</p>
                <p className="text-3xl font-semibold text-slate-900 mt-2">{stats?.connected_accounts || 0}</p>
              </div>
              <div className="w-12 h-12 rounded-lg bg-purple-100 flex items-center justify-center">
                <FaLink className="text-xl text-purple-600" />
              </div>
            </div>
          </div>
        </div>

        {/* Failed Posts Alert */}
        {failedPosts.length > 0 && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <FaExclamationTriangle className="text-red-500" />
                <h3 className="font-semibold text-red-800">
                  {failedPosts.length} Post{failedPosts.length > 1 ? 's' : ''} Failed to Publish
                </h3>
              </div>
            </div>
            <div className="space-y-2">
              {failedPosts.slice(0, 3).map((post) => (
                <div
                  key={post.id}
                  className="flex items-center justify-between bg-white rounded-md p-3 border border-red-100"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-800 truncate">{post.content || 'No content'}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-slate-500">
                        Platforms: {(post.platforms || []).join(', ')}
                      </span>
                      {post.trace_id && (
                        <span className="text-xs text-slate-400 font-mono">
                          #{post.trace_id}
                        </span>
                      )}
                    </div>
                    {post.failure_reason && (
                      <p className="text-xs text-red-500 mt-1 truncate">{post.failure_reason}</p>
                    )}
                  </div>
                  <button
                    onClick={() => handleRetry(post.id)}
                    className="ml-3 flex items-center gap-1 text-xs bg-red-600 text-white px-3 py-1.5 rounded-md hover:bg-red-700 transition-colors flex-shrink-0"
                  >
                    <FaRedo className="text-xs" />
                    Retry
                  </button>
                </div>
              ))}
              {failedPosts.length > 3 && (
                <p className="text-xs text-red-600 text-center mt-1">
                  +{failedPosts.length - 3} more failed posts in Content Library
                </p>
              )}
            </div>
          </div>
        )}

        {/* Recent Posts */}
        <div className="bg-white rounded-lg border border-border">
          <div className="p-6 border-b border-border">
            <h2 className="text-xl font-semibold text-slate-900">Recent Posts</h2>
          </div>
          <div className="divide-y divide-border">
            {recentPosts.length === 0 ? (
              <div className="p-8 text-center text-slate-600">
                <p>No posts yet. Create your first post to get started!</p>
                <Button
                  className="mt-4"
                  onClick={() => navigate('/create')}
                  data-testid="empty-create-post-button"
                >
                  <FaPlus className="mr-2" />
                  Create Post
                </Button>
              </div>
            ) : (
              recentPosts.map((post) => (
                <div
                  key={post.id}
                  className="p-6 hover:bg-slate-50 cursor-pointer transition-colors"
                  onClick={() => navigate('/content')}
                  data-testid={`post-item-${post.id}`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <p className="text-slate-900 line-clamp-2">{post.content}</p>
                      <div className="flex items-center gap-4 mt-2">
                        <span className={`text-xs px-2 py-1 rounded-full ${
                          post.status === 'published'
                            ? 'bg-green-100 text-green-700'
                            : post.status === 'scheduled'
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-slate-100 text-slate-700'
                        }`}>
                          {post.status}
                        </span>
                        <span className="text-sm text-slate-600">
                          {post.scheduled_time
                            ? format(new Date(post.scheduled_time), 'MMM d, yyyy h:mm a')
                            : format(new Date(post.created_at), 'MMM d, yyyy')}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;