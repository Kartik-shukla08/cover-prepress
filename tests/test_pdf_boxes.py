"""Unit tests for prepress PDF Box Engine and Preflight Validation.

Verifies:
- Strict PDF Box hierarchy: MediaBox, BleedBox, TrimBox, CropBox across publishers and bindings.
- Zero crop or printer marks on exported spreads.
- Preflight Total Area Coverage (TAC) ceiling enforcement (Ingram 240%, Lulu 270%, KDP 300%).
- 400% Registration Black prohibition vs 100% Key black compliance.
- Transparency flattening for PDF/X compliance.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from PIL import Image
import numpy as np

import fitz

from mbooks.prepress.specs import calculate_prepress_spec
from mbooks.prepress.pdf import (
    export_print_ready_pdf,
    inspect_tac_and_registration,
    flatten_transparency,
    PreflightError,
    TACLimitExceededError,
    RegistrationBlackError,
    PUBLISHER_TAC_LIMITS,
)


class TestPdfBoxEngine:
    """Test suite for PDF Box hierarchy and geometry compliance."""

    @pytest.mark.parametrize("publisher", ["kdp", "ingram", "lulu"])
    def test_paperback_pdf_boxes(self, publisher, tmp_path):
        """Verify paperback PDF boxes: MediaBox=BleedBox=CropBox, TrimBox inset by bleed."""
        spec = calculate_prepress_spec(
            publisher=publisher,
            binding="paperback",
            trim_w_in=6.0,
            trim_h_in=9.0,
            page_count=200,
            paper_type="white",
        )

        w_px = round(spec.total_w_in * 150)
        h_px = round(spec.total_h_in * 150)
        img = Image.new("RGB", (w_px, h_px), (220, 220, 220))

        pdf_path = str(tmp_path / f"{publisher}_paperback.pdf")
        out = export_print_ready_pdf(img, spec, pdf_path, dpi=150)
        assert Path(out).exists()

        doc = fitz.open(out)
        assert len(doc) == 1
        page = doc[0]

        # Verify page dimensions and boxes in points (72 pt/in)
        mb = page.mediabox
        bb = page.bleedbox
        tb = page.trimbox
        cb = page.cropbox

        assert mb.width == pytest.approx(spec.media_box[2], abs=0.5)
        assert mb.height == pytest.approx(spec.media_box[3], abs=0.5)
        assert bb.width == pytest.approx(spec.bleed_box[2], abs=0.5)
        assert bb.height == pytest.approx(spec.bleed_box[3], abs=0.5)
        assert cb.width == pytest.approx(spec.crop_box[2], abs=0.5)
        assert cb.height == pytest.approx(spec.crop_box[3], abs=0.5)

        # TrimBox inset by 0.125" bleed (9.0 pt)
        bleed_pt = spec.bleed_in * 72.0
        assert tb.x0 == pytest.approx(bleed_pt, abs=0.5)
        assert tb.y0 == pytest.approx(bleed_pt, abs=0.5)
        assert tb.x1 == pytest.approx(mb.x1 - bleed_pt, abs=0.5)
        assert tb.y1 == pytest.approx(mb.y1 - bleed_pt, abs=0.5)

        doc.close()

    @pytest.mark.parametrize("publisher", ["kdp", "ingram", "lulu"])
    def test_casewrap_pdf_boxes(self, publisher, tmp_path):
        """Verify casewrap PDF boxes: TrimBox inset by outer turn-in wrap allowance."""
        spec = calculate_prepress_spec(
            publisher=publisher,
            binding="casewrap",
            trim_w_in=6.0,
            trim_h_in=9.0,
            page_count=250,
            paper_type="white",
        )

        w_px = round(spec.total_w_in * 100)
        h_px = round(spec.total_h_in * 100)
        img = Image.new("RGB", (w_px, h_px), (230, 230, 230))

        pdf_path = str(tmp_path / f"{publisher}_casewrap.pdf")
        out = export_print_ready_pdf(img, spec, pdf_path, dpi=100)
        assert Path(out).exists()

        doc = fitz.open(out)
        page = doc[0]

        mb = page.mediabox
        tb = page.trimbox

        wrap_pt = spec.wrap_in * 72.0
        assert tb.x0 == pytest.approx(wrap_pt, abs=0.5)
        assert tb.y0 == pytest.approx(wrap_pt, abs=0.5)
        assert tb.x1 == pytest.approx(mb.x1 - wrap_pt, abs=0.5)
        assert tb.y1 == pytest.approx(mb.y1 - wrap_pt, abs=0.5)

        doc.close()

    def test_zero_printer_marks(self, tmp_path):
        """Verify no vector drawings, crop marks, or registration targets are added."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 150)
        img = Image.new("RGB", (500, 350), (255, 255, 255))

        pdf_path = str(tmp_path / "clean_cover.pdf")
        export_print_ready_pdf(img, spec, pdf_path, dpi=100)

        doc = fitz.open(pdf_path)
        page = doc[0]

        # Zero vector drawings
        drawings = page.get_drawings()
        assert len(drawings) == 0, f"Expected 0 vector drawings, found {len(drawings)}"

        # Exactly 1 embedded raster image covering the spread
        images = page.get_images()
        assert len(images) == 1, f"Expected 1 embedded spread image, found {len(images)}"

        doc.close()


