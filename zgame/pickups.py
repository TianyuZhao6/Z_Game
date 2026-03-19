"""Pickup support classes extracted from ZGame.py."""

from __future__ import annotations

import pygame


def install(game):
    class Spoil:
        """A coin-like pickup that pops up and bounces in place."""

        def __init__(self, x_px: float, y_px: float, value: int = 1):
            self.base_x = float(x_px)
            self.base_y = float(y_px)
            self.h = 0.0
            self.vh = float(game.COIN_POP_VY)
            self.value = int(value)
            self.r = 6
            self.rect = pygame.Rect(0, 0, self.r * 2, self.r * 2)
            self._update_rect()

        def _update_rect(self):
            cx = int(self.base_x)
            cy = int(self.base_y - self.h)
            self.rect.center = (cx, cy)

        def update(self, dt: float):
            self.vh += game.COIN_GRAVITY * dt
            self.h += self.vh * dt
            if self.h >= 0.0:
                self.h = 0.0
                if abs(self.vh) > game.COIN_MIN_BOUNCE:
                    self.vh = -self.vh * game.COIN_RESTITUTION
                else:
                    self.vh = 0.0
            self._update_rect()

    class HealPickup:
        """A small health potion pickup with the same bounce feel as coins."""

        def __init__(self, x_px: float, y_px: float, heal: int = game.HEAL_POTION_AMOUNT):
            self.base_x = float(x_px)
            self.base_y = float(y_px)
            self.h = 0.0
            self.vh = float(game.COIN_POP_VY)
            self.heal = int(heal)
            self.r = 7
            self.rect = pygame.Rect(0, 0, self.r * 2, self.r * 2)
            self._update_rect()

        def _update_rect(self):
            self.rect.center = (int(self.base_x), int(self.base_y - self.h))

        def update(self, dt: float):
            self.vh += game.COIN_GRAVITY * dt
            self.h += self.vh * dt
            if self.h >= 0.0:
                self.h = 0.0
                if abs(self.vh) > game.COIN_MIN_BOUNCE:
                    self.vh = -self.vh * game.COIN_RESTITUTION
                else:
                    self.vh = 0.0
            self._update_rect()

    game.__dict__.update({"Spoil": Spoil, "HealPickup": HealPickup})
    return Spoil, HealPickup
