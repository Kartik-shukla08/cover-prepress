"""Domain models for asset file inspection and technical property extraction."""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field

from .enums import AssetType


class FontInspectionInfo(BaseModel):
    """Details of a font identified within a PDF document."""
    name: str = Field(..., description="Font name as declared in PDF")
    font_type: str = Field(default="Unknown", description="Font format type (e.g. Type1, TrueType, OpenType, Type3)")
    is_embedded: bool = Field(default=False, description="Whether the font file/data is fully or subset embedded")
    is_subset: bool = Field(default=False, description="Whether the font is a subset (indicated by 6-char prefix +)")
    pages_used: list[int] = Field(default_factory=list, description="1-indexed page numbers where this font appears")


class ImageInspectionInfo(BaseModel):
    """Details and resolution metrics for an image raster placement."""
    image_xref: int = Field(..., description="PDF XRef object number for image")
    page_number: int = Field(..., description="1-indexed page number containing the image")
    pixel_width: int = Field(..., description="Raw image width in pixels")
    pixel_height: int = Field(..., description="Raw image height in pixels")
    placement_rect_pt: list[float] = Field(..., description="Placement rect on page [x0, y0, x1, y1] in points")
    placement_width_in: float = Field(..., description="Placement width on page in inches")
    placement_height_in: float = Field(..., description="Placement height on page in inches")
    dpi_x: float = Field(..., description="Effective horizontal DPI based on scale")
    dpi_y: float = Field(..., description="Effective vertical DPI based on scale")
    effective_dpi: float = Field(..., description="Minimum of horizontal and vertical DPI")
    colorspace: str | None = Field(default=None, description="Image color space (e.g. DeviceRGB, DeviceCMYK, DeviceGray)")
    is_low_res: bool = Field(default=False, description="True if effective DPI is below 300 DPI")
    is_critical_low_res: bool = Field(default=False, description="True if effective DPI is below 150 DPI")


class BleedSliverBreachInfo(BaseModel):
    """Details of an image crossing the trim line but stopping short of bleed boundary."""
    page_number: int = Field(..., description="1-indexed page number")
    image_xref: int = Field(..., description="PDF image xref")
    edge: str = Field(..., description="Trim edge: 'top', 'bottom', 'outside_left', 'outside_right'")
    gap_distance_in: float = Field(..., description="Gap between image edge and outer bleed boundary in inches")
    bbox_pt: list[float] = Field(default_factory=list, description="Image placement rect in points")
    bbox_in: list[float] = Field(default_factory=list, description="Image placement rect in inches")


# Alias for contract compatibility
BleedSliverInfo = BleedSliverBreachInfo


class RectInfo(BaseModel):
    """Geometric bounding box representation with point and inch coordinates for vector elements."""
    bbox_pt: list[float] = Field(..., description="[x0, y0, x1, y1] in points")
    bbox_in: list[float] = Field(..., description="[x0, y0, x1, y1] in inches")
    glyph_count: int = Field(default=1, description="Number of glyph paths clustered in this bounding box")
    breach_side: str = Field(default="", description="Side of safe area encroachment")
    breach_distance_in: float = Field(default=0.0, description="Breach distance in inches")


class SafeAreaBreachInfo(BaseModel):
    """Details of a text or glyph element encroaching outside the live area safe rectangle."""
    page_number: int = Field(..., description="1-indexed page number")
    breach_side: str = Field(..., description="Side of encroachment: 'top', 'bottom', 'inside_gutter', 'outside_trim'")
    breach_distance_in: float = Field(..., description="Distance in inches breached beyond the safe margin")
    text_snippet: str = Field(default="", description="Snippet of text encroaching into the safety margin")
    bbox_pt: list[float] = Field(default_factory=list, description="Element bounding box [x0, y0, x1, y1] in points")
    bbox_in: list[float] = Field(default_factory=list, description="Element bounding box [x0, y0, x1, y1] in inches")
    is_outlined_text: bool = Field(default=False, description="True if breach is caused by converted vector curves / outlined text")
    glyph_count: int = Field(default=0, description="Number of glyph paths clustered in this breach")


