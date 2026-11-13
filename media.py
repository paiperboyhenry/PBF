"""Image/video handling. Everything uploaded is validated by content, re-encoded and given a random name."""
from __future__ import annotations

import secrets
from io import BytesIO
from pathlib import Path

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename

Image.MAX_IMAGE_PIXELS = 90_000_000  # decompression-bomb guard
MB = 1024 * 1024
WIDTHS = (640, 1280, 1920)
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "MPO", "AVIF"}
ATTACH_IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "MPO": "jpg"}
MIME = {"webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "mp4": "video/mp4", "webm": "video/webm", "pdf": "application/pdf"}


class MediaError(ValueError):
    """Raised with a message that is safe to show to the person uploading."""


def public_root() -> Path:
    return Path(current_app.config["PUBLIC_MEDIA_DIR"])


def private_root() -> Path:
    return Path(current_app.config["PRIVATE_DIR"])


def _read_limited(fs, limit: int, label: str) -> bytes:
    data = fs.stream.read(limit + 1)
    if not data:
        raise MediaError(f"{label} is empty.")
    if len(data) > limit:
        raise MediaError(f"{label} is larger than {limit // MB} MB.")
    return data


def _open_image(data: bytes, label: str) -> Image.Image:
    try:
        Image.open(BytesIO(data)).verify()
        img = Image.open(BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise MediaError(f"{label} isn't a valid image. Use JPEG, PNG or WebP.") from None
    return img


def save_image(fs, folder: str, *, og: bool = False) -> dict:
    """Validate, strip metadata, resize and store as WebP variants. Returns DB-ready metadata."""
    label = secure_filename(getattr(fs, "filename", "") or "") or "The image"
    data = _read_limited(fs, current_app.config["MAX_IMAGE_MB"] * MB, label)
    img = _open_image(data, label)
    if img.format not in IMAGE_FORMATS:
        raise MediaError(f"{label} isn't a supported image type. Use JPEG, PNG or WebP.")
    try:
        img.seek(0)
    except EOFError:
        pass
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")

    ow, oh = img.size
    widths = sorted({w for w in WIDTHS if w < ow} | {min(ow, WIDTHS[-1])})
    token = secrets.token_hex(8)
    key = f"{folder}/{token}"
    dest = public_root() / folder
    dest.mkdir(parents=True, exist_ok=True)
    for w in widths:
        h = max(1, round(oh * w / ow))
        frame = img if w == ow else img.resize((w, h), Image.LANCZOS)
        frame.save(dest / f"{token}-{w}.webp", "WEBP", quality=82, method=4)
    if og:
        fitted = ImageOps.fit(img.convert("RGB"), (1200, 630), method=Image.LANCZOS)
        fitted.save(dest / f"{token}-og.jpg", "JPEG", quality=86, optimize=True)
    top = widths[-1]
    return {"path": key, "width": top, "height": max(1, round(oh * top / ow)), "variants": widths}


def delete_image(key: str, variants: list[int]) -> None:
    base = public_root() / key
    for w in variants:
        Path(f"{base}-{w}.webp").unlink(missing_ok=True)
    Path(f"{base}-og.jpg").unlink(missing_ok=True)


def save_video(fs, folder: str) -> str:
    """Accept MP4 or WebM only (checked by file signature) and stream to disk with a size cap."""
    limit = current_app.config["MAX_VIDEO_MB"] * MB
    label = secure_filename(getattr(fs, "filename", "") or "") or "The video"
    head = fs.stream.read(16)
    if head[4:8] == b"ftyp":
        ext = "mp4"
    elif head[:4] == b"\x1a\x45\xdf\xa3":
        ext = "webm"
    else:
        raise MediaError(f"{label} must be an MP4 (H.264) or WebM video.")
    fs.stream.seek(0)
    dest_dir = public_root() / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}.{ext}"
    dest = dest_dir / name
    total = 0
    with open(dest, "wb") as out:
        while chunk := fs.stream.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise MediaError(f"{label} is larger than {limit // MB} MB. Upload a smaller file or paste a YouTube/Vimeo link.")
            out.write(chunk)
    if total == 0:
        dest.unlink(missing_ok=True)
        raise MediaError(f"{label} is empty.")
    return f"{folder}/{name}"


def delete_public_file(key: str) -> None:
    (public_root() / key).unlink(missing_ok=True)


def save_attachment(fs, enquiry_id: int) -> dict:
    """Enquiry attachments: images and PDFs only, stored outside the public web root."""
    cfg = current_app.config
    label = secure_filename(getattr(fs, "filename", "") or "") or "attachment"
    data = _read_limited(fs, cfg["MAX_ATTACHMENT_MB"] * MB, label)
    if data.startswith(b"%PDF-"):
        ext = "pdf"
    else:
        img = _open_image(data, label)
        ext = ATTACH_IMAGE_FORMATS.get(img.format or "")
        if not ext:
            raise MediaError(f"{label} must be a JPEG, PNG, WebP or PDF file.")
    folder = private_root() / "enquiries" / str(enquiry_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(12)}.{ext}"
    (folder / stored).write_bytes(data)
    return {"original_name": label[:120], "stored_name": stored, "mime": MIME[ext], "size": len(data)}


def attachment_path(enquiry_id: int, stored_name: str) -> Path | None:
    base = (private_root() / "enquiries" / str(int(enquiry_id))).resolve()
    path = (base / Path(stored_name).name).resolve()
    return path if path.parent == base and path.is_file() else None


def delete_enquiry_files(enquiry_id: int) -> None:
    import shutil
    shutil.rmtree(private_root() / "enquiries" / str(int(enquiry_id)), ignore_errors=True)
