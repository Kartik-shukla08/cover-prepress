"""Lulu physical specifications and economics calculator."""

from __future__ import annotations
import json
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any
from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import BookFormat, BindingType, InteriorInk
from mbooks.domain.geometry import (
    SpineSpecification,
    CoverDimensions,
    InteriorDimensions,
    CalculatedSpecification,
)
from mbooks.domain.economics import PrintEconomics
from .base import BasePublisherCalculator
from .tables import (
    get_lulu_paper_caliper,
    get_lulu_hardcover_spine,
    get_lulu_gutter_spec,
    LULU_SPINE_TEXT_MIN_PAGES,
    LULU_SPINE_SAFE_MARGIN,
    LULU_SAFETY_MARGIN_IN,
    LULU_COVER_BLEED,
    LULU_CASEWRAP_WRAP,
    LULU_CASEWRAP_HINGE,
    LULU_INTERIOR_BLEED_SIDE,
    LULU_RECOMMENDED_MARGIN,
    LULU_COIL_PUNCH_MARGIN,
    LULU_PAPERBACK_SPINE_DIVISOR_IN,
    LULU_PAPERBACK_SPINE_BASE_IN,
    LULU_PAPERBACK_SPINE_DIVISOR_460PPI_IN,
    LULU_PAPERBACK_MIN_PAGES,
    LULU_HARDCOVER_MIN_PAGES,
    LULU_PAPERBACK_MAX_PAGES,
    LULU_COIL_MAX_PAGES,
    LULU_SADDLE_STITCH_MAX_PAGES,
    LULU_HARDCOVER_MAX_PAGES,
    check_page_count_bounds,
)
from mbooks.domain.enums import CoverFinish, PaperType


class UnsupportedPodPackageError(ValueError):
    """The configuration does not correspond to any product in Lulu's catalog.

    Raised by :meth:`LuluCalculator.resolve_pod_package_id` instead of guessing a
    SKU (interface I1).  Callers must refuse to order / quote the product.
    """


# ---------------------------------------------------------------------------
# Lulu catalog — normalised from packages/mbooks-calc/lulu_sku.md
# (Lulu SKU Guide, updated 3/2026).  Do not add rows that are not in the guide.
# ---------------------------------------------------------------------------

#: (trim_width_in, trim_height_in) -> Lulu trim SKU (all 16 guide rows).
LULU_TRIM_SKUS: dict[tuple[float, float], str] = {
    (4.25, 6.875): "0425X0687",
    (5.0, 8.0): "0500X0800",
    (5.5, 8.5): "0550X0850",
    (5.83, 8.27): "0583X0827",
    (6.0, 9.0): "0600X0900",
    (6.14, 9.21): "0614X0921",
    (6.63, 10.25): "0663X1025",
    (7.5, 7.5): "0750X0750",
    (7.0, 10.0): "0700X1000",
    (7.44, 9.68): "0744X0968",
    (8.5, 8.5): "0850X0850",
    (8.27, 11.69): "0827X1169",
    (8.5, 11.0): "0850X1100",
    (9.0, 7.0): "0900X0700",
    (11.0, 8.5): "1100X0850",
    (11.69, 8.27): "1169X0827",
}

#: Matching tolerance in inches (guide values are rounded to 0.01 / 0.005 in).
LULU_TRIM_TOLERANCE_IN = 0.015

#: Guide paper name -> full paper code (SKU + PPI).  The guide lists 100# as
#: SKU ``100CW`` with PPI ``200``; the full code is therefore ``100CW200``.
LULU_PAPER_SKUS: dict[str, str] = {
    "60# Uncoated White": "060UW444",
    "60# Uncoated Cream": "060UC444",
    "70# Coated White": "070CW460",
    "80# Coated White": "080CW444",
    "100# Coated White": "100CW200",
}

