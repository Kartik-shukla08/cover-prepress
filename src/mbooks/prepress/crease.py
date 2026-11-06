"""Spine fold crease boundary detection and 3D shadow bleed trimming."""

from __future__ import annotations

from typing import Tuple
from PIL import Image
import numpy as np
from pydantic import BaseModel


class CreaseDetectionResult(BaseModel):
    """Result of algorithmic spine crease detection and shadow bleed analysis."""

    x_left: int
    x_right: int
    spine_width_px: int
    shadow_bleed_right_px: int
    clean_background_rgb: Tuple[int, int, int]
    confidence: float

    model_config = {"frozen": True}


def detect_spine_creases(
    image: Image.Image,
    expected_spine_center_ratio: float = 0.5,
) -> CreaseDetectionResult:
    """Detect spine crease boundaries (x_left, x_right) and 3D shadow bleed.

    Uses margin-isolated vertical projection profiling (VPP) and horizontal gradient
    inflection analysis. Functions purely using NumPy and PIL with zero cloud
    or OpenCV dependencies.
    """
    img_rgb = image.convert("RGB")
    arr = np.array(img_rgb)
    height, width, _ = arr.shape

    # Isolate outer margin bands to avoid false positives from central photos / typography
    top_y0 = max(1, int(0.005 * height))
    top_y1 = min(25, max(2, int(0.028 * height)))
    btm_y0 = height - min(45, max(2, int(0.05 * height)))
    btm_y1 = height - max(1, int(0.005 * height))

    top_strip = arr[top_y0:top_y1, :, :].mean(axis=0)
    btm_strip = arr[btm_y0:btm_y1, :, :].mean(axis=0)
    margin_mean = (top_strip + btm_strip) / 2.0

    # Margin luminance profile
    margin_lum = (
        0.299 * margin_mean[:, 0]
        + 0.587 * margin_mean[:, 1]
        + 0.114 * margin_mean[:, 2]
    )

    grad = np.abs(np.diff(margin_lum))
    x_mid = int(round(expected_spine_center_ratio * width))

    # Search zones around expected center
    l_zone_start = max(0, x_mid - int(0.15 * width))
    l_zone_end = max(1, x_mid - int(0.015 * width))
    r_zone_start = min(width - 2, x_mid + int(0.015 * width))
    r_zone_end = min(width - 1, x_mid + int(0.15 * width))

    l_peak = l_zone_start + int(np.argmax(grad[l_zone_start:l_zone_end]))
    r_peak = r_zone_start + int(np.argmax(grad[r_zone_start:r_zone_end]))

    # Refine crease boundaries past transition shoulders
    x_left = l_peak + 1
    while x_left < l_zone_end and grad[x_left] > 0.35 * grad[l_peak]:
        x_left += 1

    x_right = r_peak + 1
    while x_right < r_zone_end and grad[x_right] > 0.35 * grad[r_peak]:
        x_right += 1

    spine_width_px = max(1, x_right - x_left)

    # Sample clean background RGB from inner spine core
    sample_x0 = x_left + max(1, int(0.05 * spine_width_px))
    sample_x1 = max(sample_x0 + 1, x_right - max(1, int(0.05 * spine_width_px)))
    spine_core = arr[:, sample_x0:sample_x1, :]
    clean_bg = tuple(int(round(c)) for c in np.median(spine_core.reshape(-1, 3), axis=0))

    # Detect 3D fold shadow bleed spilling rightwards from x_right into front panel
    shadow_bleed_right_px = 0
    max_shadow_search = min(width, x_right + 60)
    if max_shadow_search > x_right + 10:
        lum_all = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        mid_lum = lum_all[int(0.20 * height):int(0.80 * height), x_right:max_shadow_search].mean(axis=0)

        # Check if there is a noticeable shadow dip/roll-off followed by a steep positive edge (content start)
        diff_mid = np.diff(mid_lum)
        # Look for a sharp upward content edge (diff > 20) or trough
        sharp_jumps = np.where(diff_mid > 20.0)[0]
        if len(sharp_jumps) > 0 and sharp_jumps[0] >= 10:
            shadow_bleed_right_px = int(sharp_jumps[0])
        elif len(mid_lum) > 20:
            # Check for roll-off dip compared to spine edge
            min_idx = int(np.argmin(mid_lum[:45]))
            if min_idx >= 15 and (mid_lum[0] - mid_lum[min_idx]) > 10.0:
                shadow_bleed_right_px = min_idx

    # Confidence calculation
    peak_strength = float(grad[l_peak] + grad[r_peak])
    confidence = float(min(1.0, max(0.5, peak_strength / 10.0)))

    return CreaseDetectionResult(
        x_left=int(x_left),
        x_right=int(x_right),
        spine_width_px=int(spine_width_px),
        shadow_bleed_right_px=int(shadow_bleed_right_px),
        clean_background_rgb=clean_bg,
        confidence=round(confidence, 3),
    )


def trim_shadow_and_infill_background(
    image: Image.Image,
    crease_result: CreaseDetectionResult,
) -> Image.Image:
    """Trim 3D shadow bleed spilling into front panel and infill clean background."""
    img_rgb = image.convert("RGB")
    if crease_result.shadow_bleed_right_px <= 0:
        return img_rgb.copy()

    arr = np.array(img_rgb).copy()
    x_start = crease_result.x_right
    x_end = min(arr.shape[1], crease_result.x_right + crease_result.shadow_bleed_right_px)

    # Infill shadow trough with clean background RGB
    arr[:, x_start:x_end, :] = crease_result.clean_background_rgb
    return Image.fromarray(arr)
