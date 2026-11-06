"""Domain models for structured (machine-parseable) publishing rules."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RuleCondition(BaseModel):
    """A single condition or constraint in a structured rule.

    Used in both 'when' (trigger conditions) and 'require' (constraints
    that must be satisfied when the rule fires).

    Operators:
        eq       - field == value
        neq      - field != value
        gt       - field > value
        gte      - field >= value
        lt       - field < value
        lte      - field <= value
        between  - value[0] <= field <= value[1]
        in       - field in value (list)
        not_in   - field not in value (list)
        divisible - field % value == 0
        always   - unconditionally true (no field needed)
    """
    field: str | None = Field(default=None, description="BookConfiguration field name")
    op: str = Field(..., description="Comparison operator")
    value: object = Field(default=None, description="Value to compare against")

    model_config = {"frozen": True}


class StructuredRule(BaseModel):
    """A machine-parseable publishing rule using when/require semantics.

    Evaluation logic:
    1. If ALL 'when' conditions match the book configuration, the rule fires.
    2. If the rule fires:
       - 'require' is non-empty: each constraint is checked.
         Any failing constraint produces a ValidationIssue.
       - 'require' is empty: unconditionally emits an issue
         (forbidden combination for BLOCK, informational for INFO).
    3. GEOMETRY/ECONOMICS rules use 'apply' instead of 'require'
       for calculation data (evaluated in later phases).
    """
    rule_id: str = Field(..., description="Unique rule identifier, e.g. KDP-CFG-001")
    publisher: str = Field(..., description="KDP, IngramSpark, or Lulu")
    type: str = Field(..., description="CONFIG, GEOMETRY, FILE, ECONOMICS, or DISTRIBUTION")
    when: list[RuleCondition] = Field(..., description="Trigger conditions (all must match)")
    require: list[RuleCondition] = Field(default_factory=list, description="Constraints that must be satisfied")
    severity: str = Field(..., description="BLOCK, WARNING, INFO, CALC, or ECON")
    scope: str = Field(default="All", description="e.g. Paperback, Hardcover, Interior, Cover")
    message: str = Field(..., description="Human-readable description of the rule")
    status: str = Field(default="Verified")
    source_url: str | None = Field(default=None)
    note: str | None = Field(default=None, description="Implementation notes")
    evaluable: bool = Field(default=True, description="Whether the generic engine can evaluate this rule")
    apply: dict | None = Field(default=None, description="Calculation data for GEOMETRY/ECONOMICS rules")

    model_config = {"frozen": True}
