//! Independent data-only panel using PhotoCraft's public image-processing capability.
#![deny(unsafe_code)]
#![deny(
    clippy::unwrap_used,
    clippy::expect_used,
    clippy::panic,
    clippy::unimplemented,
    clippy::todo,
    clippy::unreachable
)]

use std::io::{self, Write};
use std::sync::Mutex;

use serde_json::{Value, json};

const MANIFEST: &str = include_str!("../manifest.json");
const MAX_JSON_BYTES: usize = 256 * 1024;
const MODEL_CATALOG: &str = include_str!("../../runtime/model-catalog.json");

fn model_choices() -> Option<Vec<(String, String)>> {
    let catalog: Value = serde_json::from_str(MODEL_CATALOG).ok()?;
    catalog
        .get("models")?
        .as_array()?
        .iter()
        .map(|model| {
            let label = model.get("label")?.as_str()?;
            let description = model.get("description")?.as_str()?.trim_end_matches('.');
            let id = model.get("id")?.as_str()?.to_owned();
            Some((format!("{label}: {description}"), id))
        })
        .collect()
}

fn selected_model(values: &Value) -> Option<String> {
    let choices = model_choices()?;
    match values.get("model") {
        None => choices.into_iter().next().map(|(_, id)| id),
        Some(value) => choices
            .into_iter()
            .find(|(label, _)| value.as_str() == Some(label.as_str()))
            .map(|(_, id)| id),
    }
}
const OUTPUTS: &[(&str, &str)] = &[
    ("Keep subject", "foreground"),
    ("Keep background", "background"),
    ("Subject mask", "mask"),
];

fn reply(request: &Value, message: &str) -> Value {
    json!({"state": request.get("state").unwrap_or(&Value::Null), "message": message, "commands": []})
}

fn choice<'a>(values: &Value, key: &str, choices: &'a [(&str, &str)]) -> Option<&'a str> {
    match values.get(key) {
        None => choices.first().map(|(_, id)| *id),
        Some(value) => choices
            .iter()
            .find(|(label, _)| value.as_str() == Some(*label))
            .map(|(_, id)| *id),
    }
}

fn boolean(values: &Value, key: &str) -> Option<bool> {
    match values.get(key) {
        None => Some(false),
        Some(value) => value.as_bool(),
    }
}

fn integer(values: &Value, key: &str, default: u64, maximum: u64) -> Option<u64> {
    match values.get(key) {
        None => Some(default),
        Some(value) => value.as_u64().filter(|number| *number <= maximum),
    }
}

