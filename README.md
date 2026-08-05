# 🧾 Invoice Extractor

![CI](https://github.com/jainmokshit1-byte/invoice-extractor/actions/workflows/ci.yml/badge.svg?branch=diya)

Extract structured data from **any PDF invoice** — digital or scanned — using OCR and an LLM. Export results directly to Excel with one click.

---

## What It Does

- Accepts any PDF invoice (no template needed)
- Auto-detects **scanned vs digital** PDFs
- Scanned invoices are processed through **RapidOCR** before LLM extraction
- Extracts: vendor, invoice number, date, line items, subtotal, taxes, total
- Exports to **.xlsx** (Excel)
- Works **on-premise / offline** — no data leaves your machine except for the LLM API call

---

## Tech Stack

| Component | Library |
|-----------|---------|
| UI | Streamlit |
| PDF text extraction | pdfplumber |
| PDF → image rendering (for OCR) | PyMuPDF (`fitz`) |
| OCR engine | rapidocr-onnxruntime (ONNX, offline) |
| LLM providers | Anthropic Claude, OpenAI, Gemini, Groq, Mistral, Ollama |
| Data models | pydantic |
| Excel export | openpyxl |
| Python | **3.12** (required — see below) |

---

## ⚠️ Python Version Requirement

> **You must use Python 3.12.** Python 3.13 and 3.14 are NOT supported.

`rapidocr-onnxruntime` has no pre-built wheel for Python 3.13 or 3.14. Installing on those versions will fail or require compiling NumPy from source (which requires a C compiler).

Download Python 3.12 from: https://www.python.org/downloads/release/python-3120/  
✅ Check **"Add Python to PATH"** during installation.

---

## Prerequisites

- Python 3.12 installed (see above)
- An API key from one of:
  - [Anthropic](https://console.anthropic.com/) (Claude)
  - [OpenAI](https://platform.openai.com/)
  - [Google AI Studio](https://aistudio.google.com/) (Gemini)
  - Or any OpenAI-compatible endpoint (Groq, Mistral, Ollama, vLLM, etc.)

---

## Setup — Windows

### Step 1 — Clone the repository

```powershell
git clone <repo-url>
cd invoice-extractor
```

### Step 2 — Allow PowerShell scripts (one time only)

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Step 3 — Create a Python 3.12 virtual environment

```powershell
py -3.12 -m venv venv312
```

### Step 4 — Activate and install dependencies

```powershell
.\venv312\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 5 — Run the app

```powershell
python -m streamlit run app.py
```

**Or simply double-click:** `Start Invoice Tool.bat`

---

## Setup — macOS / Linux

### Step 1 — Clone the repository

```bash
git clone <repo-url>
cd invoice-extractor
```

### Step 2 — Create a Python 3.12 virtual environment

```bash
python3.12 -m venv venv312
```

### Step 3 — Activate and install dependencies

```bash
source venv312/bin/activate
pip install -r requirements.txt
```

### Step 4 — Run the app

```bash
python -m streamlit run app.py
```

---

## Configuration

### AI Provider (required)

On first launch, expand **① AI Setup (one time)** in the sidebar and enter:
- Your API key
- Provider (Anthropic, OpenAI, Gemini, Groq, Mistral, Ollama)
- Model name (e.g. `claude-3-5-sonnet-20241022`, `gpt-4o`, `gemini-2.0-flash`)

For local Ollama, set Base URL to `http://localhost:11434/v1`.

### OCR Settings (`security.yaml`)

```yaml
ocr_enabled: true        # Set false to disable OCR entirely
ocr_dpi: 300             # Rendering DPI for scanned pages (150–300 recommended)
ocr_min_chars: 50        # Chars per page below which OCR is triggered
ocr_min_confidence: 0.5  # Minimum OCR confidence score to accept a text box (FIX 5: was 0.45, corrected to match security.yaml)
```

---

## How It Works

```
Upload PDF
    │
    ├─ Digital PDF? ──→ pdfplumber extracts native text
    │
    └─ Scanned PDF? ──→ PyMuPDF renders page to image
                              │
                              └─ RapidOCR extracts text (offline ONNX)
                                        │
                                        └─ LLM parses structured fields
                                                  │
                                                  └─ Export to Excel
```

1. Upload one or more PDF invoices via the Streamlit UI
2. The tool auto-detects whether each PDF is scanned or digital
3. Scanned pages are rendered at 300 DPI and processed by RapidOCR
4. Extracted text is sent to the LLM for structured field extraction
5. Results appear in a table; click **Download Excel** to export

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `running scripts is disabled` | PowerShell execution policy | Run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| `No module named rapidocr_onnxruntime` | Wrong Python version | Must use `py -3.12 -m venv venv312` — not Python 3.13/3.14 |
| `No text could be extracted` | OCR disabled or config missing | Check `security.yaml` has `ocr_enabled: true` |
| `OCR Triggered: 0` for a scanned invoice | venv312 not active | Always activate `.\venv312\Scripts\Activate.ps1` before running |
| `AssertionError` from PyMuPDF | `get_text("layout")` on scanned page | Fixed in current version — update your code |
| API call failed | Wrong key / model name / base URL | Re-check Step ① AI Setup in the UI |

---

## .gitignore

Make sure your `.gitignore` includes at minimum:

```
venv312/
__pycache__/
*.pyc
.env
*.xlsx
streamlit_log.txt
```

---

## Project Structure

```
invoice-extractor/
├── app.py                    # Streamlit entry point
├── pages/
│   └── 1_Extract_Any_Invoice.py
├── extractor/
│   ├── engine.py             # Core LLM extraction logic
│   ├── generic.py            # Template-free extraction
│   ├── ocr.py                # RapidOCR integration
│   ├── pdf_utils.py          # pdfplumber text extraction
│   ├── models.py             # Pydantic data models
│   ├── validate.py           # Business rule validation
│   ├── reconcile.py          # Line-item reconciliation
│   ├── security.py           # Security guardrails
│   └── export.py             # Excel export
├── rules.yaml                # Business validation rules
├── security.yaml             # OCR and security settings
├── requirements.txt
├── Start Invoice Tool.bat    # Windows one-click launcher
└── README.md
```

---

## License

MIT
