"""Prepress core engine and cover resizing package."""

from .specs import (
    PrepressSpec,
    calculate_prepress_spec,
)
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
from .centering import (
    CenteringResult,
    compute_optical_centering,
    measure_shadow_bias,
)
from .resizer import (
    DecomposedCoverResult,
    DecomposedLayer,
    ResizeOptions,
    ResizeResult,
    decompose_cover_to_layers,
    resize_cover_wrap,
)
from .pdf import (
    PreflightError,
    TACLimitExceededError,
    RegistrationBlackError,
    flatten_transparency,
    inspect_tac_and_registration,
    export_print_ready_pdf,
)
from .proof import (
    generate_diagnostic_proof,
)

__all__ = [
    "PrepressSpec",
    "calculate_prepress_spec",
    "CreaseDetectionResult",
    "detect_spine_creases",
    "trim_shadow_and_infill_background",
    "SpineElement",
    "segment_spine_elements",
    "calculate_element_scaling",
    "reconstruct_clean_spine_background",
    "CenteringResult",
    "compute_optical_centering",
    "measure_shadow_bias",
    "DecomposedCoverResult",
    "DecomposedLayer",
    "ResizeOptions",
    "ResizeResult",
    "decompose_cover_to_layers",
    "resize_cover_wrap",
    "PreflightError",
    "TACLimitExceededError",
    "RegistrationBlackError",
    "flatten_transparency",
    "inspect_tac_and_registration",
    "export_print_ready_pdf",
    "generate_diagnostic_proof",
]
