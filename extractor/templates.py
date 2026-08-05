"""
Loads vendor templates (one YAML file per vendor) from the templates/ folder.
A template is just a description of WHERE each field lives on that vendor's invoice.
Adding a new vendor = adding one YAML file. No code changes needed.
"""
from __future__ import annotations
import os
import yaml

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def list_vendors() -> list[dict]:
    """Return a list of available templates: [{'id': 'acme', 'name': 'ACME Corporation'}, ...]"""
    vendors = []
    if not os.path.isdir(TEMPLATES_DIR):
        return vendors
    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        if fname.endswith((".yaml", ".yml")):
            path = os.path.join(TEMPLATES_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            vendors.append({
                "id": os.path.splitext(fname)[0],
                "name": data.get("vendor", fname),
            })
    return vendors


def load_template(vendor_id: str) -> dict:
    """Load a single vendor template by its file id (filename without extension)."""
    for ext in (".yaml", ".yml"):
        path = os.path.join(TEMPLATES_DIR, vendor_id + ext)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise FileNotFoundError(f"No template found for vendor id '{vendor_id}' in {TEMPLATES_DIR}")
