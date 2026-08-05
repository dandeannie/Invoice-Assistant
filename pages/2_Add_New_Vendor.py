"""
Add a new vendor - build (or auto-generate) a template without leaving the app.

Three ways to build it, all feeding one editable YAML you can Test then Save:
  * AI     - let Claude read the sample invoice and write the template
  * Point  - the detected fields are highlighted on a preview; click one to grab it
  * Pick   - choose labels from dropdowns
"""
import os
import tempfile

import streamlit as st
import yaml

from extractor import builder as B
from extractor import autotemplate as AT
from extractor.security import log_event

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
    HAVE_CLICK = True
except Exception:
    HAVE_CLICK = False

from extractor.ui import apply_theme, hero

st.set_page_config(page_title="Add a vendor", page_icon="➕", layout="centered")
apply_theme()
hero("➕ Add New Vendor", "Build a reusable template from one sample invoice.", "#2F5B8F")

ss = st.session_state
ss.setdefault("draft_yaml", "")
ss.setdefault("fields", [])
ss.setdefault("sample_path", None)
ss.setdefault("pt_selected", None)
ss.setdefault("line_items_cfg", None)
ss.setdefault("li_columns", [])
ss.setdefault("li_pending_x0", None)

# ---------- vendor name + sample upload ----------
vendor_name = st.text_input("Vendor name", placeholder="e.g. Acme Corporation")
sample = st.file_uploader("Upload ONE sample invoice from this vendor (PDF)", type=["pdf"])
if sample is not None:
    prev_tmp = ss.get("sample_tmp_path")
    if prev_tmp and os.path.exists(prev_tmp):
        try:
            os.remove(prev_tmp)
        except OSError:
            pass
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(sample.getbuffer())
        tmp_path = tmp.name
    ss.sample_tmp_path = tmp_path
    ss.sample_path = tmp_path

if not ss.sample_path:
    st.info("Upload a sample invoice to begin.")
    st.stop()

page = B.load_page(ss.sample_path)
words = page["words"]

method = st.radio("How would you like to build the template?",
                  options=["auto", "ai", "point", "pick"],
                  format_func=lambda m: {
                      "auto": "⚡  Auto-build — read the invoice and write the template (no AI)",
                      "ai": "🤖  AI — generate it for me",
                      "point": "🖱️  Point — click the highlighted fields",
                      "pick": "📋  Pick — choose from dropdowns"}[m])
st.divider()


def add_field(name, anchor, ftype, gap=None, nth=None, below=None):
    if name and anchor:
        entry = {"name": name, "anchor": anchor, "type": ftype, "gap": gap,
                 "nth": nth, "below": below}
        for i, f in enumerate(ss.fields):
            if f["name"] == name:
                ss.fields[i] = entry
                return
        ss.fields.append(entry)


# =====================================================================
# METHOD: AI
# =====================================================================
if method == "auto":
    st.markdown("#### ⚡ Auto-build from this invoice")
    st.caption("Works out the labels, the line-item table and its columns from the "
               "page layout — no AI, no clicking. Handles tables with any number of "
               "rows. Then check the result below and save.")
    if st.button("Build template from this invoice", type="primary",
                 use_container_width=True):
        with st.spinner("Reading the invoice layout…"):
            tpl, report, inv, rec = AT.build_and_verify(ss.sample_path, vendor_name or None)
        ss.draft_yaml = B.to_yaml(tpl)
        ss.auto_report = report
        ss.auto_result = (inv, rec)
        log_event("template_autobuilt", f"vendor={vendor_name or tpl.get('vendor')}")

    if ss.get("auto_report"):
        for line in ss.auto_report:
            st.write("• " + line)
        inv, rec = ss.auto_result
        if inv is None:
            st.error("Couldn't read this invoice automatically. Try the AI method, or "
                     "build it by clicking the fields.")
        else:
            ok = rec.get("status") == "OK"
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Line items", len(inv.line_items))
            c2.metric("Sub total", f"{inv.subtotal:,.2f}" if inv.subtotal is not None else "—")
            c3.metric("Total", f"{inv.total:,.2f}" if inv.total is not None else "—")
            c4.metric("Check", "✅ OK" if ok else "⚠️ Review")
            if ok:
                st.success("The extracted totals match the figures printed on the "
                           "invoice. Review below and save.")
            else:
                st.warning("The numbers don't fully match the printed invoice: "
                           + (rec.get("notes") or "") +
                           "  You can edit the YAML below, or try the AI method.")
            st.write("**Header fields**")
            st.dataframe([{"Field": k, "Value": v} for k, v in
                          {"vendor": inv.vendor, "invoice_number": inv.invoice_number,
                           "invoice_date": inv.invoice_date, "subtotal": inv.subtotal,
                           "tax": inv.tax, "total": inv.total,
                           **{k: v for k, v in inv.extra.items() if not k.startswith("_")}
                           }.items()], hide_index=True, use_container_width=True)
            if inv.line_items:
                st.write(f"**Line items ({len(inv.line_items)})**")
                st.dataframe([dict(li.cols) for li in inv.line_items],
                             hide_index=True, use_container_width=True)

