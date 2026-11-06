from __future__ import annotations
from datetime import datetime, UTC
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from .enums import (
    Publisher, BookFormat, BindingType, InteriorInk,
    PaperType, CoverFinish, AssetType, AssetState, DistributionGoal,
)
from .geometry import TrimSize, CalculatedSpecification
from .analysis import AssetInspectionReport
from .validation import AssetValidationResult


class BookConfiguration(BaseModel):
    """Platform-independent book configuration.
    
    Represents the user's selected book specifications
    before publisher-specific rules are applied.
    """
    publisher: Publisher | None = Field(default=None, description="Target publishing platform")
    book_format: BookFormat = Field(..., description="Paperback or Hardcover")
    binding: BindingType | None = Field(default=None, description="Binding type")
    trim_size: TrimSize = Field(..., description="Book trim dimensions")
    page_count: int = Field(..., gt=0, description="Number of interior pages")
    interior_ink: InteriorInk = Field(default=InteriorInk.BW, description="Interior color type")
    paper_type: PaperType = Field(default=PaperType.WHITE, description="Paper stock")
    cover_finish: CoverFinish = Field(default=CoverFinish.MATTE, description="Cover lamination finish")
    has_bleed: bool = Field(default=False, description="Whether interior has bleed")
    reading_direction: str = Field(default="ltr", description="Reading direction: 'ltr' or 'rtl'")
    duplex_cover: bool = Field(default=False, description="IngramSpark exclusive: whether inside cover is printed (duplex)")
    perforated_pages: bool = Field(default=False, description="IngramSpark exclusive: whether interior pages are perforated")
    distribution_goal: DistributionGoal | None = Field(default=None, description="Distribution target: Direct or Global/Retail")
    wholesale_discount: float | None = Field(default=None, ge=0.0, le=1.0, description="Custom wholesale discount fraction (e.g. 0.0 to 0.55)")
    include_market_access_fee: bool = Field(
        default=True,
        description=(
            "Whether to deduct the IngramSpark 1.875% Market Access Fee. IngramSpark charges it on every "
            "distributed sale (help 5338716228365 / 41657495062029), so it defaults to True (Astra N9)."
        ),
    )
    currency: str | None = Field(default=None, description="Preferred currency code e.g. USD, GBP, AUD, EUR")
    isbn: str | None = Field(default=None, description="Assigned ISBN (10 or 13 digits)")

    @field_validator("cover_finish", mode="before")
    @classmethod
    def _normalize_cover_finish(cls, v):
        if isinstance(v, CoverFinish):
            return v
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if "gloss" in v_lower:
                return CoverFinish.GLOSS
            elif "matte" in v_lower:
                return CoverFinish.MATTE
            elif "textured" in v_lower:
                return CoverFinish.TEXTURED
        return v

    @field_validator("binding", mode="before")
    @classmethod
    def _normalize_binding(cls, v):
        if isinstance(v, BindingType) or v is None:
            return v
        if isinstance(v, str):
            v_lower = v.strip().lower()
            # Exact enum values first so model_dump(mode="json") round-trips (Astra N14).
            for member in BindingType:
                if v_lower == member.value.lower():
                    return member
            # Most specific substrings first: "Linen Wrap + Dust Jacket" contains
            # "jacket", and "Jacketed Case Laminate" contains "case laminate".
            if "linen" in v_lower:
                return BindingType.LINEN_WRAP_DUST_JACKET
            elif "jacket" in v_lower:
                return BindingType.JACKETED_CASE_LAMINATE
            elif "case laminate" in v_lower or "casewrap" in v_lower:
                return BindingType.CASEWRAP
            elif "digital cloth" in v_lower or "cloth" in v_lower:
                return BindingType.DIGITAL_CLOTH
            elif "perfect" in v_lower:
                return BindingType.PERFECT_BOUND
            elif "coil" in v_lower:
                return BindingType.COIL
            elif "saddle" in v_lower:
                return BindingType.SADDLE_STITCH
        return v

    @field_validator("interior_ink", mode="before")
    @classmethod
    def _normalize_interior_ink(cls, v):
        if isinstance(v, InteriorInk):
            return v
        if isinstance(v, str):
            v_lower = v.strip().lower()
            for member in InteriorInk:
                if v_lower == member.value.lower():
                    return member
            if "b&w" in v_lower or "black" in v_lower or "mono" in v_lower:
                return InteriorInk.BW
            elif "ultra" in v_lower:
                return InteriorInk.ULTRA_PREMIUM_COLOR
            elif "premium" in v_lower:
                return InteriorInk.PREMIUM_COLOR
            elif "standard" in v_lower:
                return InteriorInk.STANDARD_COLOR
            elif "color" in v_lower or "colour" in v_lower:
                return InteriorInk.COLOR
        return v

    @field_validator("paper_type", mode="before")
    @classmethod
    def _normalize_paper_type(cls, v):
        # Plain "crème"/"creme" is the same stock as "cream". PaperType.CREME is kept
        # for enum compatibility but always normalised to CREAM so that accented
        # input is accepted exactly like "cream" by every publisher (Astra N14).
        if v is PaperType.CREME:
            return PaperType.CREAM
        if isinstance(v, PaperType):
            return v
        if isinstance(v, str):
            v_lower = v.strip().lower()
            for member in PaperType:
                if v_lower == member.value.lower():
                    return PaperType.CREAM if member is PaperType.CREME else member
            if "ultra" in v_lower:
                return PaperType.ULTRA_PREMIUM_COLOR
            elif "premium" in v_lower and ("color" in v_lower or "colour" in v_lower):
                return PaperType.PREMIUM_COLOR
            elif "color 50" in v_lower or "colour 50" in v_lower:
                return PaperType.COLOR_50
            elif "color 70" in v_lower or "colour 70" in v_lower:
                return PaperType.COLOR_70
            elif "crème 50lb" in v_lower or "creme 50lb" in v_lower:
                return PaperType.CREME_50LB
            elif "creme" in v_lower or "crème" in v_lower or "cream" in v_lower:
                return PaperType.CREAM
            elif "groundwood 38lb" in v_lower or "56gsm" in v_lower:
                return PaperType.GROUNDWOOD_38LB
            elif "groundwood" in v_lower or "38" in v_lower:
                return PaperType.GROUNDWOOD
            elif "white 70lb" in v_lower or "104gsm" in v_lower:
                return PaperType.WHITE_70LB
            elif "white 70" in v_lower or "70# white" in v_lower:
                return PaperType.WHITE_70
            elif "white 50lb" in v_lower or ("white" in v_lower and "74gsm" in v_lower):
                return PaperType.WHITE_50LB
            elif "white 50" in v_lower or "50# white" in v_lower:
                return PaperType.WHITE_50
            elif "70" in v_lower:
                return PaperType.WHITE_70 if "white" in v_lower else PaperType.COLOR_70
            elif "coated" in v_lower or "premium white" in v_lower or "80" in v_lower:
                return PaperType.COATED_WHITE
            elif "white" in v_lower or "50" in v_lower:
                return PaperType.WHITE
        return v


    @property
    def trim_width(self) -> float:
        return self.trim_size.width

    @property
    def trim_height(self) -> float:
        return self.trim_size.height

    @property
    def trim_is_custom(self) -> bool:
        return self.trim_size.is_custom


