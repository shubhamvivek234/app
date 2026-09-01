import React, { useMemo } from 'react';
import { useSearchParams, useLocation } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import CreatePostForm from '@/pages/CreatePostForm';

const CreatePost = () => {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const editPostId = useMemo(() => searchParams.get('edit') || null, [searchParams]);

  const initialContent = location.state?.initialContent || location.state?.initialCaption || location.state?.caption || '';

  return (
    <DashboardLayout>
      <div className="h-[calc(100vh-3.5rem)] flex flex-col overflow-hidden">
        <CreatePostForm
          editPostId={editPostId}
          initialContent={initialContent}
          asModal={false}
        />
      </div>
    </DashboardLayout>
  );
};

export default CreatePost;
