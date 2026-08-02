```markdown
# WebcamCCTV Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the development patterns and coding conventions used in the WebcamCCTV Python repository. You'll learn how to structure Python code for a CCTV/webcam application, follow consistent naming and import/export styles, and understand how to approach testing and common workflows in this codebase.

## Coding Conventions

### File Naming
- Use **snake_case** for all file names.
  - Example: `camera_utils.py`, `motion_detector.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .camera_utils import capture_frame
    ```

### Export Style
- Use **named exports** (i.e., define and import specific functions/classes).
  - Example:
    ```python
    # In motion_detector.py
    def detect_motion(frame): ...
    
    # In another file
    from .motion_detector import detect_motion
    ```

### Commit Message Style
- Freeform commit messages, typically short (average 44 characters).
  - Example: `add motion detection logic`

## Workflows

_No automated workflows detected in the repository._

## Testing Patterns

- **Testing Framework:** Unknown (not detected)
- **Test File Pattern:** Files matching `*.test.ts` (TypeScript test files, possibly for frontend or API mocks)
  - Example: `camera.test.ts`
- **Note:** No Python-specific test framework detected; consider adding Python tests (e.g., using `pytest`).

## Commands

| Command | Purpose |
|---------|---------|
| /add-module | Scaffold a new Python module with snake_case naming and relative imports |
| /run-tests | Run all test files matching `*.test.ts` (if applicable) |
| /format-code | Ensure code follows snake_case and relative import conventions |

```