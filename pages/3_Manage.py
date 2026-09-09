"""
Manage — delete vendor templates you no longer need, and clean up generated
spreadsheet/CSV files and duplicate-detection history.
"""
import streamlit as st

from extractor import builder as B, load_history, clear_history
from extractor.templates import list_vendors
from extractor.rules import delete_vendor_rules
import importlib
import extractor.ui
importlib.reload(extractor.ui)

from extractor.ui import (apply_theme, top_nav_bar, hero_card, section_header,
                          activity_card, metric_card, ICON_FOLDER)

st.set_page_config(page_title="Manage - Invoice AI", page_icon=":material/folder:", layout="wide")
apply_theme()
top_nav_bar("TEMPLATES & DATA MANAGEMENT", search_placeholder="Search templates and artifacts...", badge_text="Data Manager")

ss = st.session_state
ss.setdefault("confirm_delete", None)
ss.setdefault("confirm_hist", False)

vendors = list_vendors()
files = B.list_output_files()
hist = load_history()

hero_card(
    title="Data & Template Hub",
    subtitle="Audit, maintain, and remove vendor extraction templates, exports, and history.",
    meta_tags=["Local Workspace", "Rule Synchronization", "Full Audit History"],
    stat_items=[
        (str(len(vendors)), "Active Templates"),
        (str(len(files)), "Generated Exports"),
        (str(len(hist)), "History Records"),
        ("Clean", "System Status")
    ],
    desc="Manage workspace artifacts without touching raw source invoices. Deleting a template automatically syncs and removes associated business rules.",
    color="#A3D9B8",
    icon=ICON_FOLDER
)

# ---------------- Vendors / templates ----------------
section_header("01", "Vendor Templates")

if not vendors:
    st.info("No vendor templates installed yet. You can build one on the 'Add New Vendor' page.")
else:
    st.caption("Active YAML templates enabling high-precision, zero-hallucination offline extraction.")
    for v in vendors:
        c1, c2, c3 = st.columns([6, 2, 2])
        c1.markdown(f"**{v['name']}** &nbsp;·&nbsp; <code style='background:#FFF;border:1.5px solid #000;border-radius:4px;padding:2px 6px;'>{v['id']}.yaml</code>", unsafe_allow_html=True)
        if ss.confirm_delete == v["id"]:
            if c2.button("Confirm Delete", key=f"conf_{v['id']}", type="primary", use_container_width=True):
                B.delete_template(v["id"])
                delete_vendor_rules(v["id"])
                ss.confirm_delete = None
                st.success(f"Deleted {v['name']} and synchronized rules.", icon=":material/check:")
                st.rerun()
            if c3.button("Cancel", key=f"cancel_{v['id']}", use_container_width=True):
                ss.confirm_delete = None
                st.rerun()
        else:
            if c3.button("Delete", key=f"del_{v['id']}", use_container_width=True):
                ss.confirm_delete = v["id"]
                st.rerun()

    if ss.confirm_delete:
        st.warning(f"Action Required: Click **Confirm Delete** next to template **{ss.confirm_delete}** to permanently delete it, or Cancel to abort.", icon=":material/warning:")

st.divider()

# ---------------- Generated output files ----------------
section_header("02", "Generated Export Artifacts")
if not files:
    st.info("Output directory is clean. Exported Excel and CSV spreadsheets will appear here.")
else:
    st.caption("Locally cached Excel, CSV, XML, and JSON batch exports.")
    for f in files:
        fc1, fc2 = st.columns([7, 2])
        fc1.markdown(f"**{f['name']}** &nbsp;·&nbsp; `{f['kb']} KB`")
        if fc2.button("Delete File", key=f"delf_{f['name']}", use_container_width=True):
            B.delete_output_file(f["name"])
            st.rerun()

st.divider()

# ---------------- Processing history ----------------
section_header("03", "Duplicate Detection History")
if not hist:
    st.info("No processing history yet. Extracted invoices will be tracked here when marked as processed.")
else:
    st.caption(f"{len(hist)} invoice(s) tracked. Uploaded documents are matched against this ledger to prevent costly duplicate payments.")
    shown_hist = [{
        "Processed": h.get("processed_at", ""),
        "Vendor": h.get("vendor", ""),
        "Invoice #": h.get("invoice_number", ""),
        "Date": h.get("invoice_date", ""),
        "Total": h.get("total", ""),
        "File": h.get("source_file", "")
    } for h in hist[-50:]]
    st.dataframe(shown_hist, hide_index=True, use_container_width=True, height=280)

    if ss.get("confirm_hist"):
        st.warning("Warning: Clearing history permanently removes all fingerprint logs used for duplicate invoice alerts.", icon=":material/warning:")
        cc1, cc2 = st.columns(2)
        if cc1.button("Yes, Clear History Ledger", type="primary", use_container_width=True):
            clear_history()
            ss.confirm_hist = False
            st.success("Processing history cleared.", icon=":material/check:")
            st.rerun()
        if cc2.button("Cancel", use_container_width=True):
            ss.confirm_hist = False
            st.rerun()
    else:
        if st.button("Clear Duplicate Ledger", icon=":material/delete:", use_container_width=False):
            ss.confirm_hist = True
            st.rerun()
