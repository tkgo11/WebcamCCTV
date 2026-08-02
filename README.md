# WebcamCCTV

A local-first desktop webcam CCTV system comprising an independent **headless recorder** and a **Qt monitoring/configuration GUI**. It performs continuous or motion-triggered MP4 recording, keeps a bounded pre-event frame ring, records post-event footage, reconnects cameras with exponential backoff, and enforces storage retention without a cloud dependency or telemetry.

> **Privacy notice:** You are responsible for camera, workplace, privacy, wiretapping, audio-recording, notice, and consent laws. WebcamCCTV does not suppress operating-system camera indicators and must not be used for covert surveillance. Audio is deliberately not enabled in this release.

## Technology and architecture

Python 3.11, OpenCV and NumPy were chosen for portable camera/video processing; PySide6 supplies an accessible, high-DPI native desktop UI; `platformdirs` keeps mutable data in OS-appropriate locations. PyInstaller can bundle the runtime. The service and GUI are separate processes. They exchange only an atomically replaced, read-only status JSON file and stop-request marker; configuration is atomically written before the service reloads it on restart. This intentionally small local IPC surface has no listening network port.

```
src/webcamcctv/
  gui.py         Qt live preview, validated settings, lifecycle controls
  service.py     headless capture/reconnect/recording state machine
  config.py      typed versioned JSON, validation, backup/restore
  motion.py      local background-subtraction detector
  storage.py     dated files, metadata, protection, retention
  cameras.py     device discovery
  cli.py         machine-readable administration
packaging/       systemd unit and cross-platform startup installer
config/          documented sample configuration
tests/           deterministic unit tests (no physical camera required)
docs/            architecture/security and operations guide
```

Recordings use `YYYY/MM/DD/YYYYMMDD_HHMMSS_Camera.mp4` with atomic JSON sidecars containing timestamps, camera, event type and motion score. A `.protected` sibling prevents cleanup. Configuration schema v1 is illustrated in [`config/example.json`](config/example.json).

## Staged implementation

1. **Delivered foundation:** safe schema-v2 configuration, discovery/preview, independent service, continuous/motion MP4, pre/post event capture, reconnect, retention, status UI and CLI.
2. **Recording expansion:** SQLite indexing, thumbnails, schedule evaluation, privacy masks, camera controls, encoder selection, atomic interrupted-segment handling, checksummed synchronization and diagnostics export.
3. **Optional integrations:** OS-keyring secrets, AES-GCM archives, notification adapters, and dependency groups for local AI and audio pipelines.
4. **Platform delivery:** Linux/Windows startup registration, a per-user macOS LaunchAgent, cross-platform packaged archives, checksums, and release signing guidance.

