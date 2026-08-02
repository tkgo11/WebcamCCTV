# Architecture, configuration, and security reference

## Process model

The GUI owns preview only; the headless service owns surveillance capture and remains alive independently. The GUI releases its camera handle before starting the service and restores preview after the service stops, avoiding exclusive-device contention. A single-instance lock validates both PID liveness and the process command before it is trusted. Configuration and service status use atomic replacement. Stop and manual-record markers provide minimal one-way commands. No privileged broker or network server exists.

The capture loop transforms frames once, applies configured motion-zone masking, feeds a bounded `deque`, and writes to the selected OpenCV encoder. Initial background-model warmup is suppressed to avoid a false full-frame event. Motion starts a segment after flushing only prior pre-event frames, extends it until the post-event interval expires, and honors cooldown before a new event. Manual mode follows explicit record-start/record-stop markers. Segments close cleanly on stop or their duration boundary. Capture read failure finalizes the writer and enters capped reconnection backoff. Status writes are rate-limited rather than emitted on every frame.

## Configuration schema v2

Top-level keys include `schema_version`, `mode`, `camera`, `cameras`, `audio`, `schedule`, `features`, `motion`, and `storage`. Version-one files are migrated in memory and the next save writes version two. Unknown nested keys are rejected by dataclass constructors. Types, FPS, dimensions, rotation, normalized polygons, schedules, encoder, sensitivity, motion timing, segment length, retention, preview rate and synchronization paths are validated. Unsupported feature switches are rejected explicitly. Writes and containing-directory metadata are fsynced before atomic replacement; only a valid existing primary may replace the last-known-good backup. `WEBCAMCCTV_CONFIG` is the supported portable-development override.

Finalized recordings are indexed in SQLite while JSON sidecars remain the recovery source of truth. Writers use a `.partial.mp4` working name, atomically publish completed segments, generate privacy-safe thumbnails, and quarantine remnants discovered at startup as interrupted recordings. Names receive a numeric suffix on same-second collision. Metadata writes are atomic and include the finalized video's SHA-256. Optional synchronization preserves the dated relative path, copies the video plus sidecar and thumbnail, streams hashes with bounded memory, and atomically publishes each verified copy.

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

Windows uses Task Scheduler `ONLOGON` for an unprivileged user process (a signed Windows Service can be added for pre-login operation). Linux uses a hardened per-user systemd service with `Restart=on-failure`. macOS uses a per-user LaunchAgent with `KeepAlive` on failure, since camera privacy authorization for daemons is constrained. The startup registrar resolves the actual adjacent packaged service or the current source environment instead of hardcoding an installation path. Sleep/wake, screen-lock state and timezone-change notifications still need dedicated platform adapters.

## Operational validation

Before deployment, validate camera permission/exclusivity, codec output with `ffprobe`, graceful SIGTERM, unplug/replug recovery, storage removal/recovery, size/age cleanup, protected retention, login startup, crash restart, and disk-full behavior on the target OS. Review privacy signage and retention policy with qualified counsel.
