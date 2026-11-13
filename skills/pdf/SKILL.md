---
name: pdf
description: Portable PDF processing and synthesis skill for reading, extracting text/tables/images, rendering page images at 300 DPI, performing OCR, and generating vector & scanned PDFs
---

# Portable PDF Processing & Generation Skill

This skill provides portable, CLI-agnostic guidelines and Python instructions for reading, extracting, rendering, OCRing, and generating PDF documents across vector and rasterized scanned formats.

## Overview

PDF document processing in automated review and synthesis systems requires handling two primary representations:
1. **Vector PDFs**: Native programmatic PDFs containing clean font glyphs, layout flowables, and structured table nodes.
2. **Rasterized / Scanned PDFs**: Bitmap-backed image PDFs resulting from physical scanning, camera captures, or image rasterization pipelines.

---

## Python Tool Workflows

### 1. Vector PDF Generation (`reportlab`)

Use `reportlab.platypus` to programmatically build clean, multi-page vector PDF documents with custom typography, structured key-value tables, grid layouts, and header/footer canvas callbacks.

```python
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table

def generate_vector_pdf(title_text: str, data_grid: list[list[str]]) -> bytes:
    """Generate clean vector PDF bytes using ReportLab Platypus elements."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54, rightMargin=54,
        topMargin=54, bottomMargin=54,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CustomTitle", parent=styles["Heading1"], fontSize=18, leading=22)

    story = [
        Paragraph(title_text, title_style),
        Spacer(1, 12),
        Table(
            data_grid,
            style=[
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F4F8')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]
        ),
    ]
    doc.build(story)
    return buffer.getvalue()
```

### 2. High-DPI Page Rendering (`pypdfium2`)

Render PDF pages into 300 DPI PIL Images for vision models, quality inspection, or rasterization pipelines.

```python
import pypdfium2 as pdfium
from PIL import Image

def render_pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> list[Image.Image]:
    """Render pages of a PDF document to 300 DPI PIL Images using pypdfium2."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    scale = dpi / 72.0
    images = []
    for page in pdf:
        bitmap = page.render(scale=scale)
        images.append(bitmap.to_pil())
    return images
```

### 3. Scan Artifact Simulation & Image Processing (`Pillow`)

Simulate physical scanning defects such as rotation skew, grayscale conversion, contrast reduction, and gaussian noise blur, then assemble back into a multi-page PDF.

```python
import io
import random
from PIL import Image, ImageEnhance, ImageFilter

def apply_scan_artifacts(images: list[Image.Image], rotation_deg: float = 1.0) -> bytes:
    """Apply realistic scan artifacts via Pillow and save as a scanned PDF."""
    processed = []
    for img in images:
        angle = random.uniform(-rotation_deg, rotation_deg)
        img_gray = img.rotate(
            angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)
        ).convert("L")

        enhanced = ImageEnhance.Contrast(img_gray).enhance(random.uniform(0.85, 1.15))
        blurred = enhanced.filter(ImageFilter.GaussianBlur(radius=0.4)).convert("RGB")
        processed.append(blurred)

    out_buffer = io.BytesIO()
    processed[0].save(
        out_buffer,
        format="PDF",
        save_all=True,
        append_images=processed[1:],
        resolution=300.0,
    )
    return out_buffer.getvalue()
```

### 4. Structured Extraction & Text Analysis (`pdfplumber`)

Extract layout-aware text, bounding boxes, and table data from vector PDFs.

```python
import io
import pdfplumber

def extract_pdf_data(pdf_bytes: bytes) -> dict:
    """Extract full text and structured tables from a vector PDF using pdfplumber."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        tables = [page.extract_tables() for page in pdf.pages]
    return {"text": text, "tables": tables}
```

### 5. Optical Character Recognition (`pytesseract`)

Perform OCR on rasterized scanned PDF images to extract textual contents.

```python
import pytesseract
from PIL import Image

def ocr_scanned_image(image: Image.Image, lang: str = "eng") -> str:
    """Extract text from a scanned page image using Tesseract OCR."""
    return pytesseract.image_to_string(image, lang=lang)
```

---

## Synthesis & Processing Lifecycle

1. **Generation / Synthesis**: Use `reportlab` to render canonical document layouts into vector PDFs.
2. **Rasterization**: Render vector PDFs at 300 DPI with `pypdfium2` and apply simulated scan artifacts using `Pillow`.
3. **Extraction & Verification**: Use `pdfplumber` for vector extraction or `pytesseract` for scanned OCR text extraction to verify document content.
