"""Audio runtime helpers extracted from ZGame.py."""

from __future__ import annotations

import pygame


def install(game):
    class GameSound:
        """
        Background BGM loader/controller.
        It probes several likely paths so ZGAME.wav is found regardless of where ZGame.py runs from.
        """

        def __init__(self, music_path: str = None, volume: float = 0.6):
            self.volume = max(0.0, min(1.0, float(volume)))
            self._ready = False
            candidates = [
                *game._asset_candidates("music", "Intro_V0.wav"),
                *game._asset_candidates("music", "ZGAME.wav"),
            ]
            if music_path:
                candidates.insert(0, music_path)
            candidates = game._expand_audio_candidates(candidates)
            self.music_path = game._first_existing_path(candidates)
            if not self.music_path:
                print("[Audio] ZGAME.wav not found in expected locations.")
                return
            try:
                if not pygame.mixer.get_init():
                    if getattr(game, "IS_WEB", False):
                        # Browser audio is more stable with a larger buffer and
                        # lower sample rate than the desktop defaults.
                        mix_freq = 22050
                        mix_buffer = 2048
                    else:
                        mix_freq = 44100
                        mix_buffer = 512
                    pygame.mixer.pre_init(mix_freq, -16, 2, mix_buffer)
                    pygame.mixer.init(mix_freq, -16, 2, mix_buffer)
            except Exception as e:
                print(f"[Audio] mixer init failed: {e}")
                return
            try:
                pygame.mixer.music.load(self.music_path)
                pygame.mixer.music.set_volume(self.volume)
                self._ready = True
                print(f"[Audio] Loaded BGM: {self.music_path}")
            except Exception as e:
                print(f"[Audio] load music failed: {e} (path tried: {self.music_path})")

        def playBackGroundMusic(self, loops: int = -1, fade_ms: int = 500):
            if not self._ready:
                return
            try:
                pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
            except Exception as e:
                print(f"[Audio] play failed: {e}")

        def stop(self, fade_ms: int = 300):
            if not self._ready:
                return
            try:
                if fade_ms > 0:
                    pygame.mixer.music.fadeout(fade_ms)
                else:
                    pygame.mixer.music.stop()
            except Exception as e:
                print(f"[Audio] stop failed: {e}")

        def pause(self):
            if self._ready:
                try:
                    pygame.mixer.music.pause()
                except Exception as e:
                    print(f"[Audio] pause failed: {e}")

        def resume(self):
            if self._ready:
                try:
                    pygame.mixer.music.unpause()
                except Exception as e:
                    print(f"[Audio] resume failed: {e}")

        def set_volume(self, volume: float):
            self.volume = max(0.0, min(1.0, float(volume)))
            if self._ready:
                try:
                    pygame.mixer.music.set_volume(self.volume)
                except Exception as e:
                    print(f"[Audio] set_volume failed: {e}")

    game.__dict__.update({"GameSound": GameSound})
    return GameSound
