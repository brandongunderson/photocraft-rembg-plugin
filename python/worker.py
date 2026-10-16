"""Local rembg library worker. The native supervisor owns its lifetime and private runtime."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import zlib

_manager_spec = importlib.util.spec_from_file_location("photocraft_rembg_models", Path(__file__).with_name("model_manager.py"))
if _manager_spec is None or _manager_spec.loader is None:
    raise RuntimeError("The bundled model manager is missing. Reinstall the plugin.")
model_manager = importlib.util.module_from_spec(_manager_spec)
_manager_spec.loader.exec_module(model_manager)
MODELS = tuple(model_manager.REGISTRY)
MAX_PIXELS = 32_000_000
MAX_MATTING_PIXELS = 4_000_000
DEFAULTS = dict(model=MODELS[0], output="foreground", alpha_matting=False,
                foreground_threshold=240, background_threshold=10, erode_size=10,
                post_process_mask=False)


def progress(percent, message):
    print(json.dumps(dict(progress=percent, message=message)), file=sys.stderr, flush=True)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def bounded_json(path, limit=16_384):
    with Path(path).open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("JSON request or metadata exceeds its size limit.")
    return json.loads(data, object_pairs_hook=unique_object)


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def validate_dimensions(width, height, matting=False):
    if not integer(width, 1, 32768) or not integer(height, 1, 32768) or width * height > MAX_PIXELS:
        raise ValueError("Rembg supports images up to 32 megapixels and 32,768 pixels per side.")
    if matting and width * height > MAX_MATTING_PIXELS:
        raise ValueError("Alpha matting supports images up to 4 megapixels. Disable alpha matting or use a smaller image.")


def load_job(path):
    job = bounded_json(path)
    required = {"apiVersion", "input", "output", "options", "outputSize", "colorSpace"}
    if type(job) is not dict or set(job) != required or type(job["apiVersion"]) is not int or job["apiVersion"] != 1 or job["colorSpace"] != "srgb":
        raise ValueError("Unsupported image worker protocol.")
    for key in ("input", "output"):
        if not isinstance(job[key], str) or not Path(job[key]).is_absolute():
            raise ValueError("Image paths must be absolute.")
    if os.path.normcase(os.path.abspath(job["input"])) == os.path.normcase(os.path.abspath(job["output"])) or os.path.lexists(job["output"]):
        raise ValueError("Image paths must differ and output must not exist.")
    supplied = job["options"]
    if type(supplied) is not dict or not set(supplied).issubset(DEFAULTS):
        raise ValueError("Unknown rembg option.")
    options = DEFAULTS | supplied
    if options["model"] not in MODELS or options["output"] not in ("foreground", "background", "mask"):
        raise ValueError("Unknown model or output mode.")
    if any(type(options[key]) is not bool for key in ("alpha_matting", "post_process_mask")):
        raise ValueError("Matting and mask processing must be boolean.")
    if not integer(options["foreground_threshold"], 0, 255) or not integer(options["background_threshold"], 0, 255) or options["background_threshold"] >= options["foreground_threshold"] or not integer(options["erode_size"], 0, 50):
        raise ValueError("Invalid alpha-matting thresholds or erosion size.")
    size = job["outputSize"]
    if type(size) is not dict or set(size) != {"width", "height"}:
        raise ValueError("outputSize must contain width and height.")
    validate_dimensions(size["width"], size["height"], options["alpha_matting"])
    job["options"] = options
    return job


def validate_png(path, expected):
    with Path(path).open("rb") as source:
        header = source.read(33)
    if len(header) != 33 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[8:16] != b"\0\0\0\rIHDR" or header[24:28] != b"\x08\x06\0\0" or header[28] not in (0, 1) or zlib.crc32(header[12:29]) != struct.unpack(">I", header[29:33])[0]:
        raise ValueError("The plugin requires a valid 8-bit RGBA sRGB PNG input.")
    dimensions = struct.unpack(">II", header[16:24])
    validate_dimensions(*dimensions)
    if dimensions != (expected["width"], expected["height"]):
        raise ValueError("Rembg keeps the original image dimensions.")


def verified_model(root, model, cache):
    row = model_manager.load_catalog(root).get(model)
    if row is None:
        raise ValueError("This model is unavailable in this plugin version.")
    return model_manager.resolve_model(root, cache, row)


def local_session(model, path):
    # Reuse rembg's actual model sessions. Override only its downloader, so no
    # missing-file fallback can fetch a model or inspect a user's model cache.
    import onnxruntime as ort
    import pooch

    def reject_download(*args, **kwargs):
        raise RuntimeError("This plugin is offline; automatic downloads are disabled.")
    pooch.retrieve = reject_download
    module, class_name = model_manager.REGISTRY[model]
    base = getattr(importlib.import_module(f"rembg.sessions.{module}"), class_name)

    class BundledSession(base):
        @classmethod
        def download_models(cls, *args, **kwargs):
            return str(path)

    settings = ort.SessionOptions()
    settings.intra_op_num_threads = min(4, os.cpu_count() or 1)
    settings.inter_op_num_threads = 1
    settings.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    settings.log_severity_level = 3
    return BundledSession(model, settings, providers=["CPUExecutionProvider"])


def compose(source, cutout, mode, matting):
    from PIL import Image, ImageChops
    if cutout.mode != "RGBA" or cutout.size != source.size:
        raise ValueError("The model returned an incompatible image.")
    predicted = cutout.getchannel("A")
    original_alpha = source.getchannel("A")
    foreground_alpha = ImageChops.multiply(predicted, original_alpha)
    if mode == "mask":
        return Image.merge("RGBA", (foreground_alpha, foreground_alpha, foreground_alpha, Image.new("L", source.size, 255)))
    rgb = cutout.convert("RGB") if matting and mode == "foreground" else source.convert("RGB")
    result = rgb.convert("RGBA")
    result.putalpha(ImageChops.multiply(ImageChops.invert(predicted), original_alpha) if mode == "background" else foreground_alpha)
    return result


def save_result(result, output, pending=None):
    from PIL import ImageCms
    output = Path(output)
    if pending is None:
        fd, temporary = tempfile.mkstemp(prefix=".rembg-", suffix=".png", dir=output.parent)
        os.close(fd)
        pending = Path(temporary)
        pending.unlink()
    else:
        pending = Path(pending)
    if pending.parent.resolve() != output.parent.resolve() or pending == output:
        raise ValueError("Invalid private output staging path.")
    created = False
    try:
        with pending.open("xb") as stream:
            created = True
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            result.save(stream, format="PNG", icc_profile=profile)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows rename fails if destination exists. POSIX link has the same
        # no-overwrite publication rule; both stay on the output filesystem.
        if os.name == "nt":
            os.rename(pending, output)
        else:
            os.link(pending, output)
    finally:
        if created:
            pending.unlink(missing_ok=True)


def run(job_path, root, cache):
    job = load_job(job_path)
    validate_png(job["input"], job["outputSize"])
    # A per-model OS lock keeps download/remove operations from changing the
    # verified weights while ONNX loads or uses them. Other models stay usable.
    with model_manager.model_lock(cache, job["options"]["model"]):
        progress(20, "Checking the selected local model…")
        model = verified_model(root, job["options"]["model"], cache)
        process(job, model)


def process(job, model):
    if importlib.metadata.version("rembg") != "2.0.85":
        raise ValueError("The bundled rembg version is incompatible. Reinstall the plugin.")
    options = job["options"]
    # rembg eagerly imports PyMatting's explicitly typed Numba functions, even
    # for a plain ONNX cutout. Skip that unused compilation for non-matting jobs.
    # Matting retains JIT in this job's private cache and never uses Python loops.
    os.environ["NUMBA_DISABLE_JIT"] = "0" if options["alpha_matting"] else "1"
    progress(25, "Preparing local image libraries…")
    from PIL import Image
    from rembg import remove
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(job["input"]) as opened:
        if opened.mode != "RGBA" or getattr(opened, "n_frames", 1) != 1:
            raise ValueError("The input must be a single RGBA PNG image.")
        source = opened.copy()
    progress(30, "Loading local AI model…")
    session = local_session(options["model"], model)
    progress(45, "Removing background and refining edges…")
    # RGB input keeps rembg from consuming source alpha twice. Preserve and
    # multiply the original alpha exactly once when composing every mode.
    cutout = remove(source.convert("RGB"), session=session,
                    alpha_matting=options["alpha_matting"],
                    alpha_matting_foreground_threshold=options["foreground_threshold"],
                    alpha_matting_background_threshold=options["background_threshold"],
                    alpha_matting_erode_size=options["erode_size"],
                    post_process_mask=options["post_process_mask"],
                    decontaminate=False)
    progress(90, "Preserving transparency…")
    result = compose(source, cutout, options["output"], options["alpha_matting"])
    progress(95, "Writing result…")
    save_result(result, job["output"], os.environ.get("PHOTOCRAFT_REMBG_PENDING"))
    progress(99, "Result prepared.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.job, Path(__file__).resolve().parents[1], args.cache)
    except Exception as exc:
        print(json.dumps(dict(error=str(exc)[:2048])), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
