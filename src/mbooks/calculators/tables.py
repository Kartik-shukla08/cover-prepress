"""Calculation tables, constants, and lookup datasets for publishing platforms."""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple, TYPE_CHECKING

if TYPE_CHECKING:
    from mbooks.domain.book import BookConfiguration
    from mbooks.domain.geometry import TrimSize

from mbooks.domain.enums import (
    BindingType,
    BookFormat,
    DistributionGoal,
    InteriorInk,
    PaperType,
)
from .errors import (
    PageCountOutOfRangeError,
    UnsupportedCurrencyError,
    UnsupportedEconomicsConfigurationError,
)


# =============================================================================
# Amazon KDP Tables & Constants
# =============================================================================

# Spine multiplier (inches per page) by (InteriorInk, PaperType)
KDP_SPINE_MULTIPLIERS: dict[tuple[str, str], float] = {
    ("B&W", "White"): 0.002252,
    ("B&W", "Cream"): 0.002500,
    ("B&W", "Groundwood"): 0.002350,
    ("Standard Color", "White"): 0.002252,
    ("Premium Color", "White"): 0.002347,
    # Extended enum variant mappings
    ("B&W", "White 50lb/74gsm"): 0.002252,
    ("B&W", "Crème 50lb/74gsm"): 0.002500,
    ("B&W", "Groundwood 38lb/56gsm"): 0.002350,
    ("Standard Color", "White 50lb/74gsm"): 0.002252,
    ("Premium Color", "White 50lb/74gsm"): 0.002347,
    ("Premium Color", "White 70lb/104gsm"): 0.002347,
    ("Standard Color", "Cream"): 0.002500,
    ("Premium Color", "Cream"): 0.002500,
}

KDP_SPINE_HINGE_CONSTANT: float = 0.0    # Authoritative Paperback spine has no hinge addition
KDP_FOLD_VARIANCE_TOLERANCE: float = 0.0625  # 1/16" (1.6 mm) manufacturing fold variance
KDP_TRIM_VARIANCE_TOLERANCE: float = 0.0625  # 1/16" (1.6 mm) trim shift tolerance
KDP_SPINE_TEXT_MIN_PAGES: int = 80       # Minimum pages for spine text
KDP_SPINE_SAFE_MARGIN: float = 0.0625    # 1/16" (1.6 mm) safety margin per side
KDP_COVER_BLEED: float = 0.125           # 1/8" bleed per side
KDP_INTERIOR_BLEED_SIDE: float = 0.125   # Outside, top, bottom bleed
KDP_HARDCOVER_WRAP: float = 0.591        # 15 mm (0.591") wrap allowance per side
KDP_HARDCOVER_HINGE: float = 0.394       # 10 mm (0.394") hinge allowance per side
KDP_HARDCOVER_BOARD_OVERHANG_W: float = 0.197  # 5 mm (0.197") board width overhang
KDP_HARDCOVER_BOARD_OVERHANG_H: float = 0.236  # 6 mm (0.236") board height overhang (3mm top + 3mm bottom)
# TODO(astra-1.3): no KDP primary source found for this allowance (not in the vendored
# docs nor KDP help pages consulted by the Astra audit). It is an EMPIRICAL constant
# reverse-fitted to KDP Cover Calculator output (e.g. 350 pp Premium Color White -> 1.01").
# Replace with a sourced value or a captured calculator table before relying on it.
KDP_HARDCOVER_SPINE_ALLOWANCE: float = 0.18855
KDP_HARDCOVER_SPINE_ALLOWANCE_IS_EMPIRICAL: bool = True
KDP_HARDCOVER_BARCODE_MARGIN_H: float = 0.375  # Hardcover barcode margin height
KDP_HARDCOVER_BARCODE_HINGE_CLEARANCE: float = 0.25  # Barcode must stay >= 0.25" clear of the hinge (Astra N13)
INGRAM_FOLD_VARIANCE_TOLERANCE: float = 0.0625  # 1/16" fold variance
INGRAM_TRIM_VARIANCE_TOLERANCE: float = 0.0625  # 1/16" trim variance
LULU_FOLD_VARIANCE_TOLERANCE: float = 0.0625    # 1/16" fold variance
LULU_TRIM_VARIANCE_TOLERANCE: float = 0.125      # 1/8" (3.175 mm) trim variance per lulu_guide.md Section 13.3 & 21


# =============================================================================
# Shared money / page helpers (Astra N9 "All vendors")
# =============================================================================

_CENT = Decimal("0.01")


def round_money(value: Decimal | float | int | str) -> Decimal:
    """Quantize a money value to cents with ROUND_HALF_UP (never float rounding)."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    return d.quantize(_CENT, rounding=ROUND_HALF_UP)


def billed_page_count(page_count: int) -> int:
    """Vendors print on sheets (2 pages); odd counts are billed as the next even count."""
    return page_count + (page_count % 2)


def check_page_count_bounds(page_count: int, max_pages: int, publisher: str) -> None:
    """Reject page counts outside the vendor's absolute manufacturable range (Astra N14)."""
    if page_count > max_pages:
        raise PageCountOutOfRangeError(
            f"{publisher}: page count {page_count} exceeds maximum supported pages of {max_pages}."
        )


# KDP Stepped Gutter / Inside Margin table: (min_pages, max_pages, min_inside_margin)
KDP_GUTTER_BANDS: list[tuple[int, int, float]] = [
    (24, 150, 0.375),
    (151, 300, 0.500),
    (301, 500, 0.625),
    (501, 700, 0.750),
    (701, 828, 0.875),
]

KDP_MIN_OUTSIDE_MARGIN_NO_BLEED: float = 0.250
KDP_MIN_OUTSIDE_MARGIN_BLEED: float = 0.375

# Absolute page-count maxima (KDP help G201834180: paperback 24-828, hardcover 75-550)
KDP_PAPERBACK_MAX_PAGES: int = 828
KDP_HARDCOVER_MAX_PAGES: int = 550


def get_kdp_spine_multiplier(ink: str, paper: str) -> float:
    """Safely resolve KDP spine multiplier across paper type variants."""
    key = (ink, paper)
    if key in KDP_SPINE_MULTIPLIERS:
        return KDP_SPINE_MULTIPLIERS[key]

    p_lower = paper.lower()
    if "cream" in p_lower or "crème" in p_lower or "creme" in p_lower:
        norm_paper = "Cream"
    elif "groundwood" in p_lower:
        norm_paper = "Groundwood"
    else:
        norm_paper = "White"

    return KDP_SPINE_MULTIPLIERS.get((ink, norm_paper), 0.002252)


# --- Amazon KDP Economics Constants (Post-June 20, 2023 Official Model) ---

KDP_REGULAR_TRIM_MAX_W: float = 6.12
KDP_REGULAR_TRIM_MAX_H: float = 9.0

KDP_PAPERBACK_FIXED_BASE: float = 1.00
KDP_HARDCOVER_FIXED_BASE: float = 5.65

# Flat fee page thresholds for short books.
# Astra N9: KDP's B&W regular-trim flat band is 24-110 pages (was 108 here, so a
# 110-page book was billed $2.32 instead of $2.30).
KDP_BW_SHORT_PAGE_THRESHOLD: int = 110
KDP_BW_SHORT_PAGE_THRESHOLD_GROUNDWOOD: int = 112
KDP_PREMIUM_COLOR_SHORT_PAGE_THRESHOLD: int = 40
KDP_HARDCOVER_BW_SHORT_PAGE_THRESHOLD: int = 108

