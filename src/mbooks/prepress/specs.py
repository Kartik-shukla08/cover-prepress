"""Prepress specification calculations across publishers and bindings."""

from __future__ import annotations

from typing import Literal, Optional, Tuple
from pydantic import BaseModel, Field

from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import BindingType, BookFormat, InteriorInk, PaperType
from mbooks.domain.geometry import TrimSize
from mbooks.calculators.kdp import KDPCalculator
from mbooks.calculators.ingram import IngramSparkCalculator
from mbooks.calculators.lulu import LuluCalculator
from mbooks.calculators.tables import (
    KDP_SPINE_SAFE_MARGIN,
    LULU_SPINE_SAFE_MARGIN,
)


class PrepressSpec(BaseModel):
    """Authoritative prepress specification for print-ready cover wrap assembly."""

    publisher: Literal["kdp", "ingram", "lulu"]
    binding: Literal["paperback", "casewrap"]
    trim_w_in: float
    trim_h_in: float
    page_count: int
    paper_type: str
    ink_type: str

    # Calculated physical dimensions (in inches)
    total_w_in: float
    total_h_in: float
    spine_w_in: float
    bleed_in: float
    wrap_in: float
    hinge_in: float
    spine_safe_margin_in: float
    cover_safe_margin_in: float

    # Text eligibility
    allow_spine_text: bool
    spine_text_warning: Optional[str] = None

    # PDF Box geometry (in points: 1 in = 72 pt)
    media_box: Tuple[float, float, float, float]
    bleed_box: Tuple[float, float, float, float]
    trim_box: Tuple[float, float, float, float]
    crop_box: Tuple[float, float, float, float]

    model_config = {"frozen": True}


def _normalize_publisher(publisher: str) -> Literal["kdp", "ingram", "lulu"]:
    p = publisher.strip().lower()
    if "kdp" in p or "amazon" in p:
        return "kdp"
    elif "ingram" in p:
        return "ingram"
    elif "lulu" in p:
        return "lulu"
    else:
        raise ValueError(f"Unsupported publisher: '{publisher}'. Must be 'kdp', 'ingram', or 'lulu'.")


def _normalize_binding(binding: str) -> Literal["paperback", "casewrap"]:
    b = binding.strip().lower()
    if "paper" in b or "soft" in b or "perfect" in b:
        return "paperback"
    elif "case" in b or "hard" in b:
        return "casewrap"
    else:
        raise ValueError(f"Unsupported binding: '{binding}'. Must be 'paperback' or 'casewrap'.")


