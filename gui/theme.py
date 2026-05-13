"""
Semantic design tokens for the voice transcription app.

Provides unified color and font systems with built-in light/dark mode support
via CustomTkinter's (light, dark) tuple format.
"""

import sys


class AppColors:
    """Semantic color tokens for application-wide use."""

    # Brand / primary
    PRIMARY = ('#2563EB', '#3B82F6')
    PRIMARY_HOVER = ('#1D4ED8', '#2563EB')

    # Semantic actions
    SUCCESS = ('#16A34A', '#22C55E')
    SUCCESS_HOVER = ('#15803D', '#16A34A')

    WARNING = ('#CA8A04', '#EAB308')
    WARNING_HOVER = ('#A16207', '#CA8A04')

    DANGER = ('#DC2626', '#EF4444')
    DANGER_HOVER = ('#B91C1C', '#DC2626')

    # Neutral / secondary actions
    SECONDARY = ('#6B7280', '#9CA3AF')
    SECONDARY_HOVER = ('#4B5563', '#6B7280')

    ACCENT = ('#7C3AED', '#8B5CF6')
    ACCENT_HOVER = ('#6D28D9', '#7C3AED')

    # Surfaces (background layers)
    SURFACE = ('gray90', 'gray17')
    SURFACE_RAISED = ('gray95', 'gray20')

    # Text
    TEXT_PRIMARY = ('gray10', 'gray95')
    TEXT_SECONDARY = ('gray50', 'gray60')
    TEXT_MUTED = ('gray60', 'gray50')

    # Borders & dividers
    BORDER = ('gray75', 'gray30')
    DIVIDER = ('gray80', 'gray25')

    # Special
    RECORDING_INDICATOR_OFF = ('gray50', 'gray50')
    SEARCH_HIGHLIGHT_BG = '#FDE68A'
    SEARCH_HIGHLIGHT_FG = '#1F2937'
    SEARCH_CURRENT_BG = '#F59E0B'
    SEARCH_CURRENT_FG = '#1F2937'


def _get_platform_font() -> str:
    """Get the best default font family for current platform."""
    if sys.platform == 'win32':
        # Windows 11: prefer Segoe UI Variable, fallback to Microsoft YaHei
        return 'Segoe UI Variable'
    elif sys.platform == 'darwin':
        return '.AppleSystemUIFont'
    else:
        # Linux: use system default, will fallback to CustomTkinter default
        return ''


class AppFonts:
    """Typography scale for application-wide use.

    Follows a consistent 4px base scale:
    - caption: 10px - helper text, hints
    - body_small: 11px - secondary labels
    - body: 12px - body text, buttons
    - subtitle: 13px - card titles, section headers
    - title: 14px - panel titles
    - heading: 18px - app title
    - monospace: 12px - numeric displays, timestamps
    """

    # Base font family - platform adaptive
    FAMILY = _get_platform_font()
    MONOSPACE = 'Consolas' if sys.platform == 'win32' else 'Courier New'

    # Typography scale
    CAPTION = (FAMILY, 10)
    BODY_SMALL = (FAMILY, 11)
    BODY = (FAMILY, 12)
    SUBTITLE = (FAMILY, 13, 'bold')
    TITLE = (FAMILY, 14, 'bold')
    HEADING = (FAMILY, 18, 'bold')

    # Specialized
    BUTTON = (FAMILY, 12)
    MONO_NUMBERS = (MONOSPACE, 12)
    TRANSCRIPTION_BODY = (FAMILY, 16)  # Base transcription text size

    # Text box spacing (for CTkTextbox)
    # Note: These are applied via tag_config in the text widget
    LINE_SPACING = 6  # spacing2 - extra space between lines
    PARAGRAPH_SPACING = 10  # spacing3 - extra space after paragraphs