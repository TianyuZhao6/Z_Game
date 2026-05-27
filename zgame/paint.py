"""Ground-spike and paint support classes extracted from ZGame.py."""

from __future__ import annotations

import math
import random


def install(game):
    class GroundSpike:
        def __init__(self, x, y, damage, life, radius, level: int = 1):
            self.x = float(x)
            self.y = float(y)
            self.damage = float(damage)
            self.t = float(life)
            self.life0 = float(life)
            self.r = float(radius)
            self.level = int(max(1, level))

    class CuringPaintFootprint:
        def __init__(self, x, y, radius, life, level: int = 1, base_color: tuple[int, int, int] | None = None):
            self.x = float(x)
            self.y = float(y)
            self.r = float(radius)
            self.t = float(life)
            self.life0 = float(life)
            self.level = int(max(1, level))
            if base_color and len(base_color) >= 3:
                self.base_color = tuple(int(c) for c in base_color[:3])
            else:
                self.base_color = game.CURING_PAINT_FILL_COLOR
            count = max(8, int(game.CURING_PAINT_BLOB_POINTS))
            self._blob_noise = [random.uniform(0.82, 1.18) for _ in range(count)]
            self._blob_phase = [random.uniform(0.0, math.tau) for _ in range(count)]
            self._blob_rot = random.uniform(0.0, math.tau)
            self._static_cache = None
            self._static_t = None

        @property
        def intensity(self) -> float:
            if self.life0 <= 0.0:
                return 0.0
            return max(0.0, min(1.0, float(self.t) / float(self.life0)))

    class PaintTile:
        __slots__ = (
            "paint_owner",
            "paint_intensity",
            "paint_age",
            "paint_type",
            "paint_life0",
            "paint_color",
            "paint_radius",
            "_blob_noise",
            "_blob_phase",
            "_blob_rot",
            "_spark_phase",
            "_static_cache",
            "_visual_identity",
        )

        def __init__(self):
            self.paint_owner = 0
            self.paint_intensity = 0.0
            self.paint_age = 0.0
            self.paint_type = None
            self.paint_life0 = 0.0
            self.paint_color = None
            self.paint_radius = 0.0
            self._blob_noise = None
            self._blob_phase = None
            self._blob_rot = 0.0
            self._spark_phase = random.uniform(0.0, math.tau)
            self._static_cache = None
            self._visual_identity = None

        def _current_visual_identity(self):
            color = getattr(self, "paint_color", None)
            if isinstance(color, (tuple, list)) and len(color) >= 3:
                color = (int(color[0]), int(color[1]), int(color[2]))
            else:
                color = None
            radius = round(float(getattr(self, "paint_radius", 0.0) or 0.0), 1)
            return (int(getattr(self, "paint_owner", 0)), getattr(self, "paint_type", None), color, radius)

        def refresh_visuals(self, *, force: bool = False):
            identity = self._current_visual_identity()
            if (
                not force
                and self._visual_identity == identity
                and self._blob_noise is not None
                and self._blob_phase is not None
            ):
                return
            count = max(8, int(game.ENEMY_PAINT_BLOB_POINTS))
            self._blob_noise = [random.uniform(0.78, 1.20) for _ in range(count)]
            self._blob_phase = [random.uniform(0.0, math.tau) for _ in range(count)]
            self._blob_rot = random.uniform(0.0, math.tau)
            self._spark_phase = random.uniform(0.0, math.tau)
            self._static_cache = None
            self._visual_identity = identity

    game.__dict__.update(
        {
            "GroundSpike": GroundSpike,
            "CuringPaintFootprint": CuringPaintFootprint,
            "PaintTile": PaintTile,
        }
    )
    return GroundSpike, CuringPaintFootprint, PaintTile
