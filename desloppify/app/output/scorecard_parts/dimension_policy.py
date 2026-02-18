"""Scorecard dimension ordering and language policy constants."""

from __future__ import annotations

_SCORECARD_MAX_DIMENSIONS = 12
_DEFAULT_ELEGANCE_COMPONENTS: tuple[str, ...] = (
    "High Elegance",
    "Mid Elegance",
    "Low Elegance",
)
_ELEGANCE_COMPONENTS_BY_LANG: dict[str, tuple[str, ...]] = {
    "python": _DEFAULT_ELEGANCE_COMPONENTS,
    "typescript": _DEFAULT_ELEGANCE_COMPONENTS,
    "csharp": _DEFAULT_ELEGANCE_COMPONENTS,
}
_SUBJECTIVE_SCORECARD_ORDER_DEFAULT: tuple[str, ...] = (
    "Naming Quality",
    "Error Consistency",
    "Abstraction Fit",
    "Logic Clarity",
    "AI Generated Debt",
    "Type Safety",
    "Contracts",
    "Elegance",
)
_SUBJECTIVE_SCORECARD_ORDER_BY_LANG: dict[str, tuple[str, ...]] = {
    "python": (
        "Naming Quality",
        "Error Consistency",
        "Abstraction Fit",
        "Logic Clarity",
        "AI Generated Debt",
        "Contracts",
        "Elegance",
    ),
    "typescript": (
        "Naming Quality",
        "Error Consistency",
        "Abstraction Fit",
        "Logic Clarity",
        "AI Generated Debt",
        "Type Safety",
        "Elegance",
    ),
    "csharp": (
        "Naming Quality",
        "Error Consistency",
        "Abstraction Fit",
        "Logic Clarity",
        "AI Generated Debt",
        "Type Safety",
        "Elegance",
    ),
}
_MECHANICAL_SCORECARD_DIMENSIONS: tuple[str, ...] = (
    "File health",
    "Code quality",
    "Duplication",
    "Test health",
    "Security",
)
_SCORECARD_DIMENSIONS_BY_LANG: dict[str, tuple[str, ...]] = {
    "python": (
        *_MECHANICAL_SCORECARD_DIMENSIONS,
        "Naming Quality",
        "Error Consistency",
        "Abstraction Fit",
        "Logic Clarity",
        "AI Generated Debt",
        "Contracts",
        "Elegance",
    ),
    "typescript": (
        *_MECHANICAL_SCORECARD_DIMENSIONS,
        "Naming Quality",
        "Error Consistency",
        "Abstraction Fit",
        "Logic Clarity",
        "AI Generated Debt",
        "Type Safety",
        "Elegance",
    ),
    "csharp": (
        *_MECHANICAL_SCORECARD_DIMENSIONS,
        "Naming Quality",
        "Error Consistency",
        "Abstraction Fit",
        "Logic Clarity",
        "AI Generated Debt",
        "Type Safety",
        "Elegance",
    ),
}


__all__ = [
    "_DEFAULT_ELEGANCE_COMPONENTS",
    "_ELEGANCE_COMPONENTS_BY_LANG",
    "_MECHANICAL_SCORECARD_DIMENSIONS",
    "_SCORECARD_DIMENSIONS_BY_LANG",
    "_SCORECARD_MAX_DIMENSIONS",
    "_SUBJECTIVE_SCORECARD_ORDER_BY_LANG",
    "_SUBJECTIVE_SCORECARD_ORDER_DEFAULT",
]
