"""Generate curated royalty-free stock audio loops with precomputed waveforms."""
import asyncio
import json
import math
import os
import struct
import subprocess
import wave
from pathlib import Path

SAMPLE_RATE = 44100
DURATION = 30.0  # 30 seconds seamless loop

TRACKS = [
    {
        "id": "stock_lofi_chill",
        "filename": "lofi_chill_vibes.mp3",
        "title": "Lo-Fi Study Chill",
        "artist": "Unravler Studio (Royalty-Free)",
        "category": "chill",
        "bpm": 84,
        "mood": "Mellow & Relaxing",
        "tags": ["lo-fi", "chill", "study", "beats", "relax"],
        "type": "lofi",
    },
    {
        "id": "stock_upbeat_vlog",
        "filename": "upbeat_vlog_groove.mp3",
        "title": "Sunny Vlog Pop",
        "artist": "Unravler Studio (Royalty-Free)",
        "category": "upbeat",
        "bpm": 120,
        "mood": "Energetic & Fun",
        "tags": ["vlog", "upbeat", "happy", "travel", "lifestyle"],
        "type": "upbeat",
    },
    {
        "id": "stock_cinematic_ambient",
        "filename": "cinematic_ambient_drone.mp3",
        "title": "Cinematic Horizon",
        "artist": "Unravler Studio (Royalty-Free)",
        "category": "cinematic",
        "bpm": 70,
        "mood": "Inspiring & Epic",
        "tags": ["cinematic", "drone", "ambient", "film", "dramatic"],
        "type": "cinematic",
    },
    {
        "id": "stock_tech_minimal",
        "filename": "tech_minimal_pulse.mp3",
        "title": "Silicon Tech Flow",
        "artist": "Unravler Studio (Royalty-Free)",
        "category": "tech",
        "bpm": 115,
        "mood": "Modern & Sleek",
        "tags": ["tech", "minimal", "product", "innovation", "clean"],
        "type": "tech",
    },
    {
        "id": "stock_acoustic_warm",
        "filename": "acoustic_warm_horizon.mp3",
        "title": "Acoustic Warmth",
        "artist": "Unravler Studio (Royalty-Free)",
        "category": "acoustic",
        "bpm": 92,
        "mood": "Organic & Folk",
        "tags": ["acoustic", "guitar", "folk", "warm", "peaceful"],
        "type": "acoustic",
    },
    {
        "id": "stock_synthwave_drive",
        "filename": "synthwave_retro_drive.mp3",
        "title": "Neon Synthwave",
        "artist": "Unravler Studio (Royalty-Free)",
        "category": "electronic",
        "bpm": 110,
        "mood": "Retro & Driving",
        "tags": ["synthwave", "retro", "80s", "neon", "drive"],
        "type": "synthwave",
    },
]


def _envelope(t, attack, decay, sustain_level, release, note_dur):
    rel_t = t % note_dur
    if rel_t < attack:
        return rel_t / max(attack, 1e-6)
    elif rel_t < attack + decay:
        decay_pos = (rel_t - attack) / max(decay, 1e-6)
        return 1.0 - (1.0 - sustain_level) * decay_pos
    elif rel_t < note_dur - release:
        return sustain_level
    else:
        rel_pos = (rel_t - (note_dur - release)) / max(release, 1e-6)
        return max(0.0, sustain_level * (1.0 - rel_pos))


