"""Print-ready PDF export and prepress preflight validation engine.

Sets exact PDF page boxes in points (72 pt/in) matching publisher specifications:
- MediaBox: Full physical sheet
- BleedBox: Outer bleed boundary
- TrimBox: Cut boundary of finished wrap
- CropBox: Display boundary (identical to MediaBox)

Validates color safety, TAC limits (Ingram 240%, Lulu 270%, KDP 300%),
prevents 400% registration black, and flattens transparency for PDF/X compliance.
Pure PyMuPDF (fitz) and Pillow implementation with zero external cloud dependencies.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple, Union

import fitz
import numpy as np
from PIL import Image

from .specs import PrepressSpec

# Authoritative publisher TAC limits (Total Area Coverage percentage)
PUBLISHER_TAC_LIMITS: dict[str, float] = {
    "ingram": 240.0,  # IS-COL-002 hard ceiling
    "lulu": 270.0,    # LULU_MAX_TAC_PERCENT
    "kdp": 300.0,     # Web press ink set-off ceiling (target 240-300%)
}


class PreflightError(ValueError):
    """Base exception for prepress preflight check failures."""

    pass


class TACLimitExceededError(PreflightError):
    """Raised when ink density exceeds publisher Total Area Coverage ceiling."""

    pass


class RegistrationBlackError(PreflightError):
    """Raised when 400% registration black (100% C, M, Y, K) is detected."""

    pass


def flatten_transparency(
    image: Image.Image,
    bg_color: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """Flatten transparency/alpha channel onto solid background for PDF/X compliance.

    Prepress transparency hazard: Unflattened PDF 1.4+ transparency causes
    catastrophic RIP defects on POD web presses (e.g. drop shadows rendering
    with solid white boxes). Flattening at source rasterizes opacity cleanly.
    """
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        alpha_img = image.convert("RGBA")
        flattened = Image.new("RGB", alpha_img.size, bg_color)
        flattened.paste(alpha_img, mask=alpha_img.split()[3])
        return flattened
    elif image.mode not in ("RGB", "CMYK"):
        return image.convert("RGB")
    return image


def inspect_tac_and_registration(
    image: Image.Image,
    tac_ceiling: float = 240.0,
) -> Tuple[float, bool, bool]:
    """Inspect Total Area Coverage (TAC) and 400% registration black.

    Returns:
        (max_tac_pct, has_tac_breach, has_registration_black)
    """
    if image.mode == "CMYK":
        arr = np.array(image, dtype=np.uint8)
        c = arr[:, :, 0]
        m = arr[:, :, 1]
        y = arr[:, :, 2]
        k = arr[:, :, 3]
        ch_sum = c.astype(np.uint16) + m + y + k
        max_sum = int(ch_sum.max())
        max_tac_pct = round((max_sum / 255.0) * 100.0, 2)
        has_tac_breach = max_tac_pct > tac_ceiling
        # Registration black requires all 4 channels saturated (>= 240 => >= 94.1%)
        has_reg_black = bool(np.any((c >= 240) & (m >= 240) & (y >= 240) & (k >= 240)))
        return max_tac_pct, has_tac_breach, has_reg_black

    elif image.mode in ("RGB", "RGBA"):
        rgb = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        # Standard Gray Component Replacement (GCR)
        k = 1.0 - np.maximum(np.maximum(r, g), b)
        denom = 1.0 - k
        safe_denom = np.where(denom == 0, 1.0, denom)
        c = np.where(denom == 0, 0.0, (1.0 - r - k) / safe_denom)
        m = np.where(denom == 0, 0.0, (1.0 - g - k) / safe_denom)
        y = np.where(denom == 0, 0.0, (1.0 - b - k) / safe_denom)
        tac = (c + m + y + k) * 100.0
        max_tac_pct = round(float(tac.max()), 2)
        has_tac_breach = max_tac_pct > tac_ceiling
        # RGB images do not have registration black
        return max_tac_pct, has_tac_breach, False

    else:
        # Grayscale / 1-bit: maximum TAC is 100%
        return 100.0, False, False


def export_print_ready_pdf(
    spread_image: Image.Image,
    spec: PrepressSpec,
    output_path: Union[str, Path],
    dpi: int = 300,
    validate: bool = True,
) -> str:
    """Export print-ready PDF spread with publisher PDF Box hierarchy.

    Args:
        spread_image: Composed cover wrap image (spread: Back + Spine + Front).
        spec: PrepressSpec containing physical geometry and PDF box coordinates.
        output_path: Destination path for the generated PDF.
        dpi: Target raster DPI (default 300 DPI).
        validate: Whether to run preflight validation (TAC ceiling & registration black).

    Returns:
        Absolute string path to the created PDF file.

    Raises:
        RegistrationBlackError: If 400% registration black is detected.
        TACLimitExceededError: If ink density exceeds publisher ceiling.
        Exception: If destination directory cannot be written or image is invalid.
    """
    output_str = str(output_path)

    # 1. Preflight Validation
    if validate:
        publisher_key = spec.publisher.lower()
        tac_ceiling = PUBLISHER_TAC_LIMITS.get(publisher_key, 300.0)
        max_tac_pct, has_tac_breach, has_reg_black = inspect_tac_and_registration(
            spread_image, tac_ceiling=tac_ceiling
        )
        if has_reg_black:
            raise RegistrationBlackError(
                f"400% Registration Black (100% C, M, Y, K) is strictly prohibited by {spec.publisher.upper()} "
                f"(causes wet ink set-off and fuzzy misregistration halos)."
            )
        if has_tac_breach:
            raise TACLimitExceededError(
                f"Total Area Coverage ({max_tac_pct:.1f}%) exceeds {spec.publisher.upper()} "
                f"hard maximum ceiling of {tac_ceiling:.1f}%."
            )

    # 2. Transparency Flattening for PDF/X Compliance
    flattened_img = flatten_transparency(spread_image)

    # 3. Create PyMuPDF Document
    doc = fitz.open()

    # Dimensions in PDF points (72 pt/in)
    media_rect = fitz.Rect(spec.media_box)
    page_w = media_rect.width
    page_h = media_rect.height

    page = doc.new_page(width=page_w, height=page_h)

    # Set strict PDF Box hierarchy (clamped to page.mediabox to prevent 32-bit float boundary errors)
    mb = page.mediabox

    def _clamp_to_mb(box: Tuple[float, float, float, float]) -> fitz.Rect:
        return fitz.Rect(
            max(mb.x0, float(box[0])),
            max(mb.y0, float(box[1])),
            min(mb.x1, float(box[2])),
            min(mb.y1, float(box[3])),
        )

    page.set_bleedbox(_clamp_to_mb(spec.bleed_box))
    page.set_trimbox(_clamp_to_mb(spec.trim_box))
    page.set_cropbox(_clamp_to_mb(spec.crop_box))

    # 4. Save image into memory buffer and insert into page
    img_buf = io.BytesIO()
    if flattened_img.mode == "CMYK":
        flattened_img.save(img_buf, format="TIFF")
    else:
        flattened_img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    # Insert image to span entire MediaBox (zero crop/printer marks)
    page.insert_image(media_rect, stream=img_bytes)

    # 5. Write PDF output
    doc.save(output_str, deflate=True)
    doc.close()

    return output_str
