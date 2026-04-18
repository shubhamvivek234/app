import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getPublicCalendar } from '@/lib/api';
import {
  format,
  startOfMonth,
  endOfMonth,
  eachDayOfInterval,
  startOfWeek,
  endOfWeek,
  isSameDay,
  addMonths,
  subMonths,
} from 'date-fns';
import { FaChevronLeft, FaChevronRight, FaCalendarAlt } from 'react-icons/fa';

const PublicCalendar = () => {
  const { token } = useParams();
  const [posts, setPosts] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await getPublicCalendar(token);
        setPosts(data.posts || []);
      } catch {
        setError('This calendar link is invalid or has been revoked.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [token]);

  // Calendar grid (month view only)
  const monthStart = startOfMonth(currentDate);
  const monthEnd = endOfMonth(currentDate);
  const calStart = startOfWeek(monthStart, { weekStartsOn: 0 });
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 0 });
  const days = eachDayOfInterval({ start: calStart, end: calEnd });

  const getPostsForDay = (day) =>
    posts.filter((p) => p.scheduled_time && isSameDay(new Date(p.scheduled_time), day));

  const isToday = (day) => isSameDay(day, new Date());

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-offwhite">
        <div className="text-gray-400 text-sm">Loading calendar…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-offwhite gap-3">
        <FaCalendarAlt className="text-gray-300 text-4xl" />
        <p className="text-gray-500 font-medium">{error}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-offwhite">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <FaCalendarAlt className="text-green-500" />
              <h1 className="text-xl font-bold text-gray-900">Content Calendar</h1>
            </div>
            <p className="text-sm text-gray-400">Read-only shared view</p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setCurrentDate(subMonths(currentDate, 1))}
              className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
            >
              <FaChevronLeft className="text-sm" />
            </button>
            <span className="text-base font-semibold text-gray-700 min-w-[140px] text-center">
              {format(currentDate, 'MMMM yyyy')}
            </span>
            <button
              onClick={() => setCurrentDate(addMonths(currentDate, 1))}
              className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors"
            >
              <FaChevronRight className="text-sm" />
            </button>
          </div>
        </div>

        {/* Calendar */}
        <div className="bg-offwhite rounded-xl border border-gray-200 overflow-hidden">
          {/* Day headers */}
          <div className="grid grid-cols-7 bg-offwhite border-b border-gray-200">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
              <div
                key={d}
                className="py-3 text-center text-xs font-semibold text-gray-500 border-r border-gray-200 last:border-r-0"
              >
                {d}
              </div>
            ))}
          </div>

          {/* Days grid */}
          <div className="grid grid-cols-7">
            {days.map((day, i) => {
              const dayPosts = getPostsForDay(day);
              const isCurrentMonth = day.getMonth() === currentDate.getMonth();
              const today = isToday(day);

              return (
                <div
                  key={i}
                  className={`min-h-[110px] border-b border-r border-gray-200 last:border-r-0 p-1.5
                    ${!isCurrentMonth ? 'bg-offwhite' : 'bg-offwhite'}
                    ${today ? 'bg-green-500' : ''}`}
                >
                  {/* Day number */}
                  <p className={`text-xs font-semibold mb-1 ${
                    isCurrentMonth
                      ? today ? 'text-white' : 'text-gray-800'
                      : 'text-gray-300'
                  }`}>
                    {format(day, 'd')}
                  </p>

                  {/* Post chips */}
                  <div className="space-y-0.5">
                    {dayPosts.slice(0, 3).map((post) => (
                      <div
                        key={post.id}
                        title={post.content}
                        className={`text-[10px] px-1.5 py-0.5 rounded truncate ${
                          today ? 'bg-green-400 text-white' : 'bg-blue-50 text-blue-700'
                        }`}
                      >
                        {post.content?.slice(0, 35) || 'Scheduled post'}
                      </div>
                    ))}
                    {dayPosts.length > 3 && (
                      <p className={`text-[10px] px-1 ${today ? 'text-green-100' : 'text-gray-400'}`}>
                        +{dayPosts.length - 3} more
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-gray-300 mt-6">
          Powered by Unravler — view-only shared calendar
        </p>
      </div>
    </div>
  );
};

export default PublicCalendar;
