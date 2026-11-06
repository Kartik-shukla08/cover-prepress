"""Canonical set of enumerations for the publishing engine."""

from enum import Enum

class Publisher(str, Enum):
    KDP = "KDP"
    INGRAMSPARK = "IngramSpark"
    LULU = "Lulu"

class BookFormat(str, Enum):
    PAPERBACK = "Paperback"
    HARDCOVER = "Hardcover"

class BindingType(str, Enum):
    PERFECT_BOUND = "Perfect Bound"
    CASEWRAP = "Casewrap"
    LINEN_WRAP_DUST_JACKET = "Linen Wrap + Dust Jacket"
    COIL = "Coil Bound"
    SADDLE_STITCH = "Saddle Stitch"
    JACKETED_CASE_LAMINATE = "Jacketed Case Laminate"
    DIGITAL_CLOTH = "Digital Cloth"

class InteriorInk(str, Enum):
    BW = "B&W"
    COLOR = "Color"
    STANDARD_COLOR = "Standard Color"
    PREMIUM_COLOR = "Premium Color"
    ULTRA_PREMIUM_COLOR = "Ultra-Premium Color"

class PaperType(str, Enum):
    WHITE = "White"
    CREAM = "Cream"  
    GROUNDWOOD = "Groundwood"
    WHITE_50LB = "White 50lb/74gsm"
    WHITE_70LB = "White 70lb/104gsm"
    CREME_50LB = "Crème 50lb/74gsm"
    GROUNDWOOD_38LB = "Groundwood 38lb/56gsm"
    COATED_WHITE = "Coated White"
    COLOR_50 = "Color 50"
    COLOR_70 = "Color 70"
    PREMIUM_COLOR = "Premium Color"
    ULTRA_PREMIUM_COLOR = "Ultra Premium Color"
    WHITE_50 = "White 50"
    WHITE_70 = "White 70"
    CREME = "Creme"

class CoverFinish(str, Enum):
    MATTE = "Matte"
    GLOSSY = "Glossy"
    GLOSS = "Gloss"
    TEXTURED = "Textured"

class DistributionGoal(str, Enum):
    DIRECT = "Direct"
    GLOBAL_RETAIL = "Global/Retail Distribution"

class AssetType(str, Enum):
    INTERIOR = "interior"
    COVER = "cover"

class AssetState(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    OUTDATED = "OUTDATED"
    NOT_GENERATED = "NOT_GENERATED"

class RuleType(str, Enum):
    CONFIG = "CONFIG"
    GEOMETRY = "GEOMETRY"
    FILE = "FILE"
    ECONOMICS = "ECONOMICS"
    DISTRIBUTION = "DISTRIBUTION"

class RuleSeverity(str, Enum):
    BLOCK = "BLOCK"
    WARNING = "WARNING"
    INFO = "INFO"
    CALC = "CALC"
    ECON = "ECON"

class ValidationStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    FAILED = "FAILED"

class RuleTaxonomyClass(str, Enum):
    CALCULATION = "CALCULATION"
    CONSTRAINT = "CONSTRAINT"
    REQUIREMENT = "REQUIREMENT"
    RECOMMENDATION = "RECOMMENDATION"
    TOLERANCE = "TOLERANCE"
    DEPENDENCY = "DEPENDENCY"

class AuthorityTier(str, Enum):
    TIER_1_DOCS = "TIER_1_DOCS"
    TIER_2_CALCULATOR = "TIER_2_CALCULATOR"
    TIER_3_EMPIRICAL = "TIER_3_EMPIRICAL"
    TIER_4_INDUSTRY_STANDARD = "TIER_4_INDUSTRY_STANDARD"

class RuleVerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    CALCULATOR_VERIFIED = "CALCULATOR_VERIFIED"
    EMPIRICALLY_VERIFIED = "EMPIRICALLY_VERIFIED"
    CONFLICT = "CONFLICT"
    DEPRECATED = "DEPRECATED"

class AuditPropertyStatus(str, Enum):
    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"
    CONFLICT = "CONFLICT"
    UNVERIFIED = "UNVERIFIED"
