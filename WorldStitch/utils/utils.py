import os
import re
from pathlib import Path

import yaml
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


def make_title_case_filename(text):
    text = text.strip().replace(" ", "_")
    text = re.sub(r"[^a-zA-Z0-9_\-]", "", text)
    text = "_".join(word.capitalize() for word in text.split("_") if word)
    return text[:50]


def get_note_names(vault_path):
    note_names = set()
    for folder_root, dirs, files in os.walk(vault_path):
        for fname in files:
            if fname.endswith(".md"):
                base = os.path.splitext(fname)[0]
                note_names.add(base)
    return note_names


def auto_link_notes(text, note_names):
    for name in sorted(note_names, key=len, reverse=True):
        pattern = r"\b" + re.escape(name) + r"\b"
        text = re.sub(pattern, f"[[{name}]]", text, flags=re.IGNORECASE)
    return text


def get_all_folders(vault_path):
    folders = []
    for folder_root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for d in dirs:
            full_path = str(Path(folder_root) / d)
            folders.append(full_path)
    folders.insert(0, "")
    return sorted(folders)


# ─── Markdown syntax highlighter (PyQt6) ──────────────────────────────


class MarkdownHighlighter(QSyntaxHighlighter):
    """
    PyQt6 QSyntaxHighlighter for Markdown / Obsidian notes.
    Attach to any QTextDocument: MarkdownHighlighter(text_edit.document())
    """

    HEADING_COLORS = ["#bf616a", "#d08770", "#ebcb8b", "#a3be8c", "#88c0d0", "#5e81ac"]
    HEADING_SIZES = [20, 18, 16, 14, 13, 12]

    def __init__(self, document):
        super().__init__(document)
        self._rules = []
        self._build_rules()

    def _fmt(self, color, bold=False, italic=False, size=None):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        if size:
            fmt.setFontPointSize(size)
        return fmt

    def _build_rules(self):
        # Headings #–######
        for lvl in range(1, 7):
            hashes = "#" * lvl
            pattern = re.compile(rf"^{hashes}(?!#)\s*.+$", re.MULTILINE)
            fmt = self._fmt(
                self.HEADING_COLORS[lvl - 1],
                bold=True,
                size=self.HEADING_SIZES[lvl - 1],
            )
            self._rules.append((pattern, fmt))

        # Bold **text**
        self._rules.append((re.compile(r"\*\*.+?\*\*"), self._fmt("#d8dee9", bold=True)))
        # Italic *text*
        self._rules.append((re.compile(r"(?<!\*)\*(?!\*).+?(?<!\*)\*(?!\*)"), self._fmt("#d8dee9", italic=True)))
        # Inline code `code`
        self._rules.append((re.compile(r"`[^`]+?`"), self._fmt("#88c0d0")))
        # Blockquotes
        self._rules.append((re.compile(r"^>\s+.+$", re.MULTILINE), self._fmt("#657b83", italic=True)))
        # Unordered lists
        self._rules.append((re.compile(r"^[-*+]\s+.+$", re.MULTILINE), self._fmt("#d8dee9")))
        # Wiki links [[...]]
        self._rules.append((re.compile(r"\[\[.+?\]\]"), self._fmt("#81a1c1")))
        # Markdown links [text](url)
        self._rules.append((re.compile(r"\[.+?\]\(.+?\)"), self._fmt("#81a1c1")))
        # Tags #tag
        self._rules.append((re.compile(r"(?<!\[)#\w+"), self._fmt("#a3be8c")))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def highlight_markdown(text_edit):
    """
    Attach a MarkdownHighlighter to a QTextEdit or QPlainTextEdit.
    Returns the highlighter instance (keep a reference so it isn't GC'd).
    """
    return MarkdownHighlighter(text_edit.document())


def read_note_metadata(note_text):
    """
    Returns (metadata_dict, body_text)
    If no YAML frontmatter, metadata_dict is empty.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", note_text, re.DOTALL)
    if match:
        yaml_str, body = match.group(1), match.group(2)
        try:
            meta = yaml.safe_load(yaml_str) or {}
            if not isinstance(meta, dict):
                meta = {}
        except Exception:
            meta = {}
        return meta, body
    else:
        # No YAML, treat entire note as body
        return {}, note_text


def write_note_metadata(metadata_dict, body_text):
    """
    Returns note text with YAML frontmatter and body.
    """
    yaml_str = yaml.safe_dump(metadata_dict, sort_keys=False).strip()
    return f"---\n{yaml_str}\n---\n{body_text.lstrip()}"


class TracebackHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Format for "Traceback (most recent call last):"
        self.traceback_format = QTextCharFormat()
        self.traceback_format.setForeground(QColor("#ffb347"))
        self.traceback_format.setFontWeight(QFont.Weight.Bold)

        # Format for file/line blocks
        self.fileline_format = QTextCharFormat()
        self.fileline_format.setForeground(QColor("#5fc4ff"))
        self.fileline_format.setFontItalic(True)

        # Format for error types
        self.error_format = QTextCharFormat()
        self.error_format.setForeground(QColor("#ff6767"))
        self.error_format.setFontWeight(QFont.Weight.Bold)

        # Format for code lines
        self.code_format = QTextCharFormat()
        self.code_format.setForeground(QColor("#bbbbbb"))

        self.re_traceback = re.compile(r"^Traceback \(most recent call last\):")
        self.re_fileline = re.compile(r'  File ".*", line \d+, in .+')
        self.re_error = re.compile(r"^[\w.]+Error: |^[\w.]+Exception:")

    def highlightBlock(self, text):
        if self.re_traceback.match(text):
            self.setFormat(0, len(text), self.traceback_format)
        elif self.re_fileline.match(text):
            self.setFormat(0, len(text), self.fileline_format)
        elif self.re_error.match(text):
            self.setFormat(0, len(text), self.error_format)
        elif text.strip().startswith("    "):
            self.setFormat(0, len(text), self.code_format)
