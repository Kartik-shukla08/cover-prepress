"""Domain models for print economics and pricing estimation."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class PrintEconomics(BaseModel):
    """Calculated print economics and pricing estimation for a book."""
    fixed_cost: float = Field(..., description="Fixed manufacturing setup cost")
    per_page_cost: float = Field(..., description="Variable per-page print cost")
    page_count: int = Field(..., gt=0, description="Interior page count")
    billed_page_count: int | None = Field(default=None, description="Page count the vendor bills (odd counts rounded up to even)")
    royalty_rate: float | None = Field(default=None, description="Royalty rate applied (KDP) at list_price, or at the min list price when no list price is given")
    estimated_print_cost: float = Field(..., description="Total estimated unit print cost")
    min_list_price: float | None = Field(default=None, description="Minimum recommended list price to cover print cost & distribution")
    estimated_royalty: float | None = Field(default=None, description="Estimated royalty per copy at list price")
    list_price: float | None = Field(default=None, description="User list price used for royalty calculation")
    currency: str = Field(default="USD", description="Currency code e.g. USD, EUR, GBP")
    marketplace: str = Field(default="US", description="Marketplace / Distribution region")
    publisher: str | None = Field(default=None, description="Publisher name")

    # Extended publisher compensation & discount fields (IngramSpark / KDP parity)
    wholesale_discount: float | None = Field(default=None, description="Wholesale discount rate (e.g. 0.55 for 55%)")
    wholesale_price: float | None = Field(default=None, description="Wholesale revenue received by publisher after retailer discount")
    market_access_fee: float | None = Field(default=None, description="Market access fee per copy (e.g. 1.875% of list price for IngramSpark)")
    publisher_compensation: float | None = Field(default=None, description="Net publisher compensation after discount, print cost, and access fees")
    quantity_discounts: list[dict[str, Any]] | None = Field(default=None, description="Volume discount tiers for publisher direct orders")

    model_config = {"frozen": True}
