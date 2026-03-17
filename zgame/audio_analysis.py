from __future__ import annotations

import math
import os

import pygame

from zgame.browser import IS_WEB
from zgame.paths import SAVE_DIR

try:
    import numpy as np
except Exception:
    np = None

try:
    import librosa
except Exception:
    librosa = None


class AudioAnalyzer:
    """
    Analyze desktop audio with librosa while keeping a lightweight browser fallback.
    """

    def __init__(self):
        self.spectrogram = None
        self.frequencies_index_ratio = 0
        self.time_index_ratio = 0
        self.duration = 0.0
        self.loaded = False
        self._fallback_mode = False

    def _get_cache_path(self, filename):
        try:
            name = os.path.basename(filename).lower()
            if "intro_v0" not in name:
                return None
            return os.path.join(SAVE_DIR, "audio_analysis_intro_v0.npz")
        except Exception:
            return None

    def _load_from_cache(self, cache_path):
        try:
            if np is None:
                return False
            if not cache_path or not os.path.exists(cache_path):
                return False
            data = np.load(cache_path)
            self.spectrogram = data["spectrogram"]
            self.time_index_ratio = float(data["time_index_ratio"])
            self.frequencies_index_ratio = float(data["frequencies_index_ratio"])
            self.duration = float(data["duration"])
            self.loaded = True
            print(f"[AudioAnalyzer] Loaded from cache: {cache_path}")
            return True
        except Exception as e:
            print(f"[AudioAnalyzer] Cache load failed: {e}")
            return False

    def _save_to_cache(self, cache_path):
        try:
            if np is None:
                return False
            if not cache_path or self.spectrogram is None:
                return False
            np.savez_compressed(
                cache_path,
                spectrogram=self.spectrogram,
                time_index_ratio=self.time_index_ratio,
                frequencies_index_ratio=self.frequencies_index_ratio,
                duration=self.duration,
            )
            print(f"[AudioAnalyzer] Saved to cache: {cache_path}")
            return True
        except Exception as e:
            print(f"[AudioAnalyzer] Cache save failed: {e}")
            return False

    def load(self, filename):
        if not filename or not os.path.exists(filename):
            self.loaded = False
            self._fallback_mode = True
            return
        if IS_WEB or librosa is None or np is None:
            self.loaded = False
            self.duration = 0.0
            self._fallback_mode = True
            return

        cache_path = self._get_cache_path(filename)
        if cache_path and self._load_from_cache(cache_path):
            self._fallback_mode = False
            return

        try:
            print(f"[AudioAnalyzer] Analyzing {filename} (this may take a moment)...")
            time_series, sample_rate = librosa.load(filename)
            stft = np.abs(librosa.stft(time_series, hop_length=512, n_fft=2048 * 2))
            self.spectrogram = librosa.amplitude_to_db(stft, ref=np.max)

            frequencies = librosa.core.fft_frequencies(n_fft=2048 * 2)
            times = librosa.core.frames_to_time(
                np.arange(self.spectrogram.shape[1]),
                sr=sample_rate,
                hop_length=512,
                n_fft=2048 * 2,
            )

            self.time_index_ratio = len(times) / times[-1] if len(times) > 0 else 0
            self.frequencies_index_ratio = len(frequencies) / frequencies[-1] if len(frequencies) > 0 else 0
            self.duration = float(times[-1]) if len(times) > 0 else 0.0
            self.loaded = True
            self._fallback_mode = False
            print(f"[AudioAnalyzer] Analysis complete for {filename}")

            if cache_path:
                self._save_to_cache(cache_path)
        except Exception as e:
            print(f"[AudioAnalyzer] Failed to analyze {filename}: {e}")
            self.loaded = False
            self.duration = 0.0
            self._fallback_mode = True

    def get_decibel(self, target_time, freq):
        if self._fallback_mode:
            return -50.0 + 18.0 * math.sin(float(target_time) * 6.0 + float(freq) * 0.012)
        if not self.loaded or self.spectrogram is None:
            return -80

        if self.duration > 0:
            target_time = target_time % self.duration
        if target_time < 0:
            target_time = 0

        t_idx = int(target_time * self.time_index_ratio)
        f_idx = int(freq * self.frequencies_index_ratio)

        if t_idx < 0:
            t_idx = 0
        if t_idx >= self.spectrogram.shape[1]:
            t_idx = self.spectrogram.shape[1] - 1
        if f_idx >= self.spectrogram.shape[0]:
            f_idx = self.spectrogram.shape[0] - 1

        return self.spectrogram[f_idx][t_idx]


