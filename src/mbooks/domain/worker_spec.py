"""Domain models for Universal Worker Contracts and Payloads.

Defines tool-agnostic, standardized JSON specification schemas that external
production workers (Cover Worker, Formatter Worker, Publisher Worker) can consume
without coupling to internal engine implementations.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any
from pydantic import BaseModel, Field


class BarcodeZoneSpec(BaseModel):
    """Normalized barcode reservation coordinates."""
    x: float = Field(..., description="X coordinate of barcode origin in inches")
    y: float = Field(..., description="Y coordinate of barcode origin in inches")
    width: float = Field(..., description="Width of barcode reservation box in inches")
    height: float = Field(..., description="Height of barcode reservation box in inches")

    model_config = {"frozen": True}


class WorkerSpecifications(BaseModel):
    """Pure physical specification payload — tool-agnostic and unified across workers."""
    units: str = Field(default="in", description="Unit of measurement: in, mm, pt")
    book_format: str = Field(..., description="Format: paperback, hardcover")
    publisher: str | None = Field(default=None, description="Target publisher e.g. kdp, ingramspark, lulu")
    trim_width: float = Field(..., description="Trim width in units")
    trim_height: float = Field(..., description="Trim height in units")
    page_count: int | None = Field(default=None, description="Interior page count")

    # Cover specifications (populated for cover_worker)
    full_cover_width: float | None = Field(default=None, description="Total cover spread width including bleed & wrap")
    full_cover_height: float | None = Field(default=None, description="Total cover spread height including bleed & wrap")
    spine_width: float | None = Field(default=None, description="Calculated spine panel width")
    front_cover_width: float | None = Field(default=None, description="Front cover panel width")
    front_cover_height: float | None = Field(default=None, description="Front cover panel height")
    back_cover_width: float | None = Field(default=None, description="Back cover panel width")
    back_cover_height: float | None = Field(default=None, description="Back cover panel height")
    bleed: float | None = Field(default=None, description="Cover bleed per edge")
    wrap: float | None = Field(default=None, description="Hardcover wrap allowance")
    hinge_allowance: float | None = Field(default=None, description="Hardcover hinge allowance")
    spine_text_allowed: bool | None = Field(default=None, description="Whether spine text is permitted")
    spine_safe_margin: float | None = Field(default=None, description="Spine text safety margin per edge")
    spine_left_x: float | None = Field(default=None, description="Canvas X coordinate where spine begins")
    spine_right_x: float | None = Field(default=None, description="Canvas X coordinate where spine ends")
    safe_margin_top: float | None = Field(default=None, description="Top safe area margin")
    safe_margin_bottom: float | None = Field(default=None, description="Bottom safe area margin")
    safe_margin_outside: float | None = Field(default=None, description="Outside trim safe area margin")
    barcode_zone: dict[str, float] | None = Field(default=None, description="Barcode reservation zone {x, y, width, height}")
    cover_finish: str | None = Field(default=None, description="Cover laminate finish: matte, glossy")

    # Interior specifications (populated for formatter)
    interior_page_width: float | None = Field(default=None, description="Page width including interior bleed")
    interior_page_height: float | None = Field(default=None, description="Page height including interior bleed")
    has_bleed: bool | None = Field(default=None, description="Whether interior extends to bleed edge")
    interior_bleed_amount: float | None = Field(default=None, description="Interior bleed amount per side")
    interior_bleed_top: float | None = Field(default=None, description="Interior top bleed")
    interior_bleed_bottom: float | None = Field(default=None, description="Interior bottom bleed")
    interior_bleed_outside: float | None = Field(default=None, description="Interior outside bleed")
    interior_bleed_inside: float | None = Field(default=None, description="Interior inside/gutter bleed")
    min_inside_margin: float | None = Field(default=None, description="Stepped minimum inside/gutter margin")
    min_outside_margin: float | None = Field(default=None, description="Minimum outside margin")
    min_top_margin: float | None = Field(default=None, description="Minimum top margin")
    min_bottom_margin: float | None = Field(default=None, description="Minimum bottom margin")
    interior_ink: str | None = Field(default=None, description="Interior ink type: B&W, Standard Color, Premium Color")
    paper_type: str | None = Field(default=None, description="Paper stock identifier")

    # Publisher / Package specifications (populated for publisher worker)
    binding: str | None = Field(default=None, description="Binding type")
    distribution_goal: str | None = Field(default=None, description="Distribution target")
    economics: dict[str, Any] | None = Field(default=None, description="Print cost and royalty projections")

    model_config = {"extra": "allow"}


class WorkerSpecificationPayload(BaseModel):
    """Universal canonical JSON specification envelope."""
    event: str = Field(default="asset.regeneration_required", description="Event name triggering this specification")
    book_id: str = Field(..., description="Unique book identifier")
    worker_type: str = Field(..., description="Target worker: cover_worker, formatter, publisher")
    priority: str = Field(default="HIGH", description="Task priority: HIGH, NORMAL, LOW")
    triggers: list[str] = Field(default_factory=list, description="Configuration changes triggering this payload")
    specifications: WorkerSpecifications = Field(..., description="Tool-agnostic physical and layout specifications")
    output_storage_bucket: str | None = Field(default=None, description="Supabase Storage bucket where the worker should upload the result")
    output_storage_path: str | None = Field(default=None, description="Object path template for the output file")
    existing_asset_url: str | None = Field(default=None, description="URL of the current asset version (for re-analysis after regeneration)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Payload timestamp")
    schema_version: str = Field(default="1.0.0", description="Contract schema semantic version")