The staged list is explicit because the current release does **not** claim unimplemented requested capabilities; see [Known limitations](#known-limitations).

## Install and first run

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -e .
webcamcctv-gui
```

On first run: review the privacy notice, choose a discovered camera and writable storage directory, select motion or continuous recording, save, then start the service. Closing the GUI does not stop it. Camera permission must be granted through the OS.

## CLI

All commands accept `--json` (place it before the command): `start`, `stop`, `restart`, `status`, `validate-config`, `list-cameras`, `test-camera`, `snapshot`, `show-log-path`, and `version`. Nonzero status means invalid input/config (2), already/not running (3), camera unavailable (4), or unsupported operation (5).

```bash
webcamcctv --json validate-config
webcamcctv list-cameras
webcamcctv start
webcamcctv --json status
webcamcctv stop
```

## Startup installation

- **Linux:** `python packaging/install.py` installs/enables a user systemd unit with restart-on-failure. Remove with `python packaging/install.py --remove`.
- **Windows 10/11:** the same command creates an `ONLOGON` Task Scheduler entry using the windowless packaged service executable where installed; removal uses `--remove`. Production installers should invoke this only after explicit consent.
- **macOS:** LaunchAgent support remains planned; run manually for now.

The service uses an exclusive lock file to prevent duplicates. Unexpected crashes are restarted by systemd/Task Scheduler policy; camera failures retry with a capped exponential delay.

## Build and package

```bash
pip install -e '.[dev]'
pytest
ruff check .
mypy src
python -m build
python packaging/build_release.py --version 0.1.0
```

### Automated releases

Push a semantic version tag matching the version in `pyproject.toml` to build and publish native
Windows, macOS, and Linux downloads automatically:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The **Cross-platform release** workflow can also be run manually for an existing tag. It builds
the GUI, headless service, and CLI with PyInstaller, smoke-tests the CLI on every operating system,
and attaches the archives and SHA-256 checksum files to a GitHub Release. A version mismatch or a
failed platform build prevents publication.

Use pinned dependencies in a release lock file and build in a clean CI image. Sign Windows binaries with SignTool, macOS bundles with `codesign`/notarization, and publish SHA-256 sums plus SBOM. End users of the PyInstaller output need no Python runtime. No release executable is checked in because this Linux environment cannot produce or sign trustworthy Windows/macOS artifacts.

## Security

There are no credentials, telemetry, remote API, cloud upload, shell interpolation, or inbound ports. Paths are handled as `Path` objects; camera names are sanitized; configuration updates and metadata are atomic; logs contain no frames or secrets. Run as the signed-in user with access only to its data directory. See [security and architecture notes](docs/ARCHITECTURE.md).

## Troubleshooting

- **Camera unavailable/in use:** close conferencing/browser apps, grant camera permission, run `webcamcctv test-camera`, then restart.
- **No MP4:** confirm the storage path is writable and OpenCV reports MP4V support. Try a standard resolution/FPS.
- **Service appears stale:** `webcamcctv --json status`; stop it, remove a stale lock only after verifying its recorded PID is absent, and restart.
- **Support bundle:** collect the redacted status JSON, `version`, `validate-config`, OS version, and OpenCV build information. Do not include configuration if paths/camera names are sensitive.

## Known limitations

Expanded capabilities are deliberately local-first and opt-in. Remote access remains loopback-only, keyring/encryption/audio/AI support requires the corresponding optional dependency group, camera controls and codecs remain backend-dependent, and signing requires release-owner certificates that are never stored in this repository. Active MP4 files use a recoverable working-file state and are quarantined after interruption, but physically damaged media may still require an external remux tool. Validate every selected camera, microphone, encoder, OS service, and installer on the target platform before deployment.

## Development and tests

`pytest` uses generated frames and temporary directories. A physical-camera smoke test is `webcamcctv test-camera`; service lifecycle testing requires a camera and must verify the resulting MP4 with `ffprobe`. Contributions must pass Ruff, mypy, pytest, dependency auditing (`pip-audit`), and platform service tests.

Uninstall with the startup removal command, then uninstall the package. Configuration, logs, and recordings are preserved intentionally; delete the OS application config/state directories and configured recording directory only after confirming no protected evidence must be retained.

## Internationalization

English and Korean are bundled as complete external UTF-8 resources. The first-run dialog selects the OS language and settings can switch language immediately; GUI status, tray controls, CLI help/messages, installer output, validation, recording search, dates, sizes, durations, and metadata paths support Korean. Runtime fallback is selected locale → English → stable key. See the [localization contribution guide](docs/LOCALIZATION.md), [English user guide](docs/en/USER_GUIDE.md), and [한국어 사용자 안내서](docs/ko/USER_GUIDE.md).

Validate translations with `python tools/validate_translations.py`. Test expanded pseudo-localized UI with `WEBCAMCCTV_PSEUDO=1 webcamcctv-gui`. Interface mockups documenting dynamic English and Korean layouts are included at [`screenshots/main-en.svg`](screenshots/main-en.svg) and [`screenshots/main-ko.svg`](screenshots/main-ko.svg).