def calculate_prepress_spec(
    publisher: str,
    binding: str,
    trim_w_in: float,
    trim_h_in: float,
    page_count: int,
    paper_type: str = "white",
    ink_type: str = "black",
) -> PrepressSpec:
    """Calculate authoritative prepress specifications, safe margins, and PDF boxes.

    Zero cloud dependencies. Accurately handles KDP, IngramSpark, and Lulu across
    both Paperback and Hardcover Casewrap bindings, including publisher short-book
    spine text threshold enforcement.
    """
    pub_norm = _normalize_publisher(publisher)
    bind_norm = _normalize_binding(binding)

    book_format = BookFormat.PAPERBACK if bind_norm == "paperback" else BookFormat.HARDCOVER
    trim_size = TrimSize(width=float(trim_w_in), height=float(trim_h_in))

    # Resolve ink & paper strings for calculators
    p_lower = paper_type.lower()
    if "cream" in p_lower or "crème" in p_lower or "creme" in p_lower:
        norm_paper = "Cream"
    elif "groundwood" in p_lower:
        norm_paper = "Groundwood"
    else:
        norm_paper = "White"

    i_lower = ink_type.lower()
    if "prem" in i_lower:
        norm_ink = "Premium Color"
    elif "std" in i_lower or "standard" in i_lower:
        norm_ink = "Standard Color"
    else:
        norm_ink = "B&W"

    cfg = BookConfiguration(
        book_format=book_format,
        page_count=page_count,
        trim_size=trim_size,
        paper_type=norm_paper,
        interior_ink=norm_ink,
    )

    if pub_norm == "kdp":
        calc = KDPCalculator()
        cover_dims = calc.calculate_cover(cfg)
        spine_spec = calc.calculate_spine(cfg)

        total_w_in = cover_dims.full_width
        total_h_in = cover_dims.full_height
        spine_w_in = cover_dims.spine_width
        bleed_in = cover_dims.bleed
        wrap_in = cover_dims.wrap
        hinge_in = cover_dims.hinge_allowance
        spine_safe_margin_in = cover_dims.spine_safe_margin or KDP_SPINE_SAFE_MARGIN
        cover_safe_margin_in = cover_dims.safe_margin_outside or 0.125

        allow_spine_text = spine_spec.spine_text_allowed
        spine_text_warning = None
        if not allow_spine_text:
            spine_text_warning = (
                f"Spine text suppressed: page count {page_count} is below KDP minimum threshold of 80 pages."
            )

    elif pub_norm == "ingram":
        calc = IngramSparkCalculator()
        cover_dims = calc.calculate_cover(cfg)
        spine_spec = calc.calculate_spine(cfg)

        total_w_in = cover_dims.full_width
        total_h_in = cover_dims.full_height
        spine_w_in = cover_dims.spine_width
        bleed_in = cover_dims.bleed
        wrap_in = cover_dims.wrap
        hinge_in = cover_dims.hinge_allowance

        # Ingram stepped spine safe margin: 0.03125" if spine < 0.350", else 0.0625"
        if spine_w_in < 0.350:
            spine_safe_margin_in = 0.03125
        else:
            spine_safe_margin_in = 0.0625
        cover_safe_margin_in = 0.250

        allow_spine_text = spine_spec.spine_text_allowed
        spine_text_warning = None
        if not allow_spine_text:
            spine_text_warning = (
                f"Spine text suppressed: page count {page_count} is below IngramSpark minimum threshold of 48 pages."
            )

    elif pub_norm == "lulu":
        calc = LuluCalculator()
        cover_dims = calc.calculate_cover(cfg)
        spine_spec = calc.calculate_spine(cfg)

        total_w_in = cover_dims.full_width
        total_h_in = cover_dims.full_height
        spine_w_in = cover_dims.spine_width
        bleed_in = cover_dims.bleed
        wrap_in = cover_dims.wrap
        hinge_in = cover_dims.hinge_allowance
        spine_safe_margin_in = cover_dims.spine_safe_margin or LULU_SPINE_SAFE_MARGIN
        cover_safe_margin_in = 0.500

        allow_spine_text = spine_spec.spine_text_allowed
        spine_text_warning = None
        if not allow_spine_text:
            spine_text_warning = (
                f"Spine text suppressed: page count {page_count} is below Lulu minimum threshold of 81 pages."
            )

    # PDF Box Geometry (in points, 72 pt = 1 in)
    media_w_pt = round(total_w_in * 72.0, 3)
    media_h_pt = round(total_h_in * 72.0, 3)

    media_box = (0.0, 0.0, media_w_pt, media_h_pt)
    bleed_box = (0.0, 0.0, media_w_pt, media_h_pt)
    crop_box = (0.0, 0.0, media_w_pt, media_h_pt)

    if bind_norm == "paperback":
        trim_inset_pt = round(bleed_in * 72.0, 3)
        trim_box = (
            trim_inset_pt,
            trim_inset_pt,
            round((total_w_in - bleed_in) * 72.0, 3),
            round((total_h_in - bleed_in) * 72.0, 3),
        )
    else:
        # Casewrap turn-in wrap allowance
        trim_inset_pt = round(wrap_in * 72.0, 3)
        trim_box = (
            trim_inset_pt,
            trim_inset_pt,
            round((total_w_in - wrap_in) * 72.0, 3),
            round((total_h_in - wrap_in) * 72.0, 3),
        )

    return PrepressSpec(
        publisher=pub_norm,
        binding=bind_norm,
        trim_w_in=round(trim_w_in, 4),
        trim_h_in=round(trim_h_in, 4),
        page_count=page_count,
        paper_type=paper_type,
        ink_type=ink_type,
        total_w_in=round(total_w_in, 4),
        total_h_in=round(total_h_in, 4),
        spine_w_in=round(spine_w_in, 4),
        bleed_in=round(bleed_in, 4),
        wrap_in=round(wrap_in, 4),
        hinge_in=round(hinge_in, 4),
        spine_safe_margin_in=round(spine_safe_margin_in, 5),
        cover_safe_margin_in=round(cover_safe_margin_in, 4),
        allow_spine_text=allow_spine_text,
        spine_text_warning=spine_text_warning,
        media_box=media_box,
        bleed_box=bleed_box,
        trim_box=trim_box,
        crop_box=crop_box,
    )
