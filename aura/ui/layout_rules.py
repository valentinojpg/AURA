"""
AURA — Reglas y Validador Estricto de Layout (Fase 78 Fix Ronda 4).

Garantiza la integridad estructural del árbol de controles de Flet/Flutter:
- Regla R1: Cualquier control con posicionamiento absoluto (left, top, right, bottom != None)
            debe tener como padre DIRECTO un ft.Stack o residir en page.overlay.
- Regla R2: La raíz de la interfaz debe ser un ft.Stack(expand=True) con el layer de fondo en hijo [0].

Modo de ejecución:
- Modo Dev (LAYOUT_STRICT=True): Lanza LayoutRuleViolationError con el tipo de control,
  propiedades ofensivas y la cadena completa de padres hasta la raíz para depuración inmediata.
- Modo Prod (LAYOUT_STRICT=False): Auto-limpia las propiedades ofensivas (asigna None),
  registra un warning detallado en logs y permite que la aplicación arranque normalmente sin pantalla roja.
"""

from __future__ import annotations

import os
from typing import Any, Optional
import flet as ft

from config.settings import settings
from utils.logger import get_logger

_logger = get_logger("aura.ui.layout_rules")


class LayoutRuleViolationError(ValueError):
    """Excepción lanzada en modo estricto (LAYOUT_STRICT=True) ante violaciones de layout."""
    pass


def get_control_children(ctrl: Any) -> list[Any]:
    """
    Retorna todos los controles hijos directos de un control o contenedor de Flet.
    Inspecciona atributos estándar de jerarquía: controls, content, leading, trailing, etc.
    """
    children: list[Any] = []
    if ctrl is None:
        return children

    # 1. Contenedores con lista 'controls' (Stack, Column, Row, ListView, etc.)
    if hasattr(ctrl, "controls") and isinstance(ctrl.controls, (list, tuple)):
        for c in ctrl.controls:
            if isinstance(c, (ft.Control, ft.Page)):
                children.append(c)

    # 2. Contenedores con único 'content' (Container, Card, etc.)
    if hasattr(ctrl, "content"):
        content_val = getattr(ctrl, "content")
        if isinstance(content_val, (ft.Control, ft.Page)):
            children.append(content_val)

    # 3. Otros atributos que albergan sub-controles
    for attr in ("leading", "trailing", "title", "subtitle", "actions", "items"):
        if hasattr(ctrl, attr):
            val = getattr(ctrl, attr)
            if isinstance(val, (ft.Control, ft.Page)):
                children.append(val)
            elif isinstance(val, (list, tuple)):
                for item in val:
                    if isinstance(item, (ft.Control, ft.Page)):
                        children.append(item)

    return children


def is_strict_mode(strict: Optional[bool] = None) -> bool:
    """Determina si la validación de layout debe operar en modo estricto (dev)."""
    if strict is not None:
        return bool(strict)
    env_strict = os.environ.get("LAYOUT_STRICT", "").strip().lower()
    if env_strict in ("1", "true", "yes"):
        return True
    return settings.get_bool("LAYOUT_STRICT", False)


