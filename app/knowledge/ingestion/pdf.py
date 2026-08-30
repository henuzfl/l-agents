"""Stable ingestion entrypoint for PDF processing."""

from app.knowledge.pdf_processing import PdfProcessingResult, process_pdf

__all__ = ["PdfProcessingResult", "process_pdf"]
