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
