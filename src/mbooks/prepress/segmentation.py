"""Spine foreground element segmentation, element classification, and aspect-ratio scaling."""

from __future__ import annotations

from typing import List, Literal, Optional, Tuple
from PIL import Image
import numpy as np
from pydantic import BaseModel


class SpineElement(BaseModel):
    """Segmented spine component (typography, ornament, or logo)."""

    element_type: Literal["ornament", "text", "logo"]
    bbox: Tuple[int, int, int, int]  # x0, y0, x1, y1 in spine crop coordinates
    is_symmetric: bool
    glyph_mask_coords: Optional[List[Tuple[int, int]]] = None

    model_config = {"frozen": True}


def segment_spine_elements(
    spine_crop: Image.Image,
    clean_bg_rgb: Tuple[int, int, int],
) -> List[SpineElement]:
    """Segment spine foreground elements from background via high-contrast luminance.

    Distinguishes non-text ornaments/logos (requiring 1:1 symmetric scaling)
    from text runs (requiring proportional scaling with aspect deviation clamping).
    """
    img_rgb = spine_crop.convert("RGB")
    arr = np.array(img_rgb)
    height, width, _ = arr.shape

    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    bg_lum = (
        0.299 * clean_bg_rgb[0]
        + 0.587 * clean_bg_rgb[1]
        + 0.114 * clean_bg_rgb[2]
    )

    # High-contrast glyph isolation: isolates bright typography from dark drop shadows
    if bg_lum < 128:
        fg_mask = lum > (bg_lum + 25)
    else:
        fg_mask = lum < (bg_lum - 25)

    # Fallback if contrast delta is mild
    if fg_mask.sum() < 20:
        fg_mask = np.abs(lum - bg_lum) > 20

    v_proj = fg_mask.any(axis=1)

    # Group connected vertical lines
    raw_blocks: List[Tuple[int, int]] = []
    in_block = False
    y_start = 0
    for y, active in enumerate(v_proj):
        if active and not in_block:
            in_block = True
            y_start = y
        elif not active and in_block:
            if y - y_start >= 3:
                raw_blocks.append((y_start, y))
            in_block = False
    if in_block and (height - y_start >= 3):
        raw_blocks.append((y_start, height))

    # Merge contiguous sub-blocks where vertical gap is small (<= 15 px)
    merged_blocks: List[Tuple[int, int]] = []
    for b in raw_blocks:
        if not merged_blocks:
            merged_blocks.append(b)
        else:
            prev_y0, prev_y1 = merged_blocks[-1]
            if b[0] - prev_y1 <= 15:
                merged_blocks[-1] = (prev_y0, b[1])
            else:
                merged_blocks.append(b)

    elements: List[SpineElement] = []
    for b_y0, b_y1 in merged_blocks:
        sub_fg = fg_mask[b_y0:b_y1, :]
        nz_y, nz_x = np.where(sub_fg)
        if len(nz_x) < 20:
            # Dust and single-pixel compression artifact rejection
            continue

        box_x0 = int(nz_x.min())
        box_x1 = int(nz_x.max()) + 1
        box_y0 = int(b_y0 + nz_y.min())
        box_y1 = int(b_y0 + nz_y.max()) + 1

        w = box_x1 - box_x0
        h = box_y1 - box_y0
        aspect_ratio = w / float(max(1, h))

        # Classification rule:
        # Non-text ornaments have near 1:1 aspect ratio (0.70 <= AR <= 1.40) and compact vertical height
        if 0.70 <= aspect_ratio <= 1.40 and h <= 150:
            element_type: Literal["ornament", "text", "logo"] = "ornament"
            is_symmetric = True
        else:
            element_type = "text"
            is_symmetric = False

        coords = [
            (int(x), int(b_y0 + y))
            for y, x in zip(nz_y[:1000], nz_x[:1000])
        ]

        elements.append(
            SpineElement(
                element_type=element_type,
                bbox=(box_x0, box_y0, box_x1, box_y1),
                is_symmetric=is_symmetric,
                glyph_mask_coords=coords,
            )
        )

    return elements


def calculate_element_scaling(
    element: SpineElement,
    scale_x: float,
    scale_y: float,
) -> Tuple[float, float]:
    """Calculate scaling factors enforcing 1:1 for ornaments and <=1.2x aspect clamp for text."""
    if element.is_symmetric:
        # Strict 1:1 isotropic scaling for ornaments/logos to prevent visual warping
        s = min(scale_x, scale_y)
        return (s, s)
    else:
        # Proportional typography scaling with aspect ratio deviation clamp (<= 1.2x)
        # Avoids vertical needle-stretching distortion
        min_sy = scale_x / 1.2
        max_sy = scale_x * 1.2
        clamped_sy = min(max(scale_y, min_sy), max_sy)
        return (scale_x, clamped_sy)


def reconstruct_clean_spine_background(
    spine_crop: Image.Image,
    clean_bg_rgb: Tuple[int, int, int],
    elements: List[SpineElement],
) -> Image.Image:
    """Infill foreground glyphs and drop shadows with clean interpolated background texture."""
    img_rgb = spine_crop.convert("RGB")
    arr = np.array(img_rgb, dtype=float)
    height, width, _ = arr.shape

    # 1. Row-by-row linear interpolation between clean left and right inner spine margins
    # This removes anti-aliased glyph halos and drop-shadow fringes while preserving vertical grain.
    if width >= 20 and elements:
        min_el_x = max(0, min(el.bbox[0] for el in elements) - 6)
        max_el_x = min(width - 1, max(el.bbox[2] for el in elements) + 6)
        l_pad = max(2, min(min_el_x, int(round(width * 0.16))))
        r_pad = min(width - 3, max(max_el_x, int(round(width * 0.84))))
        if r_pad > l_pad + 2:
            left_val = arr[:, max(0, l_pad - 2) : l_pad + 2, :].mean(axis=1)
            right_val = arr[:, r_pad - 1 : min(width, r_pad + 3), :].mean(axis=1)
            span = float(max(1, r_pad - l_pad))
            for xi in range(l_pad, r_pad + 1):
                t = (xi - l_pad) / span
                arr[:, xi, :] = (1.0 - t) * left_val + t * right_val

    # 2. Enforce strict luminance cleanup for any residual high-contrast or shadow pixels
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    bg_lum = (
        0.299 * clean_bg_rgb[0]
        + 0.587 * clean_bg_rgb[1]
        + 0.114 * clean_bg_rgb[2]
    )

    if bg_lum < 128:
        fg_mask = lum > (bg_lum + 25)
        shadow_mask = lum < (bg_lum - 15)
    else:
        fg_mask = lum < (bg_lum - 25)
        shadow_mask = lum > (bg_lum + 15)

    mask = fg_mask | shadow_mask
    arr[mask] = clean_bg_rgb
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
