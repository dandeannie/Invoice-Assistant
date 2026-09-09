"""
Business Rules — completeness and compliance checks, configurable per vendor or globally.
"""
import streamlit as st

from extractor import list_vendors
from extractor.rules import (load_all, load_rules, save_rules, delete_vendor_rules,
                             PRESETS, DEFAULT_RULES)
from extractor.security import log_event
import importlib
import extractor.ui
importlib.reload(extractor.ui)

from extractor.ui import (apply_theme, top_nav_bar, hero_card, section_header,
                          metric_card, status_pill, ICON_RULES)

st.set_page_config(page_title="Business Rules - Invoice AI", page_icon=":material/rule:", layout="wide")
apply_theme()
top_nav_bar("COMPLIANCE & RULES", search_placeholder="Search compliance checks...", badge_text="Rule Engine")

# ---------------- which profile ----------------
vendors = list_vendors()
choices = ["Default (all vendors)"] + [f"{v['name']}  ({v['id']})" for v in vendors]
pick = st.selectbox("Select Target Vendor Profile", choices, key="rule_target")
vendor_id = None if pick.startswith("Default") else vendors[choices.index(pick) - 1]["id"]

cfg = load_all()
has_own = vendor_id in cfg["vendors"] if vendor_id else False
profile_status = "Custom Vendor Profile" if has_own else ("Global Default" if not vendor_id else "Inherited Default")

r = load_rules(vendor_id)

hero_card(
    title="Invoice Validation Rules",
    subtitle=f"Configuring validation policy for: {pick}",
    meta_tags=[profile_status, "GST / Tax Rules", "Zero-Tolerance Reconciliation"],
    stat_items=[
        (str(len(r.get("require_any", [[]])[0])), "Required ID Fields"),
        ("Strict" if r.get("require_tax_breakup") else "Standard", "Tax Enforcement"),
        ("Enabled" if r.get("date_not_future") else "Disabled", "Future Date Check"),
        ("Yes" if r.get("require_line_items") else "No", "Line Items Mandatory")
    ],
    desc="Rules enforce business logic beyond simple arithmetic. When extracted invoices miss essential fields or breach spending thresholds, they are instantly flagged for human review.",
    color="#F8CD53",
    icon=ICON_RULES
)

# Preset Switcher
c1, c2 = st.columns([3, 1.5])
preset = c1.selectbox("Load Standard Compliance Preset", ["(keep current settings)"] + list(PRESETS))
if c2.button("Apply Preset", use_container_width=True) and preset != "(keep current settings)":
    r = dict(DEFAULT_RULES)
    r.update(PRESETS[preset])
    st.session_state["_loaded_preset"] = r
    st.rerun()
r = st.session_state.pop("_loaded_preset", r)

st.divider()

# ---------------- Section 1: Required Document Elements ----------------
section_header("01", "Mandatory Document Fields")

ID_FIELDS = ["invoice_number", "bill_number", "order_number", "receipt_number"]
id_group = (r.get("require_any") or [ID_FIELDS])[0]
ids = st.multiselect(
    "Document Identifier (At least ONE of these must be present)",
    ID_FIELDS, default=[f for f in id_group if f in ID_FIELDS],
    help="Invoice #, Bill #, Order # or Receipt # — satisfying any one passes this rule."
)

col_a, col_b, col_c = st.columns(3)
require_bill_from = col_a.checkbox("Require Bill From (Supplier Name/Details)", value=bool(r.get("require_bill_from", True)))
require_bill_to = col_b.checkbox("Require Bill To (Customer Details)", value=bool(r.get("require_bill_to", False)))
require_date = col_c.checkbox("Require Invoice Date", value="invoice_date" in (r.get("required") or []))

