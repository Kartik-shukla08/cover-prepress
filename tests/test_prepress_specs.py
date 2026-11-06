"""Unit tests for mbooks.prepress.specs: multi-publisher prepress specification engine."""

import pytest
from mbooks.prepress.specs import calculate_prepress_spec, PrepressSpec


class TestPrepressSpecsKDP:
    """Tests for Amazon KDP specification calculations."""

    def test_kdp_paperback_6x9_150p_white(self):
        spec = calculate_prepress_spec(
            publisher="kdp",
            binding="paperback",
            trim_w_in=6.0,
            trim_h_in=9.0,
            page_count=150,
            paper_type="white",
            ink_type="black",
        )
        assert spec.publisher == "kdp"
        assert spec.binding == "paperback"
        assert spec.trim_w_in == 6.0
        assert spec.trim_h_in == 9.0
        assert spec.page_count == 150
        assert spec.bleed_in == 0.125
        assert spec.wrap_in == 0.0
        assert spec.hinge_in == 0.0
        assert spec.spine_w_in == pytest.approx(0.3378, abs=0.001)
        assert spec.total_w_in == pytest.approx(12.5878, abs=0.001)
        assert spec.total_h_in == pytest.approx(9.25, abs=0.001)
        assert spec.spine_safe_margin_in == 0.0625
        assert spec.cover_safe_margin_in == 0.125
        assert spec.allow_spine_text is True
        assert spec.spine_text_warning is None

        # PDF Box tests (in points, 72 pt = 1 in)
        expected_w_pt = round(spec.total_w_in * 72.0, 3)
        expected_h_pt = round(spec.total_h_in * 72.0, 3)
        assert spec.media_box == (0.0, 0.0, expected_w_pt, expected_h_pt)
        assert spec.bleed_box == (0.0, 0.0, expected_w_pt, expected_h_pt)
        assert spec.crop_box == (0.0, 0.0, expected_w_pt, expected_h_pt)
        assert spec.trim_box == (9.0, 9.0, expected_w_pt - 9.0, expected_h_pt - 9.0)

    def test_kdp_casewrap_6x9_150p(self):
        spec = calculate_prepress_spec(
            publisher="kdp",
            binding="casewrap",
            trim_w_in=6.0,
            trim_h_in=9.0,
            page_count=150,
            paper_type="white",
        )
        assert spec.binding == "casewrap"
        assert spec.wrap_in == 0.591
        assert spec.hinge_in == 0.394
        assert spec.spine_w_in == pytest.approx(0.53, abs=0.01)
        assert spec.total_w_in == pytest.approx(14.105, abs=0.01)
        assert spec.total_h_in == pytest.approx(10.417, abs=0.01)
        assert spec.spine_safe_margin_in == 0.0625

        wrap_pt = round(0.591 * 72.0, 3)
        assert spec.trim_box[0] == wrap_pt
        assert spec.trim_box[1] == wrap_pt

    def test_kdp_short_spine_threshold(self):
        # 79 pages -> text prohibited
        spec_79 = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 79)
        assert spec_79.allow_spine_text is False
        assert spec_79.spine_text_warning is not None
        assert "below KDP minimum threshold of 80 pages" in spec_79.spine_text_warning

        # 80 pages -> text permitted
        spec_80 = calculate_prepress_spec("kdp", "paperback", 6.0, 9.0, 80)
        assert spec_80.allow_spine_text is True
        assert spec_80.spine_text_warning is None


