from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def optimize(
    src_dir: Path,
    dst_dir: Path,
    *,
    max_size: int = 1600,
    quality: int = 82,
    limit: int | None = None,
    skip_existing: bool = True,
) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)

    exts = {".jpg", ".jpeg", ".png", ".webp"}
    processed = 0
    for src in sorted(src_dir.iterdir()):
        if not src.is_file() or src.suffix.lower() not in exts:
            continue

        out_name = f"{src.stem}.webp"
        dst = dst_dir / out_name
        if skip_existing and dst.exists() and dst.stat().st_size > 0:
            continue

        with Image.open(src) as im:
            im = im.convert("RGB")

            im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            im.save(dst, format="WEBP", quality=quality, method=6)

        processed += 1
        if processed % 10 == 0:
            print(f"Processadas: {processed} (última: {src.name})")

        if limit is not None and processed >= limit:
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-size", type=int, default=1600)
    parser.add_argument("--quality", type=int, default=82)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-skip-existing", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    src_dir = project_root / "fotos_apartamentos"
    dst_dir = project_root / "fotos_apartamentos_web"

    optimize(
        src_dir,
        dst_dir,
        max_size=args.max_size,
        quality=args.quality,
        limit=args.limit,
        skip_existing=not args.no_skip_existing,
    )
    print(f"OK: fotos otimizadas em: {dst_dir}")
