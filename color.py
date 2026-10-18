"""Colour science for the spore-print matcher.

`srgb_to_lab` is the single conversion used by the seeder *and* the matcher, so a
persisted swatch centroid can never drift from a runtime query. Matches are
chosen with CIE76 delta-E over the stored Lab triples.
"""

from __future__ import annotations

import io
import math
from typing import Iterable

from PIL import Image, UnidentifiedImageError

# Paper/background rejection: a spore print is pigment on a pale sheet, so the
# near-white backdrop is dropped before picking the dominant colour. A photo
# that is *entirely* pale still classifies (it falls back to the overall mean,
# which is what the White class represents).
PAPER_LUMINANCE = 0.955
PAPER_CHROMA = 6.0
SAMPLE_SIDE = 96


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def hex_to_rgb(hex_colour: str) -> tuple[int, int, int]:
    value = hex_colour.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected a 6-digit hex colour, got {hex_colour!r}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: Iterable[float]) -> str:
    channels = [int(round(clamp(channel / 255.0) * 255)) for channel in rgb]
    return "#{:02X}{:02X}{:02X}".format(*channels)


def _srgb_channel_to_linear(channel: float) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _xyz_pivot(value: float) -> float:
    delta = 6.0 / 29.0
    return value ** (1.0 / 3.0) if value > delta**3 else value / (3 * delta**2) + 4.0 / 29.0


def srgb_to_xyz(r: float, g: float, b: float) -> tuple[float, float, float]:
    """sRGB (0-255) to CIE XYZ under a D65 illuminant."""
    lr, lg, lb = (_srgb_channel_to_linear(c) for c in (r, g, b))
    x = lr * 0.4124564 + lg * 0.3575761 + lb * 0.1804375
    y = lr * 0.2126729 + lg * 0.7151522 + lb * 0.0721750
    z = lr * 0.0193339 + lg * 0.1191920 + lb * 0.9503041
    return x * 100.0, y * 100.0, z * 100.0


def xyz_to_lab(x: float, y: float, z: float) -> tuple[float, float, float]:
    """XYZ (D65) to CIE Lab, with the D65 white point baked in."""
    white = (95.047, 100.0, 108.883)
    fx, fy, fz = (_xyz_pivot(v / w) for v, w in zip((x, y, z), white))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def srgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """The one conversion used by both the seeder and the matcher."""
    return xyz_to_lab(*srgb_to_xyz(r, g, b))


def hex_to_lab(hex_colour: str) -> tuple[float, float, float]:
    return srgb_to_lab(*hex_to_rgb(hex_colour))


def delta_e_cie76(lab_a: tuple[float, float, float], lab_b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab_a, lab_b)))


def confidence_from_delta_e(delta_e: float) -> float:
    """Map delta-E to a 0-100 confidence that decays smoothly with distance."""
    return round(100.0 * math.exp(-max(delta_e, 0.0) / 14.0), 1)


def _looks_like_paper(lab_l: float, lab_a: float, lab_b: float) -> bool:
    return lab_l / 100.0 >= PAPER_LUMINANCE and math.hypot(lab_a, lab_b) <= PAPER_CHROMA


def dominant_colour(image: Image.Image) -> tuple[int, int, int]:
    """Most populated colour bucket of the print, ignoring the pale paper backdrop.

    Deterministic: the image is resized with a stable filter, pixels are counted
    in 4-bit-per-channel buckets, and the winning bucket's pixels are averaged.
    """
    rgb_image = image.convert("RGB").resize((SAMPLE_SIDE, SAMPLE_SIDE), Image.Resampling.LANCZOS)
    raw = rgb_image.tobytes()
    pixels = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
    if not pixels:
        return (255, 255, 255)

    buckets: dict[tuple[int, int, int], list[float]] = {}
    totals = [0, 0, 0]
    pigment_pixels = 0
    for r, g, b in pixels:
        totals[0] += r
        totals[1] += g
        totals[2] += b
        lab_l, lab_a, lab_b = srgb_to_lab(r, g, b)
        if _looks_like_paper(lab_l, lab_a, lab_b):
            continue
        pigment_pixels += 1
        # Weight each pixel by pigment strength so the dense core of a deposit
        # outvotes the pale, half-tinted halo around it.
        strength = 1.0 + (100.0 - lab_l) / 100.0 + math.hypot(lab_a, lab_b) / 100.0
        key = (r >> 4, g >> 4, b >> 4)
        tally = buckets.setdefault(key, [0.0, 0.0, 0.0, 0.0])
        tally[0] += strength
        tally[1] += r * strength
        tally[2] += g * strength
        tally[3] += b * strength

    if pigment_pixels == 0 or not buckets:
        count = len(pixels)
        return (round(totals[0] / count), round(totals[1] / count), round(totals[2] / count))

    winner = max(buckets.values(), key=lambda t: t[0])
    return (round(winner[1] / winner[0]), round(winner[2] / winner[0]), round(winner[3] / winner[0]))


def decode_image_bytes(data: bytes) -> Image.Image:
    """Decode upload bytes, rejecting anything Pillow cannot read as an image.

    ``copy()`` forces the decoder to read the whole pixel buffer, so a truncated
    or malformed file raises here rather than half-way through colour sampling.
    The extension and the client-sent content type are never trusted; only the
    sniffed format that Pillow reports is.
    """
    try:
        with Image.open(io.BytesIO(data)) as probe:
            image_format = probe.format
            image = probe.copy()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("not a readable image") from exc
    if image_format not in {"JPEG", "PNG"}:
        raise ValueError(f"unsupported image format {image_format!r}")
    return image


def nearest_swatch(
    lab_query: tuple[float, float, float], swatches: Iterable
) -> tuple[object, float]:
    """Return (swatch_row, delta_e) for the closest persisted centroid."""
    best_row = None
    best_delta = float("inf")
    for row in swatches:
        delta = delta_e_cie76(lab_query, (row.lab_l, row.lab_a, row.lab_b))
        if delta < best_delta:
            best_row, best_delta = row, delta
    if best_row is None:
        raise LookupError("no swatch classes are seeded")
    return best_row, round(best_delta, 2)
