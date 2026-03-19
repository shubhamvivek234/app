import React, { useEffect, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getStats, getPosts, getWorkspaceMembers, getWorkspaceActivity } from '@/lib/api';
import { useNavigate } from 'react-router-dom';
import { FaPlus, FaCalendarAlt, FaCheckCircle, FaLink } from 'react-icons/fa';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { format } from 'date-fns';

const Dashboard = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [recentPosts, setRecentPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [workspaceMembers, setWorkspaceMembers] = useState([]);
  const [teamActivity, setTeamActivity] = useState([]);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [statsData, postsData] = await Promise.all([
        getStats(),
        getPosts(),
      ]);
      setStats(statsData);
      setRecentPosts(postsData.slice(0, 5));
    } catch (error) {
      toast.error('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }

    // Fetch workspace members + activity
    try {
      const [membersData, activityData] = await Promise.all([
        getWorkspaceMembers(),
        getWorkspaceActivity(10),
      ]);
      setWorkspaceMembers(membersData?.members || []);
      setTeamActivity(activityData?.activity || []);
    } catch (err) {
      // Workspace not critical — silent fail
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
          <div className="bg-offwhite rounded-lg border border-border p-6">
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

          <div className="bg-offwhite rounded-lg border border-border p-6">
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

          <div className="bg-offwhite rounded-lg border border-border p-6">
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

          <div className="bg-offwhite rounded-lg border border-border p-6">
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

        {/* Recent Posts */}
        <div className="bg-offwhite rounded-lg border border-border">
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
                            : 'bg-offwhite border border-slate-200 text-slate-700'
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

        {/* Team Activity — only show if workspace has multiple members */}
        {workspaceMembers.length > 1 && (
          <div className="bg-offwhite rounded-xl border border-slate-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-800">Team Activity</h3>
              <span className="text-xs text-slate-400">{workspaceMembers.length} members</span>
            </div>
            {teamActivity.length === 0 ? (
              <p className="text-sm text-slate-400 text-center py-4">No recent team activity</p>
            ) : (
              <div className="space-y-3">
                {teamActivity.slice(0, 5).map((item) => (
                  <div key={item.id} className="flex items-start gap-3">
                    <img
                      src={item.author?.picture || `https://ui-avatars.com/api/?name=${encodeURIComponent(item.author?.name || 'U')}&size=32`}
                      alt={item.author?.name}
                      className="w-7 h-7 rounded-full flex-shrink-0"
                    />
                    <div className="min-w-0">
                      <p className="text-xs text-slate-600 truncate">
                        <span className="font-medium text-slate-800">{item.author?.name}</span>
                        {' '}
                        {item.status === 'published' ? 'published to' : item.status === 'scheduled' ? 'scheduled for' : 'post failed on'}
                        {' '}
                        <span className="font-medium">{(item.platforms || []).join(', ')}</span>
                      </p>
                      <p className="text-xs text-slate-400 truncate mt-0.5">{(item.content || '').slice(0, 60)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;