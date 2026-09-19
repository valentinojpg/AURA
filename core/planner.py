"""
AURA — Módulo de compatibilidad para core.planner (Fase 71).
Re-exporta todo desde aura.core.planner.
"""

from aura.core.planner import (
    DEFAULT_MAX_STEPS,
    Plan,
    PlanStep,
    extract_slots,
    is_destructive_plan,
    is_instruction_chain,
    plan_from_ai,
    plan_from_rules,
    restore_slots,
    restore_plan_slots,
    split_steps,
    validate_plan_capabilities,
)

__all__ = [
    "DEFAULT_MAX_STEPS",
    "Plan",
    "PlanStep",
    "extract_slots",
    "is_destructive_plan",
    "is_instruction_chain",
    "plan_from_ai",
    "plan_from_rules",
    "restore_slots",
    "restore_plan_slots",
    "split_steps",
    "validate_plan_capabilities",
]
