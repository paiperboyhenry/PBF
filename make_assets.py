"""Generates the site's textures, favicon and subsetted self-hosted fonts.

Run once from the project root:  python tools/make_assets.py
Textures are near-white luminance maps meant to be multiplied over the palette colours in CSS.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "pbf" / "static" / "img"
FONTS = ROOT / "pbf" / "static" / "fonts"
IMG.mkdir(parents=True, exist_ok=True)
FONTS.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(20261112)


def noise(n: int, sx: float, sy: float | None = None) -> np.ndarray:
    """Periodic (tileable) gaussian-filtered noise, zero mean, unit variance."""
    sy = sx if sy is None else sy
    f = np.fft.fft2(rng.standard_normal((n, n)))
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    g = np.exp(-2 * np.pi**2 * ((sx * fx) ** 2 + (sy * fy) ** 2))
    out = np.real(np.fft.ifft2(f * g))
    out -= out.mean()
    return out / out.std()


def save_lum(name: str, lum: np.ndarray, quality: int = 80) -> None:
    arr = np.clip(lum, 0, 1)
    img = Image.fromarray((arr * 255).astype(np.uint8), "L").convert("RGB")
    img.save(IMG / name, "WEBP", quality=quality, method=6)
    print("wrote", name, (IMG / name).stat().st_size // 1024, "KB")


def concrete(n=512):
    lum = 0.935 + 0.030 * noise(n, 90) + 0.020 * noise(n, 22) + 0.014 * noise(n, 5) + 0.010 * noise(n, 0.9)
    pits = noise(n, 1.1)
    lum -= np.where(pits > 2.5, 0.10, 0.0) * 0.8
    save_lum("tex-concrete.webp", lum)


def wall(n=512):
    streak = noise(n, 0.9, 70)  # vertical formwork streaks
    lum = 0.955 + 0.020 * streak + 0.018 * noise(n, 60) + 0.010 * noise(n, 6) + 0.006 * noise(n, 0.8)
    save_lum("tex-wall.webp", lum)


def plaster(n=512):
    lum = 0.90 + 0.060 * noise(n, 38) + 0.040 * noise(n, 11) + 0.020 * noise(n, 2.5) + 0.012 * noise(n, 0.8)
    save_lum("tex-plaster.webp", lum)


def grain(n=256):
    v = rng.integers(0, 256, (n, n), dtype=np.uint8)
    rgba = np.dstack([v, v, v, np.full((n, n), 30, dtype=np.uint8)])
    Image.fromarray(rgba, "RGBA").save(IMG / "grain.png", optimize=True)
    print("wrote grain.png", (IMG / "grain.png").stat().st_size // 1024, "KB")


def favicon():
    (IMG / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" fill="#161616"/>'
        '<path d="M17 13h17a11.5 11.5 0 0 1 0 23H25.5v15H17z" fill="#F2F1ED"/>'
        '<rect x="44" y="13" width="4.5" height="38" fill="#710014"/></svg>'
    )
    print("wrote favicon.svg")


FONT_SOURCES = {
    "pbf-display-black.woff": "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf",
    "pbf-display-extrabold.woff": "/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf",
    "pbf-sans-regular.woff": "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
    "pbf-sans-medium.woff": "/usr/share/fonts/opentype/inter/Inter-Medium.otf",
    "pbf-sans-semibold.woff": "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
    "pbf-serif-regular.woff": "/usr/share/fonts/truetype/baskerville/GFSBaskerville.otf",
}
UNICODES = (
    "U+0020-007E,U+00A0-00FF,U+2013,U+2014,U+2018,U+2019,U+201C,U+201D,U+2022,U+2026,"
    "U+20AC,U+2190-2193,U+2197,U+2116,U+00D7,U+2212"
)


def fonts():
    for out, src in FONT_SOURCES.items():
        if not Path(src).exists():
            print("missing font source", src, file=sys.stderr)
            continue
        subprocess.run(
            [sys.executable, "-m", "fontTools.subset", src, f"--unicodes={UNICODES}",
             "--layout-features=kern,liga,calt,case,tnum,ccmp,locl,mark,mkmk", "--flavor=woff",
             f"--output-file={FONTS / out}"],
            check=True,
        )
        print("wrote", out, (FONTS / out).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    concrete()
    wall()
    plaster()
    grain()
    favicon()
    fonts()
