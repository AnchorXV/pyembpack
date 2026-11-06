import os
import re
import shutil
from pathlib import Path


def sanitize_filename(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.lstrip(". ")
    return name if name else "_unnamed"


def backup_file(path: Path, dry_run: bool = False) -> Path:
    if not path.exists():
        return path

    base = Path(str(path) + ".bak")
    if dry_run:
        return base

    existing = []
    if base.exists():
        existing.append(1)
    n = 2
    while Path(f"{base}.{n}").exists():
        existing.append(n)
        n += 1

    for slot in sorted(existing, reverse=True):
        src = base if slot == 1 else Path(f"{base}.{slot}")
        dest = Path(f"{base}.{slot + 1}")
        src.rename(dest)

    shutil.copy2(path, base)
    return base