class PageInspectionInfo(BaseModel):
    """Technical dimensions and content layout metrics for an individual page."""
    page_number: int = Field(..., description="1-indexed page number")
    width_pt: float = Field(..., description="Page width in points (72 pt/in)")
    height_pt: float = Field(..., description="Page height in points (72 pt/in)")
    width_in: float = Field(..., description="Page width in inches")
    height_in: float = Field(..., description="Page height in inches")
    mediabox: list[float] = Field(..., description="PDF MediaBox [x0, y0, x1, y1]")
    cropbox: list[float] = Field(..., description="PDF CropBox [x0, y0, x1, y1]")
    content_bbox_pt: list[float] | None = Field(default=None, description="Content bounding box [x0, y0, x1, y1] in points")
    content_bbox_in: list[float] | None = Field(default=None, description="Content bounding box [x0, y0, x1, y1] in inches")
    top_margin_in: float | None = Field(default=None, description="Distance from top edge to content in inches")
    bottom_margin_in: float | None = Field(default=None, description="Distance from bottom edge to content in inches")
    left_margin_in: float | None = Field(default=None, description="Distance from left edge to content in inches")
    right_margin_in: float | None = Field(default=None, description="Distance from right edge to content in inches")
    inside_margin_in: float | None = Field(default=None, description="Inside/gutter margin (left on odd, right on even pages)")
    outside_margin_in: float | None = Field(default=None, description="Outside/trim margin (right on odd, left on even pages)")
    live_area_bbox_in: list[float] | None = Field(default=None, description="Calculated Live Safe Rectangle [x0, y0, x1, y1] in inches")
    has_color: bool = Field(default=False, description="Whether this page contains color elements (text, vectors, images)")
    font_count: int = Field(default=0, description="Number of distinct fonts used on this page")
    image_count: int = Field(default=0, description="Number of images placed on this page")
    safe_area_breaches: list[SafeAreaBreachInfo] = Field(default_factory=list, description="Text safe area encroachment breaches on this page")
    has_safe_area_breach: bool = Field(default=False, description="True if any text element breaches the safe live area")
    has_transparency: bool = Field(default=False, description="True if this page contains unflattened transparency / blend modes")

    # R1: TAC & Registration Black
    max_tac_pct: float | None = Field(default=None, description="Maximum CMYK Total Area Coverage on page (0.0 to 400.0%)")
    has_tac_breach: bool = Field(default=False, description="True if page TAC exceeds the 240% ceiling")
    has_registration_black: bool = Field(default=False, description="True if 400% registration black is detected on this page")

    # R2: Bleed Slivers
    bleed_slivers: list[BleedSliverBreachInfo] = Field(default_factory=list, description="Bleed edge slivers detected on this page")
    has_bleed_sliver: bool = Field(default=False, description="True if any image crosses trim but stops short of bleed boundary")

    # R4: Outlined Text & Blank Page
    is_blank: bool = Field(default=False, description="True if page contains no visible text, images, or content drawings")
    outlined_text_encroachments: list[RectInfo] = Field(default_factory=list, description="Outlined text vector glyphs breaching safe area")
    has_outlined_text_breach: bool = Field(default=False, description="True if outlined text encroaches safe margin")


class ColorInspectionInfo(BaseModel):
    """Color profile, vector/raster chromatic analysis, and CMYK vs RGB breakdown."""
    is_color: bool = Field(default=False, description="True if any color content is detected anywhere in the document")
    total_color_pages: int = Field(default=0, description="Count of pages containing color")
    color_page_numbers: list[int] = Field(default_factory=list, description="List of 1-indexed page numbers containing color")
    detected_colorspaces: list[str] = Field(default_factory=list, description="Unique color spaces detected across elements")
    has_rgb: bool = Field(default=False, description="True if DeviceRGB raster or vector content is present")
    has_cmyk: bool = Field(default=False, description="True if DeviceCMYK raster or vector content is present")
    has_grayscale: bool = Field(default=False, description="True if DeviceGray/monochrome content is present")
    has_spot_colors: bool = Field(default=False, description="True if Separation/DeviceN spot color plates are detected")
    rgb_image_count: int = Field(default=0, description="Number of raster images in DeviceRGB/sRGB")
    cmyk_image_count: int = Field(default=0, description="Number of raster images in DeviceCMYK")
    grayscale_image_count: int = Field(default=0, description="Number of raster images in DeviceGray")
    rgb_vector_count: int = Field(default=0, description="Number of vector shapes defined in RGB")
    cmyk_vector_count: int = Field(default=0, description="Number of vector shapes defined in CMYK")
    spot_color_names: list[str] = Field(default_factory=list, description="Names of detected spot color plates")
    icc_profile_names: list[str] = Field(default_factory=list, description="Names of embedded ICC color output profiles")

    # R1 Extensions
    max_tac_pct: float | None = Field(default=None, description="Highest TAC percentage detected across all pages")
    pages_exceeding_tac: list[int] = Field(default_factory=list, description="1-indexed page numbers exceeding 240% TAC limit")
    pages_with_registration_black: list[int] = Field(default_factory=list, description="1-indexed page numbers containing 400% registration black")
    has_tac_breach: bool = Field(default=False, description="True if any page exceeds 240% TAC ceiling")
    has_registration_black: bool = Field(default=False, description="True if 400% registration black is detected")


