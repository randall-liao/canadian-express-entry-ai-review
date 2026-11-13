"""Asset downloader for public domain document templates, seals, stamps, and watermarks.

Downloads sample public domain image templates and assets from web sources with local
caching under crawler/synthetic/assets/, with graceful offline fallback to local
synthetic PNG/SVG placeholders if offline or network fails (T-48-02 mitigation).
"""

import io
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets"

PUBLIC_ASSET_URLS = {
    "seal.png": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c0/Coat_of_arms_of_Canada.svg/200px-Coat_of_arms_of_Canada.svg.png",
    "stamp.png": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/A_stamp_icon.svg/200px-A_stamp_icon.svg.png",
    "watermark.png": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Approved_stamp.svg/200px-Approved_stamp.svg.png",
    "header_logo.png": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/Canada_wordmark.svg/300px-Canada_wordmark.svg.png",
}


def ensure_assets_dir() -> Path:
    """Ensure the local asset cache directory exists."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    return ASSETS_DIR


def create_placeholder_image(asset_name: str, text: str = "OFFICIAL SEAL") -> Path:
    """Generate a clean synthetic PNG image placeholder when offline or download fails."""
    ensure_assets_dir()
    filepath = ASSETS_DIR / asset_name

    img = Image.new("RGBA", (200, 200), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    if "seal" in asset_name:
        # Draw circular seal graphic
        draw.ellipse([10, 10, 190, 190], outline="#1A365D", width=6)
        draw.ellipse([20, 20, 180, 180], outline="#2B6CB0", width=2)
        draw.text((45, 90), text, fill="#1A365D")
    elif "stamp" in asset_name:
        # Draw rectangular stamp graphic
        draw.rectangle([10, 50, 190, 150], outline="#C53030", width=5)
        draw.text((35, 90), "OFFICIAL STAMP", fill="#C53030")
    elif "watermark" in asset_name:
        # Draw light watermark graphic
        draw.rectangle([20, 20, 180, 180], outline="#CBD5E0", width=2)
        draw.text((50, 90), "VERIFIED", fill="#A0AEC0")
    else:
        # Header logo / default placeholder
        draw.rectangle([10, 70, 190, 130], fill="#2B6CB0")
        draw.text((40, 95), text, fill="#FFFFFF")

    img.save(filepath, format="PNG")
    return filepath


def fetch_asset(asset_name: str, url: Optional[str] = None, timeout: float = 3.0) -> Path:
    """Fetch an asset from a public URL with local caching and offline placeholder fallback.

    Args:
        asset_name: Local filename (e.g. 'seal.png').
        url: Direct image URL. If None, looks up in PUBLIC_ASSET_URLS.
        timeout: Network timeout in seconds.

    Returns:
        Path to the cached image asset or synthetic placeholder.
    """
    ensure_assets_dir()
    filepath = ASSETS_DIR / asset_name

    if filepath.exists() and filepath.stat().st_size > 0:
        return filepath

    target_url = url or PUBLIC_ASSET_URLS.get(asset_name)

    if target_url:
        try:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "PR-Review-Agents-SyntheticDownloader/2.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = resp.read()
                    # Validate image format using PIL
                    img = Image.open(io.BytesIO(data))
                    img.verify()
                    with open(filepath, "wb") as f:
                        f.write(data)
                    logger.info("Successfully downloaded asset %s from %s", asset_name, target_url)
                    return filepath
        except Exception as err:
            logger.warning("Failed to download asset %s from %s: %s. Using placeholder.", asset_name, target_url, err)

    # Fallback to local synthetic placeholder generator
    return create_placeholder_image(asset_name, text=asset_name.replace(".png", "").upper())


def get_seal_image_path() -> Path:
    """Return path to official seal asset."""
    return fetch_asset("seal.png")


def get_stamp_image_path() -> Path:
    """Return path to official stamp asset."""
    return fetch_asset("stamp.png")


def get_watermark_image_path() -> Path:
    """Return path to official watermark asset."""
    return fetch_asset("watermark.png")


def get_header_logo_path() -> Path:
    """Return path to official header logo asset."""
    return fetch_asset("header_logo.png")


def get_asset_path(asset_name: str, url: Optional[str] = None) -> Path:
    """Generic asset retriever."""
    return fetch_asset(asset_name, url=url)
