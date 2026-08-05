"""
Data models. Pydantic gives us type-checking and clean structure for free.
"""
from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    # All columns for this line, in the order the template defines them.
    # e.g. {"description": "...", "quantity": 5, "rate": 42000, "taxable_value": 210000,
    #       "gst_pct": 18, "cgst": 18900, "sgst": 18900, "total": 247800}
    cols: dict[str, Any] = Field(default_factory=dict)

    @property
    def description(self) -> str:
        return str(self.cols.get("description", "") or "")

    @property
    def amount(self):
        # the line's payable value, used for reconciliation; prefer an explicit name
        for k in ("amount", "total", "line_total", "total_incl"):
            v = self.cols.get(k)
            if v is not None:
                return v
        return None

    @property
    def extra(self) -> dict:
        return {k: v for k, v in self.cols.items() if k != "description"}

    @property
    def quantity(self):
        return self.cols.get("quantity")

    @property
    def unit_price(self):
        return self.cols.get("unit_price")


class Invoice(BaseModel):
    source_file: str
    vendor: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    po_number: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    cgst: Optional[float] = None
    sgst: Optional[float] = None
    igst: Optional[float] = None
    taxable_value: Optional[float] = None
    line_items: list[LineItem] = []
    # names of line-item columns where a column total is meaningful (money amounts,
    # not per-unit rates or percentages)
    line_total_columns: list[str] = Field(default_factory=list)
    # Any vendor-specific fields (passenger name, PNR, GST components, ...) land here
    extra: dict[str, Any] = Field(default_factory=dict)
    # Filled in by the validator
    validation_ok: bool = True
    validation_notes: list[str] = []
    confidence: float = 1.0
    # OCR tracking fields
    ocr_used: bool = False
    ocr_confidence: float = 1.0
    ocr_engine_version: str = ""
    # cross-check of extracted values against the printed PDF (see reconcile.py)
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    # business-rule failures (see rules.py) and duplicate detection (see dedupe.py)
    rule_failures: list[str] = Field(default_factory=list)
    duplicate_of: str = ""
    duplicate_note: str = ""
