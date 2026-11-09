# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Loads the integration modules as package 'cdt' without importing Home Assistant."""

import sys
import types
from pathlib import Path

_PKG_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "drying_pilot"
)
_pkg = types.ModuleType("cdt")
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules.setdefault("cdt", _pkg)
