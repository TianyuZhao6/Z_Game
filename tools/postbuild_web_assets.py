from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_WEB = ROOT / "build" / "web"


def copy_tree_subset(src_dir: Path, dst_dir: Path, patterns: tuple[str, ...]) -> list[Path]:
    copied: list[Path] = []
    if not src_dir.exists():
        return copied
    dst_dir.mkdir(parents=True, exist_ok=True)
    for pattern in patterns:
        for src in src_dir.glob(pattern):
            if not src.is_file():
                continue
            dst = dst_dir / src.name
            shutil.copy2(src, dst)
            copied.append(dst)
    return copied


def main() -> None:
    copied = []
    copied.extend(copy_tree_subset(ROOT / "assets" / "music", BUILD_WEB / "assets" / "music", ("*.ogg",)))
    copied.extend(copy_tree_subset(ROOT / "assets" / "Effect", BUILD_WEB / "assets" / "Effect", ("*.ogg",)))
    if not copied:
        print("no web assets copied")
        return
    print(f"copied {len(copied)} web audio assets")
    for path in copied:
        print(path.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    main()
