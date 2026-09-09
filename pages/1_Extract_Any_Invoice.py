"""
Extract Any Invoice — template-free extraction using AI. Upload any invoice/bill/
receipt PDF and get vendor, number, date, line items (multi-line descriptions joined),
quantities, all applicable taxes, subtotal and total — then download Excel.
"""
import os
from pathlib import Path
import tempfile
import traceback

import streamlit as st
import importlib
import extractor.ui
importlib.reload(extractor.ui)

from extractor import (extract_generic, validate, to_excel, reconcile, apply_rules,
                       load_rules, check_duplicates, append_history, file_hash,
                       to_json, to_quickbooks_csv, to_tally_xml)
from extractor.builder import LLM_PRESETS
from extractor.ui import (apply_theme, top_nav_bar, hero_card, section_header,
                          metric_card, analytics_sparkline_card, review_card, status_pill,
                          ICON_AI)
from extractor.security import (check_upload, safe_filename, log_event,
                                load_settings, mask_key, is_local_provider)

st.set_page_config(page_title="Extract Any Invoice - Invoice AI", page_icon=":material/auto_awesome:", layout="wide")
apply_theme()
top_nav_bar("AI GENERIC EXTRACTOR", search_placeholder="Extract arbitrary invoices without templates...", badge_text="Universal AI")

ss = st.session_state
_sec = load_settings()

active_model_desc = ss.get("gen_cfg", {}).get("model", "gpt-4o") if ss.get("gen_cfg") else "Not configured"
prov_name_display = ss.get("_gen_prov_last", "OpenAI")

hero_card(
    title="Extract Any Invoice",
    subtitle="Zero-template extraction driven by multi-modal LLMs and RapidOCR fallback.",
    meta_tags=["Universal Layout", "RapidOCR Auto-Detect", "Zero-Training Required"],
    stat_items=[
        (prov_name_display, "AI Provider"),
        ("Cloud Permitted" if _sec.get("allow_cloud_ai", True) else "Offline Only", "Privacy Lock"),
        ("Active" if _sec.get("redact_before_ai") else "Disabled", "PII Redaction"),
        ("RapidOCR ONNX", "Fallback OCR")
    ],
    desc="Process arbitrary invoices, international vendor receipts, and unstructured utility bills. Document data is quarantined inside anti-injection fences and verified against mathematical sums.",
    color="#F6C8FB",
    icon=ICON_AI
)

if not _sec.get("allow_cloud_ai", True):
    st.warning("**Offline mode enforced** (Security & Logs): Cloud providers are blocked. Point endpoint to local Ollama/vLLM.", icon=":material/lock:")
if _sec.get("redact_before_ai"):
    st.info("PII Guard Active: Personal and banking details will be sanitized before cloud submission.", icon=":material/shield:")

# ---------------- AI provider setup ----------------
with st.expander("Provider & Model Configuration", expanded=not ss.get("gen_ready"), icon=":material/settings:"):
    prov_name = st.selectbox("Select Provider Preset", list(LLM_PRESETS.keys()), key="gen_prov")
    preset = LLM_PRESETS[prov_name]
    env_key = preset.get("key_env")
    default_key = os.environ.get(env_key, "") if env_key else ""

    if ss.get("_gen_prov_last") != prov_name:
        ss["gen_model"] = preset.get("model", "")
        ss["gen_key"] = default_key
        ss["gen_base"] = preset.get("base_url") or ""
        ss["_gen_prov_last"] = prov_name

    col1, col2 = st.columns(2)
    api_key = col1.text_input("API Key / Bearer Token", type="password", key="gen_key",
                              help="Not required for local models (Ollama/vLLM).")
    model = col2.text_input("Model ID", key="gen_model",
                            help="E.g. gpt-4o, claude-sonnet-5, gemini-2.5-flash, llama-3.3-70b-versatile.")
    base_url = preset.get("base_url")
    if prov_name.startswith(("Custom", "Local")) or base_url == "":
        base_url = st.text_input("Endpoint Base URL (OpenAI-compatible)", key="gen_base",
                                 help="Local host endpoint, e.g. http://localhost:11434/v1 for Ollama.")

    if st.button("Save & Activate Model Preset", type="primary", use_container_width=True):
        ss.gen_ready = True
        ss.gen_cfg = {
            "provider": preset["provider"],
            "model": model.strip(),
            "base_url": base_url,
            "api_key": api_key.strip()
        }
        log_event("ai_configured", f"provider={prov_name} model={model.strip()} key={mask_key(api_key)}")
        st.success(f"Configured {prov_name} using model `{model.strip()}`.", icon=":material/check:")

