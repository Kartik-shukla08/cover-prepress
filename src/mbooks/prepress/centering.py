"""Glyph-only luminance optical centering and safe margin enforcement."""

from __future__ import annotations

from typing import List, Tuple
from PIL import Image
import numpy as np
from pydantic import BaseModel

from .segmentation import SpineElement


class CenteringResult(BaseModel):
    """Result of optical centering computation and safe margin audit."""

    shift_x_px: float
    optical_center_x_px: float
    geometric_center_x_px: float
    left_clearance_px: float
    right_clearance_px: float
    safe_margin_px: float
    is_safe: bool

    model_config = {"frozen": True}


def compute_optical_centering(
    spine_crop: Image.Image,
    elements: List[SpineElement],
    safe_margin_px: float,
    nudge_px: float = 0.0,
) -> CenteringResult:
    """Compute optical centering from high-contrast glyph luminance.

    Eliminates drop-shadow bias (which otherwise biases centers 14-20px toward fold creases)
    and verifies clearance against publisher safe margins.
    """
    width = float(spine_crop.width)
    geom_center_x = width / 2.0

    if not elements:
        shift_x = float(nudge_px)
        left_clearance = geom_center_x + shift_x
        right_clearance = geom_center_x - shift_x
        is_safe = (left_clearance >= safe_margin_px) and (right_clearance >= safe_margin_px)
        return CenteringResult(
            shift_x_px=round(shift_x, 2),
            optical_center_x_px=round(geom_center_x, 2),
            geometric_center_x_px=round(geom_center_x, 2),
            left_clearance_px=round(left_clearance, 2),
            right_clearance_px=round(right_clearance, 2),
            safe_margin_px=round(safe_margin_px, 2),
            is_safe=is_safe,
        )

    # Measure glyph-only bounding box across all segmented elements
    glyph_x_min = float(min(el.bbox[0] for el in elements))
    glyph_x_max = float(max(el.bbox[2] for el in elements))
    optical_center_x = (glyph_x_min + glyph_x_max) / 2.0

    # Shift required to place optical center onto geometric center, plus manual nudge
    shift_x = (geom_center_x - optical_center_x) + float(nudge_px)

    centered_x_min = glyph_x_min + shift_x
    centered_x_max = glyph_x_max + shift_x

    left_clearance = centered_x_min
    right_clearance = width - centered_x_max

    is_safe = (left_clearance >= safe_margin_px) and (right_clearance >= safe_margin_px)

    return CenteringResult(
        shift_x_px=round(shift_x, 2),
        optical_center_x_px=round(optical_center_x, 2),
        geometric_center_x_px=round(geom_center_x, 2),
        left_clearance_px=round(left_clearance, 2),
        right_clearance_px=round(right_clearance, 2),
        safe_margin_px=round(safe_margin_px, 2),
        is_safe=is_safe,
    )


def measure_shadow_bias(
    spine_crop: Image.Image,
    clean_bg_rgb: Tuple[int, int, int],
) -> Tuple[float, float, float]:
    """Measure the optical shift bias caused by dark drop shadows.

    Returns:
        (glyph_only_center_x, naive_with_shadow_center_x, shadow_bias_px)
    """
    arr = np.array(spine_crop.convert("RGB"))
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    bg_lum = (
        0.299 * clean_bg_rgb[0]
        + 0.587 * clean_bg_rgb[1]
        + 0.114 * clean_bg_rgb[2]
    )

    # 1. High contrast glyphs only
    if bg_lum < 128:
        glyph_mask = lum > (bg_lum + 25)
        naive_mask = np.abs(lum - bg_lum) > 15
    else:
        glyph_mask = lum < (bg_lum - 25)
        naive_mask = np.abs(lum - bg_lum) > 15

    g_nz_y, g_nz_x = np.where(glyph_mask)
    n_nz_y, n_nz_x = np.where(naive_mask)

    if len(g_nz_x) == 0 or len(n_nz_x) == 0:
        return (spine_crop.width / 2.0, spine_crop.width / 2.0, 0.0)

    glyph_center = float((g_nz_x.min() + g_nz_x.max()) / 2.0)
    naive_center = float((n_nz_x.min() + n_nz_x.max()) / 2.0)
    shadow_bias = naive_center - glyph_center

    return (round(glyph_center, 2), round(naive_center, 2), round(shadow_bias, 2))
