"""Domain models for publishing rules loaded from the master rules dataset."""

from pydantic import BaseModel, Field


class CanonicalInput(BaseModel):
    """Describes a single input parameter for the publishing engine."""
    input_id: str = Field(..., description="e.g. IN001")
    group: str = Field(..., description="e.g. Product, Geometry, Interior")
    name: str = Field(..., description="e.g. Publisher, Trim width")
    input_type: str = Field(..., description="e.g. enum, number, boolean")
    allowed_values: str | None = Field(default=None, description="Allowed / Example values")
    dependency_driver: bool = Field(default=False)
    used_by: str | None = Field(default=None)
    notes: str | None = Field(default=None)

    model_config = {"frozen": True}


class CompatibilityRule(BaseModel):
    """An IF/THEN compatibility rule from a publisher."""
    rule_id: str = Field(..., description="e.g. KDP-CFG-001")
    publisher: str = Field(..., description="KDP, IngramSpark, or Lulu")
    rule_type: str = Field(..., description="CONFIG, GEOMETRY, FILE, ECONOMICS, DISTRIBUTION")
    priority: int = Field(default=1)
    condition: str = Field(..., description="IF / WHEN clause")
    result: str = Field(..., description="THEN / RESULT clause")
    severity: str = Field(..., description="BLOCK, WARNING, INFO, CALC, ECON")
    scope: str = Field(default="All", description="e.g. Paperback, Hardcover, Interior, Cover")
    status: str = Field(default="Verified")
    source_url: str | None = Field(default=None)
    implementation_note: str | None = Field(default=None)

    model_config = {"frozen": True}


class GeometryRule(BaseModel):
    """A geometry/calculation formula from a publisher."""
    rule_id: str = Field(..., description="e.g. GEO-KDP-001")
    publisher: str
    geometry: str = Field(..., description="What this calculates, e.g. 'Interior bleed size'")
    inputs: str = Field(..., description="Required inputs")
    formula: str = Field(..., description="Formula / Logic")
    output: str = Field(..., description="What this produces")
    units: str = Field(default="in")
    example: str | None = Field(default=None)
    status: str = Field(default="Verified")
    source_url: str | None = Field(default=None)

    model_config = {"frozen": True}


class TrimMatrixEntry(BaseModel):
    """A row from the KDP Trim Matrix defining page count limits per trim/paper combo."""
    book_format: str = Field(..., description="Paperback or Hardcover")
    trim_size: str = Field(..., description="e.g. '6 x 9'")
    bw_white_min: int | None = None
    bw_white_max: int | None = None
    bw_cream_min: int | None = None
    bw_cream_max: int | None = None
    groundwood_min: int | None = None
    groundwood_max: int | None = None
    std_color: str | None = Field(default=None, description="Range string like '72-600' or 'Not available'")
    premium_color: str | None = Field(default=None, description="Range string like '24-828' or 'Not available'")

    model_config = {"frozen": True}


class OptionMatrixEntry(BaseModel):
    """An option availability entry from the Option Matrix."""
    publisher: str
    dimension: str = Field(..., description="Dimension / Area, e.g. 'Interior ink', 'Paper'")
    option: str = Field(..., description="The specific option, e.g. 'B&W', 'Cream'")
    allowed: str = Field(..., description="Yes, No, or Conditional")
    conditions: str | None = Field(default=None)
    source_url: str | None = Field(default=None)

    model_config = {"frozen": True}


class CalculatorOutput(BaseModel):
    """Describes a calculated output the engine must produce."""
    output_id: str
    name: str
    output_type: str
    depends_on: str | None = None
    publisher_specific: bool = False
    example_logic: str | None = None
    downstream_use: str | None = None
    status: str = "Core"

    model_config = {"frozen": True}


class SourceReference(BaseModel):
    """Official documentation source for a publisher's rules."""
    source_id: str
    publisher: str
    topic: str
    url: str

    model_config = {"frozen": True}
