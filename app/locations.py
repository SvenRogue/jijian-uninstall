"""Read-only application installation location resolution."""
from __future__ import annotations
import os
import ntpath
from .drive_label import _expand, _fallback_path, _system_executable


def resolve_location(entry):
    """Return (directory, provenance), or ('', reason) when not reliable.

    Explicit existing InstallLocation wins. Executable parents are only offered
    as inferred locations and should be labelled as such in the UI.
    """
    raw = _expand((getattr(entry, 'install_location', '') or '').strip().strip('"'))
    if raw and os.path.isdir(raw):
        return os.path.normpath(raw), '安装登记'
    for field, icon in (('display_icon', True), ('uninstall_string', False), ('quiet_uninstall_string', False)):
        path = _fallback_path(getattr(entry, field, ''), icon=icon)
        if not path or _system_executable(path) or not os.path.isfile(path):
            continue
        parent = ntpath.dirname(path)
        if parent and os.path.isdir(parent):
            return os.path.normpath(parent), '从程序路径推断'
    return '', '没有可确认的安装位置'
