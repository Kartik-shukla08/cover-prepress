"""Amazon KDP physical specifications and economics calculator."""

from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import BookFormat, DistributionGoal, InteriorInk, PaperType
from mbooks.domain.geometry import (
    SpineSpecification,
    CoverDimensions,
    InteriorDimensions,
    CalculatedSpecification,
)
from mbooks.domain.economics import PrintEconomics
from .base import BasePublisherCalculator
from .tables import (
    get_kdp_spine_multiplier,
    KDP_SPINE_HINGE_CONSTANT,
    KDP_SPINE_TEXT_MIN_PAGES,
    KDP_SPINE_SAFE_MARGIN,
    KDP_COVER_BLEED,
    KDP_INTERIOR_BLEED_SIDE,
    KDP_HARDCOVER_WRAP,
    KDP_HARDCOVER_HINGE,
    KDP_HARDCOVER_BOARD_OVERHANG_W,
    KDP_HARDCOVER_BOARD_OVERHANG_H,
    KDP_HARDCOVER_SPINE_ALLOWANCE,
    KDP_HARDCOVER_BARCODE_MARGIN_H,
    KDP_GUTTER_BANDS,
    KDP_MIN_OUTSIDE_MARGIN_NO_BLEED,
    KDP_MIN_OUTSIDE_MARGIN_BLEED,
    KDP_REGULAR_TRIM_MAX_W,
    KDP_REGULAR_TRIM_MAX_H,
    KDP_PAPERBACK_FIXED_BASE,
    KDP_HARDCOVER_FIXED_BASE,
    KDP_BW_SHORT_PAGE_THRESHOLD,
    KDP_BW_SHORT_PAGE_THRESHOLD_GROUNDWOOD,
    KDP_PREMIUM_COLOR_SHORT_PAGE_THRESHOLD,
    KDP_HARDCOVER_BW_SHORT_PAGE_THRESHOLD,
    KDP_BW_REGULAR_SHORT_FLAT,
    KDP_BW_REGULAR_SHORT_FLAT_GROUNDWOOD,
    KDP_BW_LARGE_SHORT_FLAT,
    KDP_BW_LARGE_SHORT_FLAT_GROUNDWOOD,
    KDP_PREMIUM_COLOR_REGULAR_SHORT_FLAT,
    KDP_PREMIUM_COLOR_LARGE_SHORT_FLAT,
    KDP_HARDCOVER_BW_REGULAR_SHORT_FLAT,
    KDP_HARDCOVER_BW_LARGE_SHORT_FLAT,
    KDP_BW_REGULAR_PER_PAGE,
    KDP_BW_REGULAR_PER_PAGE_GROUNDWOOD,
    KDP_BW_LARGE_PER_PAGE,
    KDP_BW_LARGE_PER_PAGE_GROUNDWOOD,
    KDP_STANDARD_COLOR_REGULAR_PER_PAGE,
    KDP_STANDARD_COLOR_LARGE_PER_PAGE,
    KDP_STANDARD_COLOR_PER_PAGE,
    KDP_PREMIUM_COLOR_REGULAR_PER_PAGE,
    KDP_PREMIUM_COLOR_LARGE_PER_PAGE,
    KDP_ROYALTY_RATE_STANDARD,
    KDP_ROYALTY_RATE_EXPANDED,
    KDP_ROYALTY_RATE_LOW_PRICE,
    KDP_LOW_PRICE_TIER_MAX_LIST_PRICE,
    KDP_SUPPORTED_CURRENCIES,
    KDP_PAPERBACK_MAX_PAGES,
    KDP_HARDCOVER_MAX_PAGES,
    check_page_count_bounds,
    billed_page_count,
    round_money,
)
from .errors import (
    UnsupportedCurrencyError,
    UnsupportedEconomicsConfigurationError,
    EconomicsUnavailableError,
)


