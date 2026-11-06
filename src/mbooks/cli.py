"""Standalone CLI entrypoint for Markee Books Cover Prepress & Studio."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

from mbooks.calculators import calculate_specifications
from mbooks.domain.book import BookConfiguration
from mbooks.domain.enums import (
    BindingType,
    BookFormat,
    CoverFinish,
    DistributionGoal,
    InteriorInk,
    PaperType,
    Publisher,
)
from mbooks.domain.geometry import TrimSize
from mbooks.prepress.centering import CenteringResult, compute_optical_centering
from mbooks.prepress.crease import CreaseDetectionResult, detect_spine_creases
from mbooks.prepress.pdf import (
    PUBLISHER_TAC_LIMITS,
    export_print_ready_pdf,
    inspect_tac_and_registration,
)
from mbooks.prepress.proof import generate_diagnostic_proof
from mbooks.prepress.resizer import ResizeOptions, resize_cover_wrap
from mbooks.prepress.segmentation import segment_spine_elements
from mbooks.prepress.specs import (
    PrepressSpec,
    _normalize_binding,
    _normalize_publisher,
    calculate_prepress_spec,
)


def _parse_spine_bounds(val: str | None) -> Tuple[int, int] | None:
    if not val:
        return None
    parts = val.split(",")
    if len(parts) != 2:
        print(
            f"Error: Malformed --spine-bounds '{val}'. Expected format 'x_left,x_right' (e.g. '588,691').",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        xl = int(parts[0].strip())
        xr = int(parts[1].strip())
    except ValueError:
        print(f"Error: Malformed --spine-bounds '{val}'. Coordinates must be integers.", file=sys.stderr)
        sys.exit(1)
    if xl < 0 or xr <= xl:
        print(
            f"Error: Invalid --spine-bounds [{xl}, {xr}]. x_right must be greater than x_left and non-negative.",
            file=sys.stderr,
        )
        sys.exit(1)
    return xl, xr


def _validate_image_readable(path: Path | str, param_name: str = "--input") -> Image.Image:
    p = Path(path)
    if not p.exists() or not p.is_file():
        print(f"Error: {param_name} file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with Image.open(p) as img:
            img.load()
            return img.copy()
    except Exception as e:
        print(f"Error: {param_name} is not a valid or readable image file: {e}", file=sys.stderr)
        sys.exit(1)


def _resolve_proof_crease_and_centering(
    img: Image.Image,
    spec: PrepressSpec,
    spine_bounds: Tuple[int, int] | None,
    spine_shift_px: float,
    safe_buffer_in: float,
    dpi: int,
) -> Tuple[CreaseDetectionResult, CenteringResult]:
    W, H = img.size
    expected_w_px = int(round(spec.total_w_in * dpi))
    is_resized = abs(W - expected_w_px) <= max(20, int(round(0.05 * expected_w_px)))

    if spine_bounds is not None:
        xl, xr = spine_bounds
        spine_w = max(1, xr - xl)
        arr = np.array(img.convert("RGB"))
        core = arr[:, xl + 2 : xr - 2, :] if xr - xl > 4 else arr
        clean_bg = tuple(int(round(c)) for c in np.median(core.reshape(-1, 3), axis=0))
        crease = CreaseDetectionResult(
            x_left=xl,
            x_right=xr,
            spine_width_px=spine_w,
            shadow_bleed_right_px=0,
            clean_background_rgb=clean_bg,
            confidence=1.0,
        )
    elif is_resized:
        if spec.binding == "paperback":
            x_fold_left = int(round((spec.bleed_in + spec.trim_w_in) * dpi))
        else:
            board_w_in = (
                spec.total_w_in
                - spec.spine_w_in
                - 2.0 * spec.wrap_in
                - 2.0 * spec.hinge_in
            ) / 2.0
            x_fold_left = int(round((spec.wrap_in + board_w_in + spec.hinge_in) * dpi))
        spine_w_px = max(1, int(round(spec.spine_w_in * dpi)))
        x_fold_right = x_fold_left + spine_w_px
        arr = np.array(img.convert("RGB"))
        clean_bg = tuple(
            int(round(c))
            for c in np.median(arr[:, x_fold_left:x_fold_right, :].reshape(-1, 3), axis=0)
        )
        crease = CreaseDetectionResult(
            x_left=x_fold_left,
            x_right=x_fold_right,
            spine_width_px=spine_w_px,
            shadow_bleed_right_px=0,
            clean_background_rgb=clean_bg,
            confidence=1.0,
        )
    else:
        crease = detect_spine_creases(img)

    safe_margin_in = spec.spine_safe_margin_in + safe_buffer_in
    safe_margin_px = safe_margin_in * dpi

    if not spec.allow_spine_text:
        centering = CenteringResult(
            shift_x_px=0.0,
            optical_center_x_px=round(crease.spine_width_px / 2.0, 2),
            geometric_center_x_px=round(crease.spine_width_px / 2.0, 2),
            left_clearance_px=round(crease.spine_width_px / 2.0, 2),
            right_clearance_px=round(crease.spine_width_px / 2.0, 2),
            safe_margin_px=round(safe_margin_px, 2),
            is_safe=True,
        )
    else:
        xl = max(0, min(W - 1, crease.x_left))
        xr = max(xl + 1, min(W, crease.x_right))
        spine_crop = img.crop((xl, 0, xr, H))
        elements = segment_spine_elements(spine_crop, crease.clean_background_rgb)
        centering = compute_optical_centering(
            spine_crop, elements, safe_margin_px, nudge_px=spine_shift_px
        )

    return crease, centering


def _handle_cover_resize(args: argparse.Namespace) -> None:
    if args.input is None and (args.front is None or args.back is None):
        print("Error: Either --input (-i) or both --front and --back must be provided.", file=sys.stderr)
        sys.exit(1)

    if args.input is not None:
        input_data = _validate_image_readable(args.input, "--input")
    else:
        panels: dict[str, Image.Image] = {}
        panels["front"] = _validate_image_readable(args.front, "--front")
        panels["back"] = _validate_image_readable(args.back, "--back")
        if args.spine is not None:
            panels["spine"] = _validate_image_readable(args.spine, "--spine")
        input_data = panels

    if args.pages <= 0:
        print(f"Error: Page count must be a positive integer, got {args.pages}", file=sys.stderr)
        sys.exit(1)

    if args.dpi <= 0:
        print(f"Error: DPI must be a positive integer, got {args.dpi}", file=sys.stderr)
        sys.exit(1)

    try:
        norm_publisher = _normalize_publisher(args.publisher)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        norm_binding = _normalize_binding(args.binding)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        TrimSize.from_string(args.trim)
    except Exception:
        print(f"Error: Invalid trim size format: {args.trim}", file=sys.stderr)
        sys.exit(1)

    spine_bounds = _parse_spine_bounds(args.spine_bounds)

    options = ResizeOptions(
        publisher=norm_publisher,
        binding=norm_binding,
        trim_size=args.trim,
        page_count=args.pages,
        paper_type=args.paper,
        ink_type=args.ink,
        dpi=args.dpi,
        override_spine_bounds=spine_bounds,
        spine_shift_px=args.spine_shift_px,
        safe_buffer_in=args.safe_buffer,
    )

    result = resize_cover_wrap(input_data, options)

    if isinstance(input_data, Image.Image):
        effective_dpi = round(input_data.width / result.spec.total_w_in, 1)
        if effective_dpi < 150.0:
            result.warnings.append(
                f"Low input image resolution: {input_data.width}x{input_data.height} px ({effective_dpi} DPI). Recommended is >= 300 DPI."
            )
    else:
        effective_dpi = float(args.dpi)

    tac_ceiling = PUBLISHER_TAC_LIMITS.get(norm_publisher, 300.0)
    max_tac_pct, has_tac_breach, has_reg_black = inspect_tac_and_registration(
        result.spread_image, tac_ceiling=tac_ceiling
    )
    if has_reg_black:
        result.warnings.append("400% registration black detected on artwork.")
    if has_tac_breach:
        result.warnings.append(
            f"Total Area Coverage ({max_tac_pct:.1f}%) exceeds {norm_publisher.upper()} ceiling of {tac_ceiling:.1f}%."
        )

    output_path = args.output
    if args.export_pdf:
        if not output_path:
            output_path = "cover_spread.pdf"
        elif not output_path.lower().endswith(".pdf"):
            img_out = output_path
            p_img = Path(img_out)
            if p_img.parent:
                p_img.parent.mkdir(parents=True, exist_ok=True)
            result.spread_image.save(img_out)
            output_path = str(Path(output_path).with_suffix(".pdf"))

        p_pdf = Path(output_path)
        if p_pdf.parent:
            p_pdf.parent.mkdir(parents=True, exist_ok=True)
        try:
            export_print_ready_pdf(result.spread_image, result.spec, output_path, dpi=options.dpi)
        except Exception as e:
            print(f"Error exporting PDF: {e}", file=sys.stderr)
            sys.exit(1)
    elif output_path:
        p_out = Path(output_path)
        if p_out.parent:
            p_out.parent.mkdir(parents=True, exist_ok=True)
        if output_path.lower().endswith(".pdf"):
            try:
                export_print_ready_pdf(result.spread_image, result.spec, output_path, dpi=options.dpi)
            except Exception as e:
                print(f"Error exporting PDF: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            result.spread_image.save(output_path)
    else:
        if not args.json:
            output_path = "resized_spread.png"
            result.spread_image.save(output_path)

    if args.json:
        summary = {
            "status": "success",
            "safe": result.centering.is_safe,
            "publisher": norm_publisher,
            "binding": norm_binding,
            "trim_size": args.trim,
            "page_count": args.pages,
            "paper_type": args.paper,
            "ink_type": args.ink,
            "dpi": args.dpi,
            "output_path": str(output_path) if output_path else None,
            "dimensions": {
                "total_width_in": result.spec.total_w_in,
                "total_height_in": result.spec.total_h_in,
                "spine_width_in": result.spec.spine_w_in,
                "bleed_in": result.spec.bleed_in,
                "wrap_in": result.spec.wrap_in,
                "hinge_in": result.spec.hinge_in,
                "width_px": result.spread_image.width,
                "height_px": result.spread_image.height,
                "spine_width_px": max(1, int(round(result.spec.spine_w_in * args.dpi))),
            },
            "crease": {
                "x_left": result.crease_detection.x_left,
                "x_right": result.crease_detection.x_right,
                "spine_width_px": result.crease_detection.spine_width_px,
                "shadow_bleed_right_px": result.crease_detection.shadow_bleed_right_px,
                "confidence": result.crease_detection.confidence,
            },
            "clearances": {
                "optical_center_x_px": result.centering.optical_center_x_px,
                "geometric_center_x_px": result.centering.geometric_center_x_px,
                "shift_x_px": result.centering.shift_x_px,
                "left_clearance_px": result.centering.left_clearance_px,
                "right_clearance_px": result.centering.right_clearance_px,
                "safe_margin_px": result.centering.safe_margin_px,
                "safe_margin_in": round(result.spec.spine_safe_margin_in + args.safe_buffer, 4),
                "is_safe": result.centering.is_safe,
            },
            "preflight": {
                "image_readable": True,
                "effective_dpi": effective_dpi,
                "max_tac_percent": max_tac_pct,
                "tac_ceiling_percent": tac_ceiling,
                "tac_pass": not has_tac_breach,
                "registration_black_detected": has_reg_black,
                "allow_spine_text": result.spec.allow_spine_text,
            },
            "warnings": result.warnings,
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    print("\n=======================================================")
    print("  MARKEE BOOKS — COVER RESIZE PREPRESS REPORT")
    print("=======================================================")
    print(f"Publisher:      {norm_publisher.upper()} ({norm_binding.title()})")
    print(f"Trim Size:      {args.trim} ({args.pages} pages, {args.paper} paper)")
    print(f"Resolution:     {args.dpi} DPI")
    print(
        f"Canvas Size:    {result.spread_image.width} x {result.spread_image.height} px ({result.spec.total_w_in:.3f}\" x {result.spec.total_h_in:.3f}\")"
    )
    print(f"Spine Width:    {result.spec.spine_w_in:.4f}\" ({int(round(result.spec.spine_w_in * args.dpi))} px)")
    print(f"Safe Margin:    {result.spec.spine_safe_margin_in:.4f}\" ({result.centering.safe_margin_px:.1f} px)")
    print("\nSpine Centering & Clearances:")
    print(
        f"  Detected Folds:   x_left={result.crease_detection.x_left}, x_right={result.crease_detection.x_right} (width={result.crease_detection.spine_width_px} px)"
    )
    print(
        f"  Optical Center:   {result.centering.optical_center_x_px:.1f} px (geometric center: {result.centering.geometric_center_x_px:.1f} px)"
    )
    print(f"  Left Clearance:   {result.centering.left_clearance_px:.1f} px [Required: >= {result.centering.safe_margin_px:.1f} px]")
    print(f"  Right Clearance:  {result.centering.right_clearance_px:.1f} px [Required: >= {result.centering.safe_margin_px:.1f} px]")
    status_label = "SAFE (PASS)" if result.centering.is_safe else "BREACH (FAIL)"
    print(f"  Safe Status:      {status_label}")
    print("\nPreflight Checks:")
    print("  Asset Readability:   PASS")
    print(f"  Effective DPI:       {effective_dpi:.1f} DPI")
    tac_label = "PASS" if not has_tac_breach else "FAIL"
    print(f"  Max Total Area Cov:  {max_tac_pct:.1f}% (Ceiling: {tac_ceiling:.1f}%) [{tac_label}]")
    reg_label = "NONE DETECTED (PASS)" if not has_reg_black else "FAIL (REGISTRATION BLACK DETECTED)"
    print(f"  Registration Black:  {reg_label}")
    allow_txt_label = "YES" if result.spec.allow_spine_text else "NO (SUPPRESSED)"
    print(f"  Spine Text Allowed:  {allow_txt_label}")
    if output_path:
        print(f"\nOutput Saved: {output_path}")
    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings:
            print(f"  - {w}")
    print("=======================================================\n")


def _handle_cover_proof(args: argparse.Namespace) -> None:
    if args.input is None:
        print("Error: --input (-i) is required for cover-proof.", file=sys.stderr)
        sys.exit(1)

    img = _validate_image_readable(args.input, "--input")

    if args.pages <= 0:
        print(f"Error: Page count must be a positive integer, got {args.pages}", file=sys.stderr)
        sys.exit(1)

    if args.dpi <= 0:
        print(f"Error: DPI must be a positive integer, got {args.dpi}", file=sys.stderr)
        sys.exit(1)

    try:
        norm_publisher = _normalize_publisher(args.publisher)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        norm_binding = _normalize_binding(args.binding)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        trim_obj = TrimSize.from_string(args.trim)
    except Exception:
        print(f"Error: Invalid trim size format: {args.trim}", file=sys.stderr)
        sys.exit(1)

    spine_bounds = _parse_spine_bounds(args.spine_bounds)

    spec = calculate_prepress_spec(
        publisher=norm_publisher,
        binding=norm_binding,
        trim_w_in=trim_obj.width,
        trim_h_in=trim_obj.height,
        page_count=args.pages,
        paper_type=args.paper,
        ink_type=args.ink,
    )

    crease, centering = _resolve_proof_crease_and_centering(
        img=img,
        spec=spec,
        spine_bounds=spine_bounds,
        spine_shift_px=args.spine_shift_px,
        safe_buffer_in=args.safe_buffer,
        dpi=args.dpi,
    )

    output_path = args.output or "cover_proof.png"
    p_out = Path(output_path)
    if p_out.parent:
        p_out.parent.mkdir(parents=True, exist_ok=True)

    generate_diagnostic_proof(
        spread_image=img,
        spec=spec,
        centering=centering,
        crease=crease,
        output_path=output_path,
        dpi=args.dpi,
    )

    safe_margin_in = spec.spine_safe_margin_in + args.safe_buffer
    safe_margin_px = safe_margin_in * args.dpi
    left_buf_px = centering.left_clearance_px - safe_margin_px
    right_buf_px = centering.right_clearance_px - safe_margin_px
    left_pass = left_buf_px >= -0.05
    right_pass = right_buf_px >= -0.05
    status_str = "PASS" if centering.is_safe else "FAIL"

    if args.json:
        summary = {
            "status": status_str,
            "is_safe": centering.is_safe,
            "publisher": norm_publisher,
            "binding": norm_binding,
            "trim_size": args.trim,
            "page_count": args.pages,
            "paper_type": args.paper,
            "ink_type": args.ink,
            "dpi": args.dpi,
            "output_path": str(output_path),
            "dimensions": {
                "total_width_in": spec.total_w_in,
                "total_height_in": spec.total_h_in,
                "spine_width_in": spec.spine_w_in,
                "spine_width_px": crease.spine_width_px,
                "bleed_in": spec.bleed_in,
            },
            "gap_measurements": {
                "left_clearance_px": centering.left_clearance_px,
                "left_clearance_in": round(centering.left_clearance_px / args.dpi, 4),
                "left_buffer_px": round(left_buf_px, 2),
                "left_buffer_in": round(left_buf_px / args.dpi, 4),
                "left_pass": left_pass,
                "right_clearance_px": centering.right_clearance_px,
                "right_clearance_in": round(centering.right_clearance_px / args.dpi, 4),
                "right_buffer_px": round(right_buf_px, 2),
                "right_buffer_in": round(right_buf_px / args.dpi, 4),
                "right_pass": right_pass,
                "safe_margin_px": centering.safe_margin_px,
                "safe_margin_in": round(centering.safe_margin_px / args.dpi, 4),
                "shift_x_px": centering.shift_x_px,
                "manual_shift_px": args.spine_shift_px,
                "optical_center_x_px": centering.optical_center_x_px,
                "geometric_center_x_px": centering.geometric_center_x_px,
            },
            "crease": {
                "x_left": crease.x_left,
                "x_right": crease.x_right,
                "spine_width_px": crease.spine_width_px,
                "confidence": crease.confidence,
            },
            "allow_spine_text": spec.allow_spine_text,
            "warnings": [spec.spine_text_warning] if spec.spine_text_warning else [],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    print("\n=======================================================")
    print("  MARKEE BOOKS — COVER DIAGNOSTIC PROOF REPORT")
    print("=======================================================")
    print(f"Preflight Status: {status_str} {'(ALL CLEARANCES MET)' if centering.is_safe else '(SAFE AREA BREACH)'}")
    print(f"Publisher:        {norm_publisher.upper()} ({norm_binding.title()})")
    print(f"Trim Size:        {args.trim} ({args.pages} pages, {args.paper} paper)")
    print(f"Resolution:       {args.dpi} DPI")
    print(f"Spine Width:      {spec.spine_w_in:.4f}\" ({crease.spine_width_px} px)")
    print(f"Safe Margin:      {spec.spine_safe_margin_in:.4f}\" ({centering.safe_margin_px:.1f} px)")
    print("\nGap Measurements & Margin Buffers:")
    print(
        f"  Left Fold Clearance:   {centering.left_clearance_px:.1f} px ({centering.left_clearance_px / args.dpi:.4f}\") --> Buffer: {left_buf_px:+.1f} px ({left_buf_px / args.dpi:+.4f}\") [{'PASS' if left_pass else 'FAIL'}]"
    )
    print(
        f"  Right Fold Clearance:  {centering.right_clearance_px:.1f} px ({centering.right_clearance_px / args.dpi:.4f}\") --> Buffer: {right_buf_px:+.1f} px ({right_buf_px / args.dpi:+.4f}\") [{'PASS' if right_pass else 'FAIL'}]"
    )
    print(f"  Shift Applied:         {centering.shift_x_px:.1f} px")
    print(f"\nDiagnostic Proof Generated: {output_path}")
    if spec.spine_text_warning:
        print(f"\nWarning: {spec.spine_text_warning}")
    print("=======================================================\n")


def _handle_install_skill(args: argparse.Namespace) -> None:
    """Install the bundled cover-prepress SKILL.md into global and/or workspace AI harness folders."""
    bundled_skill = Path(__file__).resolve().parent / "prepress" / "data" / "SKILL.md"
    if not bundled_skill.exists():
        print(f"Error: Bundled SKILL.md not found at {bundled_skill}", file=sys.stderr)
        sys.exit(1)

    skill_content = bundled_skill.read_text(encoding="utf-8")
    targets: list[tuple[str, Path]] = []

    if getattr(args, "install_global", True):
        home = Path.home()
        targets.extend(
            [
                ("Antigravity (Global)", home / ".gemini" / "config" / "skills" / "cover-prepress" / "SKILL.md"),
                ("Claude Code (Global)", home / ".claude" / "skills" / "cover-prepress" / "SKILL.md"),
                ("OpenAI Codex (Global)", home / ".codex" / "skills" / "cover-prepress" / "SKILL.md"),
            ]
        )

    ws_dir = getattr(args, "workspace_dir", None)
    if ws_dir is not None:
        ws = Path(ws_dir).resolve()
        targets.extend(
            [
                ("Antigravity (Workspace)", ws / ".agent" / "skills" / "cover-prepress" / "SKILL.md"),
                ("Claude Code (Workspace)", ws / ".claude" / "skills" / "cover-prepress" / "SKILL.md"),
                ("Codex / Portable (Workspace)", ws / "skills" / "cover-prepress" / "SKILL.md"),
            ]
        )

    installed_paths: list[str] = []
    for label, dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(skill_content, encoding="utf-8")
        installed_paths.append(f"  ✓ {label:<28} -> {dest}")

    print("\n=======================================================")
    print("  COVER-PREPRESS SKILL INSTALLED SUCCESSFULLY")
    print("=======================================================")
    for line in installed_paths:
        print(line)
    print("\nYour staff can now prompt Antigravity, Claude Code, or Codex")
    print("in any folder, or launch the visual editor with:")
    print("  mbooks cover-studio")
    print("=======================================================\n")


def _add_book_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--publisher", choices=["KDP", "IngramSpark", "Lulu"], help="Target publisher")
    parser.add_argument("--format", choices=["Paperback", "Hardcover"], required=True, help="Book format")
    parser.add_argument("--trim", required=True, help="Trim size e.g. '6 x 9'")
    parser.add_argument("--pages", type=int, required=True, help="Interior page count")
    parser.add_argument("--binding", help="Binding type e.g. 'Perfect Bound', 'Casewrap'")
    parser.add_argument("--ink", default="B&W", help="Interior ink type")
    parser.add_argument("--paper", default="White", help="Paper type")
    parser.add_argument("--cover-finish", default="Matte", choices=["Matte", "Glossy"], help="Cover finish")
    parser.add_argument("--bleed", action="store_true", help="Whether interior has bleed")
    parser.add_argument("--distribution-goal", choices=["Direct", "Global/Retail Distribution"], help="Distribution goal")


def _build_book_config(args: argparse.Namespace) -> BookConfiguration:
    try:
        trim = TrimSize.from_string(args.trim)
    except ValueError:
        print(f"Error: Invalid trim size format: {args.trim}", file=sys.stderr)
        sys.exit(1)

    return BookConfiguration(
        publisher=Publisher(args.publisher) if args.publisher else None,
        book_format=BookFormat(args.format),
        binding=BindingType(args.binding) if getattr(args, "binding", None) else None,
        trim_size=trim,
        page_count=args.pages,
        interior_ink=InteriorInk(args.ink),
        paper_type=PaperType(args.paper),
        cover_finish=CoverFinish(args.cover_finish),
        has_bleed=args.bleed,
        distribution_goal=DistributionGoal(args.distribution_goal) if getattr(args, "distribution_goal", None) else None,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mbooks",
        description="Markee Books — Cover Prepress Engine, Calculator & Web Studio",
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # calculate command
    calc_parser = subparsers.add_parser("calculate", help="Calculate spine, cover, interior, and print specifications")
    _add_book_config_args(calc_parser)
    calc_parser.add_argument("--list-price", type=float, default=None, help="Optional retail list price in USD")

    # cover-resize command
    resize_parser = subparsers.add_parser(
        "cover-resize",
        help="Resize cover wrap mockup or assemble panels into print-ready spread",
    )
    resize_parser.add_argument("-i", "--input", type=Path, default=None, help="Path to cover mockup image (spread)")
    resize_parser.add_argument("--front", type=Path, default=None, help="Path to front cover panel image")
    resize_parser.add_argument("--spine", type=Path, default=None, help="Path to spine panel image")
    resize_parser.add_argument("--back", type=Path, default=None, help="Path to back cover panel image")
    resize_parser.add_argument("-p", "--publisher", required=True, help="Target publisher: kdp, ingram, lulu")
    resize_parser.add_argument("-b", "--binding", required=True, help="Binding type: paperback, casewrap")
    resize_parser.add_argument("-t", "--trim", required=True, help="Trim size string, e.g. '6x9' or '6 x 9'")
    resize_parser.add_argument("--pages", type=int, required=True, help="Interior page count")
    resize_parser.add_argument("--paper", default="white", help="Paper stock (e.g. white, cream, color)")
    resize_parser.add_argument("--ink", default="black", help="Interior ink type (e.g. black, standard_color, premium_color)")
    resize_parser.add_argument("--dpi", type=int, default=300, help="Target resolution DPI (default: 300)")
    resize_parser.add_argument("--spine-bounds", default=None, help="Override spine crease coordinates as 'x_left,x_right'")
    resize_parser.add_argument("--spine-shift-px", type=float, default=0.0, help="Manual horizontal spine shift in pixels")
    resize_parser.add_argument("--safe-buffer", type=float, default=0.0, help="Configurable safety buffer in inches")
    resize_parser.add_argument("-o", "--output", default=None, help="Output file path for resized spread image or PDF")
    resize_parser.add_argument("--export-pdf", action="store_true", help="Export print-ready PDF with proper PDF page boxes")
    resize_parser.add_argument("--json", action="store_true", help="Output JSON summary with dimensions, clearances, and safe status")

    # cover-proof command
    proof_parser = subparsers.add_parser(
        "cover-proof",
        help="Generate diagnostic proof image with guidelines and zoomed spine metrics",
    )
    proof_parser.add_argument("-i", "--input", type=Path, required=True, help="Path to cover spread image (or raw mockup)")
    proof_parser.add_argument("-p", "--publisher", required=True, help="Target publisher: kdp, ingram, lulu")
    proof_parser.add_argument("-b", "--binding", required=True, help="Binding type: paperback, casewrap")
    proof_parser.add_argument("-t", "--trim", required=True, help="Trim size string, e.g. '6x9' or '6 x 9'")
    proof_parser.add_argument("--pages", type=int, required=True, help="Interior page count")
    proof_parser.add_argument("--paper", default="white", help="Paper stock (e.g. white, cream, color)")
    proof_parser.add_argument("--ink", default="black", help="Interior ink type (e.g. black, standard_color, premium_color)")
    proof_parser.add_argument("--dpi", type=int, default=300, help="Target resolution DPI (default: 300)")
    proof_parser.add_argument("--spine-bounds", default=None, help="Override spine crease coordinates as 'x_left,x_right'")
    proof_parser.add_argument("--spine-shift-px", type=float, default=0.0, help="Manual horizontal spine shift in pixels")
    proof_parser.add_argument("--safe-buffer", type=float, default=0.0, help="Configurable safety buffer in inches")
    proof_parser.add_argument("-o", "--output", default=None, help="Output path for diagnostic proof image (PNG/JPG)")
    proof_parser.add_argument("--json", action="store_true", help="Output JSON with gap measurements and Pass/Fail status")

    # cover-studio command
    studio_parser = subparsers.add_parser(
        "cover-studio",
        help="Launch interactive local Web Studio for visual cover prepress",
    )
    studio_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    studio_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    studio_parser.add_argument("--reload", action="store_true", default=False, help="Enable auto-reload for development")

    # install-skill command
    skill_parser = subparsers.add_parser(
        "install-skill",
        help="Install the cover-prepress AI skill across Antigravity, Claude Code, and Codex",
    )
    skill_parser.add_argument(
        "--global",
        dest="install_global",
        action="store_true",
        default=True,
        help="Install globally into user home skill folders (~/.gemini, ~/.claude, ~/.codex) [default]",
    )
    skill_parser.add_argument(
        "--no-global",
        dest="install_global",
        action="store_false",
        help="Skip global user home installation",
    )
    skill_parser.add_argument(
        "--workspace",
        dest="workspace_dir",
        type=Path,
        default=None,
        help="Optional project workspace folder to also install .agent/skills, .claude/skills, and skills/",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return

    if args.command == "install-skill":
        _handle_install_skill(args)
        return

    if args.command == "cover-studio":
        import uvicorn

        print(f"Starting Markee Books Cover Studio at http://{args.host}:{args.port}")
        uvicorn.run("mbooks.studio.server:app", host=args.host, port=args.port, reload=args.reload)
        return

    if args.command == "cover-resize":
        _handle_cover_resize(args)
        return

    if args.command == "cover-proof":
        _handle_cover_proof(args)
        return

    if args.command == "calculate":
        config = _build_book_config(args)
        spec = calculate_specifications(config, list_price=args.list_price)
        print(json.dumps(spec.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return


if __name__ == "__main__":
    main()
