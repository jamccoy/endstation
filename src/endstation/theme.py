"""Colour themes for a desktop window and its plots, as data.

Core module: standard library only. A :class:`Theme` is a set of named colours:
the window palette, the plot surfaces and three verdict colours (``ok``,
``warn``, ``bad``). :mod:`endstation.qt.theming` turns one into a ``QPalette``
and matplotlib settings; code that draws asks the active theme for a colour by
meaning, never by value.

An application with colours of its own (a diagram's tags, a family of line
colours) subclasses :class:`Theme` with extra fields that have defaults, and
builds its themes from the ones here with :meth:`Theme.extend`, so the window
palette stays defined in one place::

    @dataclass(frozen=True)
    class AppTheme(Theme):
        diagram: Mapping[str, str] = field(default_factory=dict)

    LIGHT = AppTheme.extend(endstation.theme.LIGHT, diagram={...})

The five themes here were gratinglab's, value for value.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

__all__ = [
    "DARK",
    "HIGH_CONTRAST",
    "LIGHT",
    "SOLARIZED",
    "SOLARIZED_DARK",
    "SOLARIZED_LIGHT",
    "SYSTEM",
    "THEMES",
    "Theme",
    "contrast",
    "pane",
    "rc_params",
]

#: The choice that follows the operating system's light or dark setting.
SYSTEM = "system"


@dataclass(frozen=True)
class Theme:
    """One theme. Every field is a ``#rrggbb`` colour except the first three."""

    key: str
    label: str
    dark: bool
    # Window palette.
    window: str
    base: str
    alt_base: str
    text: str
    muted: str
    button: str
    highlight: str
    highlight_text: str
    link: str
    # Plot surfaces.
    figure: str
    axes: str
    ink: str
    grid: str
    # Verdicts.
    warn: str
    bad: str
    ok: str

    @classmethod
    def extend(cls, base: "Theme", **extra):
        """A ``cls`` with every field of ``base`` and the subclass fields in ``extra``."""
        values = {f.name: getattr(base, f.name) for f in fields(Theme)}
        values.update(extra)
        return cls(**values)


LIGHT = Theme(
    key="light", label="Light", dark=False,
    window="#efefef", base="#ffffff", alt_base="#f7f7f7", text="#1a1a1a",
    muted="#666666", button="#efefef", highlight="#2d5aa8",
    highlight_text="#ffffff", link="#2d5aa8",
    figure="#ffffff", axes="#ffffff", ink="#1a1a1a", grid="#b0b0b0",
    warn="#a5370d", bad="#b00020", ok="#0a7d28",
)

DARK = Theme(
    key="dark", label="Dark", dark=True,
    window="#1f2125", base="#17181b", alt_base="#222429", text="#e6e6e6",
    muted="#9aa0a6", button="#2a2d32", highlight="#2f6fd6",
    highlight_text="#ffffff", link="#7fb0ff",
    figure="#17181b", axes="#17181b", ink="#e6e6e6", grid="#4a4f55",
    warn="#ff9f5a", bad="#ff6b81", ok="#5ad17a",
)

# Solarized, Ethan Schoonover's palette: the base tones and accents are his.
SOLARIZED = {
    "base03": "#002b36", "base02": "#073642", "base01": "#586e75",
    "base00": "#657b83", "base0": "#839496", "base1": "#93a1a1",
    "base2": "#eee8d5", "base3": "#fdf6e3", "yellow": "#b58900",
    "orange": "#cb4b16", "red": "#dc322f", "magenta": "#d33682",
    "violet": "#6c71c4", "blue": "#268bd2", "cyan": "#2aa198",
    "green": "#859900",
}
_S = SOLARIZED

SOLARIZED_LIGHT = Theme(
    key="solarized-light", label="Solarized Light", dark=False,
    window=_S["base2"], base=_S["base3"], alt_base="#f5efdc", text=_S["base02"],
    muted=_S["base01"], button=_S["base2"], highlight="#1f6fae",
    highlight_text=_S["base3"], link="#1f6fae",
    figure=_S["base3"], axes=_S["base3"], ink=_S["base02"], grid="#d9d2bf",
    warn="#b4410f", bad="#c42a27", ok="#5f6e00",
)

SOLARIZED_DARK = Theme(
    key="solarized-dark", label="Solarized Dark", dark=True,
    window=_S["base02"], base=_S["base03"], alt_base="#04313d", text=_S["base2"],
    muted=_S["base1"], button=_S["base02"], highlight="#1f6fae",
    highlight_text=_S["base3"], link="#5fb3f0",
    figure=_S["base03"], axes=_S["base03"], ink=_S["base2"], grid="#1c4a56",
    warn="#e8743b", bad="#f06260", ok="#a4bf1d",
)

HIGH_CONTRAST = Theme(
    key="high-contrast", label="High contrast", dark=True,
    window="#000000", base="#1a1a1a", alt_base="#262626", text="#ffffff",
    muted="#a8a8a8", button="#2a2a2a", highlight="#ffff00",
    highlight_text="#000000", link="#00ffff",
    figure="#000000", axes="#000000", ink="#ffffff", grid="#5a5a5a",
    warn="#ffb000", bad="#ff5c5c", ok="#3cff6e",
)

#: Every theme by key, in menu order.
THEMES: dict[str, Theme] = {
    t.key: t for t in (LIGHT, DARK, SOLARIZED_LIGHT, SOLARIZED_DARK, HIGH_CONTRAST)
}


def _luminance(color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    value = color.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast(foreground: str, background: str) -> float:
    """WCAG 2 contrast ratio between two ``#rrggbb`` colours, 1 to 21."""
    a, b = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def rc_params(theme: Theme) -> dict[str, object]:
    """matplotlib settings for this theme, for ``rcParams.update``.

    A plain dict, so building it needs no matplotlib. The settings govern what
    is created after they are set; an existing figure needs restyling too.
    """
    return {
        "figure.facecolor": theme.figure,
        "figure.edgecolor": theme.figure,
        "savefig.facecolor": theme.figure,
        "savefig.edgecolor": theme.figure,
        "axes.facecolor": theme.axes,
        "axes.edgecolor": theme.ink,
        "axes.labelcolor": theme.ink,
        "axes.titlecolor": theme.ink,
        "text.color": theme.ink,
        "xtick.color": theme.ink,
        "ytick.color": theme.ink,
        "xtick.labelcolor": theme.ink,
        "ytick.labelcolor": theme.ink,
        "grid.color": theme.grid,
        "legend.facecolor": theme.axes,
        "legend.edgecolor": theme.grid,
        "legend.labelcolor": theme.ink,
        "axes3d.xaxis.panecolor": pane(theme),
        "axes3d.yaxis.panecolor": pane(theme),
        "axes3d.zaxis.panecolor": pane(theme),
    }


def pane(theme: Theme) -> tuple[float, float, float, float]:
    """A 3D pane tinted a little away from the axes colour, as RGBA in 0..1."""
    value = theme.axes.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    shift = 0.06 if theme.dark else -0.04
    return (*(max(0.0, min(1.0, c + shift)) for c in (red, green, blue)), 1.0)