st.divider()

# ---------------- upload & extract ----------------
section_header("01", "Upload Invoices / Bills (Any Layout)")
uploads = st.file_uploader(
    "Drop one or more PDF files",
    type=["pdf"],
    accept_multiple_files=True,
    help="Accepts native vector PDFs as well as scanned camera captures/images."
)

if uploads and st.button("Run AI Extraction Pipeline", icon=":material/play_arrow:", type="primary", use_container_width=True):
    if not ss.get("gen_cfg"):
        st.error("Please configure the AI provider settings above before extracting.")
    else:
        cfg = ss.gen_cfg
        invoices, errors = [], []
        prog = st.progress(0.0, text="Initializing extraction…")
        for i, up in enumerate(uploads, start=1):
            prog.progress(i / len(uploads), text=f"Processing {up.name} ({i}/{len(uploads)})…")
            tmp = None
            try:
                data = up.getbuffer().tobytes()
                ok_up, msg_up = check_upload(data, safe_filename(up.name))
                if not ok_up:
                    errors.append(msg_up)
                    log_event("upload_rejected", msg_up, outcome="rejected")
                    continue
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f:
                    f.write(data)
                    tmp = f.name
                inv = extract_generic(
                    tmp, api_key=cfg["api_key"], model=cfg["model"],
                    provider=cfg["provider"], base_url=cfg["base_url"])
                inv.source_file = up.name
                inv.extra["_file_hash"] = file_hash(tmp)
                if not getattr(inv, 'ocr_used', False):
                    try:
                        inv.reconciliation = reconcile(inv, tmp)
                    except Exception:
                        pass
                apply_rules(inv, load_rules())
                invoices.append(inv)
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                if "model" in low and ("invalid" in low or "not found" in low or "does not exist" in low):
                    msg += " → Model ID not found. Verify your provider model string."
                elif "api key" in low or "authentication" in low or "401" in low:
                    msg += " → Authentication failed. Verify API Key."
                elif "connect" in low or "connection" in low:
                    msg += " → Server unreachable. Ensure local AI runner is active."
                errors.append(f"{up.name}: {msg}")
            finally:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
        prog.empty()
        check_duplicates(invoices)
        ss.gen_results = invoices
        ss.gen_errors = errors

# ---------------- results ----------------
invoices = ss.get("gen_results") or []
for err in (ss.get("gen_errors") or []):
    st.warning(err, icon=":material/warning:")