def generate_samples(track_type, total_seconds=DURATION, sr=SAMPLE_RATE):
    total_samples = int(total_seconds * sr)
    left_samples = [0.0] * total_samples
    right_samples = [0.0] * total_samples

    if track_type == "lofi":
        # Warm chords (Cmaj7 -> Am7 -> Dm7 -> G7)
        chords = [
            [261.63, 329.63, 392.00, 493.88],  # Cmaj7
            [220.00, 261.63, 329.63, 392.00],  # Am7
            [146.83, 220.00, 261.63, 349.23],  # Dm7
            [196.00, 246.94, 293.66, 349.23],  # G7
        ]
        chord_dur = total_seconds / len(chords)
        bpm = 84
        beat_dur = 60.0 / bpm

        for i in range(total_samples):
            t = i / sr
            # Chord
            chord_idx = int(t / chord_dur) % len(chords)
            chord = chords[chord_idx]
            chord_sig = 0.0
            for freq in chord:
                # Add slight vibrato and harmonics
                vibrato = 1.0 + 0.003 * math.sin(2 * math.pi * 4.5 * t)
                sig = math.sin(2 * math.pi * freq * vibrato * t)
                sig += 0.3 * math.sin(2 * math.pi * freq * 2 * vibrato * t)
                sig += 0.1 * math.sin(2 * math.pi * freq * 3 * vibrato * t)
                chord_sig += sig * 0.15

            # Low bass
            bass_freq = chord[0] / 2.0
            bass_sig = math.sin(2 * math.pi * bass_freq * t) * 0.25

            # Lo-Fi Drum rhythm (Kick on 1 & 3, Rim/Snare on 2 & 4)
            beat_phase = (t % beat_dur) / beat_dur
            beat_num = int((t / beat_dur) % 4)
            drum_sig = 0.0
            if beat_num in (0, 2):  # Soft Kick
                drum_sig += math.sin(2 * math.pi * 55 * math.exp(-beat_phase * 12) * t) * math.exp(-beat_phase * 8) * 0.35
            if beat_num in (1, 3):  # Soft Rim/Snare
                noise = math.sin(i * 1234.567) % 1.0 - 0.5
                drum_sig += noise * math.exp(-beat_phase * 15) * 0.15

            # Vinyl crackle warmth
            crackle = ((math.sin(i * 987.65) * 43758.5453) % 1.0 - 0.5) * 0.015

            mix = (chord_sig + bass_sig + drum_sig + crackle) * 0.7
            left_samples[i] = mix * 0.95
            right_samples[i] = mix * 1.05

    elif track_type == "upbeat":
        # Upbeat 120 bpm energetic progression
        bpm = 120
        beat_dur = 60.0 / bpm
        chords = [
            [329.63, 392.00, 493.88],  # Em
            [261.63, 329.63, 392.00],  # C
            [293.66, 369.99, 440.00],  # D
            [196.00, 246.94, 293.66],  # G
        ]
        chord_dur = beat_dur * 4

        for i in range(total_samples):
            t = i / sr
            chord_idx = int(t / chord_dur) % len(chords)
            chord = chords[chord_idx]

            # Acoustic rhythm strum
            strum_phase = (t % (beat_dur / 2)) / (beat_dur / 2)
            env = math.exp(-strum_phase * 6)
            strum_sig = 0.0
            for idx, freq in enumerate(chord):
                offset = idx * 0.015
                strum_sig += math.sin(2 * math.pi * freq * (t + offset)) * env * 0.18

            # Driving Kick & Hihat
            beat_phase = (t % beat_dur) / beat_dur
            kick_sig = math.sin(2 * math.pi * 65 * math.exp(-beat_phase * 15) * t) * math.exp(-beat_phase * 10) * 0.4
            hat_phase = (t % (beat_dur / 2)) / (beat_dur / 2)
            hat_sig = (((math.sin(i * 321.45) * 43758.5) % 1.0 - 0.5) * math.exp(-hat_phase * 20)) * 0.12

            # Bassline
            bass_freq = chord[0] / 2.0
            bass_sig = math.sin(2 * math.pi * bass_freq * t) * 0.22

            left_samples[i] = (strum_sig * 0.8 + kick_sig + hat_sig * 1.2 + bass_sig) * 0.75
            right_samples[i] = (strum_sig * 1.2 + kick_sig + hat_sig * 0.8 + bass_sig) * 0.75

    elif track_type == "cinematic":
        # Cinematic swelling pad & deep strings
        frequencies = [55.0, 110.0, 164.81, 220.0, 277.18, 329.63]
        for i in range(total_samples):
            t = i / sr
            lfo = (math.sin(2 * math.pi * 0.1 * t) + 1.0) * 0.5
            swell = math.sin(math.pi * (t % 15.0) / 15.0)

            sig_l = 0.0
            sig_r = 0.0
            for idx, freq in enumerate(frequencies):
                detune = 1.0 + (idx * 0.002 - 0.005)
                wave_val = math.sin(2 * math.pi * freq * detune * t)
                wave_val += 0.25 * math.sin(2 * math.pi * freq * 2 * detune * t)
                sig_l += wave_val * (0.12 + idx * 0.02)
                sig_r += math.sin(2 * math.pi * freq * (1.0 / detune) * t) * (0.12 + idx * 0.02)

            left_samples[i] = sig_l * (0.6 + 0.4 * swell) * 0.6
            right_samples[i] = sig_r * (0.6 + 0.4 * lfo) * 0.6

    elif track_type == "tech":
        # Minimal tech pulses & ping-pong plucks
        bpm = 115
        beat_dur = 60.0 / bpm
        notes = [220.0, 261.63, 293.66, 329.63, 392.0, 440.0]

        for i in range(total_samples):
            t = i / sr
            step_idx = int(t / (beat_dur / 4))
            note_freq = notes[step_idx % len(notes)]
            step_phase = (t % (beat_dur / 4)) / (beat_dur / 4)
            pluck = math.sin(2 * math.pi * note_freq * t) * math.exp(-step_phase * 12) * 0.25

            beat_phase = (t % beat_dur) / beat_dur
            click_kick = math.sin(2 * math.pi * 80 * math.exp(-beat_phase * 20) * t) * math.exp(-beat_phase * 15) * 0.35
            pan = math.sin(step_idx * 0.8)

            left_samples[i] = (pluck * (1.0 + pan) * 0.5 + click_kick) * 0.8
            right_samples[i] = (pluck * (1.0 - pan) * 0.5 + click_kick) * 0.8

    elif track_type == "acoustic":
        # Warm acoustic guitar chords (D - G - A)
        bpm = 92
        beat_dur = 60.0 / bpm
        chords = [
            [146.83, 220.0, 293.66, 369.99],  # D
            [196.0, 246.94, 293.66, 392.0],   # G
            [220.0, 277.18, 329.63, 440.0],  # A
            [196.0, 246.94, 293.66, 392.0],   # G
        ]
        bar_dur = beat_dur * 4

        for i in range(total_samples):
            t = i / sr
            chord_idx = int(t / bar_dur) % len(chords)
            chord = chords[chord_idx]

            arp_idx = int((t % beat_dur) / (beat_dur / 4)) % len(chord)
            arp_phase = (t % (beat_dur / 4)) / (beat_dur / 4)
            note = chord[arp_idx]
            pluck = math.sin(2 * math.pi * note * t) * math.exp(-arp_phase * 8) * 0.28
            pluck += math.sin(2 * math.pi * note * 2 * t) * math.exp(-arp_phase * 12) * 0.08

            bass = math.sin(2 * math.pi * chord[0] * t) * 0.18

            left_samples[i] = (pluck * 0.9 + bass) * 0.8
            right_samples[i] = (pluck * 1.1 + bass) * 0.8

    else:  # synthwave
        bpm = 110
        beat_dur = 60.0 / bpm
        bass_notes = [110.0, 110.0, 130.81, 146.83, 164.81, 146.83, 130.81, 110.0]

        for i in range(total_samples):
            t = i / sr
            step_idx = int(t / (beat_dur / 4))
            note = bass_notes[step_idx % len(bass_notes)]
            step_phase = (t % (beat_dur / 4)) / (beat_dur / 4)

            # Saw-like synth bass
            saw = 0.0
            for h in range(1, 6):
                saw += (math.sin(2 * math.pi * note * h * t) / h)
            saw *= math.exp(-step_phase * 6) * 0.22

            # Gated kick & snare
            beat_phase = (t % beat_dur) / beat_dur
            beat_num = int((t / beat_dur) % 2)
            drum = 0.0
            if beat_num == 0:
                drum = math.sin(2 * math.pi * 70 * math.exp(-beat_phase * 16) * t) * math.exp(-beat_phase * 12) * 0.4
            else:
                noise = (math.sin(i * 876.54) * 43758.5) % 1.0 - 0.5
                drum = noise * math.exp(-beat_phase * 10) * 0.22

            pad = math.sin(2 * math.pi * 220.0 * t) * 0.1 + math.sin(2 * math.pi * 329.63 * t) * 0.1

            left_samples[i] = (saw + drum + pad * 0.8) * 0.75
            right_samples[i] = (saw + drum + pad * 1.2) * 0.75

    return left_samples, right_samples


