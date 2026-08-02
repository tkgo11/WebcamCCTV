# WebcamCCTV

A local-first desktop webcam CCTV system comprising an independent **headless recorder** and a **Qt monitoring/configuration GUI**. It performs continuous or motion-triggered MP4 recording, keeps a bounded pre-event frame ring, records post-event footage, reconnects cameras with exponential backoff, and enforces storage retention without a cloud dependency or telemetry.

> **Privacy notice:** You are responsible for camera, workplace, privacy, wiretapping, audio-recording, notice, and consent laws. WebcamCCTV does not suppress operating-system camera indicators and must not be used for covert surveillance. Audio is deliberately not enabled in this release.

## Technology and architecture

Python 3.11, OpenCV and NumPy were chosen for portable camera/video processing; PySide6 supplies an accessible, high-DPI native desktop UI; `platformdirs` keeps mutable data in OS-appropriate locations. PyInstaller can bundle the runtime. The service and GUI are separate processes. They exchange only an atomically replaced, read-only status JSON file and small stop/manual-record request markers; configuration is atomically written before the service reloads it on restart. This intentionally small local IPC surface has no listening network port. The GUI releases its preview handle while the service owns the camera.

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

Recordings use `YYYY/MM/DD/YYYYMMDD_HHMMSS_Camera.mp4` with collision-safe numeric suffixes and atomic JSON sidecars containing timestamps, camera, event type, encoder and SHA-256. A `.protected` sibling prevents cleanup. Interrupted `.partial.mp4` files are quarantined and indexed on the next start. Configuration schema v2 is illustrated in [`config/example.json`](config/example.json).

## Implemented scope

The current release includes schema-v2 configuration, discovery/preview, an independent single-camera service, continuous/motion/manual MP4 recording, pre/post event capture, motion zones, privacy masks, reconnect, retention, SQLite indexing, thumbnails, schedules, encoder selection, interrupted-segment recovery, checksummed synchronization, diagnostics export, and per-user login startup on Linux, Windows and macOS.

