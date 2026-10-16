"""Unit tests run with Pillow plus the bundled Python runtime; no model downloads."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("rembg_worker", Path(__file__).with_name("worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job = dict(apiVersion=1, input=str(self.root / "input.png"), output=str(self.root / "output.png"), options={}, outputSize=dict(width=3,height=2), colorSpace="srgb")
        self.path = self.root / "job.json"

    def load(self, value=None):
        self.path.write_text(json.dumps(self.job if value is None else value),encoding="utf-8")
        return worker.load_job(self.path)

    def test_defaults_and_unknown_fields(self):
        self.assertEqual(self.load()["options"], worker.DEFAULTS)
        for key,value in [("apiVersion",True),("colorSpace","display-p3"),("unknown",1),("input","relative.png")]:
            with self.assertRaises(ValueError): self.load(self.job | {key:value})
        for key,value in [("model","bria-rmbg"),("alpha_matting",1),("foreground_threshold",256),("background_threshold",240),("erode_size",51),("unknown",True)]:
            with self.assertRaises(ValueError): self.load(self.job | {"options":{key:value}})

    def test_duplicate_fields_and_input_bounds(self):
        self.path.write_text('{"apiVersion":1,"apiVersion":2}',encoding="utf-8")
        with self.assertRaises(ValueError): worker.load_job(self.path)
        self.path.write_text(' ' * 16385,encoding="utf-8")
        with self.assertRaises(ValueError): worker.load_job(self.path)
        with self.assertRaises(ValueError): worker.validate_dimensions(2001,2000,True)
        worker.validate_dimensions(2000,2000,True)
        with self.assertRaises(ValueError): worker.validate_dimensions(8001,4000)

    def test_composition_keeps_source_alpha_and_original_rgb(self):
        from PIL import Image
        source = Image.new("RGBA",(3,2),(40,80,120,128))
        source.putpixel((0,0),(40,80,120,0))
        cutout = Image.new("RGBA",source.size,(200,150,100,128))
        foreground = worker.compose(source,cutout,"foreground",False)
        self.assertEqual(foreground.getpixel((1,0)),(40,80,120,64))
        self.assertEqual(foreground.getpixel((0,0))[3],0)
        self.assertEqual(worker.compose(source,cutout,"foreground",True).getpixel((1,0)),(200,150,100,64))
        self.assertEqual(worker.compose(source,cutout,"background",True).getpixel((1,0)),(40,80,120,63))
        self.assertEqual(worker.compose(source,cutout,"mask",False).getpixel((1,0)),(64,64,64,255))

    def test_png_and_atomic_output_never_overwrite(self):
        from PIL import Image
        image = Image.new("RGBA",(3,2),(30,60,90,128))
        input_path = Path(self.job["input"]); image.save(input_path)
        worker.validate_png(input_path,self.job["outputSize"])
        with self.assertRaises(ValueError): worker.validate_png(input_path,{"width":6,"height":2})
        output = Path(self.job["output"])
        worker.save_result(image,output)
        original = output.read_bytes()
        with Image.open(output) as result:
            self.assertEqual(result.mode,"RGBA")
            self.assertTrue(result.info.get("icc_profile"))
        with self.assertRaises(FileExistsError): worker.save_result(image,output)
        self.assertEqual(output.read_bytes(),original)
        self.assertFalse(list(self.root.glob('.rembg-*')))

    def test_model_manifest_is_strictly_local_and_hash_checked(self):
        import hashlib
        model = self.root / "runtime/models/u2netp.onnx"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"local model fixture")
        catalog = json.loads((Path(__file__).resolve().parents[1] / "runtime/model-catalog.json").read_text(encoding="utf-8"))
        manifest = dict(apiVersion=1,models=[row for row in catalog["models"] if row["id"] in worker.model_manager.BUILTIN_MODELS])
        row = next(row for row in manifest["models"] if row["id"] == "u2netp")
        row.update(sha256=hashlib.sha256(model.read_bytes()).hexdigest(),bytes=model.stat().st_size)
        path = self.root / "runtime/model-catalog.json"
        path.write_text(json.dumps(manifest),encoding="utf-8")
        cache = self.root / "cache"
        self.assertEqual(worker.verified_model(self.root,"u2netp",cache),model)
        model.write_bytes(b"damaged")
        with self.assertRaises(ValueError): worker.verified_model(self.root,"u2netp",cache)
        row["sessionModule"] = "../elsewhere"
        path.write_text(json.dumps(manifest),encoding="utf-8")
        with self.assertRaises(ValueError): worker.verified_model(self.root,"u2netp",cache)

    def test_model_is_locked_for_the_full_processing_operation(self):
        from PIL import Image
        import hashlib
        Image.new("RGBA", (3, 2), (30, 60, 90, 128)).save(self.job["input"])
        self.job["options"] = {"model": "u2netp"}
        self.path.write_text(json.dumps(self.job), encoding="utf-8")
        model = self.root / "runtime/models/u2netp.onnx"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"fixture")
        catalog = json.loads((Path(__file__).resolve().parents[1] / "runtime/model-catalog.json").read_text(encoding="utf-8"))
        row = next(row for row in catalog["models"] if row["id"] == "u2netp")
        row.update(bytes=model.stat().st_size, sha256=hashlib.sha256(model.read_bytes()).hexdigest())
        (self.root / "runtime/model-catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
        cache = self.root / "cache"
        def processing(job, path):
            self.assertEqual(path, model)
            with self.assertRaisesRegex(ValueError, "busy"):
                with worker.model_manager.model_lock(cache, "u2netp", timeout=0):
                    self.fail("A model mutation could run during image processing")
        with patch.object(worker, "process", side_effect=processing):
            worker.run(self.path, self.root, cache)
        with worker.model_manager.model_lock(cache, "u2netp", timeout=0):
            pass


if __name__ == "__main__":
    unittest.main()