if invoices:
    section_header("02", "Extraction Ledger & Audit Verification")
    dup_n = sum(1 for i in invoices if i.duplicate_of or i.duplicate_note)
    rule_n = sum(1 for i in invoices if i.rule_failures)
    ocr_count = sum(1 for i in invoices if getattr(i, "ocr_used", False))
    valid_count = sum(1 for i in invoices if i.validation_ok)
    acc_pct = round((valid_count / len(invoices)) * 100, 1) if invoices else 100.0

    r_col1, r_col2 = st.columns([1.5, 2.5])
    with r_col1:
        analytics_sparkline_card(
            title="Batch Precision",
            rating=f"{acc_pct}%",
            count_text=f"{len(invoices)} Invoices Processed",
            btn_text="AI Metrics",
            bg_color="#F6C8FB"
        )
    with r_col2:
        m1, m2, m3 = st.columns(3)
        with m1: metric_card("OCR Engaged", ocr_count, "#BAE6FD" if ocr_count else "#FFFFFF", subtext="Scanned Fallback")
        with m2: metric_card("Rule Violations", rule_n, "#F8CD53" if rule_n else "#FFFFFF", subtext="Compliance Flags")
        with m3: metric_card("Duplicates", dup_n, "#FFC6D9" if dup_n else "#FFFFFF", subtext="Repeated Invoices")

    if dup_n:
        st.error(f"Duplicate Alert: {dup_n} potential duplicate(s) detected in batch or history.", icon=":material/copy_all:")
        for i in invoices:
            if i.duplicate_note:
                st.caption(f"• **{i.source_file}**: {i.duplicate_note}")

    st.markdown("#### Document Header Summary")
    inv_rows = []
    for inv in invoices:
        row = {
            "File": inv.source_file,
            "Vendor": inv.vendor,
            "Invoice #": inv.invoice_number,
            "Date": inv.invoice_date,
            "Subtotal": inv.subtotal,
            "Tax": inv.tax,
            "Total": inv.total,
            **{k.replace("_", " ").title(): v for k, v in inv.extra.items() if not k.startswith("_")},
            "Audit": "PASS" if inv.validation_ok else "CHECK"
        }
        inv_rows.append(row)
    st.dataframe(inv_rows, hide_index=True, use_container_width=True)

    # Line Items Section
    line_rows = []
    for inv in invoices:
        for li in inv.line_items:
            r = {"File": inv.source_file, "Invoice #": inv.invoice_number}
            for k, v in li.cols.items():
                r[k.replace("_", " ").title()] = v
            line_rows.append(r)
        if inv.line_items:
            summable = set(inv.line_total_columns or [])
            sums = {}
            for li in inv.line_items:
                for k, v in li.cols.items():
                    if k in summable and isinstance(v, (int, float)):
                        sums[k] = round(sums.get(k, 0) + v, 2)
            tr = {"File": "", "Invoice #": inv.invoice_number}
            for k in inv.line_items[0].cols:
                tr[k.replace("_", " ").title()] = "TOTAL" if k == "description" else sums.get(k, "")
            line_rows.append(tr)

    if line_rows:
        st.markdown("#### Itemized Breakdown (Joined Multi-Line Items)")
        st.dataframe(line_rows, hide_index=True, use_container_width=True)

    recon = [inv for inv in invoices if inv.reconciliation]
    if recon:
        st.markdown("#### Optical Cross-Check (Reconciliation vs Raw PDF)")
        st.dataframe([{
            "File": inv.source_file,
            "Status": "OK" if inv.reconciliation.get("status") == "OK" else "REVIEW",
            "Printed Total": inv.reconciliation.get("printed_total"),
            "Extracted Total": inv.reconciliation.get("extracted_total"),
            "Line Items Sum": inv.reconciliation.get("line_items_sum"),
            "# Lines": inv.reconciliation.get("n_line_items"),
            "Notes": inv.reconciliation.get("notes"),
        } for inv in recon], hide_index=True, use_container_width=True)

    section_header("03", "One-Click Multi-Format Export Center")
    with tempfile.TemporaryDirectory() as d:
        xp = os.path.join(d, "invoices.xlsx"); to_excel(invoices, xp)
        tp = os.path.join(d, "tally_import.xml"); to_tally_xml(invoices, tp)
        qp = os.path.join(d, "bills.csv"); to_quickbooks_csv(invoices, qp)
        jp = os.path.join(d, "invoices.json"); to_json(invoices, jp)
        xb = Path(xp).read_bytes()
        tb = Path(tp).read_bytes()
        qb = Path(qp).read_bytes()
        jb = Path(jp).read_bytes()

    e1, e2, e3, e4 = st.columns(4)
    e1.download_button("Download Excel", xb, "extracted_invoices.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/download:", type="primary", use_container_width=True)
    e2.download_button("Tally XML", tb, "tally_import.xml", "application/xml",
                       icon=":material/download:", use_container_width=True)
    e3.download_button("QuickBooks CSV", qb, "bills.csv", "text/csv",
                       icon=":material/download:", use_container_width=True)
    e4.download_button("JSON Payload", jb, "invoices.json", "application/json",
                       icon=":material/download:", use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Commit to History (Enables Duplicate Protection)", icon=":material/check_circle:", use_container_width=False):
        append_history(invoices)
        st.success("Batch fingerprints committed to duplicate detection history.", icon=":material/check:")

st.divider()
st.caption("AI-powered extraction with automatic OCR fallback. Always review documents marked for review.")
