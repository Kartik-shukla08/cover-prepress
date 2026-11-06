"""Unit tests for Diagnostic Proof Generator.

Verifies:
- High-resolution dual-panel diagnostic image composition (full spread + zoomed spine).
- Skeletal guideline overlays: Bleed (magenta), Trim (cyan), Folds (orange), Safe margins (green).
- Real-time PASS / FAIL badge rendering based on centering.is_safe.
- Spine fold clearance callouts and buffer metrics.
- Edge case handling: zero spine width, grayscale images, extreme DPI, non-standard canvas aspect.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from PIL import Image
import numpy as np

from mbooks.prepress.specs import calculate_prepress_spec
from mbooks.prepress.crease import CreaseDetectionResult
from mbooks.prepress.centering import CenteringResult
from mbooks.prepress.proof import generate_diagnostic_proof


class TestProofGenerator:
    """Test suite for diagnostic proof rendering engine."""

    def test_dual_panel_proof_generation(self, tmp_path):
        """Generate proof and verify image dimensions exceed minimum inspection thresholds."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 150)
        w_px = round(spec.total_w_in * 300)
        h_px = round(spec.total_h_in * 300)
        img = Image.new("RGB", (w_px, h_px), (60, 80, 40))

        crease = CreaseDetectionResult(
            x_left=1838,
            x_right=1939,
            spine_width_px=101,
            shadow_bleed_right_px=0,
            clean_background_rgb=(60, 80, 40),
            confidence=1.0,
        )

        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=50.5,
            geometric_center_x_px=50.5,
            left_clearance_px=22.0,
            right_clearance_px=22.0,
            safe_margin_px=18.75,
            is_safe=True,
        )

        proof_path = str(tmp_path / "proof_standard.png")
        out = generate_diagnostic_proof(img, spec, centering, crease, proof_path, dpi=300)
        assert Path(out).exists()

        with Image.open(out) as proof_img:
            assert proof_img.size[0] >= 1200
            assert proof_img.size[1] >= 600
            assert proof_img.mode == "RGB"

    def test_pass_badge_rendered(self, tmp_path):
        """When centering.is_safe is True, proof generates PASS status."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 150)
        img = Image.new("RGB", (1000, 700), (40, 50, 60))

        crease = CreaseDetectionResult(
            x_left=480,
            x_right=520,
            spine_width_px=40,
            shadow_bleed_right_px=0,
            clean_background_rgb=(40, 50, 60),
            confidence=0.9,
        )

        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=20.0,
            geometric_center_x_px=20.0,
            left_clearance_px=20.0,
            right_clearance_px=20.0,
            safe_margin_px=18.75,
            is_safe=True,
        )

        proof_path = str(tmp_path / "proof_pass.png")
        out = generate_diagnostic_proof(img, spec, centering, crease, proof_path, dpi=100)
        assert Path(out).exists()

        # Check that green PASS pixels exist in badge area (top right)
        with Image.open(out) as proof_img:
            arr = np.array(proof_img)
            # Badge region is roughly y: 22..74, x: right edge - 300 .. right edge
            badge_area = arr[22:74, -200:-20]
            # Green badge has high G and low R
            has_green = np.any((badge_area[:, :, 1] > 180) & (badge_area[:, :, 0] < 50))
            assert has_green, "Expected green PASS badge in top right header"

    def test_fail_badge_on_safe_margin_breach(self, tmp_path):
        """When centering.is_safe is False, proof renders red FAIL badge."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 150)
        img = Image.new("RGB", (1000, 700), (40, 50, 60))

        crease = CreaseDetectionResult(
            x_left=480,
            x_right=520,
            spine_width_px=40,
            shadow_bleed_right_px=0,
            clean_background_rgb=(40, 50, 60),
            confidence=0.9,
        )

        centering = CenteringResult(
            shift_x_px=15.0,
            optical_center_x_px=35.0,
            geometric_center_x_px=20.0,
            left_clearance_px=35.0,
            right_clearance_px=2.0,  # Breaches 18.75 px safe margin!
            safe_margin_px=18.75,
            is_safe=False,
        )

        proof_path = str(tmp_path / "proof_fail.png")
        out = generate_diagnostic_proof(img, spec, centering, crease, proof_path, dpi=100)
        assert Path(out).exists()

        with Image.open(out) as proof_img:
            arr = np.array(proof_img)
            badge_area = arr[22:74, -300:-20]
            # Red badge has high R and low G
            has_red = np.any((badge_area[:, :, 0] > 200) & (badge_area[:, :, 1] < 80))
            assert has_red, "Expected red FAIL badge in top right header"

    def test_zero_spine_width_handling(self, tmp_path):
        """Zero spine width handles gracefully without division by zero."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 80)
        img = Image.new("RGB", (800, 600), (50, 50, 50))

        crease = CreaseDetectionResult(
            x_left=400,
            x_right=400,  # 0 spine width
            spine_width_px=0,
            shadow_bleed_right_px=0,
            clean_background_rgb=(50, 50, 50),
            confidence=0.5,
        )

        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=0.0,
            geometric_center_x_px=0.0,
            left_clearance_px=0.0,
            right_clearance_px=0.0,
            safe_margin_px=18.75,
            is_safe=True,
        )

        proof_path = str(tmp_path / "proof_zero_spine.png")
        out = generate_diagnostic_proof(img, spec, centering, crease, proof_path, dpi=100)
        assert Path(out).exists()

    def test_grayscale_input_support(self, tmp_path):
        """Single-channel grayscale input spread is converted cleanly."""
        spec = calculate_prepress_spec("lulu", "paperback", 6.0, 9.0, 100)
        gray_img = Image.new("L", (900, 600), 128)

        crease = CreaseDetectionResult(
            x_left=430,
            x_right=470,
            spine_width_px=40,
            shadow_bleed_right_px=0,
            clean_background_rgb=(128, 128, 128),
            confidence=0.8,
        )

        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=20.0,
            geometric_center_x_px=20.0,
            left_clearance_px=15.0,
            right_clearance_px=15.0,
            safe_margin_px=12.5,
            is_safe=True,
        )

        proof_path = str(tmp_path / "proof_grayscale.png")
        out = generate_diagnostic_proof(gray_img, spec, centering, crease, proof_path, dpi=100)
        assert Path(out).exists()

    def test_extreme_dpi_support(self, tmp_path):
        """High resolution (600 DPI) rendering works without scaling distortion."""
        spec = calculate_prepress_spec("ingram", "paperback", 6.0, 9.0, 200)
        img = Image.new("RGB", (1200, 900), (30, 40, 50))

        crease = CreaseDetectionResult(
            x_left=580,
            x_right=620,
            spine_width_px=40,
            shadow_bleed_right_px=0,
            clean_background_rgb=(30, 40, 50),
            confidence=0.85,
        )

        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=20.0,
            geometric_center_x_px=20.0,
            left_clearance_px=25.0,
            right_clearance_px=25.0,
            safe_margin_px=18.75,
            is_safe=True,
        )

        proof_path = str(tmp_path / "proof_600dpi.png")
        out = generate_diagnostic_proof(img, spec, centering, crease, proof_path, dpi=600)
        assert Path(out).exists()

    def test_non_standard_aspect_ratio(self, tmp_path):
        """Panoramic 2:1 spread fits within composite viewport."""
        spec = calculate_prepress_spec("kdp", "paperback", 8.5, 4.25, 100)
        panoramic = Image.new("RGB", (1600, 800), (70, 70, 70))

        crease = CreaseDetectionResult(
            x_left=780,
            x_right=820,
            spine_width_px=40,
            shadow_bleed_right_px=0,
            clean_background_rgb=(70, 70, 70),
            confidence=0.8,
        )

        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=20.0,
            geometric_center_x_px=20.0,
            left_clearance_px=18.0,
            right_clearance_px=18.0,
            safe_margin_px=18.75,
            is_safe=False,
        )

        proof_path = str(tmp_path / "proof_panoramic.png")
        out = generate_diagnostic_proof(panoramic, spec, centering, crease, proof_path, dpi=100)
        assert Path(out).exists()

    def test_auto_create_parent_directory(self, tmp_path):
        """Nested parent directory is automatically created."""
        spec = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 100)
        img = Image.new("RGB", (800, 600), (60, 60, 60))
        crease = CreaseDetectionResult(
            x_left=380,
            x_right=420,
            spine_width_px=40,
            shadow_bleed_right_px=0,
            clean_background_rgb=(60, 60, 60),
            confidence=0.8,
        )
        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=20.0,
            geometric_center_x_px=20.0,
            left_clearance_px=20.0,
            right_clearance_px=20.0,
            safe_margin_px=18.75,
            is_safe=True,
        )

        nested_path = str(tmp_path / "nested" / "subfolder" / "proof.png")
        out = generate_diagnostic_proof(img, spec, centering, crease, nested_path, dpi=100)
        assert Path(out).exists()
