"""
WorldStitch utilities package.

GUI utilities (MarkdownHighlighter, TracebackHighlighter, etc.) require PyQt6
and are only available in the desktop app.  Import them directly from
``WorldStitch.utils.utils`` when you need them, rather than via this package,
so that the server/API process can import ``WorldStitch.utils.audit_logger``
without pulling in PyQt6.
"""

__all__ = [
    "get_all_folders",
    "make_title_case_filename",
    "auto_link_notes",
    "get_note_names",
    "highlight_markdown",
    "read_note_metadata",
    "write_note_metadata",
    "MarkdownHighlighter",
    "TracebackHighlighter",
]


def __getattr__(name):
    """Lazy-load GUI utilities only when actually requested."""
    if name in __all__:
        from WorldStitch.utils.utils import (  # noqa: F401
            MarkdownHighlighter,
            TracebackHighlighter,
            auto_link_notes,
            get_all_folders,
            get_note_names,
            highlight_markdown,
            make_title_case_filename,
            read_note_metadata,
            write_note_metadata,
        )
        return locals()[name]
    raise AttributeError(f"module 'WorldStitch.utils' has no attribute {name!r}")