class TestPreflightValidation:
    """Test suite for TAC limits, registration black prevention, and transparency flattening."""

    def test_tac_limit_constants(self):
        """Verify official publisher TAC ceiling constants."""
        assert PUBLISHER_TAC_LIMITS["ingram"] == 240.0
        assert PUBLISHER_TAC_LIMITS["lulu"] == 270.0
        assert PUBLISHER_TAC_LIMITS["kdp"] == 300.0

    def test_ingram_tac_pass_rich_black(self, tmp_path):
        """Rich Black (60C, 40M, 40Y, 100K = 240% TAC) passes on IngramSpark."""
        spec = calculate_prepress_spec("ingram", "paperback", 6.0, 9.0, 100)

        # 60% of 255 = 153, 40% = 102, 100% = 255
        cmyk_arr = np.full((50, 50, 4), (153, 102, 102, 255), dtype=np.uint8)
        img = Image.fromarray(cmyk_arr, mode="CMYK")

        max_tac, has_breach, has_reg = inspect_tac_and_registration(img, tac_ceiling=240.0)
        assert max_tac == pytest.approx(240.0, abs=0.5)
        assert has_breach is False
        assert has_reg is False

        pdf_path = str(tmp_path / "ingram_rich_black.pdf")
        out = export_print_ready_pdf(img, spec, pdf_path, dpi=100)
        assert Path(out).exists()

    def test_ingram_tac_fail_excessive_ink(self, tmp_path):
        """Excessive ink (70C, 50M, 50Y, 100K = 270% TAC) raises TACLimitExceededError on Ingram."""
        spec = calculate_prepress_spec("ingram", "paperback", 6.0, 9.0, 100)

        cmyk_arr = np.full((50, 50, 4), (178, 128, 128, 255), dtype=np.uint8)
        img = Image.fromarray(cmyk_arr, mode="CMYK")

        max_tac, has_breach, _ = inspect_tac_and_registration(img, tac_ceiling=240.0)
        assert max_tac > 240.0
        assert has_breach is True

        pdf_path = str(tmp_path / "ingram_heavy_ink.pdf")
        with pytest.raises(TACLimitExceededError) as exc_info:
            export_print_ready_pdf(img, spec, pdf_path, dpi=100)
        assert "hard maximum ceiling of 240.0%" in str(exc_info.value)

    def test_lulu_tac_ceiling(self, tmp_path):
        """Lulu allows up to 270% TAC; rejects 285% TAC."""
        spec = calculate_prepress_spec("lulu", "paperback", 6.0, 9.0, 100)

        # <= 270% TAC passes (688 / 255.0 * 100 = 269.8%)
        cmyk_270 = np.full((40, 40, 4), (177, 128, 128, 255), dtype=np.uint8)
        img_270 = Image.fromarray(cmyk_270, mode="CMYK")
        out_270 = str(tmp_path / "lulu_270.pdf")
        export_print_ready_pdf(img_270, spec, out_270, dpi=100)
        assert Path(out_270).exists()

        # 285% TAC fails
        cmyk_285 = np.full((40, 40, 4), (190, 140, 140, 255), dtype=np.uint8)
        img_285 = Image.fromarray(cmyk_285, mode="CMYK")
        out_285 = str(tmp_path / "lulu_285.pdf")
        with pytest.raises(TACLimitExceededError):
            export_print_ready_pdf(img_285, spec, out_285, dpi=100)

    def test_registration_black_strictly_prohibited(self, tmp_path):
        """400% Registration Black (100C, 100M, 100Y, 100K) raises RegistrationBlackError."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 150)

        # 400% registration black patch
        cmyk_arr = np.full((50, 50, 4), (255, 255, 255, 255), dtype=np.uint8)
        img = Image.fromarray(cmyk_arr, mode="CMYK")

        max_tac, has_breach, has_reg = inspect_tac_and_registration(img, tac_ceiling=300.0)
        assert max_tac == 400.0
        assert has_reg is True

        pdf_path = str(tmp_path / "kdp_reg_black.pdf")
        with pytest.raises(RegistrationBlackError) as exc_info:
            export_print_ready_pdf(img, spec, pdf_path, dpi=100)
        assert "Registration Black" in str(exc_info.value)

    def test_pure_100k_black_allowed(self, tmp_path):
        """100% Key Black (0C, 0M, 0Y, 100K = 100% TAC) is compliant and passes."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 150)

        cmyk_arr = np.full((50, 50, 4), (0, 0, 0, 255), dtype=np.uint8)
        img = Image.fromarray(cmyk_arr, mode="CMYK")

        max_tac, has_breach, has_reg = inspect_tac_and_registration(img, tac_ceiling=300.0)
        assert max_tac == 100.0
        assert has_breach is False
        assert has_reg is False

        pdf_path = str(tmp_path / "kdp_pure_100k.pdf")
        out = export_print_ready_pdf(img, spec, pdf_path, dpi=100)
        assert Path(out).exists()

    def test_transparency_flattening(self, tmp_path):
        """RGBA image with semi-transparent pixels is flattened cleanly to opaque RGB."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 100)

        # Create RGBA image with translucent red over transparent
        rgba_img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        flattened = flatten_transparency(rgba_img)

        assert flattened.mode == "RGB"
        # 128 alpha red over white background: (255 * 0.5 + 255 * 0.5) ~ 255, green: ~128, blue: ~128
        pixel = flattened.getpixel((50, 50))
        assert pixel[0] == 255
        assert 120 <= pixel[1] <= 135
        assert 120 <= pixel[2] <= 135

        # Export flattened image to PDF
        pdf_path = str(tmp_path / "flattened_alpha.pdf")
        out = export_print_ready_pdf(rgba_img, spec, pdf_path, dpi=100)
        assert Path(out).exists()

        doc = fitz.open(out)
        page = doc[0]
        # In PyMuPDF, verify the page is opaque and valid
        pix = page.get_pixmap()
        assert pix.alpha == 0  # No alpha channel in rendered page
        doc.close()

    def test_invalid_output_directory_raises(self):
        """Saving to a non-existent parent directory raises exception."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 100)
        img = Image.new("RGB", (100, 100), (200, 200, 200))
        invalid_path = "non_existent_folder_abc123/nested/file.pdf"
        with pytest.raises(Exception):
            export_print_ready_pdf(img, spec, invalid_path)
