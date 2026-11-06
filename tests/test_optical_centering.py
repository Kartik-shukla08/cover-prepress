"""Unit tests for mbooks.prepress.centering: glyph-only optical centering and shadow bias elimination."""

from pathlib import Path
from PIL import Image
import numpy as np
import pytest

from mbooks.prepress.segmentation import SpineElement, segment_spine_elements
from mbooks.prepress.centering import (
    compute_optical_centering,
    measure_shadow_bias,
    CenteringResult,
)

CORPUS_COVER_PATH = Path("corpus/Denise_Hinton_Bazemore_-_That_show_lives_on_-_Cover_Design_2_3.jpeg")


class TestOpticalCenteringCorpus:
    """Tests on corpus reference spine verifying elimination of drop shadow bias."""

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus asset missing")
    def test_shadow_bias_measurement_on_denise_spine(self):
        img = Image.open(CORPUS_COVER_PATH)
        spine_crop = img.crop((588, 0, 691, 880))
        clean_bg = (70, 82, 25)

        glyph_c, naive_c, bias = measure_shadow_bias(spine_crop, clean_bg)
        # Empirical finding: naive centering with drop shadow biases center ~14px
        assert abs(bias) >= 10.0

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus asset missing")
    def test_optical_centering_achieves_equal_clearances(self):
        img = Image.open(CORPUS_COVER_PATH)
        spine_crop = img.crop((588, 0, 691, 880))
        clean_bg = (70, 82, 25)

        elements = segment_spine_elements(spine_crop, clean_bg)
        safe_margin_300dpi = 18.75  # 0.0625" * 300

        res = compute_optical_centering(spine_crop, elements, safe_margin_px=safe_margin_300dpi)
        assert res.is_safe is True
        # After optical shift, left and right clearances should be equal (symmetric centering)
        assert res.left_clearance_px == pytest.approx(res.right_clearance_px, abs=1.0)
        assert res.left_clearance_px >= safe_margin_300dpi
        assert res.right_clearance_px >= safe_margin_300dpi


class TestCenteringLogicAndNudges:
    """Tests for shift calculations, manual nudges, and breach detection."""

    def test_synthetic_element_centering(self):
        # 100px spine. Element at [20, 60] -> width = 40, center = 40.
        # Geometric center is 50. Shift needed is +10.
        arr = np.full((200, 100, 3), 100, dtype=np.uint8)
        img = Image.fromarray(arr)
        elem = SpineElement(element_type="text", bbox=(20, 10, 60, 50), is_symmetric=False)

        res = compute_optical_centering(img, [elem], safe_margin_px=15.0)
        assert res.shift_x_px == 10.0
        assert res.geometric_center_x_px == 50.0
        assert res.optical_center_x_px == 40.0
        # Centered bounds: [30, 70] -> left clearance = 30, right clearance = 30
        assert res.left_clearance_px == 30.0
        assert res.right_clearance_px == 30.0
        assert res.is_safe is True

    def test_manual_nudge_adjustment(self):
        arr = np.full((200, 100, 3), 100, dtype=np.uint8)
        img = Image.fromarray(arr)
        elem = SpineElement(element_type="text", bbox=(20, 10, 60, 50), is_symmetric=False)

        # Nudge +5.0 px to the right
        res = compute_optical_centering(img, [elem], safe_margin_px=15.0, nudge_px=5.0)
        assert res.shift_x_px == 15.0
        assert res.left_clearance_px == 35.0
        assert res.right_clearance_px == 25.0
        assert res.is_safe is True

        # Severe nudge +20.0 px breaches the 15.0 px right safe margin (right clearance = 10.0 < 15.0)
        res_breach = compute_optical_centering(img, [elem], safe_margin_px=15.0, nudge_px=20.0)
        assert res_breach.shift_x_px == 30.0
        assert res_breach.left_clearance_px == 50.0
        assert res_breach.right_clearance_px == 10.0
        assert res_breach.is_safe is False

    def test_too_wide_element_flags_unsafe(self):
        # 100px spine, element is 80px wide (from 10 to 90). Safe margin = 15.0.
        # Max clearance possible when centered is (100 - 80) / 2 = 10.0 < 15.0 -> Unsafe!
        arr = np.full((200, 100, 3), 100, dtype=np.uint8)
        img = Image.fromarray(arr)
        elem = SpineElement(element_type="text", bbox=(10, 10, 90, 50), is_symmetric=False)

        res = compute_optical_centering(img, [elem], safe_margin_px=15.0)
        assert res.left_clearance_px == 10.0
        assert res.right_clearance_px == 10.0
        assert res.is_safe is False

    def test_empty_spine_centering(self):
        arr = np.full((200, 100, 3), 100, dtype=np.uint8)
        img = Image.fromarray(arr)

        res = compute_optical_centering(img, [], safe_margin_px=15.0)
        assert res.shift_x_px == 0.0
        assert res.left_clearance_px == 50.0
        assert res.right_clearance_px == 50.0
        assert res.is_safe is True