# Flat fees for short paperbacks (pages <= threshold)
KDP_BW_REGULAR_SHORT_FLAT: float = 2.30
KDP_BW_REGULAR_SHORT_FLAT_GROUNDWOOD: float = 2.23
KDP_BW_LARGE_SHORT_FLAT: float = 2.84
KDP_BW_LARGE_SHORT_FLAT_GROUNDWOOD: float = 2.75

KDP_PREMIUM_COLOR_REGULAR_SHORT_FLAT: float = 3.60
KDP_PREMIUM_COLOR_LARGE_SHORT_FLAT: float = 4.20

# Flat fees for short hardcovers (75 <= pages <= 108)
KDP_HARDCOVER_BW_REGULAR_SHORT_FLAT: float = 6.80
KDP_HARDCOVER_BW_LARGE_SHORT_FLAT: float = 7.49

# Per-page rates
KDP_BW_REGULAR_PER_PAGE: float = 0.012
KDP_BW_REGULAR_PER_PAGE_GROUNDWOOD: float = 0.0114
KDP_BW_LARGE_PER_PAGE: float = 0.017
KDP_BW_LARGE_PER_PAGE_GROUNDWOOD: float = 0.0162

KDP_STANDARD_COLOR_REGULAR_PER_PAGE: float = 0.0255
KDP_STANDARD_COLOR_LARGE_PER_PAGE: float = 0.0402
KDP_STANDARD_COLOR_PER_PAGE: float = 0.0255  # Alias for backward compatibility

KDP_PREMIUM_COLOR_REGULAR_PER_PAGE: float = 0.065
KDP_PREMIUM_COLOR_LARGE_PER_PAGE: float = 0.080

# Royalty Rates
# Astra N9 / KDP help G201834330 & G77F3WPD3KQLJTFS (June 2025 terms): Amazon
# marketplace sales pay 60% above the threshold and 50% at or below it, paperback
# and hardcover alike. Expanded Distribution (paperback only) pays 40%.
KDP_ROYALTY_RATE_STANDARD: float = 0.60
KDP_ROYALTY_RATE_LOW_PRICE: float = 0.50
KDP_ROYALTY_RATE_EXPANDED: float = 0.40
# Inclusive list-price ceiling of the 50% tier, per currency. Only USD (Amazon.com,
# $9.98) is sourced (Astra report); other marketplaces are refused, not guessed.
KDP_LOW_PRICE_TIER_MAX_LIST_PRICE: dict[str, Decimal] = {
    "USD": Decimal("9.98"),
}
KDP_SUPPORTED_CURRENCIES: frozenset[str] = frozenset(KDP_LOW_PRICE_TIER_MAX_LIST_PRICE)



# =============================================================================
# IngramSpark Tables & Constants
# =============================================================================

# IngramSpark PPI and Caliper by PaperType / weight
class IngramPaperSpec(NamedTuple):
    ppi: int
    caliper: float  # inches per page
    gsm: float = 74.0
    case_laminate_allowance: float = 0.059


INGRAM_PAPER_SPECS: dict[str, IngramPaperSpec] = {
    "Groundwood": IngramPaperSpec(ppi=401, caliper=0.0024933, gsm=66.538, case_laminate_allowance=0.059),
    "White": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),        # 50# White B&W
    "Cream": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),       # 50# Crème B&W (live official: 0.674" / 300 pgs)
    "Creme": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "Crème": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "Color 50": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),    # 50# White Color 50
    "Color 70": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),   # 70# White Color 70
    "70# White": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),  # 70# White
    "White 70": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),   # 70# White
    "Coated White": IngramPaperSpec(ppi=326, caliper=0.003067, gsm=118.0, case_laminate_allowance=0.059), # 80# Coated White (Ultra-Premium)
    "Premium Color": IngramPaperSpec(ppi=385, caliper=0.0025978, gsm=100.459, case_laminate_allowance=0.059),
    "Premium Colour": IngramPaperSpec(ppi=385, caliper=0.0025978, gsm=100.459, case_laminate_allowance=0.059),
    "Ultra Premium Color": IngramPaperSpec(ppi=385, caliper=0.0025978, gsm=118.0, case_laminate_allowance=0.059),
    "Ultra Premium Colour": IngramPaperSpec(ppi=385, caliper=0.0025978, gsm=118.0, case_laminate_allowance=0.059),
    "Ultra-Premium Color": IngramPaperSpec(ppi=385, caliper=0.0025978, gsm=118.0, case_laminate_allowance=0.059),
    "Ultra-Premium Colour": IngramPaperSpec(ppi=385, caliper=0.0025978, gsm=118.0, case_laminate_allowance=0.059),
    "White 50": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "Colour 50": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "Colour 70": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),
    # Enum variant mappings
    "Groundwood 38lb/56gsm": IngramPaperSpec(ppi=401, caliper=0.0024933, gsm=66.538, case_laminate_allowance=0.059),
    "White 50lb/74gsm": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "Crème 50lb/74gsm": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "Creme 50lb/74gsm": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "White 70lb/104gsm": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),
    "Coated White 80lb/118gsm": IngramPaperSpec(ppi=326, caliper=0.003067, gsm=118.0, case_laminate_allowance=0.059),
    # Common alternate string names
    "50# White": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "White 50#": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "50# Cream": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "Cream 50#": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "50# Crème": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "50# Creme": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "Crème 50#": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "Creme 50#": IngramPaperSpec(ppi=445, caliper=0.0022467, gsm=74.023, case_laminate_allowance=0.139),
    "38# Groundwood": IngramPaperSpec(ppi=401, caliper=0.0024933, gsm=66.538, case_laminate_allowance=0.059),
    "Groundwood 38#": IngramPaperSpec(ppi=401, caliper=0.0024933, gsm=66.538, case_laminate_allowance=0.059),
    "70#": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),
    "70lb": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),
    "70 lb": IngramPaperSpec(ppi=368, caliper=0.0027167, gsm=100.459, case_laminate_allowance=0.059),
    "50#": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "50lb": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "50 lb": IngramPaperSpec(ppi=477, caliper=0.0020967, gsm=74.036, case_laminate_allowance=0.059),
    "38#": IngramPaperSpec(ppi=401, caliper=0.0024933, gsm=66.538, case_laminate_allowance=0.059),
    "38lb": IngramPaperSpec(ppi=401, caliper=0.0024933, gsm=66.538, case_laminate_allowance=0.059),
    "38 lb": IngramPaperSpec(ppi=401, caliper=0.0024933, gsm=66.538, case_laminate_allowance=0.059),
    "80#": IngramPaperSpec(ppi=326, caliper=0.003067, gsm=118.0, case_laminate_allowance=0.059),
    "80lb": IngramPaperSpec(ppi=326, caliper=0.003067, gsm=118.0, case_laminate_allowance=0.059),
    "80 lb": IngramPaperSpec(ppi=326, caliper=0.003067, gsm=118.0, case_laminate_allowance=0.059),
}

INGRAM_COVER_GSM_PAPERBACK: float = 242.12  # 10pt C1S softcover stock with laminate
INGRAM_BOARD_GSM_HARDCOVER: float = 2505.3  # 98pt binders board + printed laminated wrap
INGRAM_CASE_LAMINATE_SPINE_ALLOWANCE_DEFAULT: float = 0.059
INGRAM_CASE_LAMINATE_SPINE_ALLOWANCE_CREME: float = 0.139

