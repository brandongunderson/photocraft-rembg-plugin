use crate::{Result, error};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs::{File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicBool, Ordering},
};

const MAX_ARCHIVE: u64 = 256 << 20;
const MAX_MEMBER: u64 = 256 << 20;
const MAX_EXPANDED: u64 = 896 << 20;
const MAX_FILES: usize = 20_000;

pub fn cancelled(cancel: &AtomicBool) -> Result<()> {
    if cancel.load(Ordering::Relaxed) {
        Err(error("Cancelled. No output was saved."))
    } else {
        Ok(())
    }
}
pub fn sha256_file(path: &Path, max: u64, cancel: &AtomicBool) -> Result<String> {
    let file = File::open(path)?;
    if file.metadata()?.len() > max {
        return Err(error("Bundled asset exceeds the permitted size."));
    }
    let mut reader = file.take(max + 1);
    let mut hash = Sha256::new();
    let mut total = 0u64;
    let mut buffer = [0u8; 65536];
    loop {
        cancelled(cancel)?;
        let n = reader.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        total += n as u64;
        if total > max {
            return Err(error("Bundled asset exceeds the permitted size."));
        }
        hash.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeInfo {
    pub api_version: u32,
    pub archive: String,
    pub sha256: String,
    pub expanded_bytes: u64,
    pub file_count: usize,
    pub python: String,
}
pub fn read_runtime(root: &Path) -> Result<RuntimeInfo> {
    let info: RuntimeInfo =
        serde_json::from_reader(File::open(root.join("runtime/runtime.json"))?.take(65537))?;
    if info.api_version != 1
        || info.archive != "python-runtime.zip"
        || info.python != "python.exe"
        || info.sha256.len() != 64
        || !info.sha256.bytes().all(|c| c.is_ascii_hexdigit())
        || info.expanded_bytes == 0
        || info.expanded_bytes > MAX_EXPANDED
        || info.file_count == 0
        || info.file_count > MAX_FILES
    {
        return Err(error("Invalid bundled Python runtime manifest."));
    }
    Ok(info)
}
fn safe_relative(name: &str) -> Result<PathBuf> {
    if name.is_empty() || name.len() > 1024 || name.contains(['\\', ':', '\0']) {
        return Err(error("Unsafe runtime archive path."));
    }
    let mut path = PathBuf::new();
    for component in name.split('/') {
        let base = component
            .split('.')
            .next()
            .unwrap_or("")
            .to_ascii_uppercase();
        if component.is_empty()
            || component == "."
            || component == ".."
            || component.ends_with(['.', ' '])
            || component.bytes().any(|c| c < 32 || b"<>\"|?*".contains(&c))
            || ["CON", "PRN", "AUX", "NUL"].contains(&base.as_str())
            || (base.len() == 4
                && (base.starts_with("COM") || base.starts_with("LPT"))
                && base.as_bytes()[3].is_ascii_digit())
        {
            return Err(error("Unsafe runtime archive path."));
        }
        path.push(component);
    }
    Ok(path)
}
// The pinned producer writes a normal single-disk ZIP without a comment. Bound
// central-directory allocation before giving the archive to the ZIP reader.
fn preflight_zip(file: &mut File, info: &RuntimeInfo) -> Result<()> {
    let size = file.metadata()?.len();
    if !(22..=MAX_ARCHIVE).contains(&size) {
        return Err(error("Invalid runtime archive size."));
    }
    file.seek(SeekFrom::End(-22))?;
    let mut end = [0u8; 22];
    file.read_exact(&mut end)?;
    let count = u16::from_le_bytes([end[10], end[11]]) as usize;
    let directory_size = u32::from_le_bytes(end[12..16].try_into()?) as u64;
    let directory_offset = u32::from_le_bytes(end[16..20].try_into()?) as u64;
    if &end[..4] != b"PK\x05\x06"
        || end[4..8] != [0; 4]
        || end[8..10] != end[10..12]
        || end[20..22] != [0; 2]
        || count == 0
        || count > MAX_FILES
        || count != info.file_count
        || directory_size > 20 << 20
        || directory_offset + directory_size + 22 != size
    {
        return Err(error(
            "Runtime must be a bounded single-disk ZIP without ZIP64 or archive comments.",
        ));
    }
    file.seek(SeekFrom::Start(0))?;
    Ok(())
}
pub fn extract_runtime(
    root: &Path,
    destination: &Path,
    info: &RuntimeInfo,
    cancel: &AtomicBool,
    progress: &dyn Fn(f32, &str),
) -> Result<PathBuf> {
    if std::fs::read_dir(destination)?.next().is_some() {
        return Err(error(
            "Runtime extraction requires a new empty private directory.",
        ));
    }
    let archive_path = root.join("runtime").join(&info.archive);
    if sha256_file(&archive_path, MAX_ARCHIVE, cancel)? != info.sha256.to_ascii_lowercase() {
        return Err(error(
            "The bundled Python runtime checksum does not match. Reinstall the complete plugin.",
        ));
    }
    let mut file = File::open(archive_path)?;
    preflight_zip(&mut file, info)?;
    let mut archive = zip::ZipArchive::new(file)?;
    if archive.len() > MAX_FILES || archive.len() != info.file_count {
        return Err(error("Runtime file count does not match its manifest."));
    }
    let mut names = BTreeSet::new();
    let mut expanded = 0u64;
    // Validate every central entry before creating any file in the new private directory.
    for i in 0..archive.len() {
        cancelled(cancel)?;
        let member = archive.by_index(i)?;
        safe_relative(&member.name()?)?;
        if !member.is_file()
            || member.enclosed_name().is_none()
            || member.encrypted()
            || !matches!(
                member.compression(),
                zip::CompressionMethod::Stored | zip::CompressionMethod::Deflated
            )
            || member
                .unix_mode()
                .is_some_and(|mode| mode & 0o170000 != 0 && mode & 0o170000 != 0o100000)
            || member.size() > MAX_MEMBER
            || !names.insert(member.name()?.to_ascii_lowercase())
        {
            return Err(error(
                "Invalid, duplicate or unsupported runtime archive member.",
            ));
        }
        expanded = expanded
            .checked_add(member.size())
            .ok_or_else(|| error("Runtime size overflow."))?;
        if expanded > MAX_EXPANDED {
            return Err(error("Expanded Python runtime exceeds its limit."));
        }
    }
    if expanded != info.expanded_bytes {
        return Err(error("Runtime expanded size does not match its manifest."));
    }
    let mut buffer = [0u8; 65536];
    for i in 0..archive.len() {
        cancelled(cancel)?;
        let mut member = archive.by_index(i)?;
        let path = destination.join(safe_relative(&member.name()?)?);
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let mut output = OpenOptions::new().write(true).create_new(true).open(path)?;
        let mut total = 0u64;
        loop {
            cancelled(cancel)?;
            let n = member.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            total += n as u64;
            if total > member.size() || total > MAX_MEMBER {
                return Err(error("Runtime member expands beyond its declared size."));
            }
            output.write_all(&buffer[..n])?;
        }
        if total != member.size() {
            return Err(error("Runtime member is truncated."));
        }
        progress(
            2.0 + 16.0 * (i + 1) as f32 / info.file_count as f32,
            "Preparing private Python runtime…",
        );
    }
    let python = destination.join(&info.python);
    if !python.is_file() {
        return Err(error("Bundled Python executable is missing."));
    }
    cancelled(cancel)?;
    Ok(python)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn paths_reject_windows_aliases_and_traversal() {
        for name in [
            "../file",
            "/root",
            "a//b",
            "a\\b",
            "C:/a",
            "nul.txt",
            "folder/COM1.dll",
            "x.",
            "a ",
            "a/b:stream",
            "a/./b",
        ] {
            assert!(safe_relative(name).is_err(), "{name}");
        }
        for name in [
            "Lib/site-packages/numpy-2.5.dist-info/METADATA",
            "python313.zip",
            "a/b+c.py",
        ] {
            assert!(safe_relative(name).is_ok());
        }
    }
    fn fixture(files: &[(&str, &[u8])]) -> (tempfile::TempDir, RuntimeInfo) {
        let root = tempfile::tempdir().unwrap();
        std::fs::create_dir(root.path().join("runtime")).unwrap();
        let path = root.path().join("runtime/python-runtime.zip");
        let mut zip = zip::ZipWriter::new(File::create(&path).unwrap());
        for (name, data) in files {
            zip.start_file(
                *name,
                zip::write::SimpleFileOptions::default()
                    .compression_method(zip::CompressionMethod::Stored),
            )
            .unwrap();
            zip.write_all(data).unwrap();
        }
        zip.finish().unwrap();
        let info = RuntimeInfo {
            api_version: 1,
            archive: "python-runtime.zip".into(),
            sha256: sha256_file(&path, MAX_ARCHIVE, &AtomicBool::new(false)).unwrap(),
            expanded_bytes: files.iter().map(|(_, data)| data.len() as u64).sum(),
            file_count: files.len(),
            python: "python.exe".into(),
        };
        (root, info)
    }
    #[test]
    fn runtime_keeps_empty_python_files_and_rejects_bad_metadata_or_cancel() {
        let (root, mut info) =
            fixture(&[("python.exe", b"MZprivate"), ("Lib/empty/__init__.py", b"")]);
        let target = tempfile::tempdir().unwrap();
        extract_runtime(
            root.path(),
            target.path(),
            &info,
            &AtomicBool::new(false),
            &|_, _| {},
        )
        .unwrap();
        assert_eq!(
            std::fs::read(target.path().join("Lib/empty/__init__.py")).unwrap(),
            b""
        );
        assert!(
            extract_runtime(
                root.path(),
                target.path(),
                &info,
                &AtomicBool::new(false),
                &|_, _| {}
            )
            .is_err()
        );
        let target = tempfile::tempdir().unwrap();
        assert!(
            extract_runtime(
                root.path(),
                target.path(),
                &info,
                &AtomicBool::new(true),
                &|_, _| {}
            )
            .is_err()
        );
        info.expanded_bytes += 1;
        assert!(
            extract_runtime(
                root.path(),
                target.path(),
                &info,
                &AtomicBool::new(false),
                &|_, _| {}
            )
            .is_err()
        );
        assert_eq!(std::fs::read_dir(target.path()).unwrap().count(), 0);
    }
    #[test]
    fn runtime_rejects_traversal_aliases_and_crc_corruption() {
        for names in [
            ["python.exe", "../escape"],
            ["python.exe", "NUL.txt"],
            ["python.exe", "PYTHON.EXE"],
        ] {
            let (root, info) = fixture(&[(names[0], b"MZ"), (names[1], b"other")]);
            let target = tempfile::tempdir().unwrap();
            assert!(
                extract_runtime(
                    root.path(),
                    target.path(),
                    &info,
                    &AtomicBool::new(false),
                    &|_, _| {}
                )
                .is_err()
            );
            assert_eq!(std::fs::read_dir(target.path()).unwrap().count(), 0);
        }
        let (root, mut info) = fixture(&[("python.exe", b"MZprivatebody")]);
        let path = root.path().join("runtime/python-runtime.zip");
        let mut bytes = std::fs::read(&path).unwrap();
        let offset = bytes
            .windows(13)
            .position(|s| s == b"MZprivatebody")
            .unwrap();
        bytes[offset] ^= 1;
        std::fs::write(&path, bytes).unwrap();
        info.sha256 = sha256_file(&path, MAX_ARCHIVE, &AtomicBool::new(false)).unwrap();
        let target = tempfile::tempdir().unwrap();
        assert!(
            extract_runtime(
                root.path(),
                target.path(),
                &info,
                &AtomicBool::new(false),
                &|_, _| {}
            )
            .is_err()
        );
    }
}