class SpineZoneInspectionInfo(BaseModel):
    """Spine panel analysis for cover files."""
    spine_bbox_in: list[float] = Field(..., description="Estimated or calculated spine boundary [x0, y0, x1, y1] in inches")
    spine_text_detected: bool = Field(default=False, description="Whether text was detected inside the spine zone")
    detected_text: list[str] = Field(default_factory=list, description="Text strings detected inside the spine panel")
    text_within_safe_margin: bool = Field(default=True, description="Whether spine text respects safety margin from fold lines")
    min_margin_to_spine_fold_in: float | None = Field(default=None, description="Minimum distance from text to spine folds in inches")


class BarcodeZoneInspectionInfo(BaseModel):
    """Barcode quiet zone collision and symbology analysis on cover spread."""
    barcode_bbox_in: list[float] = Field(..., description="Reserved barcode quiet zone [x0, y0, x1, y1] in inches")
    barcode_bbox_pt: list[float] = Field(default_factory=list, description="Reserved barcode quiet zone [x0, y0, x1, y1] in points")
    collision_detected: bool = Field(default=False, description="True if user text or artwork collides with barcode quiet zone")
    colliding_text_snippets: list[str] = Field(default_factory=list, description="Text snippets found inside barcode quiet zone")
    colliding_element_count: int = Field(default=0, description="Number of non-background elements colliding with quiet zone")

    # R3 Symbology Additions
    barcode_detected: bool = Field(default=False, description="True if a 1D barcode was detected in the quiet zone")
    symbology: str | None = Field(default=None, description="Decoded barcode symbology (e.g. 'EAN-13')")
    decoded_value: str | None = Field(default=None, description="Decoded 13-digit EAN-13 / ISBN string")
    decoded_isbn: str | None = Field(default=None, description="Decoded 13-digit EAN-13 / ISBN string (alias for decoded_value)")
    check_digit_valid: bool | None = Field(default=None, description="True if check digit matches computed modulo-10 algorithm")
    assigned_isbn_match: bool | None = Field(default=None, description="True if decoded barcode matches configured ISBN")
    isbn_matches: bool | None = Field(default=None, description="True if decoded barcode matches configured ISBN (alias for assigned_isbn_match)")
    decoding_error: str | None = Field(default=None, description="Diagnostic error message if barcode decoding or verification fails")


class PdfConformanceInfo(BaseModel):
    """PDF standard conformance (PDF/X) and transparency flattening inspection."""
    pdf_x_standard: str | None = Field(default=None, description="Identified PDF/X standard (e.g. 'PDF/X-1a:2001', 'PDF/X-3:2002', 'PDF/X-4')")
    is_pdf_x_compliant: bool = Field(default=False, description="True if document contains valid PDF/X OutputIntent metadata")
    output_intent_profile: str | None = Field(default=None, description="OutputConditionIdentifier or ICC profile name from OutputIntents")
    has_transparency: bool = Field(default=False, description="True if unflattened transparency groups or blend modes are detected")
    unflattened_transparency_pages: list[int] = Field(default_factory=list, description="Pages containing unflattened transparency")
    transparency_details: list[str] = Field(default_factory=list, description="Details of transparency mechanisms found")


