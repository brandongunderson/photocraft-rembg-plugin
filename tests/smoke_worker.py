"""Exercise an installed/extracted package's real worker and bundled rembg models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from PIL import Image, ImageDraw

parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True, type=Path)
parser.add_argument("--work", required=True, type=Path)
parser.add_argument("--cases", nargs="*")
args = parser.parse_args()
args.work.mkdir(parents=True, exist_ok=True)
worker = args.root.resolve() / "photocraft-rembg-worker.exe"
work = args.work.resolve()
private = work / "private"
private.mkdir(exist_ok=True)
source = work / "input.png"
image = Image.new("RGBA", (96,64), (230,230,230,255))
ImageDraw.Draw(image).ellipse((25,4,71,61), fill=(160,40,30,255))
ImageDraw.Draw(image).rectangle((0,0,7,63),fill=(20,50,80,0))
ImageDraw.Draw(image).rectangle((88,0,95,63),fill=(20,50,80,128))
image.save(source)
original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
results = []


def run(name, model="u2netp", output="foreground", cancel=None, **options):
    destination = work / (name + ".png")
    destination.unlink(missing_ok=True)
    job = work / (name + "-job.json")
    job.write_text(json.dumps(dict(apiVersion=1,input=str(source),output=str(destination),options=dict(model=model,output=output,**options),outputSize=dict(width=96,height=64),colorSpace="srgb")),encoding="utf-8")
    env = dict(os.environ, TEMP=str(private), TMP=str(private))
    started = time.monotonic()
    child = subprocess.Popen([str(worker),"--job",str(job)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    lines = queue.Queue()
    def read():
        for line in child.stderr:
            lines.put(line.decode("utf-8",errors="replace"))
        lines.put(None)
    threading.Thread(target=read,daemon=True).start()
    diagnostics = []
    cancelled = None
    phases = {}
    try:
        while True:
            if time.monotonic() - started > 300:
                raise TimeoutError(name)
            try: line = lines.get(timeout=.25)
            except queue.Empty: continue
            if line is None: break
            diagnostics.append(line)
            try: event = json.loads(line)
            except json.JSONDecodeError: continue
            value = event.get("progress",0)
            if value in (1,20,25,30,45,90,95,99,100):
                phases.setdefault(str(value),round(time.monotonic()-started,3))
            trigger = 2 <= value < 18 if cancel == "extraction" else value == 45
            if cancel and trigger and cancelled is None:
                cancelled = time.monotonic()
                if cancel == "eof": child.stdin.close()
                else:
                    child.stdin.write(b"cancel\n")
                    child.stdin.flush()
        code = child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        if not child.stdin.closed: child.stdin.close()
        child.stderr.close()
    (work / (name + ".log")).write_text("".join(diagnostics),encoding="utf-8")
    result = dict(test=name,model=model,output=output,seconds=round(time.monotonic()-started,3),exitCode=code)
    result["phaseSeconds"] = phases
    if cancel:
        assert cancelled is not None,diagnostics[-10:]
        result["cancelExitSeconds"] = round(time.monotonic()-cancelled,3)
        assert code != 0 and not destination.exists(),diagnostics[-10:]
        assert result["cancelExitSeconds"] < 5,result
    else:
        assert code == 0,diagnostics[-10:]
        with Image.open(destination) as processed:
            assert processed.mode == "RGBA" and processed.size == image.size
            assert processed.info.get("icc_profile")
            if output == "mask":
                assert processed.getextrema()[3] == (255,255)
                assert processed.getpixel((0,0)) == (0,0,0,255)
                assert all(r == g == b for r,g,b,a in processed.getdata())
            else:
                assert processed.getpixel((0,0))[3] == 0
                assert processed.getpixel((90,0))[3] <= 128
                if not options.get("alpha_matting") or output == "background":
                    assert all(p[:3] == original[:3] for p,original in zip(processed.getdata(),image.getdata()))
    assert not list(private.glob("photocraft-rembg-*")),"Private runtime was not cleaned"
    assert not list(work.glob(".*-pending.png")),"Pending output was not cleaned"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    results.append(result)
    print(json.dumps(result),flush=True)


cases = [
    ("birefnet-foreground",dict(model="birefnet-general-lite")),
    ("u2netp-foreground",{}),
    ("u2netp-background",dict(output="background")),
    ("u2netp-mask",dict(output="mask")),
    ("u2netp-matting",dict(alpha_matting=True)),
    ("u2netp-postprocess",dict(post_process_mask=True)),
    ("cancel-byte",dict(cancel="byte")),
    ("cancel-eof",dict(cancel="eof")),
    ("cancel-extraction",dict(cancel="extraction")),
]
assert not args.cases or set(args.cases).issubset({name for name,_ in cases})
for name,options in cases:
    if not args.cases or name in args.cases:
        run(name,**options)
(work / "worker-smoke.json").write_text(json.dumps(dict(sourceUnchanged=True,privateRuntimeCleaned=True,tests=results),indent=2),encoding="utf-8")
