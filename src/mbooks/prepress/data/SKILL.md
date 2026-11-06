---
name: cover-prepress
description: Comprehensive prepress and book cover resizing system that automates print-ready wrap calculation, 3-panel wrap segmentation (back, spine, front), diagnostic proofing, crease detection, luminance optical centering, and multi-publisher PDF box generation across Amazon KDP, IngramSpark, and Lulu.
---

# Prepress Book Cover Resizing & Verification Guide

The `cover-prepress` skill provides an autonomous, end-to-end prepress system rooted in `packages/mbooks-calc`. It executes with zero external cloud dependencies (no Supabase, R2, or Inngest calls required), automating print-ready wrap calculation, 3-panel wrap segmentation (back, spine, front), crease detection, 3D shadow bleed trimming, 1:1 ornament scaling, typography aspect-clamping, glyph-only luminance optical centering, and multi-publisher PDF box generation across Amazon KDP, IngramSpark, and Lulu.

---

## Prepress Architecture & Pipeline

The system decouples prepress mathematics and image processing into standalone, deterministic modules:

```
[Source Artwork (Spread Mockup or Separate Panels: Front / Spine / Back)]
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │  mbooks.prepress.specs                       │  <-- Multi-publisher formulas & constants
        │  (KDP, IngramSpark, Lulu)                    │      (Paperback & Hardcover Casewrap)
        └──────────────────────┬───────────────────────┘
                               │ Target geometry (W, H, Spine W, Crease bounds, Bleeds)
                               ▼
        ┌──────────────────────────────────────────────┐
        │  mbooks.prepress.crease                      │  <-- Margin-isolated VPP & horizontal gradient
        │  (Fold Crease Detection)                     │      Finds x_left, x_right, trims 3D shadow bleed
        └──────────────────────┬───────────────────────┘
                               │ Cleaned background & segmented spine
                               ▼
        ┌──────────────────────────────────────────────┐
        │  mbooks.prepress.segmentation                │  <-- Connected components & classification
        │  (Foreground Segmentation)                   │      1:1 ornament scale, <=1.2x aspect clamp text
        └──────────────────────┬───────────────────────┘
                               │ Foreground elements & glyph masks
                               ▼
        ┌──────────────────────────────────────────────┐
        │  mbooks.prepress.centering                   │  <-- Luminance thresholding (L > L_bg + 25)
        │  (Optical Centering)                         │      Eliminates shadow bias, safe margin check
        └──────────────────────┬───────────────────────┘
                               │ Composed print spread image
                               ▼
        ┌──────────────────────────────────────────────┐
        │  mbooks.prepress.pdf                         │  <-- PyMuPDF PDF box embedding
        │  (PDF Box & Preflight)                       │      MediaBox, BleedBox, TrimBox, TAC limit
        └──────────────────────┬───────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
   ┌──────────────────────────┐  ┌──────────────────────────────────┐
   │ Diagnostic Proof Engine  │  │ User & Automation Interfaces:    │
   │ (Zoomed spine view, exact│  │ - Non-AI Staff CLI (mbooks cli)  │
   │  pixel gap measurements, │  │ - Web Studio (FastAPI + Canvas)  │
   │  real-time Pass/Fail)    │  │ - Cross-Harness Agent Skill      │
   └──────────────────────────┘  └──────────────────────────────────┘
```

### Publisher Dimension & Safety Matrix

| Publisher | Binding | Page Threshold for Spine Text | Spine Safe Margin | Total Bleed | TAC Ceiling |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Amazon KDP** | Paperback Perfect Bound | >= 79 pages | 0.0625" (1/16") | 0.125" (1/8") | 240% - 300% |
| **Amazon KDP** | Hardcover Casewrap | >= 79 pages | 0.0625" (1/16") | 0.560" wrap + hinge | 240% - 300% |
| **IngramSpark** | Paperback Perfect Bound | >= 48 pages | 0.0625" (or 0.03125") | 0.125" (1/8") | 240% |
| **IngramSpark** | Hardcover Casewrap | >= 48 pages | 0.0625" | 0.625" wrap + hinge | 240% |
| **Lulu** | Paperback Perfect Bound | > 80 pages | 0.125" (1/8") | 0.125" (1/8") | 270% |
| **Lulu** | Hardcover Casewrap | > 80 pages | 0.125" (1/8") | 0.750" wrap + hinge | 270% |

