from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.pdf.extractor import PdfExtractionError, PdfExtractor


def test_extract_text_direct(tmp_path: Path) -> None:
    # Create a dummy pdf path
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    # Mock pdfplumber
    with patch("pdfplumber.open") as mock_open:
        mock_pdf = mock_open.return_value.__enter__.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Statement details content"
        mock_pdf.pages = [mock_page]

        extractor = PdfExtractor(ocr_threshold=10)
        text = extractor.extract_text(pdf_path)

        assert text == "Statement details content"
        mock_page.extract_text.assert_called_once()


def test_extract_text_triggers_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    # Mock pdfplumber to return very little text
    with patch("pdfplumber.open") as mock_open, \
         patch("pytesseract.image_to_string") as mock_ocr:
        
        mock_pdf = mock_open.return_value.__enter__.return_value
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "too short"
        
        # Setup for OCR: to_image().original
        mock_page.to_image.return_value.original = "dummy_image"
        
        mock_pdf.pages = [mock_page]
        
        mock_ocr.return_value = "Text from OCR"

        extractor = PdfExtractor(ocr_threshold=50)
        text = extractor.extract_text(pdf_path)

        assert text == "Text from OCR"
        mock_ocr.assert_called_once_with("dummy_image")


def test_extract_text_error_handling(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    
    with patch("pdfplumber.open", side_effect=Exception("Corrupt PDF")):
        extractor = PdfExtractor()
        with pytest.raises(PdfExtractionError, match="Extraction failed"):
            extractor.extract_text(pdf_path)
