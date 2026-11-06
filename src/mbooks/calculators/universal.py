"""Universal/Generic physical specifications calculator for pre-publisher selection."""

from __future__ import annotations
from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import BookFormat
from mbooks.domain.geometry import (
    SpineSpecification,
    CoverDimensions,
    InteriorDimensions,
)
from mbooks.domain.economics import PrintEconomics
from .base import BasePublisherCalculator
from .tables import (
    UNIVERSAL_PAPER_CALIPER,
    UNIVERSAL_COVER_BLEED,
    UNIVERSAL_INTERIOR_BLEED,
    UNIVERSAL_SPINE_TEXT_MIN_PAGES,
    UNIVERSAL_SPINE_SAFE_MARGIN,
    KDP_GUTTER_BANDS,
    check_page_count_bounds,
)


class UniversalCalculator(BasePublisherCalculator):
    """Generic publishing specifications calculator used when no target publisher is selected."""

    @property
    def publisher_name(self) -> str:
        return "Universal"

    def calculate_spine(self, config: BookConfiguration) -> SpineSpecification:
        check_page_count_bounds(config.page_count, 1200, "Universal")
        spine_width = round(config.page_count * UNIVERSAL_PAPER_CALIPER, 4)
        text_allowed = config.page_count >= UNIVERSAL_SPINE_TEXT_MIN_PAGES
        safe_margin = UNIVERSAL_SPINE_SAFE_MARGIN if text_allowed else None

        return SpineSpecification(
            width=spine_width,
            spine_text_allowed=text_allowed,
            min_pages_for_text=UNIVERSAL_SPINE_TEXT_MIN_PAGES,
            safe_margin=safe_margin,
            page_multiplier=UNIVERSAL_PAPER_CALIPER,
            hinge_allowance=0.0,
            unit="in",
        )

    def calculate_cover(
        self, config: BookConfiguration, spine: SpineSpecification | None = None
    ) -> CoverDimensions:
        if spine is None:
            spine = self.calculate_spine(config)

        trim_w = config.trim_width
        trim_h = config.trim_height
        is_hardcover = config.book_format == BookFormat.HARDCOVER
        bleed = UNIVERSAL_COVER_BLEED

        if not is_hardcover:
            wrap = 0.0
            hinge = 0.0
            full_w = round((2 * trim_w) + spine.width + (2 * bleed), 4)
            full_h = round(trim_h + (2 * bleed), 4)
            front_w = trim_w
            front_h = trim_h
            back_w = trim_w
            back_h = trim_h
            spine_left_x = round(bleed + trim_w, 4)
            spine_right_x = round(spine_left_x + spine.width, 4)
        else:
            wrap = 0.625
            hinge = 0.250
            board_overhang = 0.250
            full_w = round((2 * (trim_w + hinge)) + spine.width + (2 * wrap), 4)
            full_h = round(trim_h + board_overhang + (2 * wrap), 4)
            front_w = round(trim_w + hinge, 4)
            front_h = round(trim_h + board_overhang, 4)
            back_w = round(trim_w + hinge, 4)
            back_h = round(trim_h + board_overhang, 4)
            spine_left_x = round(wrap + back_w, 4)
            spine_right_x = round(spine_left_x + spine.width, 4)

        ref_offset = wrap if is_hardcover else bleed
        barcode_box = {
            "x": round(spine_left_x - 0.250 - 2.0, 4),
            "y": round(ref_offset + 0.250, 4),
            "width": 2.0,
            "height": 1.2,
        }

        return CoverDimensions(
            full_width=full_w,
            full_height=full_h,
            front_cover_width=front_w,
            front_cover_height=front_h,
            back_cover_width=back_w,
            back_cover_height=back_h,
            spine_width=spine.width,
            bleed=bleed,
            wrap=wrap,
            hinge_allowance=hinge,
            spine_text_allowed=spine.spine_text_allowed,
            spine_safe_margin=spine.safe_margin,
            spine_left_x=spine_left_x,
            spine_right_x=round(spine_left_x + spine.width, 4),
            safe_margin_top=0.125,
            safe_margin_bottom=0.125,
            safe_margin_outside=0.125,
            front_cover_safe_width=round(front_w - 0.125, 4),
            front_cover_safe_height=round(front_h - 0.25, 4),
            spine_safe_width=round(max(0.0, spine.width - (2 * (spine.safe_margin or 0.0625))), 4),
            spine_safe_height=round(front_h - 0.25, 4),
            spine_margin=spine.safe_margin or 0.0625,
            barcode_margin=0.250,
            barcode_zone=barcode_box,
            unit="in",
        )

    def calculate_interior(self, config: BookConfiguration) -> InteriorDimensions:
        trim_w = config.trim_width
        trim_h = config.trim_height

        pages = config.page_count
        gutter = 0.375
        for min_p, max_p, g_val in KDP_GUTTER_BANDS:
            if pages <= max_p:
                gutter = g_val
                break
        else:
            gutter = 0.875

        if config.has_bleed:
            page_w = round(trim_w + UNIVERSAL_INTERIOR_BLEED, 4)
            page_h = round(trim_h + (2 * UNIVERSAL_INTERIOR_BLEED), 4)
            return InteriorDimensions(
                page_width=page_w,
                page_height=page_h,
                trim_width=trim_w,
                trim_height=trim_h,
                has_bleed=True,
                bleed_amount=UNIVERSAL_INTERIOR_BLEED,
                bleed_top=UNIVERSAL_INTERIOR_BLEED,
                bleed_bottom=UNIVERSAL_INTERIOR_BLEED,
                bleed_outside=UNIVERSAL_INTERIOR_BLEED,
                bleed_inside=0.0,
                min_inside_margin=gutter,
                min_outside_margin=0.375,
                min_top_margin=0.375,
                min_bottom_margin=0.375,
                unit="in",
            )
        else:
            return InteriorDimensions(
                page_width=trim_w,
                page_height=trim_h,
                trim_width=trim_w,
                trim_height=trim_h,
                has_bleed=False,
                bleed_amount=0.0,
                bleed_top=0.0,
                bleed_bottom=0.0,
                bleed_outside=0.0,
                bleed_inside=0.0,
                min_inside_margin=gutter,
                min_outside_margin=0.250,
                min_top_margin=0.250,
                min_bottom_margin=0.250,
                unit="in",
            )

    def calculate_economics(
        self, config: BookConfiguration, list_price: float | None = None
    ) -> PrintEconomics | None:
        # Without a target publisher, economics cannot be deterministically estimated
        return None
