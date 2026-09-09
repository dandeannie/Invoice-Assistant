"""
Security & Logs — privacy controls for the AI features, upload limits, and the
audit trail of everything the tool has done.
"""
import os
import streamlit as st

from extractor.security import (load_settings, save_settings, read_audit, clear_audit,
                                redact_text, AUDIT_PATH)
import importlib
import extractor.ui
importlib.reload(extractor.ui)

from extractor.ui import (apply_theme, top_nav_bar, hero_card, section_header,
                          metric_card, status_pill, ICON_SHIELD)

st.set_page_config(page_title="Security & Logs - Invoice AI", page_icon=":material/security:", layout="wide")
apply_theme()
top_nav_bar("SECURITY & AUDIT TRAIL", search_placeholder="Search security controls...", badge_text="Zero-Telemetry")

s = load_settings()
rows = read_audit(400)
cloud_status = "ENABLED" if s.get("allow_cloud_ai", True) else "BLOCKED"
redact_status = "ACTIVE" if s.get("redact_before_ai", False) else "OFF"

hero_card(
    title="Security & Audit Controls",
    subtitle="Enterprise privacy guardrails, PII redaction, and local tamper-evident audit logging.",
    meta_tags=["Air-Gapped Ready", "PII Redactor", "Zero External Telemetry"],
    stat_items=[
        (cloud_status, "Cloud AI Policy"),
        (redact_status, "PII Redaction"),
        (f"{s.get('max_file_mb', 25)} MB", "Max Upload Limit"),
        (str(len(rows)), "Audit Events Logged")
    ],
    desc="Template extraction runs completely offline. Security policies govern AI requests, sanitize file uploads, and maintain strict traceability without leaking credentials.",
    color="#BAE6FD",
    icon=ICON_SHIELD
)

# ---------------- AI privacy ----------------
section_header("01", "AI Privacy & Redaction Guardrails")
st.caption("Template-based parsing is strictly local. These settings apply whenever an LLM engine is invoked.")

c1, c2 = st.columns(2)
allow_cloud = c1.checkbox(
    "Allow cloud AI providers",
    value=bool(s.get("allow_cloud_ai", True)),
    help="Turn OFF to block every provider except local runners (Ollama / vLLM). No data leaves your machine."
)
redact = c2.checkbox(
    "Redact personal/banking data before cloud transmission",
    value=bool(s.get("redact_before_ai", False)),
    help="Strips emails, phone numbers, bank accounts, and card numbers. Invoice amounts, dates, and item lines remain intact."
)

if not allow_cloud:
    st.info("Offline Enforcement: Cloud AI requests are hard-blocked. Only local host addresses are permitted.", icon=":material/lock:")

max_chars = st.slider(
    "Maximum characters transmitted per document",
    5000, 200000, int(s.get("max_ai_chars", 60000)), step=5000,
    help="Sets an upper bound on token consumption and limits data payload size."
)

with st.expander("Test PII Redaction Engine", icon=":material/science:"):
    sample = st.text_area(
        "Input text with simulated sensitive information",
        "Contact: accounts.pay@benchmarkcs.in  Ph: +91 44 6690 1200\n"
        "Bank A/c: 50200098765432  IFSC: HDFC0002211  Total Due: 37,94,980.00",
        height=100
    )
    if sample:
        out, n = redact_text(sample)
        st.code(out, language="text")
        st.caption(f"{n} sensitive identifier(s) neutralized. Financial totals and structural labels preserved.")

st.divider()

# ---------------- upload limits ----------------
section_header("02", "Upload & File Safety")
u1, u2 = st.columns(2)
max_mb = u1.number_input("Maximum allowed file size (MB)", 1, 200, int(s.get("max_file_mb", 25)))
max_batch = u2.number_input("Maximum files permitted per batch", 1, 1000, int(s.get("max_batch_files", 100)))
st.caption("All incoming documents are verified for magic byte PDF signatures (%PDF) and file paths are sanitized against directory traversal.")

st.divider()

# ---------------- audit log ----------------
section_header("03", "Audit Trail & Activity Log")
a1, a2 = st.columns(2)
audit_on = a1.checkbox("Record security events in audit log", value=bool(s.get("audit_log_enabled", True)))
max_rows = a2.number_input("Maximum log entries retained", 1000, 200000, int(s.get("audit_log_max_rows", 20000)), step=1000)

if st.button("Save Security Policy", icon=":material/save:", type="primary"):
    save_settings({
        "allow_cloud_ai": allow_cloud,
        "redact_before_ai": redact,
        "log_ai_calls": True,
        "max_file_mb": int(max_mb),
        "max_batch_files": int(max_batch),
        "max_ai_chars": int(max_chars),
        "audit_log_enabled": audit_on,
        "audit_log_max_rows": int(max_rows)
    })
    st.success("Security policy updated and cached.", icon=":material/check:")
    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

if not rows:
    st.info("No audit events recorded yet.")
else:
    st.markdown(f"**Showing {len(rows)} latest audit records** (newest first). *Secrets and API keys are strictly scrubbed.*")
    ev = sorted({r.get("event", "") for r in rows if r.get("event")})
    pick = st.multiselect("Filter by event category", ev, default=[])
    shown = [r for r in rows if not pick or r.get("event") in pick]
    st.dataframe(shown, hide_index=True, use_container_width=True, height=320)

    d1, d2 = st.columns(2)
    # Safe CSV generation that avoids FileNotFoundError
    csv_bytes = b""
    if os.path.exists(AUDIT_PATH):
        try:
            with open(AUDIT_PATH, "rb") as f:
                csv_bytes = f.read()
        except Exception:
            csv_bytes = b""
    if not csv_bytes and rows:
        import io, csv
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
        csv_bytes = buf.getvalue().encode("utf-8")

    d1.download_button(
        "Download Audit Log (CSV)",
        data=csv_bytes,
        file_name="audit_log.csv",
        mime="text/csv",
        icon=":material/download:",
        use_container_width=True,
        disabled=len(csv_bytes) == 0
    )
    if d2.button("Clear Audit Log", icon=":material/delete:", use_container_width=True):
        clear_audit()
        st.rerun()

st.divider()
with st.expander("Enterprise Defense-in-Depth Architecture", icon=":material/verified_user:"):
    st.markdown("""
- **Air-Gapped Core Engine:** Rule-based template extraction operates entirely offline with zero network connectivity.
- **Strict Key Isolation:** API credentials are never written to disk or logged, and exist solely in the browser session memory.
- **Prompt Injection Fencing:** Document text sent to LLMs is quarantined inside `<INVOICE_DATA>` tags with explicit anti-hijacking directives.
- **Arithmetic Reconciliation:** Extracted financial figures are validated against mathematical sums to catch model hallucinations.
- **Path-Traversal Protection:** File creation and downloads are hard-jailed inside designated output directories.
""")
