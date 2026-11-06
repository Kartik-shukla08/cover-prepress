"""IngramSpark physical specifications and economics calculator."""

from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import BookFormat, InteriorInk, BindingType, DistributionGoal
from mbooks.domain.geometry import (
    SpineSpecification,
    CoverDimensions,
    InteriorDimensions,
)
from mbooks.domain.economics import PrintEconomics
from .base import BasePublisherCalculator
from .tables import (
    get_ingram_paper_spec,
    get_ingram_binding_cost,
    get_ingram_per_page_rate,
    get_ingram_print_rate_spec,
    get_ingram_wholesale_discount,
    check_page_count_bounds,
    billed_page_count,
    round_money,
    INGRAM_MARKET_ACCESS_FEE_RATE,
    INGRAM_DIRECT_QUANTITY_DISCOUNTS,
    INGRAM_PERFORATION_ADDON_PER_PAGE,
    INGRAM_SPINE_TEXT_MIN_PAGES,
    INGRAM_COVER_BLEED,
    INGRAM_COVER_GSM_PAPERBACK,
    INGRAM_BOARD_GSM_HARDCOVER,
    INGRAM_CASE_LAMINATE_WRAP,
    INGRAM_CASE_LAMINATE_HINGE,
    INGRAM_CASE_LAMINATE_BOARD_SETBACK_W,
    INGRAM_CASE_LAMINATE_BOARD_OVERHANG_H,
    INGRAM_DUST_JACKET_FLAP_W,
    INGRAM_DUST_JACKET_FOLD_W,
    INGRAM_DUST_JACKET_COVER_OVERHANG_W,
    INGRAM_DUST_JACKET_COVER_OVERHANG_H,
    INGRAM_DUST_JACKET_BLEED,
    INGRAM_INTERIOR_BLEED_SIDE,
    INGRAM_RECOMMENDED_SAFETY,
    INGRAM_COVER_TYPE_SAFETY,
)
from .errors import (
    UnsupportedCurrencyError,
    UnsupportedEconomicsConfigurationError,
    PageCountOutOfRangeError,
)


