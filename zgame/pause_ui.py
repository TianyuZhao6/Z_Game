"""Extracted UI flow from ZGame.py."""
from __future__ import annotations
import pygame
from zgame import runtime_state as rs

def pause_game_modal(game, screen, bg_surface, clock, time_left, player):
    """
    Show Pause (and Settings) while freezing the survival timer.
    Returns (choice, updated_time_left) where choice is:
    'continue' | 'restart' | 'home' | 'exit'
    """
    runtime = rs.runtime(game)
    runtime["_pause_player_ref"] = player
    while True:
        choice = game.show_pause_menu(screen, bg_surface)
        if choice == 'settings':
            game.show_settings_popup(screen, bg_surface)
            game.flush_events()
            continue
        break
    runtime["_time_left_runtime"] = time_left
    clock.tick(60)
    game.flush_events()
    return (choice, time_left)
