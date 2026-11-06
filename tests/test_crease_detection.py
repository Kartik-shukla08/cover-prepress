"""Unit tests for mbooks.prepress.crease: fold crease detection and shadow bleed trimming."""

from pathlib import Path
from PIL import Image
import numpy as np
import pytest

from mbooks.prepress.crease import (
    detect_spine_creases,
    trim_shadow_and_infill_background,
    CreaseDetectionResult,
)

CORPUS_COVER_PATH = Path("corpus/Denise_Hinton_Bazemore_-_That_show_lives_on_-_Cover_Design_2_3.jpeg")


class TestCreaseDetectionSynthetic:
    """Tests on synthetic covers with mathematically defined geometry."""

    def test_synthetic_sharp_creases_no_shadow(self):
        # Canvas: 1000 x 400. Back: 0..450 (val 220), Spine: 450..550 (val 100), Front: 550..1000 (val 220)
        arr = np.full((400, 1000, 3), 220, dtype=np.uint8)
        arr[:, 450:550, :] = 100
        img = Image.fromarray(arr)

        res = detect_spine_creases(img)
        assert res.x_left == 450
        assert res.x_right == 550
        assert res.spine_width_px == 100
        assert res.shadow_bleed_right_px == 0
        assert res.clean_background_rgb == (100, 100, 100)
        assert res.confidence >= 0.8

    def test_synthetic_with_central_noise_immunity(self):
        # Margins remain clean, but central region has high-frequency noise
        arr = np.full((500, 1000, 3), 200, dtype=np.uint8)
        arr[:, 460:540, :] = 80
        # Add noise to interior (Y = 100..400)
        rng = np.random.default_rng(42)
        arr[100:400, 200:800, :] = rng.integers(0, 255, size=(300, 600, 3), dtype=np.uint8)
        img = Image.fromarray(arr)

        res = detect_spine_creases(img)
        assert res.x_left == 460
        assert res.x_right == 540
        assert res.spine_width_px == 80

    def test_synthetic_off_center_spine(self):
        # Spine at 350..450 (centered at 400 / 0.40)
        arr = np.full((400, 1000, 3), 210, dtype=np.uint8)
        arr[:, 350:450, :] = 90
        img = Image.fromarray(arr)

        res = detect_spine_creases(img, expected_spine_center_ratio=0.40)
        assert res.x_left == 350
        assert res.x_right == 450
        assert res.spine_width_px == 100


class TestCreaseDetectionCorpusReference:
    """Tests on authoritative reference corpus artwork (3D mockup)."""

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus cover asset missing")
    def test_denise_mockup_crease_and_shadow_bleed(self):
        img = Image.open(CORPUS_COVER_PATH)
        assert img.size == (1280, 880)

        res = detect_spine_creases(img)
        # Authoritative verified coordinates from Survey 3
        assert res.x_left in (587, 588, 589)
        assert res.x_right in (690, 691, 692)
        assert res.spine_width_px == pytest.approx(103, abs=2)
        # Shadow bleed rolls off ~37-38px into the front panel
        assert 30 <= res.shadow_bleed_right_px <= 45
        # Clean olive background
        assert abs(res.clean_background_rgb[0] - 70) <= 5
        assert abs(res.clean_background_rgb[1] - 82) <= 5
        assert abs(res.clean_background_rgb[2] - 25) <= 5
        assert res.confidence >= 0.9

    @pytest.mark.skipif(not CORPUS_COVER_PATH.exists(), reason="Corpus cover asset missing")
    def test_trim_shadow_and_infill_background_neutralizes_seam(self):
        img = Image.open(CORPUS_COVER_PATH)
        res = detect_spine_creases(img)
        assert res.shadow_bleed_right_px > 0

        infilled = trim_shadow_and_infill_background(img, res)
        assert infilled.size == img.size

        # Verify that in the infilled shadow region, the dark shadow trough is replaced
        infilled_arr = np.array(infilled)
        shadow_patch = infilled_arr[:, res.x_right : res.x_right + res.shadow_bleed_right_px, :]
        # All pixels in shadow patch should now match clean background
        expected_color = np.array(res.clean_background_rgb, dtype=np.uint8)
        diff = np.abs(shadow_patch.astype(int) - expected_color.astype(int))
        assert np.max(diff) == 0

    def test_trim_shadow_no_op_when_zero_bleed(self):
        arr = np.full((100, 200, 3), 150, dtype=np.uint8)
        img = Image.fromarray(arr)
        res = CreaseDetectionResult(
            x_left=80,
            x_right=120,
            spine_width_px=40,
            shadow_bleed_right_px=0,
            clean_background_rgb=(150, 150, 150),
            confidence=1.0,
        )
        out = trim_shadow_and_infill_background(img, res)
        assert np.array_equal(np.array(out), arr)
