"""Pydantic models for the doc_ingest pipeline."""

from __future__ import annotations

from pydantic import BaseModel


# --- Step 1: extract_documents output ---


class TextSegment(BaseModel):
    type: str
    text: str


class ExtractedImage(BaseModel):
    path: str
    context: str


class DocumentExtraction(BaseModel):
    source_file: str
    text_segments: list[TextSegment]
    images: list[ExtractedImage]


class DocumentExtractionList(BaseModel):
    documents: list[DocumentExtraction]


# --- Step 2: describe_images output ---


class DescribedImage(BaseModel):
    path: str
    context: str = ""
    description: str


class DescribedImageList(BaseModel):
    images: list[DescribedImage]


# --- Step 3: assemble_content output ---


class AssembledDocument(BaseModel):
    source_file: str
    output_path: str
    content: str


class AssembledDocumentList(BaseModel):
    documents: list[AssembledDocument]
