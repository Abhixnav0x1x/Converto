#!/usr/bin/env python3
"""
Converto - PDF to TXT Converter (text-only)

A terminal-based tool that converts all text content from a PDF into a single .txt file.
- No page limit
- Excludes images by design (text-only extraction)
- Allows a custom output name
- Safe by default (won't overwrite unless --overwrite is passed)

Usage (examples):
  python converto.py input.pdf
  python converto.py input.pdf -o output_name.txt
  python converto.py input.pdf -o output_name.txt --overwrite
  python converto.py input.pdf --password "yourPassword"
  
  # Enable OCR (requires Tesseract installed) if text extraction is empty
  python converto.py input.pdf --ocr auto
  
  # Force OCR for all pages
  python converto.py input.pdf --ocr always --ocr-lang eng

Dependencies: see requirements.txt
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Optional
from typing import List, Tuple
import concurrent.futures as cf

# We use pdfminer.six to extract text only (images are not extracted)
try:
    from pdfminer.high_level import extract_text
except Exception as e:  # pragma: no cover
    print("Error: pdfminer.six is required. Install with: pip install -r requirements.txt", file=sys.stderr)
    raise


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="Converto",
        description="Convert a PDF to a single TXT file (text-only, no images)."
    )
    parser.add_argument(
        "input_pdf",
        type=str,
        help="Path to the input PDF file"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Path (or filename) for the output TXT. Defaults to '<input_name>.txt' in the same folder."
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting the output file if it already exists."
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Password for encrypted PDFs (if applicable)."
    )
    parser.add_argument(
        "--ocr",
        choices=["never", "auto", "always"],
        default="never",
        help=(
            "OCR mode: 'never' (default) only uses embedded text; 'auto' falls back to OCR if no text is found; "
            "'always' forces OCR for all pages. Requires Tesseract installed."
        ),
    )
    parser.add_argument(
        "--ocr-lang",
        type=str,
        default="eng",
        help="Tesseract language(s), e.g., 'eng', 'eng+hin'."
    )
    parser.add_argument(
        "--tesseract-path",
        type=str,
        default=None,
        help="Full path to tesseract executable if not in PATH (e.g., C:\\Program Files\\Tesseract-OCR\\tesseract.exe)."
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=1,
        help="Number of parallel workers to use. Pages are split across workers and results concatenated in order."
    )
    return parser.parse_args(argv)


def validate_paths(input_pdf: Path, output_txt: Path, allow_overwrite: bool) -> None:
    # Validate input
    if not input_pdf.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_pdf}")
    if not input_pdf.is_file():
        raise ValueError(f"Input path is not a file: {input_pdf}")
    if input_pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input file must be a .pdf: {input_pdf}")

    # Validate output folder
    out_dir = output_txt.parent
    if not out_dir.exists():
        raise FileNotFoundError(f"Output directory does not exist: {out_dir}")
    if output_txt.exists() and not allow_overwrite:
        raise FileExistsError(
            f"Output file already exists: {output_txt}. Use --overwrite to replace it."
        )


def determine_output_path(input_pdf: Path, output_opt: Optional[str]) -> Path:
    if output_opt is None or output_opt.strip() == "":
        # Same directory as input, with .txt extension
        return input_pdf.with_suffix(".txt")
    # If only a filename is provided, resolve it relative to current working directory
    output_path = Path(output_opt)
    if output_path.is_dir():
        # If a directory is provided, use input stem as filename within that directory
        return output_path.joinpath(input_pdf.stem + ".txt")
    # Else, user provided a file path
    if output_path.suffix.lower() != ".txt":
        output_path = output_path.with_suffix(".txt")
    return output_path


def extract_text_pdfminer(input_pdf: Path, password: Optional[str]) -> str:
    """
    Extract all text from the input PDF using pdfminer.six (text layer only).
    Returns a string (may be empty if PDF has no text layer).
    """
    try:
        return extract_text(str(input_pdf), password=password) or ""
    except Exception as e:
        msg = f"Failed to extract text via pdfminer from: {input_pdf}\nReason: {e}"
        raise RuntimeError(msg) from e


def _count_pages_pdfminer(input_pdf: Path, password: Optional[str]) -> int:
    """Return total number of pages using pdfminer."""
    try:
        from pdfminer.pdfparser import PDFParser  # type: ignore
        from pdfminer.pdfdocument import PDFDocument  # type: ignore
        from pdfminer.pdfpage import PDFPage  # type: ignore
        with open(input_pdf, "rb") as f:
            parser = PDFParser(f)
            doc = PDFDocument(parser, password)
            pages = list(PDFPage.create_pages(doc))
            return len(pages)
    except Exception as e:
        raise RuntimeError(f"Failed to count pages with pdfminer: {e}") from e


def _extract_text_pdfminer_pages(args: Tuple[str, Optional[str], List[int]]) -> Tuple[int, str]:
    """
    Worker: extract text for given page indices using pdfminer.
    Returns (start_page_index, text)
    """
    pdf_path, password, page_indices = args
    try:
        txt = extract_text(pdf_path, password=password, page_numbers=page_indices) or ""
        start_idx = page_indices[0] if page_indices else 0
        return (start_idx, txt)
    except Exception as e:
        raise RuntimeError(f"Failed to extract text (pdfminer) for pages {page_indices[:3]}...: {e}") from e


def _split_indices(total: int, parts: int) -> List[List[int]]:
    """Split range(0, total) into `parts` nearly equal lists of page indices."""
    parts = max(1, min(parts, total if total > 0 else 1))
    base, extra = divmod(total, parts)
    chunks: List[List[int]] = []
    start = 0
    for i in range(parts):
        count = base + (1 if i < extra else 0)
        end = start + count
        if count > 0:
            chunks.append(list(range(start, end)))
        start = end
    return chunks


def extract_text_pdfminer_parallel(input_pdf: Path, password: Optional[str], workers: int) -> str:
    """Parallel pdfminer text extraction by page, concatenated in order."""
    total_pages = _count_pages_pdfminer(input_pdf, password)
    if total_pages <= 0:
        return ""
    if workers <= 1 or total_pages == 1:
        return extract_text_pdfminer(input_pdf, password)

    chunks = _split_indices(total_pages, workers)
    tasks: List[Tuple[str, Optional[str], List[int]]] = [
        (str(input_pdf), password, page_indices) for page_indices in chunks
    ]
    results: List[Tuple[int, str]] = []
    with cf.ProcessPoolExecutor(max_workers=len(chunks)) as ex:
        futures = [ex.submit(_extract_text_pdfminer_pages, task) for task in tasks]
        try:
            for fut in cf.as_completed(futures):
                results.append(fut.result())
        except KeyboardInterrupt:
            ex.shutdown(cancel_futures=True)
            raise
    # Sort by starting page index and join
    results.sort(key=lambda t: t[0])
    return "".join(text for _, text in results)


def ocr_pdf_with_tesseract(input_pdf: Path, lang: str, tesseract_path: Optional[str]) -> str:
    """
    Render PDF pages via pypdfium2 and OCR each page using Tesseract (pytesseract).
    Returns concatenated text across all pages.
    """
    try:
        # Lazy imports so non-OCR runs don't require these packages
        import pypdfium2 as pdfium  # type: ignore
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "OCR dependencies missing. Install with: pip install -r requirements.txt"
        ) from e

    if tesseract_path:
        # Configure pytesseract to use a custom tesseract executable
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    text_chunks = []
    try:
        pdf = pdfium.PdfDocument(str(input_pdf))
    except Exception as e:
        raise RuntimeError(f"Failed to open PDF for OCR: {input_pdf}\nReason: {e}") from e

    # Render each page at a reasonable DPI for OCR quality/performance
    dpi = 200
    scale = dpi / 72  # 72 DPI is PDF default
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            bitmap = page.render(scale=scale).to_pil()
            # Convert to grayscale to help OCR
            img = bitmap.convert("L")
            try:
                page_text = pytesseract.image_to_string(img, lang=lang)
            except Exception as e:
                raise RuntimeError(f"Tesseract OCR failed on page {i+1}: {e}") from e
            # Add simple page separator
            text_chunks.append(page_text.rstrip())
    finally:
        # ensure resources freed
        try:
            pdf.close()  # type: ignore[attr-defined]
        except Exception:
            pass

    return "\n\n".join(text_chunks) + "\n"


def _ocr_pages_worker(args: Tuple[str, List[int], str, Optional[str]]) -> Tuple[int, str]:
    """Worker to OCR a set of pages with pytesseract via pypdfium2.
    Returns (start_page_index, text)
    """
    pdf_path, page_indices, lang, tesseract_path = args
    try:
        import pypdfium2 as pdfium  # type: ignore
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        pdf = pdfium.PdfDocument(pdf_path)
        dpi = 200
        scale = dpi / 72
        chunks: List[str] = []
        for i in page_indices:
            page = pdf[i]
            bitmap = page.render(scale=scale).to_pil()
            img = bitmap.convert("L")
            page_text = pytesseract.image_to_string(img, lang=lang)
            chunks.append(page_text.rstrip())
        try:
            pdf.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        start_idx = page_indices[0] if page_indices else 0
        return (start_idx, "\n\n".join(chunks))
    except Exception as e:
        raise RuntimeError(f"OCR worker failed for pages {page_indices[:3]}...: {e}") from e


def ocr_pdf_with_tesseract_parallel(input_pdf: Path, lang: str, tesseract_path: Optional[str], workers: int) -> str:
    """Parallel OCR using pypdfium2+pytesseract, concatenated in page order."""
    try:
        import pypdfium2 as pdfium  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "OCR dependencies missing. Install with: pip install -r requirements.txt"
        ) from e

    # Count pages using pdfium for reliability in OCR mode
    try:
        pdf = pdfium.PdfDocument(str(input_pdf))
        total_pages = len(pdf)
        try:
            pdf.close()  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception as e:
        raise RuntimeError(f"Failed to open PDF for OCR: {input_pdf}\nReason: {e}") from e

    if total_pages <= 0:
        return ""
    if workers <= 1 or total_pages == 1:
        return ocr_pdf_with_tesseract(input_pdf, lang, tesseract_path)

    chunks = _split_indices(total_pages, workers)
    tasks: List[Tuple[str, List[int], str, Optional[str]]] = [
        (str(input_pdf), page_indices, lang, tesseract_path) for page_indices in chunks
    ]
    results: List[Tuple[int, str]] = []
    with cf.ProcessPoolExecutor(max_workers=len(chunks)) as ex:
        futures = [ex.submit(_ocr_pages_worker, task) for task in tasks]
        try:
            for fut in cf.as_completed(futures):
                results.append(fut.result())
        except KeyboardInterrupt:
            ex.shutdown(cancel_futures=True)
            raise
    results.sort(key=lambda t: t[0])
    return "\n\n".join(text for _, text in results) + "\n"


def convert_pdf_to_txt(
    input_pdf: Path,
    output_txt: Path,
    password: Optional[str],
    ocr_mode: str,
    ocr_lang: str,
    tesseract_path: Optional[str],
    workers: int,
) -> None:
    """
    Extract text from the input PDF according to the chosen strategy and write it to output_txt.
    - pdfminer (embedded text)
    - optional Tesseract OCR via pypdfium2 rendering
    """
    text: str = ""
    if ocr_mode == "always":
        if workers and workers > 1:
            text = ocr_pdf_with_tesseract_parallel(input_pdf, lang=ocr_lang, tesseract_path=tesseract_path, workers=workers)
        else:
            text = ocr_pdf_with_tesseract(input_pdf, lang=ocr_lang, tesseract_path=tesseract_path)
    else:
        if workers and workers > 1:
            text = extract_text_pdfminer_parallel(input_pdf, password=password, workers=workers)
        else:
            text = extract_text_pdfminer(input_pdf, password=password)
        if ocr_mode == "auto" and (not text or text.strip() == ""):
            # Fallback to OCR if no text layer found
            if workers and workers > 1:
                text = ocr_pdf_with_tesseract_parallel(input_pdf, lang=ocr_lang, tesseract_path=tesseract_path, workers=workers)
            else:
                text = ocr_pdf_with_tesseract(input_pdf, lang=ocr_lang, tesseract_path=tesseract_path)

    # Normalize line endings to Windows-friendly CRLF when on Windows; otherwise default to \n
    newline = "\r\n" if os.name == "nt" else "\n"
    # Ensure the parent directory exists (validated earlier) and write the file
    try:
        with open(output_txt, "w", encoding="utf-8", newline=newline) as f:
            f.write(text or "")
    except Exception as e:
        raise RuntimeError(f"Failed to write output file: {output_txt}\nReason: {e}") from e



def main(argv=None) -> int:
    args = parse_args(argv)

    input_pdf = Path(args.input_pdf).expanduser().resolve()
    output_txt = determine_output_path(input_pdf, args.output)

    try:
        validate_paths(input_pdf, output_txt, args.overwrite)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    try:
        convert_pdf_to_txt(
            input_pdf,
            output_txt,
            args.password,
            args.ocr,
            args.ocr_lang,
            args.tesseract_path,
            args.workers,
        )
    except KeyboardInterrupt:
        print("Interrupted by user (Ctrl+C).", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    print(f"Success: Wrote text to {output_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
