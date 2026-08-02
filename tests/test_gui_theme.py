import pytest

from webcamcctv.gui_theme import THEMES, resolve_theme, stylesheet


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_stylesheet_contains_core_widget_states(theme):
    rendered = stylesheet(theme)
    assert THEMES[theme].background in rendered
    assert 'QPushButton[variant="primary"]' in rendered
    assert 'QLabel[state="good"]' in rendered
    assert "QLineEdit:focus" in rendered


def test_system_theme_resolves_and_invalid_preference_is_rejected():
    assert resolve_theme("system", system_is_dark=True) == "dark"
    assert resolve_theme("system", system_is_dark=False) == "light"
    assert resolve_theme("dark", system_is_dark=False) == "dark"
    with pytest.raises(ValueError, match="unsupported theme"):
        resolve_theme("neon", system_is_dark=True)