class Asset(BaseModel):
    """Represents a book asset (cover PDF, interior PDF)."""
    asset_type: AssetType
    file_path: str | None = Field(default=None)
    storage_url: str | None = Field(default=None, description="Remote storage URL (Supabase/S3) where this asset is stored")
    storage_bucket: str | None = Field(default=None, description="Storage bucket name (e.g. 'book-covers', 'book-interiors')")
    storage_object_path: str | None = Field(default=None, description="Object path within the bucket")
    state: AssetState = Field(default=AssetState.NOT_GENERATED)
    detected_properties: dict | None = Field(default=None, description="Properties extracted from the actual file")
    inspection_report: AssetInspectionReport | None = Field(default=None, description="Detailed inspection report")
    validation_result: AssetValidationResult | None = Field(default=None, description="Latest validation result for this asset")


class BookMetadata(BaseModel):
    """Non-publishing metadata about the book."""
    book_id: str | None = Field(default=None, description="Unique book identifier")
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Book(BaseModel):
    """Aggregate root representing a complete book with its configuration,
    metadata, assets, and optionally its calculated specifications."""
    metadata: BookMetadata = Field(default_factory=BookMetadata)
    configuration: BookConfiguration
    assets: list[Asset] = Field(default_factory=list)
    calculated_spec: CalculatedSpecification | None = None
