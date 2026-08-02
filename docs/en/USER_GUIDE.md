# WebcamCCTV English user guide

## Installation and first run
Create a Python 3.11 virtual environment, run `pip install -e .`, then `webcamcctv-gui`. The first-run dialog detects the OS language; choose English, review the privacy notice, continue, select a camera, storage folder, mode, and retention period, then save. Grant camera permission in OS settings. Register login startup with `webcamcctv-startup --language en` and remove it with `--remove`. In a native archive, run the adjacent `WebcamCCTV-Startup` executable instead.

## Configuration and operation
Configuration is versioned UTF-8 JSON. `language` controls the GUI while `notification_language` is reserved independently; an empty `date_time_format` follows the selected locale. Continuous recording segments MP4 files. Motion detection includes pre-event and post-event footage. In manual mode, use the GUI recording buttons or `webcamcctv record-start` and `webcamcctv record-stop`. UTF-8 metadata is stored beside recordings in dated folders. Search accepts camera or event text. Closing the GUI to its tray leaves the background service running. Validate with `webcamcctv --language en validate-config`.

## Troubleshooting
If a camera is unavailable, close conferencing software, grant permission, and run `webcamcctv --language en test-camera`. For missing video, check directory permission, free space, and MP4V codec support. Inspect service state with `webcamcctv --language en --json status`. Generate a privacy-redacted report with `webcamcctv diagnostics`; never attach recordings to a support request unless you intend to disclose them.

## Privacy and legal notice
You are responsible for applicable privacy, surveillance, workplace, audio-recording, notice, and consent laws. WebcamCCTV does not hide camera LEDs or OS privacy indicators. Provide required notice, minimize retention, and restrict recording-folder access. This release neither records audio nor uploads to a cloud.

## Uninstallation and data removal
Remove startup registration first with `webcamcctv-startup --remove` (or the native startup executable), uninstall the package, and manually remove application config/state and the configured recording folder only after confirming that protected evidence is no longer required.
