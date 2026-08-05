# Running Fully On-Premise

Short version: **the tool is already on-prem.** Template extraction, reconciliation,
business rules, duplicate detection and every export run with no network at all — this
was verified by loading the library with the AI SDKs blocked and all network sockets
disabled, then extracting invoices end to end successfully.

AI is an **optional add-on** for one feature (Extract Any Invoice), not the engine.

---

## 1. How a PDF is read without any AI

A native PDF is not a picture — it is a document format that stores **text objects with
coordinates**. Every character is already in the file with its exact position, font and
size. Nothing has to be "recognised".

The pipeline is ordinary deterministic code:

1. **`pdfplumber`** reads each word plus its bounding box (`x0, top, x1, bottom`).
2. Words are **grouped into lines** by their vertical position.
3. **Header fields** are found by anchor: locate the label ("Invoice No"), then read the
   value to its right — or below it, or left of it, per the template.
4. **Line items** are read by column geometry: each column is an x-range, so every word
   is assigned to a column by its horizontal centre. Wrapped description lines are
   merged into the nearest amount row.
5. **Types are converted** (dates normalised, currency symbols and commas stripped).
6. **Totals are derived and checked** — subtotal + tax = total, lines add up, and the
   figures are reconciled against the totals printed on the page.

That is it: coordinate geometry plus rules. No model, no training, no inference — which
is exactly why it is fast (milliseconds), free, repeatable, auditable, and offline.

**The trade-off:** it needs a small template per vendor, because the rules must know
where that vendor prints things. Once built, every future invoice from that vendor is
automatic.

---

## 2. Do you need a local LLM like Qwen?

**Only if you want template-free extraction.** Three valid deployments:

### Option A — No AI at all (simplest, fully deterministic)
Build a template per vendor. The builder's **Point** (click values on the page) and
**Pick** (choose labels from dropdowns) methods are 100% offline — only the "AI" method
in the builder needs a model. Install `requirements-onprem.txt` and you're done.

Best when: you have a manageable set of recurring suppliers (typically 10–50 covers the
large majority of AP volume). Zero cost, zero inference, complete auditability.

### Option B — Local open-source LLM (Qwen via Ollama)
Adds the "any invoice, no template" mode while keeping everything inside your network.

```bash
# 1. install Ollama on the machine or an internal server (https://ollama.com)
# 2. pull a model
ollama pull qwen2.5:14b-instruct        # good accuracy/size balance
# or: qwen2.5:7b-instruct (lighter), qwen2.5:32b-instruct (better, needs more VRAM)
# 3. the client library (talks to localhost, not the cloud)
pip install openai
```
In the app: **Extract Any Invoice → AI setup → provider "Local (Ollama)"**, base URL
`http://localhost:11434/v1`, model `qwen2.5:14b-instruct`, no API key. Then on
**Security & Logs**, switch **off** "Allow cloud AI providers" — cloud calls are then
blocked at the call site, so nothing can leave even by mistake.

Hardware: a 7B model runs on CPU (slowly) or ~6 GB VRAM; 14B wants ~10–12 GB VRAM;
32B ~24 GB. Invoices are small documents, so throughput is rarely the constraint.

Qwen 2.5 Instruct is a sound choice for this task (strong structured/JSON output).
Mistral-Nemo, Llama 3.1 8B and Phi-4 also work. Whatever you pick, the tool's
reconciliation still cross-checks the model's numbers against the printed PDF.

### Option C — Hybrid (recommended)
Templates for your recurring suppliers (fast, free, deterministic) + a local Qwen for
the long tail of one-off vendors. Best coverage, still fully on-prem.

---

## 3. Changes needed for a locked-down deployment

Most of this is configuration, not code:

1. **Install from `requirements-onprem.txt`** (omits `anthropic`/`openai`). On an air-gapped
   machine, download wheels on a connected machine first:
   `pip download -r requirements-onprem.txt -d wheels/`, copy the folder, then
   `pip install --no-index --find-links=wheels -r requirements-onprem.txt`.
2. **Turn off cloud AI**: Security & Logs → uncheck *Allow cloud AI providers*. This is
   enforced in code, not just hidden in the UI.
3. **Keep the UI local**: Streamlit binds to `localhost` by default. Do not add
   `--server.address 0.0.0.0` unless you put authentication in front of it.
4. **Firewall**: no egress required. If you use Ollama, allow only `localhost:11434`
   (or your internal Ollama host).
5. **Encrypt the folder** (BitLocker/FileVault) — invoices are commercial data.
6. **Back up** `templates/`, `rules.yaml`, `security.yaml` and `output/` — that's your
   configuration and audit trail.
7. **Audit log**: already local (`output/audit_log.csv`). Keep it enabled and review
   periodically.

---

## 4. Scanned (image) invoices

This is the one genuine gap, and it is unrelated to AI. A scanned PDF has no text layer,
so there is nothing to read. You need OCR **locally**:

- **Tesseract** (open source) + `pytesseract`, or **PaddleOCR** for tougher scans.
- OCR converts the image to text + coordinates, which then feeds the *same* engine —
  templates, rules and reconciliation work unchanged.

This is a natural extension; it needs installing an OCR engine on the machine, and
accuracy on poor scans will always be lower than on native PDFs.