Audio capture, notifications, AI event detection, automatic encryption, remote viewing/API access, screen-lock detection and concurrent multi-camera recording are not implemented. Configuration validation rejects attempts to enable those placeholders instead of silently ignoring them; see [Known limitations](#known-limitations).

## Install and first run

```bash
python -m venv .venv
. .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -e .
webcamcctv-gui
```

On first run: review the privacy notice, choose a discovered camera and writable storage directory, select motion or continuous recording, save, then start the service. The dashboard follows the system appearance by default and can be switched to dark or light mode from its header. Use `Ctrl+S` to save, `Ctrl+F` to search recordings, and `Ctrl+R` to refresh. Closing the GUI does not stop the service. Camera permission must be granted through the OS.

## CLI

All commands accept `--json` (place it before the command): `start`, `stop`, `restart`, `status`, `validate-config`, `list-cameras`, `test-camera`, `snapshot`, `diagnostics`, `show-log-path`, `version`, `record-start`, and `record-stop`. The last two commands operate only in manual mode. Nonzero status means invalid input/config (2), already/not running (3), camera unavailable (4), or unsupported/failed operation (5).

```bash
webcamcctv --json validate-config
webcamcctv list-cameras
webcamcctv start
webcamcctv --json status
webcamcctv record-start        # manual mode only
webcamcctv record-stop
webcamcctv stop
```

## Startup installation

- **Source installation:** run `webcamcctv-startup` (or `python packaging/install.py`) and add `--remove` to unregister it.
- **Native archive:** run `WebcamCCTV-Startup` from the extracted archive; it registers the adjacent service executable, so no Python runtime is needed.
- **Linux:** installs and enables a per-user systemd unit with restart-on-failure.
- **Windows 10/11:** creates an unprivileged `ONLOGON` Task Scheduler entry.
- **macOS:** installs and bootstraps a per-user LaunchAgent with restart-on-failure.

The service uses an exclusive lock file whose PID is checked against the live process command before it is trusted. Unexpected crashes are restarted by systemd or launchd; camera failures retry internally with capped exponential delay. The Windows login task starts the recorder after sign-in, but Task Scheduler restart-on-failure policy is not yet configured.

## Build and package

```bash
pip install -e '.[dev]'
pytest
ruff check .
mypy src
python -m build
python packaging/build_release.py --version 0.3.0
```

### Automated releases

Push a semantic version tag matching the version in `pyproject.toml` to build and publish native
Windows, macOS, and Linux downloads automatically:

```bash
git tag v0.3.0
git push origin v0.3.0
```

The **Cross-platform release** workflow can also be run manually for an existing tag. It runs tests, lint, type checks, translation validation, dependency auditing and package builds; then it builds
the GUI, headless service, and CLI with PyInstaller, smoke-tests the CLI on every operating system,
includes the startup registrar, and attaches the archives and SHA-256 checksum files to a GitHub Release. A version mismatch or a
failed platform build prevents publication.

Sign Windows binaries with SignTool and macOS bundles with `codesign`/notarization when release-owner certificates are available, and add an SBOM before treating builds as signed production releases. End users of the PyInstaller output need no Python runtime. No release executable is checked in because CI produces platform-native artifacts.

## Security

There are no credentials, telemetry, remote API, cloud upload, shell interpolation, or inbound ports. Paths are handled as `Path` objects; camera names are sanitized; configuration updates and metadata are atomic; logs contain no frames or secrets. Run as the signed-in user with access only to its data directory. See [security and architecture notes](docs/ARCHITECTURE.md).

## Troubleshooting

- **Camera unavailable/in use:** close conferencing/browser apps, grant camera permission, run `webcamcctv test-camera`, then restart.
- **No MP4:** confirm the storage path is writable and OpenCV reports MP4V support. Try a standard resolution/FPS.
- **Service appears stale:** `webcamcctv --json status`; stop it, remove a stale lock only after verifying its recorded PID is absent, and restart.
- **Support bundle:** collect the redacted status JSON, `version`, `validate-config`, OS version, and OpenCV build information. Do not include configuration if paths/camera names are sensitive.

## Known limitations

The recorder currently operates one camera per service. Audio, notification delivery, AI inference, automatic encryption, remote access/API serving, screen-lock detection and Windows task restart-on-failure are unavailable. Camera controls and codecs remain backend-dependent, and signing requires release-owner certificates that are never stored in this repository. Active MP4 files use a recoverable working-file state and are quarantined after interruption, but physically damaged media may still require an external remux tool. Validate the selected camera, encoder, OS startup mechanism and installer on the target platform before deployment.

## Development and tests

`pytest` uses generated frames and temporary directories. Pull requests run Ruff, mypy, translation checks, package builds, dependency auditing, and Python tests on Linux, Windows and macOS. A physical-camera smoke test is `webcamcctv test-camera`; service lifecycle testing requires a camera and must verify the resulting MP4 with `ffprobe`.

Uninstall with the startup removal command, then uninstall the package. Configuration, logs, and recordings are preserved intentionally; delete the OS application config/state directories and configured recording directory only after confirming no protected evidence must be retained.

## Internationalization

English and Korean are bundled as complete external UTF-8 resources. The first-run dialog selects the OS language and settings can switch language immediately; GUI status, tray controls, CLI help/messages, installer output, validation, recording search, dates, sizes, durations, and metadata paths support Korean. Runtime fallback is selected locale → English → stable key. See the [localization contribution guide](docs/LOCALIZATION.md), [English user guide](docs/en/USER_GUIDE.md), and [한국어 사용자 안내서](docs/ko/USER_GUIDE.md).

Validate translations with `python tools/validate_translations.py`. Test expanded pseudo-localized UI with `WEBCAMCCTV_PSEUDO=1 webcamcctv-gui`. Interface mockups documenting dynamic English and Korean layouts are included at [`screenshots/main-en.svg`](screenshots/main-en.svg) and [`screenshots/main-ko.svg`](screenshots/main-ko.svg).
