"""Multimodal 300 DPI PDF Rasterizer and Scan Artifact Simulator.

Converts clean ReportLab vector PDF bytes into 300 DPI scanned images via pypdfium2,
applies realistic scanning artifacts (rotation tilt, contrast reduction, noise blur)
via Pillow, and re-assembles into scanned multi-page PDF documents per D-48-02.
"""

import io
import logging
import math
import random
import threading
from typing import Any, List, Optional

from PIL import Image, ImageEnhance, ImageFilter
import pypdfium2 as pdfium
from reportlab.lib.utils import ImageReader

from crawler.synthetic.generator import SanitizedMetadataCanvas

logger = logging.getLogger(__name__)

_PDFIUM_LOCK = threading.Lock()

MAX_INPUT_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
MIN_DPI = 72
MAX_DPI = 600
MAX_PAGE_COUNT = 50
MAX_PAGE_PIXEL_WIDTH = 10_000
MAX_PAGE_PIXEL_HEIGHT = 10_000
MAX_AGGREGATE_PIXELS = 100_000_000  # 100 MP


def _validate_rasterizer_inputs(pdf_bytes: bytes, dpi: int) -> None:
    """Validate raw rasterizer input parameter types, size bounds, and accepted DPI range."""
    if not isinstance(pdf_bytes, bytes):
        raise ValueError("Input PDF must be bytes.")
    if len(pdf_bytes) == 0:
        raise ValueError("Input PDF bytes cannot be empty.")
    if len(pdf_bytes) > MAX_INPUT_PDF_BYTES:
        raise ValueError(
            f"Input PDF size ({len(pdf_bytes)} bytes) exceeds maximum allowed ({MAX_INPUT_PDF_BYTES} bytes)."
        )
    if not (MIN_DPI <= dpi <= MAX_DPI):
        raise ValueError(
            f"Requested DPI {dpi} is outside accepted range [{MIN_DPI}, {MAX_DPI}]."
        )


def _validate_pdf_document_bounds(pdf: pdfium.PdfDocument, dpi: int) -> None:
    """Fail closed on invalid page count, non-finite/negative dimensions, or excessive scaling before page rendering."""
    page_count = len(pdf)
    if page_count == 0:
        raise ValueError("Failed to render any PDF pages: document contains 0 pages.")
    if page_count > MAX_PAGE_COUNT:
        raise ValueError(
            f"PDF page count ({page_count}) exceeds maximum allowed ({MAX_PAGE_COUNT})."
        )

    scale = dpi / 72.0
    total_pixels = 0

    for page_idx in range(page_count):
        page = pdf[page_idx]
        w_pt, h_pt = page.get_size()

        if not (math.isfinite(w_pt) and math.isfinite(h_pt) and w_pt > 0 and h_pt > 0):
            raise ValueError(
                f"Page {page_idx} has invalid non-finite or non-positive dimensions ({w_pt}, {h_pt})."
            )

        px_w = int(w_pt * scale)
        px_h = int(h_pt * scale)

        if px_w > MAX_PAGE_PIXEL_WIDTH or px_h > MAX_PAGE_PIXEL_HEIGHT:
            raise ValueError(
                f"Page {page_idx} dimensions ({px_w}x{px_h} px) at {dpi} DPI exceed maximum "
                f"per-page pixel bounds ({MAX_PAGE_PIXEL_WIDTH}x{MAX_PAGE_PIXEL_HEIGHT} px). "
                f"Parity requires 300 DPI — refusing to silently downscale."
            )

        total_pixels += px_w * px_h
        if total_pixels > MAX_AGGREGATE_PIXELS:
            raise ValueError(
                f"Total aggregate pixels ({total_pixels}) across {page_count} pages exceeds "
                f"maximum aggregate pixel bound ({MAX_AGGREGATE_PIXELS})."
            )


