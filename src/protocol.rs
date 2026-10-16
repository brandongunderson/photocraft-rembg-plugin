use crate::{Result, error};
use serde::{Deserialize, Serialize};
use std::{io::Read, path::PathBuf};

pub const MAX_PIXELS: u64 = 32_000_000;
pub const MAX_MATTING_PIXELS: u64 = 4_000_000;
pub const MODELS: [&str; 13] = [
    "birefnet-general-lite",
    "u2netp",
    "u2net",
    "u2net_human_seg",
    "silueta",
    "isnet-general-use",
    "isnet-anime",
    "birefnet-general",
    "birefnet-portrait",
    "birefnet-dis",
    "birefnet-hrsod",
    "birefnet-cod",
    "birefnet-massive",
];

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum TaskAction {
    Status,
    Download,
    Remove,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TaskOptions {
    pub action: TaskAction,
    pub model: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Task {
    pub api_version: u32,
    pub options: TaskOptions,
    pub output: PathBuf,
}

pub fn parse_task(reader: impl Read) -> Result<Task> {
    let mut bytes = Vec::new();
    reader.take(16385).read_to_end(&mut bytes)?;
    if bytes.len() > 16384 {
        return Err(error("Task request exceeds 16 KiB."));
    }
    let task: Task = serde_json::from_slice(&bytes)?;
    if task.api_version != 1
        || !task.output.is_absolute()
        || !MODELS.contains(&task.options.model.as_str())
    {
        return Err(error("Unsupported model task, model or output path."));
    }
    if task.output.try_exists()? {
        return Err(error("Output already exists; refusing to overwrite it."));
    }
    Ok(task)
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Output {
    #[default]
    Foreground,
    Background,
    Mask,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct Options {
    pub model: String,
    pub output: Output,
    pub alpha_matting: bool,
    pub foreground_threshold: u8,
    pub background_threshold: u8,
    pub erode_size: u8,
    pub post_process_mask: bool,
}
impl Default for Options {
    fn default() -> Self {
        Self {
            model: MODELS[0].into(),
            output: Output::Foreground,
            alpha_matting: false,
            foreground_threshold: 240,
            background_threshold: 10,
            erode_size: 10,
            post_process_mask: false,
        }
    }
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct OutputSize {
    pub width: u32,
    pub height: u32,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Job {
    pub api_version: u32,
    pub input: PathBuf,
    pub output: PathBuf,
    pub options: Options,
    pub output_size: OutputSize,
    pub color_space: String,
}
pub fn check_dimensions(width: u32, height: u32, matting: bool) -> Result<()> {
    let pixels = u64::from(width) * u64::from(height);
    if width == 0 || height == 0 || width > 32768 || height > 32768 || pixels > MAX_PIXELS {
        return Err(error(
            "Rembg supports images up to 32 megapixels and 32,768 pixels per side.",
        ));
    }
    if matting && pixels > MAX_MATTING_PIXELS {
        return Err(error(
            "Alpha matting supports images up to 4 megapixels. Disable alpha matting or use a smaller image.",
        ));
    }
    Ok(())
}
pub fn parse_job(reader: impl Read) -> Result<Job> {
    let mut bytes = Vec::new();
    reader.take(16385).read_to_end(&mut bytes)?;
    if bytes.len() > 16384 {
        return Err(error("Job request exceeds 16 KiB."));
    }
    let job: Job = serde_json::from_slice(&bytes)?;
    if job.api_version != 1
        || job.color_space != "srgb"
        || !job.input.is_absolute()
        || !job.output.is_absolute()
        || job.input == job.output
    {
        return Err(error(
            "Unsupported image protocol, color space or image paths.",
        ));
    }
    if !MODELS.contains(&job.options.model.as_str())
        || job.options.background_threshold >= job.options.foreground_threshold
        || job.options.erode_size > 50
    {
        return Err(error("Unknown model or invalid alpha-matting settings."));
    }
    check_dimensions(
        job.output_size.width,
        job.output_size.height,
        job.options.alpha_matting,
    )?;
    if job.output.try_exists()? {
        return Err(error("Output already exists; refusing to overwrite it."));
    }
    Ok(job)
}
pub fn validate_source(job: &Job) -> Result<()> {
    let mut header = [0u8; 33];
    std::fs::File::open(&job.input)?.read_exact(&mut header)?;
    if &header[..8] != b"\x89PNG\r\n\x1a\n"
        || header[8..12] != 13u32.to_be_bytes()
        || &header[12..16] != b"IHDR"
        || header[24] != 8
        || header[25] != 6
        || header[26] != 0
        || header[27] != 0
        || header[28] > 1
        || crc32fast::hash(&header[12..29]).to_be_bytes() != header[29..33]
    {
        return Err(error(
            "The plugin requires a valid 8-bit RGBA sRGB PNG input.",
        ));
    }
    let width = u32::from_be_bytes(header[16..20].try_into()?);
    let height = u32::from_be_bytes(header[20..24].try_into()?);
    check_dimensions(width, height, job.options.alpha_matting)?;
    if (width, height) != (job.output_size.width, job.output_size.height) {
        return Err(error(
            "Rembg keeps the original dimensions; outputSize must match the source.",
        ));
    }
    Ok(())
}