elif method == "ai":
    st.subheader("Let an AI write the template")
    preset_name = st.selectbox("AI provider", list(B.LLM_PRESETS.keys()))
    preset = B.LLM_PRESETS[preset_name]

    base_url = None
    if preset["provider"] == "openai":
        base_url = st.text_input("API base URL", value=preset["base_url"],
                                 help="The endpoint URL. Preset for the provider above; edit for a custom one.")
    model = st.text_input("Model", value=preset["model"],
                          help="Use whatever model name your account/provider gives you.")
    env_key = os.environ.get(preset["key_env"], "") if preset.get("key_env") else ""
    key = st.text_input("API key", value=env_key, type="password",
                        help="For local models (Ollama), any text works, e.g. 'ollama'.")

    can_go = bool(vendor_name and model and (key or preset_name.startswith("Local")))
    if st.button("Generate template with AI", type="primary", disabled=not can_go):
        with st.spinner(f"Asking {preset_name} to read the invoice and write the template..."):
            try:
                ss.draft_yaml = B.llm_generate_template(
                    vendor_name, words, key or "ollama", model,
                    provider=preset["provider"], base_url=base_url)
                st.success("Draft generated. Review below, then Test and Save.")
            except Exception as e:
                st.error(f"Could not generate: {e}")

# =====================================================================
# METHOD: POINT (highlighted click)
# =====================================================================
elif method == "point":
    st.subheader("Click a highlighted value, then assign it to a field")
    if not HAVE_CLICK:
        st.warning("Click component not installed. Run:  pip install streamlit-image-coordinates")
    else:
        cands = B.field_candidates(words)
        st.caption("Each detected value is boxed and numbered. Click inside or near a box.")
        preview = B.render_preview(page["image"], page["scale"], cands, ss.pt_selected)
        coords = streamlit_image_coordinates(preview, width=560, key="clicker")
        if coords and coords.get("width"):
            x_pt = coords["x"] * page["width"] / coords["width"]
            y_pt = coords["y"] * page["height"] / coords["height"]
            idx = B.nearest_candidate(cands, x_pt, y_pt)
            if idx is not None:
                c = cands[idx]
                ss.pt_selected = idx
                ss.clicked_anchor = c["anchor"]
                ss.clicked_value = c["value"]
                ss.clicked_gap = c.get("gap_hint")
                ss.clicked_nth = c.get("nth")
                ss.clicked_below = c.get("below")
                ss.clicked_is_money = c.get("is_money", False)
            else:  # fell outside every box: snap to nearest word and derive its label
                w = B.point_to_word(words, x_pt, y_pt)
                ss.pt_selected = None
                ss.clicked_anchor = B.anchor_from_value(words, w) if w else ""
                ss.clicked_value = w["text"] if w else ""
                ss.clicked_gap = None
                ss.clicked_nth = None
                ss.clicked_below = None
                ss.clicked_is_money = False

        if ss.get("clicked_anchor"):
            kind = "money" if ss.get("clicked_is_money") else "text"
            st.info(f"Selected {kind} value **{ss.get('clicked_value') or '(blank)'}**  →  "
                    f"label **{ss['clicked_anchor']}**")
            c1, c2, c3 = st.columns([2, 2, 1])
            fname = c1.selectbox("Field name", B.STANDARD_FIELDS + ["custom..."], key="pt_field")
            if fname == "custom...":
                fname = c1.text_input("Custom field name", key="pt_custom")
            default_t = "money" if ss.get("clicked_is_money") else B.default_type(fname)
            ftype = c2.selectbox("Type", B.FIELD_TYPES,
                                 index=B.FIELD_TYPES.index(default_t), key="pt_type")
            if c3.button("Add / update", use_container_width=True):
                add_field(fname, ss["clicked_anchor"], ftype,
                          ss.get("clicked_gap"), ss.get("clicked_nth"),
                          ss.get("clicked_below"))
                st.rerun()