---

## Deterministic Multi-Step Workflow

Follow this 5-step procedural loop to resize, verify, and deliver print-ready covers:

### Step 1: Intake & Specification Calculation

Calculate the target physical spread geometry, spine width, safety zones, and PDF box coordinates before touching cover artwork.

Use `mbooks calculate` for quick dimension audits or `mbooks cover-resize` directly with publisher flags:

```bash
# Calculate physical specifications using mbooks calculate
mbooks calculate \
  --publisher KDP \
  --format Paperback \
  --binding "Perfect Bound" \
  --trim "6 x 9" \
  --pages 150 \
  --paper White \
  --ink "B&W"
```

Or calculate programmatically via the core API:
```python
from mbooks.prepress.specs import calculate_prepress_spec

spec = calculate_prepress_spec(
    publisher="kdp",
    binding="paperback",
    trim_w_in=6.0,
    trim_h_in=9.0,
    page_count=150,
    paper_type="white",
    ink_type="black",
)
print(f"Total Dimensions: {spec.total_w_in}\" x {spec.total_h_in}\"")
print(f"Spine Width: {spec.spine_w_in}\" (Text Allowed: {spec.allow_spine_text})")
```

Key Intake Rules:
- **Spine Text Minimums**: If page count is below the publisher threshold (< 79 pages on KDP, < 48 pages on IngramSpark, <= 80 pages on Lulu), spine text is disallowed (`allow_spine_text = False`). The system emits a formal warning and suppresses spine typography generation.
- **Paper & Ink Bulking Factors**: Page thickness varies by paper stock (e.g., white 0.002252" vs cream 0.0025" on KDP). The engine calculates exact spine thickness deterministically.

---

### Step 2: Diagnostic Proof Generation & Visual Inspection

Render a diagnostic proof image to verify fold creases, bleed boundaries, trim lines, and exact spine gap measurements before committing to final PDF exports:

```bash
# Generate diagnostic proof with visual guidelines and zoomed spine metrics
mbooks cover-proof \
  --input corpus/Denise_Hinton_Bazemore_-_That_show_lives_on_-_Cover_Design_2_3.jpeg \
  --publisher kdp \
  --binding paperback \
  --trim "6x9" \
  --pages 150 \
  --paper white \
  --ink black \
  --dpi 300 \
  --output proof_denise.png \
  --json
```

