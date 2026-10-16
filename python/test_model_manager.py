"""Model maintenance tests use synthetic bytes; they never access the network."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

MODULE = Path(__file__).with_name("model_manager.py").resolve()
spec = importlib.util.spec_from_file_location("rembg_model_manager_test", MODULE)
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.status = 200
        self.headers = {} if headers is None else headers

    def geturl(self):
        return "https://release-assets.githubusercontent.com/github-production-release-asset/model.onnx?token=test"


class Opener:
    def __init__(self, data, headers=None, fail=None):
        self.data, self.headers, self.fail = data, headers, fail
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        if timeout != 60:
            raise AssertionError("A finite socket timeout is required")
        if self.fail:
            raise self.fail
        return Response(self.data, self.headers)


class ModelManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.scratch = self.cache / ".download-fixture"
        self.scratch.mkdir()
        self.payload = b"pinned synthetic ONNX bytes"
        self.catalog = json.loads((MODULE.parents[1] / "runtime/model-catalog.json").read_text(encoding="utf-8"))
        self.row = next(row for row in self.catalog["models"] if row["id"] == "silueta").copy()
        self.row.update(bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())
        (self.root / "runtime").mkdir()

    def write_catalog(self, changed=None):
        catalog = self.catalog if changed is None else changed
        (self.root / "runtime/model-catalog.json").write_text(json.dumps(catalog), encoding="utf-8")

    def test_catalog_pins_only_supported_sessions_and_official_https_assets(self):
        self.write_catalog()
        catalog = manager.load_catalog(self.root)
        self.assertEqual(len(catalog), 13)
        self.assertEqual(sum(row["bundled"] for row in catalog.values()), 2)
        for key, value in [("id", "../u2net"), ("sessionModule", "os"), ("bytes", (1 << 30) + 1), ("bytes", True), ("sha256", "f" * 63), ("url", "http://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"), ("url", "https://github.com/other/release/model.onnx"), ("bundled", False)]:
            changed = json.loads(json.dumps(self.catalog))
            changed["models"][0][key] = value
            self.write_catalog(changed)
            with self.assertRaises(ValueError, msg=(key, value)):
                manager.load_catalog(self.root)

    def test_redirects_reject_downgrades_credentials_and_foreign_hosts(self):
        handler = manager.SafeRedirect()
        request = urllib.request.Request(self.row["url"])
        for url in ["http://release-assets.githubusercontent.com/a", "https://github.com.evil.test/a", "https://github.com@evil.test/a", "https://user:pass@github.com/a", "https://github.com:444/a", "file:///tmp/model.onnx"]:
            with self.assertRaises(ValueError, msg=url):
                handler.redirect_request(request, None, 302, "Found", {}, url)
        self.assertIsNotNone(handler.redirect_request(request, None, 302, "Found", {}, "https://release-assets.githubusercontent.com/a?sig=123"))

    def test_download_is_explicit_atomic_verified_and_idempotent(self):
        opener = Opener(self.payload, {"Content-Length": str(len(self.payload))})
        self.assertEqual(manager.model_status(self.root, self.cache, self.row)["data"]["state"], "missing")
        with manager.model_lock(self.cache, self.row["id"]):
            manager.download(self.root, self.cache, self.scratch, self.row, opener)
        target = self.cache / "silueta.onnx"
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertFalse((self.scratch / "model.part").exists())
        self.assertEqual(manager.resolve_model(self.root, self.cache, self.row), target)
        status = manager.model_status(self.root, self.cache, self.row)
        self.assertEqual(status["data"]["state"], "downloaded")
        self.assertTrue(status["data"]["canRemove"])
        self.assertIn(self.row["description"], status["message"])
        manager.download(self.root, self.cache, self.scratch, self.row, opener)
        self.assertEqual(opener.calls, 1)

    def test_bad_downloads_preserve_existing_copy_and_remove_staged_bytes(self):
        target = self.cache / "silueta.onnx"
        target.write_bytes(b"old damaged weights")
        for opener in [Opener(self.payload + b"extra"), Opener(self.payload[:-1]), Opener(b"x" * len(self.payload)), Opener(self.payload, {"Content-Length": "999"}), Opener(self.payload, {"Content-Encoding": "gzip"}), Opener(b"", fail=urllib.error.URLError("offline"))]:
            with self.assertRaises(ValueError):
                manager.download(self.root, self.cache, self.scratch, self.row, opener)
            self.assertEqual(target.read_bytes(), b"old damaged weights")
            self.assertFalse((self.scratch / "model.part").exists())
        status = manager.model_status(self.root, self.cache, self.row)
        self.assertEqual(status["data"]["state"], "corrupt")
        with self.assertRaisesRegex(ValueError, "Download selected model"):
            manager.resolve_model(self.root, self.cache, self.row)

    def test_pinned_size_not_content_length_bounds_the_stream(self):
        with patch.object(manager, "MAX_DOWNLOAD_SECONDS", -1):
            with self.assertRaisesRegex(ValueError, "size or time"):
                manager.download(self.root, self.cache, self.scratch, self.row, Opener(self.payload))
        with patch.object(manager.shutil, "disk_usage", return_value=types.SimpleNamespace(free=1)):
            opener = Opener(self.payload)
            with self.assertRaisesRegex(ValueError, "free disk space"):
                manager.download(self.root, self.cache, self.scratch, self.row, opener)
            self.assertEqual(opener.calls, 0)

    def test_task_protocol_remove_and_atomic_result(self):
        catalog = json.loads(json.dumps(self.catalog))
        catalog["models"] = [self.row if row["id"] == self.row["id"] else row for row in catalog["models"]]
        self.write_catalog(catalog)
        output = self.root / "result.json"
        pending = self.root / "result.pending"
        task = dict(apiVersion=1, options=dict(action="remove", model="silueta"), output=str(output))
        request = self.root / "task.json"
        request.write_text(json.dumps(task), encoding="utf-8")
        target = self.cache / "silueta.onnx"
        target.write_bytes(self.payload)
        with patch.dict(os.environ, {"PHOTOCRAFT_REMBG_PENDING": str(pending)}):
            manager.run(request, self.root, self.cache, self.scratch)
        self.assertFalse(target.exists())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["data"]["state"], "missing")
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            manager.save_result(output, dict(apiVersion=1, message="new", data={}), pending)
        self.assertEqual(output.read_bytes(), original)
        self.assertFalse(pending.exists())
        output.unlink()
        task["options"]["model"] = "u2netp"
        request.write_text(json.dumps(task), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "cannot be removed"):
            manager.run(request, self.root, self.cache, self.scratch)
        for changed in [task | {"apiVersion": True}, task | {"unknown": 1}, task | {"output": "relative.json"}, task | {"options": dict(action="execute", model="u2netp")}, task | {"options": dict(action="status", model="../model")}]:
            request.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                manager.load_task(request)

    def test_cache_refuses_links_and_unsafe_staging(self):
        outside = self.root / "outside.onnx"
        outside.write_bytes(self.payload)
        linked = self.cache / "silueta.onnx"
        os.link(outside, linked)
        with self.assertRaisesRegex(ValueError, "without links"):
            manager.resolve_model(self.root, self.cache, self.row)
        self.assertEqual(outside.read_bytes(), self.payload)
        linked.unlink()
        with self.assertRaisesRegex(ValueError, "staging directory"):
            manager.download(self.root, self.cache, self.root, self.row, Opener(self.payload))
        self.assertTrue(manager.unsafe_metadata(types.SimpleNamespace(st_mode=0o040700, st_file_attributes=0x400)))
        try:
            (self.root / "linked-dir").symlink_to(self.cache, target_is_directory=True)
        except OSError:
            pass  # Windows can require an unavailable symbolic-link privilege.
        else:
            with self.assertRaisesRegex(ValueError, "reparse points"):
                manager.secure_directory(self.root / "linked-dir")

    def test_os_lock_blocks_concurrent_mutation_and_recovers_after_process_death(self):
        code = "import importlib.util, pathlib, sys; spec=importlib.util.spec_from_file_location('models',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); ctx=m.model_lock(pathlib.Path(sys.argv[2]),'silueta'); ctx.__enter__(); print('locked',flush=True); sys.stdin.read()"
        child = subprocess.Popen([sys.executable, "-I", "-B", "-c", code, str(MODULE), str(self.cache)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "locked")
            with self.assertRaisesRegex(ValueError, "busy"):
                with manager.model_lock(self.cache, "silueta", timeout=0.1):
                    self.fail("The concurrent lock unexpectedly succeeded")
            with manager.model_lock(self.cache, "u2netp", timeout=0.1):
                pass  # Different models are independent.
        finally:
            child.kill()
            child.communicate(timeout=5)
        with manager.model_lock(self.cache, "silueta", timeout=0.1):
            pass
        self.assertEqual((self.cache / ".silueta.lock").stat().st_size, 1)


if __name__ == "__main__":
    unittest.main()
