# Optional model provenance

The download catalog is pinned to the automatic local ONNX sessions in rembg
2.0.85, source revision `202e42649a8492a7c49f808de36608a7d1cbbfe3`.
`runtime/model-catalog.json` records the exact release URL, byte count, SHA-256,
upstream session MD5, Python session class, source and license for each model.
The two bundled model files remain unchanged. The other eleven are downloaded
only when the user explicitly requests one.

The optional files total 6,586,887,748 bytes. Each full BiRefNet model is
972,666,916 bytes. The catalog describes intended subject types, not a promise
that one model produces a better cutout. Compare results on the actual image.

All eleven optional rembg release assets were streamed in full on 2026-10-15.
Their SHA-256 digests were computed locally; their byte counts matched GitHub's
release metadata and their MD5 digests matched the pinned rembg session source.
GitHub did not publish asset SHA-256 digests for these older release files.
`verification/model-catalog-asset-proof.json` retains that check's results.
Weights were not retained or added to the plugin package during this catalog
review. The shipped downloader independently checks the catalog's SHA-256 and
size before using a requested model.

| Family | Publisher and original terms |
|---|---|
| U²-Net, U²-Net Small, U²-Net Human | Xuebin Qin and contributors, [U-2-Net Apache-2.0 license](https://github.com/xuebinqin/U-2-Net/blob/ac7e1c817ecab7c7dff5ce6b1abba61cd213ff29/LICENSE), retained in `../U2Net-Apache-2.0.txt`. |
| Silueta | Quantized U²-Net shared by Kikedao; [original author discussion](https://github.com/xuebinqin/U-2-Net/issues/295). It retains U²-Net's Apache-2.0 terms. |
| IS-Net General | Xuebin Qin and contributors, [DIS Apache-2.0 license](https://github.com/xuebinqin/DIS/blob/b6764e20381f6f42a70f83fa3324181529ed1403/LICENSE.md), retained as `DIS-Apache-2.0.txt`. |
| IS-Net Anime | SkyTNT and contributors; the pinned official anime-seg model card declares Apache-2.0. Its card and project license are retained here. |
| BiRefNet family | Peng Zheng and contributors; upstream MIT license retained as `../BiRefNet-MIT.txt`. The pinned official model cards for Lite, legacy General, Portrait, DIS5K, HRSOD and COD explicitly declare MIT. The DIS5K-TR_TEs card for Massive displays an MIT license badge and points to the upstream project; its model metadata has no separate license field. All seven cards are retained here. |

`runtime/model-catalog-provenance.json` records immutable URLs and SHA-256
checksums for the additional license and model-card copies. The catalog uses
the rembg-distributed ONNX conversions, rather than downloading the current
PyTorch/Safetensors checkpoints from those model-card repositories. These
upstream records identify the publisher and terms; historical conversion
lineage and training-data rights have not been independently reconstructed.

The [rembg maintainer's clarification](https://github.com/danielgatis/rembg/issues/837#issuecomment-5172958667)
explicitly distinguishes rembg's MIT code from model weights. It identifies
U²-Net, U²-Net Small, U²-Net Human, Silueta and IS-Net General as governed by
their respective upstream Apache-2.0 terms. Download hosting does not relicense
those models. Preserve upstream notices when redistributing downloaded weights.

SAM, clothing parsing, BRIA RMBG, custom paths and cloud sessions are not in this
catalog. SAM needs prompt controls, clothing parsing has several output masks,
and BRIA has separate model licensing requirements. Adding an arbitrary ONNX
file is not supported: every exposed session has a fixed adapter and checksum.
