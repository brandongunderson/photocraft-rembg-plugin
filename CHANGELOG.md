# Rembg Background Removal changelog

Release history for this standalone PhotoCraft plugin. Plugin release versions, the
PhotoCraft Plugin API and package/worker formats have separate purposes.

## [1.2.0](https://github.com/brandongunderson/photocraft-rembg-plugin/releases/tag/v1.2.0) - 2026-10-16

### Changed

- Migrate the panel to the current PhotoCraft Plugin API using the privately included typed
  SDK/API 0.1 and bounded request/response storage.
- Generate the embedded descriptor, bindings and package metadata from `authoring.json`,
  including the panel model choices derived from the plugin-owned catalog.
- Declare `host.commands.invoke` and retain the stable plugin ID, model choices, saved
  settings and existing native image/task protocols.
- Preserve panel state and avoid processing on observer or unknown events.

### Processing retained in this release

- Local CPU inference with rembg 2.0.85, private CPython 3.13 and bundled inference libraries.
- Two included models: BiRefNet General Lite and U2-Net Small. Eleven optional models have
  explicit status, download and removal controls through `plugin.runTask`.
- Pinned download sizes and SHA-256 checks before accepting optional models. Verified
  downloads remain usable offline.
- Foreground, background and mask output, optional alpha matting and mask post-processing,
  with progress/cancellation and the shared preview/Apply workflow.

### Compatibility

Requires a Windows x64 host supporting the current panel contract (internal discriminator
`2`), package format 2, `host.commands.invoke` version 1, `plugin.processImage` and
`plugin.runTask`. Native image/task protocols remain version 1. The package supplies its
Python runtime and builds without PhotoCraft or another plugin's source.

See [migration verification](verification/API2-MIGRATION.md) for the release checks and
acceptance limits, and [README.md](README.md) for model licenses and image/matting limits.