INGRAM_SPINE_TEXT_MIN_PAGES: int = 48
INGRAM_COVER_BLEED: float = 0.125
INGRAM_CASE_LAMINATE_WRAP: float = 0.625             # 5/8" wrap for hardcover per ingram_guide.md Section 7.2
INGRAM_CASE_LAMINATE_HINGE: float = 0.500            # 1/2" hinge score per side per ingram_guide.md Section 7.2
INGRAM_CASE_LAMINATE_BOARD_SETBACK_W: float = 0.185  # -0.185" board width setback
INGRAM_CASE_LAMINATE_BOARD_OVERHANG_H: float = 0.250 # +0.250" board height overhang

INGRAM_DUST_JACKET_FLAP_W: float = 3.250             # 3.25" flap per side per ingram_guide.md Section 7.3
INGRAM_DUST_JACKET_FOLD_W: float = 0.250             # 0.25" fold per side
INGRAM_DUST_JACKET_COVER_OVERHANG_W: float = 0.4375  # +0.4375" cover width allowance
INGRAM_DUST_JACKET_COVER_OVERHANG_H: float = 0.2500  # +0.250" cover height allowance
INGRAM_DUST_JACKET_BLEED: float = 0.125              # 0.125" outer bleed

INGRAM_INTERIOR_BLEED_SIDE: float = 0.125
INGRAM_RECOMMENDED_SAFETY: float = 0.500
INGRAM_COVER_TYPE_SAFETY: float = 0.250


def get_ingram_paper_spec(paper: str, ink: str = "B&W") -> IngramPaperSpec:
    """Safely resolve IngramSpark paper PPI/caliper spec across paper variants and ink types.
    
    IngramSpark live official calibrations:
    - 50# White (B&W and Color 50): 477 PPI (0.0020967" / page, 0.053257 mm/page)
    - 50# Crème (B&W): 445 PPI (0.0022467" / page, 0.057067 mm/page)
    - 38# Groundwood (B&W): 401 PPI (0.0024933" / page, 0.063330 mm/page)
    - 70# White (B&W and Color 70): 368 PPI (0.0027167" / page, 0.069003 mm/page)
    """
    ink_lower = str(ink).lower()
    is_color = "color" in ink_lower or "colour" in ink_lower
    is_ultra = "ultra" in ink_lower
    is_premium = "premium" in ink_lower and not is_ultra

    p_lower = str(paper).strip().lower()

    # 1. Stock-specific matches always take precedence regardless of ink or casing
    if "ultra" in p_lower:
        return INGRAM_PAPER_SPECS["Ultra Premium Color"]
    if "premium" in p_lower:
        return INGRAM_PAPER_SPECS["Premium Color"]
    if "cream" in p_lower or "crème" in p_lower or "creme" in p_lower:
        return INGRAM_PAPER_SPECS["Cream"]
    if "groundwood" in p_lower or "38" in p_lower:
        return INGRAM_PAPER_SPECS["Groundwood"]
    if "coated" in p_lower or "80" in p_lower:
        return INGRAM_PAPER_SPECS["Coated White"]
    if "color 50" in p_lower or "colour 50" in p_lower:
        return INGRAM_PAPER_SPECS["Color 50"]
    if "color 70" in p_lower or "colour 70" in p_lower:
        return INGRAM_PAPER_SPECS["Color 70"]
    if "white 70" in p_lower or ("white" in p_lower and "70" in p_lower) or "70" in p_lower or "104" in p_lower:
        return INGRAM_PAPER_SPECS["70# White"]
    if "white 50" in p_lower or ("white" in p_lower and "50" in p_lower):
        return INGRAM_PAPER_SPECS["White"]

    # 2. Check exact known keys in dictionary
    if paper in INGRAM_PAPER_SPECS:
        if paper in ("White", "White 50lb/74gsm", "50# White", "White 50#", "50#", "50lb", "50 lb"):
            if is_ultra:
                return INGRAM_PAPER_SPECS["Coated White"]
            elif is_premium:
                return INGRAM_PAPER_SPECS["Color 70"]
            elif is_color:
                return INGRAM_PAPER_SPECS["Color 50"]
        return INGRAM_PAPER_SPECS[paper]

    # 3. For White or unspecified paper stock, resolve stock via ink type
    if is_ultra:
        return INGRAM_PAPER_SPECS["Coated White"]
    elif is_premium:
        return INGRAM_PAPER_SPECS["Color 70"]
    elif is_color:
        return INGRAM_PAPER_SPECS["Color 50"]

    return INGRAM_PAPER_SPECS["White"]


# --- IngramSpark Economics Constants & Lookup Tables (Authoritative: INGRAM_PRICESHEET.md Feb 1, 2026) ---

INGRAM_SMALL_TRIM_MAX_WIDTH: float = 6.15  # Small = < 6.15 width (15.62cm)

# Baseline per-cover constants (Small B&W 50# White baseline from official schedule)
INGRAM_BASE_BINDING_PAPERBACK: float = 1.33
INGRAM_BASE_BINDING_HARDCOVER_CASEWRAP: float = 5.31
INGRAM_BASE_BINDING_HARDCOVER_DUST_JACKET: float = 7.76

# Cover Add-ons & Surcharges
INGRAM_DUPLEX_COVER_ADDON: float = 0.30  # USD $0.30 per cover printed
INGRAM_DUPLEX_COVER_RATES: dict[str, float] = {
    "USD": 0.30,
    "GBP": 0.20,
    "AUD": 0.35,
    "EUR": 0.25,
}

INGRAM_PERFORATION_ADDON_PER_PAGE: float = 0.0030  # USD $0.0030 per page printed (US only)
INGRAM_MARKET_ACCESS_FEE_RATE: float = 0.01875    # 1.875% of local list price at time of sale

# Wholesale Discounts
# Astra N9: "DIRECT" used to be modelled as a 40% wholesale discount. That is not an
# IngramSpark concept: publisher-direct orders are author copies bought at print cost
# (see INGRAM_PRICESHEET.md "Publisher Direct Orders"). The constant was removed;
# DistributionGoal.DIRECT now maps to publisher-direct economics (no wholesale/royalty).
INGRAM_WHOLESALE_DISCOUNT_STANDARD: float = 0.55

# Absolute IngramSpark page-count maximum across the 2026 price sheet (50# white: 1200)
INGRAM_MAX_PAGES: int = 1200

# Structured Dictionaries
INGRAM_BINDING_RATES: dict[str, float] = {
    "paperback_perfect_bound": INGRAM_BASE_BINDING_PAPERBACK,
    "hardcover_casewrap": INGRAM_BASE_BINDING_HARDCOVER_CASEWRAP,
    "hardcover_dust_jacket": INGRAM_BASE_BINDING_HARDCOVER_DUST_JACKET,
}

INGRAM_WHOLESALE_DISCOUNTS: dict[str, float] = {
    "standard": INGRAM_WHOLESALE_DISCOUNT_STANDARD,
}

INGRAM_DIRECT_QUANTITY_DISCOUNTS: list[tuple[int, float]] = [
    (10000, 0.35),
    (5000, 0.30),
    (2500, 0.25),
    (1500, 0.20),
    (1000, 0.15),
    (500, 0.10),
    (400, 0.075),
    (300, 0.05),
    (100, 0.02),
    (1, 0.00),
]

