"""Domain models for multi-publisher package dispatch and bundle generation.

Phase 8.4: Multi-Publisher Package Dispatcher & Bundle Generator.

Architecture Principle:
    One common book configuration → N publisher-specific interpretations
    → N publisher-specific output packages.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from pydantic import BaseModel, Field

from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import Publisher, RuleSeverity, ValidationStatus
from mbooks.domain.geometry import CalculatedSpecification
from mbooks.domain.validation import ValidationIssue
from mbooks.domain.worker_spec import WorkerSpecificationPayload


class PublisherFeasibility(BaseModel):
    """Per-publisher feasibility result for a given BookConfiguration.

    Determines whether a specific publisher can accept the book's trim size,
    page count, binding type, color mode, and other physical constraints.
    """
    publisher: Publisher = Field(..., description="Target publisher evaluated")
    is_supported: bool = Field(..., description="Whether the publisher can accept this configuration")
    issues: list[ValidationIssue] = Field(
        default_factory=list,
        description="Blocking issues that prevent publishing (severity=BLOCK)",
    )
    warnings: list[ValidationIssue] = Field(
        default_factory=list,
        description="Non-blocking warnings and advisories",
    )


class PublisherPackage(BaseModel):
    """A complete publisher-specific output package with exact physical specs
    and worker payloads ready for dispatch.

    Each package contains the publisher's own spine width, cover spread geometry,
    interior margins, color profile, and barcode placement — with zero compromises
    or harmonization from other publishers.
    """
    publisher: Publisher = Field(..., description="Target publisher for this package")
    calculated_spec: CalculatedSpecification = Field(
        ..., description="Publisher-specific physical specifications"
    )
    cover_worker_payload: WorkerSpecificationPayload = Field(
        ..., description="Cover worker specification payload for this publisher"
    )
    interior_worker_payload: WorkerSpecificationPayload = Field(
        ..., description="Interior/formatter worker specification payload for this publisher"
    )


class MultiPublisherFeasibilityReport(BaseModel):
    """Feasibility matrix — which publishers can accept this book configuration.

    Provides a per-publisher breakdown of compatibility, surfacing blocking issues
    and non-blocking warnings for each target platform.
    """
    configuration_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Human-readable summary of the evaluated book configuration",
    )
    publisher_results: list[PublisherFeasibility] = Field(
        default_factory=list,
        description="Per-publisher feasibility evaluations",
    )
    supported_publishers: list[Publisher] = Field(
        default_factory=list,
        description="Publishers that can accept this configuration (convenience list)",
    )
    unsupported_publishers: list[Publisher] = Field(
        default_factory=list,
        description="Publishers that cannot accept this configuration (convenience list)",
    )


class MultiPublisherPackageBundle(BaseModel):
    """The complete dispatch bundle: N publisher-specific packages ready for workers.

    Contains the feasibility report plus all generated packages for supported publishers.
    Each package includes publisher-specific cover and interior worker payloads.
    """
    book_id: str = Field(..., description="Common book identifier across all packages")
    configuration_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Human-readable summary of the source book configuration",
    )
    target_publishers: list[Publisher] = Field(
        ..., description="All requested target publishers"
    )
    feasibility_report: MultiPublisherFeasibilityReport = Field(
        ..., description="Full feasibility matrix for all requested publishers"
    )
    packages: list[PublisherPackage] = Field(
        default_factory=list,
        description="Publisher-specific packages (only for supported publishers)",
    )
    total_packages: int = Field(
        default=0, description="Number of generated packages"
    )
    total_worker_payloads: int = Field(
        default=0,
        description="Total worker payloads (cover + interior per package)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Bundle generation timestamp",
    )


class PublisherSpecComparison(BaseModel):
    """Side-by-side specification comparison for a single publisher."""
    publisher: str = Field(..., description="Publisher name")
    is_supported: bool = Field(..., description="Whether this publisher supports the configuration")
    spine_width: float | None = Field(default=None, description="Calculated spine width (inches)")
    min_inside_gutter: float | None = Field(default=None, description="Minimum inside/gutter margin (inches)")
    cover_spread_width: float | None = Field(default=None, description="Full cover spread width (inches)")
    cover_spread_height: float | None = Field(default=None, description="Full cover spread height (inches)")
    color_profile: str | None = Field(default=None, description="Recommended color profile (sRGB, DeviceCMYK)")
    page_count_valid: bool = Field(default=True, description="Whether page count is within publisher limits")
    notes: list[str] = Field(default_factory=list, description="Additional publisher-specific notes")


class MultiPublisherComparisonReport(BaseModel):
    """Side-by-side comparison of physical specifications across multiple publishers."""
    configuration_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Human-readable summary of the book configuration",
    )
    comparisons: list[PublisherSpecComparison] = Field(
        default_factory=list,
        description="Per-publisher specification comparisons",
    )
