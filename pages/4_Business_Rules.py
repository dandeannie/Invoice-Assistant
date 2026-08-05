"""
Business Rules — completeness and compliance checks, per vendor.
"""
import streamlit as st

from extractor import list_vendors
from extractor.rules import (load_all, load_rules, save_rules, delete_vendor_rules,
                             PRESETS, DEFAULT_RULES)
from extractor.security import log_event
from extractor.ui import apply_theme, hero

st.set_page_config(page_title="Business Rules", page_icon="📋", layout="wide")
apply_theme()
hero("📋 Business Rules",
     "Checks applied to every invoice on top of the arithmetic validation. "
     "Set a different profile for each vendor.", "#0B6E4F")

# ---------------- which profile ----------------
vendors = list_vendors()
choices = ["Default (all vendors)"] + [f"{v['name']}  ({v['id']})" for v in vendors]
pick = st.selectbox("Apply rules to", choices, key="rule_target")
vendor_id = None if pick.startswith("Default") else vendors[choices.index(pick) - 1]["id"]

cfg = load_all()
has_own = vendor_id in cfg["vendors"] if vendor_id else False
if vendor_id:
    st.caption(f"This vendor {'has its own profile' if has_own else 'currently inherits the Default profile'}.")

r = load_rules(vendor_id)

c1, c2 = st.columns([3, 2])
preset = c1.selectbox("Start from a preset", ["(keep current settings)"] + list(PRESETS))
if c2.button("Load preset", use_container_width=True) and preset != "(keep current settings)":
    r = dict(DEFAULT_RULES); r.update(PRESETS[preset])
    st.session_state["_loaded_preset"] = r
    st.rerun()
r = st.session_state.pop("_loaded_preset", r)

st.divider()

# ---------------- what an invoice must contain ----------------
st.subheader("An invoice must contain")

ID_FIELDS = ["invoice_number", "bill_number", "order_number", "receipt_number"]
id_group = (r.get("require_any") or [ID_FIELDS])[0]
ids = st.multiselect(
    "An identifier — at least ONE of these must be present",
    ID_FIELDS, default=[f for f in id_group if f in ID_FIELDS],
    help="Invoice #, Bill #, Order # or Receipt # — any one satisfies the rule.")

d1, d2, d3 = st.columns(3)
require_bill_from = d1.checkbox("Bill from (supplier details)", value=bool(r.get("require_bill_from", True)))
require_bill_to = d2.checkbox("Bill to (customer details)", value=bool(r.get("require_bill_to", False)))
require_date = d3.checkbox("Invoice date", value="invoice_date" in (r.get("required") or []))

e1, e2, e3 = st.columns(3)
require_tax_id = e1.checkbox("GST / VAT / tax number", value=bool(r.get("require_tax_id", False)))
require_reg = e2.checkbox("Regulatory details (HSN/SAC, PAN, CIN, place of supply)",
                          value=bool(r.get("require_regulatory", False)))
require_breakup = e3.checkbox("Tax breakup (CGST+SGST, or IGST)",
                              value=bool(r.get("require_tax_breakup", False)))

f1, f2 = st.columns(2)
require_subtotal = f1.checkbox("Sub total", value=bool(r.get("require_subtotal", False)))
require_total = f2.checkbox("Invoice total", value=bool(r.get("require_total", True)))

st.markdown("**Line items**")
g1, g2 = st.columns([3, 2])
line_fields = g1.multiselect(
    "Every line item must have", ["description", "quantity", "unit_rate", "amount"],
    default=r.get("require_line_fields") or ["description"],
    help="A descriptive list of items, with unit rate and quantity where required.")
require_li = g2.checkbox("At least one line item", value=bool(r.get("require_line_items", True)))

st.divider()

# ---------------- amounts, dates, formats ----------------
st.subheader("Amounts, dates and formats")
h1, h2 = st.columns(2)
use_max = h1.checkbox("Flag invoices above an amount", value=r.get("max_total") is not None)
max_total = h1.number_input("Maximum total", min_value=0.0, step=1000.0,
                            value=float(r.get("max_total") or 100000.0)) if use_max else None
use_min = h2.checkbox("Flag invoices below an amount", value=r.get("min_total") is not None)
min_total = h2.number_input("Minimum total", min_value=0.0, step=100.0,
                            value=float(r.get("min_total") or 0.0)) if use_min else None

i1, i2 = st.columns(2)
date_not_future = i1.checkbox("Invoice date must not be in the future",
                              value=bool(r.get("date_not_future", True)))
use_age = i2.checkbox("Flag invoices older than N days", value=r.get("date_max_age_days") is not None)
max_age = i2.number_input("Days", min_value=1, step=30,
                          value=int(r.get("date_max_age_days") or 90)) if use_age else None

use_rates = st.checkbox("Only allow specific tax percentages",
                        value=r.get("allowed_tax_rates") is not None)
rates_txt = st.text_input("Allowed rates (comma separated)",
                          value=", ".join(str(x) for x in (r.get("allowed_tax_rates")
                                                           or [0, 5, 12, 18, 28]))) if use_rates else ""

with st.expander("Format checks (advanced)"):
    st.caption("Field → regular expression. Example: `supplier_gstin` → "
               "`[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]` for an Indian GSTIN.")
    regex_txt = st.text_area("One per line:  field | pattern",
                             value="\n".join(f"{k} | {v}" for k, v in (r.get("regex") or {}).items()),
                             height=90)

st.divider()
b1, b2, b3 = st.columns([2, 2, 3])
if b1.button("💾 Save rules", type="primary", use_container_width=True):
    regex = {}
    for line in regex_txt.splitlines():
        if "|" in line:
            k, v = line.split("|", 1)
            if k.strip() and v.strip():
                regex[k.strip()] = v.strip()
    rates = None
    if use_rates:
        try:
            rates = [float(x.strip()) for x in rates_txt.split(",") if x.strip()]
        except ValueError:
            st.error("Allowed rates must be numbers, e.g. 0, 5, 12, 18, 28")
            st.stop()
    new = {
        "required": (["invoice_date"] if require_date else []),
        "require_any": [ids] if ids else [],
        "require_bill_from": require_bill_from,
        "require_bill_to": require_bill_to,
        "require_tax_id": require_tax_id,
        "require_regulatory": require_reg,
        "require_tax_breakup": require_breakup,
        "require_subtotal": require_subtotal,
        "require_total": require_total,
        "require_line_fields": line_fields,
        "require_line_items": require_li,
        "regex": regex,
        "max_total": float(max_total) if use_max else None,
        "min_total": float(min_total) if use_min else None,
        "date_not_future": date_not_future,
        "date_max_age_days": int(max_age) if use_age else None,
        "allowed_tax_rates": rates,
    }
    save_rules(new, vendor_id)
    log_event("rules_saved", f"profile={vendor_id or 'default'}")
    st.success(f"Saved rules for **{pick}**. They apply to the next extraction run.")

if vendor_id and has_own:
    if b2.button("Remove this vendor's profile", use_container_width=True):
        delete_vendor_rules(vendor_id)
        log_event("rules_deleted", f"profile={vendor_id}")
        st.success(f"{pick} now inherits the Default profile.")
        st.rerun()

with st.expander("Current effective rules (raw)"):
    st.code(load_rules(vendor_id))
