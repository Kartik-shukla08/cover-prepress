# AGENTS.md — Cover Prepress & Studio

## Context Pointers

- **Domain vocabulary & geometry terms** (`Spread Wrap`, `Trim Area`, `Bleed`, `Turn-In Wrap`, `French Groove`, `Spine Crease`, `Cover Part`, `Source Crop`, `Skeletal Guide`): read [`GLOSSARY.md`](GLOSSARY.md) before changing prepress calculations, CLI flags, or studio UI wording.
- **5-step prepress workflow, publisher formulas, & CLI flags**: read [`skills/cover-prepress/SKILL.md`](skills/cover-prepress/SKILL.md) when modifying CLI commands, publisher rules, or agent skill instructions.

## Single Sources of Truth & Architecture Invariants

- **Publisher Wrap Geometry** ([`src/mbooks/prepress/specs.py`](src/mbooks/prepress/specs.py)): `calculate_prepress_spec()` is the single authority for Amazon KDP, IngramSpark, and Lulu dimensions, spine width, bleed/turn-in wrap, French groove hinges, safe zones, and barcode zones. Never hardcode publisher margins in the CLI or frontend.
- **3-Panel Segmentation & Resizing** ([`src/mbooks/prepress/resizer.py`](src/mbooks/prepress/resizer.py)):
  - `decompose_cover_to_layers()` slices a source cover along detected or manual `Spine Crease` boundaries into three lossless PNG `Cover Part` bitmaps (`back`, `spine`, `front`) with default 300 DPI placement coordinates.
  - `resize_cover_wrap()` performs non-uniform 3-panel warping with `Optical Centering` and edge bleeding for headless CLI runs.
- **PDF/X Box Embedding** ([`src/mbooks/prepress/pdf.py`](src/mbooks/prepress/pdf.py)): `generate_prepress_pdf()` embeds 300 DPI spreads into PDF with exact `MediaBox`, `BleedBox`, `TrimBox`, and `ArtBox` coordinates in points (`72 pt/inch`).
- **Interactive Cover Studio** ([`src/mbooks/studio/static/studio.js`](src/mbooks/studio/static/studio.js), [`index.html`](src/mbooks/studio/static/index.html), [`studio.css`](src/mbooks/studio/static/studio.css)):
  - **Coordinate space**: `state.layers` (`back`, `spine`, `front`) stores `x, y, w, h` in **300 DPI print pixels** (`inch * 300`) and normalized `Source Crop` insets (`cropL, cropT, cropR, cropB` in `[0..0.95]`).
  - **Pasteboard accessibility**: Artwork extending outside the `Spread Wrap` remains visible and interactive under a translucent grey pasteboard overlay (`drawPasteboardOverlay`), while `exportCompositePdf` clips strictly to the print canvas.
  - **Handles & Hit-Testing**: Resize/crop handles are zoom-adaptive circles (`getHandleRadiusCanvas`) tested via Euclidean distance (`hitTestHandles`) so corners and midpoints stay distinct on narrow spines when zoomed out.
  - **2D Direct-Fit Snapping**: `getSkeletalSnapTargets()` snaps `Cover Part` edges/centers to all 15 vertical and 9 horizontal `Skeletal Guide` lines during move, resize, and crop when `state.zoom < 0.75` (`shouldSnap(e)`), bypassed when `state.zoom >= 0.75` or holding `Alt`.
  - **Zoom Performance**: `animateZoomTo()` uses a 3-frame GPU CSS width/height transition (`6%` wheel step, `10%` button step) and calls `renderCanvas()` only on the final frame.
  - **Cache busting**: Whenever you modify `studio.js` or `studio.css`, increment the `?v=YYYYMMDD_vN` query string in [`src/mbooks/studio/static/index.html`](src/mbooks/studio/static/index.html).
- **Cross-Harness Skill Parity**: [`skills/cover-prepress/SKILL.md`](skills/cover-prepress/SKILL.md) is canonical. Whenever you edit it, copy the identical file to:
  1. [`.agent/skills/cover-prepress/SKILL.md`](.agent/skills/cover-prepress/SKILL.md)
  2. [`.claude/skills/cover-prepress/SKILL.md`](.claude/skills/cover-prepress/SKILL.md)
  3. [`src/mbooks/prepress/data/SKILL.md`](src/mbooks/prepress/data/SKILL.md)

## Verification Gate

Run the full test suite before completing any code, UI, or skill change:

```powershell
$env:PYTHONPATH="src"; pytest tests/ -q
```

Every test in `tests/` (prepress specs, crease detection, optical centering, PDF boxes, studio API, and skill conformance) must pass.
