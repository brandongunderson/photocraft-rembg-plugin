# Rembg 1.0.0 validation

Verified locally on Windows x64 on 2026-10-15. This package uses the actual rembg 2.0.85
library with CPU ONNX Runtime 1.31.0 and private CPython 3.13.16. PhotoCraft's existing
package-v2 image API is used without editing core source or rebuilding the editor.

## Completed checks

- Native Rust: seven tests passed; the ignored helper is invoked as a subprocess by the
  cancellation test. Protocol, dimensions, PNG headers, runtime ZIP paths/CRC/bounds/empty
  files and child kill/reap behavior are covered. Formatting, all-target Clippy and release build passed.
- Panel: seven tests, formatting, native and WASM-target Clippy, and release WASM build passed.
  Model/result mapping, strict settings, limits and deferred guest state are covered.
- Python: five adapter tests passed, including with the packaged interpreter. Source alpha,
  original RGB, mask composition, duplicate/unknown fields, model hashes and no-overwrite output
  publication are covered. Five runtime-preparation tests also passed.
- Actual staged worker: nine processing/cancellation cases passed. Disabling unused Numba JIT
  on non-matting jobs produced exactly the same RGBA pixels for both models and all three modes.
  Matting retains JIT. This reduced ordinary processing from roughly 34–46 seconds to 9–19 seconds
  in those local cases, including fresh private-runtime preparation and cleanup.
- Final package: **16 actual cases passed**, including both models, subject/background/mask,
  alpha matting, hard-edge post-processing, original transparency/color checks, malformed requests,
  early cancellation, host EOF, cancellation during inference and 24-MP processing. The
  24-MP U2NetP case completed in about 11.7 seconds; matting above 4 MP was rejected clearly.
  Active-inference cancellation and cleanup took about 1.9 seconds. These are single local
  measurements, not hardware-independent performance guarantees.
- Host acceptance: two external tests passed against the already compiled public PhotoCraft API.
  Real package installation/restart/download removal, default BiRefNet preview, source/lease safety,
  new-tab Apply, same-size 16-bit layer conversion, Undo/Redo, Discard, stale-source rejection,
  cancellation and deferred state were exercised. The real generated UI's model selector,
  Generate preview, destination selector, Apply and Done were clicked.
- Four ready/completed screenshots at 1152×768 and 640×480 were captured; representative completed
  wide and compact states were inspected. The compact body scrolls; footer actions stay visible.
- The unchanged desktop editor loaded this package alongside AI Upscale, IMG.LY Background
  Removal and the neutral starter on startup and restart with disposable settings. Exact installed
  and model sizes matched; restricted native processing was refused.

## Isolation and reproducibility

The exact-package cases used only Windows directories in PATH and deliberately unusable ambient
Python and model-cache paths. The private runtime import probe confirmed Python, the scientific
modules and all four Microsoft VC DLLs loaded from the private runtime. No global Python or
runtime installation is used. Offline model resolution is explicit; automatic model downloads
are disabled. Every completed/cancelled package case cleaned its private runtime and pending output.

A fresh independent copy of the plugin's scripts, pinned manifests, retained license sources
and cached upstream assets reproduced the final runtime ZIP byte-for-byte without prebuilt DLLs,
the editor or either sibling plugin. The recorded producer is Python 3.12.14 / zlib 1.3.2;
compressed ZIP identity is not promised across different producer versions.

The final package is 312,895,540 bytes, SHA256
`425dd6fea2fc3605fb543f2cdf4de5b01bdfad9b6aa7e898fe81b16c26eb9c02`.
Its runtime ZIP is SHA256 `d26e09cf5ed131a6062274575edb7e0e7471167d43e558ea2d85077eac41e2b8`,
containing 5,442 regular files / 404,092,122 expanded bytes. The nested archive is extracted by
the plugin under its own limits; PhotoCraft's outer package limits were not increased.

Local-only validation reports retain the package cases, runtime import checks, restoration
proof and host screenshots. Images use NASA/JSC public-domain material recorded in the local
`photo-source.json`; processed images are plugin outputs. Consult the
[PhotoCraft plugin documentation](https://github.com/brandongunderson/photocraft/tree/feature/plugin-platform/docs)
for the current host contracts.

## Qualifications

Only Windows x64 CPU execution is verified. Normal image input is limited to 32 MP and 32,768
pixels per side; matting is limited to 4 MP. Source/output is flattened 8-bit sRGB through the
shared host boundary; original layers remain available through new-tab output or Undo.
Native plugins retain the user's OS permissions. Difficult edges may need manual refinement.
There is no assertion that every image, computer or third-party plugin is bug-free.

Library, models and runtimes have distinct licenses. Preserve all notices; Microsoft runtime
redistribution requires the publisher's qualifying rights. See `THIRD-PARTY-NOTICES.md`.
Tests used disposable settings and installations; they left user preferences and installed
plugin packages unchanged.
