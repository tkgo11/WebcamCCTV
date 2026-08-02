# Architecture, configuration, and security reference

## Process model

The GUI owns preview only; the headless service owns surveillance capture and remains alive independently. A single-instance lock prevents parallel recorders. Configuration and service status use atomic replacement. A stop marker provides a minimal one-way command. No privileged broker or network server exists.

The capture loop transforms frames once, feeds the same frame to motion analysis and a bounded `deque`, and writes it to OpenCV's MP4V encoder. Motion starts a segment after flushing the pre-event deque and extends it until the post-event interval expires. Segments close cleanly on stop or their duration boundary. Capture read failure finalizes the writer and enters capped reconnection backoff.

## Configuration schema v2

Top-level keys include `schema_version`, `mode`, `camera`, `cameras`, `audio`, `schedule`, `features`, `motion`, and `storage`. Version-one files are migrated in memory and the next save writes version two. Unknown nested keys are rejected by dataclass constructors. FPS, dimensions, rotation, schedules, audio format, encoder, sensitivity, minimum motion area, segment length, and retention values are validated. Writes are fsynced then atomically renamed; an existing valid file is backed up and used if the primary becomes corrupt. `WEBCAMCCTV_CONFIG` is the supported portable-development override.

Finalized recordings are indexed in SQLite while JSON sidecars remain the recovery source of truth. Writers use a `.partial.mp4` working name, atomically publish completed segments, generate privacy-safe thumbnails, and quarantine remnants discovered at startup. Optional synchronization verifies SHA-256 before publishing its copy.

Camera controls vary radically by backend and are intentionally not promised until capability probing is implemented. `device` is an OpenCV numeric index. Storage supports any mounted path writable by the account, including mounted NAS volumes; unavailable paths surface as service failures rather than silently switching locations.

## Threat model and mitigations

- **Unauthorized viewing:** no remote interface; recordings inherit user directory permissions. Restrict the storage ACL.
- **Path traversal:** camera-derived file components are allowlisted; user storage paths are never concatenated with untrusted relative traversal.
- **Command injection:** lifecycle commands use argument arrays and never a shell.
- **Secret leakage:** no credentials are accepted. Future notification/API modules must use DPAPI, Keychain, or Secret Service/keyring and redact structured logs.
- **Resource exhaustion:** pre-event frames have a fixed maximum, retries cap at 30 seconds, recordings segment, logs are delegated to bounded system journals, and cleanup enforces age/size/free-space limits.
- **Evidence deletion:** `.protected` markers exclude recordings from automatic retention. This is not tamper-proof; regulated deployments require append-only external storage and audit controls.
- **Malformed config:** schema/version/range checks occur before capture starts, and the last backup can be restored.
- **Covert surveillance:** the app does not bypass camera LEDs or OS privacy indicators and documents active state.

Future remote access must remain disabled by default and add TLS, Argon2id passwords, expiring/revocable sessions, CSRF protection, secure cookies, token hashing, rate limiting and access auditing. Port forwarding must never be enabled automatically.

## Platform mechanisms

Windows uses Task Scheduler `ONLOGON` for an unprivileged user process (a signed Windows Service can be added for pre-login operation). Linux uses a hardened per-user systemd service with `Restart=on-failure`. macOS should use a signed per-user LaunchAgent, since camera privacy authorization for daemons is constrained. Sleep/wake and timezone schedule recalculation need dedicated platform adapters in the scheduling milestone.

## Operational validation

Before deployment, validate camera permission/exclusivity, codec output with `ffprobe`, graceful SIGTERM, unplug/replug recovery, storage removal/recovery, size/age cleanup, protected retention, login startup, crash restart, and disk-full behavior on the target OS. Review privacy signage and retention policy with qualified counsel.
