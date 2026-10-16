#![forbid(unsafe_code)]
use photocraft_rembg_plugin::{Result, error, protocol, runtime};
use std::{
    io::Read,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};

fn progress(value: f32, message: &str) {
    eprintln!(
        "{}",
        serde_json::json!({"progress":value,"message":message})
    );
}
fn wait_child(child: &mut Child, cancel: &AtomicBool) -> Result<()> {
    let start = Instant::now();
    loop {
        if cancel.load(Ordering::Relaxed) || start.elapsed() > Duration::from_secs(40 * 60) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error(if cancel.load(Ordering::Relaxed) {
                "Cancelled. No output was saved."
            } else {
                "Rembg operation exceeded 40 minutes. No output was saved."
            }));
        }
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(_)) => {
                return Err(error(
                    "Rembg operation failed. See the preceding worker error.",
                ));
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(25)),
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e.into());
            }
        }
    }
}
fn reject_linked_directory(path: &Path) -> Result<()> {
    let info = std::fs::symlink_metadata(path)?;
    #[cfg(windows)]
    let reparse = {
        use std::os::windows::fs::MetadataExt;
        info.file_attributes() & 0x400 != 0
    };
    #[cfg(not(windows))]
    let reparse = false;
    if !info.is_dir() || info.file_type().is_symlink() || reparse {
        return Err(error(
            "The plugin model cache cannot use linked or redirected directories.",
        ));
    }
    Ok(())
}

fn cache_root() -> Result<PathBuf> {
    let base = PathBuf::from(
        std::env::var_os("LOCALAPPDATA")
            .ok_or_else(|| error("Windows local application-data directory is unavailable."))?,
    );
    if !base.is_absolute()
        || base
            .components()
            .any(|part| matches!(part, std::path::Component::ParentDir))
    {
        return Err(error(
            "The Windows local application-data path must be absolute.",
        ));
    }
    // LocalAppData supplies the user's ordinary Windows profile permissions.
    // Refuse every existing reparse point before making plugin-owned children.
    for parent in base.ancestors() {
        reject_linked_directory(parent)?;
    }
    let mut path = base;
    for component in ["PhotoCraft", "Plugins", "org.photocraft.rembg", "models"] {
        path.push(component);
        match std::fs::create_dir(&path) {
            Ok(()) => {}
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(e) => return Err(e.into()),
        }
        reject_linked_directory(&path)?;
    }
    Ok(path)
}

enum Request {
    Image(protocol::Job),
    Task(protocol::Task),
}
impl Request {
    fn output(&self) -> &Path {
        match self {
            Self::Image(job) => &job.output,
            Self::Task(task) => &task.output,
        }
    }
    fn flag(&self) -> &str {
        match self {
            Self::Image(_) => "--job",
            Self::Task(_) => "--task",
        }
    }
}

