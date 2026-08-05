"""
Manage — delete vendor templates you no longer need, and clean up generated
spreadsheet/CSV files.
"""
import streamlit as st

from extractor import builder as B
from extractor.templates import list_vendors

from extractor.ui import apply_theme, hero

st.set_page_config(page_title="Manage", page_icon="🗂️", layout="centered")
apply_theme()
hero("🗂️ Manage", "Delete vendor templates, generated files, and processing history.", "#6B4E8F")

ss = st.session_state
ss.setdefault("confirm_delete", None)   # vendor id awaiting confirmation
ss.setdefault("confirm_hist", False)

# ---------------- Vendors / templates ----------------
st.subheader("Vendor templates")
vendors = list_vendors()
if not vendors:
    st.info("No templates yet. Add one on the 'Add New Vendor' page.")
else:
    st.caption("Deleting a template removes that vendor from the dropdown. "
               "Your invoices and spreadsheets are not affected.")
    for v in vendors:
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{v['name']}**  ·  `{v['id']}.yaml`")
        if ss.confirm_delete == v["id"]:
            if c2.button("Confirm", key=f"conf_{v['id']}", type="primary"):
                B.delete_template(v["id"])
                ss.confirm_delete = None
                st.success(f"Deleted {v['name']}.")
                st.rerun()
        else:
            if c2.button("Delete", key=f"del_{v['id']}"):
                ss.confirm_delete = v["id"]
                st.rerun()
    if ss.confirm_delete:
        st.warning(f"Click **Confirm** next to '{ss.confirm_delete}' to permanently "
                   f"delete it, or refresh the page to cancel.")

st.divider()

# ---------------- Generated output files ----------------
st.subheader("Generated files (spreadsheets / CSV)")
files = B.list_output_files()
if not files:
    st.info("No generated files in the output folder.")
else:
    st.caption("These are Excel/CSV files saved in the tool's 'output' folder. "
               "Deleting them here does not touch files you've already downloaded elsewhere.")
    for f in files:
        c1, c2 = st.columns([5, 1])
        c1.write(f"📄 {f['name']}  ·  {f['kb']} KB")
        if c2.button("Delete", key=f"delf_{f['name']}"):
            B.delete_output_file(f["name"])
            st.rerun()

st.divider()

# ---------------- Processing history ----------------
st.subheader("Processing history (duplicate detection)")
from extractor import load_history, clear_history

hist = load_history()
if not hist:
    st.info("No invoices recorded yet. Use 'Mark as processed' after an extraction run "
            "so repeat invoices get flagged later.")
else:
    st.caption(f"{len(hist)} invoice(s) recorded. New uploads are checked against these "
               "to catch duplicate billing.")
    st.dataframe([{k: h.get(k) for k in
                   ("processed_at", "vendor", "invoice_number", "invoice_date",
                    "total", "source_file")} for h in hist[-50:]],
                 hide_index=True, use_container_width=True)
    if ss.get("confirm_hist"):
        st.warning("This clears the duplicate-detection history permanently.")
        cc1, cc2 = st.columns(2)
        if cc1.button("Yes, clear history", type="primary"):
            clear_history()
            ss.confirm_hist = False
            st.success("History cleared.")
            st.rerun()
        if cc2.button("Cancel"):
            ss.confirm_hist = False
            st.rerun()
    else:
        if st.button("Clear history"):
            ss.confirm_hist = True
            st.rerun()

st.divider()
st.caption("Tip: to remove invoices from a batch *before* extracting, use the ✕ on each "
           "file in the uploader on the main page.")
