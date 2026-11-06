# Cover Prepress & Print Sizing

Print-ready book cover wrap geometry, 3-panel artwork decomposition, and interactive prepress proofing across Amazon KDP, IngramSpark, and Lulu.

## Language

### Print Geometry & Layout

**Spread Wrap**:
The full single-sheet print canvas spanning back cover, spine, front cover, and outer bleed or turn-in wrap margins.
_Avoid_: Full cover, flat cover, layout canvas

**Trim Area**:
The finished width and height of a closed book panel after printer guillotine cutting (paperback) or board placement (casewrap hardcover).
_Avoid_: Page size, cut area, book size

**Bleed**:
The sacrificial outer margin (`0.125"`) beyond a paperback's trim line that is trimmed off during binding so artwork reaches the cut edge without white slivers.
_Avoid_: Overhang, margin, padding

**Turn-In Wrap**:
The outer perimeter extension (`0.500"`–`0.625"`) on a casewrap hardcover that folds around and glues to the inside of the binder board.
_Avoid_: Hardcover bleed, fold-over, flap

**French Groove (Hinge)**:
The flexible joint channel on either side of a hardcover spine board where the front and back covers hinge open.
_Avoid_: Spine margin, gutter, fold gap

**Spine Crease**:
The vertical fold boundary separating the back cover from the spine (`left_x`) and the spine from the front cover (`right_x`).
_Avoid_: Spine border, divider line, fold mark

**Spine Safe Zone**:
The inner vertical strip of the spine inset from both spine creases (`0.0625"` standard, `0.03125"` low-page Lulu) where spine lettering is guaranteed not to wrap onto the cover hinges.
_Avoid_: Spine padding, text box, inner spine

**Panel Safe Zone**:
The inner rectangular area of the front or back cover inset from the trim line and hinge where text and critical artwork are protected from cutting variance and hinge creasing.
_Avoid_: Inner margin, text area, content box

**Barcode Clear Zone**:
The reserved rectangular region on the lower-right back cover where publisher ISBN barcodes are printed and foreground text must not intrude.
_Avoid_: ISBN box, barcode placeholder

**Skeletal Guide**:
One of the 24 publisher geometry lines (15 vertical, 9 horizontal) marking bleed/wrap edges, trim lines, spine creases, hinge joints, panel centers, and safe zones.
_Avoid_: Grid line, ruler, border

### Artwork Segmentation & Studio

**Cover Part (Layer)**:
One of the three independently movable, resizable, and croppable artwork regions (`back`, `spine`, `front`) placed on the Spread Wrap.
_Avoid_: Slice, segment, widget

**Source Crop**:
Normalized `[0..1)` edge insets (`cropL`, `cropT`, `cropR`, `cropB`) that trim away edges of a Cover Part's original bitmap without stretching or squishing the remaining artwork.
_Avoid_: Clip rect, mask, zoom crop

**Optical Centering**:
Aligning spine lettering or emblems by their foreground luminance center of mass rather than geometric bounding-box midpoint.
_Avoid_: Auto-centering, text centering

**Direct-Fit Snapping**:
Magnetic alignment of a Cover Part's edges or center to the nearest vertical or horizontal Skeletal Guide when zoomed below `75%`.
_Avoid_: Grid lock, auto-fit