# Baseline per-page rates for common Small 6x9 stock
INGRAM_PER_PAGE_RATES: dict[str, dict[str, float]] = {
    "BW": {
        "50_white_creme": 0.0146,
        "70_white": 0.0232,
        "38_groundwood": 0.0144,
    },
    "STANDARD_COLOR": {
        "50_white": 0.0249,
        "70_white": 0.0374,
    },
    "PREMIUM_COLOR": {
        "70_white": 0.0721,
        "80_coated_white": 0.0849,
    },
}

# --- Official IngramSpark 39-Product Matrix Across Currencies ---
# Key: (size, binding, ink, paper) -> (per_cover, per_page, min_pages, max_pages)

INGRAM_PRINT_RATES_USD: dict[tuple[str, str, str, str], tuple[float, float, int, int]] = {
    ('small', 'paperback', 'bw', 'groundwood'): (1.33, 0.0144, 18, 900),
    ('small', 'hardcover', 'bw', 'groundwood'): (5.71, 0.0141, 18, 840),
    ('small', 'hardcover_jacket', 'bw', 'groundwood'): (7.76, 0.0145, 18, 840),
    ('large', 'paperback', 'bw', 'groundwood'): (1.39, 0.0211, 18, 900),
    ('small', 'paperback', 'bw', '50_creme'): (1.33, 0.0146, 18, 1050),
    ('small', 'paperback', 'bw', '50_white'): (1.33, 0.0146, 18, 1200),
    ('large', 'paperback', 'bw', '50_white'): (1.39, 0.0212, 18, 1200),
    ('small', 'hardcover', 'bw', '50_creme'): (5.31, 0.0132, 18, 1050),
    ('small', 'hardcover', 'bw', '50_white'): (5.31, 0.0132, 18, 1200),
    ('small', 'hardcover_jacket', 'bw', '50_creme'): (7.76, 0.0147, 18, 1050),
    ('small', 'hardcover_jacket', 'bw', '50_white'): (7.76, 0.0147, 18, 1200),
    ('large', 'hardcover', 'bw', '50_white'): (5.26, 0.0185, 18, 1200),
    ('small', 'paperback', 'bw', '70_white'): (1.35, 0.0232, 18, 900),
    ('large', 'paperback', 'bw', '70_white'): (1.41, 0.0361, 18, 900),
    ('small', 'hardcover', 'bw', '70_white'): (5.88, 0.0229, 18, 840),
    ('small', 'hardcover_jacket', 'bw', '70_white'): (7.76, 0.0229, 18, 840),
    ('large', 'hardcover', 'bw', '70_white'): (6.01, 0.0357, 18, 840),
    ('small', 'paperback', 'std_color', '50_white'): (1.16, 0.0249, 18, 1200),
    ('large', 'paperback', 'std_color', '50_white'): (1.23, 0.0392, 18, 1200),
    ('small', 'hardcover', 'std_color', '50_white'): (6.38, 0.0276, 18, 1200),
    ('small', 'hardcover_jacket', 'std_color', '50_white'): (8.43, 0.0276, 18, 1200),
    ('large', 'hardcover', 'std_color', '50_white'): (6.55, 0.0427, 18, 1200),
    ('small', 'paperback', 'std_color', '70_white'): (1.35, 0.0374, 18, 900),
    ('large', 'paperback', 'std_color', '70_white'): (1.41, 0.0593, 18, 900),
    ('small', 'hardcover', 'std_color', '70_white'): (6.38, 0.0359, 18, 840),
    ('small', 'hardcover_jacket', 'std_color', '70_white'): (8.43, 0.0359, 18, 840),
    ('large', 'hardcover', 'std_color', '70_white'): (6.55, 0.0572, 18, 840),
    ('small', 'paperback', 'premium_color', '70_white'): (1.35, 0.0721, 18, 900),
    ('large', 'paperback', 'premium_color', '70_white'): (1.41, 0.0946, 18, 900),
    ('small', 'hardcover', 'premium_color', '70_white'): (6.51, 0.0752, 18, 840),
    ('small', 'hardcover_jacket', 'premium_color', '70_white'): (8.43, 0.0752, 18, 840),
    ('large', 'hardcover', 'premium_color', '70_white'): (6.69, 0.1003, 18, 840),
    ('small', 'paperback', 'ultra_premium_color', '70_white'): (2.66, 0.0849, 18, 900),
    ('large', 'paperback', 'ultra_premium_color', '70_white'): (2.66, 0.1061, 18, 900),
    ('large', 'paperback_landscape', 'ultra_premium_color', '70_white'): (2.66, 0.1061, 18, 400),
    ('small', 'hardcover', 'ultra_premium_color', '70_white'): (7.70, 0.0849, 18, 840),
    ('small', 'hardcover_jacket', 'ultra_premium_color', '70_white'): (9.55, 0.0849, 18, 840),
    ('large', 'hardcover', 'ultra_premium_color', '70_white'): (7.70, 0.1061, 18, 840),
    ('large', 'hardcover_landscape', 'ultra_premium_color', '70_white'): (7.70, 0.1061, 18, 400),
}

INGRAM_PRINT_RATES_GBP: dict[tuple[str, str, str, str], tuple[float, float, int, int]] = {
    ('small', 'paperback', 'bw', 'groundwood'): (1.37, 0.0115, 18, 900),
    ('small', 'hardcover', 'bw', 'groundwood'): (5.06, 0.0115, 18, 840),
    ('small', 'hardcover_jacket', 'bw', 'groundwood'): (6.33, 0.0115, 18, 840),
    ('small', 'paperback', 'bw', '50_creme'): (1.37, 0.0116, 18, 1050),
    ('small', 'paperback', 'bw', '50_white'): (1.37, 0.0116, 18, 1200),
    ('large', 'paperback', 'bw', '50_white'): (1.37, 0.0196, 18, 1200),
    ('small', 'hardcover', 'bw', '50_creme'): (5.06, 0.0116, 18, 1050),
    ('small', 'hardcover', 'bw', '50_white'): (5.06, 0.0116, 18, 1200),
    ('small', 'hardcover_jacket', 'bw', '50_creme'): (6.33, 0.0116, 18, 1050),
    ('small', 'hardcover_jacket', 'bw', '50_white'): (6.33, 0.0116, 18, 1200),
    ('large', 'hardcover', 'bw', '50_white'): (5.21, 0.0202, 18, 1200),
    ('small', 'paperback', 'bw', '70_white'): (1.41, 0.0137, 18, 900),
    ('large', 'paperback', 'bw', '70_white'): (1.41, 0.0231, 18, 900),
    ('small', 'hardcover', 'bw', '70_white'): (5.21, 0.0137, 18, 840),
    ('small', 'hardcover_jacket', 'bw', '70_white'): (6.52, 0.0137, 18, 840),
    ('large', 'hardcover', 'bw', '70_white'): (5.21, 0.0231, 18, 840),
    ('small', 'paperback', 'std_color', '50_white'): (1.41, 0.0222, 18, 1200),
    ('large', 'paperback', 'std_color', '50_white'): (1.41, 0.0325, 18, 1200),
    ('small', 'hardcover', 'std_color', '50_white'): (5.21, 0.0222, 18, 1200),
    ('small', 'hardcover_jacket', 'std_color', '50_white'): (6.52, 0.0222, 18, 1200),
    ('large', 'hardcover', 'std_color', '50_white'): (5.21, 0.0325, 18, 1200),
    ('small', 'paperback', 'std_color', '70_white'): (1.41, 0.0239, 18, 900),
    ('large', 'paperback', 'std_color', '70_white'): (1.41, 0.0353, 18, 900),
    ('small', 'hardcover', 'std_color', '70_white'): (5.21, 0.0239, 18, 840),
    ('small', 'hardcover_jacket', 'std_color', '70_white'): (6.52, 0.0239, 18, 840),
    ('large', 'hardcover', 'std_color', '70_white'): (5.21, 0.0353, 18, 840),
    ('small', 'paperback', 'premium_color', '70_white'): (1.41, 0.0457, 18, 900),
    ('large', 'paperback', 'premium_color', '70_white'): (1.41, 0.0637, 18, 900),
    ('small', 'hardcover', 'premium_color', '70_white'): (5.21, 0.0443, 18, 840),
    ('small', 'hardcover_jacket', 'premium_color', '70_white'): (6.52, 0.0443, 18, 840),
    ('large', 'hardcover', 'premium_color', '70_white'): (5.21, 0.0618, 18, 840),
    ('small', 'paperback', 'ultra_premium_color', '70_white'): (1.41, 0.0608, 18, 900),
    ('large', 'paperback', 'ultra_premium_color', '70_white'): (1.41, 0.0847, 18, 900),
    ('large', 'paperback_landscape', 'ultra_premium_color', '70_white'): (2.01, 0.1046, 18, 400),
    ('small', 'hardcover', 'ultra_premium_color', '70_white'): (5.21, 0.0591, 18, 840),
    ('small', 'hardcover_jacket', 'ultra_premium_color', '70_white'): (6.52, 0.0591, 18, 840),
    ('large', 'hardcover', 'ultra_premium_color', '70_white'): (5.21, 0.0823, 18, 840),
    ('large', 'hardcover_landscape', 'ultra_premium_color', '70_white'): (4.92, 0.1046, 18, 400),
}

