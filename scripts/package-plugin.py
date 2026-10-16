#!/usr/bin/env python3
"""Create a deterministic PhotoCraft package-v2 ZIP from a prepared directory.

Python 3.11+ standard library only. This performs structural checks, never executes
or imports plugin code. PhotoCraft remains the authority for ABI and grant checks.
"""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

MAX_FILE = 256 << 20
MAX_TOTAL = 1024 << 20
MAX_ARCHIVE = 512 << 20
MAX_FILES = 512
MAX_MODULE = 8 << 20
MAX_FILTER = 32 << 20
PLATFORMS = {f"{system}-{arch}" for system in ("windows", "linux", "macos") for arch in ("x86_64", "aarch64")}
RESERVED = {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"} | {f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)}


def safe_path(name):
    if not isinstance(name, str) or not 1 <= len(name.encode("utf-8")) <= 240 or not re.fullmatch(r"[A-Za-z0-9._/-]+", name):
        raise ValueError(f"Unsafe archive path: {name!r}")
    components = name.split("/")
    for component in components:
        if not component or component in (".", "..") or len(component) > 128 or component.endswith((".", " ")):
            raise ValueError(f"Unsafe archive component: {name!r}")
        if component.split(".", 1)[0].upper() in RESERVED:
            raise ValueError(f"Reserved archive name: {name!r}")
    if name == ".photocraft-install.json":
        raise ValueError("The installation marker belongs to PhotoCraft.")
    return name


def exact_keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError(f"Expected required keys {sorted(required)} and optional keys {sorted(optional)}.")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def metadata(files):
    if "package.json" not in files:
        raise ValueError("Missing package.json at the archive root.")
    if files["package.json"].stat().st_size > 64 * 1024:
        raise ValueError("package.json exceeds 64 KiB.")
    value = json.loads(files["package.json"].read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    exact_keys(value, {"packageVersion", "module"}, {"native", "filters"})
    if type(value["packageVersion"]) is not int or value["packageVersion"] != 2 or value["module"] != "plugin.pcext":
        raise ValueError("This helper accepts packageVersion 2 with module plugin.pcext.")
    modules = ["plugin.pcext"]
    entries = set()
    native = value.get("native")
    if native is not None:
        exact_keys(native, {"service", "platform", "entry"})
        if native["service"] != "plugin.processImage" or native["platform"] not in PLATFORMS:
            raise ValueError("Native service/platform is unsupported by package version 2.")
        entry = safe_path(native["entry"])
        if native["platform"].startswith("windows-") and not entry.lower().endswith(".exe"):
            raise ValueError("Windows native entries must end in .exe.")
        if entry in {"package.json", "plugin.pcext", "LICENSE", "THIRD-PARTY-NOTICES.md"}:
            raise ValueError("The native entry conflicts with package metadata.")
        entries.add(entry)
    filters = value.get("filters", [])
    if not isinstance(filters, list) or len(filters) > 16:
        raise ValueError("filters must be an array containing at most 16 modules.")
    for entry in filters:
        exact_keys(entry, {"module"})
        module = safe_path(entry["module"])
        if not module.endswith(".wasm"):
            raise ValueError("Filter modules must be safe relative .wasm paths.")
        if module in entries or module in modules:
            raise ValueError("Backend module paths must be unique.")
        modules.append(module)
        entries.add(module)
    required = {"LICENSE", "THIRD-PARTY-NOTICES.md", *modules, *entries}
    missing = required - files.keys()
    if missing:
        raise ValueError(f"Missing required package files: {sorted(missing)}")
    for name in required:
        if files[name].stat().st_size == 0:
            raise ValueError(f"Required file is empty: {name}")
    for name in modules:
        path = files[name]
        with path.open("rb") as stream:
            if stream.read(8) != b"\0asm\x01\0\0\0":
                raise ValueError(f"Not a core WebAssembly v1 module: {name}")
        limit = MAX_MODULE if name == "plugin.pcext" else MAX_FILTER
        if path.stat().st_size > limit:
            raise ValueError(f"WASM module exceeds its {limit >> 20} MiB limit: {name}")
    # Embedded identities and imports require actual WASM inspection in PhotoCraft.
    return value


def collect(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Package root must be a real directory.")
    files, folded = {}, set()
    total = 0
    def failed_walk(error):
        raise error

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=failed_walk):
        for name in dirs:
            path = Path(directory, name)
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError(f"Filesystem links are not package sources: {path}")
        for name in names:
            path = Path(directory, name)
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink():
                raise ValueError(f"Only regular files can be packaged: {path}")
            archive_name = safe_path(path.relative_to(root).as_posix())
            alias = archive_name.lower()
            if alias in folded:
                raise ValueError(f"Duplicate or case-aliased archive path: {archive_name}")
            folded.add(alias)
            files[archive_name] = path
            total += info.st_size
            if info.st_size > MAX_FILE or total > MAX_TOTAL or len(files) > MAX_FILES:
                raise ValueError("Package exceeds the file, expanded-size or member-count limit.")
    for name in files:
        components = name.split("/")
        if any("/".join(components[:index]).lower() in folded for index in range(1, len(components))):
            raise ValueError(f"An archive file is also a parent path: {name}")
    return files


def package(root, output):
    root = Path(root)
    if root.is_symlink() or getattr(root, "is_junction", lambda: False)():
        raise ValueError("Package root cannot be a filesystem link.")
    root, output = root.resolve(), Path(output).resolve()
    if output == root or root in output.parents:
        raise ValueError("Write the archive outside its prepared source directory.")
    files = collect(root)
    value = metadata(files)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=False) as archive:
            for name, path in sorted(files.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                executable = bool(value.get("native") and name == value["native"]["entry"])
                info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                with path.open("rb") as source, archive.open(info, "w", force_zip64=False) as target:
                    copied = 0
                    while data := source.read(1024 * 1024):
                        copied += len(data)
                        if copied > MAX_FILE:
                            raise ValueError(f"Source changed or exceeds the file limit: {name}")
                        target.write(data)
                    if copied != path.stat().st_size:
                        raise ValueError(f"Source changed while packaging: {name}")
        if temporary.stat().st_size > MAX_ARCHIVE:
            raise ValueError("Compressed package exceeds 512 MiB.")
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("Archive CRC verification failed.")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Prepared package directory, including package.json")
    parser.add_argument("--output", type=Path, required=True, help="Destination .pcplugin outside --root")
    args = parser.parse_args()
    try:
        result = package(args.root, args.output)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Package failed: {error}\n")
    print(f"Built {result} ({result.stat().st_size:,} bytes). Review and install it in PhotoCraft.")


if __name__ == "__main__":
    main()
