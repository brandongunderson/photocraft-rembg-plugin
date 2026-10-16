"""Explicit, pinned model downloads and private model-cache maintenance.

This module intentionally uses only Python's standard library. Inference never
calls download(); the user must request it through the plugin's model controls.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_MODEL_BYTES = 1 << 30
MAX_RESULT_BYTES = 128 << 10
MAX_DOWNLOAD_SECONDS = 30 * 60
REGISTRY = {
    "birefnet-general-lite": ("birefnet_general_lite", "BiRefNetSessionGeneralLite"),
    "u2netp": ("u2netp", "U2netpSession"),
    "u2net": ("u2net", "U2netSession"),
    "u2net_human_seg": ("u2net_human_seg", "U2netHumanSegSession"),
    "silueta": ("silueta", "SiluetaSession"),
    "isnet-general-use": ("dis_general_use", "DisSession"),
    "isnet-anime": ("dis_anime", "DisSession"),
    "birefnet-general": ("birefnet_general", "BiRefNetSessionGeneral"),
    "birefnet-portrait": ("birefnet_portrait", "BiRefNetSessionPortrait"),
    "birefnet-dis": ("birefnet_dis", "BiRefNetSessionDIS"),
    "birefnet-hrsod": ("birefnet_hrsod", "BiRefNetSessionHRSOD"),
    "birefnet-cod": ("birefnet_cod", "BiRefNetSessionCOD"),
    "birefnet-massive": ("birefnet_massive", "BiRefNetSessionMassive"),
}
BUILTIN_MODELS = {"birefnet-general-lite", "u2netp"}
ALLOWED_DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def progress(percent, message):
    print(json.dumps(dict(progress=percent, message=message)), file=sys.stderr, flush=True)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def bounded_json(path, limit=65536):
    with Path(path).open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Model metadata or task exceeds its size limit.")
    return json.loads(data, object_pairs_hook=unique_object)


def allowed_url(url, initial=False):
    if not isinstance(url, str) or len(url) > 8192:
        raise ValueError("Invalid model download URL.")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443):
        raise ValueError("Model downloads require an approved HTTPS source.")
    if initial and (parsed.hostname != "github.com" or parsed.query or not re.fullmatch(r"/danielgatis/rembg/releases/download/v0\.0\.0/[A-Za-z0-9_.-]+\.onnx", parsed.path)):
        raise ValueError("The model source is not a pinned rembg release asset.")
    return url


def load_catalog(root):
    catalog = bounded_json(Path(root) / "runtime/model-catalog.json")
    if type(catalog) is not dict or type(catalog.get("apiVersion")) is not int or catalog["apiVersion"] != 1 or type(catalog.get("models")) is not list or not 1 <= len(catalog["models"]) <= len(REGISTRY):
        raise ValueError("Invalid bundled model catalog. Reinstall the plugin.")
    result = {}
    for row in catalog["models"]:
        if type(row) is not dict or not isinstance(row.get("id"), str) or row["id"] not in REGISTRY or row["id"] in result:
            raise ValueError("Unknown or duplicate model in the catalog.")
        model = row["id"]
        if (row.get("sessionModule"), row.get("sessionClass")) != REGISTRY[model]:
            raise ValueError("The model session is incompatible with this plugin.")
        if type(row.get("bytes")) is not int or not 1 <= row["bytes"] <= MAX_MODEL_BYTES or not isinstance(row.get("sha256"), str) or not re.fullmatch("[0-9a-f]{64}", row["sha256"]):
            raise ValueError("Invalid model size or checksum in the catalog.")
        if type(row.get("bundled")) is not bool or row["bundled"] != (model in BUILTIN_MODELS):
            raise ValueError("Invalid bundled-model catalog entry.")
        if not isinstance(row.get("description"), str) or not 1 <= len(row["description"]) <= 1000 or not isinstance(row.get("license"), str) or not 1 <= len(row["license"]) <= 200:
            raise ValueError("Missing model description or license.")
        if "label" in row and (not isinstance(row["label"], str) or not 1 <= len(row["label"]) <= 100):
            raise ValueError("Invalid model label in the catalog.")
        allowed_url(row.get("url"), initial=True)
        result[model] = row
    if not BUILTIN_MODELS.issubset(result):
        raise ValueError("The catalog is missing an included model.")
    return result


def unsafe_metadata(metadata):
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def secure_directory(path, create=False):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("The plugin model-cache path must be absolute.")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                raise ValueError("The plugin model-cache directory is missing.") from None
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            metadata = current.lstat()
        if unsafe_metadata(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("Model-cache directories cannot use links or reparse points.")
    return path


def regular_file(path, allow_missing=False):
    path = Path(path)
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if allow_missing:
            return None
        raise
    if unsafe_metadata(metadata) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError("Model-cache files must be ordinary files, without links.")
    return metadata


def checked_file(path, flags, mode=0o600):
    path = Path(path)
    regular_file(path, allow_missing=True)
    descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), mode)
    try:
        metadata = os.fstat(descriptor)
        after = regular_file(path)
        if metadata.st_nlink != 1 or not stat.S_ISREG(metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError("The model-cache file changed while opening it.")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def model_lock(cache, model, timeout=5.0):
    if model not in REGISTRY:
        raise ValueError("Unknown rembg model.")
    cache = secure_directory(cache, create=True)
    path = cache / f".{model}.lock"
    descriptor = checked_file(path, os.O_RDWR | os.O_CREAT)
    locked = False
    try:
        if os.fstat(descriptor).st_size > 1:
            raise ValueError("The model-cache lock file is damaged.")
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
        start = time.monotonic()
        while not locked:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError:
                if time.monotonic() - start >= timeout:
                    raise ValueError("This model is busy in another operation. Try again when it finishes.") from None
                time.sleep(0.1)
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        # Keep this one-byte file. Deleting an advisory-lock file can split
        # waiting operations across different file identities and break locking.


def verify_file(path, row):
    metadata = regular_file(path, allow_missing=True)
    if metadata is None or metadata.st_size != row["bytes"]:
        return False
    digest = hashlib.sha256()
    descriptor = checked_file(path, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as source:
        total = 0
        while chunk := source.read(256 << 10):
            total += len(chunk)
            if total > row["bytes"]:
                return False
            digest.update(chunk)
    return total == row["bytes"] and digest.hexdigest() == row["sha256"]


def model_path(root, cache, row):
    if row["bundled"]:
        return Path(root) / "runtime/models" / f"{row['id']}.onnx"
    secure_directory(cache, create=True)
    return Path(cache) / f"{row['id']}.onnx"


def resolve_model(root, cache, row):
    path = model_path(root, cache, row)
    if not verify_file(path, row):
        if row["bundled"]:
            raise ValueError("An included model is missing or damaged. Reinstall the complete plugin.")
        raise ValueError("This model is not downloaded or is damaged. Use Download selected model before generating a preview.")
    return path


def model_status(root, cache, row):
    path = model_path(root, cache, row)
    metadata = regular_file(path, allow_missing=True)
    installed = verify_file(path, row)
    state = ("bundled" if row["bundled"] else "downloaded") if installed else ("corrupt" if metadata is not None else "missing")
    data = dict(model=row["id"], state=state, installed=installed, bundled=row["bundled"], bytes=row["bytes"], downloadedBytes=0 if row["bundled"] or metadata is None else metadata.st_size, description=row["description"], license=row["license"], canRemove=not row["bundled"] and metadata is not None, canDownload=not row["bundled"])
    size = row["bytes"] / (1 << 20)
    status = {"bundled": "Included with the plugin", "downloaded": "Downloaded and ready", "missing": "Not downloaded", "corrupt": "Missing or damaged model data"}[state]
    message = f"{row.get('label', row['id'])}: {status}.\n{row['description']}\nModel size: {size:.1f} MiB. License: {row['license']}."
    if state == "corrupt":
        message += "\nReinstall the plugin to repair this included model." if row["bundled"] else "\nDownload this model again to repair it."
    return dict(apiVersion=1, message=message, data=data)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        allowed_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download(root, cache, scratch, row, opener=None):
    path = model_path(root, cache, row)
    if row["bundled"]:
        resolve_model(root, cache, row)
        return
    if verify_file(path, row):
        progress(99, "This model is already downloaded and verified.")
        return
    scratch = secure_directory(scratch)
    if scratch.parent != Path(cache) or not scratch.name.startswith(".download-"):
        raise ValueError("Invalid private model-download staging directory.")
    if shutil.disk_usage(cache).free < row["bytes"] + (16 << 20):
        raise ValueError("There is not enough free disk space to download this model.")
    pending = scratch / "model.part"
    allowed_url(row["url"], initial=True)
    if opener is None:
        opener = urllib.request.build_opener(SafeRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request = urllib.request.Request(row["url"], headers={"User-Agent": "PhotoCraft-Rembg/1.1", "Accept": "application/octet-stream", "Accept-Encoding": "identity"})
    start = time.monotonic()
    last_progress = start
    digest = hashlib.sha256()
    total = 0
    progress(20, "Downloading the selected model from rembg…")
    try:
        with opener.open(request, timeout=60) as response:
            allowed_url(response.geturl())
            if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                raise ValueError("The model server returned an unsupported response.")
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isascii() or not length.isdecimal() or int(length) != row["bytes"]):
                raise ValueError("The model download size does not match the pinned release.")
            descriptor = checked_file(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            with os.fdopen(descriptor, "wb") as output:
                while chunk := response.read(256 << 10):
                    total += len(chunk)
                    if total > row["bytes"] or time.monotonic() - start > MAX_DOWNLOAD_SECONDS:
                        raise ValueError("The model download exceeded its size or time limit.")
                    output.write(chunk)
                    digest.update(chunk)
                    now = time.monotonic()
                    if now - last_progress >= 0.5:
                        progress(20 + 73 * total / row["bytes"], f"Downloading model: {total / (1 << 20):.1f} / {row['bytes'] / (1 << 20):.1f} MiB…")
                        last_progress = now
                output.flush()
                os.fsync(output.fileno())
        if total != row["bytes"] or digest.hexdigest() != row["sha256"]:
            raise ValueError("The downloaded model checksum or size does not match. No model was installed.")
        progress(95, "Verifying and installing the downloaded model…")
        secure_directory(cache)
        regular_file(path, allow_missing=True)
        os.replace(pending, path)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"The rembg model download failed (HTTP {exc.code}). Try again later.") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("The rembg model download could not complete. Check your internet connection and try again.") from exc
    finally:
        pending.unlink(missing_ok=True)


def load_task(path):
    task = bounded_json(path, 16384)
    if type(task) is not dict or set(task) != {"apiVersion", "options", "output"} or type(task["apiVersion"]) is not int or task["apiVersion"] != 1:
        raise ValueError("Unsupported model-task protocol.")
    options = task["options"]
    if type(options) is not dict or set(options) != {"action", "model"} or options["action"] not in ("status", "download", "remove") or options["model"] not in REGISTRY:
        raise ValueError("Unknown model task or model.")
    if not isinstance(task["output"], str) or not Path(task["output"]).is_absolute() or os.path.lexists(task["output"]):
        raise ValueError("The task output must be a new absolute file path.")
    return task


def save_result(output, result, pending):
    output, pending = Path(output), Path(pending)
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES or pending.parent.resolve() != output.parent.resolve() or pending == output:
        raise ValueError("Invalid model-task result or staging path.")
    created = False
    try:
        with pending.open("xb") as stream:
            created = True
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            os.rename(pending, output)
        else:
            os.link(pending, output)
    finally:
        if created:
            pending.unlink(missing_ok=True)


def run(task_path, root, cache, scratch):
    task = load_task(task_path)
    row = load_catalog(root).get(task["options"]["model"])
    if row is None:
        raise ValueError("This model is unavailable in this plugin version.")
    with model_lock(cache, row["id"]):
        action = task["options"]["action"]
        if action == "download":
            download(root, cache, scratch, row)
        elif action == "remove":
            if row["bundled"]:
                raise ValueError("Included models cannot be removed. Only downloaded models can be removed.")
            path = model_path(root, cache, row)
            if regular_file(path, allow_missing=True) is not None:
                path.unlink()
        progress(98, "Checking model availability…")
        result = model_status(root, cache, row)
    pending = os.environ.get("PHOTOCRAFT_REMBG_PENDING")
    if not pending:
        raise ValueError("The native supervisor did not supply a private result path.")
    save_result(task["output"], result, pending)
    progress(100, "Model operation complete.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.task, Path(__file__).resolve().parents[1], args.cache, args.scratch)
    except Exception as exc:
        print(json.dumps(dict(error=str(exc)[:2048])), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
