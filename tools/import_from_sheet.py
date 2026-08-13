"""Download employee photos from a Google Forms response spreadsheet.

Google Forms puts uploaded photos in Drive and records a link in the sheet, so
the exported .xlsx holds links rather than pictures. This script reads the
sheet, downloads each photo, and saves it into 01_inbox named after the
employee, which is the name the headshot tool then uses all the way through to
the website file.

    python tools/import_from_sheet.py "Employee Info with photo (Responses).xlsx"

Running it again only downloads people who are missing, so it is safe to re-run
whenever new staff fill in the form.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from wegro_headshot.manifest import slugify_text  # noqa: E402

# Header names are matched loosely, so the script survives columns being
# renamed or reordered in the form.
NAME_HINTS = ("full name", "name", "employee name")
ID_HINTS = ("employee id", "emp id", "id")
PHOTO_HINTS = ("photo", "photograph", "picture", "image")

DRIVE_ID = re.compile(r"(?:/d/|id=|/file/d/)([A-Za-z0-9_-]{20,})")

SIGNATURES = {
    b"\xff\xd8\xff": ".jpg",
    b"\x89PNG\r\n\x1a\n": ".png",
    b"GIF87a": ".gif",
    b"GIF89a": ".gif",
    b"BM": ".bmp",
}

HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm",
               b"hevs", b"mif1", b"msf1", b"avif"}

USER_AGENT = "Mozilla/5.0 (compatible; WeGroPhotoImporter/1.0)"


def find_column(headers: list[str], hints: tuple[str, ...]) -> int | None:
    """Best matching column for a set of header hints, longest hint first."""
    lowered = [str(h or "").strip().lower() for h in headers]
    for hint in sorted(hints, key=len, reverse=True):
        for index, header in enumerate(lowered):
            if hint in header:
                return index
    return None


def extract_drive_id(value: str) -> str | None:
    match = DRIVE_ID.search(str(value))
    return match.group(1) if match else None


def guess_extension(data: bytes) -> str | None:
    for signature, suffix in SIGNATURES.items():
        if data.startswith(signature):
            return suffix
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[4:8] == b"ftyp" and data[8:12] in HEIF_BRANDS:
        return ".heic"
    return None


def heic_to_jpeg(data: bytes) -> bytes:
    """Convert an iPhone HEIC photo to JPEG.

    Photos straight off an iPhone are HEIC, which most tools cannot read, so
    they are converted once here rather than being a problem later.
    """
    import io

    import pillow_heif
    from PIL import Image

    pillow_heif.register_heif_opener()
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def download(file_id: str, timeout: int = 60) -> tuple[bytes, str]:
    """Fetch one Drive file. Returns (data, extension)."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()

    extension = guess_extension(data)
    if extension is None:
        # Drive serves an HTML page instead of the file when it is not shared,
        # or when it wants a confirmation click.
        if data.lstrip()[:1] == b"<":
            raise RuntimeError(
                "Drive returned a web page instead of the picture. The file is "
                "probably not shared - open it in Drive and set sharing to "
                "'Anyone with the link'."
            )
        raise RuntimeError(
            f"The downloaded file is not a recognised image "
            f"(it starts with {data[:12]!r})."
        )

    if extension == ".heic":
        try:
            data = heic_to_jpeg(data)
            extension = ".jpg"
        except ImportError:
            raise RuntimeError(
                "This is an iPhone HEIC photo and pillow-heif is not "
                "installed. Run setup.bat again to add it."
            ) from None
        except Exception as exc:
            raise RuntimeError(f"The HEIC photo could not be converted: {exc}") from exc

    return data, extension


