"""
Business rules ("validation rules") - configurable checks applied to every extracted
invoice, beyond arithmetic.

Two levels:
  * a **default** profile, and
  * optional **per-vendor** profiles, selected in the app by a dropdown.

A vendor profile inherits the default and overrides only what it sets, so you can
require (say) a GSTIN for Indian suppliers but not for an overseas one.
"""
import os
import re
from datetime import datetime, date

import yaml

BASE = os.path.dirname(os.path.dirname(__file__))
RULES_PATH = os.path.join(BASE, "rules.yaml")

# ---- field aliases: invoices label the same thing many different ways -------
ALIASES = {
    "invoice_number": ["invoice_number", "bill_number", "order_number", "receipt_number",
                       "bill_no", "order_no", "invoice_no", "voucher_number"],
    "bill_from": ["vendor", "supplier", "supplier_name", "bill_from", "seller",
                  "store", "merchant", "supplier_gstin", "supplier_address"],
    "bill_to": ["bill_to", "billed_to", "customer", "customer_name", "buyer",
                "ship_to", "consignee", "customer_gstin", "recipient"],
    "tax_id": ["supplier_gstin", "gstin", "gst_number", "customer_gstin", "vat_number",
               "tax_id", "tin", "abn", "ein"],
    "regulatory": ["hsn_sac", "pan", "cin", "place_of_supply", "state_code",
                   "reverse_charge", "irn", "eway_bill", "lut"],
    "cgst": ["cgst", "cgst_amount", "cgst_amt"],
    "sgst": ["sgst", "sgst_amount", "sgst_amt", "utgst"],
    "igst": ["igst", "igst_amount", "igst_amt"],
}

LINE_ALIASES = {
    "description": ["description", "particulars", "item", "details", "product"],
    "quantity": ["quantity", "qty", "units", "nos"],
    "unit_rate": ["unit_rate", "rate", "unit_price", "price", "mrp", "unit_cost"],
    "amount": ["amount", "total", "line_total", "taxable_value", "value"],
}

DEFAULT_RULES = {
    "required": ["invoice_date"],
    "require_any": [["invoice_number", "bill_number", "order_number", "receipt_number"]],
    "require_bill_from": True,
    "require_bill_to": False,
    "require_tax_id": False,
    "require_regulatory": False,
    "require_line_fields": ["description"],
    "require_tax_breakup": False,
    "require_subtotal": False,
    "require_total": True,
    "regex": {},
    "max_total": None,
    "min_total": None,
    "date_not_future": True,
    "date_max_age_days": None,
    "allowed_tax_rates": None,
    "require_line_items": True,
}

GST_PROFILE = {
    "required": ["invoice_date"],
    "require_any": [["invoice_number", "bill_number", "order_number"]],
    "require_bill_from": True,
    "require_bill_to": True,
    "require_tax_id": True,
    "require_regulatory": True,
    "require_line_fields": ["description", "quantity", "unit_rate"],
    "require_tax_breakup": True,
    "require_subtotal": True,
    "require_total": True,
    "allowed_tax_rates": [0, 0.25, 3, 5, 12, 18, 28],
}

PRESETS = {
    "Standard (default)": DEFAULT_RULES,
    "Full GST tax invoice (strict)": GST_PROFILE,
    "Receipt / delivery order (light)": {
        "required": [],
        "require_any": [["invoice_number", "bill_number", "order_number", "receipt_number"]],
        "require_bill_from": True, "require_bill_to": False, "require_tax_id": False,
        "require_regulatory": False, "require_line_fields": ["description"],
        "require_tax_breakup": False, "require_subtotal": False, "require_total": True,
        "require_line_items": True, "date_not_future": True,
    },
}


