"""
OCR module for scanned/image-based PDFs using PyMuPDF (fitz) and RapidOCR (ONNX).
Maintains lazy initialization and handles mixed native/scanned PDF documents page-by-page.
"""
from __future__ import annotations
import gc
import logging
import os
import re
import traceback
from typing import Tuple

import fitz  # PyMuPDF
import numpy as np

from .pdf_utils import _pdf_text
from .security import log_event  # FIX 3: needed for audit trail on OCR confidence fallback

logger = logging.getLogger(__name__)

_OCR_ENGINE = None


def get_ocr_engine():
    """Lazy-load singleton instance of RapidOCR."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
            logger.info("RapidOCR engine initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize RapidOCR engine: {e}")
            raise RuntimeError(
                f"Failed to load OCR engine. Ensure ONNX runtime dependencies are installed. Error: {e}"
            ) from e
    return _OCR_ENGINE


def _strip_page_markers(text: str) -> str:
    """Strip page section markers, control chars, and non-alphanumeric noise to evaluate true content length."""
    if not text:
        return ""
    clean = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    clean = re.sub(r'---\s*PAGE\s*\d+\s*---', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'===\s*.*?\s*===', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'[^a-zA-Z0-9]', '', clean)
    return clean


def is_scanned(pdf_path: str, min_chars_per_page: int = 50) -> bool:
    """
    Detect whether a PDF is overall scanned/image-only by analyzing cumulative native alphanumeric text.
    Sums ALL pages completely without early exiting.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
        if doc.is_encrypted:
            doc.close()  # FIX 6: prevent file handle leak on encrypted PDFs
            return False

        page_count = len(doc)
        if page_count == 0:
            doc.close()
            return True

        total_chars = 0
        for page in doc:
            text = page.get_text("text") or ""
            total_chars += len(_strip_page_markers(text))

        doc.close()
        return total_chars < (min_chars_per_page * page_count)
    except Exception as e:
        logger.warning(f"Error inspecting PDF structure for {pdf_path}: {e}")
        return True


