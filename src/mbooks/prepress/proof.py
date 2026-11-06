"""Diagnostic proof generator for prepress book covers.

Renders deterministic, high-resolution dual-panel diagnostic proof images:
- Left panel: Full spread view with guidelines (Bleed, Trim, Spine Folds, Safe Boundaries).
- Right panel: High-magnification zoomed spine view with exact pixel gap callouts.
- Real-time PASS/FAIL preflight status banner.
- Comprehensive footer metrics detailing left/right fold clearances and safety buffers.

Zero external cloud dependencies (Pillow and NumPy only).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .centering import CenteringResult
from .crease import CreaseDetectionResult
from .specs import PrepressSpec


def _get_font(size: int = 14) -> ImageFont.ImageFont:
    """Load default font with size support across Pillow versions."""
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def generate_diagnostic_proof(
    spread_image: Image.Image,
    spec: PrepressSpec,
    centering: CenteringResult,
    crease: CreaseDetectionResult,
    output_path: Union[str, Path],
    dpi: int = 300,
) -> str:
    """Generate high-resolution composite diagnostic proof image.

    Args:
        spread_image: Book cover spread image (RGB, Grayscale, or CMYK).
        spec: PrepressSpec containing physical dimensions and publisher geometry.
        centering: CenteringResult containing optical center, clearances, and is_safe.
        crease: CreaseDetectionResult containing detected/assigned fold positions.
        output_path: Output image path (PNG or JPG).
        dpi: Target resolution DPI (default 300).

    Returns:
        Absolute string path to the generated proof image.
    """
    output_str = str(output_path)
    parent_dir = os.path.dirname(output_str)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # 1. Normalize image mode to RGB
    img = spread_image.convert("RGB")
    W, H = img.size

    # 2. Derive fold positions on the input spread image
    expected_w_px = int(round(spec.total_w_in * dpi))
    is_resized_spread = abs(W - expected_w_px) <= max(20, int(round(0.05 * expected_w_px)))

    if is_resized_spread:
        if spec.binding == "paperback":
            x_fold_left = int(round((spec.bleed_in + spec.trim_w_in) * dpi))
        else:
            board_w_in = (
                spec.total_w_in
                - spec.spine_w_in
                - 2.0 * spec.wrap_in
                - 2.0 * spec.hinge_in
            ) / 2.0
            x_fold_left = int(round((spec.wrap_in + board_w_in + spec.hinge_in) * dpi))
        spine_w_px = max(1, int(round(spec.spine_w_in * dpi)))
        x_fold_right = x_fold_left + spine_w_px
        bleed_px = int(round((spec.bleed_in if spec.binding == "paperback" else spec.wrap_in) * dpi))
    else:
        # Source mockup geometry from crease detection
        x_fold_left = crease.x_left
        x_fold_right = crease.x_right
        spine_w_px = max(1, x_fold_right - x_fold_left)
        bleed_px = max(10, int(round(W * (spec.bleed_in / max(0.1, spec.total_w_in)))))

    safe_margin_px = max(1.0, spec.spine_safe_margin_in * dpi if is_resized_spread else centering.safe_margin_px)

    # Safe margin boundary coordinates
    x_safe_left = x_fold_left + safe_margin_px
    x_safe_right = x_fold_right - safe_margin_px

    # 3. Build Full Spread Preview Panel (scaled to width ~1100 px)
    preview_w = min(1200, max(800, W))
    scale = preview_w / W
    preview_h = max(200, int(round(H * scale)))

    preview = img.resize((preview_w, preview_h), Image.Resampling.LANCZOS)
    draw_prev = ImageDraw.Draw(preview)

    # Bleed line (magenta)
    draw_prev.rectangle([(0, 0), (preview_w - 1, preview_h - 1)], outline=(255, 0, 128), width=2)

    # Trim box (cyan)
    trim_x0 = max(0, int(round(bleed_px * scale)))
    trim_y0 = max(0, int(round(bleed_px * scale)))
    trim_x1 = min(preview_w - 1, int(round((W - bleed_px) * scale)))
    trim_y1 = min(preview_h - 1, int(round((H - bleed_px) * scale)))
    draw_prev.rectangle([(trim_x0, trim_y0), (trim_x1, trim_y1)], outline=(0, 220, 255), width=2)

    # Fold lines (orange)
    f_l = int(round(x_fold_left * scale))
    f_r = int(round(x_fold_right * scale))
    draw_prev.line([(f_l, 0), (f_l, preview_h)], fill=(255, 140, 0), width=2)
    draw_prev.line([(f_r, 0), (f_r, preview_h)], fill=(255, 140, 0), width=2)

    # Spine safe margin lines (green)
    s_l = int(round(x_safe_left * scale))
    s_r = int(round(x_safe_right * scale))
    draw_prev.line([(s_l, 0), (s_l, preview_h)], fill=(0, 230, 120), width=1)
    draw_prev.line([(s_r, 0), (s_r, preview_h)], fill=(0, 230, 120), width=1)

    # Label on preview
    draw_prev.text((15, 15), "FULL SPREAD VIEW (WITH GUIDELINES)", fill=(240, 240, 240), font=_get_font(12))

    # 4. Build Zoomed Spine Inset Panel (high magnification)
    pad = max(25, int(round(spine_w_px * 0.45)))
    crop_x0 = max(0, x_fold_left - pad)
    crop_x1 = min(W, x_fold_right + pad)
    crop_w = max(1, crop_x1 - crop_x0)

    spine_crop = img.crop((crop_x0, 0, crop_x1, H))

    zoom_h = preview_h
    # Zoom width proportional with high magnification
    zoom_w = max(320, min(500, int(round(crop_w * (zoom_h / H) * 3.5))))
    zoom_spine = spine_crop.resize((zoom_w, zoom_h), Image.Resampling.LANCZOS)
    draw_zoom = ImageDraw.Draw(zoom_spine)

    z_scale_x = zoom_w / crop_w
    z_fold_left = (x_fold_left - crop_x0) * z_scale_x
    z_fold_right = (x_fold_right - crop_x0) * z_scale_x
    z_safe_left = (x_safe_left - crop_x0) * z_scale_x
    z_safe_right = (x_safe_right - crop_x0) * z_scale_x

    # Draw fold lines (orange, 3px)
    draw_zoom.line([(z_fold_left, 0), (z_fold_left, zoom_h)], fill=(255, 140, 0), width=3)
    draw_zoom.line([(z_fold_right, 0), (z_fold_right, zoom_h)], fill=(255, 140, 0), width=3)

    # Draw safe margin lines (bright green, 2px)
    draw_zoom.line([(z_safe_left, 0), (z_safe_left, zoom_h)], fill=(0, 255, 100), width=2)
    draw_zoom.line([(z_safe_right, 0), (z_safe_right, zoom_h)], fill=(0, 255, 100), width=2)

    # Glyph bounds in zoom coordinates
    glyph_min_x = x_fold_left + centering.left_clearance_px
    glyph_max_x = x_fold_right - centering.right_clearance_px
    z_glyph_min = (glyph_min_x - crop_x0) * z_scale_x
    z_glyph_max = (glyph_max_x - crop_x0) * z_scale_x

    # Measurement callout lines (yellow, horizontal arrows across clearances)
    callout_y = int(zoom_h * 0.48)
    if z_glyph_min > z_fold_left:
        draw_zoom.line([(z_fold_left, callout_y), (z_glyph_min, callout_y)], fill=(255, 230, 0), width=2)
        draw_zoom.line([(z_fold_left, callout_y - 6), (z_fold_left, callout_y + 6)], fill=(255, 230, 0), width=2)
        draw_zoom.line([(z_glyph_min, callout_y - 6), (z_glyph_min, callout_y + 6)], fill=(255, 230, 0), width=2)
        draw_zoom.text(
            (z_fold_left + 4, callout_y - 18),
            f"{centering.left_clearance_px:.1f}px",
            fill=(255, 230, 0),
            font=_get_font(11),
        )

    if z_fold_right > z_glyph_max:
        draw_zoom.line([(z_glyph_max, callout_y), (z_fold_right, callout_y)], fill=(255, 230, 0), width=2)
        draw_zoom.line([(z_glyph_max, callout_y - 6), (z_glyph_max, callout_y + 6)], fill=(255, 230, 0), width=2)
        draw_zoom.line([(z_fold_right, callout_y - 6), (z_fold_right, callout_y + 6)], fill=(255, 230, 0), width=2)
        draw_zoom.text(
            (z_glyph_max + 4, callout_y - 18),
            f"{centering.right_clearance_px:.1f}px",
            fill=(255, 230, 0),
            font=_get_font(11),
        )

    draw_zoom.text((15, 15), "ZOOMED SPINE VIEW (HIGH MAGNIFICATION)", fill=(240, 240, 240), font=_get_font(12))

    # 5. Composite Header & Footer Assembly
    header_h = 105
    footer_h = 125
    gap = 20
    comp_w = preview_w + zoom_w + gap * 3
    comp_h = header_h + preview_h + footer_h

    composite = Image.new("RGB", (comp_w, comp_h), (24, 26, 30))
    composite.paste(preview, (gap, header_h))
    composite.paste(zoom_spine, (preview_w + gap * 2, header_h))

    draw_comp = ImageDraw.Draw(composite)

    # Header text
    font_title = _get_font(18)
    font_sub = _get_font(13)
    font_bold = _get_font(14)
    font_small = _get_font(11)

    draw_comp.text((gap, 18), "MARKEE BOOKS - PREPRESS DIAGNOSTIC PROOF REPORT", fill=(255, 255, 255), font=font_title)
    draw_comp.text(
        (gap, 48),
        f"Target: {spec.publisher.upper()} | Trim: {spec.trim_w_in:.3f}\" x {spec.trim_h_in:.3f}\" | "
        f"Pages: {spec.page_count} | Paper: {spec.paper_type} | Binding: {spec.binding.title()}",
        fill=(190, 205, 225),
        font=font_sub,
    )
    draw_comp.text(
        (gap, 72),
        f"Calculated Spine: {spec.spine_w_in:.4f}\" ({spine_w_px:.1f} px) | "
        f"Publisher Safe Margin: {spec.spine_safe_margin_in:.4f}\" ({safe_margin_px:.1f} px)",
        fill=(170, 185, 205),
        font=font_sub,
    )

    # Real-time PASS / FAIL badge
    if centering.is_safe:
        status_text = "PREFLIGHT: PASS"
        badge_bg = (0, 205, 110)
        badge_fg = (10, 20, 10)
    else:
        status_text = "PREFLIGHT: FAIL - SAFE AREA BREACH"
        badge_bg = (230, 45, 45)
        badge_fg = (255, 255, 255)

    badge_w = 300 if not centering.is_safe else 180
    badge_x1 = comp_w - gap
    badge_x0 = badge_x1 - badge_w
    draw_comp.rectangle([(badge_x0, 22), (badge_x1, 74)], fill=badge_bg)
    draw_comp.text((badge_x0 + 15, 38), status_text, fill=badge_fg, font=font_bold)

    # Footer metrics
    f_y = header_h + preview_h + 15
    draw_comp.text((gap, f_y), "SPINE CLEARANCE METRICS:", fill=(255, 255, 255), font=font_bold)

    left_in = centering.left_clearance_px / dpi
    left_buf_in = (centering.left_clearance_px - safe_margin_px) / dpi
    left_buf_px = centering.left_clearance_px - safe_margin_px
    left_pass = left_buf_in >= -0.001

    right_in = centering.right_clearance_px / dpi
    right_buf_in = (centering.right_clearance_px - safe_margin_px) / dpi
    right_buf_px = centering.right_clearance_px - safe_margin_px
    right_pass = right_buf_in >= -0.001

    left_color = (0, 230, 120) if left_pass else (255, 80, 80)
    right_color = (0, 230, 120) if right_pass else (255, 80, 80)

    draw_comp.text(
        (gap, f_y + 25),
        f"Left Fold Clearance:  {left_in:.4f}\" ({centering.left_clearance_px:.1f} px)  -->  "
        f"Margin Buffer: {left_buf_in:+.4f}\" ({left_buf_px:+.1f} px)   [{'PASS' if left_pass else 'FAIL'}]",
        fill=left_color,
        font=font_sub,
    )
    draw_comp.text(
        (gap, f_y + 48),
        f"Right Fold Clearance: {right_in:.4f}\" ({centering.right_clearance_px:.1f} px)  -->  "
        f"Margin Buffer: {right_buf_in:+.4f}\" ({right_buf_px:+.1f} px)   [{'PASS' if right_pass else 'FAIL'}]",
        fill=right_color,
        font=font_sub,
    )
    draw_comp.text(
        (gap, f_y + 75),
        "Legend: Cyan=Trim Box, Magenta=Bleed Box, Orange=Spine Folds, Green=Publisher Safe Zone, Yellow=Measured Clearance",
        fill=(160, 175, 195),
        font=font_small,
    )

    # 6. Save Composite Image
    composite.save(output_str)
    return output_str