# =====================================================================
# METHOD: PICK (dropdowns)
# =====================================================================
elif method == "pick":
    st.subheader("Pick the label for each field")
    labels = B.field_candidates(words)
    opts = [f"{d['anchor']}   →   {d['value'][:30]}" for d in labels]
    c1, c2, c3 = st.columns([2, 2, 1])
    fname = c1.selectbox("Field name", B.STANDARD_FIELDS + ["custom..."], key="pk_field")
    if fname == "custom...":
        fname = c1.text_input("Custom field name", key="pk_custom")
    choice = c2.selectbox("Detected label", opts, key="pk_label") if opts else None
    ftype = c3.selectbox("Type", B.FIELD_TYPES,
                         index=B.FIELD_TYPES.index(B.default_type(fname)), key="pk_type")
    if st.button("Add / update field") and choice and fname:
        chosen = labels[opts.index(choice)]
        default_t = "money" if chosen.get("is_money") else ftype
        add_field(fname, chosen["anchor"], default_t if chosen.get("is_money") else ftype,
                  chosen.get("gap_hint"), chosen.get("nth"))
        st.rerun()

# ---------- fields collected so far (Point / Pick) ----------
if method in ("point", "pick"):
    if ss.fields:
        st.write("**Fields added:**")
        for i, f in enumerate(list(ss.fields)):
            cc = st.columns([5, 1])
            extra = f"  ·  #{f['nth']}" if f.get("nth") else ""
            if f.get("below"):
                extra += "  ·  value below label"
            cc[0].write(f"`{f['name']}`  ←  \"{f['anchor']}\"  ·  {f['type']}{extra}")
            if cc[1].button("remove", key=f"rm{i}"):
                ss.fields.pop(i); st.rerun()

        with st.expander("Line items (optional)"):
            has_li = st.checkbox("This invoice has a line-item table")
            if not has_li:
                ss.line_items_cfg = None
            else:
                li_mode = st.radio("How is the table laid out?",
                                   ["Multi-column table — click each column (recommended)",
                                    "Simple table — match header words"],
                                   key="li_mode")
                ha = st.text_input("A word in the table's HEADER row", "Description", key="li_ha")
                ea = st.text_input("A word where the table STOPS (e.g. Grand Total, Subtotal)",
                                   "Grand Total", key="li_ea")

                if li_mode.startswith("Simple"):
                    cols_raw = st.text_area(
                        "Columns — one per line:  name | header word on invoice | text/number/money",
                        "description | Description | text\nquantity | Qty | number\n"
                        "rate | Rate | money\namount | Total | money", key="li_simple")
                    cols = []
                    for line in cols_raw.splitlines():
                        parts = [p.strip() for p in line.split("|")]
                        if len(parts) == 3:
                            cols.append({"name": parts[0], "header": parts[1], "type": parts[2]})
                    ss.line_items_cfg = {"header_anchor": ha, "end_anchor": ea, "columns": cols}

                else:
                    # ---- click each column on a data row ----
                    st.caption("Click on ONE value in each numeric column (Qty, Rate, Taxable, "
                               "GST %, CGST, SGST, Total). Description is captured automatically. "
                               "Then name each column below.")
                    if not HAVE_CLICK:
                        st.warning("Click component not installed.")
                    else:
                        xs = [c["x0"] for c in ss.get("li_columns", [])]
                        prev = B.render_column_markers(page["image"], page["scale"], xs)
                        lc = streamlit_image_coordinates(prev, width=560, key="liclick")
                        if lc and lc.get("width"):
                            xp = lc["x"] * page["width"] / lc["width"]
                            yp = lc["y"] * page["height"] / lc["height"]
                            w = B.point_to_word(words, xp, yp)
                            if w:
                                ss["li_pending_x0"] = round(w["x0"], 1)
                                ss["li_pending_val"] = w["text"]
                        if ss.get("li_pending_x0") is not None:
                            cc = st.columns([2, 2, 1])
                            cn = cc[0].text_input("Column name (e.g. gst_pct, cgst, total)",
                                                  key="li_cname")
                            ct = cc[1].selectbox("Type", B.FIELD_TYPES, index=3, key="li_ctype")
                            if cc[2].button("Add column", key="li_addcol"):
                                cols = ss.get("li_columns", [])
                                cols.append({"name": cn or f"col{len(cols)+1}",
                                             "type": ct, "x0": ss["li_pending_x0"]})
                                ss["li_columns"] = cols
                                ss["li_pending_x0"] = None
                                st.rerun()

                    if ss.get("li_columns"):
                        st.write("**Columns captured (left → right):**")
                        for i, c in enumerate(sorted(ss.li_columns, key=lambda c: c["x0"])):
                            r = st.columns([5, 1])
                            r[0].write(f"`{c['name']}`  ·  {c['type']}  ·  x={c['x0']}")
                            if r[1].button("remove", key=f"lic_rm{i}"):
                                ss.li_columns = [x for x in ss.li_columns if x is not c]
                                st.rerun()
                        names = [c["name"] for c in sorted(ss.li_columns, key=lambda c: c["x0"])]
                        d1, d2 = st.columns(2)
                        tax_col = d1.selectbox("Which column is the pre-tax value? (for Subtotal)",
                                               ["(none)"] + names, key="li_taxcol")
                        tot_col = d2.selectbox("Which column is the line Total? (for Total)",
                                               ["(none)"] + names, key="li_totcol")
                        cols = B.line_item_columns_from_clicks(ss.li_columns)
                        cfg = {"header_anchor": ha, "end_anchor": ea, "row_tol": 6, "columns": cols}
                        derive = {}
                        if tot_col != "(none)":
                            derive["total"] = {"sum": tot_col}
                        if tax_col != "(none)":
                            derive["subtotal"] = {"sum": tax_col}
                        if tax_col != "(none)" and tot_col != "(none)":
                            derive["tax"] = {"diff": ["total", "subtotal"]}
                        if derive:
                            cfg["derive_totals"] = derive
                        ss.line_items_cfg = cfg

        # auto-build the YAML so nothing is forgotten
        keyword = vendor_name.split()[0] if vendor_name else ""
        d = B.build_template_dict(vendor_name, keyword, ss.fields, ss.line_items_cfg)
        ss.draft_yaml = B.to_yaml(d)
    else:
        st.caption("Add at least one field above to build the template.")

