"""Unit tests for mbooks.prepress.resizer: cover wrap resizing and panel assembly."""

from pathlib import Path
from PIL import Image
import numpy as np
import pytest

from mbooks.prepress.resizer import (
    ResizeOptions,
    ResizeResult,
    resize_cover_wrap,
)

CORPUS_COVER_PATH = Path("corpus/Denise_Hinton_Bazemore_-_That_show_lives_on_-_Cover_Design_2_3.jpeg")


class TestCoverResizerCorpus:
    """End-to-end resizing tests on reference corpus artwork."""

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus asset missing")
    def test_denise_mockup_resize_to_kdp_6x9_150p(self):
        img = Image.open(CORPUS_COVER_PATH)
        opts = ResizeOptions(
            publisher="kdp",
            binding="paperback",
            trim_size="6x9",
            page_count=150,
            paper_type="white",
            ink_type="black",
            dpi=300,
        )

        res = resize_cover_wrap(img, opts)

        # Verified dimensions for KDP 6x9 150p White: 3776 x 2775 px at 300 DPI
        assert res.spread_image.size == (3776, 2775)
        assert res.spec.total_w_in == pytest.approx(12.5878, abs=0.001)
        assert res.spec.total_h_in == pytest.approx(9.25, abs=0.001)
        assert res.spec.spine_w_in == pytest.approx(0.3378, abs=0.001)

        # Crease detection
        assert res.crease_detection.x_left in (587, 588, 589)
        assert res.crease_detection.x_right in (690, 691, 692)
        assert res.crease_detection.shadow_bleed_right_px > 0

        # Safe margins & centering audit: safe margin is 18.75 px (0.0625" * 300)
        assert res.centering.safe_margin_px == pytest.approx(18.75, abs=0.01)
        assert res.centering.left_clearance_px >= 18.75
        assert res.centering.right_clearance_px >= 18.75
        assert res.centering.is_safe is True
        assert len(res.warnings) == 0

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus asset missing")
    def test_denise_resize_with_override_spine_bounds(self):
        img = Image.open(CORPUS_COVER_PATH)
        opts = ResizeOptions(
            publisher="kdp",
            binding="paperback",
            trim_size="6x9",
            page_count=150,
            override_spine_bounds=(590, 690),
            dpi=300,
        )

        res = resize_cover_wrap(img, opts)
        assert res.crease_detection.x_left == 590
        assert res.crease_detection.x_right == 690
        assert res.crease_detection.spine_width_px == 100

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus asset missing")
    def test_denise_resize_with_manual_spine_shift(self):
        img = Image.open(CORPUS_COVER_PATH)
        opts = ResizeOptions(
            publisher="kdp",
            binding="paperback",
            trim_size="6x9",
            page_count=150,
            spine_shift_px=3.0,
            dpi=300,
        )

        res = resize_cover_wrap(img, opts)
        assert res.centering.shift_x_px == 3.0


class TestCoverResizerSeparatePanels:
    """Tests assembling wraps from separate front, back, and spine images."""

    def test_assemble_from_three_separate_panels(self):
        front = Image.new("RGB", (1800, 2700), (220, 40, 40))
        back = Image.new("RGB", (1800, 2700), (40, 40, 220))
        spine = Image.new("RGB", (150, 2700), (40, 220, 40))

        panels = {"front": front, "back": back, "spine": spine}
        opts = ResizeOptions(
            publisher="ingram",
            binding="paperback",
            trim_size="6x9",
            page_count=200,
            dpi=300,
        )

        res = resize_cover_wrap(panels, opts)
        assert res.spread_image.width == int(round(res.spec.total_w_in * 300))
        assert res.spread_image.height == int(round(res.spec.total_h_in * 300))
        assert res.spec.publisher == "ingram"

    def test_assemble_without_spine_generates_clean_spine(self):
        front = Image.new("RGB", (1800, 2700), (100, 150, 200))
        back = Image.new("RGB", (1800, 2700), (100, 150, 200))

        panels = {"front": front, "back": back}
        opts = ResizeOptions(
            publisher="lulu",
            binding="paperback",
            trim_size="6x9",
            page_count=100,
            dpi=300,
        )

        res = resize_cover_wrap(panels, opts)
        assert res.spread_image.size == (int(round(res.spec.total_w_in * 300)), int(round(res.spec.total_h_in * 300)))
        assert res.centering.is_safe is True


class TestCoverResizerShortSpineAndCasewrap:
    """Tests for short-book spine suppression and Casewrap binding."""

    def test_kdp_short_book_spine_text_suppression(self):
        # 50 pages < 80 threshold -> spine text suppressed with warning
        arr = np.full((880, 1280, 3), 100, dtype=np.uint8)
        arr[:, 588:691, :] = 50
        img = Image.fromarray(arr)

        opts = ResizeOptions(
            publisher="kdp",
            binding="paperback",
            trim_size="6x9",
            page_count=50,
            dpi=300,
        )

        res = resize_cover_wrap(img, opts)
        assert res.spec.allow_spine_text is False
        assert len(res.warnings) >= 1
        assert "below KDP minimum threshold of 80 pages" in res.warnings[0]
        # Clean solid spine is created and is safe
        assert res.centering.is_safe is True

    def test_casewrap_assembly_lulu(self):
        front = Image.new("RGB", (1800, 2700), (100, 100, 100))
        back = Image.new("RGB", (1800, 2700), (100, 100, 100))
        panels = {"front": front, "back": back}

        opts = ResizeOptions(
            publisher="lulu",
            binding="casewrap",
            trim_size="6x9",
            page_count=150,
            dpi=300,
        )

        res = resize_cover_wrap(panels, opts)
        assert res.spec.binding == "casewrap"
        assert res.spec.wrap_in == 0.750
        assert res.spec.hinge_in == 0.125
        assert res.spread_image.size == (int(round(res.spec.total_w_in * 300)), int(round(res.spec.total_h_in * 300)))