class NeuroMusicVisualizer:
    """
    Real-time frequency visualizer with a browser-safe fallback path.
    """

    def __init__(self):
        self.analyzer = AudioAnalyzer()
        self.bars = []
        self.radius = 120
        self.min_radius = 120
        self.max_radius = 140
        self.radius_vel = 0

        self.circle_color = (6, 10, 16)
        self.poly_color = [70, 230, 255]
        self.poly_color_default = [70, 230, 255]
        self.poly_color_bass = [180, 100, 255]

        if IS_WEB:
            self.freq_groups = [
                {"start": 50, "stop": 100, "count": 6},
                {"start": 120, "stop": 250, "count": 12},
                {"start": 251, "stop": 2000, "count": 18},
                {"start": 2001, "stop": 6000, "count": 8},
            ]
        else:
            self.freq_groups = [
                {"start": 50, "stop": 100, "count": 10},
                {"start": 120, "stop": 250, "count": 25},
                {"start": 251, "stop": 2000, "count": 40},
                {"start": 2001, "stop": 6000, "count": 15},
            ]

        self._init_bars()

    def _init_bars(self):
        self.bars = []
        total_bars = sum(group["count"] for group in self.freq_groups)
        angle_step = 360 / total_bars
        current_angle = 0

        for group in self.freq_groups:
            step = (group["stop"] - group["start"]) / group["count"]
            rng = group["start"]

            for _ in range(group["count"]):
                if np is not None:
                    freq_rng = np.arange(rng, rng + step + 1)
                else:
                    freq_rng = list(range(int(rng), int(rng + step) + 1))
                self.bars.append(
                    {
                        "freq_rng": freq_rng,
                        "angle": current_angle,
                        "val": 0.0,
                        "x": 0,
                        "y": 0,
                    }
                )
                rng += step
                current_angle += angle_step

    def load_music(self, path):
        if path:
            self.analyzer.load(path)

    def update(self, dt, music_pos_seconds):
        if not self.analyzer.loaded and not self.analyzer._fallback_mode:
            self.radius += (self.min_radius - self.radius) * min(1.0, 6.0 * dt)
            self.radius_vel *= 0.85
            for channel in range(3):
                self.poly_color[channel] += (
                    self.poly_color_default[channel] - self.poly_color[channel]
                ) * 4 * dt
            for bar in self.bars:
                bar["val"] += (0.0 - bar["val"]) * min(1.0, 10.0 * dt)
            return

        if self.analyzer.duration > 0:
            music_pos_seconds = music_pos_seconds % self.analyzer.duration
        elif music_pos_seconds < 0:
            music_pos_seconds = 0.0

        avg_bass = 0
        bass_count = 0

        for index, bar in enumerate(self.bars):
            db_sum = 0
            for freq in bar["freq_rng"]:
                db_sum += self.analyzer.get_decibel(music_pos_seconds, freq)
            avg_db = db_sum / len(bar["freq_rng"])
            val = max(0.0, (avg_db + 80) / 80.0)
            target = val * 80
            bar["val"] += (target - bar["val"]) * 15 * dt

            if index < self.freq_groups[0]["count"]:
                avg_bass += val
                bass_count += 1

        if bass_count > 0:
            avg_bass /= bass_count

        bass_trigger = 0.65
        if avg_bass > bass_trigger:
            target_r = self.max_radius + (avg_bass - bass_trigger) * 60
            self.radius_vel = (target_r - self.radius) * 10
            for channel in range(3):
                self.poly_color[channel] += (
                    self.poly_color_bass[channel] - self.poly_color[channel]
                ) * 5 * dt
        else:
            self.radius_vel += (self.min_radius - self.radius) * 8 * dt
            for channel in range(3):
                self.poly_color[channel] += (
                    self.poly_color_default[channel] - self.poly_color[channel]
                ) * 5 * dt

        self.radius += self.radius_vel * dt
        self.radius_vel *= 0.9

    def draw(self, screen, center_x, center_y):
        if not self.analyzer.loaded and not self.analyzer._fallback_mode:
            pygame.draw.circle(screen, self.circle_color, (center_x, center_y), int(self.min_radius), 2)
            return

        poly_points = []
        for bar in self.bars:
            radius = self.radius + bar["val"]
            rad = math.radians(bar["angle"] - 90)
            x = center_x + math.cos(rad) * radius
            y = center_y + math.sin(rad) * radius
            poly_points.append((int(round(x)), int(round(y))))

        if len(poly_points) > 2:
            poly_col = tuple(max(0, min(255, int(round(channel)))) for channel in self.poly_color)
            circle_col = tuple(max(0, min(255, int(round(channel)))) for channel in self.circle_color)
            pygame.draw.polygon(screen, circle_col, poly_points)
            pygame.draw.polygon(screen, poly_col, poly_points, 3)

        pygame.draw.circle(screen, (30, 40, 50), (center_x, center_y), int(self.radius * 0.8), 1)
