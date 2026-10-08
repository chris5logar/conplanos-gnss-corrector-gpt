"""Ensure the Streamlit entry point and its independently imported screens stay in sync.

Streamlit reruns app.py without necessarily discarding modules in sys.modules.
When a deployment changes an imported UI module, from-import can keep rendering
a previous version while app.py displays a new global version.
"""
from __future__ import annotations

import importlib
from types import ModuleType


def load_ui_module(module_name: str, expected_version: str) -> ModuleType:
    """Reload an outdated imported UI module and refuse a version mismatch.

    This is deliberately not a Streamlit cache: cached screen code must never
    outlive the source release advertised to operators.
    """
    module = importlib.import_module(module_name)
    if getattr(module, "UI_VERSION", None) != expected_version:
        importlib.invalidate_caches()
        module = importlib.reload(module)
    loaded_version = getattr(module, "UI_VERSION", None)
    if loaded_version != expected_version:
        raise RuntimeError(
            f"Módulo {module_name} desactualizado: se esperaba {expected_version} "
            f"y se cargó {loaded_version or 'sin versión'}. Reinicia la app."
        )
    return module


def ensure_core_schema(expected_version: str) -> ModuleType:
    """Synchronize Leica report classes as well as Python screen modules.

    Streamlit hot reruns can keep an old `core.ReportInfo` class in memory
    even when app.py and the UI source are up to date. Checking just the
    read_csv() function signature is not sufficient.
    """
    from dataclasses import fields, is_dataclass

    required_report_fields = {
        "reference_lat", "reference_lon", "mobile_lat", "mobile_lon",
        "utm_zone", "utm_hemisphere", "error_x_m", "error_y_m", "error_z_m",
    }

    module = importlib.import_module("core")

    def _valid(candidate):
        report_class = getattr(candidate, "ReportInfo", None)
        return (
            getattr(candidate, "CORE_SCHEMA_VERSION", None) == expected_version
            and isinstance(report_class, type)
            and is_dataclass(report_class)
            and required_report_fields.issubset(
                {item.name for item in fields(report_class)}
            )
        )

    if not _valid(module):
        importlib.invalidate_caches()
        module = importlib.reload(module)
    if not _valid(module):
        raise RuntimeError(
            "El lector del informe GNSS no coincide con la versión publicada. "
            "Reinicia la aplicación Streamlit antes de continuar."
        )
    return module
