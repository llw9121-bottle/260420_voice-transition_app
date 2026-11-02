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
    BACKGROUND = ('#F3F5F9', '#111827')
    SURFACE = ('#E9EEF5', '#1B2738')
    SURFACE_RAISED = ('#FFFFFF', '#202D40')

    # Text
    TEXT_PRIMARY = ('#1F2937', '#F1F5F9')
    TEXT_SECONDARY = ('#526173', '#B4C1D2')
    TEXT_MUTED = ('#66768A', '#94A3B8')

    # Borders & dividers
    BORDER = ('#CBD5E1', '#43536B')
    DIVIDER = ('#DFE5ED', '#334155')

    # Special
    RECORDING_INDICATOR_OFF = ('gray50', 'gray50')
    SEARCH_HIGHLIGHT_BG = '#FDE68A'
    SEARCH_HIGHLIGHT_FG = '#1F2937'
    SEARCH_CURRENT_BG = '#F59E0B'
    SEARCH_CURRENT_FG = '#1F2937'


def _get_platform_font() -> str:
    """Get the best default font family for current platform."""
    if sys.platform == 'win32':
        # 中文界面优先使用系统无衬线字体，避免回退为宋体。
        return 'Microsoft YaHei UI'
    elif sys.platform == 'darwin':
        return '.AppleSystemUIFont'
    else:
        # Linux: use system default, will fallback to CustomTkinter default
        return ''


class AppFonts:
    """Typography scale for application-wide use.

    Follows a consistent 4px base scale:
    - caption: 10px - helper text, hints
    - body_small: 12px - secondary labels
    - body: 13px - body text, buttons
    - subtitle: 13px - card titles, section headers
    - title: 15px - panel titles
    - heading: 21px - app title
    - monospace: 12px - numeric displays, timestamps
    """

    # Base font family - platform adaptive
    FAMILY = _get_platform_font()
    MONOSPACE = 'Consolas' if sys.platform == 'win32' else 'Courier New'

    # Typography scale
    CAPTION = (FAMILY, 10)
    BODY_SMALL = (FAMILY, 12)
    BODY = (FAMILY, 13)
    SUBTITLE = (FAMILY, 13, 'bold')
    TITLE = (FAMILY, 15, 'bold')
    HEADING = (FAMILY, 21, 'bold')

    # Specialized
    BUTTON = (FAMILY, 13)
    MONO_NUMBERS = (MONOSPACE, 12)
    TRANSCRIPTION_BODY = (FAMILY, 16)  # Base transcription text size

    # Text box spacing (for CTkTextbox)
    # Note: These are applied via tag_config in the text widget
    LINE_SPACING = 6  # spacing2 - extra space between lines
    PARAGRAPH_SPACING = 10  # spacing3 - extra space after paragraphs
