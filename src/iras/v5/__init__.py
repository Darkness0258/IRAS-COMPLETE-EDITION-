"""IRAS v5 capability layer.

The v5 package keeps high-level autonomous capabilities modular so the v4.4
permissioned device/control core remains a stable safety boundary.
"""

from .runtime import V5Runtime, build_v5_runtime

__all__ = ["V5Runtime", "build_v5_runtime"]
