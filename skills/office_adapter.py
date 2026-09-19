# -*- coding: utf-8 -*-
"""
Re-export de OfficeAdapter desde aura.skills.office_adapter para compatibilidad.
"""
from aura.skills.office_adapter import OfficeAdapter, _format_com_error

__all__ = ["OfficeAdapter", "_format_com_error"]
