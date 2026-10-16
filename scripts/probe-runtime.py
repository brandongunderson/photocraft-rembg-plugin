"""Run with the bundled python.exe -I -B to verify imports and native DLL ownership."""
import ctypes
from ctypes import wintypes
import importlib.metadata
import json
from pathlib import Path
import site
import sys

import rembg
import onnxruntime
import numpy
import scipy
import numba
import pymatting
import skimage

root = Path(sys.executable).resolve().parent
if not sys.flags.isolated or site.ENABLE_USER_SITE:
    raise RuntimeError("The bundled interpreter must isolate user/global packages")
if any(not Path(path).resolve().is_relative_to(root) for path in sys.path):
    raise RuntimeError(f"Unexpected non-private Python search path: {sys.path}")

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.K32EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
kernel.K32EnumProcessModules.restype = wintypes.BOOL
kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
kernel.GetModuleFileNameW.restype = wintypes.DWORD
modules = (wintypes.HMODULE * 8192)()
required = wintypes.DWORD()
if not kernel.K32EnumProcessModules(kernel.GetCurrentProcess(), modules, ctypes.sizeof(modules), ctypes.byref(required)) or required.value > ctypes.sizeof(modules):
    raise ctypes.WinError(ctypes.get_last_error())
loaded = []
for module in modules[:required.value // ctypes.sizeof(wintypes.HMODULE)]:
    buffer = ctypes.create_unicode_buffer(32768)
    if not kernel.GetModuleFileNameW(module, buffer, len(buffer)):
        raise ctypes.WinError(ctypes.get_last_error())
    loaded.append(Path(buffer.value).resolve())
private = [path for path in loaded if path.is_relative_to(root)]
for name in ("python313.dll", "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll"):
    selected = [path for path in loaded if path.name.lower() == name]
    if not selected or any(not path.is_relative_to(root) for path in selected):
        raise RuntimeError(f"A required DLL was not loaded from the private runtime: {name}: {selected}")
print(json.dumps({"passed": True, "python": sys.version, "root": str(root), "isolated": bool(sys.flags.isolated), "sysPath": sys.path,
    "versions": {name: importlib.metadata.version(name) for name in ("rembg", "onnxruntime", "numpy", "scipy", "numba", "pymatting", "scikit-image")},
    "privateNativeModules": [str(path.relative_to(root)) for path in private], "loadedModules": [str(path) for path in loaded]}, indent=2))