fn handle(request: &Value) -> Value {
    let Some(object) = request.as_object() else {
        return reply(request, "Invalid event request.");
    };
    if object
        .keys()
        .any(|key| !matches!(key.as_str(), "event" | "document" | "values" | "state"))
    {
        return reply(request, "Unknown event request field.");
    }
    let Some(event) = request["event"].as_str().filter(|event| {
        matches!(
            *event,
            "remove" | "model_status" | "model_download" | "model_remove"
        )
    }) else {
        return reply(
            request,
            "Choose Generate preview or one of the model actions.",
        );
    };
    let Some(values) = request.get("values").filter(|value| value.is_object()) else {
        return reply(request, "Panel values must be an object.");
    };
    if values.as_object().is_some_and(|values| {
        values.keys().any(|key| {
            !matches!(
                key.as_str(),
                "model"
                    | "output"
                    | "alpha_matting"
                    | "foreground_threshold"
                    | "background_threshold"
                    | "erode_size"
                    | "post_process_mask"
            )
        })
    }) {
        return reply(request, "Unknown panel field.");
    }
    let Some(model) = selected_model(values) else {
        return reply(request, "Choose a model from the list.");
    };
    let task = match event {
        "model_status" => Some(("status", "Checking the selected model…")),
        "model_download" => Some((
            "download",
            "Downloading the selected model. You can cancel this operation.",
        )),
        "model_remove" => Some((
            "remove",
            "Removing the selected downloaded model. Included models are kept.",
        )),
        _ => None,
    };
    if let Some((action, message)) = task {
        return json!({"state":request.get("state").unwrap_or(&Value::Null), "message":message,
            "commands":[{"command":"plugin.runTask","params":{"options":{"action":action,"model":model}}}]});
    }
    let Some(document) = request.get("document").and_then(Value::as_object) else {
        return reply(
            request,
            "Open an RGB or grayscale image before generating a preview. Model downloads work without an image.",
        );
    };
    let Some((width, height)) = document
        .get("width")
        .and_then(Value::as_u64)
        .zip(document.get("height").and_then(Value::as_u64))
    else {
        return reply(request, "The active image dimensions are unavailable.");
    };
    let Some(pixels) = width.checked_mul(height) else {
        return reply(request, "The image dimensions are too large.");
    };
    if width == 0 || height == 0 || width > 32_768 || height > 32_768 || pixels > 32_000_000 {
        return reply(
            request,
            "Rembg accepts up to 32 megapixels and 32,768 pixels per side. Resize or crop a copy before continuing.",
        );
    }
    let Some(output) = choice(values, "output", OUTPUTS) else {
        return reply(request, "Choose a supported result.");
    };
    let Some(alpha_matting) = boolean(values, "alpha_matting") else {
        return reply(request, "Alpha matting must be on or off.");
    };
    let Some(post_process_mask) = boolean(values, "post_process_mask") else {
        return reply(request, "Post-process mask must be on or off.");
    };
    let Some(foreground_threshold) = integer(values, "foreground_threshold", 240, 255) else {
        return reply(
            request,
            "Foreground threshold must be an integer from 0 to 255.",
        );
    };
    let Some(background_threshold) = integer(values, "background_threshold", 10, 255) else {
        return reply(
            request,
            "Background threshold must be an integer from 0 to 255.",
        );
    };
    let Some(erode_size) = integer(values, "erode_size", 10, 50) else {
        return reply(request, "Edge erosion must be an integer from 0 to 50.");
    };
    if background_threshold >= foreground_threshold {
        return reply(
            request,
            "Background threshold must be lower than foreground threshold.",
        );
    }
    if alpha_matting && pixels > 4_000_000 {
        return reply(
            request,
            "Alpha matting is limited to 4 megapixels. Turn it off or resize a copy before continuing.",
        );
    }
    let mut state = request
        .get("state")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    let runs = state
        .get("runs")
        .and_then(Value::as_u64)
        .unwrap_or(0)
        .saturating_add(1);
    state.insert("runs".to_owned(), json!(runs));
    json!({
        "state": state,
        "message": "Generating a local preview. Compare the result, then Apply or Discard.",
        "commands": [{"command": "plugin.processImage", "params": {
            "processor": "native", "width": width, "height": height, "preview": true,
            "options": {"model": model, "output": output, "alpha_matting": alpha_matting,
                "foreground_threshold": foreground_threshold, "background_threshold": background_threshold,
                "erode_size": erode_size, "post_process_mask": post_process_mask}
        }}]
    })
}

#[derive(Default)]
struct Buffers {
    request: Vec<u8>,
    response: Vec<u8>,
}

impl Buffers {
    fn allocate(&mut self, size: usize) -> Option<*mut u8> {
        if size == 0 || size > MAX_JSON_BYTES {
            return None;
        }
        if size > self.request.len() {
            self.request
                .try_reserve_exact(size - self.request.len())
                .ok()?;
        }
        self.request.resize(size, 0);
        Some(self.request.as_mut_ptr())
    }