def write_wav(filename, left, right, sr=SAMPLE_RATE):
    with wave.open(filename, "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)
        frames = bytearray()
        for l, r in zip(left, right):
            # Clamp to [-1.0, 1.0] and convert to 16-bit PCM
            l_int = max(-32767, min(32767, int(l * 32767)))
            r_int = max(-32767, min(32767, int(r * 32767)))
            frames.extend(struct.pack("<hh", l_int, r_int))
        wav_file.writeframes(frames)


def compute_waveform_peaks(left, right, bar_count=64):
    total = len(left)
    chunk_size = total // bar_count
    peaks = []
    for b in range(bar_count):
        start = b * chunk_size
        end = start + chunk_size if b < bar_count - 1 else total
        sum_sq = 0.0
        count = end - start
        for i in range(start, end):
            val = (left[i] + right[i]) * 0.5
            sum_sq += val * val
        rms = math.sqrt(sum_sq / max(count, 1))
        peaks.append(round(rms, 4))
    # Normalize peaks between 0.05 and 1.0
    max_peak = max(peaks) if peaks and max(peaks) > 0 else 1.0
    return [round(max(0.08, min(1.0, p / max_peak)), 3) for p in peaks]


def main():
    backend_static = Path("static/stock_audio")
    frontend_public = Path("frontend/public/stock_audio")
    backend_static.mkdir(parents=True, exist_ok=True)
    frontend_public.mkdir(parents=True, exist_ok=True)

    catalog = []

    for item in TRACKS:
        print(f"Generating {item['title']} ({item['category']})...")
        left, right = generate_samples(item["type"], total_seconds=DURATION)
        peaks = compute_waveform_peaks(left, right, bar_count=64)

        wav_path = f"/tmp/{item['id']}.wav"
        mp3_filename = item["filename"]
        backend_mp3 = backend_static / mp3_filename
        frontend_mp3 = frontend_public / mp3_filename

        write_wav(wav_path, left, right)

        # Convert to high-quality MP3 with FFmpeg
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", wav_path,
                "-codec:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", str(SAMPLE_RATE),
                str(backend_mp3),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Copy to frontend public
        subprocess.run(["cp", str(backend_mp3), str(frontend_mp3)], check=True)
        if os.path.exists(wav_path):
            os.remove(wav_path)

        catalog_entry = {
            "media_id": item["id"],
            "title": item["title"],
            "artist": item["artist"],
            "category": item["category"],
            "mood": item["mood"],
            "bpm": item["bpm"],
            "tags": item["tags"],
            "duration_seconds": DURATION,
            "filename": mp3_filename,
            "media_url": f"/stock_audio/{mp3_filename}",
            "storage_key": f"stock_audio/{mp3_filename}",
            "waveform_peaks": peaks,
            "asset_kind": "audio",
            "mime_type": "audio/mpeg",
            "is_stock": True,
            "has_audio": True,
        }
        catalog.append(catalog_entry)

    # Save stock_audio.py module in api/data/
    Path("api/data").mkdir(parents=True, exist_ok=True)
    with open("api/data/stock_audio.py", "w") as f:
        f.write('"""Curated royalty-free stock audio library catalog."""\n\n')
        f.write(f"STOCK_AUDIO_CATALOG = {json.dumps(catalog, indent=4)}\n\n")
        f.write(
            "def get_stock_audio_by_id(media_id: str) -> dict | None:\n"
            "    for track in STOCK_AUDIO_CATALOG:\n"
            '        if track["media_id"] == media_id:\n'
            "            return dict(track)\n"
            "    return None\n"
        )

    # Also save stock_audio.json for frontend bundle convenience
    with open("frontend/src/data/stockAudio.json", "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"Successfully generated {len(catalog)} stock audio tracks and catalog module!")


if __name__ == "__main__":
    main()
