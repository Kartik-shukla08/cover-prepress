"""Unit tests for mbooks.prepress.segmentation: foreground extraction, element classification, and aspect-ratio scaling."""

from pathlib import Path
from PIL import Image
import numpy as np
import pytest

from mbooks.prepress.segmentation import (
    SpineElement,
    segment_spine_elements,
    calculate_element_scaling,
    reconstruct_clean_spine_background,
)

CORPUS_COVER_PATH = Path("corpus/Denise_Hinton_Bazemore_-_That_show_lives_on_-_Cover_Design_2_3.jpeg")


class TestSpineSegmentationCorpus:
    """Tests on corpus reference cover spine."""

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus asset missing")
    def test_segment_elements_on_denise_spine(self):
        img = Image.open(CORPUS_COVER_PATH)
        spine_crop = img.crop((588, 0, 691, 880))
        clean_bg = (70, 82, 25)

        elements = segment_spine_elements(spine_crop, clean_bg)
        assert len(elements) >= 3

        # Locate the star ornament (located between title and author, Y ~ 530..560)
        ornaments = [e for e in elements if e.element_type == "ornament"]
        assert len(ornaments) == 1
        star = ornaments[0]
        assert star.is_symmetric is True

        # Verify star ornament has near 1:1 aspect ratio
        x0, y0, x1, y1 = star.bbox
        w, h = x1 - x0, y1 - y0
        aspect_ratio = w / float(h)
        assert 0.85 <= aspect_ratio <= 1.25
        assert y0 >= 500 and y1 <= 600

        # Verify text elements are flagged as non-symmetric
        text_elements = [e for e in elements if e.element_type == "text"]
        assert len(text_elements) >= 2
        for t in text_elements:
            assert t.is_symmetric is False

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus asset missing")
    def test_reconstruct_clean_background_infills_glyphs_and_shadows(self):
        img = Image.open(CORPUS_COVER_PATH)
        spine_crop = img.crop((588, 0, 691, 880))
        clean_bg = (70, 82, 25)

        elements = segment_spine_elements(spine_crop, clean_bg)
        clean_img = reconstruct_clean_spine_background(spine_crop, clean_bg, elements)
        assert clean_img.size == spine_crop.size

        # In clean_img, bright gold glyph pixels (L > 105) should no longer exist
        arr = np.array(clean_img)
        lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        bg_lum = 0.299 * 70 + 0.587 * 82 + 0.114 * 25  # ~71.9
        bright_count = np.sum(lum > bg_lum + 25)
        assert bright_count == 0


class TestElementScalingRules:
    """Tests for 1:1 symmetric ornament scaling vs <=1.2x aspect clamp for typography."""

    def test_symmetric_ornament_scaling_enforces_1to1_aspect(self):
        star = SpineElement(
            element_type="ornament",
            bbox=(39, 537, 62, 559),
            is_symmetric=True,
        )

        # Non-isotropic request: scale_x = 0.8, scale_y = 1.6
        sx, sy = calculate_element_scaling(star, scale_x=0.8, scale_y=1.6)
        assert sx == pytest.approx(0.8)
        assert sy == pytest.approx(0.8)
        assert sx == sy  # Strictly 1:1 isotropic

        # Reverse non-isotropic request: scale_x = 1.5, scale_y = 0.9
        sx2, sy2 = calculate_element_scaling(star, scale_x=1.5, scale_y=0.9)
        assert sx2 == pytest.approx(0.9)
        assert sy2 == pytest.approx(0.9)
        assert sx2 == sy2

    def test_typography_needle_stretching_clamp_1_2x(self):
        title = SpineElement(
            element_type="text",
            bbox=(29, 53, 79, 192),
            is_symmetric=False,
        )

        # Severe vertical stretch request: scale_x = 1.0, scale_y = 2.5
        sx, sy = calculate_element_scaling(title, scale_x=1.0, scale_y=2.5)
        assert sx == 1.0
        assert sy == pytest.approx(1.2, abs=0.001)  # Clamped to 1.2x
        # Aspect ratio deviation |sy/sx - 1.0| <= 0.20
        assert abs(sy / sx - 1.0) <= 0.2001

        # Severe vertical compression request: scale_x = 1.0, scale_y = 0.4
        sx_c, sy_c = calculate_element_scaling(title, scale_x=1.0, scale_y=0.4)
        assert sx_c == 1.0
        assert sy_c == pytest.approx(1.0 / 1.2, abs=0.001)  # Clamped to 1.0 / 1.2
        assert abs(sy_c / sx_c - 1.0) <= 0.2001

        # Moderate request within +/- 20%: scale_x = 1.0, scale_y = 1.1
        sx_m, sy_m = calculate_element_scaling(title, scale_x=1.0, scale_y=1.1)
        assert sx_m == 1.0
        assert sy_m == 1.1


class TestEdgeCasesAndDustRejection:
    """Tests for edge cases, dust filtering, and empty spines."""

    def test_plain_solid_spine_yields_empty_elements(self):
        arr = np.full((300, 80, 3), 100, dtype=np.uint8)
        img = Image.fromarray(arr)
        elements = segment_spine_elements(img, (100, 100, 100))
        assert elements == []

    def test_dust_speck_rejection(self):
        arr = np.full((300, 80, 3), 50, dtype=np.uint8)
        # Add 3 isolated single-pixel specks
        arr[50, 40, :] = 255
        arr[120, 35, :] = 255
        arr[200, 45, :] = 255
        img = Image.fromarray(arr)

        elements = segment_spine_elements(img, (50, 50, 50))
        # Dust specks (< 20 px) must be rejected
        assert elements == []