def ocr_pdf(
    pdf_path: str,
    dpi: int = 300,
    min_confidence: float = 0.5,
    min_chars_per_page: int = 50,
    force_ocr: bool = False
) -> Tuple[str, bool, float]:
    """
    Process PDF page-by-page. Pages with sufficient native text use native text,
    while pages below min_chars_per_page (or when force_ocr is True) are rendered to image and processed with OCR.
    
    Returns:
        tuple: (full_extracted_text, ocr_used: bool, ocr_confidence_avg: float)
    """
    engine = None
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    page_texts = []
    total_conf = 0.0
    valid_box_count = 0
    ocr_used = False

    try:
        for p_idx, page in enumerate(doc, start=1):
            native_txt = page.get_text("text") or ""
            clean_len = len(_strip_page_markers(native_txt))

            if not force_ocr and clean_len >= min_chars_per_page:
                page_lines = [f"--- PAGE {p_idx} ---", "=== NATIVE PAGE TEXT ===", native_txt]
                page_texts.append("\n".join(page_lines))
            else:
                ocr_used = True
                if engine is None:
                    engine = get_ocr_engine()

                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img_rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                pix = None

                # RapidOCR works with RGB numpy arrays (not BGR).
                # Pass RGB directly — the ONNX model handles its own normalisation.
                result, elapse = engine(img_rgb)
                del img_rgb

                # FIX 1: Removed DIAGNOSTIC block — was emitting raw OCR text (PII risk) at WARNING level on every page.
                ocr_lines = []
                if result:
                    for box, text, confidence in result:
                        conf_val = float(confidence)
                        txt_str = text.strip()
                        if not txt_str:
                            continue
                        if conf_val >= min_confidence:
                            ocr_lines.append(txt_str)
                            total_conf += conf_val
                            valid_box_count += 1
                        elif conf_val >= 0.4:
                            # FIX 5: low-confidence marker (0.4 <= conf < min_confidence)
                            ocr_lines.append(f"[?{txt_str}?]")
                            total_conf += conf_val
                            valid_box_count += 1

                if not ocr_lines and result:
                    # Confidence filter removed everything — log min/max so we know the range
                    all_confs = [float(c) for _, _, c in result]
                    logger.warning(
                        f"[OCR DIAG] Page {p_idx}: all {len(result)} boxes filtered out by "
                        f"min_confidence={min_confidence}. Actual range: "
                        f"min={min(all_confs):.3f} max={max(all_confs):.3f}. "
                        "Consider lowering ocr_min_confidence in security.yaml."
                    )
                    # FIX 3: audit trail + warning so the fallback is never silent
                    log_event("ocr_low_confidence",
                              f"page {p_idx}: all boxes below threshold {min_confidence}, "
                              "using emergency fallback (conf > 0.1)")
                    logger.warning("OCR low-confidence fallback triggered on page %s", p_idx)
                    # Emergency fallback: accept anything with conf > 0.1 to avoid empty output
                    for box, text, confidence in result:
                        conf_val = float(confidence)
                        txt_str = text.strip()
                        if not txt_str or conf_val <= 0.1:
                            continue
                        if conf_val >= min_confidence:
                            ocr_lines.append(txt_str)
                        elif conf_val >= 0.4:
                            ocr_lines.append(f"[?{txt_str}?]")
                        else:
                            # FIX 5: very low-confidence marker (conf < 0.4)
                            ocr_lines.append(f"[??{txt_str}??]")
                        total_conf += conf_val
                        valid_box_count += 1

                page_lines = [f"--- PAGE {p_idx} ---", "=== OCR TEXT ==="] + ocr_lines
                page_texts.append("\n".join(page_lines))

    finally:
        doc.close()
        gc.collect()

    avg_conf = (total_conf / valid_box_count) if valid_box_count > 0 else (1.0 if not ocr_used else 0.0)
    full_text = "\n\n".join(page_texts)
    return full_text, ocr_used, round(avg_conf, 4)


def extract_text_with_ocr_fallback(
    pdf_path: str,
    dpi: int = 300,
    min_chars: int = 50,
    min_confidence: float = 0.5,
    force_ocr: bool = False,
    pdf_doc=None
) -> Tuple[str, bool, float]:
    """
    Primary Entry Point for PDF Text Extraction with Per-Page OCR Fallback.
    Automatically detects scanned documents and invokes RapidOCR.
    """
    from .security import load_settings
    sec = load_settings()

    if not sec.get("ocr_enabled", True):
        native_text = _pdf_text(pdf_path, pdf_doc=pdf_doc)
        return native_text, False, 1.0

    scanned = force_ocr or is_scanned(pdf_path, min_chars_per_page=min_chars)

    try:
        text, ocr_used, avg_conf = ocr_pdf(
            pdf_path, dpi=dpi, min_confidence=min_confidence,
            min_chars_per_page=min_chars, force_ocr=scanned
        )
        # Strip structural markers before checking whether we actually got content.
        # Without this, marker-only output ("--- PAGE 1 ---\n=== OCR TEXT ===")
        # looks non-empty but produces nothing useful for the LLM.
        _clean = re.sub(r'---\s*PAGE\s*\d+\s*---', '', text, flags=re.IGNORECASE)
        _clean = re.sub(r'===\s*\S.*?\s*===', '', _clean, flags=re.IGNORECASE)
        _clean = _clean.strip()
        if _clean:
            return text, ocr_used, avg_conf
        logger.warning(f"[OCR] ocr_pdf returned no usable text for {pdf_path}; falling back to pdfplumber.")
    except Exception as e:
        logger.error(
            f"OCR execution failed on {pdf_path}: {type(e).__name__}: {e}\n"
            f"{traceback.format_exc()}"
        )

    native_text = _pdf_text(pdf_path, pdf_doc=pdf_doc)
    return native_text, False, 1.0