# =====================================================================
# SHARED: edit / test / save
# =====================================================================
st.divider()
st.subheader("Template (editable)")
ss.draft_yaml = st.text_area("Review or hand-tweak before saving", value=ss.draft_yaml, height=300)

ct, cs = st.columns(2)
if ct.button("🔍  Test on this invoice", use_container_width=True, disabled=not ss.draft_yaml):
    try:
        tpl = yaml.safe_load(ss.draft_yaml)
        inv = B.preview_extract(ss.sample_path, tpl)
        st.write("**Extracted header fields:**")
        st.json({"invoice_number": inv.invoice_number, "invoice_date": inv.invoice_date,
                 "subtotal": inv.subtotal, "tax": inv.tax, "total": inv.total, **inv.extra})
        if inv.line_items:
            st.write("**Line items:**")
            st.dataframe([{k.replace("_", " ").title(): v for k, v in li.cols.items()}
                          for li in inv.line_items], hide_index=True, use_container_width=True)
        empty = [k for k, v in {"invoice_number": inv.invoice_number,
                                "total": inv.total}.items() if v in (None, "")]
        if empty:
            st.warning(f"These came back empty: {', '.join(empty)}. "
                       f"Re-click those fields or check the labels.")
        else:
            st.success("Looks good!" if inv.validation_ok else
                       "Extracted — but totals didn't fully reconcile; double-check the amounts.")
    except Exception as e:
        st.error(f"Test failed: {e}")

if cs.button("💾  Save template", type="primary", use_container_width=True,
             disabled=not (ss.draft_yaml and vendor_name)):
    try:
        vid = B.slugify(vendor_name)
        B.save_template(vid, ss.draft_yaml)
        st.success(f"Saved as templates/{vid}.yaml. Refresh the browser (F5); "
                   f"the vendor now appears on the main page.")
    except Exception as e:
        st.error(f"Could not save: {e}")
