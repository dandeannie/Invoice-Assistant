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

from extractor import (extract_generic, validate, to_excel, reconcile, apply_rules,
                       load_rules, check_duplicates, append_history, file_hash,
                       to_json, to_quickbooks_csv, to_tally_xml)
from extractor.builder import LLM_PRESETS

from extractor.ui import apply_theme, hero
from extractor.security import (check_upload, safe_filename, log_event,
                                load_settings, mask_key, is_local_provider)

st.set_page_config(page_title="Extract Any Invoice", page_icon="✨", layout="wide")
apply_theme()
hero("✨ Extract Any Invoice", "No template needed. Works on invoices, bills, and receipts from any vendor.", "#1B4F86")

ss = st.session_state

# ---------------- AI provider setup ----------------
_sec = load_settings()
if not _sec.get("allow_cloud_ai", True):
    st.warning("🔒 **Offline mode is on** (Security & Logs): cloud AI providers are "
               "blocked. Use a local model such as Ollama, or re-enable cloud AI.")
if _sec.get("redact_before_ai"):
    st.info("🛡️ Personal data (emails, phone, bank/card numbers) will be redacted "
            "before anything is sent to a cloud model.")

with st.expander("① AI setup (one time)", expanded=not ss.get("gen_ready")):
    prov_name = st.selectbox("AI provider", list(LLM_PRESETS.keys()), key="gen_prov")
    preset = LLM_PRESETS[prov_name]
    env_key = preset.get("key_env")
    default_key = os.environ.get(env_key, "") if env_key else ""
    # When the provider changes, load THAT provider's default model/key so a model
    # name from a previous provider can't be sent (a common "invalid model ID" cause).
    if ss.get("_gen_prov_last") != prov_name:
        ss["gen_model"] = preset.get("model", "")
        ss["gen_key"] = default_key
        ss["gen_base"] = preset.get("base_url") or ""
        ss["_gen_prov_last"] = prov_name
    col1, col2 = st.columns(2)
    api_key = col1.text_input("API key", type="password", key="gen_key",
                              help="Not needed for a local model (Ollama).")
    model = col2.text_input("Model", key="gen_model",
                            help="Must be a model ID your provider/account offers.")
    base_url = preset.get("base_url")
    # Local servers (Ollama/vLLM) and Custom endpoints get an editable URL box so the
    # server host/port — e.g. a vLLM instance used for testing — can be pointed anywhere.
    if prov_name.startswith(("Custom", "Local")) or base_url == "":
        base_url = st.text_input("Base URL (OpenAI-compatible endpoint)", key="gen_base",
                                 help="Point this at your local model server, e.g. "
                                      "vLLM: http://localhost:8000/v1 · "
                                      "Ollama: http://localhost:11434/v1")
    st.caption(f"Example model IDs — Anthropic: `claude-sonnet-5` · OpenAI: `gpt-4o` · "
               f"Gemini: `gemini-2.5-flash` · Groq: `llama-3.3-70b-versatile`. "
               f"You can type any model your account has access to.")
    if st.button("Save AI setup"):
        ss.gen_ready = True
        ss.gen_cfg = {"provider": preset["provider"], "model": model.strip(),
                      "base_url": base_url, "api_key": api_key.strip()}
        log_event("ai_configured",
                  f"provider={prov_name} model={model.strip()} key={mask_key(api_key)}")
        st.success(f"Ready to use {prov_name} with model '{model.strip()}'.")

# ---------------- upload & extract ----------------
st.subheader("② Upload invoices")
uploads = st.file_uploader("Drop one or more PDF invoices (any format)",
                           type=["pdf"], accept_multiple_files=True)

if uploads and st.button("Extract", type="primary", use_container_width=True):
    if not ss.get("gen_cfg"):
        st.error("Please complete the AI setup above first.")
    else:
        cfg = ss.gen_cfg
        invoices, errors = [], []
        prog = st.progress(0.0, text="Starting…")
        for i, up in enumerate(uploads, start=1):
            prog.progress(i / len(uploads), text=f"Reading {up.name} …")
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
                        # FIX 10: skip reconciliation for scanned invoices — pdfplumber returns
                        # empty text for OCR-processed PDFs, causing false REVIEW flags
                    except Exception:
                        pass
                apply_rules(inv, load_rules())
                invoices.append(inv)
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                if "model" in low and ("invalid" in low or "not found" in low or "does not exist" in low):
                    msg += ("  →  The Model ID isn't valid for this provider/account. "
                            "Open '① AI setup' and set a model you have access to "
                            "(e.g. Anthropic: claude-sonnet-5, OpenAI: gpt-4o).")
                elif "api key" in low or "authentication" in low or "401" in low or "unauthorized" in low:
                    msg += "  →  Check your API key in '① AI setup'."
                elif "connect" in low or "connection" in low:
                    msg += "  →  Couldn't reach the provider. If using a local model, make sure it's running."
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
    st.warning("⚠️ " + err)