# Domain paper enum -> Lulu paper code.  Explicit table (no substring guessing).
# There is no PaperType for 100# yet, so 100CW200 is not reachable from a
# BookConfiguration until the domain model adds one.
_LULU_PAPER_SKU_BY_TYPE: dict[PaperType, str] = {
    PaperType.WHITE: LULU_PAPER_SKUS["60# Uncoated White"],
    PaperType.WHITE_50LB: LULU_PAPER_SKUS["60# Uncoated White"],
    PaperType.WHITE_50: LULU_PAPER_SKUS["60# Uncoated White"],
    PaperType.CREAM: LULU_PAPER_SKUS["60# Uncoated Cream"],
    PaperType.CREME: LULU_PAPER_SKUS["60# Uncoated Cream"],
    PaperType.CREME_50LB: LULU_PAPER_SKUS["60# Uncoated Cream"],
    PaperType.WHITE_70LB: LULU_PAPER_SKUS["70# Coated White"],
    PaperType.WHITE_70: LULU_PAPER_SKUS["70# Coated White"],
    PaperType.COATED_WHITE: LULU_PAPER_SKUS["80# Coated White"],
}

# Interior ink -> (color SKU, print-quality SKU).
_LULU_INK_SKUS: dict[InteriorInk, tuple[str, str]] = {
    InteriorInk.BW: ("BW", "STD"),
    InteriorInk.STANDARD_COLOR: ("FC", "STD"),
    InteriorInk.COLOR: ("FC", "STD"),
    InteriorInk.PREMIUM_COLOR: ("FC", "PRE"),
}

_LULU_FINISH_SKUS: dict[CoverFinish, str] = {
    CoverFinish.MATTE: "M",
    CoverFinish.GLOSS: "G",
    CoverFinish.GLOSSY: "G",
}

_LULU_PAPERBACK_BIND_SKUS: dict[BindingType, str] = {
    BindingType.PERFECT_BOUND: "PB",
    BindingType.COIL: "CO",
    BindingType.SADDLE_STITCH: "SS",
}
_LULU_HARDCOVER_BIND_SKUS: dict[BindingType, str] = {
    BindingType.CASEWRAP: "CW",
}


def find_lulu_trim_sku(width: float, height: float) -> str | None:
    """Return the Lulu trim SKU for ``width`` x ``height`` inches, or ``None``."""
    for (tw, th), sku in LULU_TRIM_SKUS.items():
        if abs(width - tw) <= LULU_TRIM_TOLERANCE_IN and abs(height - th) <= LULU_TRIM_TOLERANCE_IN:
            return sku
    return None


def _resolve_lulu_bind_sku(config: BookConfiguration) -> str:
    binding = config.binding
    if config.book_format == BookFormat.HARDCOVER:
        if binding is None:
            return "CW"
        if binding in _LULU_HARDCOVER_BIND_SKUS:
            return _LULU_HARDCOVER_BIND_SKUS[binding]
        if binding == BindingType.LINEN_WRAP_DUST_JACKET:
            raise UnsupportedPodPackageError(
                "Lulu linen wrap requires a linen colour and foil selection, which BookConfiguration "
                "does not carry; refusing to guess a linen-wrap SKU."
            )
    else:
        if binding is None:
            return "PB"
        if binding in _LULU_PAPERBACK_BIND_SKUS:
            return _LULU_PAPERBACK_BIND_SKUS[binding]
    raise UnsupportedPodPackageError(
        f"Binding '{getattr(binding, 'value', binding)}' is not a Lulu "
        f"{config.book_format.value.lower()} binding."
    )


#: Calibrated print-cost tables, one per Lulu environment, written by
#: ``scripts/calibrate_lulu_prices.py`` from Lulu's own cost API.
_LULU_PRICE_DIR = Path(__file__).resolve().parent / "data"
LULU_PRICE_LISTS = ("sandbox", "production")


