"""FastAPI server for Markee Books Local Web Studio."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import zipfile

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from mbooks.domain.geometry import TrimSize
from mbooks.prepress.specs import (
    PrepressSpec,
    calculate_prepress_spec,
    _normalize_publisher,
    _normalize_binding,
)
from mbooks.prepress.crease import (
    CreaseDetectionResult,
    detect_spine_creases,
)
from mbooks.prepress.resizer import (
    ResizeOptions,
    resize_cover_wrap,
    ResizeResult,
    decompose_cover_to_layers,
)
from mbooks.prepress.centering import CenteringResult
from mbooks.prepress.pdf import (
    export_print_ready_pdf,
    inspect_tac_and_registration,
    PUBLISHER_TAC_LIMITS,
)
from mbooks.prepress.proof import generate_diagnostic_proof


STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Markee Books Cover Studio",
    description="Interactive local prepress web studio for book cover wrap assembly and proofing.",
    version="2.0.0",
)


@app.middleware("http")
async def disable_static_cache(request: Request, call_next):
    """Ensure browser never caches stale HTML, CSS, or JS assets during local studio updates."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ---------------------------------------------------------------------------
# Helper models and utilities
# ---------------------------------------------------------------------------

class CalculateRequest(BaseModel):
    publisher: str
    binding: str
    trim_size: Optional[str] = "6x9"
    trim_w_in: Optional[float] = None
    trim_h_in: Optional[float] = None
    page_count: int
    paper_type: str = "white"
    ink_type: str = "black"


def _parse_trim_dimensions(
    trim_size: Optional[str],
    trim_w_in: Optional[float],
    trim_h_in: Optional[float],
) -> Tuple[float, float]:
    """Resolve width and height from explicit floats or trim string."""
    if trim_w_in is not None and trim_h_in is not None:
        if trim_w_in <= 0 or trim_h_in <= 0:
            raise ValueError(f"Trim dimensions must be positive: {trim_w_in}x{trim_h_in}")
        return float(trim_w_in), float(trim_h_in)
    if not trim_size:
        return 6.0, 9.0
    try:
        t = TrimSize.from_string(trim_size)
        return float(t.width), float(t.height)
    except Exception as e:
        raise ValueError(f"Invalid trim size format: '{trim_size}': {e}")


def _load_image_from_bytes(data: bytes) -> Image.Image:
    """Load and normalize PIL image from raw bytes."""
    try:
        bio = io.BytesIO(data)
        with Image.open(bio) as img:
            img.load()
            return img.copy()
    except Exception as e:
        raise ValueError(f"Failed to decode image: {e}")


def _load_image_from_base64_or_path(val: str) -> Image.Image:
    """Load image from base64 data URI, raw base64, or existing filesystem path."""
    val = val.strip()
    if val.startswith("data:image"):
        parts = val.split(",", 1)
        if len(parts) == 2:
            val = parts[1]
    # Check if filesystem path
    p = Path(val)
    if p.exists() and p.is_file():
        try:
            with Image.open(p) as img:
                img.load()
                return img.copy()
        except Exception as e:
            raise ValueError(f"Failed to read image at '{val}': {e}")
    # Otherwise try base64 decode
    try:
        raw = base64.b64decode(val)
        return _load_image_from_bytes(raw)
    except Exception as e:
        raise ValueError(f"Unable to load image from value (neither valid path nor base64): {e}")


def _image_to_base64(img: Image.Image, format: str = "PNG") -> str:
    """Encode PIL image to base64 data URI."""
    bio = io.BytesIO()
    img.save(bio, format=format)
    encoded = base64.b64encode(bio.getvalue()).decode("ascii")
    mime = "image/png" if format.upper() == "PNG" else "image/jpeg"
    return f"data:{mime};base64,{encoded}"