Visual Inspection Checklist:
1. **Spread Overview (Left Panel)**:
   - **Cyan Line**: Outer bleed boundary (0.125" on paperback). Artwork must extend fully to this line.
   - **Magenta Line**: Trim cut boundary. Key foreground art must not cross trim.
   - **Yellow / Orange Lines**: Left and right spine fold crease positions (`x_left`, `x_right`).
   - **Green Shaded Band**: Safe text area. Spine text and logos must remain strictly inside.
2. **Spine Zoom Inset (Right Panel)**:
   - Inspect the 300% magnified spine crop.
   - Verify that `Left Fold Clearance` and `Right Fold Clearance` display green `[PASS]` callouts.
   - Confirm that the pixel gap to the fold line satisfies `Clearance >= Safe Margin` (e.g. >= 19 px at 300 DPI for KDP 0.0625").

---

### Step 3: Boundary & Centering Refinement

If mockups feature heavy photographic drop shadows, 3D book mockup perspective distortion, or asymmetrical fold lines, refine the spine boundaries and optical positioning using explicit overrides:

```bash
# Refine spine crease coordinates, apply horizontal nudge, and add safety buffer
mbooks cover-resize \
  --input cover_mockup.jpg \
  --publisher kdp \
  --binding paperback \
  --trim "6x9" \
  --pages 150 \
  --spine-bounds "588,691" \
  --spine-shift-px 3.5 \
  --safe-buffer 0.02 \
  --dpi 300 \
  --output resized_spread.png \
  --json
```

Refinement Parameters:
- `--spine-bounds "x_left,x_right"`: Bypasses automated crease detection and forces exact pixel boundaries for the spine. Useful for complex gradient mockups.
- `--spine-shift-px <float>`: Manually nudges segmented spine typography along the horizontal axis (positive = right, negative = left).
- `--safe-buffer <float>`: Adds an extra safety cushion (in inches, e.g. `0.02`) on top of publisher minimum safe margins to guarantee zero glyph encroachment under loose physical binding tolerances.
- **Luminance Optical Centering**: The engine isolates bright glyph pixels (`L > L_bg + 25`) from dark drop shadows, eliminating 14-20px shadow bias and ensuring text is optically centered between spine creases.

---

### Step 4: Print-Ready Spread & PDF/X Export

Produce the final print-ready spread in PDF or high-resolution image format:

```bash
# Export print-ready PDF with embedded PDF box hierarchy
mbooks cover-resize \
  --input cover_mockup.jpg \
  --publisher kdp \
  --binding paperback \
  --trim "6x9" \
  --pages 150 \
  --paper white \
  --ink black \
  --dpi 300 \
  --export-pdf \
  --output print_cover_kdp.pdf \
  --json
```

Export & Preflight Verification:
- **PDF Box Structure**:
  * `MediaBox`: [0, 0, total_w_pt, total_h_pt] (Full spread extent)
  * `BleedBox`: [0, 0, total_w_pt, total_h_pt]
  * `TrimBox`: [bleed_pt, bleed_pt, total_w_pt - bleed_pt, total_h_pt - bleed_pt]
  * `CropBox`: Matching `MediaBox`
- **Zero Printer Marks**: Modern POD facilities (KDP, IngramSpark, Lulu) reject covers with crop marks or registration targets. The output contains zero printer marks.
- **TAC Ceiling Enforcement**: Total Area Coverage is checked against publisher ceilings (IngramSpark <= 240%, Lulu <= 270%, KDP <= 300%).
- **Registration Black Prohibition**: Rich black CMYK (100, 100, 100, 100) is flagged or converted to safe print black.
- **Preflight Flattening**: Transparency layers are flattened into high-resolution rasters (300 DPI) before PDF generation.

---

### Step 5: Local Web Studio for Non-AI Staff

When manual visual adjustment is preferred by non-AI design and production staff, launch the local Web Studio:

```bash
# Launch interactive local Web Studio
mbooks cover-studio --host 127.0.0.1 --port 8000
```

Studio Features:
- **FastAPI Backend + HTML5 Canvas**: Pure local server running on standard web browsers.
- **Artwork Upload & Drag-and-Drop**: Load spread mockups or separate front/spine/back panel images.
- **Interactive Sliders**: Real-time adjustment of `--spine-bounds`, `--spine-shift-px`, and `--safe-buffer`.
- **Live Skeletal Overlays**: Real-time canvas rendering of trim, bleed, fold creases, and safe zones.
- **Multi-Format Bundle Export**: One-click export of print-ready PDF, high-resolution JPG, and PNG packages.

---

## Complete CLI Flag Reference

The CLI commands `mbooks calculate`, `mbooks cover-resize`, `mbooks cover-proof`, and `mbooks cover-studio` share standardized parameters:

| CLI Option | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `-i`, `--input` | Path | Yes (resize/proof) | `None` | Path to full cover spread image or 3D mockup |
| `--front` | Path | Optional | `None` | Path to separate front cover panel image |
| `--spine` | Path | Optional | `None` | Path to separate spine panel image |
| `--back` | Path | Optional | `None` | Path to separate back cover panel image |
| `-p`, `--publisher` | String | Yes | `None` | Target publisher: `kdp`, `ingram`, `lulu` (or `KDP`, `IngramSpark`, `Lulu`) |
| `-b`, `--binding` | String | Yes | `None` | Binding style: `paperback`, `casewrap` (or `Perfect Bound`, `Casewrap`) |
| `--format` | String | Calc/Val | `None` | Book format: `Paperback`, `Hardcover` |
| `-t`, `--trim` | String | Yes | `None` | Trim dimensions: `"6x9"`, `"5.5x8.5"`, `"6 x 9"`, `"8.5x11"` |
| `--pages` | Integer | Yes | `None` | Total interior page count (e.g. `150`) |
| `--paper` | String | Optional | `white` | Paper type: `white`, `cream`, `color` |
| `--ink` | String | Optional | `black` | Interior ink: `black`, `standard_color`, `premium_color` (or `B&W`) |
| `--dpi` | Integer | Optional | `300` | Target print resolution (default 300 DPI) |
| `--spine-bounds` | String | Optional | `None` | Override crease coordinates as `"x_left,x_right"` (e.g. `"588,691"`) |
| `--spine-shift-px` | Float | Optional | `0.0` | Manual horizontal nudge in pixels (e.g. `3.5`) |
| `--safe-buffer` | Float | Optional | `0.0` | Additional safety margin in inches (e.g. `0.02`) |
| `-o`, `--output` | Path | Optional | `None` | Output file path for resized image or PDF |
| `--export-pdf` | Flag | Optional | `False` | Render and export print-ready PDF with PDF box hierarchy |
| `--json` | Flag | Optional | `False` | Output structured JSON metrics and Pass/Fail diagnostics |
| `--host` | String | Studio | `127.0.0.1` | Local IP binding for Web Studio |
| `--port` | Integer | Studio | `8000` | Listening port for Web Studio |

---

## Panel Assembly Workflow (Separate Front, Spine, Back)

When artwork is provided as distinct panel files instead of a single spread:

```bash
# Assemble individual panels into a cohesive IngramSpark casewrap cover
mbooks cover-resize \
  --front assets/front_cover.png \
  --spine assets/spine_panel.png \
  --back assets/back_cover.png \
  --publisher ingram \
  --binding casewrap \
  --trim "6x9" \
  --pages 280 \
  --paper white \
  --ink black \
  --dpi 300 \
  --export-pdf \
  --output ingram_hardcover_spread.pdf \
  --json
```

The assembly pipeline:
1. Calculates wrap margins (0.625" on IngramSpark casewrap) and hinge gaps.
2. Insets the front and back panels onto the board dimensions with fold wrap bleed.
3. Centers the spine panel between the hinge channels.
4. Validates that spine text meets safety clearance.
5. Embeds Casewrap `MediaBox`, `BleedBox`, and `TrimBox` into the exported PDF.

---

## Cross-Harness Execution Instructions

This skill is designed to run interchangeably across the three primary AI harnesses:

### 1. Google Antigravity
- **Location**: Installed under `.agent/skills/cover-prepress/SKILL.md` (and symlinked/copied to `skills/cover-prepress/SKILL.md`).
- **Autonomous Invocation**: When dispatched to prepare or verify book covers, Antigravity loads this skill definition and directly triggers commands via `run_command` in powershell or bash.
- **Interactive Verification**: Use the `--json` flag to inspect machine-readable clearances and confirm that `is_safe: true`.

### 2. Claude Code
- **Location**: Installed under `.claude/skills/cover-prepress/SKILL.md`.
- **CLI Workflow**: Claude Code invokes `mbooks cover-resize` or `mbooks cover-proof` via its Bash tool.
- **Self-Critique Protocol**:
  1. Execute `mbooks cover-proof` to generate the diagnostic proof image.
  2. Inspect the JSON clearance summary.
  3. If clearance fails (`is_safe: false`), apply `--spine-bounds` or `--spine-shift-px` until `is_safe: true`.
  4. Run `mbooks cover-resize --export-pdf` to produce the final print asset.

### 3. OpenAI Codex & CLI Automation
- **Location**: Installed under `skills/cover-prepress/SKILL.md`.
- **Scripted Pipelines**: Codex agents integrate `mbooks` into automated CI/CD batch workflows:
  ```python
  import subprocess
  import json

  cmd = [
      "mbooks", "cover-resize",
      "-i", "input_mockup.jpg",
      "-p", "kdp",
      "-b", "paperback",
      "-t", "6x9",
      "--pages", "200",
      "--export-pdf",
      "-o", "output_cover.pdf",
      "--json",
  ]
  res = subprocess.run(cmd, capture_output=True, text=True, check=True)
  data = json.loads(res.stdout)
  assert data["safe"] is True
  assert data["clearances"]["is_safe"] is True
  ```

---

## Security & Path Integrity Rules

- **Zero Cloud Leakage**: Cover assets must never be uploaded to external APIs, mock generation servers, or cloud endpoints. All calculations, raster processing, and PDF box embedding are performed strictly in local memory.
- **Path Traversal Protection**: All file paths passed to `--input`, `--front`, `--spine`, `--back`, or `--output` are resolved strictly against local directory paths. Relative path traversals outside the project tree are rejected.