class TestPrepressSpecsIngramSpark:
    """Tests for IngramSpark specification calculations."""

    def test_ingram_paperback_narrow_spine_safety_step(self):
        # 150p White: spine is ~0.3215" (< 0.350") -> safe margin steps down to 0.03125" (1/32")
        spec_thin = calculate_prepress_spec("ingram", "paperback", 6.0, 9.0, 150)
        assert spec_thin.publisher == "ingram"
        assert spec_thin.spine_w_in < 0.350
        assert spec_thin.spine_safe_margin_in == 0.03125
        assert spec_thin.cover_safe_margin_in == 0.250
        assert spec_thin.allow_spine_text is True

        # 300p White: spine is > 0.350" -> safe margin is 0.0625" (1/16")
        spec_thick = calculate_prepress_spec("ingram", "paperback", 6.0, 9.0, 300)
        assert spec_thick.spine_w_in >= 0.350
        assert spec_thick.spine_safe_margin_in == 0.0625

    def test_ingram_casewrap_dimensions(self):
        spec = calculate_prepress_spec("ingram", "casewrap", 6.0, 9.0, 150)
        assert spec.binding == "casewrap"
        assert spec.wrap_in == 0.625
        assert spec.hinge_in == 0.500
        assert spec.total_h_in == pytest.approx(10.50, abs=0.01)
        assert spec.total_w_in == pytest.approx(14.26, abs=0.05)

    def test_ingram_short_spine_threshold(self):
        # 47 pages -> prohibited
        spec_47 = calculate_prepress_spec("ingram", "paperback", 6.0, 9.0, 47)
        assert spec_47.allow_spine_text is False
        assert "below IngramSpark minimum threshold of 48 pages" in spec_47.spine_text_warning

        # 48 pages -> permitted
        spec_48 = calculate_prepress_spec("ingram", "paperback", 6.0, 9.0, 48)
        assert spec_48.allow_spine_text is True
        assert spec_48.spine_text_warning is None


class TestPrepressSpecsLulu:
    """Tests for Lulu specification calculations."""

    def test_lulu_paperback_6x9_150p(self):
        spec = calculate_prepress_spec("lulu", "paperback", 6.0, 9.0, 150)
        assert spec.publisher == "lulu"
        assert spec.spine_w_in == pytest.approx(150 / 444 + 0.060, abs=0.001)
        assert spec.spine_safe_margin_in == 0.125
        assert spec.cover_safe_margin_in == 0.500
        assert spec.bleed_in == 0.125
        assert spec.total_h_in == 9.25

    def test_lulu_casewrap_discrete_table(self):
        spec = calculate_prepress_spec("lulu", "casewrap", 6.0, 9.0, 150)
        assert spec.binding == "casewrap"
        assert spec.spine_w_in == 0.625  # Discrete step lookup for 150p
        assert spec.wrap_in == 0.750
        assert spec.hinge_in == 0.125
        assert spec.total_w_in == 14.375
        assert spec.total_h_in == 10.75
        assert spec.spine_safe_margin_in == 0.125

    def test_lulu_short_spine_threshold(self):
        # 80 pages -> prohibited (Lulu requires > 80 pages)
        spec_80 = calculate_prepress_spec("lulu", "paperback", 6.0, 9.0, 80)
        assert spec_80.allow_spine_text is False
        assert "below Lulu minimum threshold of 81 pages" in spec_80.spine_text_warning

        # 81 pages -> permitted
        spec_81 = calculate_prepress_spec("lulu", "paperback", 6.0, 9.0, 81)
        assert spec_81.allow_spine_text is True
        assert spec_81.spine_text_warning is None


class TestPrepressSpecsNormalization:
    """Tests for input validation and case/string normalization."""

    @pytest.mark.parametrize("pub_input,expected", [
        ("KDP", "kdp"),
        ("Amazon KDP", "kdp"),
        ("ingramspark", "ingram"),
        ("INGRAM", "ingram"),
        ("Lulu", "lulu"),
    ])
    def test_publisher_normalization(self, pub_input, expected):
        spec = calculate_prepress_spec(pub_input, "paperback", 6.0, 9.0, 150)
        assert spec.publisher == expected

    @pytest.mark.parametrize("bind_input,expected", [
        ("Paperback", "paperback"),
        ("softcover", "paperback"),
        ("perfect bound", "paperback"),
        ("Casewrap", "casewrap"),
        ("hardcover", "casewrap"),
    ])
    def test_binding_normalization(self, bind_input, expected):
        spec = calculate_prepress_spec("kdp", bind_input, 6.0, 9.0, 150)
        assert spec.binding == expected

    def test_invalid_publisher_raises(self):
        with pytest.raises(ValueError, match="Unsupported publisher"):
            calculate_prepress_spec("blurb", "paperback", 6.0, 9.0, 150)

    def test_invalid_binding_raises(self):
        with pytest.raises(ValueError, match="Unsupported binding"):
            calculate_prepress_spec("kdp", "spiral", 6.0, 9.0, 150)
