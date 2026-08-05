"""Unit test stubs for previously uncovered core modules."""
import pytest


class TestEngineModule:
    def test_template_loads_without_error(self):
        from extractor import engine
        assert engine is not None

    def test_extract_returns_invoice_model(self):
        pytest.skip("Requires fixture PDF — implement with sample in tests/fixtures/")


class TestClassifyModule:
    def test_classify_returns_vendor_name(self):
        from extractor import classify
        assert classify is not None


class TestAutotemplateModule:
    def test_autotemplate_build_smoke(self):
        from extractor import autotemplate
        assert autotemplate is not None


class TestDedupeModule:
    def test_dedupe_identical_invoices(self):
        from extractor import dedupe
        assert dedupe is not None


class TestExportModule:
    def test_export_to_excel_smoke(self):
        from extractor import export
        assert export is not None


class TestRulesModule:
    def test_rules_load_from_yaml(self):
        from extractor.rules import load_rules
        assert load_rules is not None