INGRAM_PRINT_RATES_AUD: dict[tuple[str, str, str, str], tuple[float, float, int, int]] = {
    ('small', 'paperback', 'bw', 'groundwood'): (2.50, 0.0245, 18, 900),
    ('small', 'hardcover', 'bw', 'groundwood'): (9.36, 0.0231, 18, 840),
    ('small', 'hardcover_jacket', 'bw', 'groundwood'): (11.68, 0.0231, 18, 840),
    ('small', 'paperback', 'bw', '50_creme'): (2.50, 0.0248, 18, 1050),
    ('small', 'paperback', 'bw', '50_white'): (2.50, 0.0248, 18, 1200),
    ('large', 'paperback', 'bw', '50_white'): (2.50, 0.0351, 18, 1200),
    ('small', 'hardcover', 'bw', '50_creme'): (9.36, 0.0233, 18, 1050),
    ('small', 'hardcover', 'bw', '50_white'): (9.36, 0.0233, 18, 1200),
    ('small', 'hardcover_jacket', 'bw', '50_creme'): (11.68, 0.0233, 18, 1050),
    ('small', 'hardcover_jacket', 'bw', '50_white'): (11.68, 0.0233, 18, 1200),
    ('large', 'hardcover', 'bw', '50_white'): (9.36, 0.0331, 18, 1200),
    ('small', 'paperback', 'bw', '70_white'): (2.57, 0.0286, 18, 900),
    ('large', 'paperback', 'bw', '70_white'): (2.57, 0.0414, 18, 900),
    ('small', 'hardcover', 'bw', '70_white'): (9.36, 0.0263, 18, 840),
    ('small', 'hardcover_jacket', 'bw', '70_white'): (11.68, 0.0263, 18, 840),
    ('large', 'hardcover', 'bw', '70_white'): (9.63, 0.0391, 18, 840),
    ('small', 'paperback', 'std_color', '50_white'): (2.57, 0.0401, 18, 1200),
    ('large', 'paperback', 'std_color', '50_white'): (2.57, 0.0586, 18, 1200),
    ('small', 'hardcover', 'std_color', '50_white'): (9.63, 0.0378, 18, 1200),
    ('small', 'hardcover_jacket', 'std_color', '50_white'): (12.03, 0.0378, 18, 1200),
    ('large', 'hardcover', 'std_color', '50_white'): (9.63, 0.0553, 18, 1200),
    ('small', 'paperback', 'std_color', '70_white'): (2.57, 0.0434, 18, 900),
    ('large', 'paperback', 'std_color', '70_white'): (2.57, 0.0638, 18, 900),
    ('small', 'hardcover', 'std_color', '70_white'): (9.63, 0.0409, 18, 840),
    ('small', 'hardcover_jacket', 'std_color', '70_white'): (12.03, 0.0409, 18, 840),
    ('large', 'hardcover', 'std_color', '70_white'): (9.63, 0.0602, 18, 840),
    ('small', 'paperback', 'premium_color', '70_white'): (2.57, 0.0598, 18, 900),
    ('large', 'paperback', 'premium_color', '70_white'): (2.57, 0.1127, 18, 900),
    ('small', 'hardcover', 'premium_color', '70_white'): (9.63, 0.0604, 18, 840),
    ('small', 'hardcover_jacket', 'premium_color', '70_white'): (12.03, 0.0604, 18, 840),
    ('large', 'hardcover', 'premium_color', '70_white'): (9.63, 0.1170, 18, 840),
    ('small', 'paperback', 'ultra_premium_color', '70_white'): (2.57, 0.0797, 18, 900),
    ('large', 'paperback', 'ultra_premium_color', '70_white'): (2.57, 0.1502, 18, 900),
    ('large', 'paperback_landscape', 'ultra_premium_color', '70_white'): (3.64, 0.1952, 18, 400),
    ('small', 'hardcover', 'ultra_premium_color', '70_white'): (9.63, 0.0804, 18, 840),
    ('small', 'hardcover_jacket', 'ultra_premium_color', '70_white'): (12.03, 0.0804, 18, 840),
    ('large', 'hardcover', 'ultra_premium_color', '70_white'): (9.63, 0.1559, 18, 840),
    ('large', 'hardcover_landscape', 'ultra_premium_color', '70_white'): (13.38, 0.1952, 18, 400),
}