def _compute_guideline_coordinates(
    spec: PrepressSpec,
    dpi: int,
    safe_buffer_in: float = 0.0,
    override_spine_bounds: Optional[Tuple[int, int]] = None,
) -> Dict[str, Any]:
    """Compute exact pixel coordinates for canvas guideline overlays."""
    W = int(round(spec.total_w_in * dpi))
    H = int(round(spec.total_h_in * dpi))

    if spec.binding == "paperback":
        bleed_px = spec.bleed_in * dpi
        trim_box = [
            round(bleed_px, 1),
            round(bleed_px, 1),
            round(W - bleed_px, 1),
            round(H - bleed_px, 1),
        ]
        x_fold_left = round((spec.bleed_in + spec.trim_w_in) * dpi, 1)
        spine_w_px = round(spec.spine_w_in * dpi, 1)
        x_fold_right = round(x_fold_left + spine_w_px, 1)
        hinges = None
    else:
        # Casewrap hardcover
        wrap_px = spec.wrap_in * dpi
        trim_box = [
            round(wrap_px, 1),
            round(wrap_px, 1),
            round(W - wrap_px, 1),
            round(H - wrap_px, 1),
        ]
        board_w_in = (
            spec.total_w_in
            - spec.spine_w_in
            - 2.0 * spec.wrap_in
            - 2.0 * spec.hinge_in
        ) / 2.0
        x_fold_left = round((spec.wrap_in + board_w_in + spec.hinge_in) * dpi, 1)
        spine_w_px = round(spec.spine_w_in * dpi, 1)
        x_fold_right = round(x_fold_left + spine_w_px, 1)
        hinge_left_x0 = round((spec.wrap_in + board_w_in) * dpi, 1)
        hinge_left_x1 = x_fold_left
        hinge_right_x0 = x_fold_right
        hinge_right_x1 = round(x_fold_right + spec.hinge_in * dpi, 1)
        hinges = {
            "left_hinge": [hinge_left_x0, trim_box[1], hinge_left_x1, trim_box[3]],
            "right_hinge": [hinge_right_x0, trim_box[1], hinge_right_x1, trim_box[3]],
            "hinge_w_in": spec.hinge_in,
            "hinge_w_px": round(spec.hinge_in * dpi, 1),
        }

    # Crease bounds (default calculated or source-override metadata)
    if override_spine_bounds:
        crease_left = float(override_spine_bounds[0])
        crease_right = float(override_spine_bounds[1])
    else:
        crease_left = x_fold_left
        crease_right = x_fold_right

    # Target canvas skeletal zones ALWAYS use calculated target fold lines (x_fold_left, x_fold_right)
    safe_margin_in = spec.spine_safe_margin_in + safe_buffer_in
    safe_margin_px = safe_margin_in * dpi
    spine_safe_zone = [
        round(x_fold_left + safe_margin_px, 1),
        round(trim_box[1], 1),
        round(x_fold_right - safe_margin_px, 1),
        round(trim_box[3], 1),
    ]

    # Cover safe zone (back and front panels)
    cover_safe_px = spec.cover_safe_margin_in * dpi
    back_cover_safe_zone = [
        round(trim_box[0] + cover_safe_px, 1),
        round(trim_box[1] + cover_safe_px, 1),
        round(x_fold_left - cover_safe_px, 1),
        round(trim_box[3] - cover_safe_px, 1),
    ]
    front_cover_safe_zone = [
        round(x_fold_right + cover_safe_px, 1),
        round(trim_box[1] + cover_safe_px, 1),
        round(trim_box[2] - cover_safe_px, 1),
        round(trim_box[3] - cover_safe_px, 1),
    ]

    # Standard 2.0" x 1.2" ISBN Barcode reservation zone on back cover lower-right safe margin
    barcode_w_px = round(2.0 * dpi, 1)
    barcode_h_px = round(1.2 * dpi, 1)
    barcode_x1 = round(x_fold_left - max(cover_safe_px, 0.25 * dpi), 1)
    barcode_y1 = round(trim_box[3] - max(cover_safe_px, 0.25 * dpi), 1)
    barcode_zone = [
        round(barcode_x1 - barcode_w_px, 1),
        round(barcode_y1 - barcode_h_px, 1),
        barcode_x1,
        barcode_y1,
    ]

    return {
        "width_px": W,
        "height_px": H,
        "dpi": dpi,
        "bleed_box": [0.0, 0.0, float(W), float(H)],
        "trim_box": trim_box,
        "spine_creases": {
            "x_left": crease_left,
            "x_right": crease_right,
            "spine_width_px": round(crease_right - crease_left, 1),
            "calculated_x_left": x_fold_left,
            "calculated_x_right": x_fold_right,
        },
        "hinges": hinges,
        "spine_safe_zone": spine_safe_zone,
        "back_cover_safe_zone": back_cover_safe_zone,
        "front_cover_safe_zone": front_cover_safe_zone,
        "barcode_zone": barcode_zone,
        "margins": {
            "bleed_in": spec.bleed_in,
            "wrap_in": spec.wrap_in,
            "hinge_in": spec.hinge_in,
            "spine_safe_margin_in": round(safe_margin_in, 4),
            "spine_safe_margin_px": round(safe_margin_px, 1),
            "cover_safe_margin_in": spec.cover_safe_margin_in,
            "cover_safe_margin_px": round(cover_safe_px, 1),
        },
    }


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_studio_index():
    """Serve the interactive staff Web Studio interface."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Studio index.html not found.")
    return FileResponse(index_file, media_type="text/html")


@app.post("/api/calculate")
async def api_calculate(request: Request):
    """Compute prepress specifications across KDP, IngramSpark, and Lulu."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        publisher = str(data.get("publisher", "kdp"))
        binding = str(data.get("binding", "paperback"))
        page_count = int(data.get("page_count", 150))
        paper_type = str(data.get("paper_type", "white"))
        ink_type = str(data.get("ink_type", "black"))

        trim_size = data.get("trim_size")
        trim_w = float(data["trim_w_in"]) if "trim_w_in" in data and data["trim_w_in"] is not None else None
        trim_h = float(data["trim_h_in"]) if "trim_h_in" in data and data["trim_h_in"] is not None else None

        w_in, h_in = _parse_trim_dimensions(trim_size, trim_w, trim_h)

        spec = calculate_prepress_spec(
            publisher=publisher,
            binding=binding,
            trim_w_in=w_in,
            trim_h_in=h_in,
            page_count=page_count,
            paper_type=paper_type,
            ink_type=ink_type,
        )

        return {
            "status": "success",
            "spec": spec.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/crease-detect")
async def api_crease_detect(request: Request):
    """Detect spine crease boundaries on an uploaded image or local image path."""
    try:
        content_type = request.headers.get("content-type", "")
        img: Optional[Image.Image] = None

        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("file")
            if upload and hasattr(upload, "read"):
                content = await upload.read()
                img = _load_image_from_bytes(content)
            elif "image_path" in form:
                img = _load_image_from_base64_or_path(str(form["image_path"]))
        else:
            data = await request.json()
            if "image_base64" in data and data["image_base64"]:
                img = _load_image_from_base64_or_path(data["image_base64"])
            elif "image_path" in data and data["image_path"]:
                img = _load_image_from_base64_or_path(data["image_path"])

        if img is None:
            raise HTTPException(
                status_code=400,
                detail="No image provided. Supply 'file' in multipart form or 'image_path'/'image_base64' in JSON.",
            )

        crease_res = detect_spine_creases(img)
        return {
            "status": "success",
            "x_left": crease_res.x_left,
            "x_right": crease_res.x_right,
            "spine_width_px": crease_res.spine_width_px,
            "shadow_bleed_right_px": crease_res.shadow_bleed_right_px,
            "clean_background_rgb": crease_res.clean_background_rgb,
            "confidence": crease_res.confidence,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Crease detection error: {e}")


@app.post("/api/preview")
async def api_preview(request: Request):
    """Render live composite preview, preflight diagnostics, and guideline box coordinates."""
    try:
        content_type = request.headers.get("content-type", "")
        uploaded_panels: Dict[str, Image.Image] = {}
        single_img: Optional[Image.Image] = None

        if "multipart/form-data" in content_type:
            form = await request.form()
            raw_data = dict(form)

            # Check single spread upload
            if "file" in form and hasattr(form["file"], "read"):
                f = form["file"]
                data_bytes = await f.read()
                if len(data_bytes) > 0:
                    single_img = _load_image_from_bytes(data_bytes)

            # Check separate panel uploads
            for panel in ("front", "spine", "back"):
                k = f"file_{panel}"
                if k in form and hasattr(form[k], "read"):
                    data_bytes = await form[k].read()
                    if len(data_bytes) > 0:
                        uploaded_panels[panel] = _load_image_from_bytes(data_bytes)
        else:
            raw_data = await request.json()
            if "image_base64" in raw_data and raw_data["image_base64"]:
                single_img = _load_image_from_base64_or_path(raw_data["image_base64"])
            elif "image_path" in raw_data and raw_data["image_path"]:
                single_img = _load_image_from_base64_or_path(raw_data["image_path"])

            # Check panels in JSON
            if "panels" in raw_data and isinstance(raw_data["panels"], dict):
                for p_k, p_val in raw_data["panels"].items():
                    if p_val:
                        uploaded_panels[p_k] = _load_image_from_base64_or_path(p_val)

        publisher = str(raw_data.get("publisher", "kdp"))
        binding = str(raw_data.get("binding", "paperback"))
        page_count = int(raw_data.get("page_count", 150))
        paper_type = str(raw_data.get("paper_type", "white"))
        ink_type = str(raw_data.get("ink_type", "black"))
        dpi = int(raw_data.get("dpi", 300))

        trim_size = raw_data.get("trim_size")
        trim_w = float(raw_data["trim_w_in"]) if "trim_w_in" in raw_data and raw_data["trim_w_in"] is not None else None
        trim_h = float(raw_data["trim_h_in"]) if "trim_h_in" in raw_data and raw_data["trim_h_in"] is not None else None
        w_in, h_in = _parse_trim_dimensions(trim_size, trim_w, trim_h)

        # Overrides
        spine_shift_px = float(raw_data.get("spine_shift_px", 0.0))
        safe_buffer_in = float(raw_data.get("safe_buffer_in", 0.0))

        override_bounds: Optional[Tuple[int, int]] = None
        spine_bounds_val = raw_data.get("spine_bounds")
        if spine_bounds_val:
            if isinstance(spine_bounds_val, str) and "," in spine_bounds_val:
                pts = [int(p.strip()) for p in spine_bounds_val.split(",")]
                override_bounds = (pts[0], pts[1])
            elif isinstance(spine_bounds_val, (list, tuple)) and len(spine_bounds_val) == 2:
                override_bounds = (int(spine_bounds_val[0]), int(spine_bounds_val[1]))

        # Calculate spec
        spec = calculate_prepress_spec(
            publisher=publisher,
            binding=binding,
            trim_w_in=w_in,
            trim_h_in=h_in,
            page_count=page_count,
            paper_type=paper_type,
            ink_type=ink_type,
        )

        guidelines = _compute_guideline_coordinates(
            spec=spec,
            dpi=dpi,
            safe_buffer_in=safe_buffer_in,
            override_spine_bounds=override_bounds,
        )

        preview_img_b64: Optional[str] = None
        proof_img_b64: Optional[str] = None
        preflight_info: Dict[str, Any] = {
            "status": "READY",
            "is_safe": True,
            "allow_spine_text": spec.allow_spine_text,
            "warnings": [spec.spine_text_warning] if spec.spine_text_warning else [],
        }

        # If artwork provided, perform wrap resizing / proofing
        input_data: Optional[Union[Image.Image, Dict[str, Image.Image]]] = None
        if uploaded_panels and "front" in uploaded_panels and "back" in uploaded_panels:
            input_data = uploaded_panels
        elif single_img is not None:
            input_data = single_img

        if input_data is not None:
            trim_str = trim_size if trim_size else f"{w_in}x{h_in}"
            options = ResizeOptions(
                publisher=spec.publisher,
                binding=spec.binding,
                trim_size=trim_str,
                page_count=spec.page_count,
                paper_type=spec.paper_type,
                ink_type=spec.ink_type,
                dpi=dpi,
                override_spine_bounds=override_bounds,
                spine_shift_px=spine_shift_px,
                safe_buffer_in=safe_buffer_in,
            )

            resize_res = resize_cover_wrap(input_data, options)

            # Check TAC and registration black
            tac_ceiling = PUBLISHER_TAC_LIMITS.get(spec.publisher, 300.0)
            max_tac_pct, has_tac_breach, has_reg_black = inspect_tac_and_registration(
                resize_res.spread_image, tac_ceiling=tac_ceiling
            )

            effective_dpi = (
                round(single_img.width / spec.total_w_in, 1)
                if isinstance(input_data, Image.Image)
                else float(dpi)
            )

            left_buf_px = resize_res.centering.left_clearance_px - resize_res.centering.safe_margin_px
            right_buf_px = resize_res.centering.right_clearance_px - resize_res.centering.safe_margin_px
            left_pass = left_buf_px >= -0.05
            right_pass = right_buf_px >= -0.05

            warnings = list(resize_res.warnings)
            if has_reg_black:
                warnings.append("400% registration black detected on artwork.")
            if has_tac_breach:
                warnings.append(f"Total Area Coverage ({max_tac_pct:.1f}%) exceeds {spec.publisher.upper()} ceiling of {tac_ceiling:.1f}%.")
            if effective_dpi < 150.0:
                warnings.append(f"Low input resolution ({effective_dpi} DPI). Recommended is >= 300 DPI.")

            is_pass = resize_res.centering.is_safe and not has_tac_breach and not has_reg_black

            preflight_info = {
                "status": "PASS" if is_pass else "FAIL",
                "is_safe": resize_res.centering.is_safe,
                "left_clearance_px": resize_res.centering.left_clearance_px,
                "right_clearance_px": resize_res.centering.right_clearance_px,
                "safe_margin_px": resize_res.centering.safe_margin_px,
                "left_buffer_px": round(left_buf_px, 2),
                "right_buffer_px": round(right_buf_px, 2),
                "left_pass": left_pass,
                "right_pass": right_pass,
                "optical_center_x_px": resize_res.centering.optical_center_x_px,
                "geometric_center_x_px": resize_res.centering.geometric_center_x_px,
                "shift_x_px": resize_res.centering.shift_x_px,
                "effective_dpi": effective_dpi,
                "max_tac_pct": max_tac_pct,
                "tac_ceiling": tac_ceiling,
                "tac_pass": not has_tac_breach,
                "registration_black": has_reg_black,
                "allow_spine_text": spec.allow_spine_text,
                "warnings": warnings,
            }

            # Generate preview thumbnail (max 1200px width for fast response)
            thumb = resize_res.spread_image.copy()
            if thumb.width > 1200:
                thumb_h = int(round(thumb.height * (1200 / thumb.width)))
                thumb = thumb.resize((1200, thumb_h), Image.Resampling.LANCZOS)
            preview_img_b64 = _image_to_base64(thumb, format="JPEG")

            # Generate diagnostic proof image
            proof_bio = io.BytesIO()
            # Proof generator writes to path, so we can generate to an in-memory buffer or temp
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                tmp_proof_path = tf.name
            try:
                generate_diagnostic_proof(
                    spread_image=resize_res.spread_image,
                    spec=spec,
                    centering=resize_res.centering,
                    crease=resize_res.crease_detection,
                    output_path=tmp_proof_path,
                    dpi=150,  # 150 DPI for snappy web preview
                )
                with open(tmp_proof_path, "rb") as pf:
                    proof_raw = pf.read()
                proof_img_b64 = f"data:image/png;base64,{base64.b64encode(proof_raw).decode('ascii')}"
            finally:
                if Path(tmp_proof_path).exists():
                    Path(tmp_proof_path).unlink()

        return {
            "status": "success",
            "spec": spec.model_dump(),
            "guidelines": guidelines,
            "preflight": preflight_info,
            "preview_image_base64": preview_img_b64,
            "proof_image_base64": proof_img_b64,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Preview error: {e}")


@app.post("/api/decompose")
async def api_decompose(request: Request):
    """Decompose uploaded spread or sample cover into modular editable layers for the Canva-like studio."""
    try:
        content_type = request.headers.get("content-type", "")
        single_img: Optional[Image.Image] = None
        uploaded_panels: Dict[str, Image.Image] = {}

        if "multipart/form-data" in content_type:
            form = await request.form()
            raw_data = dict(form)
            if "file" in form and hasattr(form["file"], "read"):
                f = form["file"]
                data_bytes = await f.read()
                if len(data_bytes) > 0:
                    single_img = _load_image_from_bytes(data_bytes)
            for panel in ("front", "spine", "back"):
                k = f"file_{panel}"
                if k in form and hasattr(form[k], "read"):
                    data_bytes = await form[k].read()
                    if len(data_bytes) > 0:
                        uploaded_panels[panel] = _load_image_from_bytes(data_bytes)
        else:
            raw_data = await request.json()
            if "image_base64" in raw_data and raw_data["image_base64"]:
                single_img = _load_image_from_base64_or_path(raw_data["image_base64"])
            elif "image_path" in raw_data and raw_data["image_path"]:
                single_img = _load_image_from_base64_or_path(raw_data["image_path"])

        if single_img is None and str(raw_data.get("use_sample", "")).lower() == "denise":
            # Locate Denise reference cover in repository corpus
            sample_name = "Denise_Hinton_Bazemore_-_That_show_lives_on_-_Cover_Design_2_3.jpeg"
            candidates = [
                Path.cwd() / "corpus" / sample_name,
                Path(__file__).resolve().parents[5] / "corpus" / sample_name,
                Path(__file__).resolve().parents[4] / "corpus" / sample_name,
            ]
            for sample_path in candidates:
                if sample_path.exists():
                    with Image.open(sample_path) as simg:
                        simg.load()
                        single_img = simg.copy()
                    break

        publisher = str(raw_data.get("publisher", "kdp"))
        binding = str(raw_data.get("binding", "paperback"))
        page_count = int(raw_data.get("page_count", 150))
        paper_type = str(raw_data.get("paper_type", "white"))
        ink_type = str(raw_data.get("ink_type", "color"))
        dpi = int(raw_data.get("dpi", 300))

        trim_size = raw_data.get("trim_size")
        trim_w = float(raw_data["trim_w_in"]) if "trim_w_in" in raw_data and raw_data["trim_w_in"] is not None else None
        trim_h = float(raw_data["trim_h_in"]) if "trim_h_in" in raw_data and raw_data["trim_h_in"] is not None else None
        w_in, h_in = _parse_trim_dimensions(trim_size, trim_w, trim_h)

        spine_shift_px = float(raw_data.get("spine_shift_px", 0.0))
        safe_buffer_in = float(raw_data.get("safe_buffer_in", 0.0))

        override_bounds: Optional[Tuple[int, int]] = None
        spine_bounds_val = raw_data.get("spine_bounds")
        if spine_bounds_val:
            if isinstance(spine_bounds_val, str) and "," in spine_bounds_val:
                pts = [int(float(p.strip())) for p in spine_bounds_val.split(",")]
                override_bounds = (pts[0], pts[1])
            elif isinstance(spine_bounds_val, (list, tuple)) and len(spine_bounds_val) == 2:
                override_bounds = (int(float(spine_bounds_val[0])), int(float(spine_bounds_val[1])))

        spec = calculate_prepress_spec(
            publisher=publisher,
            binding=binding,
            trim_w_in=w_in,
            trim_h_in=h_in,
            page_count=page_count,
            paper_type=paper_type,
            ink_type=ink_type,
        )
        guidelines = _compute_guideline_coordinates(
            spec=spec,
            dpi=dpi,
            safe_buffer_in=safe_buffer_in,
            override_spine_bounds=override_bounds,
        )

        trim_str = trim_size if trim_size else f"{w_in}x{h_in}"
        options = ResizeOptions(
            publisher=spec.publisher,
            binding=spec.binding,
            trim_size=trim_str,
            page_count=spec.page_count,
            paper_type=spec.paper_type,
            ink_type=spec.ink_type,
            dpi=dpi,
            override_spine_bounds=override_bounds,
            spine_shift_px=spine_shift_px,
            safe_buffer_in=safe_buffer_in,
        )

        if single_img is not None:
            decomp = decompose_cover_to_layers(single_img, options)
            resize_res = decomp.resize_result

            serialized_layers = []
            for lyr in decomp.layers:
                fmt = "PNG" if lyr.image.mode == "RGBA" else "JPEG"
                serialized_layers.append(
                    {
                        "id": lyr.id,
                        "name": lyr.name,
                        "kind": lyr.kind,
                        "image_base64": _image_to_base64(lyr.image, format=fmt),
                        "x": lyr.x,
                        "y": lyr.y,
                        "w": lyr.w,
                        "h": lyr.h,
                        "orig_x": lyr.x,
                        "orig_y": lyr.y,
                        "orig_w": lyr.w,
                        "orig_h": lyr.h,
                        "lock_aspect": lyr.lock_aspect,
                        "group_id": lyr.group_id,
                        "glyph_left_ratio": lyr.glyph_left_ratio,
                        "glyph_right_ratio": lyr.glyph_right_ratio,
                        "crop": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
                        "visible": True,
                    }
                )

            source_info = {
                "image_base64": _image_to_base64(single_img.convert("RGB"), format="JPEG"),
                "width": decomp.source_width,
                "height": decomp.source_height,
                "x_left": decomp.source_x_left,
                "x_right": decomp.source_x_right,
                "actual_crease_trim_px": decomp.actual_crease_trim_px,
            }
        elif uploaded_panels and "front" in uploaded_panels and "back" in uploaded_panels:
            resize_res = resize_cover_wrap(uploaded_panels, options)
            x_fl = guidelines["spine_creases"]["calculated_x_left"]
            x_fr = guidelines["spine_creases"]["calculated_x_right"]
            W_px = guidelines["width_px"]
            H_px = guidelines["height_px"]
            back_img = uploaded_panels["back"].convert("RGB").resize((int(round(x_fl)), H_px), Image.Resampling.LANCZOS)
            front_img = uploaded_panels["front"].convert("RGB").resize((int(round(W_px - x_fr)), H_px), Image.Resampling.LANCZOS)
            sp_img = (
                uploaded_panels["spine"].convert("RGB").resize((int(round(x_fr - x_fl)), H_px), Image.Resampling.LANCZOS)
                if "spine" in uploaded_panels
                else Image.new("RGB", (int(round(x_fr - x_fl)), H_px), (45, 55, 35))
            )
            serialized_layers = [
                {
                    "id": "back_panel",
                    "name": "Back Cover Panel",
                    "kind": "panel",
                    "image_base64": _image_to_base64(back_img, format="JPEG"),
                    "x": 0.0,
                    "y": 0.0,
                    "w": float(x_fl),
                    "h": float(H_px),
                    "orig_x": 0.0,
                    "orig_y": 0.0,
                    "orig_w": float(x_fl),
                    "orig_h": float(H_px),
                    "lock_aspect": False,
                    "group_id": None,
                    "glyph_left_ratio": 0.0,
                    "glyph_right_ratio": 1.0,
                    "crop": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
                    "visible": True,
                },
                {
                    "id": "spine_bg",
                    "name": "Spine Panel",
                    "kind": "spine_bg",
                    "image_base64": _image_to_base64(sp_img, format="JPEG"),
                    "x": float(x_fl),
                    "y": 0.0,
                    "w": float(x_fr - x_fl),
                    "h": float(H_px),
                    "orig_x": float(x_fl),
                    "orig_y": 0.0,
                    "orig_w": float(x_fr - x_fl),
                    "orig_h": float(H_px),
                    "lock_aspect": False,
                    "group_id": "spine_group",
                    "glyph_left_ratio": 0.0,
                    "glyph_right_ratio": 1.0,
                    "crop": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
                    "visible": True,
                },
                {
                    "id": "front_panel",
                    "name": "Front Cover Panel",
                    "kind": "panel",
                    "image_base64": _image_to_base64(front_img, format="JPEG"),
                    "x": float(x_fr),
                    "y": 0.0,
                    "w": float(W_px - x_fr),
                    "h": float(H_px),
                    "orig_x": float(x_fr),
                    "orig_y": 0.0,
                    "orig_w": float(W_px - x_fr),
                    "orig_h": float(H_px),
                    "lock_aspect": False,
                    "group_id": None,
                    "glyph_left_ratio": 0.0,
                    "glyph_right_ratio": 1.0,
                    "crop": {"top": 0.0, "right": 0.0, "bottom": 0.0, "left": 0.0},
                    "visible": True,
                },
            ]
            source_info = None
        else:
            return {
                "status": "success",
                "spec": spec.model_dump(),
                "guidelines": guidelines,
                "layers": [],
                "source_spread": None,
                "preflight": {
                    "status": "READY",
                    "is_safe": True,
                    "allow_spine_text": spec.allow_spine_text,
                    "warnings": [spec.spine_text_warning] if spec.spine_text_warning else [],
                },
                "proof_image_base64": None,
            }

        tac_ceiling = PUBLISHER_TAC_LIMITS.get(spec.publisher, 300.0)
        max_tac_pct, has_tac_breach, has_reg_black = inspect_tac_and_registration(
            resize_res.spread_image, tac_ceiling=tac_ceiling
        )
        effective_dpi = (
            round(single_img.width / spec.total_w_in, 1)
            if single_img is not None
            else float(dpi)
        )
        left_buf_px = resize_res.centering.left_clearance_px - resize_res.centering.safe_margin_px
        right_buf_px = resize_res.centering.right_clearance_px - resize_res.centering.safe_margin_px
        is_pass = resize_res.centering.is_safe and not has_tac_breach and not has_reg_black

        preflight_info = {
            "status": "PASS" if is_pass else "FAIL",
            "is_safe": resize_res.centering.is_safe,
            "left_clearance_px": resize_res.centering.left_clearance_px,
            "right_clearance_px": resize_res.centering.right_clearance_px,
            "safe_margin_px": resize_res.centering.safe_margin_px,
            "left_buffer_px": round(left_buf_px, 2),
            "right_buffer_px": round(right_buf_px, 2),
            "left_pass": left_buf_px >= -0.05,
            "right_pass": right_buf_px >= -0.05,
            "optical_center_x_px": resize_res.centering.optical_center_x_px,
            "geometric_center_x_px": resize_res.centering.geometric_center_x_px,
            "shift_x_px": resize_res.centering.shift_x_px,
            "effective_dpi": effective_dpi,
            "max_tac_pct": max_tac_pct,
            "tac_ceiling": tac_ceiling,
            "tac_pass": not has_tac_breach,
            "registration_black": has_reg_black,
            "allow_spine_text": spec.allow_spine_text,
            "warnings": list(resize_res.warnings),
        }

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tmp_proof_path = tf.name
        try:
            generate_diagnostic_proof(
                spread_image=resize_res.spread_image,
                spec=spec,
                centering=resize_res.centering,
                crease=resize_res.crease_detection,
                output_path=tmp_proof_path,
                dpi=150,
            )
            with open(tmp_proof_path, "rb") as pf:
                proof_raw = pf.read()
            proof_img_b64 = f"data:image/png;base64,{base64.b64encode(proof_raw).decode('ascii')}"
        finally:
            if Path(tmp_proof_path).exists():
                Path(tmp_proof_path).unlink()

        return {
            "status": "success",
            "spec": spec.model_dump(),
            "guidelines": guidelines,
            "layers": serialized_layers,
            "source_spread": source_info,
            "preflight": preflight_info,
            "proof_image_base64": proof_img_b64,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decompose error: {e}")


@app.post("/api/export")
async def api_export(request: Request):
    """Generate and download print-ready PDF, PNG, JPG, or full ZIP export bundle."""
    try:
        content_type = request.headers.get("content-type", "")
        uploaded_panels: Dict[str, Image.Image] = {}
        single_img: Optional[Image.Image] = None
        composited_img: Optional[Image.Image] = None

        if "multipart/form-data" in content_type:
            form = await request.form()
            raw_data = dict(form)
            if "file_composited" in form and hasattr(form["file_composited"], "read"):
                fc = form["file_composited"]
                cb = await fc.read()
                if len(cb) > 0:
                    composited_img = _load_image_from_bytes(cb)
            elif "composited_image_base64" in form and form["composited_image_base64"]:
                composited_img = _load_image_from_base64_or_path(str(form["composited_image_base64"]))
            if "file" in form and hasattr(form["file"], "read"):
                f = form["file"]
                data_bytes = await f.read()
                if len(data_bytes) > 0:
                    single_img = _load_image_from_bytes(data_bytes)
            for panel in ("front", "spine", "back"):
                k = f"file_{panel}"
                if k in form and hasattr(form[k], "read"):
                    data_bytes = await form[k].read()
                    if len(data_bytes) > 0:
                        uploaded_panels[panel] = _load_image_from_bytes(data_bytes)
        else:
            raw_data = await request.json()
            if "composited_image_base64" in raw_data and raw_data["composited_image_base64"]:
                composited_img = _load_image_from_base64_or_path(raw_data["composited_image_base64"])
            if "image_base64" in raw_data and raw_data["image_base64"]:
                single_img = _load_image_from_base64_or_path(raw_data["image_base64"])
            elif "image_path" in raw_data and raw_data["image_path"]:
                single_img = _load_image_from_base64_or_path(raw_data["image_path"])
            if "panels" in raw_data and isinstance(raw_data["panels"], dict):
                for p_k, p_val in raw_data["panels"].items():
                    if p_val:
                        uploaded_panels[p_k] = _load_image_from_base64_or_path(p_val)

        export_format = str(raw_data.get("format", "pdf")).strip().lower()

        publisher = str(raw_data.get("publisher", "kdp"))
        binding = str(raw_data.get("binding", "paperback"))
        page_count = int(raw_data.get("page_count", 150))
        paper_type = str(raw_data.get("paper_type", "white"))
        ink_type = str(raw_data.get("ink_type", "black"))
        dpi = int(raw_data.get("dpi", 300))

        trim_size = raw_data.get("trim_size")
        trim_w = float(raw_data["trim_w_in"]) if "trim_w_in" in raw_data and raw_data["trim_w_in"] is not None else None
        trim_h = float(raw_data["trim_h_in"]) if "trim_h_in" in raw_data and raw_data["trim_h_in"] is not None else None
        w_in, h_in = _parse_trim_dimensions(trim_size, trim_w, trim_h)

        spine_shift_px = float(raw_data.get("spine_shift_px", 0.0))
        safe_buffer_in = float(raw_data.get("safe_buffer_in", 0.0))

        override_bounds: Optional[Tuple[int, int]] = None
        spine_bounds_val = raw_data.get("spine_bounds")
        if spine_bounds_val:
            if isinstance(spine_bounds_val, str) and "," in spine_bounds_val:
                pts = [int(float(p.strip())) for p in spine_bounds_val.split(",")]
                override_bounds = (pts[0], pts[1])
            elif isinstance(spine_bounds_val, (list, tuple)) and len(spine_bounds_val) == 2:
                override_bounds = (int(float(spine_bounds_val[0])), int(float(spine_bounds_val[1])))

        trim_str = trim_size if trim_size else f"{w_in}x{h_in}"
        options = ResizeOptions(
            publisher=publisher,
            binding=binding,
            trim_size=trim_str,
            page_count=page_count,
            paper_type=paper_type,
            ink_type=ink_type,
            dpi=dpi,
            override_spine_bounds=override_bounds,
            spine_shift_px=spine_shift_px,
            safe_buffer_in=safe_buffer_in,
        )

        if composited_img is not None:
            spec = calculate_prepress_spec(
                publisher=publisher,
                binding=binding,
                trim_w_in=w_in,
                trim_h_in=h_in,
                page_count=page_count,
                paper_type=paper_type,
                ink_type=ink_type,
            )
            w_px = int(round(spec.total_w_in * dpi))
            h_px = int(round(spec.total_h_in * dpi))
            spread_rgb = composited_img.convert("RGB")
            if spread_rgb.size != (w_px, h_px):
                spread_rgb = spread_rgb.resize((w_px, h_px), Image.Resampling.LANCZOS)
            g = _compute_guideline_coordinates(spec, dpi, safe_buffer_in)
            x_fl = int(round(g["spine_creases"]["calculated_x_left"]))
            x_fr = int(round(g["spine_creases"]["calculated_x_right"]))
            sp_w = max(1, x_fr - x_fl)
            safe_m = spec.spine_safe_margin_in * dpi
            resize_res = ResizeResult(
                spread_image=spread_rgb,
                spec=spec,
                crease_detection=CreaseDetectionResult(
                    x_left=x_fl,
                    x_right=x_fr,
                    spine_width_px=sp_w,
                    shadow_bleed_right_px=0,
                    clean_background_rgb=(45, 55, 35),
                    confidence=1.0,
                ),
                centering=CenteringResult(
                    shift_x_px=0.0,
                    optical_center_x_px=round(sp_w / 2.0, 2),
                    geometric_center_x_px=round(sp_w / 2.0, 2),
                    left_clearance_px=round(safe_m + 6.0, 2),
                    right_clearance_px=round(safe_m + 6.0, 2),
                    safe_margin_px=round(safe_m, 2),
                    is_safe=True,
                ),
                warnings=[],
            )
        else:
            # Prepare input
            input_data: Optional[Union[Image.Image, Dict[str, Image.Image]]] = None
            if uploaded_panels and "front" in uploaded_panels and "back" in uploaded_panels:
                input_data = uploaded_panels
            elif single_img is not None:
                input_data = single_img

            if input_data is None:
                # If no artwork supplied, create a clean neutral placeholder canvas for demonstration
                spec = calculate_prepress_spec(
                    publisher=publisher,
                    binding=binding,
                    trim_w_in=w_in,
                    trim_h_in=h_in,
                    page_count=page_count,
                    paper_type=paper_type,
                    ink_type=ink_type,
                )
                w_px = int(round(spec.total_w_in * dpi))
                h_px = int(round(spec.total_h_in * dpi))
                input_data = Image.new("RGB", (w_px, h_px), (245, 245, 248))

            resize_res = resize_cover_wrap(input_data, options)

        norm_pub = resize_res.spec.publisher
        clean_trim = trim_str.replace(" ", "")

        if export_format == "pdf":
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tmp_pdf_path = tf.name
            try:
                export_print_ready_pdf(
                    spread_image=resize_res.spread_image,
                    spec=resize_res.spec,
                    output_path=tmp_pdf_path,
                    dpi=dpi,
                )
                with open(tmp_pdf_path, "rb") as pf:
                    pdf_bytes = pf.read()
            finally:
                if Path(tmp_pdf_path).exists():
                    Path(tmp_pdf_path).unlink()

            filename = f"cover_spread_{norm_pub}_{clean_trim}_{dpi}dpi.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        elif export_format in ("png", "image/png"):
            bio = io.BytesIO()
            resize_res.spread_image.save(bio, format="PNG")
            filename = f"cover_spread_{norm_pub}_{clean_trim}_{dpi}dpi.png"
            return Response(
                content=bio.getvalue(),
                media_type="image/png",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        elif export_format in ("jpg", "jpeg", "image/jpeg"):
            bio = io.BytesIO()
            rgb_img = resize_res.spread_image.convert("RGB")
            rgb_img.save(bio, format="JPEG", quality=95)
            filename = f"cover_spread_{norm_pub}_{clean_trim}_{dpi}dpi.jpg"
            return Response(
                content=bio.getvalue(),
                media_type="image/jpeg",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        elif export_format in ("zip", "bundle"):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf_pdf:
                tmp_pdf_path = tf_pdf.name
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf_proof:
                tmp_proof_path = tf_proof.name

            try:
                # 1. Print-ready PDF
                export_print_ready_pdf(
                    spread_image=resize_res.spread_image,
                    spec=resize_res.spec,
                    output_path=tmp_pdf_path,
                    dpi=dpi,
                )
                with open(tmp_pdf_path, "rb") as pf:
                    pdf_bytes = pf.read()

                # 2. PNG spread
                bio_png = io.BytesIO()
                resize_res.spread_image.save(bio_png, format="PNG")
                png_bytes = bio_png.getvalue()

                # 3. Diagnostic proof image
                generate_diagnostic_proof(
                    spread_image=resize_res.spread_image,
                    spec=resize_res.spec,
                    centering=resize_res.centering,
                    crease=resize_res.crease_detection,
                    output_path=tmp_proof_path,
                    dpi=150,
                )
                with open(tmp_proof_path, "rb") as prf:
                    proof_bytes = prf.read()

                # 4. Prepress JSON manifest
                manifest = {
                    "publisher": resize_res.spec.publisher,
                    "binding": resize_res.spec.binding,
                    "trim_size": trim_str,
                    "page_count": resize_res.spec.page_count,
                    "paper_type": resize_res.spec.paper_type,
                    "ink_type": resize_res.spec.ink_type,
                    "dpi": dpi,
                    "dimensions": {
                        "total_w_in": resize_res.spec.total_w_in,
                        "total_h_in": resize_res.spec.total_h_in,
                        "spine_w_in": resize_res.spec.spine_w_in,
                        "bleed_in": resize_res.spec.bleed_in,
                        "wrap_in": resize_res.spec.wrap_in,
                        "hinge_in": resize_res.spec.hinge_in,
                        "width_px": resize_res.spread_image.width,
                        "height_px": resize_res.spread_image.height,
                    },
                    "crease": {
                        "x_left": resize_res.crease_detection.x_left,
                        "x_right": resize_res.crease_detection.x_right,
                        "spine_width_px": resize_res.crease_detection.spine_width_px,
                    },
                    "centering": {
                        "optical_center_x_px": resize_res.centering.optical_center_x_px,
                        "geometric_center_x_px": resize_res.centering.geometric_center_x_px,
                        "left_clearance_px": resize_res.centering.left_clearance_px,
                        "right_clearance_px": resize_res.centering.right_clearance_px,
                        "safe_margin_px": resize_res.centering.safe_margin_px,
                        "is_safe": resize_res.centering.is_safe,
                    },
                    "warnings": resize_res.warnings,
                }
                manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

                zip_bio = io.BytesIO()
                with zipfile.ZipFile(zip_bio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("print_ready_spread.pdf", pdf_bytes)
                    zf.writestr("print_ready_spread.png", png_bytes)
                    zf.writestr("diagnostic_proof.png", proof_bytes)
                    zf.writestr("prepress_manifest.json", manifest_json)

                filename = f"cover_bundle_{norm_pub}_{clean_trim}_{dpi}dpi.zip"
                return Response(
                    content=zip_bio.getvalue(),
                    media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )
            finally:
                if Path(tmp_pdf_path).exists():
                    Path(tmp_pdf_path).unlink()
                if Path(tmp_proof_path).exists():
                    Path(tmp_proof_path).unlink()

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported export format: '{export_format}'. Must be pdf, png, jpg, or zip.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Export error: {e}")


STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
