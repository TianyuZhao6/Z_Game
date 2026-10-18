"""Lightweight hazard classes extracted from ZGame.py."""

from __future__ import annotations


def install(game):
    class AcidPool:
        def __init__(self, x, y, r, dps, slow_frac, life):
            self.x, self.y, self.r = x, y, r
            self.dps, self.slow_frac = dps, slow_frac
            self.t = life
            self.life0 = life

        def contains(self, px, py):
            return (px - self.x) ** 2 + (py - self.y) ** 2 <= self.r ** 2

    class TelegraphCircle:
        def __init__(self, x, y, r, life, kind="acid", payload=None, color=(255, 60, 60)):
            self.x, self.y, self.r = x, y, r
            self.t = life
            self.kind = kind
            self.payload = payload or {}
            self.color = color

    game.__dict__.update({"AcidPool": AcidPool, "TelegraphCircle": TelegraphCircle})
    return AcidPool, TelegraphCircle
