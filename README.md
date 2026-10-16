# Rembg Background Removal for PhotoCraft

A PhotoCraft plugin using the [rembg Python library](https://github.com/danielgatis/rembg/tree/v2.0.85). Version **1.2.0** bundles rembg **2.0.85**, a private CPython 3.13 runtime, CPU inference libraries, and two local models. Download additional models through the plugin's pinned catalog. All controls and the comparison preview appear inside PhotoCraft; the package supplies its Python runtime.

[Source repository](https://github.com/brandongunderson/photocraft-rembg-plugin)

[Download the latest plugin](https://github.com/brandongunderson/photocraft-rembg-plugin/releases/latest/download/PhotoCraft-Rembg.pcplugin) · [All releases](https://github.com/brandongunderson/photocraft-rembg-plugin/releases)

You can install this alongside [Background Removal](https://github.com/brandongunderson/photocraft-background-removal-plugin), which uses IMG.LY models through a Rust worker. Rembg uses the distinct id `org.photocraft.rembg`.

## Install and use

1. Run the updated Windows x64 PhotoCraft build supporting panel API 2, package format 2, `host.commands.invoke` version 1, `plugin.processImage` and `plugin.runTask`. This release requires API 2; replace older API 1 panels with this rebuilt package.
2. Choose **Plugins → Manage Plugins → Browse**, then select **PhotoCraft-Rembg.pcplugin**. Review its requested access and bundled native-code permission, then install.
3. Open an image and choose **Plugins → Rembg Background Removal**.
4. Choose a model and result. Each model name includes a short explanation. For an optional model, select **Check model status** to see its size, installation status and terms, then **Download selected model**. Model actions work without an image open. Leave optional edge controls at their defaults initially, then select **Generate preview**.
5. Drag the comparison divider to inspect the result. **Fit**, **100%**, and pan help inspect edges. Generating a preview leaves the source unchanged.
6. Choose a destination and **Apply**, or select **Discard**. The default destination creates a new unsaved result tab. Because this plugin preserves dimensions, a new raster layer is also available. Layer Apply is undoable; the original layers remain beneath the result and are hidden in the same history step so transparency matches the preview. Undo restores their visibility.

Use **Manage Plugins** to disable, replace, or remove the plugin. Keep its stable id when publishing updates. Replacing an installed package requires the manager's replacement option and native-code consent. The original downloaded package is no longer needed after installation.

## Models and settings

| Control | Meaning |
|---|---|
| BiRefNet General Lite | Default bundled general-purpose segmentation model, id `birefnet-general-lite` |
| U²-Net Small | Smaller bundled alternative, id `u2netp`; compare its speed and edges on your images |
| Keep subject | Retain the estimated foreground using transparency |
| Keep background | Retain the estimated background; content hidden behind the subject is not reconstructed |
| Subject mask | Show effective foreground coverage as opaque grayscale; white retains, black removes, and existing source transparency reduces coverage |
| Alpha matting | Slower edge refinement using rembg's matting implementation; can change foreground edge colors as well as opacity |
| Foreground threshold | Integer 0–255, default 240; values above this mask threshold seed confident foreground for matting |
| Background threshold | Integer 0–255, default 10; values below this threshold seed confident background; must be below the foreground threshold |
| Edge erosion | Integer 0–50, default 10; erodes confident regions when preparing matting; zero uses rembg/SciPy's default cross-shaped structuring element |
| Post-process mask | Optional binary-edge cleanup before composition/matting; leave off to retain the model's soft coverage |

Threshold and erosion settings affect alpha matting. Post-processing can harden edges and remove the model's partial coverage; it is not a general quality upgrade. Matting is limited to **4 megapixels** because its memory and execution cost grow with image size. Turn it off or resize a copy for larger sources. Difficult hair, translucent material, similar foreground/background colors, or small details may still require manual refinement. Model names do not guarantee a quality ranking.

## Optional model downloads

The model list includes these automatic local sessions. Short explanations appear next to their
names in the selector; a model's description and exact download size also appear when checking status.

| Model | Simple explanation | Availability |
|---|---|---|
| BiRefNet General Lite | General photos with a smaller model | Included |
| U²-Net Small | Small model for simple general cutouts | Included |
| U²-Net | General subjects in everyday photos | Download |
| U²-Net Human | People and full-body silhouettes | Download |
| Silueta | Smaller U²-Net alternative for general subjects | Download |
| IS-Net General | General subjects with detailed object outlines | Download |
| IS-Net Anime | Anime and illustrated characters | Download |
| BiRefNet General | General subjects using the full BiRefNet model | Download |
| BiRefNet Portrait | People and portrait cutouts | Download |
| BiRefNet DIS | Detailed object shapes and boundaries | Download |
| BiRefNet HRSOD | Prominent subjects in high-resolution photos | Download |
| BiRefNet COD | Objects that blend into their surroundings | Download |
| BiRefNet Massive | An alternative for general-purpose photo cutouts | Download |

Select a model, then use **Check model status**, **Download selected model**, or **Remove downloaded
model**. Downloading is an explicit action and shows progress with cancellation. A complete file must
match the catalog's expected size and SHA-256 before becoming usable. Repeating a download reuses an
already verified copy. Missing or damaged models produce a clear error; generating a preview never
silently fetches one. There is no arbitrary URL or custom checkpoint entry.

Downloaded weights belong to this plugin's own user cache under
`%LOCALAPPDATA%/PhotoCraft/Plugins/org.photocraft.rembg/models`. They survive normal package replacement
and are separate from the installed package. **Remove downloaded model** only removes that model's
cached copy; the two included models are kept. Uninstalling the plugin in PhotoCraft removes its
installed payload, so remove optional models first if you also want to reclaim their cache space.
PhotoCraft's manager shows installed package/model payload size; use the plugin's status action for
optional model storage. A downloaded model can be larger than the installer's individual-file limit
because it is not an archive member; plugin-owned bounded verification still applies.

Some full BiRefNet models approach one gigabyte and can require substantially more RAM during
inference. Model names describe training/use cases, not a guaranteed quality ranking. Compare results
on your own images. This plugin does not expose rembg's cloud services, arbitrary model paths,
prompt-based SAM, clothing parsing, BRIA RMBG, CUDA/ROCm, or ViTMatte.

## Images, limits, and privacy

PhotoCraft supplies the full visible flattened composite as **8-bit RGBA sRGB**, converting supported 8/16-bit RGB or grayscale documents before processing. Results keep the original width and height and are also 8-bit RGBA sRGB. **Keep subject** and **Keep background** multiply their estimated opacity by the original alpha, so previously transparent pixels stay transparent. **Subject mask** is an opaque grayscale image of effective coverage; originally transparent pixels become black in that mask rather than visible subject color.

Input is limited to **32 megapixels**, **32,768 pixels per side**, and the host's shared image/memory bounds. Alpha matting has the separate 4-megapixel limit. These bounds do not guarantee enough free RAM on every machine. CPU inference and matting can take time; the first matting run may also compile numerical kernels. A new tab retains source DPI; same-size layer Apply uses PhotoCraft's normal conversion to the source profile and bit depth. Inference does not recover original 16-bit precision. Convert a copy of unsupported HDR/32-bit or other document modes first.

Processing is local and does not send images to a cloud API. Network access occurs only when the user explicitly downloads a selected optional model, from the fixed HTTPS rembg release URLs in the plugin's catalog. Its dependencies and two starter models remain bundled. The native worker runs with the user's Windows permissions, outside the panel's WASM sandbox. Install packages only from publishers you trust. Windows OS libraries remain system prerequisites.

The worker extracts the bundled private Python runtime into a per-job temporary directory, then launches that interpreter directly in isolated mode with bytecode writes disabled (`-I -B`). Numerical caches belong to the private temporary job, not the installed package. The Rust worker supervises Python, stops and reaps it on cancellation or host disconnect, and cleans private files afterward. Unapplied results remain tied to the source revision and plugin installation; source changes or disabling/replacing the plugin invalidate them.

## Independent source project

```text
authoring.json                Panel API 2 and package-v2 authoring source
extension/build.rs            Validates authoring and generates manifest/bindings
extension/src/lib.rs           Typed panel handler and bounded SDK export
extension/vendor/              Private PhotoCraft API/SDK sources and release hashes
src/                          Rust native supervisor and generic job validation
python/                       rembg adapter, composition and Python-side tests
runtime/                      Pinned private runtime archive, models and provenance
runtime/model-catalog.json    Optional model descriptions, hashes, sizes and source/terms
runtime/licenses/             Model, interpreter and runtime notices
requirements.lock             Pinned Python dependency closure
scripts/fetch-assets.ps1      Restore approved runtime/model assets
scripts/build-plugin.ps1      Build and package the installable plugin
verification/                 Completed validation evidence
```

The panel and native worker have separate Cargo workspaces and lockfiles. Both build independently of the PhotoCraft editor and other plugins. Source history includes manifests, lockfiles, pinned asset records, fetch/build scripts and notices. Cargo caches, generated packages, downloaded runtimes/models, temporary test files and machine-specific validation reports stay local. The Markdown summaries in `verification/` record the tested releases and limits; their referenced JSON reports accompany local test runs.

PhotoCraft supplies its shared installer, permissions, WASM execution, generic image/task transport, progress/cancellation, comparison and document transactions. The general `plugin.runTask` capability lets any consenting native plugin perform its own maintenance without an image open. It contains no rembg model registry, network downloader or cache logic. Model choices, settings, validation, rembg, Python, numerical libraries, ONNX Runtime, downloads and processing code belong to this plugin. Updating those within the supported contracts requires rebuilding this package, without changing the editor.

See the [PhotoCraft plugin documentation](https://github.com/brandongunderson/photocraft/tree/feature/plugin-platform/docs) for host compatibility and API contracts. [Validation results](verification/TEST-RESULTS.md) identify the tested release package and the scope of plugin, installed-package and desktop checks. The machine-specific reports and screenshots referenced by those results remain local test artifacts.

## Build and develop

Use Rust 1.95 or later with a Windows x64 linker and the `wasm32-unknown-unknown` target. The asset scripts also require Python 3.11 or later and Windows' system `tar.exe` for cabinet extraction. Asset scripts verify pinned source URLs and hashes. Preserve the license and provenance records when preparing a release.

From this project directory:

```powershell
rustup target add wasm32-unknown-unknown
./scripts/fetch-assets.ps1
python ./scripts/sync-panel-models.py --check
cargo test --locked
cargo test --locked --manifest-path extension/Cargo.toml
cargo clippy --locked --all-targets -- -D warnings
cargo clippy --locked --manifest-path extension/Cargo.toml --all-targets -- -D warnings
./scripts/build-plugin.ps1 -Python python
```

Use the scripts' offline mode when all required assets and compiler dependencies are cached. Pass `-Python <path-to-python.exe>` to the fetch/build scripts to select the developer interpreter. The output is **dist/PhotoCraft-Rembg.pcplugin**. Test the final package in PhotoCraft with a clean runtime environment; native unit tests alone cannot establish bundled Python/DLL compatibility. Consult `verification/` for recorded cases, hashes and practical limits.

The runtime builder uses pinned CPython and wheel inputs, then writes the resulting ZIP hash into `runtime/runtime.json`. ZIP bytes can differ between developer Python/zlib versions. The verified release archive used Python 3.12.14 with zlib 1.3.2 as its producer; the embedded interpreter remains CPython 3.13.16. Use the same producer to reproduce that archive byte for byte. Other producers require validation of the newly built package.

To change a control, update the embedded manifest and its handler together. To change optional models, update `runtime/model-catalog.json`, the explicit Python session registry, validation and notices. Run `python scripts/sync-panel-models.py` to regenerate the dropdown, then rebuild. Confirm new weights' identity and terms from primary sources. Keep unknown options rejected. Rebuild the WASM after any manifest/catalog change; editing a loose JSON file after installation has no effect. Update the plugin release version and reinstall with replacement enabled.

## Package and worker contract

The `.pcplugin` is an ordinary ZIP with `package.json` and `plugin.pcext` at its root, without an enclosing directory. Its native entry is `photocraft-rembg-worker.exe` and its service is **plugin.processImage**. The panel grants `documentRead`, `plugin.processImage` and `plugin.runTask`. It cannot choose arbitrary executable paths, shell commands, files or another installation's backend.

The handler returns one generic request with `processor: "native"`, exact source `width`/`height`, `preview: true`, and plugin-owned `options`:

```json
{
  "model": "birefnet-general-lite",
  "output": "foreground",
  "alpha_matting": false,
  "foreground_threshold": 240,
  "background_threshold": 10,
  "erode_size": 10,
  "post_process_mask": false
}
```

PhotoCraft invokes the installed worker directly with `--job <absolute-job-json>`. Job API version 1 supplies absolute `input`/`output` PNG paths, `options`, `outputSize: {width,height}`, and `colorSpace: "srgb"`. The worker validates these fields and plugin bounds before loading inference. Unknown models/options, resizing requests and incompatible inputs fail clearly. Progress uses JSON lines on stderr; image bytes are written only to the designated PNG. stdin cancellation or EOF stops the operation. No HTTP server, CLI image stream, global interpreter or core-specific service participates.

Model buttons return a sole `plugin.runTask` command with options
`{"action":"status|download|remove","model":"catalog-id"}`. The host invokes the same installed
worker with `--task <absolute-job-json>`, supplying API version 1, options and a host-owned JSON output
path. A successful result contains `apiVersion: 1`, a friendly `message`, and a bounded `data` object.
This route receives no document pixels, creates no preview/history entry, and does not increment the
image-processing run count. It uses the same host cancellation/progress boundary. The native plugin
owns cache paths, file verification, locking, HTTPS requests and cleanup.

## Licenses

The plugin source is MIT. rembg, model weights, CPython, numerical libraries, ONNX Runtime and Microsoft runtime components retain separate terms. The MIT source license does not relicense model weights or proprietary redistributables. Preserve [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), the original notices in `runtime/licenses/`, Python package license metadata and pinned asset/provenance manifests. The U²-Net checkpoint's older conversion history is not fully documented; its rembg release mirror does not change the upstream model terms.

## API 2 compatibility (1.2.0)

This release requires a PhotoCraft host supporting **panel API 2**, package format 2 and
the `host.commands.invoke` capability at version 1. API 1 panels are no longer supported.
The stable plugin id, model choices, processing algorithms and worker protocols are preserved.
The native image/task protocol remains version 1; it is separate from the panel API.

Edit `authoring.json` for both the panel descriptor and archive metadata. The panel's
build script validates it with the private SDK and generates the embedded descriptor and
bindings into Cargo output. The package builder derives its root `package.json` from the
same source. `extension/vendor/` contains this project's SDK/API sources and their
`SDK-RELEASE.json` hashes. Builds require no PhotoCraft source checkout or sibling plugin.
The SDK handles bounded ABI buffers and API 2 event validation, including additive host
metadata. Failed/unknown/observer events propose no processing and preserve panel state.