def validate_layout(
    root: Any,
    page: Optional[ft.Page] = None,
    strict: Optional[bool] = None,
) -> list[dict[str, Any]]:
    """
    Valida el árbol de controles desde la raíz según las reglas R1 y R2.

    Args:
        root: Control raíz de la UI (típicamente MainWindow._root_stack o ft.Page).
        page: Instancia opcional de ft.Page para validar controles en page.overlay.
        strict: Si es True, lanza LayoutRuleViolationError ante violaciones.
                Si es False, auto-limpia coordenadas inválidas y loguea warning.
                Si es None, se lee de configuración (LAYOUT_STRICT).

    Returns:
        Lista de violaciones detectadas (y auto-corregidas en modo prod).
    """
    strict_enabled = is_strict_mode(strict)
    violations: list[dict[str, Any]] = []

    if root is None:
        return violations

    # Identificar la raíz efectiva de la UI
    effective_root = root
    if isinstance(root, ft.Page):
        page = page or root
        if root.controls:
            effective_root = root.controls[0]

    # ──────────────────────────────────────────────────────────────
    # REGLA R2: La raíz debe ser un ft.Stack(expand=True) con fondo en hijo [0]
    # ──────────────────────────────────────────────────────────────
    if not isinstance(effective_root, ft.Stack):
        err_msg = (
            f"[Regla R2] La raíz de la UI debe ser ft.Stack, se encontró '{type(effective_root).__name__}'."
        )
        if strict_enabled:
            raise LayoutRuleViolationError(err_msg)
        _logger.warning("LAYOUT R2 VIOLATION: %s", err_msg)
        violations.append({
            "rule": "R2",
            "control": effective_root,
            "type": type(effective_root).__name__,
            "message": err_msg,
            "cleaned": False,
        })
    else:
        if not effective_root.expand:
            err_msg = "[Regla R2] El Stack raíz debe tener expand=True para garantizar cobertura completa."
            if strict_enabled:
                raise LayoutRuleViolationError(err_msg)
            _logger.warning("LAYOUT R2 AUTO-FIX: Asignando expand=True al Stack raíz.")
            effective_root.expand = True
            violations.append({
                "rule": "R2",
                "control": effective_root,
                "type": "Stack",
                "message": err_msg,
                "cleaned": True,
            })

        if not effective_root.controls or len(effective_root.controls) < 1:
            err_msg = "[Regla R2] El Stack raíz debe tener al menos hijo [0] como layer de fondo."
            if strict_enabled:
                raise LayoutRuleViolationError(err_msg)
            _logger.warning("LAYOUT R2 VIOLATION: %s", err_msg)
            violations.append({
                "rule": "R2",
                "control": effective_root,
                "type": "Stack",
                "message": err_msg,
                "cleaned": False,
            })

    # ──────────────────────────────────────────────────────────────
    # REGLA R1: left/top/right/bottom != None requiere padre Stack o page.overlay
    # ──────────────────────────────────────────────────────────────
    visited_ids: set[int] = set()

    def _walk_tree(
        ctrl: Any,
        parent: Optional[Any],
        parent_chain: list[str],
        is_in_overlay: bool = False,
    ) -> None:
        if ctrl is None:
            return
        ctrl_id = id(ctrl)
        if ctrl_id in visited_ids:
            return
        visited_ids.add(ctrl_id)

        ctrl_type = type(ctrl).__name__

        # Inspeccionar coordenadas absolutas
        has_coords = False
        coords: dict[str, Any] = {}
        for prop in ("left", "top", "right", "bottom"):
            val = getattr(ctrl, prop, None)
            if val is not None:
                has_coords = True
                coords[prop] = val

        if has_coords:
            # Validar padre legítimo: Stack directo o estar en overlay
            parent_is_stack = parent is not None and isinstance(parent, ft.Stack)
            is_valid = parent_is_stack or is_in_overlay

            if not is_valid:
                chain_str = " -> ".join(parent_chain + [ctrl_type])
                parent_type = type(parent).__name__ if parent is not None else "None"
                err_msg = (
                    f"[Regla R1] Control '{ctrl_type}' tiene coordenadas absolutas {coords} "
                    f"pero su padre directo es '{parent_type}' (debe ser ft.Stack o page.overlay).\n"
                    f"Cadena de ancestros: {chain_str}"
                )

                if strict_enabled:
                    raise LayoutRuleViolationError(err_msg)

                # Modo prod: Auto-limpiar propiedades para evitar crash de Flet en cliente
                for prop in ("left", "top", "right", "bottom"):
                    setattr(ctrl, prop, None)

                _logger.warning(
                    "LAYOUT R1 AUTO-CLEANED: Control '%s' con coordenadas %s fuera de Stack directo. "
                    "Propiedades limpiadas a None. Cadena: %s",
                    ctrl_type,
                    coords,
                    chain_str,
                )
                violations.append({
                    "rule": "R1",
                    "control": ctrl,
                    "type": ctrl_type,
                    "coords": coords,
                    "parent": parent_type,
                    "parent_chain": chain_str,
                    "cleaned": True,
                })

        # Recorrer hijos
        children = get_control_children(ctrl)
        new_chain = parent_chain + [ctrl_type]
        for child in children:
            _walk_tree(child, parent=ctrl, parent_chain=new_chain, is_in_overlay=is_in_overlay)

    # 1. Recorrer árbol principal
    _walk_tree(effective_root, parent=None, parent_chain=[], is_in_overlay=False)

    # 2. Recorrer page.overlay si está disponible
    overlay_container = getattr(page, "overlay", None)
    if overlay_container and isinstance(overlay_container, (list, tuple)):
        for overlay_ctrl in overlay_container:
            _walk_tree(overlay_ctrl, parent=None, parent_chain=["page.overlay"], is_in_overlay=True)

    return violations
