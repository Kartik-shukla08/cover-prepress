"""Domain models for 6-class publishing rule taxonomy and 4-tier authority hierarchy."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from mbooks.domain.enums import (
    AuthorityTier,
    Publisher,
    RuleSeverity,
    RuleTaxonomyClass,
    RuleVerificationStatus,
)


class AuthorityCitation(BaseModel):
    """Verifiable source citation from official publisher documentation, calculators, or standards."""
    source_id: str = Field(..., description="Unique source identifier e.g. SRC-KDP-DOC-01")
    tier: AuthorityTier = Field(..., description="Tier in the 4-level authority hierarchy")
    publisher: Publisher | str = Field(..., description="Target publisher or standard organization (e.g. KDP, ISO)")
    source_name: str = Field(..., description="Human-readable title of documentation or tool")
    url: str | None = Field(default=None, description="Official online URL or calculator endpoint")
    retrieval_timestamp: str = Field(..., description="ISO 8601 timestamp/date of data retrieval or verification")
    excerpt: str | None = Field(default=None, description="Direct quote or reference passage from source")
    verified_values: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured dictionary of authoritative reference values captured from this source"
    )

    model_config = {"frozen": True}


class TaxonomyRule(BaseModel):
    """A publishing rule formalized under the 6-class taxonomy and 4-tier authority hierarchy.

    Classes:
        CALCULATION: Deterministic mathematical formulas.
        CONSTRAINT: Hard physical and catalog boundaries.
        REQUIREMENT: Mandatory file and physical requirements.
        RECOMMENDATION: Advisory print best practices.
        TOLERANCE: Manufacturing & bindery shift allowances.
        DEPENDENCY: Change propagation relationships.
    """
    rule_id: str = Field(..., description="Unique rule identifier e.g. KDP-PB-SPINE-001")
    publisher: Publisher | str = Field(..., description="KDP, IngramSpark, Lulu, or Universal")
    taxonomy_class: RuleTaxonomyClass = Field(..., description="One of the 6 formal taxonomy classes")
    severity: RuleSeverity = Field(default=RuleSeverity.BLOCK, description="BLOCK, WARNING, INFO, CALC, ECON")
    
    # Partial applicability filter: only specified dimensions are evaluated
    applies_when: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of partial condition criteria (e.g. {'publisher': 'KDP', 'binding': 'Paperback'})"
    )

    # Core logic / specification definition
    formula: str | None = Field(default=None, description="Mathematical formula for CALCULATION rules")
    require: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of constraint assertions that must evaluate to true"
    )
    tolerance_value: float | None = Field(
        default=None,
        description="Numeric allowance/tolerance margin (inches) for TOLERANCE rules"
    )
    cascades_to: list[str] = Field(
        default_factory=list,
        description="List of downstream attributes triggered by DEPENDENCY rules"
    )

    # Human-readable & provenance metadata
    description: str = Field(..., description="Clear explanation of the rule")
    scope: str = Field(default="All", description="Paperback, Hardcover, Interior, Cover, etc.")
    verification_status: RuleVerificationStatus = Field(
        default=RuleVerificationStatus.UNVERIFIED,
        description="Verification state of this rule against authoritative sources"
    )
    citations: list[AuthorityCitation] = Field(
        default_factory=list,
        description="Authority citations backing this rule across the 4 tiers"
    )
    notes: str | None = Field(default=None, description="Technical and implementation notes")

    model_config = {"frozen": True}


class TaxonomyVerificationSummary(BaseModel):
    """Progress metrics and verification breakdown by publisher and taxonomy class."""
    publisher: str
    total_rules: int
    by_class: dict[str, int]
    by_status: dict[str, int]
    verified_count: int
    unverified_count: int
    conflict_count: int
    coverage_percentage: float
