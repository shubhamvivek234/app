import React, { useEffect, useState } from 'react';
import DashboardLayout from '@/components/DashboardLayout';
import { getPosts } from '@/lib/api';
import { toast } from 'sonner';
import { format, startOfMonth, endOfMonth, eachDayOfInterval, isSameDay, startOfWeek, endOfWeek, addMonths, subMonths, addWeeks, subWeeks } from 'date-fns';
import { FaChevronLeft, FaChevronRight, FaInfoCircle } from 'react-icons/fa';
import { Button } from '@/components/ui/button';

const CalendarView = () => {
  const [posts, setPosts] = useState([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState('month'); // 'month' or 'week'

  useEffect(() => {
    fetchPosts();
  }, []);

  const fetchPosts = async () => {
    try {
      const data = await getPosts();
      setPosts(data.filter((p) => p.scheduled_time));
    } catch (error) {
      toast.error('Failed to load posts');
    } finally {
      setLoading(false);
    }
  };

  let calendarStart, calendarEnd;
  if (viewMode === 'month') {
    const monthStart = startOfMonth(currentDate);
    const monthEnd = endOfMonth(currentDate);
    calendarStart = startOfWeek(monthStart, { weekStartsOn: 0 });
    calendarEnd = endOfWeek(monthEnd, { weekStartsOn: 0 });
  } else {
    calendarStart = startOfWeek(currentDate, { weekStartsOn: 0 });
    calendarEnd = endOfWeek(currentDate, { weekStartsOn: 0 });
  }
  const calendarDays = eachDayOfInterval({ start: calendarStart, end: calendarEnd });

  const getPostsForDay = (day) => {
    return posts.filter((post) => isSameDay(new Date(post.scheduled_time), day));
  };

  const goToPrevious = () => {
    if (viewMode === 'month') {
      setCurrentDate(subMonths(currentDate, 1));
    } else {
      setCurrentDate(subWeeks(currentDate, 1));
    }
  };

  const goToNext = () => {
    if (viewMode === 'month') {
      setCurrentDate(addMonths(currentDate, 1));
    } else {
      setCurrentDate(addWeeks(currentDate, 1));
    }
  };

  const isToday = (day) => isSameDay(day, new Date());

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <div className="text-gray-600">Loading calendar...</div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="max-w-full mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">Calendar</h1>
            <FaInfoCircle className="text-gray-400" />
          </div>

          <div className="flex items-center gap-4">
            {/* Month Navigation */}
            <div className="flex items-center gap-2">
              <button
                onClick={goToPrevious}
                className="p-1 hover:bg-gray-100 rounded"
                data-testid="prev-button"
              >
                <FaChevronLeft className="text-gray-500" />
              </button>
              <span className="text-lg font-medium text-gray-900 min-w-[200px] text-center">
                {viewMode === 'month'
                  ? format(currentDate, 'MMMM yyyy')
                  : `Week of ${format(calendarStart, 'MMM d, yyyy')}`}
              </span>
              <button
                onClick={goToNext}
                className="p-1 hover:bg-gray-100 rounded"
                data-testid="next-button"
              >
                <FaChevronRight className="text-gray-500" />
              </button>
            </div>

            {/* View Toggle */}
            <div className="flex bg-gray-100 rounded-lg p-1">
              <Button
                variant={viewMode === 'month' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('month')}
                className={viewMode === 'month' ? 'bg-green-500 hover:bg-green-600' : ''}
                data-testid="month-view-button"
              >
                📅 Month
              </Button>
              <Button
                variant={viewMode === 'week' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setViewMode('week')}
                className={viewMode === 'week' ? 'bg-green-500 hover:bg-green-600' : ''}
                data-testid="week-view-button"
              >
                📆 Week
              </Button>
            </div>
          </div>
        </div>

        {/* Calendar Grid */}
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          {/* Weekday Headers */}
          <div className="grid grid-cols-7 bg-gray-50 border-b border-gray-200">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
              <div
                key={day}
                className="text-center text-sm font-medium text-gray-600 py-3 border-r border-gray-200 last:border-r-0"
              >
                {day}
              </div>
            ))}
          </div>

          {/* Calendar Days */}
          <div className="grid grid-cols-7">
            {calendarDays.map((day, index) => {
              const dayPosts = getPostsForDay(day);
              const isCurrentMonth = day.getMonth() === currentDate.getMonth();
              const today = isToday(day);

              return (
                <div
                  key={index}
                  className={`min-h-[120px] border-b border-r border-gray-200 last:border-r-0 ${!isCurrentMonth ? 'bg-gray-50' : 'bg-white'
                    } ${today ? 'bg-green-500' : ''}`}
                  data-testid={`calendar-day-${format(day, 'yyyy-MM-dd')}`}
                >
                  {/* Day Number */}
                  <div className={`p-2 ${today ? 'text-white' : ''}`}>
                    <span className={`text-sm font-medium ${isCurrentMonth
                        ? today ? 'text-white' : 'text-gray-900'
                        : 'text-gray-400'
                      }`}>
                      {format(day, 'MMM d') === format(day, 'MMM 1')
                        ? format(day, 'MMM d')
                        : format(day, 'd')}
                    </span>
                  </div>

                  {/* Posts */}
                  <div className="px-1 pb-1 space-y-1">
                    {dayPosts.length > 0 ? (
                      <>
                        {dayPosts.slice(0, 3).map((post) => (
                          <div
                            key={post.id}
                            className={`text-xs px-2 py-1 rounded truncate cursor-pointer hover:opacity-80 ${today
                                ? 'bg-green-400 text-white'
                                : 'bg-gray-100 text-gray-700'
                              }`}
                            title={post.content}
                            data-testid={`post-${post.id}`}
                          >
                            {post.content?.substring(0, 30) || 'Scheduled post'}
                          </div>
                        ))}
                        {dayPosts.length > 3 && (
                          <div className={`text-xs px-2 ${today ? 'text-green-100' : 'text-gray-500'}`}>
                            +{dayPosts.length - 3} more
                          </div>
                        )}
                      </>
                    ) : (
                      isCurrentMonth && (
                        <div className={`text-xs px-2 ${today ? 'text-green-200' : 'text-gray-400'}`}>
                          No posts
                        </div>
                      )
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default CalendarView;
