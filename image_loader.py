"""Load an image from disk, dither it, and pack into ESC/POS raster bytes."""

from PIL import Image as PILImage


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
    img = img.convert("1", dither=PILImage.Dither.FLOYDSTEINBERG)
    # PIL "1" tobytes: leftmost pixel in MSB, 1=white. Invert so 1=black (ESC/POS).
    return bytes(b ^ 0xFF for b in img.tobytes())
