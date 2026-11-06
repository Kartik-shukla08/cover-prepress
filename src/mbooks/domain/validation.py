"""Validation result models for configuration and file compliance."""

from __future__ import annotations
from datetime import datetime, UTC
from typing import Any, Optional
from pydantic import BaseModel, Field
from .enums import RuleSeverity, ValidationStatus, AssetType
from .analysis import AssetInspectionReport


class ValidationIssue(BaseModel):
    """A single validation finding."""
    rule_id: str = Field(..., description="The rule that triggered this issue")
    severity: RuleSeverity
    message: str
    details: str | None = None
    field: str | None = Field(default=None, description="Which input field or property triggered the issue")


class ValidationResult(BaseModel):
    """Complete validation result for a book configuration or generic entity."""
    status: ValidationStatus
    issues: list[ValidationIssue] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ruleset_version: str | None = Field(default=None, description="Version identifier for the rules used")

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == RuleSeverity.BLOCK]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == RuleSeverity.WARNING]

    @property
    def info(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == RuleSeverity.INFO]


class AssetValidationResult(ValidationResult):
    """Complete validation result for a physical book asset (cover or interior PDF)."""
    asset_type: AssetType = Field(..., description="Interior or cover asset")
    file_path: str | None = Field(default=None, description="Path of validated file")
    expected_spec: dict[str, Any] = Field(default_factory=dict, description="Expected dimensions, margins, bleed, page count")
    actual_properties: dict[str, Any] = Field(default_factory=dict, description="Measured properties from file inspection")
    passed_checks: list[str] = Field(default_factory=list, description="Descriptions of checks that passed successfully")
    inspection_report: AssetInspectionReport | None = Field(default=None, description="Full technical inspection report")
