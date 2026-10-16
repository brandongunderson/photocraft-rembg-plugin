> Current panel API 2 migration and package identity: [API2-MIGRATION.md](API2-MIGRATION.md). The results below identify their earlier validation artifact.

# Rembg 1.1.0 validation

Machine-specific JSON reports referenced below remain with local validation runs.
This source repository retains the release summary and the scripts used to run its checks.

Verified locally on Windows x64 on 2026-10-15. The package uses rembg 2.0.85,
CPU ONNX Runtime 1.31.0 and private CPython 3.13.16. It retains two bundled models
and exposes eleven explicit optional downloads with plain-language explanations.

## Plugin checks

- Native Rust: eight tests passed; one ignored helper is invoked by the cancellation test.
  Protocol, task options, dimensions, PNG headers, bounded runtime ZIP extraction and child
  kill/reap behavior are covered. Formatting, all-target Clippy and release build passed.
- Panel: nine tests, formatting, native/WASM Clippy and release WASM build passed. The tests
  cover all thirteen choices, explanations, image settings, no-document model actions,
  strict options, limits, own-package command binding and unchanged task state.
- Python: six image-adapter and eight model-manager tests passed, including under the private
  CPython 3.13.16 interpreter. Tests cover source alpha/RGB, composition, strict JSON/options,
  hashes, output publication, pinned HTTPS/redirects, truncated/oversize/bad-hash downloads,
  atomic replacement, insufficient disk space, hard-link/reparse refusal and OS-lock recovery.
  A model lock is held for the full inference operation. Five catalog consistency tests and
  five private-runtime preparation tests also passed.
- Packaged backend: **sixteen actual image/protocol/cancellation cases passed**, including both
  bundled models, subject/background/mask, matting, hard-edge post-processing, original
  transparency/RGB checks, invalid input, host EOF, active inference cancellation and 24-MP
  processing. The 24-MP U²-Net Small case took about 9.9 seconds; active cancellation including
  cleanup took about 0.9 seconds. These are individual local measurements, not speed guarantees.
- Model maintenance: **twenty-four packaged-backend cases passed**, including no-image status,
  included-model removal refusal, invalid tasks, missing-model offline refusal, actual downloads
  of U²-Net, IS-Net Anime and the 972,666,916-byte BiRefNet Portrait model, verified cached reuse,
  real inference for those three models, corrupt-file refusal and removal. Cancelling an active
  download removed staging/partial data in about 0.9 second. No test weights remain in that cache.

All eleven optional upstream model assets were independently streamed in full without retaining
them, matched against upstream release sizes and rembg MD5 pins, and pinned by SHA-256. This
establishes asset identity; it does not claim inference testing of every optional model or quality
on every image. Original model notices/cards and provenance are retained with the catalog.

## Host and source boundaries

Model actions use the general `plugin.runTask` API. They receive no document pixels and do not
create images, comparisons or history entries. PhotoCraft was updated with generic task transport,
permission, progress/cancellation and state checks. All rembg/download/model/cache code remains
in this independent plugin. The existing Upscale and IMG.LY packages are unchanged.

Three installed-package host tests passed for model tasks without an open image, image previews,
new-tab/layer Apply, cancellation and source-change protection. Desktop startup and restart
checks passed, and wide/compact panels were visually checked. The forty backend cases preceded
a punctuation-only panel update; the other 184 payload files are byte-identical. Panel unit
tests and the three host tests passed again against the final package. Local-only JSON reports
retain the tested package identities and byte comparison. Versioned 1.0.0 records are historical.

The [PhotoCraft plugin documentation](https://github.com/brandongunderson/photocraft/tree/feature/plugin-platform/docs)
describes the host contracts, native tasks and validation requirements.

## Isolation and reproducibility

Exact-package cases used only Windows directories in PATH, deliberately unusable ambient
Python/model-cache paths, and disposable LOCALAPPDATA settings inside the workspace. No user
plugin store, preference or model cache was changed. Automatic downloads during inference remain
disabled; explicit downloads use fixed HTTPS rembg release URLs and bounded SHA-256 verification.
Every completed/cancelled case cleaned its private runtime and download staging. Small one-byte
OS-lock files remain deliberately; removing advisory-lock identities would break concurrency.

The private runtime and bundled model bytes are identical to 1.0.0. Its retained import probe
confirmed the interpreter, scientific native modules and all four Microsoft VC DLLs loaded from
the private runtime. An independent offline restoration reproduced the same runtime ZIP using
Python 3.12.14 / zlib 1.3.2; byte identity across different ZIP producers is not promised.

The final package is **312,946,045 bytes**, SHA-256
`26227de6cbe8633f33dbbb263c7b3107d7a73fa616b5197b4d0337c255b7ec15`.
Its 185 regular members total 375,741,317 installed bytes, including 228,579,949 bundled model
bytes. Root and dist copies, ZIP CRCs, source payloads and compiled worker/panel bytes match.
The runtime ZIP is SHA-256 `d26e09cf5ed131a6062274575edb7e0e7471167d43e558ea2d85077eac41e2b8`,
with 5,442 files / 404,092,122 expanded bytes. The host's package limits were not increased.

Detailed plugin evidence: `package-smoke.json`, `model-download-smoke.json`, `panel-copy-update.json`,
`model-catalog-asset-proof.json`, `runtime-import-probe.json` and `runtime-restoration-proof.json`.
NASA/JSC public-domain image provenance is in `photo-source.json`; processed images are outputs.

## Qualifications

Only Windows x64 CPU execution is verified. Normal input is limited to 32 MP and 32,768 pixels
per side; alpha matting is limited to 4 MP. Source/output passes through flattened RGBA8 sRGB.
Full optional BiRefNet models are about 928 MiB each and need additional inference memory.
The private runtime expands to about 385 MiB per active operation. Native plugins have the user's
OS permissions. Difficult edges can require refinement; the checks do not establish universal
image/hardware compatibility or freedom from all bugs.

Library, models and runtimes have distinct licenses. Preserve notices; Microsoft runtime
redistribution requires the publisher's qualifying rights. See [third-party notices](../THIRD-PARTY-NOTICES.md).
