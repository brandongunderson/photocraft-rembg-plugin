use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};

use crate::{ApiError, Capabilities, Contributions, ErrorCode, MAX_DESCRIPTOR_BYTES, PANEL_API_VERSION, Result, event_identifier, identifier, invalid, label};

/// Complete independent panel-2 descriptor. Legacy manifests retain their original reader.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Descriptor {
    #[cfg_attr(feature = "schema", schemars(range(min = 2, max = 2)))]
    pub api_version: u32,
    #[cfg_attr(feature = "schema", schemars(length(min = 1, max = 64), regex(pattern = "^[a-z0-9][a-z0-9._-]*$")))]
    pub id: String,
    #[cfg_attr(feature = "schema", schemars(length(min = 1, max = 64)))]
    pub name: String,
    #[cfg_attr(feature = "schema", schemars(length(max = 32)))]
    pub version: String,
    #[serde(default)]
    #[cfg_attr(feature = "schema", schemars(length(max = 128)))]
    pub author: String,
    #[serde(default)]
    #[cfg_attr(feature = "schema", schemars(length(max = 1024)))]
    pub description: String,
    pub permissions: Permissions,
    pub panel: Panel,
    #[serde(default, skip_serializing_if = "Capabilities::is_empty")]
    pub capabilities: Capabilities,
    #[serde(default, skip_serializing_if = "Contributions::is_empty")]
    pub contributes: Contributions,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Permissions {
    #[serde(default)]
    pub document_read: bool,
    #[serde(default)]
    #[cfg_attr(feature = "schema", schemars(length(max = 128)))]
    pub commands: Vec<String>,
}

#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Panel {
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub preview: bool,
    #[serde(default)]
    #[cfg_attr(feature = "schema", schemars(length(max = 32)))]
    pub fields: Vec<Field>,
    #[cfg_attr(feature = "schema", schemars(length(max = 16)))]
    pub buttons: Vec<Button>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub struct Field {
    #[cfg_attr(feature = "schema", schemars(length(min = 1, max = 64), regex(pattern = "^[A-Za-z0-9][A-Za-z0-9_]*$")))]
    pub id: String,
    #[cfg_attr(feature = "schema", schemars(length(min = 1, max = 128)))]
    pub label: String,
    #[serde(flatten)]
    pub spec: Parameter,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(deny_unknown_fields)]
pub struct Button {
    #[cfg_attr(feature = "schema", schemars(length(min = 1, max = 64), regex(pattern = "^[A-Za-z0-9][A-Za-z0-9_]*$")))]
    pub id: String,
    #[cfg_attr(feature = "schema", schemars(length(min = 1, max = 128)))]
    pub label: String,
}

/// Same declarative controls as panel-1; no host UI implementation is imported.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(tag = "type", rename_all = "camelCase", deny_unknown_fields)]
pub enum Parameter {
    Number {
        min: f64,
        max: f64,
        default: f64,
    },
    Int {
        #[serde(default = "int_min")]
        min: i64,
        #[serde(default = "int_max")]
        max: i64,
        #[serde(default)]
        default: i64,
    },
    Bool {
        #[serde(default)]
        default: bool,
    },
    Choice {
        #[cfg_attr(feature = "schema", schemars(length(min = 1, max = 64)))]
        options: Vec<String>,
        #[serde(default)]
        default: Option<String>,
    },
}

fn int_min() -> i64 {
    -1_000_000
}

fn int_max() -> i64 {
    1_000_000
}

impl Descriptor {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        if bytes.len() > MAX_DESCRIPTOR_BYTES {
            return Err(ApiError::new(ErrorCode::LimitExceeded, "descriptor exceeds 64 KiB"));
        }
        let descriptor: Self = serde_json::from_slice(bytes).map_err(|e| ApiError::new(ErrorCode::InvalidJson, e.to_string()))?;
        descriptor.validate()?;
        Ok(descriptor)
    }

    pub fn validate(&self) -> Result<()> {
        if self.api_version != PANEL_API_VERSION {
            return Err(ApiError::at(ErrorCode::IncompatibleApi, "apiVersion", "this descriptor requires panel API 2"));
        }
        if !identifier(&self.id, 64) || !label(&self.name, 64) {
            return Err(invalid("id/name", "plugin ID or name is invalid"));
        }
        if self.version.len() > 32 || self.author.len() > 128 || self.description.len() > 1024 {
            return Err(invalid("version/author/description", "plugin metadata exceeds its byte budget"));
        }
        if self.permissions.commands.len() > 128 {
            return Err(invalid("permissions.commands", "at most 128 command permissions are allowed"));
        }
        let mut command_ids = BTreeSet::new();
        for command in &self.permissions.commands {
            if command.is_empty()
                || command.len() > 128
                || !command.bytes().all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
                || !command_ids.insert(command)
            {
                return Err(invalid("permissions.commands", "invalid or duplicate command permission"));
            }
        }
        self.panel.validate()?;
        if self.panel.buttons.is_empty() && self.contributes.inspectors.is_empty() {
            return Err(invalid("panel.buttons", "a panel without buttons must contribute an inspector"));
        }
        self.capabilities.validate()?;
        self.contributes.validate(&self.id)?;
        Ok(())
    }
}

impl Panel {
    pub fn validate(&self) -> Result<()> {
        if self.fields.len() > 32 || self.buttons.len() > 16 {
            return Err(invalid("panel", "panel permits at most 16 buttons and 32 fields"));
        }
        let mut ids = BTreeSet::new();
        for field in &self.fields {
            if !event_identifier(&field.id) || !label(&field.label, 128) || !ids.insert(&field.id) {
                return Err(invalid("panel.fields", "invalid or duplicate field"));
            }
            match &field.spec {
                Parameter::Number { min, max, default } => {
                    if !min.is_finite() || !max.is_finite() || !default.is_finite() || min > max {
                        return Err(invalid("panel.fields", "numeric parameter has a non-finite or reversed range"));
                    }
                }
                Parameter::Int { min, max, .. } if min > max => return Err(invalid("panel.fields", "integer parameter has a reversed range")),
                Parameter::Choice { options, default }
                    if options.is_empty()
                        || options.len() > 64
                        || options.iter().any(|option| option.is_empty() || option.contains(['|', '"']))
                        || default.as_ref().is_some_and(|value| !options.contains(value)) =>
                {
                    return Err(invalid("panel.fields", "choice parameter has invalid options or default"));
                }
                _ => {}
            }
        }
        ids.clear();
        for button in &self.buttons {
            if !event_identifier(&button.id) || !label(&button.label, 128) || !ids.insert(&button.id) {
                return Err(invalid("panel.buttons", "invalid or duplicate button"));
            }
        }
        Ok(())
    }
}
