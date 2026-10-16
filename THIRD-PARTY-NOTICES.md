# Third-party notices for Rembg Background Removal

The plugin's own Rust/Python adapter and documentation use the MIT license in `LICENSE`.
Bundled third-party source, binaries and model weights retain their original terms.
Do not treat the plugin's MIT license, or rembg's MIT license, as a license for every model
or runtime component. Preserve the original license texts, copyright notices and asset records
when redistributing a package or source export.

## rembg

[rembg 2.0.85](https://github.com/danielgatis/rembg/tree/v2.0.85), by Daniel Gatis and contributors,
is used as a Python library under its [MIT license](https://github.com/danielgatis/rembg/blob/v2.0.85/LICENSE.txt).
Its CLI, HTTP server and cloud providers are not this plugin's user interface. Two local model
sessions are bundled; approved additional sessions can be downloaded explicitly through the
plugin's pinned catalog. The library's default model is not used.
The runtime contains the distribution's original license metadata.

## Bundled models

| Model in this plugin | Upstream and model terms |
|---|---|
| `birefnet-general-lite` | BiRefNet by Peng Zheng and contributors; [source MIT license](https://github.com/ZhengPeng7/BiRefNet/blob/c4d649666cc171486329413dc2b61f0137158b6a/LICENSE). The [official BiRefNet_lite model card](https://huggingface.co/ZhengPeng7/BiRefNet_lite/blob/aa62cd87eafb9cc43056d08ef3615a14628b831d/README.md) separately declares MIT terms. The shipped ONNX file is the rembg-distributed conversion, pinned by URL and checksum. |
| `u2netp` | U²-Net by Xuebin Qin and contributors; [upstream Apache License 2.0](https://github.com/xuebinqin/U-2-Net/blob/ac7e1c817ecab7c7dff5ce6b1abba61cd213ff29/LICENSE). The rembg-hosted ONNX checkpoint remains subject to the upstream model terms. Its historical conversion process is not fully documented. |

Original model license copies are retained as `runtime/licenses/BiRefNet-MIT.txt`,
`runtime/licenses/BiRefNet-lite-MODEL-CARD.md` and `runtime/licenses/U2Net-Apache-2.0.txt`;
exact asset URLs and
SHA-256 values are recorded by the fetch/provenance manifests. A checksum establishes which
bytes were packaged; it does not prove training-data provenance or grant additional rights.
The [rembg maintainer's clarification](https://github.com/danielgatis/rembg/issues/837#issuecomment-5172958667)
distinguishes the library's MIT code license from the licenses of hosted model weights.

This package does not include BRIA RMBG weights, cloud services, SAM or ViTMatte checkpoints.
References to their capabilities in upstream rembg do not imply those models are bundled or licensed here.

## Optional downloaded models

`runtime/model-catalog.json` identifies eleven additional automatic local models downloaded only
on the user's explicit request. Their original notices and model cards are retained under
`runtime/licenses/optional-models/`; its `README.md` describes the source and licensing evidence.
`runtime/model-catalog-provenance.json` records immutable source revisions and notice hashes.
Every optional rembg release asset was fully streamed, checked against its upstream MD5/size,
and pinned by SHA-256 before being added. Downloading or converting a checkpoint does not
relicense its weights or establish the provenance of its training data.

The catalog records Apache-2.0 terms for the U²-Net/Silueta and IS-Net families, MIT
for BiRefNet, and the exact publisher sources supporting those terms. The
historical conversion provenance qualifications remain documented. BiRefNet Massive's official
model card displays a publisher MIT badge although its metadata has no separate license field;
the retained source record makes that distinction explicit.

## Private Python and numerical runtime

The package includes a private CPython 3.13 interpreter and the pinned dependency closure
listed in `requirements.lock` and `runtime/python-packages.json`. It uses CPU ONNX Runtime,
NumPy, Pillow, SciPy, scikit-image, PyMatting, Numba, llvmlite and their transitive libraries.
Each distribution retains its own license metadata in the runtime archive. CPython's
original `LICENSE.txt`, including notices for components in the interpreter distribution,
is retained as `runtime/licenses/Python-LICENSE.txt`. Scientific binary wheels can contain additional native
libraries with their own notices; the collected package metadata is part of redistribution.

Microsoft Visual C++ runtime DLLs, when included, are proprietary redistributables rather
than MIT code. Preserve `runtime/licenses/MICROSOFT-VC-RUNTIME-LICENSE.html` and
`runtime/licenses/MICROSOFT-VC-RUNTIME-NOTICE.md`. Publishing them
requires the distributor's qualifying redistribution rights; local packaging or successful
execution does not establish that entitlement. The plugin does not run a system-wide
Microsoft or Python installer. Wheel license copies are collected beneath
`runtime/licenses/python-wheels/`, with their mapping in `runtime/python-packages.json`;
rembg's own text is also retained as `runtime/licenses/rembg-MIT.txt`.

The FlatBuffers 25.12.19 wheel does not contain its full license text. The
supplemental `runtime/licenses/FlatBuffers-Apache-2.0.txt` is copied from the
upstream release's immutable revision
[`7e163021e59cca4f8e1e35a7c828b5c6b7915953`](https://github.com/google/flatbuffers/blob/7e163021e59cca4f8e1e35a7c828b5c6b7915953/LICENSE).
Its source URL and checksum are recorded in `runtime/assets.json`, and its
distribution mapping is retained in `runtime/python-packages.json`.

## Panel and Rust dependencies

The bounded panel ABI storage follows PhotoCraft's independent Image Gain starter, available
under MIT OR Apache-2.0 and used here under MIT. The panel uses serde_json and its pinned
transitive Rust dependencies. The native supervisor's separate Cargo lockfile records its
own dependency closure. Preserve collected Rust dependency licenses and notices as well as
the Python/model records. PhotoCraft editor crates and other plugin binaries are not linked
or copied as runtime dependencies.

`scripts/package-plugin.py` is an unmodified copy of PhotoCraft's independent
`scripts/plugins/package-plugin.py` helper, also available under MIT OR Apache-2.0
and used here under MIT. The original ArtCraft Team and PhotoCraft contributors'
copyright notice and MIT terms for the copied starter/helper are retained in
`licenses/PhotoCraft-MIT.txt`.
