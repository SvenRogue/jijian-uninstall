"""Registry access layer.

Uses ``winreg`` (no subprocess, real unicode, no HKCU/HKEY_CURRENT_USER alias
mismatch) with a ``reg.exe`` fallback for shapes winreg cannot express.
"""
from __future__ import annotations

import subprocess
import sys

IS_WIN = sys.platform == "win32"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

ROOTS = {
    "HKCU": winreg.HKEY_CURRENT_USER if winreg else None,
    "HKLM": winreg.HKEY_LOCAL_MACHINE if winreg else None,
}

ROOT_LABEL = {
    "HKEY_CURRENT_USER": "HKCU",
    "HKEY_LOCAL_MACHINE": "HKLM",
    "HKEY_CLASSES_ROOT": "HKCR",
    "HKEY_USERS": "HKU",
}


def split_key(full: str) -> tuple[str, str]:
    """'HKCU\\Software\\X' -> ('HKCU', 'Software\\X')"""
    parts = full.split("\\", 1)
    if len(parts) == 1:
        return parts[0].upper(), ""
    root, rest = parts[0].upper(), parts[1]
    root = ROOT_LABEL.get(root, root)
    return root, rest


def open_key(full: str, write: bool = False):
    if not winreg:
        raise OSError("winreg unavailable")
    root, rest = split_key(full)
    h = ROOTS.get(root)
    if h is None:
        raise OSError(f"unknown hive {root}")
    access = winreg.KEY_READ | ((winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) if write else 0)
    if write:
        access = winreg.KEY_READ | winreg.KEY_WRITE
    return winreg.OpenKey(h, rest, 0, access)


def subkeys(full: str) -> list[str]:
    """Full child key paths."""
    try:
        k = open_key(full)
    except OSError:
        return []
    out = []
    try:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(k, i)
            except OSError:
                break
            out.append(full.rstrip("\\") + "\\" + name)
            i += 1
    finally:
        winreg.CloseKey(k)
    return out


def values(full: str) -> dict[str, str]:
    """All string values of a key, as str."""
    try:
        k = open_key(full)
    except OSError:
        return {}
    out: dict[str, str] = {}
    try:
        i = 0
        while True:
            try:
                name, data, _t = winreg.EnumValue(k, i)
            except OSError:
                break
            if isinstance(data, str):
                out[name] = data
            elif isinstance(data, int):
                out[name] = str(data)
            i += 1
    finally:
        winreg.CloseKey(k)
    return out


def exists(full: str) -> bool:
    try:
        k = open_key(full)
        winreg.CloseKey(k)
        return True
    except OSError:
        return False


def delete_tree(full: str) -> bool:
    """Delete a key and its subkeys. Returns True when it is gone afterwards."""
    if not exists(full):
        return True
    _reg_delete(full)
    return not exists(full)


def _reg_delete(full: str) -> None:
    """reg.exe resolves hive aliases and handles the recursion."""
    root, rest = split_key(full)
    try:
        subprocess.run(["reg", "delete", f"{root}\\{rest}", "/f"],
                       capture_output=True, creationflags=NO_WINDOW, timeout=120)
    except Exception:
        pass


def delete_tree_deep(full: str) -> bool:
    """winreg recursion first (unicode-safe), reg.exe as backup."""
    if not exists(full):
        return True
    try:
        _delete_recursive(full)
    except OSError:
        pass
    if exists(full):
        _reg_delete(full)
    return not exists(full)


def _delete_recursive(full: str) -> None:
    root, rest = split_key(full)
    h = ROOTS[root]
    if winreg is None:
        return
    for child in _child_names(h, rest):
        _delete_recursive(f"{root}\\{rest}\\{child}")
    winreg.DeleteKey(h, rest)


def _child_names(h, path: str) -> list[str]:
    names = []
    try:
        k = winreg.OpenKey(h, path, 0, winreg.KEY_READ)
    except OSError:
        return names
    try:
        i = 0
        while True:
            try:
                names.append(winreg.EnumKey(k, i))
            except OSError:
                break
            i += 1
    finally:
        winreg.CloseKey(k)
    return names
