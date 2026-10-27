"""Determine a display location without probing or modifying the filesystem."""
from __future__ import annotations

import ntpath
import os
import re

_UNKNOWN = "位置未知"
_NETWORK = "网络位置"
_ENV = re.compile(r"%([^%]+)%")
_DRIVE = re.compile(r"^[A-Za-z]:\\")
_EXECUTABLE = re.compile(r"\.exe$", re.IGNORECASE)


def _expand(value: str) -> str:
    # Windows environment variable names are case-insensitive, even when tests
    # or other callers run on a different platform.
    environment = {key.casefold(): val for key, val in os.environ.items()}
    return _ENV.sub(lambda match: environment.get(match[1].casefold(), match[0]), value)


def _location(path: str) -> str | None:
    path = _expand(path.strip()).replace("/", "\\")
    if not path or '%' in path or '"' in path or any(ord(c) < 32 for c in path):
        return None
    if path.startswith('\\\\?\\') or path.startswith('\\\\.\\'):
        return None
    if path.startswith('\\\\'):
        parts = path[2:].split('\\')
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return None
        return _NETWORK
    if not _DRIVE.match(path):
        return None
    return path[:2].upper()


def _system_executable(path: str) -> bool:
    path = ntpath.normpath(_expand(path).replace('/', '\\'))
    base = ntpath.basename(path).casefold()
    if base in {'msiexec.exe', 'rundll32.exe', 'msiexec', 'rundll32'}:
        return True
    # Do not infer an application's location from Windows binaries.
    parts = [part.casefold() for part in path.split('\\')]
    if len(parts) > 1 and parts[1] in {'windows', 'winnt'}:
        return True
    if any(part in {'windows', 'winnt'} and index + 1 < len(parts)
           and parts[index + 1] in {'system32', 'syswow64', 'system'}
           for index, part in enumerate(parts)):
        return True
    for variable in ('SystemRoot', 'windir'):
        root = _expand(f'%{variable}%')
        if '%' not in root:
            root = ntpath.normcase(ntpath.normpath(root))
            normalized = ntpath.normcase(path)
            if normalized == root or normalized.startswith(root.rstrip('\\') + '\\'):
                return True
    return False


def _fallback_path(value: str, *, icon: bool) -> str | None:
    value = _expand((value or '').strip())
    if not value:
        return None
    if value.startswith('"'):
        end = value.find('"', 1)
        if end < 0:
            return None
        path, rest = value[1:end], value[end + 1:].strip()
        if icon and rest and not re.fullmatch(r',\s*-?\d+', rest):
            return None
        if not icon and rest and not value[end + 1].isspace():
            return None
    else:
        if '"' in value:
            return None
        if icon:
            path = re.sub(r',\s*-?\d+\s*$', '', value).strip()
        else:
            # An unquoted executable path with spaces and arguments is ambiguous.
            path = value.split(None, 1)[0]
            if not _EXECUTABLE.search(path):
                return None
    if not _EXECUTABLE.search(path) or _system_executable(path):
        return None
    return path


def drive_label(entry) -> str:
    """Return the install drive, network location, or an unknown label."""
    raw = (getattr(entry, 'install_location', '') or '').strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        raw = raw[1:-1]
    # Executables in system directories do not establish an app location.
    if raw and not (_EXECUTABLE.search(raw) and _system_executable(raw)):
        label = _location(raw)
        if label:
            return label
    for field, icon in (('display_icon', True), ('uninstall_string', False),
                        ('quiet_uninstall_string', False)):
        path = _fallback_path(getattr(entry, field, ''), icon=icon)
        if path:
            label = _location(path)
            if label:
                return label
    return _UNKNOWN
