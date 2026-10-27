"""Apply Windows DWM title-bar appearance to native Qt windows."""
from __future__ import annotations
import ctypes
import sys


def apply_titlebar(widget, dark: bool) -> bool:
    """Keep native controls, requesting DWM immersive dark mode on Windows 10/11.

    Older builds may not support the flag; in that case keep the OS default.
    """
    if sys.platform != 'win32':
        return False
    try:
        dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
        fn = dwm.DwmSetWindowAttribute
        fn.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        fn.restype = ctypes.c_long
        hwnd = ctypes.c_void_p(int(widget.winId()))
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            if fn(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                widget.update()
                return True
    except (AttributeError, OSError, ValueError):
        pass
    return False
