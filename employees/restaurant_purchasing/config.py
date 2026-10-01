"""Settings and onboarding wizard steps. Both are exported as JSON Schema, so the
install screen renders them with AutoForm and no pack-specific UI code."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PurchasingConfig(BaseModel):
    restaurant_name: str = Field(description="Shown on purchase orders")
    approval_threshold: float = Field(1500, ge=0, description="Orders above this total wait for the owner")
    price_variance_tolerance_pct: float = Field(2.0, ge=0, description="Invoice price above PO price by more than this is disputed")
    primary_supplier: str | None = Field(None, description="Your main broadline distributor, used to measure savings")
    delivery_note: str = Field("Please confirm by reply.", description="Added to every PO email")


class SupplierIn(BaseModel):
    name: str
    email: str
    min_order: float = 0
    delivery_days: list[str] = []


class PriceLine(BaseModel):
    item: str
    pack_size: float = Field(gt=0)
    pack_price: float = Field(ge=0)
    unit: str = "each"
    category: str = "general"


class PriceList(BaseModel):
    supplier: str
    lines: list[PriceLine]


class ParLevel(BaseModel):
    item: str
    par_level: float = Field(ge=0)
    on_hand: float | None = Field(None, ge=0)


class SuppliersStep(BaseModel):
    suppliers: list[SupplierIn]


class PriceListsStep(BaseModel):
    price_lists: list[PriceList]


class ParLevelsStep(BaseModel):
    items: list[ParLevel]