if invoices:
    st.subheader("③ Results")
    dup_n = sum(1 for i in invoices if i.duplicate_of or i.duplicate_note)
    rule_n = sum(1 for i in invoices if i.rule_failures)
    ocr_count = sum(1 for i in invoices if getattr(i, "ocr_used", False))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Extracted", len(invoices))
    c2.metric("OCR Triggered", ocr_count)
    c3.metric("Rule Failures", rule_n)
    c4.metric("Duplicates", dup_n)

    if ocr_count > 0:
        st.info(f"🔍 **{ocr_count} invoice(s)** were processed using OCR fallback engine (`rapidocr-onnxruntime`).")

    if dup_n:
        st.error(f"🔁 {dup_n} possible duplicate invoice(s) — check before paying.")
        for i in invoices:
            if i.duplicate_note:
                st.caption(f"• **{i.source_file}**: {i.duplicate_note}")
    if rule_n:
        st.warning(f"📋 {rule_n} invoice(s) failed a business rule.")
        for i in invoices:
            for f in i.rule_failures:
                st.caption(f"• **{i.source_file}**: {f}")
    inv_rows = []
    for inv in invoices:
        row = {"File": inv.source_file, "Vendor": inv.vendor,
               "Invoice #": inv.invoice_number, "Date": inv.invoice_date,
               "Subtotal": inv.subtotal, "Tax": inv.tax, "Total": inv.total,
               **{k.replace("_", " ").title(): v for k, v in inv.extra.items()},
               "OK": "✅" if inv.validation_ok else "⚠️"}
        inv_rows.append(row)
    st.dataframe(inv_rows, hide_index=True, use_container_width=True)

    for inv in invoices:
        if not inv.validation_ok and inv.validation_notes:
            st.caption(f"⚠️ {inv.source_file}: {inv.validation_notes}")

    # line items with a per-invoice TOTAL row
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
        st.write("**Line items**")
        st.dataframe(line_rows, hide_index=True, use_container_width=True)

    recon = [inv for inv in invoices if inv.reconciliation]
    if recon:
        st.write("**Reconciliation vs original PDF**")
        st.dataframe([{
            "File": inv.source_file,
            "Status": "✅ OK" if inv.reconciliation.get("status") == "OK" else "⚠️ REVIEW",
            "Printed total": inv.reconciliation.get("printed_total"),
            "Extracted total": inv.reconciliation.get("extracted_total"),
            "Printed subtotal": inv.reconciliation.get("printed_subtotal"),
            "Extracted subtotal": inv.reconciliation.get("extracted_subtotal"),
            "Line-items sum": inv.reconciliation.get("line_items_sum"),
            "# lines": inv.reconciliation.get("n_line_items"),
            "Notes": inv.reconciliation.get("notes"),
        } for inv in recon], hide_index=True, use_container_width=True)

    with tempfile.TemporaryDirectory() as d:  # FIX 12: removed duplicate inline import — uses top-level tempfile
        xp = os.path.join(d, "invoices.xlsx"); to_excel(invoices, xp)
        tp = os.path.join(d, "tally_import.xml"); to_tally_xml(invoices, tp)
        qp = os.path.join(d, "bills.csv"); to_quickbooks_csv(invoices, qp)
        jp = os.path.join(d, "invoices.json"); to_json(invoices, jp)
        xb = Path(xp).read_bytes()
        tb = Path(tp).read_bytes()
        qb = Path(qp).read_bytes()
        jb = Path(jp).read_bytes()
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button("⬇ Excel", xb, "extracted_invoices.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       type="primary", use_container_width=True)
    e2.download_button("⬇ Tally XML", tb, "tally_import.xml", "application/xml",
                       use_container_width=True)
    e3.download_button("⬇ Accounting CSV", qb, "bills.csv", "text/csv",
                       use_container_width=True)
    e4.download_button("⬇ JSON", jb, "invoices.json", "application/json",
                       use_container_width=True)

    if st.button("✅ Mark as processed (adds to duplicate history)"):
        append_history(invoices)
        st.success("Recorded — these will be flagged if uploaded again.")

st.divider()
st.caption(
    "AI-powered extraction with automatic OCR for scanned invoices. "
    "Always spot-check flagged (⚠️) invoices — AI can occasionally "
    "misread unusual layouts."
)  # FIX 9: updated caption — OCR is now automatic, old text was misleading
