from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber
import pytesseract

logger = logging.getLogger(__name__)


class PdfExtractionError(Exception):
    """Raised when PDF extraction fails."""


class PdfExtractor:
    def __init__(self, ocr_threshold: int = 100) -> None:
        self.ocr_threshold = ocr_threshold

    def extract_text(self, pdf_path: Path) -> str:
        """
        Extract text from a PDF file.
        Falls back to OCR if the extracted text is too short.
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    full_text += text + "\n"

            full_text = full_text.strip()

            if len(full_text) < self.ocr_threshold:
                logger.info(
                    "Extracted text too short (%d chars). Starting OCR for %s",
                    len(full_text),
                    pdf_path.name,
                )
                return self._perform_ocr(pdf_path)

            return full_text

        except Exception as exc:
            logger.error("Failed to extract text from %s: %s", pdf_path, exc)
            raise PdfExtractionError(f"Extraction failed: {exc}") from exc

    def _perform_ocr(self, pdf_path: Path) -> str:
        """
        Perform OCR on the PDF pages.
        Note: Requires Tesseract-OCR and pdf2image (or similar) or use pdfplumber's image features.
        """
        try:
            # Simple approach: use pdfplumber to get images of pages
            ocr_text = ""
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    # Convert page to image (higher resolution for better OCR)
                    img = page.to_image(resolution=300).original
                    text = pytesseract.image_to_string(img)
                    ocr_text += text + "\n"

            return ocr_text.strip()
        except Exception as exc:
            logger.error("OCR failed for %s: %s", pdf_path, exc)
            raise PdfExtractionError(f"OCR failed: {exc}") from exc
