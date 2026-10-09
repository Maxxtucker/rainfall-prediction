#!/usr/bin/env python3
"""Build the importable Spark --py-files archive (standard library only)."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
target = root / "dist" / "rainfall.zip"
target.parent.mkdir(exist_ok=True)
with ZipFile(target, "w", ZIP_DEFLATED) as out:
    for path in sorted((root / "src").rglob("*.py")):
        out.write(path, path.relative_to(root / "src"))
    for path in sorted((root / "tests").rglob("*.py")):
        out.write(path, path.relative_to(root))
print(target)
