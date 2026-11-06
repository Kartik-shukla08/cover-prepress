"""High-level cover wrap assembly and resizing engine."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union
from PIL import Image
import numpy as np
from pydantic import BaseModel, Field

from mbooks.domain.geometry import TrimSize
from .specs import PrepressSpec, calculate_prepress_spec
from .crease import (
    CreaseDetectionResult,
    detect_spine_creases,
    trim_shadow_and_infill_background,
)
from .segmentation import (
    SpineElement,
    segment_spine_elements,
    calculate_element_scaling,
    reconstruct_clean_spine_background,
)
from .centering import CenteringResult, compute_optical_centering


class ResizeOptions(BaseModel):
    """Options and parameters for cover resizing and wrap assembly."""

    publisher: str
    binding: str
    trim_size: str  # e.g. "6x9", "6 x 9", "5.5 x 8.5"
    page_count: int
    paper_type: str = "white"
    ink_type: str = "black"
    dpi: int = 300
    override_spine_bounds: Optional[Tuple[int, int]] = None
    spine_shift_px: float = 0.0
    safe_buffer_in: float = 0.0


class ResizeResult(BaseModel):
    """Result of cover wrap resizing and prepress composition."""

    spread_image: Image.Image
    spec: PrepressSpec
    crease_detection: CreaseDetectionResult
    centering: CenteringResult
    warnings: List[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True, "frozen": True}


def resize_cover_wrap(
    input_image_or_panels: Union[Image.Image, Dict[str, Image.Image]],
    options: ResizeOptions,
) -> ResizeResult:
    """Resize existing cover wrap mockup or assemble separate panels into print-ready spread.

    Zero external cloud dependencies. Automatically handles:
    - Spine crease boundary detection and 3D shadow bleed trimming
    - 1:1 symmetric scaling for ornaments vs proportional aspect-clamped text scaling
    - High-contrast glyph luminance optical centering (immune to drop shadows)
    - Multi-publisher specs across KDP, IngramSpark, and Lulu (Paperback & Casewrap)
    - Automatic short-book spine text suppression
    """
    ts = TrimSize.from_string(options.trim_size)
    spec = calculate_prepress_spec(
        publisher=options.publisher,
        binding=options.binding,
        trim_w_in=ts.width,
        trim_h_in=ts.height,
        page_count=options.page_count,
        paper_type=options.paper_type,
        ink_type=options.ink_type,
    )

    dpi = options.dpi
    target_w_px = int(round(spec.total_w_in * dpi))
    target_h_px = int(round(spec.total_h_in * dpi))
    target_spine_w_px = max(1, int(round(spec.spine_w_in * dpi)))

    # Fold line positions on output canvas
    if spec.binding == "paperback":
        target_x_fold_left = int(round((spec.bleed_in + spec.trim_w_in) * dpi))
    else:
        # Casewrap fold positions
        board_w_in = (
            spec.total_w_in
            - spec.spine_w_in
            - 2.0 * spec.wrap_in
            - 2.0 * spec.hinge_in
        ) / 2.0
        target_x_fold_left = int(round((spec.wrap_in + board_w_in + spec.hinge_in) * dpi))

    target_x_fold_right = target_x_fold_left + target_spine_w_px
    target_back_w = target_x_fold_left
    target_front_w = target_w_px - target_x_fold_right

    warnings: List[str] = []

    # 1. Input Processing
    if isinstance(input_image_or_panels, dict):
        front_crop = input_image_or_panels["front"].convert("RGB")
        back_crop = input_image_or_panels["back"].convert("RGB")
        spine_crop_raw = input_image_or_panels.get("spine")
        spine_crop = spine_crop_raw.convert("RGB") if spine_crop_raw else None

        if spine_crop is not None and spine_crop.width > 0:
            arr_spine = np.array(spine_crop)
            clean_bg = tuple(
                int(round(c))
                for c in np.median(arr_spine.reshape(-1, 3), axis=0)
            )
        else:
            arr_front = np.array(front_crop)
            clean_bg = tuple(
                int(round(c))
                for c in np.median(arr_front[:, :15, :].reshape(-1, 3), axis=0)
            )
        crease_detection = CreaseDetectionResult(
            x_left=back_crop.width,
            x_right=back_crop.width + (spine_crop.width if spine_crop else 0),
            spine_width_px=spine_crop.width if spine_crop else 0,
            shadow_bleed_right_px=0,
            clean_background_rgb=clean_bg,
            confidence=1.0,
        )
    else:
        input_img = input_image_or_panels.convert("RGB")
        if options.override_spine_bounds is not None:
            xl, xr = options.override_spine_bounds
            spine_w = max(1, xr - xl)
            core = (
                np.array(input_img)[:, xl + 2 : xr - 2, :]
                if xr - xl > 4
                else np.array(input_img)
            )
            clean_bg = tuple(
                int(round(c)) for c in np.median(core.reshape(-1, 3), axis=0)
            )
            crease_detection = CreaseDetectionResult(
                x_left=xl,
                x_right=xr,
                spine_width_px=spine_w,
                shadow_bleed_right_px=0,
                clean_background_rgb=clean_bg,
                confidence=1.0,
            )
        else:
            crease_detection = detect_spine_creases(input_img)

        # Infill 3D fold shadow bleed without eating into the front cover margin
        infilled_img = trim_shadow_and_infill_background(input_img, crease_detection)
        actual_crease_trim_px = min(
            crease_detection.shadow_bleed_right_px,
            max(4, int(round(0.004 * input_img.width))),
        )

        back_crop = input_img.crop((0, 0, max(1, crease_detection.x_left - 2), input_img.height))
        spine_crop = input_img.crop(
            (crease_detection.x_left, 0, crease_detection.x_right, input_img.height)
        )
        front_x_start = min(input_img.width - 1, crease_detection.x_right + actual_crease_trim_px)
        front_crop = input_img.crop(
            (front_x_start, 0, input_img.width, input_img.height)
        )

    # 2. Spine & Centering Processing
    effective_safe_margin_in = spec.spine_safe_margin_in + options.safe_buffer_in
    safe_margin_px = effective_safe_margin_in * dpi

    if not spec.allow_spine_text:
        # Short book: automatically suppress spine text
        if spec.spine_text_warning:
            warnings.append(spec.spine_text_warning)
        else:
            warnings.append("Spine text suppressed: book below minimum page count.")

        target_spine_img = Image.new(
            "RGB", (target_spine_w_px, target_h_px), crease_detection.clean_background_rgb
        )
        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=round(target_spine_w_px / 2.0, 2),
            geometric_center_x_px=round(target_spine_w_px / 2.0, 2),
            left_clearance_px=round(target_spine_w_px / 2.0, 2),
            right_clearance_px=round(target_spine_w_px / 2.0, 2),
            safe_margin_px=round(safe_margin_px, 2),
            is_safe=True,
        )
    else:
        if spine_crop is not None and spine_crop.width > 0:
            elements = segment_spine_elements(
                spine_crop, crease_detection.clean_background_rgb
            )
            if elements:
                usable_w = max(1, target_spine_w_px - int(round(2 * safe_margin_px)) - 6)
                orig_elements_w = max(el.bbox[2] for el in elements) - min(
                    el.bbox[0] for el in elements
                )
                scale_w = (
                    float(usable_w) / float(max(1, orig_elements_w))
                    if orig_elements_w > usable_w
                    else min(1.0, float(usable_w) / float(max(1, orig_elements_w)))
                )
                scale_h = float(target_h_px) / float(max(1, spine_crop.height))

                clean_bg = reconstruct_clean_spine_background(
                    spine_crop, crease_detection.clean_background_rgb, elements
                )
                target_spine_arr = np.array(
                    clean_bg.resize(
                        (target_spine_w_px, target_h_px), Image.Resampling.LANCZOS
                    ),
                    dtype=float,
                )

                # Group consecutive text elements (not separated by an ornament) into cohesive blocks
                # so multi-word titles ("THAT SHOW IS ON!") stay intact without broken word gaps.
                cohesive_groups: List[SpineElement] = []
                for el in elements:
                    if (
                        cohesive_groups
                        and not el.is_symmetric
                        and not cohesive_groups[-1].is_symmetric
                        and (el.bbox[1] - cohesive_groups[-1].bbox[3]) <= max(40, int(0.06 * spine_crop.height))
                    ):
                        prev = cohesive_groups[-1]
                        cohesive_groups[-1] = SpineElement(
                            element_type="text",
                            bbox=(
                                min(prev.bbox[0], el.bbox[0]),
                                min(prev.bbox[1], el.bbox[1]),
                                max(prev.bbox[2], el.bbox[2]),
                                max(prev.bbox[3], el.bbox[3]),
                            ),
                            is_symmetric=False,
                        )
                    else:
                        cohesive_groups.append(el)

                bg_rgb = crease_detection.clean_background_rgb
                bg_lum = 0.299 * bg_rgb[0] + 0.587 * bg_rgb[1] + 0.114 * bg_rgb[2]
                target_geom_center = target_spine_w_px / 2.0

                rendered_groups = []
                for grp in cohesive_groups:
                    gx0, gy0, gx1, gy1 = grp.bbox
                    # Add small padding around group bbox so drop shadows and serifs aren't clipped
                    pad_x = min(6, gx0, spine_crop.width - gx1)
                    pad_y = min(4, gy0, spine_crop.height - gy1)
                    cx0 = max(0, gx0 - max(2, pad_x))
                    cy0 = max(0, gy0 - max(1, pad_y))
                    cx1 = min(spine_crop.width, gx1 + max(2, pad_x))
                    cy1 = min(spine_crop.height, gy1 + max(1, pad_y))

                    if grp.is_symmetric:
                        # Strict 1:1 isotropic scaling for ornaments/logos (e.g. star)
                        sx, sy = calculate_element_scaling(grp, scale_w * 1.15, scale_h)
                        # Boost small ornaments modestly while keeping strict 1:1 sx == sy
                        iso_s = min(max(sx, min(1.35, usable_w / float(max(1, gx1 - gx0)))), scale_h)
                        sx, sy = iso_s, iso_s
                    else:
                        if scale_h > 1.8:
                            # When upscaling a lower-res mockup to 300 DPI, scale vertically
                            # proportionally to fill the spine naturally without needle distortion
                            sx = min(scale_w, 0.92)
                            sy = min(scale_h * 0.72, sx * 2.65)
                        else:
                            sx, sy = calculate_element_scaling(grp, scale_w, scale_h)

                    nw = min(target_spine_w_px - 4, max(1, int(round((cx1 - cx0) * sx))))
                    nh = max(1, int(round((cy1 - cy0) * sy)))

                    sp_sub = spine_crop.crop((cx0, cy0, cx1, cy1)).resize(
                        (nw, nh), Image.Resampling.LANCZOS
                    )
                    cl_sub = clean_bg.crop((cx0, cy0, cx1, cy1)).resize(
                        (nw, nh), Image.Resampling.LANCZOS
                    )
                    sp_arr = np.array(sp_sub, dtype=float)
                    diff = sp_arr - np.array(cl_sub, dtype=float)

                    # Soft feather mask on edges for seamless blending
                    w_mask = np.ones((nh, nw, 1), dtype=float)
                    fy = min(8, max(1, nh // 6))
                    fx = min(4, max(1, nw // 8))
                    for i in range(fy):
                        f = i / float(fy)
                        w_mask[i, :, 0] = np.minimum(w_mask[i, :, 0], f)
                        w_mask[nh - 1 - i, :, 0] = np.minimum(w_mask[nh - 1 - i, :, 0], f)
                    for j in range(fx):
                        f = j / float(fx)
                        w_mask[:, j, 0] = np.minimum(w_mask[:, j, 0], f)
                        w_mask[:, nw - 1 - j, 0] = np.minimum(w_mask[:, nw - 1 - j, 0], f)

                    # Find high-contrast foreground glyph bounds inside resized strip
                    sub_lum = (
                        0.299 * sp_arr[:, :, 0]
                        + 0.587 * sp_arr[:, :, 1]
                        + 0.114 * sp_arr[:, :, 2]
                    )
                    fg_m = (sub_lum > (bg_lum + 25)) if bg_lum < 128 else (sub_lum < (bg_lum - 25))
                    if not fg_m.any():
                        fg_m = np.abs(sub_lum - bg_lum) > 18
                    if fg_m.any():
                        _, fxs = np.where(fg_m)
                        fg_min_x, fg_max_x = int(fxs.min()), int(fxs.max()) + 1
                    else:
                        fg_min_x, fg_max_x = 0, nw

                    # Detect if dark drop shadow sits to the left of the bright glyphs
                    sh_m = (sub_lum < (bg_lum - 14)) if bg_lum < 128 else (sub_lum > (bg_lum + 14))
                    optical_left_comp = 0.0
                    if sh_m.any() and fg_m.any():
                        _, sxs = np.where(sh_m)
                        if int(sxs.min()) < fg_min_x:
                            # Compensate half of unilateral left shadow width for human optical balance
                            optical_left_comp = min(2.5, 0.45 * float(fg_min_x - int(sxs.min())))

                    fg_center_x = 0.5 * (fg_min_x + fg_max_x)
                    el_x = int(
                        round(
                            (target_geom_center - optical_left_comp)
                            - fg_center_x
                            + options.spine_shift_px
                        )
                    )
                    rendered_groups.append(
                        (diff * w_mask, nw, nh, el_x, fg_min_x, fg_max_x, cy0)
                    )

                # Position groups vertically: stack centered with proportional gaps
                if len(rendered_groups) > 1:
                    gap_px = max(24, min(130, int(round(0.047 * target_h_px))))
                else:
                    gap_px = 0
                total_stack_h = sum(r[2] for r in rendered_groups) + gap_px * max(0, len(rendered_groups) - 1)
                if total_stack_h <= target_h_px:
                    cur_y = (target_h_px - total_stack_h) // 2
                else:
                    cur_y = 0
                    gap_px = 4

                scaled_bboxes = []
                for diff_masked, nw, nh, el_x, fg_min_x, fg_max_x, _ in rendered_groups:
                    el_y = min(max(0, cur_y), max(0, target_h_px - nh))
                    src_x0 = max(0, -el_x)
                    dst_x0 = max(0, el_x)
                    copy_w = max(0, min(nw - src_x0, target_spine_w_px - dst_x0))
                    if copy_w > 0 and nh > 0:
                        target_spine_arr[el_y : el_y + nh, dst_x0 : dst_x0 + copy_w, :] = np.clip(
                            target_spine_arr[el_y : el_y + nh, dst_x0 : dst_x0 + copy_w, :]
                            + diff_masked[:, src_x0 : src_x0 + copy_w, :],
                            0,
                            255,
                        )
                    abs_fg_l = max(0, el_x + fg_min_x)
                    abs_fg_r = min(target_spine_w_px, el_x + fg_max_x)
                    scaled_bboxes.append((abs_fg_l, el_y, abs_fg_r, el_y + nh))
                    cur_y += nh + gap_px

                target_spine_img = Image.fromarray(target_spine_arr.astype(np.uint8))

                min_x = min(b[0] for b in scaled_bboxes)
                max_x = max(b[2] for b in scaled_bboxes)
                left_c = float(min_x)
                right_c = float(target_spine_w_px - max_x)
                is_safe = (left_c >= safe_margin_px) and (right_c >= safe_margin_px)
                opt_center = float((min_x + max_x) / 2.0)

                centering = CenteringResult(
                    shift_x_px=round(options.spine_shift_px, 2),
                    optical_center_x_px=round(opt_center, 2),
                    geometric_center_x_px=round(target_geom_center, 2),
                    left_clearance_px=round(left_c, 2),
                    right_clearance_px=round(right_c, 2),
                    safe_margin_px=round(safe_margin_px, 2),
                    is_safe=is_safe,
                )
                if not is_safe:
                    warnings.append(
                        f"Spine text breaches safe margin: left clearance {left_c:.1f}px, right clearance {right_c:.1f}px vs required {safe_margin_px:.1f}px."
                    )
            else:
                target_spine_img = spine_crop.resize(
                    (target_spine_w_px, target_h_px), Image.Resampling.LANCZOS
                )
                centering = compute_optical_centering(
                    spine_crop, [], safe_margin_px, options.spine_shift_px
                )
        else:
            target_spine_img = Image.new(
                "RGB", (target_spine_w_px, target_h_px), crease_detection.clean_background_rgb
            )
            centering = CenteringResult(
                shift_x_px=0.0,
                optical_center_x_px=round(target_spine_w_px / 2.0, 2),
                geometric_center_x_px=round(target_spine_w_px / 2.0, 2),
                left_clearance_px=round(target_spine_w_px / 2.0, 2),
                right_clearance_px=round(target_spine_w_px / 2.0, 2),
                safe_margin_px=round(safe_margin_px, 2),
                is_safe=True,
            )

    # 3. Canvas Assembly
    back_resized = back_crop.resize((target_back_w, target_h_px), Image.Resampling.LANCZOS)
    front_resized = front_crop.resize((target_front_w, target_h_px), Image.Resampling.LANCZOS)

    spread_image = Image.new(
        "RGB", (target_w_px, target_h_px), crease_detection.clean_background_rgb
    )
    spread_image.paste(back_resized, (0, 0))
    spread_image.paste(target_spine_img, (target_x_fold_left, 0))
    spread_image.paste(front_resized, (target_x_fold_right, 0))

    return ResizeResult(
        spread_image=spread_image,
        spec=spec,
        crease_detection=crease_detection,
        centering=centering,
        warnings=warnings,
    )


class DecomposedLayer(BaseModel):
    """An individual editable layer on the target prepress canvas."""

    id: str
    name: str
    kind: str  # "panel" | "spine_bg" | "spine_text" | "spine_ornament"
    image: Image.Image
    x: float
    y: float
    w: float
    h: float
    lock_aspect: bool = False
    group_id: Optional[str] = None
    glyph_left_ratio: float = 0.0
    glyph_right_ratio: float = 1.0

    model_config = {"arbitrary_types_allowed": True}


class DecomposedCoverResult(BaseModel):
    """Result of decomposing a cover spread into modular editable layers."""

    layers: List[DecomposedLayer]
    resize_result: ResizeResult
    source_width: int
    source_height: int
    source_x_left: int
    source_x_right: int
    actual_crease_trim_px: int

    model_config = {"arbitrary_types_allowed": True}


def decompose_cover_to_layers(
    input_image: Image.Image,
    options: ResizeOptions,
) -> DecomposedCoverResult:
    """Decompose a single spread image into modular editable canvas layers (Back, Spine BG, Spine Elements, Front)."""
    res = resize_cover_wrap(input_image, options)
    spec = res.spec
    dpi = options.dpi
    target_w_px = int(round(spec.total_w_in * dpi))
    target_h_px = int(round(spec.total_h_in * dpi))

    if spec.binding == "paperback":
        target_x_fold_left = int(round((spec.bleed_in + spec.trim_w_in) * dpi))
    else:
        board_w_in = (
            spec.total_w_in
            - spec.spine_w_in
            - 2.0 * spec.wrap_in
            - 2.0 * spec.hinge_in
        ) / 2.0
        target_x_fold_left = int(
            round((spec.wrap_in + board_w_in + spec.hinge_in) * dpi)
        )
    target_spine_w_px = int(round(spec.spine_w_in * dpi))
    target_x_fold_right = target_x_fold_left + target_spine_w_px
    target_back_w = target_x_fold_left
    target_front_w = target_w_px - target_x_fold_right

    rgb_img = input_image.convert("RGB")
    cd = res.crease_detection
    max_auto_trim = max(4, int(round(0.004 * rgb_img.width)))
    actual_crease_trim_px = min(cd.shadow_bleed_right_px, max_auto_trim)
    x_l = cd.x_left
    x_r = cd.x_right

    back_crop = rgb_img.crop((0, 0, max(1, x_l), rgb_img.height))
    spine_crop = rgb_img.crop((x_l, 0, max(x_l + 1, x_r), rgb_img.height))
    front_start_x = min(rgb_img.width - 1, x_r + actual_crease_trim_px)
    front_crop = rgb_img.crop((front_start_x, 0, rgb_img.width, rgb_img.height))

    back_resized = back_crop.resize((target_back_w, target_h_px), Image.Resampling.LANCZOS)
    front_resized = front_crop.resize((target_front_w, target_h_px), Image.Resampling.LANCZOS)

    elements = segment_spine_elements(spine_crop, cd.clean_background_rgb) if spec.allow_spine_text else []
    clean_bg = reconstruct_clean_spine_background(spine_crop, cd.clean_background_rgb, elements)
    spine_bg_resized = clean_bg.resize((target_spine_w_px, target_h_px), Image.Resampling.LANCZOS)

    layers: List[DecomposedLayer] = [
        DecomposedLayer(
            id="back_panel",
            name="Back Cover",
            kind="panel",
            image=back_resized,
            x=0.0,
            y=0.0,
            w=float(target_back_w),
            h=float(target_h_px),
            lock_aspect=False,
            group_id=None,
        ),
        DecomposedLayer(
            id="spine_bg",
            name="Spine Background",
            kind="spine_bg",
            image=spine_bg_resized,
            x=float(target_x_fold_left),
            y=0.0,
            w=float(target_spine_w_px),
            h=float(target_h_px),
            lock_aspect=False,
            group_id="spine_group",
        ),
        DecomposedLayer(
            id="front_panel",
            name="Front Cover",
            kind="panel",
            image=front_resized,
            x=float(target_x_fold_right),
            y=0.0,
            w=float(target_front_w),
            h=float(target_h_px),
            lock_aspect=False,
            group_id=None,
        ),
    ]

    if spec.allow_spine_text:
        if elements:
            sp_arr = np.asarray(spine_crop.convert("RGB"), dtype=np.uint8)
            clean_bg_arr = np.asarray(clean_bg.convert("RGB"), dtype=np.uint8)
            scale_w = target_spine_w_px / float(max(1, spine_crop.width))
            scale_h = target_h_px / float(max(1, spine_crop.height))

            grouped_blocks = []
            for el in elements:
                x0, y0, x1, y1 = el.bbox
                if not grouped_blocks:
                    grouped_blocks.append([x0, y0, x1, y1, el.is_symmetric])
                else:
                    prev = grouped_blocks[-1]
                    if (not el.is_symmetric) and (not prev[4]):
                        prev[0] = min(prev[0], x0)
                        prev[1] = min(prev[1], y0)
                        prev[2] = max(prev[2], x1)
                        prev[3] = max(prev[3], y1)
                    else:
                        grouped_blocks.append([x0, y0, x1, y1, el.is_symmetric])

            rendered_items = []
            for idx, (x0, y0, x1, y1, is_sym) in enumerate(grouped_blocks):
                bw = max(1, x1 - x0)
                bh = max(1, y1 - y0)
                sx = scale_w * 0.90 if scale_h > 1.8 else scale_w
                if is_sym:
                    sy = sx
                else:
                    sy = min(scale_h * 0.72, sx * 2.65) if scale_h > 1.8 else min(scale_h, sx * 1.2)

                nw = max(1, int(round(bw * sx)))
                nh = max(1, int(round(bh * sy)))

                raw_crop_arr = sp_arr[y0:y1, x0:x1].astype(np.float32)
                bg_crop_arr = clean_bg_arr[y0:y1, x0:x1].astype(np.float32)
                diff_max = np.max(np.abs(raw_crop_arr - bg_crop_arr), axis=2)
                w_mask = np.clip((diff_max - 8.0) / 18.0, 0.0, 1.0)

                # Create clean RGBA image where alpha = w_mask and RGB = raw_crop
                rgba_src = np.zeros((bh, bw, 4), dtype=np.uint8)
                rgba_src[:, :, :3] = np.clip(raw_crop_arr, 0, 255).astype(np.uint8)
                rgba_src[:, :, 3] = np.clip(w_mask * 255.0, 0, 255).astype(np.uint8)
                rgba_scaled = Image.fromarray(rgba_src, mode="RGBA").resize(
                    (nw, nh), Image.Resampling.LANCZOS
                )

                lum_crop = (
                    0.299 * raw_crop_arr[:, :, 0]
                    + 0.587 * raw_crop_arr[:, :, 1]
                    + 0.114 * raw_crop_arr[:, :, 2]
                )
                bg_lum_crop = (
                    0.299 * bg_crop_arr[:, :, 0]
                    + 0.587 * bg_crop_arr[:, :, 1]
                    + 0.114 * bg_crop_arr[:, :, 2]
                )
                p95 = float(np.percentile(lum_crop, 95))
                p05 = float(np.percentile(lum_crop, 5))
                bg_med = float(np.median(bg_lum_crop))
                if abs(p95 - bg_med) >= abs(bg_med - p05):
                    fg_thresh = bg_med + 0.35 * max(25.0, p95 - bg_med)
                    fg_mask = lum_crop >= fg_thresh
                else:
                    fg_thresh = bg_med - 0.35 * max(25.0, bg_med - p05)
                    fg_mask = lum_crop <= fg_thresh

                xs_fg = np.where(fg_mask)[1]
                if xs_fg.size > 0:
                    fg_l_ratio = float(np.min(xs_fg)) / float(bw)
                    fg_r_ratio = float(np.max(xs_fg) + 1) / float(bw)
                else:
                    fg_l_ratio = 0.0
                    fg_r_ratio = 1.0

                fg_center_x = nw * (fg_l_ratio + fg_r_ratio) / 2.0
                dark_shadow_bias_px = -1.0 if (not is_sym and scale_h > 1.8) else 0.0
                target_geom_center = target_spine_w_px / 2.0
                el_x_local = int(
                    round(
                        target_geom_center
                        - fg_center_x
                        + dark_shadow_bias_px
                        + options.spine_shift_px
                    )
                )
                rendered_items.append(
                    (rgba_scaled, nw, nh, el_x_local, fg_l_ratio, fg_r_ratio, is_sym)
                )

            gap_px = max(18, int(round(0.052 * target_h_px)))
            total_stack_h = sum(it[2] for it in rendered_items) + gap_px * max(
                0, len(rendered_items) - 1
            )
            if total_stack_h < target_h_px:
                cur_y = (target_h_px - total_stack_h) // 2
            else:
                cur_y = 0
                gap_px = 4

            text_idx = 0
            orn_idx = 0
            for idx, (
                rgba_scaled,
                nw,
                nh,
                el_x_local,
                fg_l_ratio,
                fg_r_ratio,
                is_sym,
            ) in enumerate(rendered_items):
                el_y = min(max(0, cur_y), max(0, target_h_px - nh))
                if is_sym:
                    orn_idx += 1
                    l_name = f"Spine Ornament ★ #{orn_idx}" if orn_idx > 1 else "Spine Ornament ★"
                    l_kind = "spine_ornament"
                else:
                    text_idx += 1
                    if text_idx == 1:
                        l_name = "Spine Title Block"
                    elif text_idx == 2:
                        l_name = "Spine Author / Subtitle"
                    else:
                        l_name = f"Spine Text Block #{text_idx}"
                    l_kind = "spine_text"

                layers.append(
                    DecomposedLayer(
                        id=f"spine_el_{idx}",
                        name=l_name,
                        kind=l_kind,
                        image=rgba_scaled,
                        x=float(target_x_fold_left + el_x_local),
                        y=float(el_y),
                        w=float(nw),
                        h=float(nh),
                        lock_aspect=bool(is_sym),
                        group_id="spine_group",
                        glyph_left_ratio=round(fg_l_ratio, 4),
                        glyph_right_ratio=round(fg_r_ratio, 4),
                    )
                )
                cur_y += nh + gap_px

    return DecomposedCoverResult(
        layers=layers,
        resize_result=res,
        source_width=rgb_img.width,
        source_height=rgb_img.height,
        source_x_left=x_l,
        source_x_right=x_r,
        actual_crease_trim_px=actual_crease_trim_px,
    )

