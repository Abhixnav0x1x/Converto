# Converto — PDF to TXT (text-only)

Converto is a terminal CLI that extracts all text from a PDF and writes it to a single `.txt` file.

- No page limit
- Text-only extraction (images are ignored by design)
- Optional OCR fallback (Tesseract) for scanned PDFs
- Custom output name or directory
- Safe by default (won’t overwrite unless `--overwrite` is passed)

---

## Installation

Requirements:

- Python 3.8+
- A terminal (Windows PowerShell, cmd, Bash, etc.)

Set up a virtual environment and install dependencies:

```powershell
# From the project directory
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If you plan to use OCR for scanned PDFs, install Tesseract OCR (see “Tesseract on Windows” below).

### Install via pip (local project)

You can install the CLI from this folder, which exposes the `converto` command:

```powershell
# From the project directory (with .venv activated, optional)
pip install .

# Or include optional OCR dependencies
pip install .[ocr]
```

Now run:

```powershell
converto path\to\input.pdf
```

### Install directly from GitHub (after you push)

Replace `your-username` and repo name if different:

```powershell
pip install "git+https://github.com/your-username/converto.git#egg=converto"

# With OCR extras
pip install "git+https://github.com/your-username/converto.git#egg=converto[ocr]"
```

---

## Quick Start

Basic conversion (outputs `input.txt` next to the PDF):

```powershell
python converto.py path\to\input.pdf
```

Custom output name or path:

```powershell
# Set a specific filename
python converto.py path\to\input.pdf -o output_name.txt

# Place the output inside a directory (uses input filename with .txt)
python converto.py path\to\input.pdf -o path\to\output\directory

# Provide a full path and it will ensure .txt extension
python converto.py path\to\input.pdf -o C:\\temp\\my_notes
```

Overwrite an existing file:

```powershell
python converto.py input.pdf -o output.txt --overwrite
```

Password-protected PDF:

```powershell
python converto.py secret.pdf --password "YourPassword"
```

---

## CLI Usage

```text
Converto — Convert a PDF to a single TXT file (text-only)

positional arguments:
  input_pdf                Path to the input PDF file

options:
  -o, --output PATH        Path (or filename) for the output TXT. Defaults to
                           "<input_name>.txt" in the same folder.
  --overwrite              Allow overwriting the output file if it already exists.
  --password STR           Password for encrypted PDFs (if applicable).
  --ocr {never,auto,always}
                           OCR mode: 'never' (default) only uses embedded text;
                           'auto' falls back to OCR if no text is found;
                           'always' forces OCR for all pages. Requires Tesseract.
  --ocr-lang STR           Tesseract language(s), e.g., 'eng', 'eng+hin'.
  --tesseract-path PATH    Full path to tesseract executable if not in PATH
                           (e.g., C:\\Program Files\\Tesseract-OCR\\tesseract.exe).
```

Output rules:

- Default output: same folder and name as the input, with `.txt` extension.
- If `-o` is a directory, output will be `<input_stem>.txt` inside that directory.
- If `-o` is a filename without `.txt`, it will be saved with `.txt` appended.
- Will not overwrite unless `--overwrite` is provided.

Line endings: on Windows, output uses CRLF; on other OSes, LF.

---

## OCR (for scanned PDFs)

If your PDF is scanned and has no embedded text, enable OCR. Install Tesseract first.

Examples:

```powershell
# Try embedded text first; if nothing is found, fall back to OCR
python converto.py input.pdf --ocr auto

# Force OCR for all pages
python converto.py input.pdf --ocr always --ocr-lang eng

# If Tesseract is not on PATH, specify its full path
python converto.py input.pdf --ocr always --tesseract-path "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
```

OCR options:

- `--ocr`: `never` (default), `auto`, or `always`.
- `--ocr-lang`: Tesseract language code(s), e.g., `eng`, `eng+hin`.
- `--tesseract-path`: Full path to `tesseract.exe` if it isn’t on your PATH.

---

## Tesseract on Windows

1. Download the installer (UB Mannheim builds recommended for extra languages):
   - https://github.com/UB-Mannheim/tesseract/wiki
2. Install it. The default path is typically `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`.
3. Either add the installation directory to your PATH or pass `--tesseract-path` to Converto.

---

## Troubleshooting

- "Input PDF not found": Check the path and filename. Ensure the file exists.
- "Input path is not a file": Verify you passed a file, not a directory.
- "Input file must be a .pdf": The input must have a `.pdf` extension.
- "Output directory does not exist": Create the folder or specify a valid path.
- "Output file already exists": Use `--overwrite` to replace it or choose a different name.
- "Failed to extract text": The file might be encrypted or malformed. Try opening it with a viewer to confirm.
- "OCR dependencies missing": Install Python deps (`pip install -r requirements.txt`) and Tesseract as above.

---

## Contributing

Issues and PRs are welcome. If you have feature ideas (batch mode, PDF range selection, etc.), open an issue to discuss.

