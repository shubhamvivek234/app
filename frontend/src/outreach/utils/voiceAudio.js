// Decode the actual browser format and produce bounded mono 16 kHz PCM WAV.
export function pcmWav(samples) {
  if (!samples.length || samples.length > 960000) throw new Error('Audio exceeds 60 seconds.');
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset, value) => [...value].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, buffer.byteLength - 8, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, 16000, true); view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, i) => {
    const value = Math.max(-1, Math.min(1, Number.isFinite(sample) ? sample : 0));
    view.setInt16(44 + i * 2, value * (value < 0 ? 32768 : 32767), true);
  });
  return buffer;
}

export async function normalizeVoiceSample(blob) {
  if (blob.size > 10 * 1024 * 1024) throw new Error('Audio file is too large (max 10MB).');
  const Context = window.AudioContext || window.webkitAudioContext;
  const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!Context || !Offline) throw new Error('Audio conversion is unavailable in this browser.');
  const context = new Context();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    if (decoded.duration < 20 || decoded.duration > 60) throw new Error('Use a 20–60 second recording.');
    const offline = new Offline(1, Math.ceil(decoded.duration * 16000), 16000);
    const source = offline.createBufferSource();
    source.buffer = decoded; source.connect(offline.destination); source.start();
    const rendered = await offline.startRendering();
    return new Blob([pcmWav(rendered.getChannelData(0))], { type: 'audio/wav' });
  } finally {
    await context.close();
  }
}
