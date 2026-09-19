"""
AURA — Paquete de automatizaciones (Fase 19)

Exporta el motor de automatizaciones y sus tipos públicos.
"""

from automation.engine import (
    AutomationEngine,
    AutomationResult,
    AutomationInfo,
    StepResult,
    automation_engine,
)

__all__ = [
    "AutomationEngine",
    "AutomationResult",
    "AutomationInfo",
    "StepResult",
    "automation_engine",
]