INGRAM_PRINT_RATES_EUR: dict[tuple[str, str, str, str], tuple[float, float, int, int]] = {
    ('small', 'paperback', 'bw', 'groundwood'): (1.61, 0.0135, 18, 900),
    ('small', 'hardcover', 'bw', 'groundwood'): (5.97, 0.0135, 18, 840),
    ('small', 'hardcover_jacket', 'bw', 'groundwood'): (7.45, 0.0135, 18, 840),
    ('small', 'paperback', 'bw', '50_creme'): (1.61, 0.0136, 18, 1050),
    ('small', 'paperback', 'bw', '50_white'): (1.61, 0.0136, 18, 1200),
    ('large', 'paperback', 'bw', '50_white'): (1.61, 0.0231, 18, 1200),
    ('small', 'hardcover', 'bw', '50_creme'): (5.97, 0.0136, 18, 1050),
    ('small', 'hardcover', 'bw', '50_white'): (5.97, 0.0136, 18, 1200),
    ('small', 'hardcover_jacket', 'bw', '50_creme'): (7.45, 0.0136, 18, 1050),
    ('small', 'hardcover_jacket', 'bw', '50_white'): (7.45, 0.0136, 18, 1200),
    ('large', 'hardcover', 'bw', '50_white'): (6.14, 0.0238, 18, 1200),
    ('small', 'paperback', 'bw', '70_white'): (1.66, 0.0160, 18, 900),
    ('large', 'paperback', 'bw', '70_white'): (1.66, 0.0273, 18, 900),
    ('small', 'hardcover', 'bw', '70_white'): (6.14, 0.0160, 18, 840),
    ('small', 'hardcover_jacket', 'bw', '70_white'): (7.67, 0.0160, 18, 840),
    ('large', 'hardcover', 'bw', '70_white'): (6.14, 0.0272, 18, 840),
    ('small', 'paperback', 'std_color', '50_white'): (1.66, 0.0261, 18, 1200),
    ('large', 'paperback', 'std_color', '50_white'): (1.66, 0.0381, 18, 1200),
    ('small', 'hardcover', 'std_color', '50_white'): (6.14, 0.0261, 18, 1200),
    ('small', 'hardcover_jacket', 'std_color', '50_white'): (7.67, 0.0261, 18, 1200),
    ('large', 'hardcover', 'std_color', '50_white'): (6.14, 0.0381, 18, 1200),
    ('small', 'paperback', 'std_color', '70_white'): (1.66, 0.0281, 18, 900),
    ('large', 'paperback', 'std_color', '70_white'): (1.66, 0.0416, 18, 900),
    ('small', 'hardcover', 'std_color', '70_white'): (6.14, 0.0281, 18, 840),
    ('small', 'hardcover_jacket', 'std_color', '70_white'): (7.67, 0.0281, 18, 840),
    ('large', 'hardcover', 'std_color', '70_white'): (6.14, 0.0415, 18, 840),
    ('small', 'paperback', 'premium_color', '70_white'): (1.66, 0.0537, 18, 900),
    ('large', 'paperback', 'premium_color', '70_white'): (1.66, 0.0748, 18, 900),
    ('small', 'hardcover', 'premium_color', '70_white'): (6.14, 0.0523, 18, 840),
    ('small', 'hardcover_jacket', 'premium_color', '70_white'): (7.67, 0.0543, 18, 840),
    ('large', 'hardcover', 'premium_color', '70_white'): (6.14, 0.0760, 18, 840),
    ('small', 'paperback', 'ultra_premium_color', '70_white'): (1.66, 0.0716, 18, 900),
    ('large', 'paperback', 'ultra_premium_color', '70_white'): (1.66, 0.0998, 18, 900),
    ('large', 'paperback_landscape', 'ultra_premium_color', '70_white'): (2.37, 0.1231, 18, 400),
    ('small', 'hardcover', 'ultra_premium_color', '70_white'): (6.14, 0.0696, 18, 840),
    ('small', 'hardcover_jacket', 'ultra_premium_color', '70_white'): (7.67, 0.0724, 18, 840),
    ('large', 'hardcover', 'ultra_premium_color', '70_white'): (6.14, 0.1012, 18, 840),
    ('large', 'hardcover_landscape', 'ultra_premium_color', '70_white'): (5.79, 0.1231, 18, 400),
}

INGRAM_RATES_BY_CURRENCY: dict[str, dict[tuple[str, str, str, str], tuple[float, float, int, int]]] = {
    "USD": INGRAM_PRINT_RATES_USD,
    "GBP": INGRAM_PRINT_RATES_GBP,
    "AUD": INGRAM_PRINT_RATES_AUD,
    "EUR": INGRAM_PRINT_RATES_EUR,
}

@dataclass(frozen=True)
class IngramPrintRateSpec:
    """Print rate specification from official IngramSpark pricing schedule."""
    per_cover_cost: float
    per_page_cost: float
    size_category: str
    currency: str = "USD"
    min_pages: int = 18
    max_pages: int = 1200


def resolve_ingram_pricing_tuple(
    trim_width: float = 6.0,
    trim_height: float = 9.0,
    book_format: BookFormat | str = BookFormat.PAPERBACK,
    binding: BindingType | str | None = None,
    ink: InteriorInk | str = InteriorInk.BW,
    paper: PaperType | str = PaperType.WHITE,
    currency: str = "USD",
) -> tuple[float, float, int, int]:
    """Resolve authoritative IngramSpark (per_cover, per_page, min_pages, max_pages) tuple.

    Raises:
        UnsupportedCurrencyError: currency has no IngramSpark 2026 rate table (USD/GBP/AUD/EUR only).
        UnsupportedEconomicsConfigurationError: the price sheet publishes no row for this product
            in this currency (never substitutes another currency's figures — Astra N14).
    """
    curr = currency.upper() if currency else "USD"
    if curr not in INGRAM_RATES_BY_CURRENCY:
        raise UnsupportedCurrencyError(
            f"IngramSpark rates are published in {sorted(INGRAM_RATES_BY_CURRENCY)} only; got {currency!r}."
        )
    table = INGRAM_RATES_BY_CURRENCY[curr]

    size = "small" if trim_width < INGRAM_SMALL_TRIM_MAX_WIDTH else "large"
    is_landscape = trim_width > trim_height

    # Normalize binding
    b_str = str(binding.value if hasattr(binding, "value") else binding).lower() if binding is not None else ""
    f_str = str(book_format.value if hasattr(book_format, "value") else book_format).lower() if book_format is not None else ""

    if (
        binding in (BindingType.LINEN_WRAP_DUST_JACKET, BindingType.JACKETED_CASE_LAMINATE)
        or "jacket" in b_str
        or "linen" in b_str
    ):
        binding_key = "hardcover_jacket"
    elif (
        binding in (BindingType.CASEWRAP, BindingType.DIGITAL_CLOTH)
        or book_format == BookFormat.HARDCOVER
        or "hardcover" in f_str
        or "case" in b_str
        or "cloth" in b_str
    ):
        binding_key = "hardcover_landscape" if (is_landscape and "ultra" in str(ink).lower()) else "hardcover"
    else:
        binding_key = "paperback_landscape" if (is_landscape and "ultra" in str(ink).lower()) else "paperback"

    # Normalize ink
    i_str = str(ink.value if hasattr(ink, "value") else ink).lower()
    p_str = str(paper.value if hasattr(paper, "value") else paper).lower()

    if "ultra" in i_str or "ultra" in p_str or "coated" in p_str or "80" in p_str:
        ink_key = "ultra_premium_color"
    elif "premium" in i_str or "premium" in p_str:
        ink_key = "premium_color"
    elif "standard" in i_str or i_str in ("color", "colour"):
        ink_key = "std_color"
    else:
        ink_key = "bw"

    # Normalize paper
    if "groundwood" in p_str or "38" in p_str:
        paper_key = "groundwood"
    elif "cream" in p_str or "crème" in p_str or "creme" in p_str:
        paper_key = "50_creme"
    elif "70" in p_str or "104" in p_str:
        paper_key = "70_white"
    elif "coated" in p_str or "80" in p_str or "118" in p_str:
        paper_key = "70_white"
    elif "50" in p_str:
        paper_key = "50_white"
    else:
        if ink_key in ("ultra_premium_color", "premium_color"):
            paper_key = "70_white"
        else:
            paper_key = "50_white"

    key = (size, binding_key, ink_key, paper_key)
    if key in table:
        return table[key]

    # Premium color is only manufactured on 70# White / 80# Coated
    if ink_key in ("premium_color", "ultra_premium_color") and paper_key != "70_white":
        key = (size, binding_key, ink_key, "70_white")
        if key in table:
            return table[key]

    # Standard color is only manufactured on 50# White or 70# White
    if ink_key == "std_color" and paper_key not in ("50_white", "70_white"):
        key = (size, binding_key, ink_key, "50_white")
        if key in table:
            return table[key]

    if paper_key == "50_creme" and size == "large":
        key = (size, binding_key, ink_key, "50_white")
        if key in table:
            return table[key]

    if paper_key == "groundwood" and size == "large" and "hardcover" in binding_key:
        key = (size, binding_key, ink_key, "50_white")
        if key in table:
            return table[key]

    if "landscape" in binding_key:
        reg_b = binding_key.replace("_landscape", "")
        key = (size, reg_b, ink_key, paper_key)
        if key in table:
            return table[key]

    # Astra P1-1: a "large hardcover_jacket" branch used to return
    # ("small", "hardcover", ink, paper) — strings in place of prices — which raised
    # TypeError downstream. The 2026 price sheet publishes no Large dust-jacket rows.
    # Astra N14: the old code also fell back to the *USD* row for a missing GBP/AUD/EUR
    # row (labelled in the requested currency) and finally to a default product row.
    # Both are refused now.
    raise UnsupportedEconomicsConfigurationError(
        f"IngramSpark 2026 price sheet has no {curr} rate for "
        f"size={size}, binding={binding_key}, ink={ink_key}, paper={paper_key}."
    )


