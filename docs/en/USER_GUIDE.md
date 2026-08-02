# WebcamCCTV English user guide

## Installation and first run
Create a Python 3.11 virtual environment, run `pip install -e .`, then `webcamcctv-gui`. The first-run dialog detects the OS language; choose English, review the privacy notice, continue, select a camera, storage folder, mode, and retention period, then save. Grant camera permission in OS settings. Register login startup with `python packaging/install.py --language en` and remove it with `--remove`.

## Configuration and operation
Configuration is versioned UTF-8 JSON. `language` controls the GUI while `notification_language` is independent; an empty `date_time_format` follows the selected locale. Continuous recording segments MP4 files. Motion detection includes pre-event and post-event footage. UTF-8 metadata is stored beside recordings in dated folders. Search accepts camera or event text. Closing the GUI leaves the background service running. Validate with `webcamcctv --language en validate-config`.

## Troubleshooting
If a camera is unavailable, close conferencing software, grant permission, and run `webcamcctv --language en test-camera`. For missing video, check directory permission, free space, and MP4V codec support. Inspect service state with `webcamcctv --language en --json status`. Redact paths, camera names, video, and secrets from support material.

## Privacy and legal notice
You are responsible for applicable privacy, surveillance, workplace, audio-recording, notice, and consent laws. WebcamCCTV does not hide camera LEDs or OS privacy indicators. Provide required notice, minimize retention, and restrict recording-folder access. This release neither records audio nor uploads to a cloud.

## Uninstallation and data removal
Remove startup registration first, uninstall the package, and manually remove application config/state and the configured recording folder only after confirming that protected evidence is no longer required.
