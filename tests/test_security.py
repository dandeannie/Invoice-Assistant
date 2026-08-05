"""Tests for security module in extractor/security.py."""
import extractor.security as sec


def test_scrub_openai_key():
    text = "Key is sk-abc123456789xyz"
    scrubbed = sec._scrub(text)
    assert "[REDACTED]" in scrubbed
    assert "sk-abc123456789xyz" not in scrubbed


def test_scrub_gemini_key():
    gemini_key = "AIza" + "A" * 35
    text = f"Gemini key: {gemini_key}"
    scrubbed = sec._scrub(text)
    assert "[REDACTED]" in scrubbed
    assert gemini_key not in scrubbed


def test_scrub_bearer_token():
    token = "Bearer eyJhbGciOiJSUzI1NiJ9"
    text = f"Authorization: {token}"
    scrubbed = sec._scrub(text)
    assert "[REDACTED]" in scrubbed
    assert token not in scrubbed


def test_scrub_clean_text():
    text = "Invoice total is 118.00 USD for ACME Corp"
    assert sec._scrub(text) == text


def test_scrub_multiple_secrets():
    sk_key = "sk-1234567890abcdef"
    bearer = "Bearer token12345"
    text = f"Key: {sk_key} and Token: {bearer}"
    scrubbed = sec._scrub(text)
    assert scrubbed.count("[REDACTED]") == 2
    assert sk_key not in scrubbed
    assert bearer not in scrubbed


def test_load_settings_cache_identity():
    """Confirm consecutive load_settings() calls return the cached dict object."""
    sec._settings_cache = None  # Reset cache before testing
    s1 = sec.load_settings()
    s2 = sec.load_settings()
    assert s1 is s2


def test_log_event_writes_to_csv(tmp_path, monkeypatch):
    audit_file = tmp_path / "audit_log.csv"
    monkeypatch.setattr(sec, "AUDIT_PATH", str(audit_file))
    monkeypatch.setattr(sec, "OUTPUT_DIR", str(tmp_path))

    sec.log_event("test_event", "test detail", outcome="ok")

    assert audit_file.exists()
    content = audit_file.read_text(encoding="utf-8")
    assert "test_event" in content
    assert "test detail" in content
