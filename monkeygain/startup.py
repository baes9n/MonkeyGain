"""Fast dependency checks before opening the GTK workspace.

APT resolves mandatory package dependencies during Debian installation. These
checks also cover developers launching a checkout and broken system installs.
"""
from __future__ import annotations

from dataclasses import dataclass
import importlib

from .core import BackendStatus, probe_backend


@dataclass(frozen=True)
class RuntimeStatus:
    ready: bool
    message: str = ''
    backend: BackendStatus = BackendStatus()


def check_runtime() -> RuntimeStatus:
    """Return an actionable error instead of exposing binary-selection widgets."""
    try:
        importlib.import_module('mutagen')
    except (ImportError, OSError):
        return RuntimeStatus(False, 'Audio metadata support is unavailable. Reinstall MonkeyGain with APT to restore python3-mutagen.')
    backend = probe_backend()
    if not backend.path:
        return RuntimeStatus(False, 'The ReplayGain engine is unavailable. Reinstall MonkeyGain with APT to restore rsgain.')
    return RuntimeStatus(True, backend=backend)
