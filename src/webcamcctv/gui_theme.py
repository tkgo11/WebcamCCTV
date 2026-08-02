"""Central design tokens and Qt styles for the desktop monitor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Theme:
    background: str
    surface: str
    surface_raised: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    success: str
    warning: str
    danger: str
    preview: str


THEMES = {
    "dark": Theme(
        background="#0B1120",
        surface="#111827",
        surface_raised="#172033",
        border="#263247",
        text="#F8FAFC",
        muted="#94A3B8",
        accent="#5B8DEF",
        accent_hover="#76A2F5",
        accent_pressed="#4677D3",
        success="#34D399",
        warning="#FBBF24",
        danger="#FB7185",
        preview="#050914",
    ),
    "light": Theme(
        background="#F4F7FB",
        surface="#FFFFFF",
        surface_raised="#F8FAFC",
        border="#DCE4EF",
        text="#172033",
        muted="#64748B",
        accent="#356FE0",
        accent_hover="#285DC6",
        accent_pressed="#1F4DA8",
        success="#059669",
        warning="#D97706",
        danger="#E11D48",
        preview="#0B1120",
    ),
}


def _rgba(color: str, alpha: float) -> str:
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha:.2f})"


def resolve_theme(preference: str, *, system_is_dark: bool) -> str:
    """Resolve a stored theme preference into a concrete palette name."""
    if preference not in {"system", *THEMES}:
        raise ValueError(f"unsupported theme: {preference}")
    if preference == "system":
        return "dark" if system_is_dark else "light"
    return preference


def stylesheet(theme_name: str) -> str:
    """Build one application-wide stylesheet from the selected design tokens."""
    theme = THEMES[theme_name]
    return f"""
        QWidget#appRoot, QDialog#setupDialog {{
            background: {theme.background};
            color: {theme.text};
            font-family: "Inter", "Segoe UI", "SF Pro Display", sans-serif;
            font-size: 13px;
        }}
        QWidget#topBar {{ background: transparent; }}
        QLabel#brandTitle {{ font-size: 22px; font-weight: 700; color: {theme.text}; }}
        QLabel#brandSubtitle, QLabel[role="muted"] {{ color: {theme.muted}; }}
        QLabel[role="sectionTitle"] {{ font-size: 15px; font-weight: 650; color: {theme.text}; }}
        QLabel[role="eyebrow"] {{
            color: {theme.accent}; font-size: 11px; font-weight: 700;
        }}
        QWidget[card="true"] {{
            background: {theme.surface};
            border: 1px solid {theme.border};
            border-radius: 14px;
        }}
        QWidget#previewSurface {{
            background: {theme.preview};
            border: 1px solid {theme.border};
            border-radius: 12px;
        }}
        QLabel#cameraPreview {{ color: #CBD5E1; padding: 18px; }}
        QComboBox, QLineEdit, QSpinBox {{
            min-height: 38px;
            padding: 0 11px;
            color: {theme.text};
            background: {theme.surface_raised};
            border: 1px solid {theme.border};
            border-radius: 8px;
            selection-background-color: {theme.accent};
        }}
        QComboBox:hover, QLineEdit:hover, QSpinBox:hover {{ border-color: {theme.muted}; }}
        QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border: 2px solid {theme.accent}; }}
        QComboBox::drop-down {{ border: 0; width: 30px; }}
        QComboBox QAbstractItemView {{
            color: {theme.text}; background: {theme.surface};
            border: 1px solid {theme.border}; selection-background-color: {theme.accent};
        }}
        QPushButton {{
            min-height: 38px;
            padding: 0 14px;
            color: {theme.text};
            background: {theme.surface_raised};
            border: 1px solid {theme.border};
            border-radius: 8px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {theme.border}; }}
        QPushButton:pressed {{ padding-top: 2px; }}
        QPushButton:focus {{ border: 2px solid {theme.accent}; }}
        QPushButton:disabled {{ color: {theme.muted}; background: {theme.surface}; }}
        QPushButton[variant="primary"] {{
            color: white; background: {theme.accent}; border-color: {theme.accent};
        }}
        QPushButton[variant="primary"]:hover {{ background: {theme.accent_hover}; }}
        QPushButton[variant="primary"]:pressed {{ background: {theme.accent_pressed}; }}
        QPushButton[variant="danger"] {{ color: {theme.danger}; }}
        QPushButton[variant="record"] {{ color: white; background: {theme.danger}; border: 0; }}
        QPushButton[compact="true"] {{ min-height: 34px; padding: 0 11px; }}
        QLabel[status="true"] {{
            min-height: 26px; padding: 0 10px; border-radius: 13px;
            font-size: 11px; font-weight: 700;
        }}
        QLabel[state="good"] {{ color: {theme.success}; background: {_rgba(theme.success, 0.13)}; }}
        QLabel[state="warning"] {{ color: {theme.warning}; background: {_rgba(theme.warning, 0.13)}; }}
        QLabel[state="danger"] {{ color: {theme.danger}; background: {_rgba(theme.danger, 0.13)}; }}
        QLabel[state="neutral"] {{ color: {theme.muted}; background: {_rgba(theme.muted, 0.10)}; }}
        QListWidget {{
            color: {theme.text}; background: transparent; border: 0; outline: 0;
        }}
        QListWidget::item {{
            min-height: 42px; margin: 2px 0; padding: 0 10px;
            border: 1px solid transparent; border-radius: 8px;
        }}
        QListWidget::item:hover {{ background: {theme.surface_raised}; border-color: {theme.border}; }}
        QListWidget::item:selected {{
            background: {_rgba(theme.accent, 0.16)}; border-color: {theme.accent};
        }}
        QScrollArea {{ background: transparent; border: 0; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 3px; }}
        QScrollBar::handle:vertical {{ background: {theme.border}; border-radius: 4px; min-height: 28px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QSplitter::handle {{ width: 8px; background: transparent; }}
        QToolTip {{
            color: {theme.text}; background: {theme.surface_raised};
            border: 1px solid {theme.border}; padding: 6px;
        }}
        QMenu, QMessageBox {{ background: {theme.surface}; color: {theme.text}; }}
        QMenu::item {{ padding: 7px 22px; }}
        QMenu::item:selected {{ background: {theme.accent}; color: white; }}
    """
