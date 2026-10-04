import { pcmWav, normalizeVoiceSample } from './voiceAudio';

test('WAV output has actual mono PCM header and clipped signed samples', () => {
  const buffer = pcmWav(new Float32Array([-2, 0, 2, NaN]));
  const view = new DataView(buffer);
  expect(String.fromCharCode(...new Uint8Array(buffer, 0, 4))).toBe('RIFF');
  expect(view.getUint32(24, true)).toBe(16000);
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getInt16(44, true)).toBe(-32768);
  expect(view.getInt16(48, true)).toBe(32767);
  expect(view.getInt16(50, true)).toBe(0);
  expect(() => pcmWav(new Float32Array(960001))).toThrow('60 seconds');
});

test('conversion decodes real source format, checks duration and closes context', async () => {
  const close = jest.fn().mockResolvedValue(undefined);
  let duration = 20;
  window.AudioContext = jest.fn(() => ({ close, decodeAudioData: jest.fn(async () => ({ duration })) }));
  window.OfflineAudioContext = jest.fn(() => ({ destination: {},
    createBufferSource: () => ({ connect: jest.fn(), start: jest.fn() }),
    startRendering: async () => ({ getChannelData: () => new Float32Array(320000) }) }));
  const result = await normalizeVoiceSample({ size: 100, arrayBuffer: async () => new ArrayBuffer(100) });
  expect(result.type).toBe('audio/wav');
  expect(result.size).toBe(640044);
  duration = 19;
  await expect(normalizeVoiceSample({ size: 100, arrayBuffer: async () => new ArrayBuffer(100) })).rejects.toThrow('20–60');
  expect(close).toHaveBeenCalledTimes(2);
  await expect(normalizeVoiceSample({ size: 11 * 1024 * 1024 })).rejects.toThrow('10MB');
});