class KDPCalculator(BasePublisherCalculator):
    """Calculates publishing specifications according to Amazon KDP requirements."""

    @property
    def publisher_name(self) -> str:
        return "KDP"

    def calculate_spine(self, config: BookConfiguration) -> SpineSpecification:
        is_hardcover = config.book_format == BookFormat.HARDCOVER
        max_pages = KDP_HARDCOVER_MAX_PAGES if is_hardcover else KDP_PAPERBACK_MAX_PAGES
        check_page_count_bounds(config.page_count, max_pages, "KDP")

        multiplier = get_kdp_spine_multiplier(
            config.interior_ink.value, config.paper_type.value
        )
        if is_hardcover:
            # Amazon KDP Hardcover includes spine allowance for binder board & hinge bulk
            # Formatted to 2 decimals as in official KDP Cover Calculator (e.g. 1.01" for 350 pgs Premium Color White)
            spine_width = round(config.page_count * multiplier + KDP_HARDCOVER_SPINE_ALLOWANCE, 2)
            hinge_allowance = KDP_HARDCOVER_HINGE
        else:
            # Authoritative KDP Paperback formula: spine_width = page_count * multiplier
            spine_width = round(config.page_count * multiplier, 4)
            hinge_allowance = 0.0

        text_allowed = config.page_count >= KDP_SPINE_TEXT_MIN_PAGES
        safe_margin = KDP_SPINE_SAFE_MARGIN if text_allowed else None

        return SpineSpecification(
            width=spine_width,
            spine_text_allowed=text_allowed,
            min_pages_for_text=KDP_SPINE_TEXT_MIN_PAGES,
            safe_margin=safe_margin,
            page_multiplier=multiplier,
            hinge_allowance=hinge_allowance,
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
        reading_dir = getattr(config, "reading_direction", "ltr") or "ltr"

        if not is_hardcover:
            # Paperback Cover
            bleed = KDP_COVER_BLEED
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
            barcode_margin_w = 0.250
            barcode_margin_h = 0.250
            barcode_x = round(bleed + back_w - barcode_margin_w - 2.0, 4)
            barcode_y = round(bleed + barcode_margin_h, 4)
            safe_top = 0.125
            safe_bottom = 0.125
            safe_outside = 0.125
            spine_margin = spine.safe_margin if spine.safe_margin is not None else 0.0625
            front_safe_w = round(front_w - safe_outside, 4)
            front_safe_h = round(front_h - (safe_top + safe_bottom), 4)
            spine_safe_w = round(max(0.0, spine.width - (2 * spine_margin)), 4)
            spine_safe_h = round(front_h - (safe_top + safe_bottom), 4)
        else:
            # Hardcover Case Laminate
            # Amazon KDP derives hardcover dimensions from exact metric manufacturing standards:
            # Wrap: 15 mm = 0.591"
            # Hinge: 10 mm = 0.394"
            # Board overhang: +5 mm width = +0.197", +6 mm height = +0.236"
            bleed = 0.0
            wrap = KDP_HARDCOVER_WRAP
            hinge = KDP_HARDCOVER_HINGE
            trim_w_mm = trim_w * 25.4
            trim_h_mm = trim_h * 25.4
            front_w = round((trim_w_mm + 5.0) / 25.4, 3)
            front_h = round((trim_h_mm + 6.0) / 25.4, 3)
            back_w = front_w
            back_h = front_h
            full_w = round((30.0 + 2 * (trim_w_mm + 5.0) + (spine.width * 25.4)) / 25.4, 3)
            full_h = round((trim_h_mm + 36.0) / 25.4, 3)
            spine_left_x = round(wrap + back_w, 4)
            spine_right_x = round(spine_left_x + spine.width, 4)
            barcode_margin_w = 0.250
            barcode_margin_h = KDP_HARDCOVER_BARCODE_MARGIN_H
            barcode_x = round(wrap + back_w - hinge - barcode_margin_w - 2.0, 4)
            barcode_y = round(wrap + barcode_margin_h, 4)
            safe_top = 0.125
            safe_bottom = 0.125
            safe_outside = 0.125
            spine_margin = 0.0625
            front_safe_w = round(front_w - safe_outside, 3)
            front_safe_h = round(front_h - (safe_top + safe_bottom), 3)
            spine_safe_w = round(max(0.0, spine.width - (2 * spine_margin)), 3)
            spine_safe_h = round(front_h - (safe_top + safe_bottom), 3)

        barcode_box = {
            "x": barcode_x,
            "y": barcode_y,
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
            spine_right_x=spine_right_x,
            safe_margin_top=safe_top,
            safe_margin_bottom=safe_bottom,
            safe_margin_outside=safe_outside,
            front_cover_safe_width=front_safe_w,
            front_cover_safe_height=front_safe_h,
            spine_safe_width=spine_safe_w,
            spine_safe_height=spine_safe_h,
            spine_margin=spine_margin,
            barcode_margin=barcode_margin_w,
            barcode_margin_height=barcode_margin_h,
            barcode_zone=barcode_box,
            reading_direction=reading_dir,
            unit="in",
        )

    def calculate_interior(self, config: BookConfiguration) -> InteriorDimensions:
        trim_w = config.trim_width
        trim_h = config.trim_height

        # KDP stepped gutter calculation
        pages = config.page_count
        gutter = 0.375
        for min_p, max_p, g_val in KDP_GUTTER_BANDS:
            if pages <= max_p:
                gutter = g_val
                break
        else:
            gutter = 0.875

        if config.has_bleed:
            page_w = round(trim_w + KDP_INTERIOR_BLEED_SIDE, 4)
            page_h = round(trim_h + (2 * KDP_INTERIOR_BLEED_SIDE), 4)
            min_out = KDP_MIN_OUTSIDE_MARGIN_BLEED
            return InteriorDimensions(
                page_width=page_w,
                page_height=page_h,
                trim_width=trim_w,
                trim_height=trim_h,
                has_bleed=True,
                bleed_amount=KDP_INTERIOR_BLEED_SIDE,
                bleed_top=KDP_INTERIOR_BLEED_SIDE,
                bleed_bottom=KDP_INTERIOR_BLEED_SIDE,
                bleed_outside=KDP_INTERIOR_BLEED_SIDE,
                bleed_inside=0.0,
                min_inside_margin=gutter,
                min_outside_margin=min_out,
                min_top_margin=min_out,
                min_bottom_margin=min_out,
                unit="in",
            )
        else:
            min_out = KDP_MIN_OUTSIDE_MARGIN_NO_BLEED
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
                min_outside_margin=min_out,
                min_top_margin=min_out,
                min_bottom_margin=min_out,
                unit="in",
            )

    def calculate_economics(
        self, config: BookConfiguration, list_price: float | None = None
    ) -> PrintEconomics:
        currency = (config.currency or "USD").upper()
        if currency not in KDP_SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(
                f"KDP economics engine does not support currency {config.currency!r} (supported: {sorted(KDP_SUPPORTED_CURRENCIES)})"
            )

        is_hardcover = config.book_format == BookFormat.HARDCOVER
        max_pages = 550 if is_hardcover else 828
        check_page_count_bounds(config.page_count, max_pages, "KDP")
        ink = config.interior_ink
        paper = str(
            config.paper_type.value
            if hasattr(config.paper_type, "value")
            else (config.paper_type or "")
        ).lower()
        is_groundwood = "groundwood" in paper or "38" in paper

        if is_hardcover and is_groundwood:
            raise UnsupportedEconomicsConfigurationError(
                "Amazon KDP does not support Groundwood paper for Hardcover bindings."
            )

        pages = max(1, config.page_count)
        billed_pages = billed_page_count(pages)
        trim_w = config.trim_width
        trim_h = config.trim_height
        is_large_trim = (round(trim_w, 4) > KDP_REGULAR_TRIM_MAX_W) or (
            round(trim_h, 4) > KDP_REGULAR_TRIM_MAX_H
        )

        # 1. Base fixed fee & per-page rate resolution
        if not is_hardcover:
            # Paperback
            if ink == InteriorInk.BW or str(ink).lower() in ("b&w", "bw", "black"):
                if is_groundwood:
                    if not is_large_trim and billed_pages <= KDP_BW_SHORT_PAGE_THRESHOLD_GROUNDWOOD:
                        fixed, per_page = KDP_BW_REGULAR_SHORT_FLAT_GROUNDWOOD, 0.0
                    elif is_large_trim and billed_pages <= KDP_BW_SHORT_PAGE_THRESHOLD_GROUNDWOOD:
                        fixed, per_page = KDP_BW_LARGE_SHORT_FLAT_GROUNDWOOD, 0.0
                    else:
                        fixed = KDP_PAPERBACK_FIXED_BASE
                        per_page = (
                            KDP_BW_LARGE_PER_PAGE_GROUNDWOOD
                            if is_large_trim
                            else KDP_BW_REGULAR_PER_PAGE_GROUNDWOOD
                        )
                else:
                    if not is_large_trim and billed_pages <= KDP_BW_SHORT_PAGE_THRESHOLD:
                        fixed, per_page = KDP_BW_REGULAR_SHORT_FLAT, 0.0
                    elif is_large_trim and billed_pages <= KDP_BW_SHORT_PAGE_THRESHOLD:
                        fixed, per_page = KDP_BW_LARGE_SHORT_FLAT, 0.0
                    else:
                        fixed = KDP_PAPERBACK_FIXED_BASE
                        per_page = (
                            KDP_BW_LARGE_PER_PAGE
                            if is_large_trim
                            else KDP_BW_REGULAR_PER_PAGE
                        )

            elif ink in (InteriorInk.STANDARD_COLOR, InteriorInk.COLOR) or str(ink).lower() in (
                "standard color",
                "color",
                "colour",
            ):
                # Standard color: supported for both regular (0.0255) and large trim (0.0402), 72-600 pages
                fixed = KDP_PAPERBACK_FIXED_BASE
                per_page = (
                    KDP_STANDARD_COLOR_LARGE_PER_PAGE
                    if is_large_trim
                    else KDP_STANDARD_COLOR_REGULAR_PER_PAGE
                )

            else:  # Premium Color / Ultra-Premium
                if not is_large_trim and billed_pages <= KDP_PREMIUM_COLOR_SHORT_PAGE_THRESHOLD:
                    fixed, per_page = KDP_PREMIUM_COLOR_REGULAR_SHORT_FLAT, 0.0
                elif is_large_trim and billed_pages <= KDP_PREMIUM_COLOR_SHORT_PAGE_THRESHOLD:
                    fixed, per_page = KDP_PREMIUM_COLOR_LARGE_SHORT_FLAT, 0.0
                else:
                    fixed = KDP_PAPERBACK_FIXED_BASE
                    per_page = (
                        KDP_PREMIUM_COLOR_LARGE_PER_PAGE
                        if is_large_trim
                        else KDP_PREMIUM_COLOR_REGULAR_PER_PAGE
                    )
        else:
            # Hardcover (Min 75, Max 550 pages)
            if ink == InteriorInk.BW or str(ink).lower() in ("b&w", "bw", "black"):
                if billed_pages <= KDP_HARDCOVER_BW_SHORT_PAGE_THRESHOLD:
                    fixed = (
                        KDP_HARDCOVER_BW_LARGE_SHORT_FLAT
                        if is_large_trim
                        else KDP_HARDCOVER_BW_REGULAR_SHORT_FLAT
                    )
                    per_page = 0.0
                else:
                    fixed = KDP_HARDCOVER_FIXED_BASE
                    if is_groundwood:
                        per_page = (
                            KDP_BW_LARGE_PER_PAGE_GROUNDWOOD
                            if is_large_trim
                            else KDP_BW_REGULAR_PER_PAGE_GROUNDWOOD
                        )
                    else:
                        per_page = (
                            KDP_BW_LARGE_PER_PAGE
                            if is_large_trim
                            else KDP_BW_REGULAR_PER_PAGE
                        )
            elif ink in (InteriorInk.STANDARD_COLOR, InteriorInk.COLOR) or str(ink).lower() in (
                "standard color",
                "color",
                "colour",
            ):
                raise UnsupportedEconomicsConfigurationError(
                    "Amazon KDP does not support Standard Color for Hardcover books. "
                    "Only Black & White or Premium Color are supported."
                )
            else:  # Premium Color
                fixed = KDP_HARDCOVER_FIXED_BASE
                per_page = (
                    KDP_PREMIUM_COLOR_LARGE_PER_PAGE
                    if is_large_trim
                    else KDP_PREMIUM_COLOR_REGULAR_PER_PAGE
                )

        fixed_d = Decimal(str(fixed))
        per_page_d = Decimal(str(per_page))
        billed_pages_d = Decimal(str(billed_pages))

        raw_cost_d = fixed_d + (billed_pages_d * per_page_d)
        est_print_cost = float(round_money(raw_cost_d))

        # 2. Distribution & Royalty Resolution
        is_expanded = config.distribution_goal == DistributionGoal.GLOBAL_RETAIL
        max_low_price = KDP_LOW_PRICE_TIER_MAX_LIST_PRICE.get(currency, Decimal("9.98"))

        if is_expanded and not is_hardcover:
            active_royalty_rate = Decimal(str(KDP_ROYALTY_RATE_EXPANDED))
            min_list_d = round_money(raw_cost_d / active_royalty_rate)
        else:
            floor_50 = raw_cost_d / Decimal(str(KDP_ROYALTY_RATE_LOW_PRICE))
            if floor_50 <= max_low_price:
                min_list_d = round_money(floor_50)
            else:
                floor_60 = raw_cost_d / Decimal(str(KDP_ROYALTY_RATE_STANDARD))
                min_list_d = max(Decimal("9.99"), round_money(floor_60))

        if list_price is not None:
            list_price_d = Decimal(str(list_price))
            if is_expanded and not is_hardcover:
                active_royalty_rate = Decimal(str(KDP_ROYALTY_RATE_EXPANDED))
            elif list_price_d <= max_low_price:
                active_royalty_rate = Decimal(str(KDP_ROYALTY_RATE_LOW_PRICE))
            else:
                active_royalty_rate = Decimal(str(KDP_ROYALTY_RATE_STANDARD))

            gross_d = (list_price_d * active_royalty_rate) - raw_cost_d
            est_royalty = float(max(Decimal("0.00"), round_money(gross_d)))
        else:
            if is_expanded and not is_hardcover:
                active_royalty_rate = Decimal(str(KDP_ROYALTY_RATE_EXPANDED))
            elif min_list_d <= max_low_price:
                active_royalty_rate = Decimal(str(KDP_ROYALTY_RATE_LOW_PRICE))
            else:
                active_royalty_rate = Decimal(str(KDP_ROYALTY_RATE_STANDARD))
            est_royalty = None

        return PrintEconomics(
            fixed_cost=fixed,
            per_page_cost=per_page,
            page_count=pages,
            billed_page_count=billed_pages,
            royalty_rate=float(active_royalty_rate),
            estimated_print_cost=est_print_cost,
            min_list_price=float(min_list_d),
            estimated_royalty=est_royalty,
            list_price=list_price,
            currency=currency,
            marketplace="US",
            publisher="KDP",
        )

    def calculate(
        self, config: BookConfiguration, list_price: float | None = None
    ) -> CalculatedSpecification:
        """Orchestrate complete physical specification calculation."""
        spine = self.calculate_spine(config)
        cover = self.calculate_cover(config, spine=spine)
        interior = self.calculate_interior(config)
        try:
            economics = self.calculate_economics(config, list_price=list_price)
            notes = ["Weight data unavailable for KDP"]
        except EconomicsUnavailableError as exc:
            economics = None
            notes = ["Weight data unavailable for KDP", f"Economics unavailable: {exc}"]
        except ValueError:
            economics = None
            notes = ["Weight data unavailable for KDP"]

        return CalculatedSpecification(
            publisher=self.publisher_name,
            spine=spine,
            cover=cover,
            interior=interior,
            spine_width=spine.width,
            spine_text_allowed=spine.spine_text_allowed,
            weight_lb=spine.weight_lb,
            weight_g=spine.weight_g,
            economics=economics,
            unit="in",
            notes=notes,
        )
