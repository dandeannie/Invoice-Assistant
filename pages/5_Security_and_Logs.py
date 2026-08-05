"""
Security & Logs — privacy controls for the AI features, upload limits, and the
audit trail of everything the tool has done.
"""
import streamlit as st

from extractor.security import (load_settings, save_settings, read_audit, clear_audit,
                                redact_text, log_event, AUDIT_PATH)
from extractor.ui import apply_theme, hero

st.set_page_config(page_title="Security & Logs", page_icon="🔒", layout="wide")
apply_theme()
hero("🔒 Security & Logs",
     "Control what leaves this machine, cap what the AI can be sent, and review "
     "an audit trail of every action.", "#6B2D5C")

s = load_settings()

# ---------------- AI privacy ----------------
st.subheader("AI privacy controls")
st.caption("Template extraction is always fully offline. These settings apply to the "
           "AI (Extract Any Invoice) features only.")

c1, c2 = st.columns(2)
allow_cloud = c1.checkbox(
    "Allow cloud AI providers", value=bool(s.get("allow_cloud_ai", True)),
    help="Turn OFF to block every provider except a local model (Ollama). "
         "Nothing then leaves your machine.")
redact = c2.checkbox(
    "Redact personal data before sending to a cloud model",
    value=bool(s.get("redact_before_ai", False)),
    help="Removes emails, phone numbers, bank/card/IBAN numbers. Invoice amounts, "
         "dates and item descriptions are untouched.")

if not allow_cloud:
    st.success("🔒 Offline mode: cloud AI is blocked. Only a local model can be used.")

max_chars = st.slider("Maximum characters sent to the AI per invoice", 5000, 200000,
                      int(s.get("max_ai_chars", 60000)), step=5000,
                      help="Caps cost and limits how much of a document can ever leave.")

with st.expander("Preview redaction on sample text"):
    sample = st.text_area("Sample", "Contact: procurement@benchmarkcs.in  Ph: +91 44 6690 1200\n"
                                    "A/c No: 50200098765432  IFSC: HDFC0002211\nTotal: 37,94,980.00",
                          height=110)
    if sample:
        out, n = redact_text(sample)
        st.code(out)
        st.caption(f"{n} identifier(s) would be removed. Amounts are preserved.")

st.divider()

# ---------------- upload limits ----------------
st.subheader("Upload limits")
u1, u2 = st.columns(2)
max_mb = u1.number_input("Maximum file size (MB)", 1, 200, int(s.get("max_file_mb", 25)))
max_batch = u2.number_input("Maximum files per batch", 1, 1000, int(s.get("max_batch_files", 100)))
st.caption("Uploads are also checked for a real PDF signature, and file names are "
           "sanitised so nothing can be written outside the output folder.")

st.divider()

# ---------------- audit log ----------------
st.subheader("Audit trail")
a1, a2 = st.columns(2)
audit_on = a1.checkbox("Keep an audit log", value=bool(s.get("audit_log_enabled", True)))
max_rows = a2.number_input("Maximum rows kept", 1000, 200000,
                           int(s.get("audit_log_max_rows", 20000)), step=1000)

if st.button("💾 Save security settings", type="primary"):
    save_settings({"allow_cloud_ai": allow_cloud, "redact_before_ai": redact,
                   "log_ai_calls": True, "max_file_mb": int(max_mb),
                   "max_batch_files": int(max_batch), "max_ai_chars": int(max_chars),
                   "audit_log_enabled": audit_on, "audit_log_max_rows": int(max_rows)})
    st.success("Security settings saved.")

rows = read_audit(400)
if not rows:
    st.info("No activity recorded yet.")
else:
    st.caption(f"Most recent {len(rows)} events (newest first). Secrets are never logged.")
    ev = sorted({r.get("event", "") for r in rows})
    pick = st.multiselect("Filter by event", ev, default=[])
    shown = [r for r in rows if not pick or r.get("event") in pick]
    st.dataframe(shown, hide_index=True, use_container_width=True, height=340)
    d1, d2 = st.columns(2)
    with open(AUDIT_PATH, "rb") as f:
        d1.download_button("⬇ Download audit log (CSV)", f, "audit_log.csv", "text/csv",
                           use_container_width=True)
    if d2.button("Clear audit log", use_container_width=True):
        clear_audit()
        st.rerun()

st.divider()
with st.expander("What this tool does to keep your data safe"):
    st.markdown("""
- **Templates run fully offline.** No network access is needed or used.
- **API keys are never written to disk** by the tool, never logged, and shown masked.
  They live only in the browser session.
- **Untrusted document text is fenced.** A PDF could contain text designed to hijack an
  AI model ("ignore previous instructions..."). Document text is wrapped and explicitly
  labelled as data, and the model's reply must be strict JSON.
- **Every AI answer is verified.** Extracted totals are reconciled against the figures
  printed on the PDF, so a hallucinated or manipulated number is flagged, not trusted.
- **Uploads are validated** (real-PDF signature, size caps) and file names sanitised.
- **Writes stay inside the output folder** — path traversal is refused.
- **The audit log records actions, never content** — no invoice text, no keys.
- **Nothing is sent anywhere except the AI provider you choose**, and only when you use
  an AI feature. There is no telemetry.
""")