col_d, col_e, col_f = st.columns(3)
require_tax_id = col_d.checkbox("Require GSTIN / Tax ID", value=bool(r.get("require_tax_id", False)))
require_reg = col_e.checkbox("Require Regulatory Fields (HSN/SAC, PAN, CIN)", value=bool(r.get("require_regulatory", False)))
require_breakup = col_f.checkbox("Require Tax Breakup (CGST+SGST or IGST)", value=bool(r.get("require_tax_breakup", False)))

col_g, col_h = st.columns(2)
require_subtotal = col_g.checkbox("Require Subtotal", value=bool(r.get("require_subtotal", False)))
require_total = col_h.checkbox("Require Total Amount", value=bool(r.get("require_total", True)))

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("#### Line Item Constraints")
g1, g2 = st.columns([3, 2])
line_fields = g1.multiselect(
    "Every line item must include",
    ["description", "quantity", "unit_rate", "amount"],
    default=r.get("require_line_fields") or ["description"],
    help="Ensures invoices contain detailed itemized breakdowns."
)
require_li = g2.checkbox("Enforce at least one line item", value=bool(r.get("require_line_items", True)))

st.divider()

# ---------------- Section 2: Amounts & Dates ----------------
section_header("02", "Thresholds, Dates & Regex Checks")

h1, h2 = st.columns(2)
use_max = h1.checkbox("Flag invoices exceeding maximum total", value=r.get("max_total") is not None)
max_total = h1.number_input("Maximum allowed invoice total", min_value=0.0, step=1000.0,
                            value=float(r.get("max_total") or 100000.0)) if use_max else None

use_min = h2.checkbox("Flag invoices below minimum total", value=r.get("min_total") is not None)
min_total = h2.number_input("Minimum allowed invoice total", min_value=0.0, step=100.0,
                            value=float(r.get("min_total") or 0.0)) if use_min else None

i1, i2 = st.columns(2)
date_not_future = i1.checkbox("Disallow future-dated invoices", value=bool(r.get("date_not_future", True)))
use_age = i2.checkbox("Flag stale invoices older than N days", value=r.get("date_max_age_days") is not None)
max_age = i2.number_input("Maximum age threshold (days)", min_value=1, step=30,
                          value=int(r.get("date_max_age_days") or 90)) if use_age else None

use_rates = st.checkbox("Strict tax percentage validation", value=r.get("allowed_tax_rates") is not None)
rates_txt = st.text_input(
    "Allowed tax rates % (comma separated)",
    value=", ".join(str(x) for x in (r.get("allowed_tax_rates") or [0, 5, 12, 18, 28]))
) if use_rates else ""

with st.expander("Advanced Format Constraints (Regex)", icon=":material/search:"):
    st.caption("Map fields to custom regular expressions. Example: `supplier_gstin` → `[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]`")
    regex_txt = st.text_area(
        "One rule per line: field | regex_pattern",
        value="\n".join(f"{k} | {v}" for k, v in (r.get("regex") or {}).items()),
        height=100
    )

st.divider()

b1, b2, _ = st.columns([2, 2, 2])
if b1.button("Save Profile Rules", icon=":material/save:", type="primary", use_container_width=True):
    regex = {}
    if regex_txt:
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
            st.error("Tax rates must be valid numbers, e.g. 0, 5, 12, 18, 28")
            st.stop()

    new_rules = {
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
    save_rules(new_rules, vendor_id)
    log_event("rules_saved", f"profile={vendor_id or 'default'}")
    st.success(f"Compliance rules saved for **{pick}**. Active immediately.", icon=":material/check:")

if vendor_id and has_own:
    if b2.button("Remove Custom Vendor Profile", icon=":material/delete:", use_container_width=True):
        delete_vendor_rules(vendor_id)
        log_event("rules_deleted", f"profile={vendor_id}")
        st.success(f"Profile reset: {pick} now inherits Default rules.", icon=":material/check:")
        st.rerun()

with st.expander("Effective YAML Rules Definition", icon=":material/code:"):
    st.code(load_rules(vendor_id), language="yaml")
