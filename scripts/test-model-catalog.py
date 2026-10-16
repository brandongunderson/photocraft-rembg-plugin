"""Check catalog integrity and its independent, pinned source evidence."""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "runtime/model-catalog.json").read_text(encoding="utf-8"))
EXPECTED = {
    "birefnet-general-lite", "u2netp", "u2net", "u2net_human_seg", "silueta",
    "isnet-general-use", "isnet-anime", "birefnet-general", "birefnet-portrait",
    "birefnet-dis", "birefnet-hrsod", "birefnet-cod", "birefnet-massive",
}


class CatalogTests(unittest.TestCase):
    def test_reviewed_model_set_and_simple_descriptions(self):
        self.assertEqual(CATALOG["apiVersion"], 1)
        self.assertEqual(CATALOG["rembgVersion"], "2.0.85")
        self.assertEqual({row["id"] for row in CATALOG["models"]}, EXPECTED)
        self.assertEqual(len(CATALOG["models"]), len(EXPECTED))
        for row in CATALOG["models"]:
            self.assertTrue(row["label"].strip())
            self.assertTrue(15 <= len(row["description"]) <= 60)
            self.assertNotRegex(row["description"].lower(), r"best|guarantee|state.of.the.art")

    def test_bundled_identity_and_optional_sizes(self):
        bundled = json.loads((ROOT / "runtime/models.json").read_text(encoding="utf-8"))["models"]
        selected = {row["id"]: row for row in CATALOG["models"] if row["bundled"]}
        self.assertEqual(set(selected), {row["id"] for row in bundled})
        for row in bundled:
            for key in ("file", "bytes", "sha256"):
                self.assertEqual(selected[row["id"]][key], row[key])
        self.assertEqual(sum(row["bytes"] for row in CATALOG["models"] if not row["bundled"]), 6_586_887_748)

    def test_immutable_asset_contract(self):
        for row in CATALOG["models"]:
            url = urlsplit(row["url"])
            self.assertEqual((url.scheme, url.netloc), ("https", "github.com"))
            self.assertRegex(url.path, r"^/danielgatis/rembg/releases/download/v0\.0\.0/[\w.-]+\.onnx$")
            self.assertFalse(url.query or url.fragment)
            self.assertTrue(0 < row["bytes"] < 1024**3)
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(row["upstreamMd5"], r"^[0-9a-f]{32}$")
            self.assertEqual(row["file"], "models/" + row["id"] + ".onnx")
            self.assertIn(row["license"], {"MIT", "Apache-2.0"})
            self.assertTrue((ROOT / row["licenseFile"]).is_file())
            self.assertIn(CATALOG["rembgSourceRevision"], row["sessionSource"])

    def test_provenance_file_hashes_and_weight_proof(self):
        provenance = json.loads((ROOT / "runtime/model-catalog-provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(len(provenance["files"]), 10)
        for row in provenance["files"]:
            data = (ROOT / row["path"]).read_bytes()
            self.assertEqual(len(data), row["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), row["sha256"])
        proof = json.loads((ROOT / "verification/model-catalog-asset-proof.json").read_text(encoding="utf-8"))
        self.assertEqual(len(proof["assets"]), 11)
        models = {row["sessionModule"]: row for row in CATALOG["models"] if not row["bundled"]}
        for row in proof["assets"]:
            model = models[row["module"]]
            for key in ("url", "bytes", "sha256", "upstreamMd5"):
                self.assertEqual(row[key], model[key])

    def test_pinned_rembg_sessions_when_runtime_is_prepared(self):
        sessions = ROOT / "runtime/cache/python-runtime/Lib/site-packages/rembg/sessions"
        if not sessions.is_dir():
            self.skipTest("Prepare the pinned private runtime to check its session source")
        for row in CATALOG["models"]:
            source = (sessions / (row["sessionModule"] + ".py")).read_text(encoding="utf-8")
            module = ast.parse(source)
            self.assertIn(row["sessionClass"], {node.name for node in module.body if isinstance(node, ast.ClassDef)})
            self.assertIn(row["url"], source)
            self.assertIn("md5:"+row["upstreamMd5"], source)
            self.assertRegex(source, r'return ["\x27]'+re.escape(row["id"])+r'["\x27]')


if __name__ == "__main__":
    unittest.main()