# ------------------------------------------------------------------ storage
def _raw() -> dict:
    if os.path.exists(RULES_PATH):
        try:
            with open(RULES_PATH, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _is_legacy(data: dict) -> bool:
    return bool(data) and "default" not in data and "vendors" not in data


def load_all() -> dict:
    data = _raw()
    if _is_legacy(data):
        data = {"default": data, "vendors": {}}
    default = dict(DEFAULT_RULES)
    default.update(data.get("default") or {})
    return {"default": default, "vendors": data.get("vendors") or {}}


def load_rules(vendor_id: str = None) -> dict:
    cfg = load_all()
    rules = dict(cfg["default"])
    if vendor_id and vendor_id in cfg["vendors"]:
        rules.update(cfg["vendors"][vendor_id] or {})
    return rules


def save_all(cfg: dict) -> str:
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump({"default": cfg.get("default") or DEFAULT_RULES,
                        "vendors": cfg.get("vendors") or {}},
                       f, sort_keys=False, allow_unicode=True)
    return RULES_PATH


def save_rules(rules: dict, vendor_id: str = None) -> str:
    cfg = load_all()
    if vendor_id:
        cfg["vendors"][vendor_id] = rules
    else:
        cfg["default"] = rules
    return save_all(cfg)


def delete_vendor_rules(vendor_id: str) -> bool:
    cfg = load_all()
    if vendor_id in cfg["vendors"]:
        del cfg["vendors"][vendor_id]
        save_all(cfg)
        return True
    return False


# ------------------------------------------------------------------ helpers
def _get(inv, field):
    if hasattr(inv, field):
        v = getattr(inv, field)
        if v not in (None, "", []):
            return v
    for k, v in (inv.extra or {}).items():
        if k.lower() == field.lower() and v not in (None, "", []):
            return v
    return None


def _any_alias(inv, group: str):
    names = ALIASES.get(group, [group])
    for name in names:
        if _get(inv, name) is not None:
            return True
    for k, v in (inv.extra or {}).items():
        if v in (None, "", []) or k.startswith("_"):
            continue
        lk = k.lower()
        if any(a in lk for a in names):
            return True
    # some identifiers (HSN/SAC codes) live on the line items rather than the header
    for li in inv.line_items:
        for k, v in li.cols.items():
            if v in (None, "", []):
                continue
            lk = k.lower()
            if any(a in lk for a in names):
                return True
    return False


def _line_has(inv, concept: str) -> bool:
    names = LINE_ALIASES.get(concept, [concept])
    if not inv.line_items:
        return False
    for li in inv.line_items:
        present = any(str(li.cols.get(n, "")).strip() not in ("", "None")
                      for n in names if n in li.cols)
        if not present:
            return False
    return True


def _parse_date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None


# ------------------------------------------------------------------ the checks
def apply_rules(inv, rules: dict = None, vendor_id: str = None):
    """Run the rules for this vendor. Sets inv.rule_failures and returns it."""
    rules = rules if rules is not None else load_rules(vendor_id)
    f = []

    for field in (rules.get("required") or []):
        if _get(inv, field) is None:
            f.append(f"missing required field '{field}'")

    for group in (rules.get("require_any") or []):
        if not any(_get(inv, g) is not None for g in group):
            f.append("missing an identifier - need one of: " + " / ".join(group))

    if rules.get("require_bill_from") and not _any_alias(inv, "bill_from"):
        f.append("no supplier / 'bill from' details found")
    if rules.get("require_bill_to") and not _any_alias(inv, "bill_to"):
        f.append("no customer / 'bill to' details found")
    if rules.get("require_tax_id") and not _any_alias(inv, "tax_id"):
        f.append("no GST/VAT/tax registration number found")
    if rules.get("require_regulatory") and not _any_alias(inv, "regulatory"):
        f.append("no regulatory details found (HSN/SAC, PAN, CIN, place of supply...)")

    for concept in (rules.get("require_line_fields") or []):
        if not _line_has(inv, concept):
            f.append(f"line items are missing '{concept}'")

    if rules.get("require_tax_breakup"):
        has_cgst = _any_alias(inv, "cgst")
        has_sgst = _any_alias(inv, "sgst")
        has_igst = _any_alias(inv, "igst")
        if not ((has_cgst and has_sgst) or has_igst):
            f.append("no tax breakup found - expected CGST + SGST, or IGST")

    if rules.get("require_subtotal") and inv.subtotal is None:
        f.append("no sub total found")
    if rules.get("require_total") and inv.total is None:
        f.append("no invoice total found")

    for field, pattern in (rules.get("regex") or {}).items():
        v = _get(inv, field)
        if v is not None and v != "" and not re.fullmatch(pattern, str(v).strip()):
            f.append(f"'{field}' ({v}) doesn't match the expected format")

    total = inv.total
    if total is not None:
        mx, mn = rules.get("max_total"), rules.get("min_total")
        if mx is not None and total > float(mx):
            f.append(f"total {total:,.2f} exceeds the approval threshold {float(mx):,.2f}")
        if mn is not None and total < float(mn):
            f.append(f"total {total:,.2f} is below the minimum {float(mn):,.2f}")

    d = _parse_date(inv.invoice_date)
    if d:
        if rules.get("date_not_future") and d > date.today():
            f.append(f"invoice date {d} is in the future")
        age = rules.get("date_max_age_days")
        if age is not None and (date.today() - d).days > int(age):
            f.append(f"invoice is older than {age} days (dated {d})")
    elif inv.invoice_date:
        f.append(f"invoice date '{inv.invoice_date}' couldn't be understood")

    if rules.get("require_line_items") and not inv.line_items:
        f.append("no line items were extracted")

    allowed = rules.get("allowed_tax_rates")
    if allowed:
        allowed_set = {float(a) for a in allowed}
        for i, li in enumerate(inv.line_items, 1):
            for key in ("gst_pct", "tax_rate", "igst_pct", "rate_pct", "gst_rate"):
                v = li.cols.get(key)
                if isinstance(v, (int, float)) and float(v) not in allowed_set:
                    f.append(f"line {i}: tax rate {v}% is not an allowed rate")
                    break

    inv.rule_failures = f
    return f