def rasterize_pdf_to_scanned_images(
    pdf_bytes: bytes,
    dpi: int = 300,
    rotation_deg: float = 1.0,
    add_noise: bool = True,
) -> List[Image.Image]:
    """Convert clean PDF bytes into a list of 300 DPI PIL Images with scan artifacts.

    Args:
        pdf_bytes: Input vector PDF byte string.
        dpi: Target resolution for page rendering (default: 300 DPI).
        rotation_deg: Max random rotation angle in degrees (-rotation_deg to +rotation_deg).
        add_noise: Whether to inject gaussian blur/noise artifacts.

    Returns:
        List of processed RGB PIL Images.
    """
    _validate_rasterizer_inputs(pdf_bytes, dpi)

    with _PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(pdf_bytes)
        try:
            _validate_pdf_document_bounds(pdf, dpi)
            scanned_pages: List[Image.Image] = []
            scale = dpi / 72.0

            for page_idx in range(len(pdf)):
                page = pdf[page_idx]
                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil()

                # 1. Subtle tilt / rotation
                if rotation_deg > 0:
                    angle = random.uniform(-rotation_deg, rotation_deg)
                    pil_img = pil_img.rotate(
                        angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)
                    )

                # 2. Grayscale conversion & contrast adjustment
                pil_img = pil_img.convert("L")
                enhancer = ImageEnhance.Contrast(pil_img)
                pil_img = enhancer.enhance(random.uniform(0.85, 1.15))

                # 3. Gaussian noise / scan blur simulation
                if add_noise:
                    pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=0.4))

                scanned_pages.append(pil_img.convert("RGB"))

            return scanned_pages
        finally:
            pdf.close()


def rasterize_pdf_to_scanned_pdf(
    vector_pdf_bytes: Optional[bytes] = None,
    dpi: int = 300,
    rotation_angle: float = 1.0,
    add_noise: bool = True,
    pdf_bytes: Optional[bytes] = None,
    rotation_deg: Optional[float] = None,
    **kwargs: Any,
) -> bytes:
    """Rasterize clean vector PDF bytes into a realistic scanned/image-based PDF byte string per D-05, D-07, D-08.

    Guarantees zero text layer in the resulting PDF and metadata sanitization via SanitizedMetadataCanvas.

    Args:
        vector_pdf_bytes: Input vector PDF bytes (or passed as pdf_bytes).
        dpi: Target resolution in DPI (default 300).
        rotation_angle: Rotation tilt degree range (or passed as rotation_deg).
        add_noise: Inject scan blur/noise.
        pdf_bytes: Backwards-compatible parameter name for vector_pdf_bytes.
        rotation_deg: Backwards-compatible parameter name for rotation_angle.

    Returns:
        Scanned PDF bytes with zero text layer and sanitized metadata.
    """
    input_bytes = vector_pdf_bytes if vector_pdf_bytes is not None else pdf_bytes
    if input_bytes is None:
        raise ValueError("rasterize_pdf_to_scanned_pdf requires vector_pdf_bytes or pdf_bytes input.")

    rot_deg = rotation_deg if rotation_deg is not None else rotation_angle
    _validate_rasterizer_inputs(input_bytes, dpi)

    with _PDFIUM_LOCK:
        pdf = pdfium.PdfDocument(input_bytes)
        try:
            _validate_pdf_document_bounds(pdf, dpi)

            scale = dpi / 72.0
            out_buffer = io.BytesIO()

            p0 = pdf[0]
            w_pt, h_pt = p0.get_size()
            c = SanitizedMetadataCanvas(out_buffer, pagesize=(w_pt, h_pt))

            for page_idx in range(len(pdf)):
                page = pdf[page_idx]
                w_pt, h_pt = page.get_size()
                c.setPageSize((w_pt, h_pt))

                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil()

                # 1. Subtle tilt / rotation
                if rot_deg > 0:
                    angle = random.uniform(-rot_deg, rot_deg)
                    pil_img = pil_img.rotate(
                        angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)
                    )

                # 2. Grayscale conversion & contrast adjustment
                pil_img = pil_img.convert("L")
                enhancer = ImageEnhance.Contrast(pil_img)
                pil_img = enhancer.enhance(random.uniform(0.85, 1.15))

                # 3. Scan noise simulation
                if add_noise:
                    pil_img = pil_img.filter(ImageFilter.GaussianBlur(radius=0.4))

                pil_img = pil_img.convert("RGB")

                img_buf = io.BytesIO()
                pil_img.save(img_buf, format="JPEG", quality=85)
                img_buf.seek(0)

                reader = ImageReader(img_buf)
                c.drawImage(reader, 0, 0, width=w_pt, height=h_pt)
                c.showPage()

            c.save()
            return out_buffer.getvalue()
        finally:
            pdf.close()
