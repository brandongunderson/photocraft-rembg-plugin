"""Build a private, pinned CPython environment without pip or global installation."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
CACHE = RUNTIME / "cache"
MAX_FILES = 20_000
MAX_EXPANDED = 896 << 20
MAX_MEMBER = 256 << 20
TIMESTAMP = (2026, 1, 1, 0, 0, 0)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_parts(name: str) -> tuple[str, ...]:
    if not name or "\\" in name or ":" in name or name.startswith("/"):
        raise ValueError(f"Unsafe runtime path: {name!r}")
    parts = tuple(name.split("/"))
    if any(not part or part in (".", "..") or part.endswith((".", " ")) for part in parts):
        raise ValueError(f"Unsafe runtime path: {name!r}")
    if any(not part.isascii() or len(part) > 128 for part in parts) or len(name) > 240:
        raise ValueError(f"Unsupported runtime path: {name!r}")
    return parts


def runtime_path(name: str) -> Path:
    path = RUNTIME.joinpath(*safe_parts(name))
    if not path.resolve().is_relative_to(RUNTIME.resolve()):
        raise ValueError("Runtime asset path escapes the plugin")
    for candidate in [path, *path.parents]:
        if candidate == RUNTIME:
            break
        if candidate.is_symlink():
            raise ValueError(f"Runtime assets must not be symlinks: {candidate}")
    return path


def asset_valid(path: Path, asset: dict) -> bool:
    return path.is_file() and path.stat().st_size == asset["bytes"] and sha256(path) == asset["sha256"]


def fetch(asset: dict, offline: bool) -> Path:
    path = runtime_path(asset["path"])
    if asset_valid(path, asset):
        return path
    if offline:
        raise ValueError(f"Missing or changed pinned asset: {asset['path']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    if temporary.is_symlink():
        raise ValueError("Refusing linked download staging file")
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "Photocraft-plugin-dev"})
    try:
        with urllib.request.urlopen(request, timeout=120) as source, temporary.open("wb") as output:
            remaining = asset["bytes"] + 1
            while remaining:
                block = source.read(min(1 << 20, remaining))
                if not block:
                    break
                output.write(block)
                remaining -= len(block)
        if not asset_valid(temporary, asset):
            raise ValueError(f"Downloaded asset failed size/SHA-256 verification: {asset['path']}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def wheel_destination(name: str) -> str:
    parts = safe_parts(name)
    if parts[0].endswith(".data"):
        if len(parts) < 3:
            raise ValueError(f"Invalid wheel data layout: {name}")
        prefixes = {"purelib": "Lib/site-packages", "platlib": "Lib/site-packages", "scripts": "Scripts", "headers": "Include", "data": ""}
        if parts[1] not in prefixes:
            raise ValueError(f"Unknown wheel data directory: {name}")
        return "/".join(part for part in (prefixes[parts[1]], *parts[2:]) if part)
    return "Lib/site-packages/" + name


def extract(archive_path: Path, destination: Path, seen: dict[str, int], wheel: bool = False) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            if entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Encrypted or linked runtime members are unsupported")
            name = wheel_destination(entry.filename) if wheel else entry.filename
            parts = safe_parts(name)
            key = name.casefold()
            if key in seen or entry.file_size > MAX_MEMBER:
                raise ValueError(f"Duplicate or oversized runtime member: {name}")
            if sum(seen.values()) + entry.file_size > MAX_EXPANDED:
                raise ValueError("Runtime expanded-byte limit exceeded")
            if len(seen) >= MAX_FILES:
                raise ValueError("Runtime file-count limit exceeded")
            seen[key] = entry.file_size
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("xb") as output:
                count = 0
                while block := source.read(1 << 20):
                    count += len(block)
                    if count > entry.file_size or count > MAX_MEMBER:
                        raise ValueError("Runtime member exceeds its declared size")
                    output.write(block)
            if count != entry.file_size:
                raise ValueError("Truncated runtime member")


def runtime_files(environment: Path) -> list[Path]:
    files = sorted((path for path in environment.rglob("*") if path.is_file()), key=lambda path: path.relative_to(environment).as_posix())
    if len(files) > MAX_FILES or sum(path.stat().st_size for path in files) > MAX_EXPANDED:
        raise ValueError("Private runtime exceeds its worker extraction bounds")
    for path in files:
        if path.is_symlink() or path.stat().st_size > MAX_MEMBER:
            raise ValueError(f"Invalid private runtime file: {path}")
        safe_parts(path.relative_to(environment).as_posix())
    return files


def archive_runtime(environment: Path, destination: Path) -> tuple[int, int]:
    files = runtime_files(environment)
    temporary = destination.with_name(destination.name + ".part")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                info = zipfile.ZipInfo(path.relative_to(environment).as_posix(), TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                with path.open("rb") as source, archive.open(info, "w") as output:
                    shutil.copyfileobj(source, output, 1 << 20)
        if temporary.stat().st_size > MAX_MEMBER:
            raise ValueError("Private runtime ZIP exceeds the host's 256 MiB member bound")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return len(files), sum(path.stat().st_size for path in files)


def collect_licenses(wheels: list[dict], supplements: list[dict] | None = None) -> None:
    packages = []
    for wheel in wheels:
        records = []
        with zipfile.ZipFile(runtime_path(wheel["path"])) as archive:
            selected = sorted((entry for entry in archive.infolist() if not entry.is_dir() and any(word in PurePosixPath(entry.filename).name.upper() for word in ("LICENSE", "LICENCE", "COPYING", "NOTICE", "COPYRIGHT"))), key=lambda entry: entry.filename)
            for index, entry in enumerate(selected):
                data = archive.read(entry)
                if not data:
                    continue
                name = f"licenses/python-wheels/{wheel['name']}-{wheel['version']}/{index:03}-{PurePosixPath(entry.filename).name}"
                path = runtime_path(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                records.append({"wheelPath": entry.filename, "bundledPath": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        for supplement in supplements or []:
            if supplement.get("distribution") == wheel["name"]:
                records.append({"wheelPath": None, "bundledPath": supplement["path"], "sha256": supplement["sha256"], "bytes": supplement["bytes"], "sourceUrl": supplement["url"]})
        packages.append({**{key: wheel.get(key) for key in ("name", "version", "filename", "url", "sha256", "bytes", "licenseExpression", "license", "projectUrls")}, "bundledLicenses": records})
    write_json(RUNTIME / "python-packages.json", {"apiVersion": 1, "packages": packages})


def prepare(offline: bool) -> dict:
    assets = json.loads((RUNTIME / "assets.json").read_text(encoding="utf-8"))
    if assets.get("apiVersion") != 1 or assets.get("platform") != "windows-x86_64":
        raise ValueError("Unsupported pinned runtime manifest")
    for asset in [assets["python"], *assets["wheels"], *assets["models"], *assets["licenses"]]:
        fetch(asset, offline)
    vc = json.loads((RUNTIME / "vc-runtime.json").read_text(encoding="utf-8"))
    for asset in vc["files"]:
        if not asset_valid(runtime_path(asset["path"]), {**asset, "bytes": asset["size"]}):
            raise ValueError("Run fetch-vc-runtime.ps1 before preparing the Python runtime")
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="python-stage-", dir=CACHE) as temporary:
        environment = Path(temporary)
        seen: dict[str, int] = {}
        extract(runtime_path(assets["python"]["path"]), environment, seen)
        for wheel in assets["wheels"]:
            extract(runtime_path(wheel["path"]), environment, seen, wheel=True)
        for asset in vc["files"]:
            if asset["path"].startswith("bin/"):
                target = environment / Path(asset["path"]).name
                if target.exists() and sha256(target) != asset["sha256"]:
                    raise ValueError("Pinned VC DLL conflicts with the official Python embed; update the complete VC pin")
                shutil.copyfile(runtime_path(asset["path"]), target)
        (environment / "python313._pth").write_bytes(b"python313.zip\n.\nLib/site-packages\nimport site\n")
        shutil.copyfile(environment / "LICENSE.txt", RUNTIME / "licenses/Python-LICENSE.txt")
        count, expanded = archive_runtime(environment, RUNTIME / "python-runtime.zip")
        retained = CACHE / "python-runtime"
        if retained.exists():
            resolved = retained.resolve()
            if retained.is_symlink() or resolved.parent != CACHE.resolve():
                raise ValueError("Refusing to replace an unexpected runtime cache directory")
            shutil.rmtree(resolved)
        shutil.copytree(environment, retained)
    collect_licenses(assets["wheels"], assets["licenses"])
    models = [{"id": asset["id"], "file": asset["path"], "sha256": asset["sha256"], "bytes": asset["bytes"]} for asset in assets["models"]]
    write_json(RUNTIME / "models.json", {"apiVersion": 1, "models": models})
    result = {"apiVersion": 1, "archive": "python-runtime.zip", "sha256": sha256(RUNTIME / "python-runtime.zip"), "expandedBytes": expanded, "fileCount": count, "python": "python.exe"}
    write_json(RUNTIME / "runtime.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Only accept already-cached exact pinned assets")
    arguments = parser.parse_args()
    try:
        print(json.dumps(prepare(arguments.offline), indent=2))
    except (OSError, ValueError, zipfile.BadZipFile) as cause:
        parser.exit(1, f"Runtime preparation failed: {cause}\n")
