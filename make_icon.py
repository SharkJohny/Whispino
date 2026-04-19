"""Generate icon.icns (a minimal microphone glyph on a red rounded square)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from AppKit import (
    NSBezierPath,
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSCalibratedRGBColorSpace,
    NSColor,
    NSGradient,
    NSGraphicsContext,
)
from Foundation import NSMakeRect

# iconutil expects this exact set of PNGs inside <name>.iconset/
ICONSET_FILES = [
    (16,   "icon_16x16.png"),
    (32,   "icon_16x16@2x.png"),
    (32,   "icon_32x32.png"),
    (64,   "icon_32x32@2x.png"),
    (128,  "icon_128x128.png"),
    (256,  "icon_128x128@2x.png"),
    (256,  "icon_256x256.png"),
    (512,  "icon_256x256@2x.png"),
    (512,  "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]


def _draw_icon(size: int) -> NSBitmapImageRep:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, size, size, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0
    )
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    # Rounded background with subtle top-to-bottom gradient
    corner = size * 0.22
    bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(0, 0, size, size), corner, corner
    )
    top = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.00, 0.42, 0.42, 1.0)
    bot = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.82, 0.18, 0.30, 1.0)
    NSGradient.alloc().initWithStartingColor_endingColor_(top, bot) \
        .drawInBezierPath_angle_(bg, 270.0)

    # Microphone drawn as three white shapes
    NSColor.whiteColor().set()

    body_w = size * 0.28
    body_h = size * 0.42
    body_x = (size - body_w) / 2
    body_y = size * 0.34
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(body_x, body_y, body_w, body_h),
        body_w / 2, body_w / 2,
    ).fill()

    stem_w = size * 0.045
    stem_h = size * 0.10
    NSBezierPath.bezierPathWithRect_(
        NSMakeRect((size - stem_w) / 2, size * 0.22, stem_w, stem_h),
    ).fill()

    base_w = size * 0.32
    base_h = size * 0.045
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect((size - base_w) / 2, size * 0.18, base_w, base_h),
        base_h / 2, base_h / 2,
    ).fill()

    NSGraphicsContext.restoreGraphicsState()
    return rep


def _write_png(rep: NSBitmapImageRep, path: str) -> None:
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, None)
    if not data.writeToFile_atomically_(path, True):
        raise RuntimeError(f"Failed to write {path}")


def build(output_icns: str) -> None:
    workdir = os.path.join(os.path.dirname(output_icns) or ".", "icon.iconset")
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)

    # Cache reps per size to avoid re-rendering for @2x duplicates
    cache: dict[int, NSBitmapImageRep] = {}
    for size, filename in ICONSET_FILES:
        if size not in cache:
            cache[size] = _draw_icon(size)
        _write_png(cache[size], os.path.join(workdir, filename))

    subprocess.run(
        ["iconutil", "-c", "icns", workdir, "-o", output_icns],
        check=True,
    )
    shutil.rmtree(workdir)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.icns"
    build(out)
    print(f"Wrote {out}")
