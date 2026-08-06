"""Load an image from disk, dither it, and pack into ESC/POS raster bytes."""

import numpy as np
from PIL import Image as PILImage, ImageFilter

DARK_CLUMP_KERNEL_SIZE = 16
DARK_CLUMP_THRESHOLD = 80
DARK_CLUMP_MIN_COVERAGE = 0.05
DARK_CLUMP_MAX_COVERAGE = 0.3
MAX_SHADOW_LIFT = 180

# 4x4 Bayer matrix, normalized to 0-1 range
_BAYER_4x4 = (
    np.array(
        [
            [0, 8, 2, 10],
            [12, 4, 14, 6],
            [3, 11, 1, 9],
            [15, 7, 13, 5],
        ],
        dtype=np.float32,
    )
    / 16.0
)


def _compute_shadow_lift(
    img: PILImage.Image,
    max_shadow_lift: int,
    kernel_size: int = DARK_CLUMP_KERNEL_SIZE,
    dark_threshold: int = DARK_CLUMP_THRESHOLD,
    min_coverage: float = DARK_CLUMP_MIN_COVERAGE,
    max_coverage: float = DARK_CLUMP_MAX_COVERAGE,
) -> int:
    """Determine shadow lift based on how much of the image has large dark clumps."""
    blurred = img.filter(ImageFilter.BoxBlur(kernel_size))
    pixels = np.array(blurred)
    dark_ratio = np.mean(pixels < dark_threshold)
    if dark_ratio <= min_coverage:
        return 0
    scale = min(1.0, (dark_ratio - min_coverage) / (max_coverage - min_coverage))
    return round(max_shadow_lift * scale)


def _lift_shadows(img: PILImage.Image, shadow_lift: int) -> PILImage.Image:
    """Raise dark values by shadow_lift, fading to zero boost at white."""
    if shadow_lift <= 0:
        return img
    lut = [min(255, x + round(shadow_lift * (1 - x / 255) ** 2)) for x in range(256)]
    return img.point(lut)


def _ordered_dither(img: PILImage.Image) -> PILImage.Image:
    """Apply 4x4 Bayer ordered dithering to a grayscale image."""
    pixels = np.array(img, dtype=np.float32) / 255.0
    h, w = pixels.shape
    threshold = np.tile(_BAYER_4x4, (h // 4 + 1, w // 4 + 1))[:h, :w]
    result = (pixels > threshold).astype(np.uint8) * 255
    return PILImage.fromarray(result, mode="L").convert("1")


def load_dithered(path: str, width_dots: int) -> bytes:
    """Return MSB-first packed raster bytes (1=black) at the given dot width."""
    if width_dots % 8 != 0:
        raise ValueError("width_dots must be a multiple of 8")
    img = PILImage.open(path).convert("RGBA")
    background = PILImage.new("RGBA", img.size, (255, 255, 255, 255))
    img = PILImage.alpha_composite(background, img).convert("L")
    aspect = img.height / img.width
    height = max(1, round(width_dots * aspect))
    img = img.resize((width_dots, height), PILImage.LANCZOS)
    lift = _compute_shadow_lift(img, MAX_SHADOW_LIFT)
    img = _lift_shadows(img, lift)
    img = _ordered_dither(img)
    # PIL "1" tobytes: leftmost pixel in MSB, 1=white. Invert so 1=black (ESC/POS).
    return bytes(b ^ 0xFF for b in img.tobytes())
