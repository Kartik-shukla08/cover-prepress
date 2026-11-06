"""Comprehensive unit and API test suite for Markee Books Cover Studio."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import zipfile
import pytest
from fastapi.testclient import TestClient
import fitz
import numpy as np
from PIL import Image, ImageDraw

from mbooks.studio.server import app
from mbooks.cli import main


client = TestClient(app)


@pytest.fixture
def synthetic_cover_image(tmp_path: Path) -> Path:
    """Create a synthetic 3-panel cover wrap for testing crease detection and preview."""
    p = tmp_path / "synthetic_spread.png"
    # 1200 x 800 image with crease lines at 550 and 650
    img = Image.new("RGB", (1200, 800), (45, 55, 75))
    draw = ImageDraw.Draw(img)
    # Draw faint crease line
    draw.line([(550, 0), (550, 800)], fill=(90, 110, 140), width=1)
    draw.line([(650, 0), (650, 800)], fill=(90, 110, 140), width=1)
    # Bright spine element centered at x=600
    draw.rectangle([592, 250, 608, 550], fill=(255, 230, 100))
    img.save(p, format="PNG")
    return p


@pytest.fixture
def synthetic_panels(tmp_path: Path) -> dict[str, Path]:
    """Create separate front, spine, and back panel images."""
    front_p = tmp_path / "panel_front.png"
    spine_p = tmp_path / "panel_spine.png"
    back_p = tmp_path / "panel_back.png"

    Image.new("RGB", (600, 900), (30, 45, 70)).save(front_p)
    Image.new("RGB", (600, 900), (30, 45, 70)).save(back_p)

    spine_img = Image.new("RGB", (100, 900), (25, 35, 55))
    draw = ImageDraw.Draw(spine_img)
    draw.rectangle([40, 200, 60, 500], fill=(240, 220, 90))
    spine_img.save(spine_p)

    return {"front": front_p, "spine": spine_p, "back": back_p}


# ===========================================================================
# 1. Static Assets & Studio Index HTML Tests
# ===========================================================================

class TestStudioStaticFiles:
    """Verify HTML5 staff studio interface and static file serving."""

    def test_get_studio_index(self):
        """GET / returns 200 OK with HTML5 canvas and form elements."""
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        html = res.text
        assert "Markee Books" in html
        assert "Cover Studio" in html
        assert 'id="studio-canvas"' in html
        assert 'id="sel-publisher"' in html
        assert 'id="sel-binding"' in html
        assert 'id="sel-trim"' in html
        assert 'id="inp-pages"' in html
        assert 'id="btn-export-pdf"' in html
        assert 'id="btn-export-png"' in html
        assert 'id="btn-export-zip"' in html

    def test_get_static_js_and_css(self):
        """GET /static/studio.js and /static/studio.css return 200 OK."""
        res_js = client.get("/static/studio.js")
        assert res_js.status_code == 200
        assert "renderCanvas" in res_js.text

        res_css = client.get("/static/studio.css")
        assert res_css.status_code == 200
        assert "studio-canvas" in res_css.text


# ===========================================================================
# 2. Prepress Calculation Endpoint (/api/calculate) Tests
# ===========================================================================

class TestStudioCalculateApi:
    """Verify prepress calculation API across publishers and bindings."""

    def test_calculate_kdp_paperback_standard(self):
        """Calculate KDP paperback 6x9 150 pages."""
        payload = {
            "publisher": "kdp",
            "binding": "paperback",
            "trim_size": "6x9",
            "page_count": 150,
            "paper_type": "white",
            "ink_type": "black",
        }
        res = client.post("/api/calculate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        spec = data["spec"]
        assert spec["publisher"] == "kdp"
        assert spec["binding"] == "paperback"
        assert spec["trim_w_in"] == 6.0
        assert spec["trim_h_in"] == 9.0
        assert spec["bleed_in"] == 0.125
        assert spec["spine_safe_margin_in"] == 0.0625
        assert spec["allow_spine_text"] is True
        assert spec["total_w_in"] > 12.0
        assert len(spec["media_box"]) == 4

    def test_calculate_ingram_casewrap(self):
        """Calculate IngramSpark casewrap hardcover."""
        payload = {
            "publisher": "ingram",
            "binding": "casewrap",
            "trim_size": "5.5x8.5",
            "page_count": 250,
            "paper_type": "white",
            "ink_type": "black",
        }
        res = client.post("/api/calculate", json=payload)
        assert res.status_code == 200
        spec = res.json()["spec"]
        assert spec["publisher"] == "ingram"
        assert spec["binding"] == "casewrap"
        assert spec["hinge_in"] == 0.5

    def test_calculate_lulu_short_spine(self):
        """Calculate Lulu short-spine warning (< 80 pages)."""
        payload = {
            "publisher": "lulu",
            "binding": "paperback",
            "trim_size": "6x9",
            "page_count": 40,
        }
        res = client.post("/api/calculate", json=payload)
        assert res.status_code == 200
        spec = res.json()["spec"]
        assert spec["allow_spine_text"] is False
        assert spec["spine_text_warning"] is not None

    def test_calculate_custom_trim(self):
        """Calculate with explicit custom trim dimensions."""
        payload = {
            "publisher": "kdp",
            "binding": "paperback",
            "trim_w_in": 7.0,
            "trim_h_in": 10.0,
            "page_count": 200,
        }
        res = client.post("/api/calculate", json=payload)
        assert res.status_code == 200
        spec = res.json()["spec"]
        assert spec["trim_w_in"] == 7.0
        assert spec["trim_h_in"] == 10.0

    def test_calculate_invalid_publisher(self):
        """Invalid publisher returns 400 error."""
        res = client.post("/api/calculate", json={"publisher": "unknown", "page_count": 100})
        assert res.status_code == 400

    def test_calculate_get_healthcheck(self):
        """GET /api/calculate returns 200 OK default spec for Railway healthcheck."""
        res = client.get("/api/calculate")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["spec"]["publisher"] == "kdp"


# ===========================================================================
# 3. Crease Detection Endpoint (/api/crease-detect) Tests
# ===========================================================================

class TestStudioCreaseDetectApi:
    """Verify spine crease detection endpoint with multipart and JSON payloads."""

    def test_crease_detect_multipart_file(self, synthetic_cover_image: Path):
        """Multipart upload detects creases reliably."""
        with open(synthetic_cover_image, "rb") as f:
            res = client.post(
                "/api/crease-detect",
                files={"file": ("cover.png", f, "image/png")},
            )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert 500 <= data["x_left"] <= 580
        assert 620 <= data["x_right"] <= 700
        assert data["spine_width_px"] == data["x_right"] - data["x_left"]
        assert len(data["clean_background_rgb"]) == 3

    def test_crease_detect_json_base64(self, synthetic_cover_image: Path):
        """JSON payload with base64 data URI detects creases."""
        with open(synthetic_cover_image, "rb") as f:
            b64_str = base64.b64encode(f.read()).decode("ascii")
        res = client.post(
            "/api/crease-detect",
            json={"image_base64": f"data:image/png;base64,{b64_str}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["x_right"] > data["x_left"]

    def test_crease_detect_json_path(self, synthetic_cover_image: Path):
        """JSON payload with filesystem path detects creases."""
        res = client.post(
            "/api/crease-detect",
            json={"image_path": str(synthetic_cover_image)},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["x_left"] > 0

    def test_crease_detect_no_image_returns_400(self):
        """Missing image in request returns 400."""
        res = client.post("/api/crease-detect", json={})
        assert res.status_code == 400


# ===========================================================================
# 4. Preview & Guidelines Endpoint (/api/preview) Tests
# ===========================================================================

class TestStudioPreviewApi:
    """Verify live composite preview, guideline coordinates, and preflight calculations."""

    def test_preview_guidelines_without_image(self):
        """Preview without artwork returns computed skeletal guidelines and dimensions."""
        payload = {
            "publisher": "kdp",
            "binding": "paperback",
            "trim_size": "6x9",
            "page_count": 150,
            "dpi": 300,
        }
        res = client.post("/api/preview", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"

        guidelines = data["guidelines"]
        assert guidelines["width_px"] > 3000
        assert guidelines["height_px"] > 2500
        assert len(guidelines["trim_box"]) == 4
        assert len(guidelines["bleed_box"]) == 4
        assert guidelines["spine_creases"]["x_right"] > guidelines["spine_creases"]["x_left"]
        assert len(guidelines["spine_safe_zone"]) == 4
        assert len(guidelines["back_cover_safe_zone"]) == 4
        assert len(guidelines["front_cover_safe_zone"]) == 4
        assert data["preflight"]["status"] == "READY"

    def test_preview_casewrap_includes_hinges(self):
        """Preview for hardcover casewrap includes hinge guideline boxes."""
        payload = {
            "publisher": "ingram",
            "binding": "casewrap",
            "trim_size": "6x9",
            "page_count": 200,
            "dpi": 300,
        }
        res = client.post("/api/preview", json=payload)
        assert res.status_code == 200
        g = res.json()["guidelines"]
        assert g["hinges"] is not None
        assert "left_hinge" in g["hinges"]
        assert g["hinges"]["hinge_w_in"] == 0.5

    def test_preview_with_spread_artwork(self, synthetic_cover_image: Path):
        """Preview with uploaded spread artwork returns base64 images and preflight metrics."""
        with open(synthetic_cover_image, "rb") as f:
            res = client.post(
                "/api/preview",
                data={
                    "publisher": "kdp",
                    "binding": "paperback",
                    "trim_size": "6x9",
                    "page_count": 150,
                    "dpi": 300,
                },
                files={"file": ("spread.png", f, "image/png")},
            )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["preview_image_base64"] is not None
        assert data["preview_image_base64"].startswith("data:image/jpeg;base64,")
        assert data["proof_image_base64"] is not None
        assert data["proof_image_base64"].startswith("data:image/png;base64,")

        pf = data["preflight"]
        assert pf["status"] in ("PASS", "FAIL")
        assert "left_clearance_px" in pf
        assert "right_clearance_px" in pf
        assert "max_tac_pct" in pf

    def test_preview_with_overrides(self, synthetic_cover_image: Path):
        """Preview with manual spine bounds, shift, and safety buffer overrides."""
        with open(synthetic_cover_image, "rb") as f:
            res = client.post(
                "/api/preview",
                data={
                    "publisher": "kdp",
                    "binding": "paperback",
                    "trim_size": "6x9",
                    "page_count": 150,
                    "spine_bounds": "540,660",
                    "spine_shift_px": "4.5",
                    "safe_buffer_in": "0.025",
                    "dpi": 300,
                },
                files={"file": ("spread.png", f, "image/png")},
            )
        assert res.status_code == 200
        data = res.json()
        g = data["guidelines"]
        assert g["spine_creases"]["x_left"] == 540.0
        assert g["spine_creases"]["x_right"] == 660.0
        assert g["margins"]["spine_safe_margin_in"] == pytest.approx(0.0625 + 0.025, 0.001)

    def test_preview_with_separate_panels(self, synthetic_panels: dict[str, Path]):
        """Preview assembling separate front, spine, and back panels."""
        files = {
            "file_front": ("front.png", open(synthetic_panels["front"], "rb"), "image/png"),
            "file_spine": ("spine.png", open(synthetic_panels["spine"], "rb"), "image/png"),
            "file_back": ("back.png", open(synthetic_panels["back"], "rb"), "image/png"),
        }
        res = client.post(
            "/api/preview",
            data={
                "publisher": "kdp",
                "binding": "paperback",
                "trim_size": "6x9",
                "page_count": 150,
                "dpi": 300,
            },
            files=files,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["preview_image_base64"] is not None


# ===========================================================================
# 5. Export Endpoints (/api/export) Tests
# ===========================================================================

class TestStudioExportApi:
    """Verify print-ready export bundles for PDF, PNG, JPG, and ZIP."""

    def test_export_pdf_print_ready(self, synthetic_cover_image: Path):
        """Export print-ready PDF containing valid PDF page boxes."""
        with open(synthetic_cover_image, "rb") as f:
            res = client.post(
                "/api/export",
                data={
                    "format": "pdf",
                    "publisher": "kdp",
                    "binding": "paperback",
                    "trim_size": "6x9",
                    "page_count": 150,
                    "dpi": 300,
                },
                files={"file": ("spread.png", f, "image/png")},
            )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert "cover_spread_kdp" in res.headers["content-disposition"]

        # Validate with PyMuPDF
        pdf_doc = fitz.open(stream=res.content, filetype="pdf")
        assert len(pdf_doc) == 1
        page = pdf_doc[0]
        # Verify page boxes are defined
        assert page.rect.width > 0
        assert page.rect.height > 0
        pdf_doc.close()

    def test_export_png_spread(self, synthetic_cover_image: Path):
        """Export high-resolution PNG spread."""
        with open(synthetic_cover_image, "rb") as f:
            res = client.post(
                "/api/export",
                data={
                    "format": "png",
                    "publisher": "kdp",
                    "binding": "paperback",
                    "trim_size": "6x9",
                    "page_count": 150,
                    "dpi": 300,
                },
                files={"file": ("spread.png", f, "image/png")},
            )
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        img = Image.open(io.BytesIO(res.content))
        assert img.width > 3000
        assert img.height > 2500

    def test_export_jpg_spread(self, synthetic_cover_image: Path):
        """Export JPEG spread."""
        with open(synthetic_cover_image, "rb") as f:
            res = client.post(
                "/api/export",
                data={
                    "format": "jpg",
                    "publisher": "kdp",
                    "binding": "paperback",
                    "trim_size": "6x9",
                    "page_count": 150,
                    "dpi": 300,
                },
                files={"file": ("spread.png", f, "image/png")},
            )
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/jpeg"
        img = Image.open(io.BytesIO(res.content))
        assert img.format == "JPEG"

    def test_export_zip_bundle(self, synthetic_cover_image: Path):
        """Export comprehensive ZIP bundle with PDF, PNG, proof image, and JSON manifest."""
        with open(synthetic_cover_image, "rb") as f:
            res = client.post(
                "/api/export",
                data={
                    "format": "bundle",
                    "publisher": "ingram",
                    "binding": "paperback",
                    "trim_size": "6x9",
                    "page_count": 150,
                    "dpi": 300,
                },
                files={"file": ("spread.png", f, "image/png")},
            )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"

        zf = zipfile.ZipFile(io.BytesIO(res.content))
        file_list = zf.namelist()
        assert "print_ready_spread.pdf" in file_list
        assert "print_ready_spread.png" in file_list
        assert "diagnostic_proof.png" in file_list
        assert "prepress_manifest.json" in file_list

        manifest = json.loads(zf.read("prepress_manifest.json").decode("utf-8"))
        assert manifest["publisher"] == "ingram"
        assert "dimensions" in manifest
        assert "crease" in manifest
        assert "centering" in manifest

    def test_export_unsupported_format_returns_400(self):
        """Unsupported format returns 400 error."""
        res = client.post(
            "/api/export",
            json={"format": "docx", "publisher": "kdp", "page_count": 100},
        )
        assert res.status_code == 400


# ===========================================================================
# 5b. Modular Layer Decomposition Endpoint (/api/decompose) Tests
# ===========================================================================

class TestStudioDecomposeLayersApi:
    """Verify Canva-like modular layer decomposition and fixed skeletal guidelines."""

    def test_decompose_uploaded_cover(self, synthetic_cover_image: Path):
        """Decompose uploaded spread into Back, Spine BG, Spine Elements, and Front layers."""
        res = client.post(
            "/api/decompose",
            json={
                "image_path": str(synthetic_cover_image),
                "publisher": "kdp",
                "binding": "paperback",
                "trim_size": "6x9",
                "page_count": 150,
                "paper_type": "white",
                "ink_type": "color",
                "dpi": 300,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        # Authoritative target guidelines must stay at 1838..1939 on 3776x2775 canvas
        g = data["guidelines"]
        assert g["width_px"] == 3776
        assert g["height_px"] == 2775
        assert g["spine_creases"]["calculated_x_left"] == pytest.approx(1838.0, abs=1.0)
        assert g["spine_creases"]["calculated_x_right"] == pytest.approx(1939.0, abs=1.0)
        assert g["spine_safe_zone"][0] > 1850.0
        assert g["spine_safe_zone"][2] < 1925.0

        # Source spread cut metadata should report synthetic 1200x800 coordinates (~550..650)
        src = data["source_spread"]
        assert src["width"] == 1200
        assert src["height"] == 800
        assert 500 <= src["x_left"] <= 580
        assert 620 <= src["x_right"] <= 700

        # Layers must include back_panel, spine_bg, front_panel, and spine foreground elements
        layer_ids = [l["id"] for l in data["layers"]]
        assert "back_panel" in layer_ids
        assert "spine_bg" in layer_ids
        assert "front_panel" in layer_ids
        assert any(lid.startswith("spine_el_") for lid in layer_ids)
        assert data["preflight"]["is_safe"] is True



# ===========================================================================
# 6. CLI Integration Tests
# ===========================================================================

class TestCoverStudioCli:
    """Verify CLI subcommand registration and help text."""

    def test_cover_studio_help(self, capsys):
        """'mbooks cover-studio --help' outputs usage and exits 0."""
        with pytest.raises(SystemExit) as excinfo:
            main(["cover-studio", "--help"])
        assert excinfo.value.code == 0
        captured = capsys.readouterr()
        assert "cover-studio" in captured.out
        assert "--host" in captured.out
        assert "--port" in captured.out
        assert "--reload" in captured.out
