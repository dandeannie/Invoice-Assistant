"""Invoice extractor package."""
from .engine import extract_invoice
from .templates import list_vendors, load_template
from .validate import validate
from .export import to_excel, to_csv
from .models import Invoice, LineItem
from .generic import extract_generic, invoice_from_data
from .reconcile import reconcile
from .classify import detect_vendor, guess_vendor_name, pdf_text
from .rules import (apply_rules, load_rules, save_rules, load_all as load_all_rules,
                    save_all as save_all_rules, delete_vendor_rules, PRESETS as RULE_PRESETS,
                    DEFAULT_RULES)
from .dedupe import check_duplicates, append_history, load_history, file_hash, clear_history
from .exporters import to_json, to_quickbooks_csv, to_tally_xml
from .ocr import extract_text_with_ocr_fallback, ocr_pdf, is_scanned
from . import security, ui

__all__ = [
    "extract_invoice", "list_vendors", "load_template",
    "validate", "to_excel", "to_csv", "Invoice", "LineItem",
    "extract_generic", "invoice_from_data", "reconcile",
    "detect_vendor", "guess_vendor_name", "pdf_text",
    "apply_rules", "load_rules", "save_rules", "load_all_rules", "save_all_rules",
    "delete_vendor_rules", "RULE_PRESETS", "DEFAULT_RULES", "security", "ui",
    "check_duplicates", "append_history", "load_history", "file_hash", "clear_history",
    "to_json", "to_quickbooks_csv", "to_tally_xml",
    "extract_text_with_ocr_fallback", "ocr_pdf", "is_scanned",
]

