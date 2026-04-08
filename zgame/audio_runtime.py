"""Audio runtime helpers extracted from ZGame.py."""

from __future__ import annotations

import os

import pygame


def install(game):
    class GameSound:
        """
        Background BGM loader/controller.
        It probes several likely paths so ZGAME.wav is found regardless of where ZGame.py runs from.
        """

        @staticmethod
        def _mixer_attempts() -> list[tuple[int, int]]:
            if getattr(game, "IS_WEB", False):
                # Prefer full-rate playback in browser so the original asset
                # is not audibly degraded by an aggressive downsample step.
                return [
                    (44100, 4096),
                    (44100, 2048),
                    (48000, 4096),
                    (22050, 2048),
                ]
            return [
                (44100, 512),
                (44100, 1024),
            ]

        @classmethod
        def _ensure_music_mixer(cls) -> bool:
            try:
                current = pygame.mixer.get_init()
            except Exception:
                current = None
            if current:
                try:
                    cur_freq = int(current[0])
                except Exception:
                    cur_freq = 0
                if (not getattr(game, "IS_WEB", False)) or cur_freq >= 44100:
                    return True
                try:
                    busy = bool(pygame.mixer.music.get_busy())
                except Exception:
                    busy = False
                if not busy:
                    try:
                        pygame.mixer.quit()
                    except Exception:
                        pass
                else:
                    return True
            last_error = None
            for mix_freq, mix_buffer in cls._mixer_attempts():
                try:
                    pygame.mixer.pre_init(mix_freq, -16, 2, mix_buffer)
                    pygame.mixer.init(mix_freq, -16, 2, mix_buffer)
                    actual = pygame.mixer.get_init()
                    print(f"[Audio] mixer ready: requested={mix_freq}/{mix_buffer} actual={actual}")
                    return True
                except Exception as e:
                    last_error = e
            print(f"[Audio] mixer init failed: {last_error}")
            return False

        @staticmethod
        def _browser_music_url(path: str) -> str:
            name = os.path.basename(str(path or ""))
            return f"assets/music/{name}" if name else ""

        def _open_native_web_audio(self) -> bool:
            try:
                url = self._browser_music_url(self.music_path)
                if not url:
                    return False
                ok = self._window_call("__zgame_bgm_open", url, self.volume)
                if bool(ok):
                    self._native_web_audio = True
                    return True
            except Exception as e:
                print(f"[Audio] html bgm open failed: {e}")
            return False

        def _window_call(self, fn_name: str, *args):
            try:
                import platform as web_platform

                window = getattr(web_platform, "window", None)
                fn = getattr(window, fn_name, None) if window is not None else None
                if fn is None:
                    return None
                return fn(*args)
            except Exception:
                return None

        def __init__(self, music_path: str = None, volume: float = 0.6):
            self.volume = max(0.0, min(1.0, float(volume)))
            self._ready = False
            self._native_web_audio = False
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
            if getattr(game, "IS_WEB", False) and bool(getattr(game, "WEB_NATIVE_BGM", False)) and self._open_native_web_audio():
                self._ready = True
                print(f"[Audio] Loaded HTML BGM: {self.music_path}")
                return
            try:
                if not self._ensure_music_mixer():
                    return
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
            if self._native_web_audio:
                self._window_call("__zgame_bgm_play", loops, fade_ms)
                return
            try:
                pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
            except Exception as e:
                print(f"[Audio] play failed: {e}")

        def stop(self, fade_ms: int = 300):
            if not self._ready:
                return
            if self._native_web_audio:
                self._window_call("__zgame_bgm_stop")
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
                if self._native_web_audio:
                    self._window_call("__zgame_bgm_pause")
                    return
                try:
                    pygame.mixer.music.pause()
                except Exception as e:
                    print(f"[Audio] pause failed: {e}")

        def resume(self):
            if self._ready:
                if self._native_web_audio:
                    self._window_call("__zgame_bgm_resume")
                    return
                try:
                    pygame.mixer.music.unpause()
                except Exception as e:
                    print(f"[Audio] resume failed: {e}")

        def set_volume(self, volume: float):
            self.volume = max(0.0, min(1.0, float(volume)))
            if self._ready:
                if self._native_web_audio:
                    self._window_call("__zgame_bgm_set_volume", self.volume)
                    return
                try:
                    pygame.mixer.music.set_volume(self.volume)
                except Exception as e:
                    print(f"[Audio] set_volume failed: {e}")

        def is_busy(self) -> bool:
            if not self._ready:
                return False
            if self._native_web_audio:
                return bool(self._window_call("__zgame_bgm_busy"))
            try:
                if not pygame.mixer.get_init():
                    return False
                return bool(pygame.mixer.music.get_busy())
            except Exception:
                return False

        def position_ms(self) -> int | None:
            if not self._ready:
                return None
            if self._native_web_audio:
                try:
                    if not bool(self._window_call("__zgame_bgm_busy")):
                        return None
                except Exception:
                    return None
                pos = self._window_call("__zgame_bgm_pos_ms")
                try:
                    pos_i = int(pos)
                except Exception:
                    return None
                return pos_i if pos_i >= 0 else None
            try:
                pos = pygame.mixer.music.get_pos()
                if pos is None or pos < 0:
                    return None
                return int(pos)
            except Exception:
                return None

    game.__dict__.update({"GameSound": GameSound})
    return GameSound