def get_ingram_print_rate_spec(
    config: BookConfiguration,
    currency: str = "USD",
) -> IngramPrintRateSpec:
    """Retrieve full official IngramSpark print rate specification for a book configuration."""
    trim_w = config.trim_width
    trim_h = config.trim_height
    size_cat = "Small" if trim_w < INGRAM_SMALL_TRIM_MAX_WIDTH else "Large"

    per_cover, per_page, min_p, max_p = resolve_ingram_pricing_tuple(
        trim_width=trim_w,
        trim_height=trim_h,
        book_format=config.book_format,
        binding=config.binding,
        ink=config.interior_ink,
        paper=config.paper_type,
        currency=currency,
    )

    b_str = str(config.binding.value if hasattr(config.binding, "value") else config.binding).lower() if config.binding is not None else ""
    f_str = str(config.book_format.value if hasattr(config.book_format, "value") else config.book_format).lower() if config.book_format is not None else ""
    is_hardcover = (
        config.binding in (BindingType.CASEWRAP, BindingType.DIGITAL_CLOTH, BindingType.LINEN_WRAP_DUST_JACKET, BindingType.JACKETED_CASE_LAMINATE)
        or config.book_format == BookFormat.HARDCOVER
        or "hardcover" in f_str
        or "case" in b_str
        or "cloth" in b_str
        or "jacket" in b_str
        or "linen" in b_str
    )

    duplex = getattr(config, "duplex_cover", False)
    if duplex and not is_hardcover:
        per_cover += INGRAM_DUPLEX_COVER_RATES.get(currency.upper(), INGRAM_DUPLEX_COVER_ADDON)

    perforated = getattr(config, "perforated_pages", False)
    if perforated and currency.upper() == "USD":
        per_page += INGRAM_PERFORATION_ADDON_PER_PAGE

    return IngramPrintRateSpec(
        per_cover_cost=round(per_cover, 2),
        per_page_cost=round(per_page, 4),
        size_category=size_cat,
        currency=currency.upper(),
        min_pages=min_p,
        max_pages=max_p,
    )


def get_ingram_binding_cost(
    binding: BindingType | str | None = None,
    book_format: BookFormat | str | None = None,
    duplex_cover: bool = False,
    trim_width: float | None = None,
    trim_height: float | None = None,
    trim_size: TrimSize | None = None,
    ink: InteriorInk | str | None = None,
    paper: PaperType | str | None = None,
    currency: str = "USD",
) -> float:
    """Resolve authoritative IngramSpark fixed binding / unit cover cost."""
    w = trim_size.width if trim_size is not None else (trim_width or 6.0)
    h = trim_size.height if trim_size is not None else (trim_height or 9.0)

    per_cover, _, _, _ = resolve_ingram_pricing_tuple(
        trim_width=w,
        trim_height=h,
        book_format=book_format or BookFormat.PAPERBACK,
        binding=binding,
        ink=ink or InteriorInk.BW,
        paper=paper or PaperType.WHITE,
        currency=currency,
    )

    b_str = str(binding.value if hasattr(binding, "value") else binding).lower() if binding is not None else ""
    f_str = str(book_format.value if hasattr(book_format, "value") else book_format).lower() if book_format is not None else ""
    is_hardcover = (
        binding in (BindingType.CASEWRAP, BindingType.DIGITAL_CLOTH, BindingType.LINEN_WRAP_DUST_JACKET, BindingType.JACKETED_CASE_LAMINATE)
        or book_format == BookFormat.HARDCOVER
        or "hardcover" in f_str
        or "case" in b_str
        or "cloth" in b_str
        or "jacket" in b_str
        or "linen" in b_str
    )

    if duplex_cover and not is_hardcover:
        per_cover += INGRAM_DUPLEX_COVER_RATES.get(currency.upper(), INGRAM_DUPLEX_COVER_ADDON)

    return round(per_cover, 2)


def get_ingram_per_page_rate(
    ink: InteriorInk | str = InteriorInk.BW,
    paper: PaperType | str = PaperType.WHITE,
    trim_width: float | None = None,
    trim_height: float | None = None,
    trim_size: TrimSize | None = None,
    book_format: BookFormat | str | None = None,
    binding: BindingType | str | None = None,
    currency: str = "USD",
) -> float:
    """Resolve authoritative IngramSpark per-page rate based on trim size, ink, paper, and binding."""
    w = trim_size.width if trim_size is not None else (trim_width or 6.0)
    h = trim_size.height if trim_size is not None else (trim_height or 9.0)

    _, per_page, _, _ = resolve_ingram_pricing_tuple(
        trim_width=w,
        trim_height=h,
        book_format=book_format or BookFormat.PAPERBACK,
        binding=binding,
        ink=ink,
        paper=paper,
        currency=currency,
    )

    return round(per_page, 4)


def get_ingram_wholesale_discount(
    distribution_goal: DistributionGoal | str | None = None,
) -> float:
    """Resolve IngramSpark wholesale discount (0.40 for direct, 0.55 for standard retail)."""
    if distribution_goal is None:
        return INGRAM_WHOLESALE_DISCOUNT_STANDARD

    goal_str = (
        str(
            distribution_goal.value
            if hasattr(distribution_goal, "value")
            else distribution_goal
        ).lower()
    )
    if "direct" in goal_str:
        raise ValueError(
            "DistributionGoal.DIRECT represents author copy direct orders and does not have a wholesale discount."
        )
    return INGRAM_WHOLESALE_DISCOUNT_STANDARD


# =============================================================================
# Lulu Tables & Constants (Authoritative: lulu_guide.md)
# =============================================================================

LULU_BLEED_IN: float = 0.125
LULU_BLEED_MM: float = 3.175
LULU_SAFETY_MARGIN_IN: float = 0.500
LULU_SAFETY_MARGIN_MM: float = 12.7

LULU_PAPERBACK_SPINE_DIVISOR_IN: float = 444.0
LULU_PAPERBACK_SPINE_BASE_IN: float = 0.060
LULU_PAPERBACK_SPINE_DIVISOR_MM: float = 17.48
LULU_PAPERBACK_SPINE_BASE_MM: float = 1.524

LULU_PAPERBACK_SPINE_DIVISOR_460PPI_IN: float = 460.0