def read_rows(path: Path) -> tuple[list[str], list[tuple]]:
    try:
        import openpyxl
    except ImportError:
        raise SystemExit(
            "openpyxl is not installed. Run setup.bat again, or:\n"
            "  .venv\\Scripts\\python.exe -m pip install openpyxl"
        )

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    rows = [r for r in sheet.iter_rows(values_only=True) if any(v is not None for v in r)]
    if not rows:
        raise SystemExit(f"{path.name} appears to be empty.")
    return [str(h or "") for h in rows[0]], rows[1:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Download employee photos from a Google Forms spreadsheet "
                    "into 01_inbox."
    )
    parser.add_argument("spreadsheet", nargs="?",
                        default="Employee Info with photo (Responses).xlsx",
                        help="The .xlsx exported from Google Forms.")
    parser.add_argument("--out", default="01_inbox",
                        help="Folder to save into (default: 01_inbox).")
    parser.add_argument("--dry-run", action="store_true",
                        help="List what would be downloaded, download nothing.")
    parser.add_argument("--force", action="store_true",
                        help="Download again even if the photo is already there.")
    parser.add_argument("--with-id", action="store_true",
                        help="Put the employee ID in every file name.")
    args = parser.parse_args(argv)

    source = Path(args.spreadsheet)
    if not source.is_absolute():
        source = ROOT / source
    if not source.exists():
        raise SystemExit(f"Spreadsheet not found: {source}")

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    headers, rows = read_rows(source)
    name_col = find_column(headers, NAME_HINTS)
    photo_col = find_column(headers, PHOTO_HINTS)
    id_col = find_column(headers, ID_HINTS)

    if name_col is None or photo_col is None:
        raise SystemExit(
            "Could not find the name and photo columns.\n"
            f"  Headers seen: {headers}"
        )

    print(f"Reading  : {source.name}")
    print(f"Name from: '{headers[name_col]}'")
    print(f"Photo    : '{headers[photo_col]}'")
    print(f"Saving to: {out_dir}")
    print()

    # Work out every file name first, so duplicates can be told apart.
    planned: list[dict] = []
    slug_counts: dict[str, int] = {}
    for row in rows:
        name = str(row[name_col] or "").strip()
        if not name:
            continue
        slug = slugify_text(name)
        slug_counts[slug] = slug_counts.get(slug, 0) + 1
        planned.append({
            "name": name,
            "slug": slug,
            "employee_id": str(row[id_col] or "").strip() if id_col is not None else "",
            "link": str(row[photo_col] or "").strip(),
        })

    downloaded = skipped = failed = 0

    for entry in planned:
        slug = entry["slug"]
        # Two people with the same name would overwrite each other, so their
        # employee ID is added to keep them apart.
        if args.with_id or slug_counts[slug] > 1:
            suffix = slugify_text(entry["employee_id"]) if entry["employee_id"] else ""
            if suffix:
                slug = f"{slug}-{suffix}"

        existing = [p for p in out_dir.glob(f"{slug}.*") if p.suffix != ".txt"]
        if existing and not args.force:
            skipped += 1
            continue

        file_id = extract_drive_id(entry["link"])
        if not file_id:
            print(f"  [X] {entry['name']}: no Google Drive link in the sheet")
            failed += 1
            continue

        if args.dry_run:
            print(f"  [ ] would download {slug}  <- {entry['name']}")
            downloaded += 1
            continue

        try:
            data, extension = download(file_id)
        except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
            print(f"  [X] {entry['name']}: {exc}")
            failed += 1
            continue

        for stale in existing:
            stale.unlink()

        target = out_dir / f"{slug}{extension}"
        target.write_bytes(data)
        print(f"  [ok] {target.name:<34} {len(data) // 1024:>5} KB   {entry['name']}")
        downloaded += 1

    print()
    print(f"  downloaded : {downloaded}")
    print(f"  skipped    : {skipped}  (already there)")
    if failed:
        print(f"  failed     : {failed}")
    print()
    if downloaded and not args.dry_run:
        print("Now double-click run.bat to turn these into website photos.")

    return 1 if failed and not downloaded else 0


if __name__ == "__main__":
    raise SystemExit(main())
