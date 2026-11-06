"""Domain model for 9-dimensional contextual resolution tuple."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import (
    BindingType,
    BookFormat,
    InteriorInk,
    PaperType,
    Publisher,
)
from mbooks.domain.geometry import TrimSize


class ContextualResolutionTuple(BaseModel):
    """Canonical 9-dimensional context tuple for publishing rule resolution.

    Dimensions:
        1. publisher: Publisher platform (KDP, IngramSpark, Lulu)
        2. book_format: Physical format (Paperback, Hardcover)
        3. binding: Specific binding style (Perfect Bound, Casewrap, etc.)
        4. trim_size: Trim dimensions (width, height, standard vs custom)
        5. paper_type: Paper stock and weight
        6. interior_ink: Ink type (B&W, Standard Color, Premium Color)
        7. page_count: Total interior page count
        8. has_bleed: Bleed presence (True / False)
        9. market: Target geographic marketplace (US, UK, DE, etc.)
    """
    publisher: Publisher = Field(..., description="Target publisher")
    book_format: BookFormat = Field(..., description="Paperback or Hardcover")
    binding: BindingType = Field(default=BindingType.PERFECT_BOUND, description="Binding type")
    trim_size: TrimSize = Field(..., description="Trim size object")
    paper_type: PaperType = Field(..., description="Paper stock")
    interior_ink: InteriorInk = Field(..., description="Interior ink")
    page_count: int = Field(..., description="Interior page count")
    has_bleed: bool = Field(default=False, description="Whether interior has bleed")
    market: str = Field(default="US", description="Target market")

    model_config = {"frozen": True}

    @classmethod
    def from_book_config(
        cls,
        config: BookConfiguration,
        market: str = "US",
    ) -> ContextualResolutionTuple:
        """Construct a ContextualResolutionTuple from a BookConfiguration."""
        if config.publisher is None:
            raise ValueError("BookConfiguration must have a publisher specified for contextual resolution.")

        # Default binding if not explicitly set
        binding = config.binding
        if binding is None:
            if config.book_format == BookFormat.HARDCOVER:
                binding = BindingType.CASEWRAP
            else:
                binding = BindingType.PERFECT_BOUND

        return cls(
            publisher=config.publisher,
            book_format=config.book_format,
            binding=binding,
            trim_size=config.trim_size,
            paper_type=config.paper_type,
            interior_ink=config.interior_ink,
            page_count=config.page_count,
            has_bleed=config.has_bleed,
            market=market,
        )

    def to_dimension_dict(self) -> dict[str, Any]:
        """Convert tuple to normalized dictionary for partial dimension matching."""
        return {
            "publisher": self.publisher.value,
            "book_format": self.book_format.value,
            "binding": self.binding.value,
            "trim_width": self.trim_size.width,
            "trim_height": self.trim_size.height,
            "trim_size": self.trim_size.display_name,
            "trim_name": self.trim_size.display_name,
            "paper_type": self.paper_type.value,
            "interior_ink": self.interior_ink.value,
            "page_count": self.page_count,
            "has_bleed": self.has_bleed,
            "market": self.market,
        }

    def matches_partial(self, criteria: dict[str, Any]) -> bool:
        """Check if this context tuple satisfies partial criteria.

        Args:
            criteria: Dictionary of dimension constraints.
                      Values can be literals (str, int, bool), lists/sets,
                      or operator dicts (e.g. {"gte": 80}, {"between": [24, 828]}).

        Returns:
            True if all criteria in the dictionary match this context tuple.
        """
        if not criteria:
            return True

        dim_dict = self.to_dimension_dict()

        for field, target in criteria.items():
            # Normalize field name
            f_norm = field.lower().replace("-", "_")
            if f_norm == "format":
                f_norm = "book_format"
            elif f_norm == "paper":
                f_norm = "paper_type"
            elif f_norm == "ink":
                f_norm = "interior_ink"
            elif f_norm == "pages":
                f_norm = "page_count"
            elif f_norm == "bleed":
                f_norm = "has_bleed"
            elif f_norm == "trim":
                f_norm = "trim_size"

            val = dim_dict.get(f_norm)
            if val is None and f_norm not in dim_dict:
                # Unknown field in criteria
                return False

            if not self._evaluate_field_match(val, target):
                return False

        return True

    @staticmethod
    def _evaluate_field_match(val: Any, target: Any) -> bool:
        """Evaluate match between actual dimension value and target condition."""
        if isinstance(target, dict):
            # Operator dictionary: {"gte": 80}, {"lt": 100}, {"in": [...]}, {"neq": "..."}
            for op, op_val in target.items():
                op_lower = op.lower()
                if op_lower == "eq" and val != op_val:
                    return False
                elif op_lower == "neq" and val == op_val:
                    return False
                elif op_lower == "gt" and not (val > op_val):
                    return False
                elif op_lower == "gte" and not (val >= op_val):
                    return False
                elif op_lower == "lt" and not (val < op_val):
                    return False
                elif op_lower == "lte" and not (val <= op_val):
                    return False
                elif op_lower == "in" and val not in op_val:
                    return False
                elif op_lower == "not_in" and val in op_val:
                    return False
                elif op_lower == "between" and not (op_val[0] <= val <= op_val[1]):
                    return False
            return True

        if isinstance(target, (list, set, tuple)):
            return val in target

        if isinstance(target, str) and isinstance(val, str):
            return val.lower() == target.lower()

        return val == target