LULU_SPINE_TEXT_MIN_PAGES: int = 80  # Spine text disallowed if <= 80 pages; allowed if > 80
LULU_SPINE_SAFE_MARGIN: float = 0.125  # Minimum 0.125" (3.175 mm) clearance to each spine edge

LULU_PAPERBACK_MIN_PAGES: int = 32
LULU_HARDCOVER_MIN_PAGES: int = 24

# Absolute page-count maxima, matching the Lulu BLOCK rules in
# validators/trim_and_page_validator.py (LULU-PAGE-001..004).
LULU_PAPERBACK_MAX_PAGES: int = 800  # Perfect bound
LULU_COIL_MAX_PAGES: int = 470
LULU_SADDLE_STITCH_MAX_PAGES: int = 48
LULU_HARDCOVER_MAX_PAGES: int = 800

LULU_COVER_BLEED: float = 0.125
LULU_CASEWRAP_WRAP: float = 0.750
LULU_CASEWRAP_HINGE: float = 0.125
LULU_CASEWRAP_TOTAL_MARGIN: float = 1.750  # 2 * (0.750 wrap + 0.125 overhang)
LULU_INTERIOR_BLEED_SIDE: float = 0.125
LULU_RECOMMENDED_MARGIN: float = 0.500
LULU_COIL_PUNCH_MARGIN: float = 0.375

# Lulu Engineering Constants (Section 22)
LULU_IMAGE_PPI_MIN: int = 300
LULU_IMAGE_PPI_MAX: int = 600
LULU_IMAGE_PPI_SIMPLE_PRINT_MIN: int = 150
LULU_GRAYSCALE_GAMMA_MIN: float = 2.2
LULU_GRAYSCALE_GAMMA_MAX: float = 2.4
LULU_MAX_TAC_PERCENT: int = 270
LULU_LIGHT_TINT_THRESHOLD_PERCENT: int = 20
LULU_RGB_PROFILE: str = "sRGB IEC61966-2.1"
LULU_CMYK_PROFILE: str = "Coated GRACoL 2006"
LULU_GUTTER_FILE_SPEC_MIN_IN: float = 0.2

# Standard Lulu Trim Sizes (Section 9: Book trim sizes and interior file dimensions)
LULU_STANDARD_TRIM_SIZES: dict[str, tuple[float, float]] = {
    "Pocketbook": (4.25, 6.875),
    "Novella": (5.0, 8.0),
    "Digest": (5.5, 8.5),
    "A5": (5.83, 8.27),
    "Royal": (6.14, 9.21),
    "US Trade": (6.0, 9.0),
    "Comic Book": (6.63, 10.25),
    "Executive": (7.0, 10.0),
    "Crown Quarto": (7.44, 9.68),
    "Small Square": (7.5, 7.5),
    "A4": (8.27, 11.69),
    "Square": (8.5, 8.5),
    "US Letter": (8.5, 11.0),
    "Small Landscape": (9.0, 7.0),
    "US Letter Landscape": (11.0, 8.5),
    "A4 Landscape": (11.69, 8.27),
    "Calendar": (11.0, 8.5),
}

LULU_PAPER_CALIPERS: dict[str, float] = {
    "White": 0.002252,              # 60# uncoated (1/444)
    "Cream": 0.002252,              # 60# cream (Section 10A: same standard 444 calculation)
    "Creme": 0.002252,
    "Crème": 0.002252,
    "Groundwood": 0.002350,
    "80# Coated White": 0.002750,
    "Coated White": 0.002750,       # Enum value mapping
    "White 50lb/74gsm": 0.002252,
    "Crème 50lb/74gsm": 0.002252,
    "Creme 50lb/74gsm": 0.002252,
    "White 70lb/104gsm": 0.002750,
    "Groundwood 38lb/56gsm": 0.002350,
}

# Lulu Gutter Bands: (min_pages, max_pages, additional_gutter, recommended_inside, full_bleed_inside)
LULU_GUTTER_BANDS: list[tuple[int, int, float, float, float]] = [
    (1, 60, 0.0, 0.500, 0.625),
    (61, 150, 0.125, 0.625, 0.750),
    (151, 400, 0.500, 1.000, 1.125),
    (401, 600, 0.625, 1.125, 1.250),
    (601, 9999, 0.750, 1.250, 1.375),
]

# Lulu Hardcover Spine Table from Section 11.4: (min_pages, max_pages, spine_width_in)
LULU_HARDCOVER_SPINE_TABLE: list[tuple[int, int, float]] = [
    (24, 84, 0.250),
    (85, 140, 0.500),
    (141, 168, 0.625),
    (169, 194, 0.688),
    (195, 222, 0.750),
    (223, 250, 0.813),
    (251, 278, 0.875),
    (279, 306, 0.938),
    (307, 334, 1.000),
    (335, 360, 1.063),
    (361, 388, 1.125),
    (389, 416, 1.188),
    (417, 444, 1.250),
    (445, 472, 1.313),
    (473, 500, 1.375),
    (501, 528, 1.438),
    (529, 556, 1.500),
    (557, 582, 1.563),
    (583, 610, 1.625),
    (611, 638, 1.688),
    (639, 666, 1.750),
    (667, 694, 1.813),
    (695, 722, 1.875),
    (723, 750, 1.938),
    (751, 778, 2.000),
    (779, 799, 2.063),
    (800, 800, 2.125),
]


class LuluGutterSpec(NamedTuple):
    additional_gutter: float
    recommended_inside_margin: float
    full_bleed_inside_margin: float


def get_lulu_paper_caliper(paper: str) -> float:
    """Safely resolve Lulu paper caliper across paper variants."""
    if paper in LULU_PAPER_CALIPERS:
        return LULU_PAPER_CALIPERS[paper]

    p_lower = paper.lower()
    if "coated" in p_lower or "80" in p_lower:
        return LULU_PAPER_CALIPERS["80# Coated White"]
    elif "cream" in p_lower or "crème" in p_lower or "creme" in p_lower:
        return LULU_PAPER_CALIPERS["Cream"]
    elif "groundwood" in p_lower:
        return LULU_PAPER_CALIPERS["Groundwood"]
    else:
        return LULU_PAPER_CALIPERS["White"]


def get_lulu_hardcover_spine(page_count: int) -> float | None:
    """Look up authoritative hardcover spine width for Lulu from Section 11.4 table."""
    if page_count < 24:
        return None
    for min_p, max_p, width in LULU_HARDCOVER_SPINE_TABLE:
        if min_p <= page_count <= max_p:
            return width
    return 2.125


def get_lulu_gutter_spec(page_count: int) -> LuluGutterSpec:
    """Resolve Lulu gutter addition and recommended inside margins based on page count."""
    for min_p, max_p, gutter, rec_in, fb_in in LULU_GUTTER_BANDS:
        if min_p <= page_count <= max_p:
            return LuluGutterSpec(
                additional_gutter=gutter,
                recommended_inside_margin=rec_in,
                full_bleed_inside_margin=fb_in,
            )
    return LuluGutterSpec(
        additional_gutter=0.750,
        recommended_inside_margin=1.250,
        full_bleed_inside_margin=1.375,
    )


# =============================================================================
# Universal / Generic Fallback Constants
# =============================================================================

UNIVERSAL_PAPER_CALIPER: float = 0.002252
UNIVERSAL_COVER_BLEED: float = 0.125
UNIVERSAL_INTERIOR_BLEED: float = 0.125
UNIVERSAL_SPINE_TEXT_MIN_PAGES: int = 80
UNIVERSAL_SPINE_SAFE_MARGIN: float = 0.0625
