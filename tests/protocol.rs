use photocraft_rembg_plugin::protocol;
use serde_json::{Value, json};
fn request(root: &std::path::Path) -> Value {
    json!({"apiVersion":1,"input":root.join("input.png"),"output":root.join("output.png"),"options":{},"outputSize":{"width":3,"height":2},"colorSpace":"srgb"})
}
fn parse(value: &Value) -> photocraft_rembg_plugin::Result<protocol::Job> {
    protocol::parse_job(serde_json::to_vec(value).unwrap().as_slice())
}
#[test]
fn model_tasks_have_a_strict_non_image_protocol() {
    let root = tempfile::tempdir().unwrap();
    let valid = json!({"apiVersion":1,"output":root.path().join("task-result.json"),"options":{"action":"status","model":"birefnet-portrait"}});
    let parse_task =
        |value: &Value| protocol::parse_task(serde_json::to_vec(value).unwrap().as_slice());
    assert_eq!(
        parse_task(&valid).unwrap().options.action,
        protocol::TaskAction::Status
    );
    for (key, value) in [
        ("apiVersion", json!(true)),
        ("apiVersion", json!(2)),
        ("output", json!("relative.json")),
        ("input", json!("unexpected.png")),
        ("options", json!({"action":"execute","model":"u2net"})),
        ("options", json!({"action":"download","model":"../u2net"})),
        (
            "options",
            json!({"action":"remove","model":"silueta","url":"https://example.com/weights"}),
        ),
    ] {
        let mut invalid = valid.clone();
        invalid[key] = value;
        assert!(parse_task(&invalid).is_err(), "{invalid}");
    }
    std::fs::write(root.path().join("task-result.json"), b"existing").unwrap();
    assert!(parse_task(&valid).is_err());
    assert!(protocol::parse_task(vec![b' '; 16385].as_slice()).is_err());
}
#[test]
fn generic_job_defaults_and_strict_options() {
    let root = tempfile::tempdir().unwrap();
    let valid = request(root.path());
    let job = parse(&valid).unwrap();
    assert_eq!(job.options.model, "birefnet-general-lite");
    assert_eq!(job.options.foreground_threshold, 240);
    assert!(!job.options.alpha_matting);
    for (key, value) in [
        ("apiVersion", json!(2)),
        ("colorSpace", json!("display-p3")),
        ("input", json!("relative.png")),
        ("unknown", json!(true)),
        ("outputSize", json!({"width":0,"height":1})),
    ] {
        let mut invalid = valid.clone();
        invalid[key] = value;
        assert!(parse(&invalid).is_err());
    }
    for (key, value) in [
        ("model", json!("bria-rmbg")),
        ("model", json!("../u2netp")),
        ("output", json!("other")),
        ("alpha_matting", json!(1)),
        ("foreground_threshold", json!(256)),
        ("background_threshold", json!(240)),
        ("erode_size", json!(51)),
        ("unknown", json!(true)),
    ] {
        let mut invalid = valid.clone();
        invalid["options"][key] = value;
        assert!(parse(&invalid).is_err(), "{invalid}");
    }
    std::fs::write(root.path().join("output.png"), b"existing").unwrap();
    assert!(parse(&valid).is_err());
    assert!(protocol::parse_job(vec![b' '; 16385].as_slice()).is_err());
}
#[test]
fn bounds_and_matting_limits_are_distinct() {
    assert!(protocol::check_dimensions(8000, 4000, false).is_ok());
    assert!(protocol::check_dimensions(8001, 4000, false).is_err());
    assert!(protocol::check_dimensions(2000, 2000, true).is_ok());
    assert!(protocol::check_dimensions(2001, 2000, true).is_err());
    assert!(protocol::check_dimensions(32769, 1, false).is_err());
}
#[test]
fn header_rejects_wrong_depth_dimensions_and_corruption() {
    let root = tempfile::tempdir().unwrap();
    let mut bytes = b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR".to_vec();
    bytes.extend_from_slice(&3u32.to_be_bytes());
    bytes.extend_from_slice(&2u32.to_be_bytes());
    bytes.extend_from_slice(&[8, 6, 0, 0, 0]);
    bytes.extend_from_slice(&crc32fast::hash(&bytes[12..29]).to_be_bytes());
    let path = root.path().join("input.png");
    std::fs::write(&path, &bytes).unwrap();
    let mut job = parse(&request(root.path())).unwrap();
    protocol::validate_source(&job).unwrap();
    job.output_size.width = 6;
    assert!(protocol::validate_source(&job).is_err());
    job.output_size.width = 3;
    bytes[24] = 16;
    std::fs::write(&path, &bytes).unwrap();
    assert!(protocol::validate_source(&job).is_err());
    bytes[24] = 8;
    bytes[32] ^= 1;
    std::fs::write(&path, bytes).unwrap();
    assert!(protocol::validate_source(&job).is_err());
}
