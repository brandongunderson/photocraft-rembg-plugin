# PhotoCraft Plugin API compatibility

## Release 1.2.1 — 2026-10-16

Validated locally on Windows x64 against the current PhotoCraft Plugin API host.
The plugin privately includes its SDK/API development sources. It builds without the editor
source and requires no sibling plugin or separately installed SDK runtime. Package format 2
and its declared native protocol remain independent.

- Package: `PhotoCraft-Rembg.pcplugin` (313,006,250 bytes).
- SHA-256: `4ca6497ac198e70ad9e71db78d544b4b252608a38125dd0a416c051b58672b44`.
- Final update-metadata revision: 8 panel tests, formatting and all-target Clippy passed.
  The unchanged native worker previously passed 8 tests, formatting and all-target Clippy.
- Release WASM/native builds and package conformance passed. Archive CRCs, all
  35 private SDK files, 3 pinned runtime/model assets, packaged README
  and exact compiled panel/worker bytes were verified.
- The embedded descriptor declares this plugin's [GitHub repository](https://github.com/brandongunderson/photocraft-rembg-plugin)
  and exact update asset `PhotoCraft-Rembg.pcplugin`. Conformance verified both fields;
  update checks and installation require explicit user actions.
- Real-host acceptance on the final package passed: reviewed installation, restart discovery,
  refusal of an undeclared public action, native processing, source-preserving preview,
  layer Apply, Undo/Redo, Discard, new-tab Apply with DPI preserved, stale-source refusal,
  cancellation/reaping preserving source and panel state, and removal.
- Model-status maintenance without a document and task cancellation preserving panel state passed.
- The standalone ignored child-process fixture is exercised by the passing cancellation test.

## Scope and limits

The integration run used a deterministic 32×24 synthetic image in a 16-bit document.
Native image transport and previews are 8-bit sRGB; layer Apply preserved the document's
16-bit depth. Removal plugins exercised their default model/output. This run does not
qualify every model, large-image performance or additional operating systems. Desktop
click-through and installation of a future GitHub release were outside this run. User
installations and normal plugin-data folders were untouched; all host stores and plugin
user data were isolated.

Host verification used Rust 1.99.0 (`b940084d7eb6a299eb4bfeb8e34901bc051e7ac4`),
`x86_64-pc-windows-gnu`. Machine-specific logs, PNGs and host-library fingerprints remain
local verification artifacts. See [README](../README.md) for processing, platform and license limits.