    fn handle(&mut self, pointer: *const u8, size: usize) -> Option<&[u8]> {
        if pointer != self.request.as_ptr()
            || size == 0
            || size != self.request.len()
            || size > MAX_JSON_BYTES
        {
            return None;
        }
        let request = serde_json::from_slice::<Value>(self.request.get(..size)?);
        let response = match request {
            Ok(request) => handle(&request),
            Err(_) => {
                json!({"state": null, "message": "Invalid event request JSON.", "commands": []})
            }
        };
        self.response.clear();
        serde_json::to_writer(LimitedWriter(&mut self.response), &response).ok()?;
        Some(&self.response)
    }
}

struct LimitedWriter<'a>(&'a mut Vec<u8>);

impl Write for LimitedWriter<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let length = self
            .0
            .len()
            .checked_add(bytes.len())
            .ok_or(io::ErrorKind::InvalidData)?;
        if length > MAX_JSON_BYTES {
            return Err(io::ErrorKind::InvalidData.into());
        }
        self.0
            .try_reserve(bytes.len())
            .map_err(|_| io::Error::from(io::ErrorKind::OutOfMemory))?;
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

static BUFFERS: Mutex<Buffers> = Mutex::new(Buffers {
    request: Vec::new(),
    response: Vec::new(),
});

fn packed(bytes: &[u8]) -> u64 {
    let Ok(pointer) = u32::try_from(bytes.as_ptr() as usize) else {
        return 0;
    };
    let Ok(length) = u32::try_from(bytes.len()) else {
        return 0;
    };
    (u64::from(length) << 32) | u64::from(pointer)
}

// These attributes export ABI symbols only; there are no unsafe pointer dereferences.
#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn pce_api_version() -> u32 {
    1
}

#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn pce_manifest() -> u64 {
    packed(MANIFEST.as_bytes())
}

#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn pce_alloc(size: u32) -> *mut u8 {
    let Ok(mut buffers) = BUFFERS.lock() else {
        return std::ptr::null_mut();
    };
    buffers
        .allocate(size as usize)
        .unwrap_or(std::ptr::null_mut())
}

