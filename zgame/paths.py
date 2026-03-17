from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_DIR = os.path.normpath(str(PROJECT_ROOT))
SAVE_DIR = os.path.join(BASE_DIR, "TEMP")
SAVE_FILE = os.path.join(SAVE_DIR, "savegame.json")
EXPORT_DIR = os.path.join(SAVE_DIR, "exports")

os.makedirs(SAVE_DIR, exist_ok=True)


def project_roots() -> list[str]:
    roots: list[str] = []
    for raw in (BASE_DIR, os.getcwd()):
        if not raw:
            continue
        norm = os.path.normpath(raw)
        if norm not in roots:
            roots.append(norm)
        nested = os.path.normpath(os.path.join(norm, "Z_Game"))
        if nested not in roots:
            roots.append(nested)
    return roots


def candidate_paths(*parts: str) -> list[str]:
    if not parts:
        return []
    rel = os.path.normpath(os.path.join(*parts))
    seen: set[str] = set()
    candidates: list[str] = []
    for root in project_roots():
        path = os.path.normpath(os.path.join(root, rel))
        if path not in seen:
            seen.add(path)
            candidates.append(path)
    return candidates


def asset_candidates(*parts: str) -> list[str]:
    return candidate_paths("assets", *parts)


def first_existing_path(candidates: list[str]) -> Optional[str]:
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def audio_path_variants(path: str) -> list[str]:
    if not path:
        return []
    root, ext = os.path.splitext(path)
    ext = ext.lower()
    if ext == ".ogg":
        return [path, f"{root}.wav"]
    if ext == ".wav":
        return [f"{root}.ogg", path]
    return [path]


def expand_audio_candidates(candidates: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        for path in audio_path_variants(candidate):
            if path and path not in seen:
                seen.add(path)
                out.append(path)
    return out

