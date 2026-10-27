import unittest
from unittest.mock import Mock, patch
from app import native_titlebar as nt

class NativeTitlebarTests(unittest.TestCase):
    def test_non_windows_graceful(self):
        with patch.object(nt.sys,'platform','linux'):
            self.assertFalse(nt.apply_titlebar(Mock(), True))
    def test_windows_fallback_and_light_reset(self):
        calls=[]
        class Dwm:
            def __init__(self): self.DwmSetWindowAttribute=Fn()
        class Fn:
            def __call__(self, hwnd, attr, pointer, size):
                import ctypes
                calls.append((attr, ctypes.cast(pointer,ctypes.POINTER(ctypes.c_int)).contents.value))
                return -1 if attr==20 else 0
        widget=Mock(); widget.winId.return_value=123
        with patch.object(nt.sys,'platform','win32'), patch.object(nt.ctypes,'WinDLL',return_value=Dwm(),create=True):
            self.assertTrue(nt.apply_titlebar(widget,True))
            self.assertTrue(nt.apply_titlebar(widget,False))
        self.assertEqual(calls,[(20,1),(19,1),(20,0),(19,0)])