#[allow(unsafe_code)]
#[unsafe(no_mangle)]
pub extern "C" fn pce_handle(pointer: *const u8, size: u32) -> u64 {
    let Ok(mut buffers) = BUFFERS.lock() else {
        return 0;
    };
    buffers.handle(pointer, size as usize).map_or(0, packed)
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    fn request() -> Value {
        json!({"event":"remove","document":{"id":1,"width":40,"height":30,"revision":0},"values":{},"state":{"saved":1}})
    }

    fn assert_rejected(request: &Value) {
        let response = handle(request);
        assert_eq!(response["commands"], json!([]));
        assert_eq!(
            response["state"],
            request.get("state").unwrap_or(&Value::Null).clone()
        );
        assert!(
            response["message"]
                .as_str()
                .is_some_and(|message| !message.is_empty())
        );
    }

    #[test]
    fn identity_permission_controls_and_defaults_match_the_general_job() {
        let manifest: Value = serde_json::from_str(MANIFEST).unwrap();
        assert_eq!(manifest["id"], "org.photocraft.rembg");
        assert_eq!(manifest["name"], "Rembg Background Removal");
        assert_eq!(manifest["version"], "1.1.0");
        assert_eq!(
            manifest["permissions"],
            json!({"documentRead":true,"commands":["plugin.processImage","plugin.runTask"]})
        );
        assert_eq!(manifest["panel"]["preview"], true);
        assert_eq!(
            manifest["panel"]["buttons"],
            json!([{"id":"remove","label":"Generate preview"},
                {"id":"model_status","label":"Check model status"},
                {"id":"model_download","label":"Download selected model"},
                {"id":"model_remove","label":"Remove downloaded model"}])
        );
        let defaults = manifest["panel"]["fields"]
            .as_array()
            .unwrap()
            .iter()
            .map(|field| {
                (
                    field["id"].as_str().unwrap().to_owned(),
                    field["default"].clone(),
                )
            })
            .collect::<serde_json::Map<_, _>>();
        let mut input = request();
        let response = handle(&input);
        input["values"] = json!(defaults);
        assert_eq!(handle(&input), response);
        assert_eq!(response["state"], json!({"saved":1,"runs":1}));
        assert_eq!(
            response["commands"],
            json!([{"command":"plugin.processImage","params":{
                "processor":"native","width":40,"height":30,"preview":true,
                "options":{"model":"birefnet-general-lite","output":"foreground","alpha_matting":false,
                    "foreground_threshold":240,"background_threshold":10,"erode_size":10,"post_process_mask":false}
            }}])
        );
        assert!(response["commands"][0]["params"].get("id").is_none());
    }

    #[test]
    fn every_model_and_result_maps_to_its_own_worker_option() {
        let manifest: Value = serde_json::from_str(MANIFEST).unwrap();
        assert_eq!(
            manifest["panel"]["fields"][0]["options"],
            json!(
                model_choices()
                    .unwrap()
                    .iter()
                    .map(|(label, _)| label)
                    .collect::<Vec<_>>()
            )
        );
        assert_eq!(
            manifest["panel"]["fields"][1]["options"],
            json!(OUTPUTS.iter().map(|(label, _)| label).collect::<Vec<_>>())
        );
        for (label, model) in model_choices().unwrap() {
            for (choice, output) in OUTPUTS {
                let mut input = request();
                input["values"] = json!({"model":label,"output":choice});
                let response = handle(&input);
                assert_eq!(response["commands"][0]["params"]["options"]["model"], model);
                assert_eq!(
                    response["commands"][0]["params"]["options"]["output"],
                    *output
                );
                assert_eq!(response["commands"][0]["params"]["width"], 40);
                assert_eq!(response["commands"][0]["params"]["height"], 30);
            }
        }
    }

    #[test]
    fn model_tasks_need_no_document_and_preserve_image_run_state() {
        for (event, action) in [
            ("model_status", "status"),
            ("model_download", "download"),
            ("model_remove", "remove"),
        ] {
            for (label, id) in model_choices().unwrap() {
                let input = json!({"event":event,"document":null,"values":{"model":label,
                    "alpha_matting":true,"foreground_threshold":0,"background_threshold":255},"state":{"runs":7,"saved":true}});
                let response = handle(&input);
                assert_eq!(response["state"], input["state"]);
                assert_eq!(
                    response["commands"],
                    json!([{"command":"plugin.runTask","params":{
                    "options":{"action":action,"model":id}}}])
                );
                assert!(response["commands"][0]["params"].get("id").is_none());
            }
            let mut invalid =
                json!({"event":event,"values":{"model":"arbitrary-url"},"state":{"runs":7}});
            assert_rejected(&invalid);
            invalid["values"] = json!({"path":"elsewhere"});
            assert_rejected(&invalid);
        }
    }

    #[test]
    fn every_model_has_a_short_explanation_and_unique_valid_choice() {
        let choices = model_choices().unwrap();
        assert!(choices.len() > 2 && choices.len() <= 32);
        let labels = choices
            .iter()
            .map(|(label, _)| label)
            .collect::<std::collections::BTreeSet<_>>();
        let ids = choices
            .iter()
            .map(|(_, id)| id)
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(labels.len(), choices.len());
        assert_eq!(ids.len(), choices.len());
        for (label, _) in choices {
            assert!(label.contains(": ") && label.chars().count() <= 128);
        }
    }

    #[test]
    fn matting_thresholds_erosion_and_postprocessing_are_explicit_and_bounded() {
        for erode in [0, 10, 50] {
            let mut input = request();
            input["values"] = json!({"alpha_matting":true,"foreground_threshold":255,
                "background_threshold":0,"erode_size":erode,"post_process_mask":true});
            let response = handle(&input);
            let options = &response["commands"][0]["params"]["options"];
            assert_eq!(options["alpha_matting"], true);
            assert_eq!(options["foreground_threshold"], 255);
            assert_eq!(options["background_threshold"], 0);
            assert_eq!(options["erode_size"], erode);
            assert_eq!(options["post_process_mask"], true);
        }
        for values in [
            json!({"foreground_threshold":256}),
            json!({"foreground_threshold":-1}),
            json!({"background_threshold":256}),
            json!({"background_threshold":240}),
            json!({"foreground_threshold":10,"background_threshold":10}),
            json!({"erode_size":51}),
            json!({"erode_size":1.5}),
            json!({"erode_size":-1}),
            json!({"alpha_matting":"true"}),
            json!({"post_process_mask":1}),
            json!({"model":"unknown"}),
            json!({"output":"unknown"}),
            json!({"model":false}),
            json!({"output":null}),
            json!({"runtime":"elsewhere"}),
        ] {
            let mut input = request();
            input["values"] = values;
            assert_rejected(&input);
        }
    }

    #[test]
    fn dimensions_and_matting_have_separate_exact_limits() {
        for (width, height) in [(32_000u64, 1_000u64), (32_768, 1), (2_000, 2_000)] {
            let mut input = request();
            input["document"]["width"] = json!(width);
            input["document"]["height"] = json!(height);
            assert_eq!(handle(&input)["commands"].as_array().unwrap().len(), 1);
        }
        for (width, height) in [
            (0, 1),
            (1, 0),
            (32_769, 1),
            (32_000, 1_001),
            (u64::MAX, u64::MAX),
        ] {
            let mut input = request();
            input["document"]["width"] = json!(width);
            input["document"]["height"] = json!(height);
            assert_rejected(&input);
        }
        let mut input = request();
        input["document"]["width"] = json!(2_000);
        input["document"]["height"] = json!(2_000);
        input["values"]["alpha_matting"] = json!(true);
        assert_eq!(handle(&input)["commands"].as_array().unwrap().len(), 1);
        input["document"]["width"] = json!(2_001);
        assert_rejected(&input);
        assert!(
            handle(&input)["message"]
                .as_str()
                .unwrap()
                .contains("4 megapixels")
        );
        input["values"]["alpha_matting"] = json!(false);
        assert_eq!(handle(&input)["commands"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn malformed_events_and_documents_never_process_or_change_state() {
        for input in [
            Value::Null,
            json!([]),
            json!({}),
            json!({"event":"unknown"}),
            json!({"event":"remove","document":null,"values":{}}),
            json!({"event":"remove","document":{"width":1},"values":{}}),
            json!({"event":"remove","document":{"width":"1","height":1},"values":{}}),
        ] {
            assert_rejected(&input);
        }
        for values in [json!(null), json!([]), json!(false)] {
            let mut input = request();
            input["values"] = values;
            assert_rejected(&input);
        }
        let mut input = request();
        input["path"] = json!("another-plugin");
        assert_rejected(&input);
    }

    #[test]
    fn abi_storage_rejects_bad_lengths_pointers_and_json_without_dereferencing() {
        let mut buffers = Buffers::default();
        assert!(buffers.allocate(0).is_none());
        assert!(buffers.allocate(MAX_JSON_BYTES + 1).is_none());
        let pointer = buffers.allocate(2).unwrap();
        assert!(buffers.handle(std::ptr::null(), 2).is_none());
        assert!(buffers.handle(pointer, 1).is_none());
        buffers.request.copy_from_slice(b"{!");
        let response: Value = serde_json::from_slice(buffers.handle(pointer, 2).unwrap()).unwrap();
        assert_eq!(response["commands"], json!([]));
    }

    #[test]
    fn response_writer_is_bounded() {
        let mut bytes = Vec::new();
        let mut writer = LimitedWriter(&mut bytes);
        writer.write_all(&vec![b'x'; MAX_JSON_BYTES]).unwrap();
        assert!(writer.write_all(b"x").is_err());
        assert_eq!(bytes.len(), MAX_JSON_BYTES);
    }
}
