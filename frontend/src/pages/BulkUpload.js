import React from 'react';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '@/components/DashboardLayout';
import {
  FaVideo, FaFileCsv, FaArrowRight, FaLayerGroup,
} from 'react-icons/fa';
import { SiInstagram, SiYoutube, SiTiktok, SiFacebook, SiLinkedin, SiX } from 'react-icons/si';

const PLATFORM_ICONS = [
  { Icon: SiInstagram, color: '#E1306C' },
  { Icon: SiYoutube, color: '#FF0000' },
  { Icon: SiFacebook, color: '#1877F2' },
  { Icon: SiLinkedin, color: '#0A66C2' },
  { Icon: SiTiktok, color: '#000000' },
  { Icon: SiX, color: '#000000' },
];

const FeatureCard = ({ icon: Icon, iconBg, title, badge, description, onClick, active }) => (
  <button
    onClick={onClick}
    className={`group text-left w-full rounded-2xl border-2 p-7 transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 ${
      active
        ? 'border-green-400 bg-green-50/60 shadow-md'
        : 'border-gray-200 bg-white hover:border-green-300'
    }`}
  >
    <div className="flex items-start gap-5">
      <div className={`w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 ${iconBg}`}>
        <Icon className="text-2xl text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <h3 className="text-base font-bold text-gray-900">{title}</h3>
          {badge && (
            <span className="px-2 py-0.5 text-[10px] font-bold bg-green-100 text-green-700 rounded-full uppercase tracking-wide">
              {badge}
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 leading-relaxed">{description}</p>
        <div className="flex items-center gap-1.5 mt-4">
          {PLATFORM_ICONS.map(({ Icon: PIcon, color }, i) => (
            <PIcon key={i} style={{ color }} className="text-base" />
          ))}
        </div>
      </div>
      <FaArrowRight className="text-gray-300 group-hover:text-green-500 transition-colors mt-1 flex-shrink-0" />
    </div>
  </button>
);

const BulkUpload = () => {
  const navigate = useNavigate();

  return (
    <DashboardLayout>
      <div className="max-w-2xl mx-auto pb-12">

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-green-500 flex items-center justify-center">
              <FaLayerGroup className="text-white text-base" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Bulk Upload</h1>
          </div>
          <p className="text-sm text-gray-500 ml-12">
            Upload and schedule content at scale — videos one by one or hundreds via CSV.
          </p>
        </div>

        {/* Selection cards */}
        <div className="space-y-4">
          <FeatureCard
            icon={FaVideo}
            iconBg="bg-green-500"
            title="Bulk Video Upload"
            badge="NEW"
            description="Upload and schedule multiple videos at once. Set individual captions, dates, and times — or apply bulk settings to all."
            onClick={() => navigate('/bulk-video')}
          />
          <FeatureCard
            icon={FaFileCsv}
            iconBg="bg-blue-500"
            title="Bulk Upload via CSV"
            badge="NEW"
            description="Import hundreds of posts at once using a CSV file. Download our template, fill it in, upload and we'll validate every row before scheduling."
            onClick={() => navigate('/bulk-csv')}
          />
        </div>
      </div>

    </DashboardLayout>
  );
};

export default BulkUpload;