class IngramSparkCalculator(BasePublisherCalculator):
    """Calculates publishing specifications according to IngramSpark requirements."""

    @property
    def publisher_name(self) -> str:
        return "IngramSpark"

    def calculate_weight(
        self, config: BookConfiguration, spine_width: float | None = None
    ) -> tuple[float, float]:
        """Calculates physical book weight (lb, g) matching IngramSpark official calculator.
        
        Interior weight = (pages / 2) * sheet_area_m2 * paper_gsm.
        Cover weight = cover_spread_area_m2 * cover_stock_gsm (or board allowance for hardcover).
        """
        trim_w = config.trim_width
        trim_h = config.trim_height
        pages = config.page_count
        sheets = pages / 2.0

        paper_name = config.paper_type.value if hasattr(config.paper_type, "value") else str(config.paper_type)
        ink_name = config.interior_ink.value if hasattr(config.interior_ink, "value") else str(config.interior_ink)
        spec = get_ingram_paper_spec(paper_name, ink_name)

        # Interior weight in grams
        sheet_area_m2 = (trim_w * 0.0254) * (trim_h * 0.0254)
        interior_g = sheets * sheet_area_m2 * spec.gsm

        # Cover weight in grams
        is_hardcover = config.book_format == BookFormat.HARDCOVER
        if not is_hardcover:
            sw = spine_width if spine_width is not None else round(pages * spec.caliper, 4)
            spread_w_m = ((2 * trim_w) + sw + (2 * INGRAM_COVER_BLEED)) * 0.0254
            spread_h_m = (trim_h + (2 * INGRAM_COVER_BLEED)) * 0.0254
            cover_g = spread_w_m * spread_h_m * INGRAM_COVER_GSM_PAPERBACK
        else:
            allowance = spec.case_laminate_allowance
            sw = spine_width if spine_width is not None else round(pages * spec.caliper + allowance, 4)
            board_w_m = (trim_w - INGRAM_CASE_LAMINATE_BOARD_SETBACK_W) * 0.0254
            board_h_m = (trim_h + INGRAM_CASE_LAMINATE_BOARD_OVERHANG_H) * 0.0254
            sw_m = sw * 0.0254
            cover_g = (2 * board_w_m + sw_m) * board_h_m * INGRAM_BOARD_GSM_HARDCOVER

        total_g = round(interior_g + cover_g, 3)
        total_lb = round(total_g / 453.59237, 3)
        return total_lb, total_g

    def _calculate_white50_spine_block(self, pages: int) -> float:
        """Dynamic clamp-compression curve for 50# White paper matching live IngramSpark portal across 200-1200 pages."""
        if pages <= 200:
            return 0.424 - (200 - pages) * 0.002050
        elif pages <= 300:
            return 0.424 + (pages - 200) * ((0.629 - 0.424) / 100.0)
        elif pages <= 350:
            return 0.629 + (pages - 300) * ((0.728 - 0.629) / 50.0)
        elif pages <= 400:
            return 0.728 + (pages - 350) * ((0.821 - 0.728) / 50.0)
        elif pages <= 500:
            return 0.821 + (pages - 400) * ((1.005 - 0.821) / 100.0)
        elif pages <= 700:
            return 1.005 + (pages - 500) * ((1.401 - 1.005) / 200.0)
        elif pages <= 900:
            return 1.401 + (pages - 700) * ((1.778 - 1.401) / 200.0)
        elif pages <= 1100:
            return 1.778 + (pages - 900) * ((2.155 - 1.778) / 200.0)
        elif pages <= 1200:
            return 2.155 + (pages - 1100) * ((2.344 - 2.155) / 100.0)
        else:
            return 2.344 + (pages - 1200) * 0.001890

    def _calculate_creme_spine_block(self, pages: int) -> float:
        """Dynamic clamp-compression curve for 50# Crème paper matching live IngramSpark portal across 100-1050 pages."""
        if pages <= 100:
            return 0.240 - (100 - pages) * 0.002180
        elif pages <= 200:
            return 0.240 + (pages - 100) * ((0.458 - 0.240) / 100.0)
        elif pages <= 300:
            return 0.458 + (pages - 200) * ((0.674 - 0.458) / 100.0)
        elif pages <= 400:
            return 0.674 + (pages - 300) * ((0.890 - 0.674) / 100.0)
        elif pages <= 600:
            return 0.890 + (pages - 400) * ((1.333 - 0.890) / 200.0)
        elif pages <= 650:
            return 1.333 + (pages - 600) * ((1.436 - 1.333) / 50.0)
        elif pages <= 700:
            return 1.436 + (pages - 650) * ((1.538 - 1.436) / 50.0)
        elif pages <= 750:
            return 1.538 + (pages - 700) * ((1.650 - 1.538) / 50.0)
        elif pages <= 800:
            return 1.650 + (pages - 750) * ((1.767 - 1.650) / 50.0)
        elif pages <= 900:
            return 1.767 + (pages - 800) * ((2.001 - 1.767) / 100.0)
        elif pages <= 1000:
            return 2.001 + (pages - 900) * ((2.235 - 2.001) / 100.0)
        elif pages <= 1050:
            return 2.235 + (pages - 1000) * ((2.352 - 2.235) / 50.0)
        else:
            return 2.352 + (pages - 1050) * 0.002340

    def _calculate_groundwood_spine_block(self, pages: int) -> float:
        """Dynamic clamp-compression curve for 38# Groundwood paper matching live IngramSpark portal across 100-900 pages."""
        if pages <= 100:
            return 0.255 - (100 - pages) * 0.002470
        elif pages <= 200:
            return 0.255 + (pages - 100) * ((0.502 - 0.255) / 100.0)
        elif pages <= 300:
            return 0.502 + (pages - 200) * ((0.748 - 0.502) / 100.0)
        elif pages <= 400:
            return 0.748 + (pages - 300) * ((0.994 - 0.748) / 100.0)
        elif pages <= 500:
            return 0.994 + (pages - 400) * ((1.241 - 0.994) / 100.0)
        elif pages <= 600:
            return 1.241 + (pages - 500) * ((1.487 - 1.241) / 100.0)
        elif pages <= 700:
            return 1.487 + (pages - 600) * ((1.734 - 1.487) / 100.0)
        elif pages <= 800:
            return 1.734 + (pages - 700) * ((1.980 - 1.734) / 100.0)
        elif pages <= 900:
            return 1.980 + (pages - 800) * ((2.227 - 1.980) / 100.0)
        else:
            return 2.227 + (pages - 900) * 0.002470

    def _calculate_premium_color_spine_block(self, pages: int) -> float:
        """Dynamic clamp-compression curve for Premium Color paper matching live IngramSpark portal across 100-900 pages."""
        if pages <= 100:
            return 0.260 - (100 - pages) * 0.002600
        elif pages <= 200:
            return 0.260 + (pages - 100) * ((0.520 - 0.260) / 100.0)
        elif pages <= 300:
            return 0.520 + (pages - 200) * ((0.779 - 0.520) / 100.0)
        elif pages <= 400:
            return 0.779 + (pages - 300) * ((1.039 - 0.779) / 100.0)
        elif pages <= 500:
            return 1.039 + (pages - 400) * ((1.299 - 1.039) / 100.0)
        elif pages <= 600:
            return 1.299 + (pages - 500) * ((1.558 - 1.299) / 100.0)
        elif pages <= 700:
            return 1.558 + (pages - 600) * ((1.818 - 1.558) / 100.0)
        elif pages <= 800:
            return 1.818 + (pages - 700) * ((2.078 - 1.818) / 100.0)
        elif pages <= 900:
            return 2.078 + (pages - 800) * ((2.338 - 2.078) / 100.0)
        else:
            return 2.338 + (pages - 900) * 0.002600

    def calculate_spine(self, config: BookConfiguration) -> SpineSpecification:
        check_page_count_bounds(config.page_count, 1200, "IngramSpark")
        paper_name = config.paper_type.value if hasattr(config.paper_type, "value") else str(config.paper_type)
        ink_name = config.interior_ink.value if hasattr(config.interior_ink, "value") else str(config.interior_ink)
        spec = get_ingram_paper_spec(paper_name, ink_name)

        is_hardcover = config.book_format == BookFormat.HARDCOVER
        allowance = spec.case_laminate_allowance if is_hardcover else 0.0

        p_name_lower = paper_name.lower()
        is_white_50 = (
            paper_name in ("White", "White 50lb/74gsm", "Color 50", "White 50", "Colour 50")
            or (("white" in p_name_lower or "color 50" in p_name_lower or "colour 50" in p_name_lower)
                and "70" not in p_name_lower
                and "coated" not in p_name_lower
                and "cream" not in p_name_lower
                and "crème" not in p_name_lower
                and "creme" not in p_name_lower
                and "groundwood" not in p_name_lower
                and "premium" not in p_name_lower
                and "ultra" not in p_name_lower)
        )

        is_creme = (
            paper_name in ("Creme", "Crème", "Cream", "Crème 50lb/74gsm", "Creme 50lb/74gsm")
            or "cream" in p_name_lower or "crème" in p_name_lower or "creme" in p_name_lower
        )

        is_groundwood = (
            paper_name in ("Groundwood", "Groundwood 38lb/56gsm", "38# Groundwood", "Groundwood 38#")
            or "groundwood" in p_name_lower
        )

        is_premium_color = (
            paper_name in (
                "Premium Color", "Premium Colour",
                "Ultra Premium Color", "Ultra Premium Colour",
                "Ultra-Premium Color", "Ultra-Premium Colour",
            )
            or "premium" in p_name_lower
        )

        if is_white_50:
            block_w = self._calculate_white50_spine_block(config.page_count)
            spine_width = round(block_w + allowance, 4)
            page_multiplier = round(block_w / config.page_count, 7)
        elif is_creme:
            block_w = self._calculate_creme_spine_block(config.page_count)
            spine_width = round(block_w + allowance, 4)
            page_multiplier = round(block_w / config.page_count, 7)
        elif is_groundwood:
            block_w = self._calculate_groundwood_spine_block(config.page_count)
            spine_width = round(block_w + allowance, 4)
            page_multiplier = round(block_w / config.page_count, 7)
        elif is_premium_color:
            block_w = self._calculate_premium_color_spine_block(config.page_count)
            spine_width = round(block_w + allowance, 4)
            page_multiplier = round(block_w / config.page_count, 7)
        else:
            # Standard linear stock formula: page_count * caliper + allowance for hardcover
            spine_width = round(config.page_count * spec.caliper + allowance, 4)
            page_multiplier = spec.caliper

        text_allowed = config.page_count >= INGRAM_SPINE_TEXT_MIN_PAGES

        # Ingram threshold safety rule: >= 0.35" spine -> 0.0625" (2mm), < 0.35" -> 0.03125" (1mm)
        safe_margin = None
        if text_allowed:
            safe_margin = 0.0625 if spine_width >= 0.35 else 0.03125

        weight_lb, weight_g = self.calculate_weight(config, spine_width=spine_width)

        return SpineSpecification(
            width=spine_width,
            spine_text_allowed=text_allowed,
            min_pages_for_text=INGRAM_SPINE_TEXT_MIN_PAGES,
            safe_margin=safe_margin,
            page_multiplier=page_multiplier,
            hinge_allowance=allowance,
            weight_lb=weight_lb,
            weight_g=weight_g,
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

        is_dust_jacket = config.binding == BindingType.JACKETED_CASE_LAMINATE

        if not is_hardcover:
            # Paperback Perfect Bound (per ingram_guide.md Section 7.1)
            bleed = INGRAM_COVER_BLEED
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
            barcode_x = round(spine_left_x - barcode_margin_w - 2.0, 4)
            barcode_y = round(bleed + barcode_margin_h, 4)
        elif is_dust_jacket:
            # Hardcover Dust Jacket (per ingram_guide.md Section 7.3)
            bleed = INGRAM_DUST_JACKET_BLEED
            wrap = 0.0
            hinge = INGRAM_DUST_JACKET_FOLD_W
            cover_w = round(trim_w + INGRAM_DUST_JACKET_COVER_OVERHANG_W, 4)
            cover_h = round(trim_h + INGRAM_DUST_JACKET_COVER_OVERHANG_H, 4)
            flap_w = INGRAM_DUST_JACKET_FLAP_W
            fold_w = INGRAM_DUST_JACKET_FOLD_W
            full_w = round((2 * bleed) + (2 * flap_w) + (2 * fold_w) + (2 * cover_w) + spine.width, 4)
            full_h = round(cover_h + (2 * bleed), 4)
            front_w = cover_w
            front_h = cover_h
            back_w = cover_w
            back_h = cover_h
            spine_left_x = round(bleed + flap_w + fold_w + back_w, 4)
            spine_right_x = round(spine_left_x + spine.width, 4)
            barcode_margin_w = 0.250
            barcode_margin_h = 0.250
            barcode_x = round(spine_left_x - barcode_margin_w - 2.0, 4)
            barcode_y = round(bleed + barcode_margin_h, 4)
        else:
            # Hardcover Case Laminate (per ingram_guide.md Section 7.2)
            bleed = 0.0
            wrap = INGRAM_CASE_LAMINATE_WRAP
            hinge = INGRAM_CASE_LAMINATE_HINGE
            board_w = round(trim_w - INGRAM_CASE_LAMINATE_BOARD_SETBACK_W, 4)
            board_h = round(trim_h + INGRAM_CASE_LAMINATE_BOARD_OVERHANG_H, 4)
            full_w = round((2 * wrap) + (2 * board_w) + (2 * hinge) + spine.width, 4)
            full_h = round((2 * wrap) + board_h, 4)
            front_w = board_w
            front_h = board_h
            back_w = board_w
            back_h = board_h
            spine_left_x = round(wrap + back_w + hinge, 4)
            spine_right_x = round(spine_left_x + spine.width, 4)
            barcode_margin_w = 0.250
            barcode_margin_h = 0.250
            barcode_x = round(spine_left_x - hinge - barcode_margin_w - 2.0, 4)
            barcode_y = round(wrap + barcode_margin_h, 4)

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
            safe_margin_top=INGRAM_COVER_TYPE_SAFETY,
            safe_margin_bottom=INGRAM_COVER_TYPE_SAFETY,
            safe_margin_outside=INGRAM_COVER_TYPE_SAFETY,
            barcode_zone=barcode_box,
            unit="in",
        )

    def calculate_interior(self, config: BookConfiguration) -> InteriorDimensions:
        trim_w = config.trim_width
        trim_h = config.trim_height

        if config.has_bleed:
            # Interior bleed: +0.125" outside, +0.25" total height
            page_w = round(trim_w + INGRAM_INTERIOR_BLEED_SIDE, 4)
            page_h = round(trim_h + (2 * INGRAM_INTERIOR_BLEED_SIDE), 4)
            return InteriorDimensions(
                page_width=page_w,
                page_height=page_h,
                trim_width=trim_w,
                trim_height=trim_h,
                has_bleed=True,
                bleed_amount=INGRAM_INTERIOR_BLEED_SIDE,
                bleed_top=INGRAM_INTERIOR_BLEED_SIDE,
                bleed_bottom=INGRAM_INTERIOR_BLEED_SIDE,
                bleed_outside=INGRAM_INTERIOR_BLEED_SIDE,
                bleed_inside=0.0,
                min_inside_margin=INGRAM_RECOMMENDED_SAFETY,
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
                min_inside_margin=INGRAM_RECOMMENDED_SAFETY,
                min_outside_margin=0.250,
                min_top_margin=0.250,
                min_bottom_margin=0.250,
                unit="in",
            )

    def calculate_economics(
        self,
        config: BookConfiguration,
        list_price: float | None = None,
        currency: str = "USD",
        wholesale_discount: float | None = None,
        include_market_access_fee: bool | None = None,
    ) -> PrintEconomics:
        pages = max(1, config.page_count)
        billed_pages = billed_page_count(pages)
        eff_currency = (getattr(config, "currency", None) or currency or "USD").upper()

        if eff_currency not in {"USD", "GBP", "EUR", "AUD"}:
            raise UnsupportedCurrencyError(
                f"IngramSpark rates are published in ['AUD', 'EUR', 'GBP', 'USD'] only; got {eff_currency!r}."
            )

        rate_spec = get_ingram_print_rate_spec(config, currency=eff_currency)
        fixed = rate_spec.per_cover_cost
        per_page = rate_spec.per_page_cost

        d_fixed = Decimal(str(fixed))
        d_per_page = Decimal(str(per_page))
        d_pages = Decimal(billed_pages)
        d_raw_cost = d_fixed + (d_pages * d_per_page)
        d_est_print_cost = d_raw_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        est_print_cost = float(d_est_print_cost)

        # Check if direct order (author copies)
        is_direct = False
        goal = getattr(config, "distribution_goal", None)
        if goal is not None:
            goal_str = str(goal.value if hasattr(goal, "value") else goal).lower()
            if "direct" in goal_str:
                is_direct = True

        if is_direct:
            eff_wd = None
            min_list = None
            est_royalty = None
            pub_comp = None
            market_access_fee = None
            wholesale_price = None
        else:
            # Resolve wholesale discount (0.0 to 1.0)
            eff_wd = wholesale_discount
            if eff_wd is None:
                eff_wd = getattr(config, "wholesale_discount", None)
            if eff_wd is None:
                eff_wd = get_ingram_wholesale_discount(config.distribution_goal)

            d_wd = Decimal(str(eff_wd))
            d_pub_share = Decimal("1.0") - d_wd

            # Determine Market Access Fee behavior (default True per Astra N9)
            eff_include_maf = include_market_access_fee
            if eff_include_maf is None:
                eff_include_maf = getattr(config, "include_market_access_fee", True)

            d_maf_rate = Decimal(str(INGRAM_MARKET_ACCESS_FEE_RATE))

            # Min list price calculation:
            if eff_include_maf:
                d_denom = d_pub_share - d_maf_rate
                if d_denom <= Decimal("0.0"):
                    d_denom = Decimal("0.01")
                min_list = float((d_est_print_cost / d_denom).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            else:
                d_denom = d_pub_share if d_pub_share > Decimal("0.0") else Decimal("0.01")
                min_list = float((d_est_print_cost / d_denom).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            est_royalty = None
            pub_comp = None
            market_access_fee = None
            wholesale_price = None

            if list_price is not None:
                d_price = Decimal(str(list_price))
                d_wholesale_price = (d_price * d_pub_share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                wholesale_price = float(d_wholesale_price)
                d_maf = (d_price * d_maf_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                market_access_fee = float(d_maf)

                # Net Publisher Compensation: use exact fee unrounded to avoid premature rounding error
                d_raw_comp = d_wholesale_price - d_est_print_cost - (d_price * d_maf_rate)
                if d_raw_comp < Decimal("0.0"):
                    pub_comp = 0.0
                else:
                    pub_comp = float(d_raw_comp.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

                # Legacy / standard estimated_royalty:
                if eff_include_maf:
                    est_royalty = pub_comp
                else:
                    d_raw_royalty = (d_price * d_pub_share) - d_est_print_cost
                    if d_raw_royalty < Decimal("0.0"):
                        est_royalty = 0.0
                    else:
                        est_royalty = float(d_raw_royalty.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

        # Quantity Discounts table for author copies (Publisher Direct)
        qty_discounts_info = []
        for min_qty, disc_rate in sorted(INGRAM_DIRECT_QUANTITY_DISCOUNTS, key=lambda x: x[0]):
            d_disc_rate = Decimal(str(disc_rate))
            d_unit_cost = (d_est_print_cost * (Decimal("1.0") - d_disc_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if min_qty == 1:
                tier_label = "1-99"
                max_copies = 99
            elif min_qty == 100:
                tier_label = "100-299"
                max_copies = 299
            elif min_qty == 300:
                tier_label = "300-399"
                max_copies = 399
            elif min_qty == 400:
                tier_label = "400-499"
                max_copies = 499
            elif min_qty == 500:
                tier_label = "500-999"
                max_copies = 999
            elif min_qty == 1000:
                tier_label = "1,000-1,499"
                max_copies = 1499
            elif min_qty == 1500:
                tier_label = "1,500-2,499"
                max_copies = 2499
            elif min_qty == 2500:
                tier_label = "2,500-4,999"
                max_copies = 4999
            elif min_qty == 5000:
                tier_label = "5,000-9,999"
                max_copies = 9999
            else:
                tier_label = f"{min_qty:,}+"
                max_copies = None

            qty_discounts_info.append({
                "min_copies": min_qty,
                "max_copies": max_copies,
                "tier_label": tier_label,
                "discount_percent": float(d_disc_rate * Decimal("100.0")),
                "discount_rate": disc_rate,
                "unit_cost": float(d_unit_cost),
                "savings_per_copy": float((d_est_print_cost - d_unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            })

        market_map = {"USD": "US", "GBP": "UK", "AUD": "AU", "EUR": "EU"}
        marketplace = market_map.get(eff_currency, "US")

        return PrintEconomics(
            fixed_cost=fixed,
            per_page_cost=per_page,
            page_count=pages,
            billed_page_count=billed_pages,
            estimated_print_cost=est_print_cost,
            min_list_price=min_list,
            estimated_royalty=est_royalty,
            list_price=list_price,
            currency=eff_currency,
            marketplace=marketplace,
            publisher="IngramSpark",
            wholesale_discount=float(eff_wd) if eff_wd is not None else None,
            wholesale_price=wholesale_price,
            market_access_fee=market_access_fee,
            publisher_compensation=pub_comp,
            quantity_discounts=qty_discounts_info,
        )