class AssetInspectionReport(BaseModel):
    """Comprehensive technical inspection report for a PDF asset."""
    asset_type: AssetType = Field(..., description="Interior or Cover asset")
    file_path: str | None = Field(default=None, description="Source file path if inspected from disk")
    file_size_bytes: int | None = Field(default=None, description="File size in bytes")
    pdf_version: str | None = Field(default=None, description="PDF format specification version (e.g. '1.7')")
    is_encrypted: bool = Field(default=False, description="Whether document is password protected / encrypted")
    page_count: int = Field(..., description="Total number of pages in the PDF")
    uniform_page_dimensions: bool = Field(default=True, description="True if all pages have identical dimensions")
    min_width_in: float = Field(..., description="Smallest page width in inches")
    max_width_in: float = Field(..., description="Largest page width in inches")
    avg_width_in: float = Field(..., description="Average page width in inches")
    min_height_in: float = Field(..., description="Smallest page height in inches")
    max_height_in: float = Field(..., description="Largest page height in inches")
    avg_height_in: float = Field(..., description="Average page height in inches")
    
    # Fonts
    fonts: list[FontInspectionInfo] = Field(default_factory=list, description="All fonts detected in document")
    all_fonts_embedded: bool = Field(default=True, description="True if every font in the document is embedded")
    unembedded_fonts: list[str] = Field(default_factory=list, description="Names of un-embedded fonts")
    
    # Images & DPI
    images: list[ImageInspectionInfo] = Field(default_factory=list, description="All image placements inspected")
    min_image_dpi: float | None = Field(default=None, description="Lowest effective image DPI found across the document")
    has_low_dpi_images: bool = Field(default=False, description="True if any image has DPI < 300")
    has_critical_low_dpi_images: bool = Field(default=False, description="True if any image has DPI < 150")
    
    # Color & TAC
    color: ColorInspectionInfo = Field(default_factory=ColorInspectionInfo)
    max_tac_pct: float | None = Field(default=None, description="Convenience copy of highest TAC percentage across pages")
    has_tac_breach: bool = Field(default=False, description="True if any page exceeds 240% TAC limit")
    has_registration_black: bool = Field(default=False, description="True if 400% registration black is detected")
    pages_exceeding_tac: list[int] = Field(default_factory=list, description="Page numbers with TAC > 240%")
    pages_with_registration_black: list[int] = Field(default_factory=list, description="Page numbers with registration black")
    
    # Margins & Gutters (Interior)
    min_inside_margin_in: float | None = Field(default=None, description="Smallest inside/gutter margin detected across pages")
    min_outside_margin_in: float | None = Field(default=None, description="Smallest outside margin detected across pages")
    min_top_margin_in: float | None = Field(default=None, description="Smallest top margin detected across pages")
    min_bottom_margin_in: float | None = Field(default=None, description="Smallest bottom margin detected across pages")
    
    # Live Content & Safe Area
    has_safe_area_breaches: bool = Field(default=False, description="True if any text encroaches into unsafe cut/gutter margins")
    total_safe_area_breaches: int = Field(default=0, description="Total number of safe area encroachments detected")
    breached_page_numbers: list[int] = Field(default_factory=list, description="Pages containing safe area margin encroachments")

    # R2: Bleed Edge Slivers
    bleed_slivers: list[BleedSliverBreachInfo] = Field(default_factory=list, description="All detected bleed edge slivers")
    total_bleed_slivers: int = Field(default=0, description="Count of detected image bleed edge slivers")
    bleed_sliver_pages: list[int] = Field(default_factory=list, description="Page numbers containing bleed edge slivers")
    has_bleed_slivers: bool = Field(default=False, description="True if any image bleed edge sliver exists")

    # R4: Blank Page Runs
    blank_page_numbers: list[int] = Field(default_factory=list, description="1-indexed numbers of blank pages")
    blank_page_runs: list[list[int]] = Field(default_factory=list, description="Consecutive blank page runs")
    excessive_blank_page_runs: list[list[int]] = Field(default_factory=list, description="Consecutive blank runs exceeding 2 pages")
    has_excessive_blank_pages: bool = Field(default=False, description="True if any blank page sequence exceeds 2 pages")

    # PDF/X & Transparency Conformance
    conformance: PdfConformanceInfo = Field(default_factory=PdfConformanceInfo, description="PDF/X and transparency conformance")

    # Detailed page data
    pages: list[PageInspectionInfo] = Field(default_factory=list, description="Detailed metrics per page")
    
    # Remote Storage Metadata (Phase 8.3)
    source_url: str | None = Field(default=None, description="Remote storage URL if asset was analyzed from Supabase/S3")
    storage_provider: str | None = Field(default=None, description="Detected provider: supabase, aws_s3, cloudflare_r2, generic_http")

    # Cover-specific inspections
    spine_info: SpineZoneInspectionInfo | None = Field(default=None, description="Spine zone inspection for cover files")
    barcode_info: BarcodeZoneInspectionInfo | None = Field(default=None, description="Barcode quiet zone inspection for cover files")
