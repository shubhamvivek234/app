import React from 'react';

const PlayableVideoPreview = ({
  src,
  poster,
  className = '',
  controls = true,
  muted = false,
  ...props
}) => {
  if (!src) return null;

  return (
    <video
      src={src}
      poster={poster}
      controls={controls}
      muted={muted}
      preload="metadata"
      playsInline
      className={`bg-black object-contain ${className}`}
      {...props}
    />
  );
};

export default PlayableVideoPreview;