fn run() -> Result<()> {
    let mut args = std::env::args_os().skip(1);
    let flag = args
        .next()
        .ok_or_else(|| error("Expected --job or --task <absolute-request.json>."))?;
    let job_path = args.next().ok_or_else(|| error("Missing job request."))?;
    if args.next().is_some() || !Path::new(&job_path).is_absolute() {
        return Err(error("Unexpected argument or non-absolute job path."));
    }
    let request = if flag == "--job" {
        let job = protocol::parse_job(std::fs::File::open(&job_path)?)?;
        protocol::validate_source(&job)?;
        Request::Image(job)
    } else if flag == "--task" {
        Request::Task(protocol::parse_task(std::fs::File::open(&job_path)?)?)
    } else {
        return Err(error("Expected --job or --task <absolute-request.json>."));
    };
    if request.output() == Path::new(&job_path) {
        return Err(error("Request and output paths must differ."));
    }
    let cancel = Arc::new(AtomicBool::new(false));
    let lifetime = Arc::clone(&cancel);
    std::thread::Builder::new()
        .name("rembg-host-lifetime".into())
        .spawn(move || {
            let mut byte = [0u8; 1];
            let _ = std::io::stdin().read(&mut byte);
            lifetime.store(true, Ordering::Relaxed);
        })?;
    let executable = std::env::current_exe()?;
    let root = executable
        .parent()
        .ok_or_else(|| error("Cannot locate plugin installation."))?;
    let info = runtime::read_runtime(root)?;
    let private = tempfile::Builder::new()
        .prefix("photocraft-rembg-")
        .tempdir()?;
    progress(1.0, "Checking the bundled runtime…");
    let python = runtime::extract_runtime(root, private.path(), &info, &cancel, &progress)?;
    let cache = cache_root()?;
    // Stage on the cache filesystem, so verified weights publish atomically.
    // Drop this directory only after the child has been killed and reaped.
    let staging = tempfile::Builder::new()
        .prefix(".download-")
        .tempdir_in(&cache)?;
    let script = root.join(match request {
        Request::Image(_) => "python/worker.py",
        Request::Task(_) => "python/model_manager.py",
    });
    if !script.is_file() {
        return Err(error(
            "Bundled rembg worker script is missing. Reinstall the plugin.",
        ));
    }
    let mut command = Command::new(python);
    command
        .arg("-I")
        .arg("-B")
        .arg(script)
        .arg(request.flag())
        .arg(job_path)
        .arg("--cache")
        .arg(&cache)
        .current_dir(private.path())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());
    for name in [
        "NUMBA_CACHE_DIR",
        "TEMP",
        "TMP",
        "XDG_CACHE_HOME",
        "REMBG_HOME",
        "U2NET_HOME",
    ] {
        command.env(name, private.path());
    }
    command
        .env("OMP_NUM_THREADS", "4")
        .env("OPENBLAS_NUM_THREADS", "4")
        .env("NUMBA_NUM_THREADS", "4")
        .env("PYTHONNOUSERSITE", "1");
    if matches!(request, Request::Task(_)) {
        command.arg("--scratch").arg(staging.path());
    }
    let pending = request.output().with_file_name(format!(
        ".{}-pending.{}",
        private
            .path()
            .file_name()
            .ok_or_else(|| error("Missing private job name."))?
            .to_string_lossy(),
        if matches!(request, Request::Image(_)) {
            "png"
        } else {
            "json"
        },
    ));
    command.env("PHOTOCRAFT_REMBG_PENDING", &pending);
    command.env(
        "NUMBA_DISABLE_JIT",
        if matches!(&request, Request::Image(job) if job.options.alpha_matting) {
            "0"
        } else {
            "1"
        },
    );
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
        let windows = std::env::var_os("SystemRoot")
            .ok_or_else(|| error("Cannot locate Windows system libraries."))?;
        let windows = std::path::PathBuf::from(windows);
        command.env(
            "PATH",
            std::env::join_paths([private.path(), &windows.join("System32"), &windows])?,
        );
    }
    runtime::cancelled(&cancel)?;
    let mut child = command.spawn()?;
    let result = wait_child(&mut child, &cancel);
    let _ = std::fs::remove_file(pending);
    // Child is reaped before TempDir cleanup, including cancellation/host EOF.
    if result.is_err() || cancel.load(Ordering::Relaxed) {
        let _ = std::fs::remove_file(request.output());
    }
    result?;
    runtime::cancelled(&cancel)?;
    if !request.output().is_file() {
        return Err(error("Rembg worker completed without an output file."));
    }
    progress(100.0, "Result ready.");
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        let message: String = e.to_string().chars().take(2048).collect();
        eprintln!("{}", serde_json::json!({"error":message}));
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "child-process fixture, launched only by cancellation test"]
    fn child_wait_fixture() {
        std::thread::sleep(Duration::from_secs(20));
    }
    #[test]
    fn cancellation_kills_and_reaps_the_private_child() {
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args(["--ignored", "--exact", "tests::child_wait_fixture"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command.spawn().unwrap();
        let cancel = AtomicBool::new(false);
        let start = Instant::now();
        std::thread::scope(|scope| {
            scope.spawn(|| {
                std::thread::sleep(Duration::from_millis(100));
                cancel.store(true, Ordering::Relaxed);
            });
            assert!(wait_child(&mut child, &cancel).is_err());
        });
        assert!(start.elapsed() < Duration::from_secs(2));
        assert!(child.try_wait().unwrap().is_some());
    }
}
