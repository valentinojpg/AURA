"""
Shim de compatibilidad para ui.layout_rules.
Reexporta desde aura.ui.layout_rules.
"""

from aura.ui.layout_rules import (
    LayoutRuleViolationError,
    get_control_children,
    is_strict_mode,
    validate_layout,
)

__all__ = [
    "LayoutRuleViolationError",
    "get_control_children",
    "is_strict_mode",
    "validate_layout",
]
