"""Select a reproducible positive-only IKAR subset from PRIVATE local media.

IKAR: Intelligent Kinetic Activity Recognition - Fall Detection Dataset,
Opyrchał et al. (2026), CC BY 4.0, DOI:10.58032/AGH/A1NZPE.
Videos are genuine recordings of volunteers staging falls on mats, NOT accidents.
This script never downloads assets, opens frames, or copies video into Git.
"""
import argparse
import json
from pathlib import Path

CATEGORIES = ("blackouts", "faintings", "slips", "trips")
DOI = "https://doi.org/10.58032/AGH/A1NZPE"
DATASET_CITATION = (
    "IKAR v1, Opyrchal, Burliga, Zielinska, Zajac, Potwora, "
    "Jagoda, Mika, Kubala (2026), CC BY 4.0, " + DOI
)


def build_manifest(root: Path, *, samples_per_category: int = 2) -> dict:
    """Generate a positive-only clip manifest; no event onsets are invented."""
    if not 1 <= samples_per_category <= 10:
        raise ValueError("samples_per_category must be 1..10")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Dataset root must be a directory")
    entries = []
    for category in CATEGORIES:
        path = root / category / "videos"
        if not path.is_dir():
            raise ValueError(f"Expected {category}/videos directory")
        videos = sorted(
            (video for video in path.glob("*.mp4") if video.is_file()
             and not video.is_symlink()
             and video.resolve().is_relative_to(root)),
            key=lambda video: video.name,
        )
        if len(videos) < samples_per_category:
            raise ValueError(
                f"Category {category} has {len(videos)} local MP4s, "
                f"requires {samples_per_category}"
            )
        for ordinal, video in enumerate(videos[:samples_per_category], start=1):
            entries.append({
                "id": f"ikar-{category}-{ordinal:02d}",
                "video": video.relative_to(root).as_posix(),
                "expected_fall": True,
                # Bounding boxes do not establish exact onset time.
                # Do not invent onset_ms from a video class label.
            })
    return {"version": 1, "permission_basis": DATASET_CITATION, "clips": entries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private IKAR positive-only manifest builder")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--samples-per-category", type=int, default=2)
    parser.add_argument("--acknowledge-cc-by", action="store_true",
                        help="Acknowledge CC BY 4.0 attribution and data handling")
    args = parser.parse_args(argv)
    if not args.acknowledge_cc_by:
        parser.error("Supply --acknowledge-cc-by after reviewing dataset license")
    try:
        manifest = build_manifest(args.dataset_root,
                                  samples_per_category=args.samples_per_category)
        out = args.dataset_root / "ikar_sample_manifest.json"
        # Never overwrite an existing private evaluation or its annotations.
        with out.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except (ValueError, OSError) as exc:
        parser.error(f"Cannot build IKAR subset: {exc}")
    print(f"Prepared {len(manifest['clips'])} positive-only clips; "
          "onsets unknown; negatives absent. Manifest is in the private dataset root.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
