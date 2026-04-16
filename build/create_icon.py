"""
build/create_icon.py  –  Generate a simple icon.ico for the dbcdiff exe.
Requires: pip install pillow
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def create_icon() -> None:
    out = Path(__file__).parent / "icon.ico"

    if not HAS_PIL:
        # Fallback: write a minimal 1-pixel ICO (16×16 blank icon)
        # so the build still works without Pillow.
        _write_minimal_ico(out)
        print(f"Pillow not installed – wrote minimal placeholder icon to {out}")
        return

    sizes = [256, 128, 64, 48, 32, 16]
    imgs = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background rounded rect (dark GitHub tone)
        _draw_rounded_rect(draw, size, bg=(13, 17, 23, 255), radius=int(size * 0.20))

        # Blue accent circle
        margin = int(size * 0.12)
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(31, 111, 235, 200),
        )

        # Letter "D" in white
        font_size = int(size * 0.48)
        try:
            font = ImageFont.truetype("segoeui.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        bbox = font.getbbox("D")
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) // 2 - bbox[0]
        ty = (size - th) // 2 - bbox[1]
        draw.text((tx, ty), "D", font=font, fill=(255, 255, 255, 255))

        imgs.append(img)

    imgs[0].save(out, format="ICO", append_images=imgs[1:], sizes=[(s, s) for s in sizes])
    print(f"Icon written to {out} ({', '.join(str(s) for s in sizes)} px)")


def _draw_rounded_rect(draw, size, bg, radius):
    x0, y0, x1, y1 = 0, 0, size - 1, size - 1
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=bg)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=bg)
    draw.pieslice([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=bg)
    draw.pieslice([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=bg)
    draw.pieslice([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=bg)
    draw.pieslice([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=bg)


def _write_minimal_ico(out: Path) -> None:
    """Write the smallest valid ICO (1×1 transparent pixel)."""
    # ICO header + 1 image entry + BITMAPINFOHEADER + 4 bytes pixel data
    ico = bytes([
        0, 0,        # reserved
        1, 0,        # ICO type
        1, 0,        # 1 image
        # ICONDIRENTRY
        1, 1,        # width=1 height=1
        0, 0,        # colours, reserved
        1, 0, 1, 0,  # planes, bit count
        40 + 8, 0, 0, 0,  # size of image data
        22, 0, 0, 0,  # offset to image data
        # BITMAPINFOHEADER (40 bytes)
        40, 0, 0, 0,  # header size
        1, 0, 0, 0,   # width
        2, 0, 0, 0,   # height (×2 for ICO)
        1, 0,         # planes
        32, 0,        # bit count
        0, 0, 0, 0,   # compression
        0, 0, 0, 0,   # image size
        0, 0, 0, 0,   # X pels/metre
        0, 0, 0, 0,   # Y pels/metre
        0, 0, 0, 0,   # colours used
        0, 0, 0, 0,   # colours important
        # XOR pixel (BGRA transparent)
        0, 0, 0, 0,
        # AND mask (1 byte + 3 pad)
        0, 0, 0, 0,
    ])
    out.write_bytes(ico)


if __name__ == "__main__":
    create_icon()
