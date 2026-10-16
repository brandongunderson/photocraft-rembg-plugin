# Independent PhotoCraft plugin

Read README.md, authoring.json, extension/src/lib.rs and the worker sources before editing.
Keep dependencies, models and algorithms in this project. No editor or sibling checkout paths.
Target the PhotoCraft Plugin API through the privately vendored SDK 0.1.
Edit authoring.json for identity, controls, required capabilities and package metadata.
Cargo generates the embedded manifest/bindings; packaging derives package.json from that source.
Keep the stable plugin id on updates. The Plugin API, package format 2, native image/task
protocol 1 and filter ABI 1 are independent versions. Do not change worker protocols implicitly.
The SDK macro owns bounded ABI storage. Never add raw pointer access, host imports or leaked buffers.
Accept additive host metadata, preserve state, and issue no effects for observer/unknown events.
Keep user-approved model choices, downloads, cancellation and inference limits intact.
Run both Cargo workspaces' tests, clippy and formatting, then build the actual release WASM/package.
Check it with the current photocraft-plugin tool and test install/restart/preview/Apply/Undo
in a disposable host store. Do not modify a user's installation or publish without authorization.
Retain all dependency and model license notices. Report actual checks and untested behavior.

Maintain CHANGELOG.md for this plugin's releases, with version/date, behavior changes and
compatibility notes. Keep shared platform history in the editor repository. Record future
changes under Unreleased until publishing a tag; do not retag a release for documentation edits.
