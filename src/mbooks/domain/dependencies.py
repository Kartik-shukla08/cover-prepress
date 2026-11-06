"""Domain models for the Dependency Engine and Change Propagation system."""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from .book import Asset, BookConfiguration
from .enums import AssetType, AssetState
from .geometry import CalculatedSpecification, CoverDimensions, InteriorDimensions
from .validation import ValidationResult


class WorkerType(str, Enum):
    """Downstream Markee workers that consume publishing specifications."""
    COVER_WORKER = "cover_worker"
    FORMATTER = "formatter"
    PUBLISHER = "publisher"


class RegenerationPriority(str, Enum):
    """Urgency / priority of the asset regeneration task."""
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class ConfigDiff(BaseModel):
    """Represents a single configuration field change between old and new configurations."""
    field: str = Field(..., description="Configuration attribute name that changed")
    old_value: Any = Field(default=None, description="Previous value")
    new_value: Any = Field(default=None, description="Updated value")
    impact_summary: str = Field(..., description="Human-readable description of the impact of this change")

    model_config = {"frozen": True}


class SpecificationDiff(BaseModel):
    """Represents a delta in calculated physical or economic specifications."""
    component: str = Field(..., description="Component changed: spine, cover, interior, economics")
    property_name: str = Field(..., description="Specific metric name, e.g. width, full_width, min_inside_margin")
    old_value: Any = Field(default=None, description="Previous calculated value")
    new_value: Any = Field(default=None, description="New calculated value")
    delta: float | None = Field(default=None, description="Numerical delta (new - old) if applicable")
    unit: str = Field(default="in", description="Unit of measurement or currency")
    notes: str | None = Field(default=None, description="Context or explanation of the change")

    model_config = {"frozen": True}


class RegenerationRequirement(BaseModel):
    """Actionable specification payload prepared for a specific downstream worker."""
    worker: WorkerType = Field(..., description="Target worker responsible for producing the asset")
    asset_type: AssetType = Field(..., description="Asset type being generated: cover or interior")
    priority: RegenerationPriority = Field(default=RegenerationPriority.HIGH, description="Regeneration priority")
    reason: str = Field(..., description="Explanation of why regeneration is required")
    triggers: list[str] = Field(default_factory=list, description="List of configuration fields that triggered this requirement")
    target_specs: dict[str, Any] = Field(default_factory=dict, description="Dictionary of raw calculated parameters for worker")
    cover_spec: CoverDimensions | None = Field(default=None, description="Full calculated cover layout if worker is cover_worker")
    interior_spec: InteriorDimensions | None = Field(default=None, description="Full calculated interior dimensions if worker is formatter")
    calculated_spec: CalculatedSpecification | None = Field(default=None, description="Complete calculated specification")

    model_config = {"frozen": True}

    @property
    def target(self) -> str:
        """Convenience property mapping to asset_type value ('cover', 'interior')."""
        return self.asset_type.value


class ChangeImpactReport(BaseModel):
    """Comprehensive analysis report detailing the consequences of a configuration change."""
    has_changes: bool = Field(..., description="True if any configuration differences were detected")
    config_diffs: list[ConfigDiff] = Field(default_factory=list, description="Detected configuration field changes")
    is_valid_new_config: bool = Field(..., description="Whether the new configuration is valid under publisher rules")
    validation_result: ValidationResult | None = Field(default=None, description="Validation result for the new configuration")
    old_spec: CalculatedSpecification | None = Field(default=None, description="Specifications calculated before change")
    new_spec: CalculatedSpecification | None = Field(default=None, description="Specifications calculated after change")
    spec_diffs: list[SpecificationDiff] = Field(default_factory=list, description="Differences in physical specifications")
    affected_asset_types: list[AssetType] = Field(default_factory=list, description="Asset types affected by this change")
    affected_workers: list[WorkerType] = Field(default_factory=list, description="Workers that need to be notified or re-run")
    updated_assets: list[Asset] = Field(default_factory=list, description="Assets with updated states (e.g. OUTDATED)")
    regeneration_requirements: list[RegenerationRequirement] = Field(default_factory=list, description="Actionable worker payloads")
