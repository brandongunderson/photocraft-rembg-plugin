//! This native supervisor belongs entirely to the installed rembg plugin.
#![forbid(unsafe_code)]
pub mod protocol;
pub mod runtime;
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
pub fn error(message: impl Into<String>) -> Box<dyn std::error::Error + Send + Sync> {
    std::io::Error::other(message.into()).into()
}