@lru_cache(maxsize=None)
def load_lulu_price_list(environment: str = "sandbox") -> dict[str, Any] | None:
    """Return the calibrated price list for ``environment``, or None if none exists."""
    if environment not in LULU_PRICE_LISTS:
        raise ValueError(f"Unknown Lulu price list {environment!r}")
    path = _LULU_PRICE_DIR / f"lulu_prices_{environment}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def lulu_price_entry(sku: str, environment: str = "sandbox") -> dict[str, str] | None:
    """Fixed and per-page cost for a Lulu product SKU, or None if not calibrated.

    Lookup is by the SKU's own parts (trim tier, binding, ink, paper); the cover
    finish does not change the print cost.
    """
    table = load_lulu_price_list(environment)
    if table is None:
        return None
    trim, color, quality, binding, paper = sku.split(".")[:5]
    tier = table["trim_tiers"].get(binding, {}).get(trim)
    if tier is None:
        return None
    return (
        table["prices"].get(binding, {}).get(tier, {}).get(f"{color}.{quality}", {}).get(paper)
    )


class LuluCalculator(BasePublisherCalculator):
    """Calculates publishing specifications according to Lulu requirements."""

    @property
    def publisher_name(self) -> str:
        return "Lulu"

    def calculate_spine(self, config: BookConfiguration) -> SpineSpecification:
        binding = config.binding or BindingType.PERFECT_BOUND
        paper_name = (config.paper_type.value if hasattr(config.paper_type, "value") else str(config.paper_type or "")).lower()
        is_hardcover = config.book_format == BookFormat.HARDCOVER or binding in (
            BindingType.CASEWRAP,
            BindingType.LINEN_WRAP_DUST_JACKET,
        )

        if binding == BindingType.SADDLE_STITCH:
            max_pages = LULU_SADDLE_STITCH_MAX_PAGES
        elif binding == BindingType.COIL:
            max_pages = LULU_COIL_MAX_PAGES
        elif is_hardcover:
            max_pages = LULU_HARDCOVER_MAX_PAGES
        else:
            max_pages = LULU_PAPERBACK_MAX_PAGES
        check_page_count_bounds(config.page_count, max_pages, "Lulu")

        if binding == BindingType.SADDLE_STITCH or binding == BindingType.COIL:
            # Coil bound and Saddle stitch books have no flat printable spine per Lulu guide
            return SpineSpecification(
                width=0.0,
                spine_text_allowed=False,
                min_pages_for_text=999,
                safe_margin=None,
                page_multiplier=0.0,
                hinge_allowance=0.0,
                unit="in",
            )
        elif is_hardcover:
            # Casewrap Hardcover uses discrete lookup table from Lulu guide Section 11.4
            spine_w = get_lulu_hardcover_spine(config.page_count)
            if spine_w is None:
                spine_w = 0.0
            text_allowed = config.page_count > LULU_SPINE_TEXT_MIN_PAGES
            safe_margin = LULU_SPINE_SAFE_MARGIN if text_allowed else None
            return SpineSpecification(
                width=round(spine_w, 4),
                spine_text_allowed=text_allowed,
                min_pages_for_text=LULU_SPINE_TEXT_MIN_PAGES + 1,
                safe_margin=safe_margin,
                page_multiplier=0.0,
                hinge_allowance=LULU_CASEWRAP_HINGE,
                unit="in",
            )
        else:
            # Standard Softcover Perfect Bound Paperback: (pages / 444) + 0.06 in
            # Exception for 460 PPI paper: (pages / 460) + 0.06 in
            is_460 = "460" in paper_name or "70" in paper_name
            divisor = LULU_PAPERBACK_SPINE_DIVISOR_460PPI_IN if is_460 else LULU_PAPERBACK_SPINE_DIVISOR_IN
            spine_w = round((config.page_count / divisor) + LULU_PAPERBACK_SPINE_BASE_IN, 4)
            text_allowed = config.page_count > LULU_SPINE_TEXT_MIN_PAGES
            safe_margin = LULU_SPINE_SAFE_MARGIN if text_allowed else None
            return SpineSpecification(
                width=spine_w,
                spine_text_allowed=text_allowed,
                min_pages_for_text=LULU_SPINE_TEXT_MIN_PAGES + 1,
                safe_margin=safe_margin,
                page_multiplier=round(1.0 / divisor, 6),
                hinge_allowance=LULU_PAPERBACK_SPINE_BASE_IN,
                unit="in",
            )

    @classmethod
    def resolve_pod_package_id(cls, config: BookConfiguration) -> str:
        """Resolve BookConfiguration to canonical Lulu dotted pod_package_id (SKU).

        Format (Lulu SKU Guide / ``lulu_api_doc.yml``):
        ``TRIM.COLOR.PRINT.BIND.PAPER.FINISH+LINEN+FOIL`` e.g.
        ``0600X0900.BW.STD.PB.060UW444.MXX``.

        Fails closed: raises :class:`UnsupportedPodPackageError` for any trim,
        ink, paper, binding or finish that is not in the vendored Lulu catalog
        (``lulu_sku.md``).  It never substitutes a default product.
        """
        trim_sku = find_lulu_trim_sku(config.trim_width, config.trim_height)
        if trim_sku is None:
            raise UnsupportedPodPackageError(
                f"Trim {config.trim_width:g} x {config.trim_height:g} in is not a Lulu catalog trim size "
                f"(supported: {', '.join(f'{w:g}x{h:g}' for w, h in LULU_TRIM_SKUS)})."
            )

        ink = config.interior_ink
        if ink not in _LULU_INK_SKUS:
            raise UnsupportedPodPackageError(
                f"Interior ink '{getattr(ink, 'value', ink)}' is not offered by Lulu."
            )
        color_sku, print_sku = _LULU_INK_SKUS[ink]

        bind_sku = _resolve_lulu_bind_sku(config)

        paper = config.paper_type
        if paper not in _LULU_PAPER_SKU_BY_TYPE:
            raise UnsupportedPodPackageError(
                f"Paper '{getattr(paper, 'value', paper)}' has no Lulu catalog paper code."
            )
        paper_sku = _LULU_PAPER_SKU_BY_TYPE[paper]

        finish = config.cover_finish or CoverFinish.MATTE
        if finish not in _LULU_FINISH_SKUS:
            raise UnsupportedPodPackageError(
                f"Cover finish '{getattr(finish, 'value', finish)}' is not offered by Lulu (Gloss or Matte)."
            )
        # Linen + foil are 'X' (none) for every binding we can resolve; linen
        # wrap (which needs a linen colour and foil) is refused above.
        finish_sku = f"{_LULU_FINISH_SKUS[finish]}XX"

        return f"{trim_sku}.{color_sku}.{print_sku}.{bind_sku}.{paper_sku}.{finish_sku}"

    def calculate_cover(
        self, config: BookConfiguration, spine: SpineSpecification | None = None
    ) -> CoverDimensions:
        if spine is None:
            spine = self.calculate_spine(config)

        trim_w = config.trim_width
        trim_h = config.trim_height
        is_hardcover = config.book_format == BookFormat.HARDCOVER or config.binding in (BindingType.CASEWRAP, BindingType.LINEN_WRAP_DUST_JACKET)

        if not is_hardcover:
            bleed = LULU_COVER_BLEED
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
            barcode_clearance = 0.5
            barcode_edge = bleed
        else:
            bleed = 0.0
            wrap = LULU_CASEWRAP_WRAP
            hinge = LULU_CASEWRAP_HINGE
            board_overhang = 0.250
            full_w = round((2 * (trim_w + hinge)) + spine.width + (2 * wrap), 4)
            full_h = round(trim_h + board_overhang + (2 * wrap), 4)
            front_w = round(trim_w + hinge, 4)
            front_h = round(trim_h + board_overhang, 4)
            back_w = round(trim_w + hinge, 4)
            back_h = round(trim_h + board_overhang, 4)
            spine_left_x = round(wrap + back_w, 4)
            spine_right_x = round(spine_left_x + spine.width, 4)
            barcode_clearance = 0.625
            # The template's barcode bottom is 1.25 inches from the canvas
            # edge (0.625 template wrap + 0.625 inset). Its wrap convention
            # differs from the existing board-geometry model; do not add that
            # model's 0.75-inch wrap to the template inset a second time.
            barcode_edge = 0.625

        # Vendor template measurements and hashes are recorded in
        # data/ground_truth/barcode_template_evidence.json. The reservation
        # stays inside the back panel, clear of the fold/hinge. Narrow trims
        # use the available safe width, as in Lulu's Pocket Book template.
        barcode_w = round(min(3.625, back_w - 2 * barcode_clearance), 4)
        barcode_h = 1.25
        barcode_x = round(spine_left_x - barcode_clearance - barcode_w, 4)
        barcode_y = round(barcode_edge + barcode_clearance, 4)

        barcode_box = {
            "x": barcode_x,
            "y": barcode_y,
            "width": barcode_w,
            "height": barcode_h,
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
            safe_margin_top=LULU_SAFETY_MARGIN_IN,
            safe_margin_bottom=LULU_SAFETY_MARGIN_IN,
            safe_margin_outside=LULU_SAFETY_MARGIN_IN,
            barcode_zone=barcode_box,
            unit="in",
        )

    def calculate_interior(self, config: BookConfiguration) -> InteriorDimensions:
        trim_w = config.trim_width
        trim_h = config.trim_height
        is_coil = config.binding == BindingType.COIL
        is_saddle = config.binding == BindingType.SADDLE_STITCH

        add_gutter = 0.0
        rec_inside = 0.500
        fb_inside = 0.625

        if is_coil:
            inside_margin = LULU_COIL_PUNCH_MARGIN
            rec_inside = LULU_COIL_PUNCH_MARGIN
            fb_inside = LULU_COIL_PUNCH_MARGIN
        elif is_saddle:
            inside_margin = 0.500
            rec_inside = 0.500
            fb_inside = 0.500
        else:
            gutter_spec = get_lulu_gutter_spec(config.page_count)
            add_gutter = gutter_spec.additional_gutter
            rec_inside = gutter_spec.recommended_inside_margin
            fb_inside = gutter_spec.full_bleed_inside_margin
            inside_margin = (
                fb_inside
                if config.has_bleed
                else rec_inside
            )

        if config.has_bleed:
            page_w = round(trim_w + (2 * LULU_INTERIOR_BLEED_SIDE), 4)
            page_h = round(trim_h + (2 * LULU_INTERIOR_BLEED_SIDE), 4)
            return InteriorDimensions(
                page_width=page_w,
                page_height=page_h,
                trim_width=trim_w,
                trim_height=trim_h,
                has_bleed=True,
                bleed_amount=LULU_INTERIOR_BLEED_SIDE,
                bleed_top=LULU_INTERIOR_BLEED_SIDE,
                bleed_bottom=LULU_INTERIOR_BLEED_SIDE,
                bleed_outside=LULU_INTERIOR_BLEED_SIDE,
                bleed_inside=LULU_INTERIOR_BLEED_SIDE,
                min_inside_margin=inside_margin,
                additional_gutter=add_gutter,
                recommended_inside_margin=rec_inside,
                full_bleed_inside_margin=fb_inside,
                min_outside_margin=LULU_SAFETY_MARGIN_IN,
                min_top_margin=LULU_SAFETY_MARGIN_IN,
                min_bottom_margin=LULU_SAFETY_MARGIN_IN,
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
                min_inside_margin=inside_margin,
                additional_gutter=add_gutter,
                recommended_inside_margin=rec_inside,
                full_bleed_inside_margin=fb_inside,
                min_outside_margin=LULU_SAFETY_MARGIN_IN,
                min_top_margin=LULU_SAFETY_MARGIN_IN,
                min_bottom_margin=LULU_SAFETY_MARGIN_IN,
                unit="in",
            )

    def calculate_economics(
        self,
        config: BookConfiguration,
        list_price: float | None = None,
        live_quote: bool = False,
        shipping_address: Any | None = None,
        shipping_option: str = "MAIL",
        pricing_service: Any | None = None,
        price_list: str = "sandbox",
    ) -> PrintEconomics | None:
        if live_quote:
            from mbooks.services.lulu_pricing import LuluPricingService

            service = pricing_service or LuluPricingService()
            return service.get_live_economics(
                book_config=config,
                list_price=list_price,
                shipping_address=shipping_address,
                shipping_option=shipping_option,
            )

        # Offline estimate from the calibrated Lulu price list: Lulu bills
        # fixed + page_count x per_page on the actual page count, rounded
        # half-up to the cent (verified against the cost API). A product Lulu
        # does not offer, or one not in the list, has no price at all.
        try:
            sku = self.resolve_pod_package_id(config)
        except UnsupportedPodPackageError:
            return None
        entry = lulu_price_entry(sku, price_list)
        if entry is None:
            return None
        pages = max(1, config.page_count)
        fixed_dec = Decimal(entry["fixed"])
        per_page_dec = Decimal(entry["per_page"])
        fixed = float(fixed_dec)
        per_page = float(per_page_dec)

        # Money is computed in Decimal and rounded half-up to the cent, like Lulu.
        cent = Decimal("0.01")
        est_cost_dec = (fixed_dec + pages * per_page_dec).quantize(cent, ROUND_HALF_UP)
        est_print_cost = float(est_cost_dec)
        # Lulu Global Distribution model: 50% distribution fee -> min price = 2x print cost
        min_list = float((est_cost_dec * 2).quantize(cent, ROUND_HALF_UP))

        resolved_list_price = float(list_price) if list_price is not None else None
        if resolved_list_price is not None and resolved_list_price <= 0.0:
            resolved_list_price = None

        est_royalty = None
        if resolved_list_price is not None:
            gross_profit = max(
                Decimal("0"),
                Decimal(str(resolved_list_price)) * Decimal("0.50") - est_cost_dec,
            )
            est_royalty = float((gross_profit * Decimal("0.80")).quantize(cent, ROUND_HALF_UP))

        return PrintEconomics(
            fixed_cost=fixed,
            per_page_cost=per_page,
            page_count=pages,
            estimated_print_cost=est_print_cost,
            min_list_price=min_list,
            estimated_royalty=est_royalty,
            list_price=resolved_list_price,
            currency="USD",
            marketplace="US",
            publisher="Lulu",
        )

    def calculate(
        self,
        config: BookConfiguration,
        list_price: float | None = None,
        live_quote: bool = False,
        shipping_address: Any | None = None,
        shipping_option: str = "MAIL",
        pricing_service: Any | None = None,
        **kwargs: Any,
    ) -> CalculatedSpecification:
        """Orchestrate complete physical specification and economics calculation.

        Supports both fast offline estimates (live_quote=False) and real-time carrier quotes (live_quote=True).
        """
        spine = self.calculate_spine(config)
        cover = self.calculate_cover(config, spine=spine)
        interior = self.calculate_interior(config)
        economics = self.calculate_economics(
            config,
            list_price=list_price,
            live_quote=live_quote,
            shipping_address=shipping_address,
            shipping_option=shipping_option,
            pricing_service=pricing_service,
        )

        # A configuration outside Lulu's catalog has no orderable product; the
        # geometry is still reported, but the SKU is explicitly absent (never a
        # substitute).  Configuration validation BLOCKs such configs.
        try:
            pod_sku: str | None = self.resolve_pod_package_id(config)
        except UnsupportedPodPackageError:
            pod_sku = None
        return CalculatedSpecification(
            publisher=self.publisher_name,
            pod_package_id=pod_sku,
            spine=spine,
            cover=cover,
            interior=interior,
            spine_width=spine.width,
            spine_text_allowed=spine.spine_text_allowed,
            weight_lb=spine.weight_lb,
            weight_g=spine.weight_g,
            economics=economics,
            unit="in",
        )
