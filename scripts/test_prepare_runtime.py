"""Synthetic packaging regressions; never download assets or execute a worker."""
import importlib.util
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("prepare_runtime", Path(__file__).with_name("prepare-runtime.py"))
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimePackagingTests(unittest.TestCase):
    def test_paths_cannot_escape_or_alias_host_drives(self):
        for name in ("", "../escape", "a/../b", "/absolute", "C:/drive", "a\\b", "a//b", "a./file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runtime.safe_parts(name)

    def test_wheel_data_layout_maps_explicit_install_schemes(self):
        self.assertEqual(runtime.wheel_destination("example/mod.py"), "Lib/site-packages/example/mod.py")
        self.assertEqual(runtime.wheel_destination("x.data/purelib/example.py"), "Lib/site-packages/example.py")
        self.assertEqual(runtime.wheel_destination("x.data/scripts/tool"), "Scripts/tool")
        with self.assertRaises(ValueError):
            runtime.wheel_destination("x.data/unknown/file")

    def test_empty_markers_preserve_bytes_and_duplicate_members_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "wheel.zip"
            output = root / "output"
            output.mkdir()
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr("example/__init__.py", b"")
                writer.writestr("example/main.py", b"VALUE = 1\n")
            seen = {}
            runtime.extract(archive, output, seen, wheel=True)
            self.assertEqual((output / "Lib/site-packages/example/__init__.py").read_bytes(), b"")
            with self.assertRaises(ValueError):
                runtime.extract(archive, output, seen, wheel=True)

    def test_symlink_members_and_expansion_overflow_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "linked.zip"
            info = zipfile.ZipInfo("linked")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr(info, b"outside")
            with self.assertRaises(ValueError):
                runtime.extract(archive, root, {})
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr("file.py", b"print(1)\n")
            with self.assertRaises(ValueError):
                runtime.extract(archive, root, {"previous": runtime.MAX_EXPANDED})

    def test_runtime_zip_is_reproducible_and_has_only_regular_file_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "env"
            environment.mkdir()
            (environment / "empty.py").write_bytes(b"")
            (environment / "data.bin").write_bytes(b"test data" * 100)
            first, second = root / "first.zip", root / "second.zip"
            self.assertEqual(runtime.archive_runtime(environment, first), runtime.archive_runtime(environment, second))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                self.assertTrue(all(not item.is_dir() and stat.S_ISREG(item.external_attr >> 16) for item in archive.infolist()))
                self.assertTrue(all(item.date_time == runtime.TIMESTAMP for item in archive.infolist()))


if __name__ == "__main__":
    unittest.main()
