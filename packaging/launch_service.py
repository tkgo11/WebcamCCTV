"""PyInstaller entry point for the headless recorder."""

from webcamcctv.service import main

if __name__ == "__main__":
    raise SystemExit(main())
