"""Domain models for book geometry and calculated physical specifications."""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

from .economics import PrintEconomics


class TrimSize(BaseModel):
    """Represents a book's trim dimensions."""
    width: float = Field(..., gt=0, description="Trim width in inches")
    height: float = Field(..., gt=0, description="Trim height in inches")
    unit: str = Field(default="in", description="Unit of measurement")
    name: str | None = Field(default=None, description="Preset name e.g. '6 x 9'")
    is_custom: bool = Field(default=False, description="True if custom trim size")

    @classmethod
    def from_string(cls, s: str) -> "TrimSize":
        """Parse '6 x 9', '5.5 x 8.5', or standard named trims (e.g. 'US Trade') into TrimSize."""
        s_clean = s.strip()
        from mbooks.calculators.tables import LULU_STANDARD_TRIM_SIZES
        for name, (w, h) in LULU_STANDARD_TRIM_SIZES.items():
            if s_clean.lower() == name.lower():
                return cls(width=w, height=h, name=name)

        parts = s.lower().replace('×', 'x').split('x')
        if len(parts) != 2:
            raise ValueError(f"Cannot parse trim size: {s}")
        return cls(width=float(parts[0].strip()), height=float(parts[1].strip()), name=s.strip())

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        w_str = f"{int(self.width)}" if self.width.is_integer() else f"{self.width}"
        h_str = f"{int(self.height)}" if self.height.is_integer() else f"{self.height}"
        return f"{w_str} x {h_str}"

    def __str__(self) -> str:
        return self.display_name
    
    model_config = {"frozen": True}


class SpineSpecification(BaseModel):
    """Calculated spine dimensions and constraints."""
    width: float = Field(..., ge=0, description="Calculated spine width in inches")
    spine_text_allowed: bool = Field(default=False, description="Whether spine is wide enough for title text")
    min_pages_for_text: int = Field(default=80, description="Minimum page count required for spine text")
    safe_margin: float | None = Field(default=None, description="Spine text safety margin per side (in)")
    page_multiplier: float | None = Field(default=None, description="Per-page caliper/multiplier used")
    hinge_allowance: float = Field(default=0.0, description="Spine hinge/fold allowance (in)")
    weight_lb: float | None = Field(default=None, description="Calculated book physical weight in pounds")
    weight_g: float | None = Field(default=None, description="Calculated book physical weight in grams")
    unit: str = Field(default="in")

    model_config = {"frozen": True}


class InteriorDimensions(BaseModel):
    """Calculated interior page dimensions and formatting margins."""
    page_width: float = Field(..., description="Interior page width (with bleed if applicable)")
    page_height: float = Field(..., description="Interior page height (with bleed if applicable)")
    trim_width: float = Field(..., description="Original trim width")
    trim_height: float = Field(..., description="Original trim height")
    has_bleed: bool = Field(default=False)
    bleed_amount: float = Field(default=0.0, description="Bleed amount per side")
    bleed_top: float = Field(default=0.0, description="Bleed added to top edge")
    bleed_bottom: float = Field(default=0.0, description="Bleed added to bottom edge")
    bleed_outside: float = Field(default=0.0, description="Bleed added to outside edge")
    bleed_inside: float = Field(default=0.0, description="Bleed added to binding edge (usually 0.0)")
    min_inside_margin: float | None = Field(default=None, description="Minimum inside/gutter margin based on page count")
    additional_gutter: float | None = Field(default=None, description="Additional gutter allowance added to interior margin")
    recommended_inside_margin: float | None = Field(default=None, description="Recommended inside margin for no-bleed layout")
    full_bleed_inside_margin: float | None = Field(default=None, description="Recommended inside margin for full-bleed layout")
    min_outside_margin: float | None = Field(default=None, description="Minimum outside margin")
    min_top_margin: float | None = Field(default=None, description="Minimum top margin")
    min_bottom_margin: float | None = Field(default=None, description="Minimum bottom margin")
    unit: str = Field(default="in")

    model_config = {"frozen": True}


class CoverDimensions(BaseModel):
    """Calculated full cover layout dimensions and guide coordinates."""
    full_width: float = Field(..., description="Total cover file width in inches")
    full_height: float = Field(..., description="Total cover file height in inches")
    front_cover_width: float = Field(..., description="Front cover panel width")
    front_cover_height: float = Field(..., description="Front cover panel height")
    back_cover_width: float = Field(..., description="Back cover panel width")
    back_cover_height: float = Field(..., description="Back cover panel height")
    spine_width: float = Field(..., description="Spine panel width")
    bleed: float = Field(default=0.125, description="Cover bleed amount per side")
    wrap: float = Field(default=0.0, description="Hardcover wrap allowance")
    hinge_allowance: float = Field(default=0.0, description="Hardcover hinge allowance per side")
    spine_text_allowed: bool = Field(default=False)
    spine_safe_margin: float | None = Field(default=None, description="Spine text safety margin per side")
    spine_left_x: float = Field(default=0.0, description="X coordinate on canvas where spine begins")
    spine_right_x: float = Field(default=0.0, description="X coordinate on canvas where spine ends")
    safe_margin_top: float = Field(default=0.125, description="Safety distance from top edge")
    safe_margin_bottom: float = Field(default=0.125, description="Safety distance from bottom edge")
    safe_margin_outside: float = Field(default=0.125, description="Safety distance from outside trim")
    front_cover_safe_width: float | None = Field(default=None, description="Front cover safe area width")
    front_cover_safe_height: float | None = Field(default=None, description="Front cover safe area height")
    spine_safe_width: float | None = Field(default=None, description="Spine text safe area width")
    spine_safe_height: float | None = Field(default=None, description="Spine text safe area height")
    spine_margin: float = Field(default=0.0625, description="Spine safety margin per side")
    barcode_margin: float = Field(default=0.250, description="Recommended barcode margin from edges")
    barcode_margin_height: float = Field(default=0.250, description="Recommended barcode margin from bottom edge")
    barcode_zone: dict[str, float] | None = Field(default=None, description="Recommended barcode bounding box on back cover")
    reading_direction: str = Field(default="ltr", description="Reading direction: 'ltr' or 'rtl'")
    unit: str = Field(default="in")

    model_config = {"frozen": True}


class CalculatedSpecification(BaseModel):
    """Complete calculated physical specification for a book configuration."""
    publisher: str | None = Field(default=None, description="Target publisher used for calculations")
    spine: SpineSpecification = Field(..., description="Spine specifications")
    cover: CoverDimensions = Field(..., description="Cover layout specifications")
    interior: InteriorDimensions = Field(..., description="Interior layout specifications")
    spine_width: float = Field(..., description="Convenience copy of spine width")
    spine_text_allowed: bool = Field(default=False, description="Convenience copy of spine text eligibility")
    weight_lb: float | None = Field(default=None, description="Calculated book physical weight in pounds")
    weight_g: float | None = Field(default=None, description="Calculated book physical weight in grams")
    economics: PrintEconomics | None = Field(default=None, description="Print cost and royalty projections")
    pod_package_id: str | None = Field(default=None, description="Canonical POD package ID (e.g. Lulu Dotted SKU)")
    unit: str = Field(default="in")
    notes: list[str] = Field(default_factory=list, description="Calculation notes and warnings")

    model_config = {"frozen": True}
