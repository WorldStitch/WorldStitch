import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path

from WorldStitch.utils.smtp_reporter import reporter
from WorldStitch.utils.utils import TracebackHighlighter

try:
    from PyQt6.QtWidgets import QApplication

    PYQT6 = True

except ImportError:
    PYQT6 = False

RECOVERY_DIR = Path(__file__).resolve().parent.parent.parent / "recovery"

RECOVERY_DIR.mkdir(exist_ok=True)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

LOG_DIR.mkdir(exist_ok=True)


class CrashHandler:
    """Singleton-style crash/error logger with pro-level features."""

    @staticmethod
    def write_crash_log(exc_type, exc_value, exc_tb, extra_info=None):
        """Write crash information to log files."""

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        log_file = LOG_DIR / f"crash_{timestamp}.log"

        summary_file = LOG_DIR / "last_crash_summary.txt"

        header = (
            f"Timestamp: {datetime.now().isoformat()}\n"
            f"Platform: {platform.platform()}\n"
            f"Python: {platform.python_version()}\n"
            f"Executable: {sys.executable}\n"
            f"Args: {' '.join(sys.argv)}\n"
            f"{'-' * 80}\n"
        )

        extra = ""

        if extra_info:
            extra = f"--- EXTRA CONTEXT ---\n{extra_info}\n{'-' * 80}\n"

        error_msg = header + extra + "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

        with log_file.open("w", encoding="utf-8") as f:
            f.write(error_msg)

        with summary_file.open("w", encoding="utf-8") as f:
            f.write(f"{exc_type.__name__}: {exc_value}\nSee full log: {log_file}")

        print("\n>>> CRASH LOGGED:", log_file)

        print(error_msg)

        CrashHandler.cleanup_old_logs()

        return error_msg, str(log_file)

    @staticmethod
    def show_error_dialog(error_msg, log_file):
        """Display error dialog or print to stderr if GUI unavailable."""

        if PYQT6 and QApplication.instance():
            CrashHandler._show_gui_error_dialog(error_msg, log_file)

        else:
            CrashHandler._show_cli_error_output(error_msg, log_file)

    @staticmethod
    def _show_gui_error_dialog(error_msg, log_file):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QDialog,
            QFileDialog,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QTabWidget,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )

        dlg = QDialog()

        dlg.setWindowTitle("WorldStitch – Crash Handler")

        dlg.resize(780, 500)

        dlg.setModal(True)

        dlg.setStyleSheet(
            """

            QDialog {

                background: #232629;

            }

            QLabel, QTextEdit {

                color: #e3e3e3;

            }

            QPushButton {

                padding: 5px 14px;

                border-radius: 6px;

                background: #393939;

                color: #e3e3e3;

                font-size: 11pt;

            }

            QPushButton:disabled {

                color: #777;

            }

            QTabBar::tab {

                min-width: 140px;

                font-weight: bold;

                padding: 7px 18px;

                background: #282828;

                color: #dcdcdc;

                border-top-left-radius: 9px;

                border-top-right-radius: 9px;

                margin: 0 2px 0 0;

            }

            QTabBar::tab:selected {

                background: #353739;

                color: #fff;

            }

            QTabWidget::pane {

                border: 1.5px solid #333;

                border-radius: 10px;

                top: -1px;

            }

        """
        )

        main_layout = QVBoxLayout(dlg)

        main_layout.setSpacing(9)

        main_layout.setContentsMargins(12, 12, 12, 12)

        # Header area

        header = QLabel("❌ Application Crash")

        header.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))

        main_layout.addWidget(header, alignment=Qt.AlignmentFlag.AlignLeft)

        # Tabs

        tabs = QTabWidget()

        main_layout.addWidget(tabs, 1)

        # --- General Tab ---

        tab_general = QWidget()

        layout_gen = QVBoxLayout(tab_general)

        layout_gen.setSpacing(15)

        layout_gen.setContentsMargins(16, 16, 16, 16)

        header_row = QHBoxLayout()

        icon_label = QLabel()

        icon_label.setText("🛑")  # You can use a PNG/icon here if you want

        icon_label.setFont(QFont("Segoe UI", 24))

        header_row.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignLeft)

        header_title = QLabel("<span style='font-size:22pt;font-weight:bold;'>WorldStitch Crash Handler</span>")

        header_row.addWidget(header_title, alignment=Qt.AlignmentFlag.AlignLeft)

        header_row.addStretch(1)

        layout_gen.addLayout(header_row)

        layout_gen.addSpacing(8)

        summary = QLabel(
            "<b>Oops!</b> WorldStitch encountered a critical error and must close.<br>"
            "A crash report has been generated.<br><br>"
            "<b>Crash log:</b> "
            f"<a style='color:#43e0fe;text-decoration:none;' href='file:///{log_file}'>{log_file}</a>"
        )

        summary.setFont(QFont("Segoe UI", 11))

        summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )

        layout_gen.addWidget(summary)

        layout_gen.addSpacing(12)

        support = QLabel("The generated crash information is useful for reporting bugs or support.")

        support.setFont(QFont("Segoe UI", 10))

        layout_gen.addWidget(support)

        layout_gen.addSpacing(20)

        layout_gen.addStretch(1)

        tabs.addTab(tab_general, "General")

        # --- Developer Information Tab ---

        tab_dev = QWidget()

        layout_dev = QVBoxLayout(tab_dev)

        layout_dev.setSpacing(8)

        dev_info_label = QLabel("Developer Information")

        dev_info_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

        layout_dev.addWidget(dev_info_label)

        dev_text = QTextEdit()

        dev_text.setReadOnly(True)

        dev_text.setFont(QFont("Consolas", 10))

        dev_text.setStyleSheet("background: #18191b; color: #e6dede; border: 1px solid #454545;")

        dev_text.setPlainText(error_msg)

        # ← THIS activates syntax highlighting!

        TracebackHighlighter(dev_text.document())

        layout_dev.addWidget(dev_text, 1)

        tabs.addTab(tab_dev, "Developer Information")

        # --- Buttons row ---

        btn_row = QHBoxLayout()

        btn_row.setSpacing(8)

        btn_reload = QPushButton("Reload")

        btn_copy = QPushButton("Copy")

        btn_save = QPushButton("Save")

        btn_report = QPushButton("Report Bug")

        btn_report.setEnabled(False)  # No bug URL—greyed out, as in Krita

        btn_restart = QPushButton("Restart Application")

        btn_close = QPushButton("Close")

        for btn in [btn_reload, btn_copy, btn_save, btn_report, btn_restart, btn_close]:
            btn_row.addWidget(btn)

        main_layout.addLayout(btn_row)

        # --- Button logic ---

        clipboard = QApplication.instance().clipboard()

        def do_reload():
            dev_text.setPlainText(error_msg)

        def do_copy():
            clipboard.setText(error_msg)

        def do_save():
            fname, _ = QFileDialog.getSaveFileName(dlg, "Save Crash Log", "crash_log.txt", "Text Files (*.txt)")

            if fname:
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(error_msg)

        def do_report():
            # No URL; show disabled or info

            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.information(dlg, "No Bug URL", "Bug reporting is not configured for this app.")

        def do_restart():
            import os

            python = sys.executable

            os.execl(python, python, *sys.argv)

        btn_reload.clicked.connect(do_reload)

        btn_copy.clicked.connect(do_copy)

        btn_save.clicked.connect(do_save)

        btn_report.clicked.connect(do_report)

        btn_restart.clicked.connect(do_restart)

        btn_close.clicked.connect(dlg.accept)

        dlg.exec()

    @staticmethod
    def _show_cli_error_output(error_msg, log_file):
        """Print error details to stderr for CLI/headless environments."""

        print("\n--- Application Crash ---", file=sys.stderr)

        print("A critical error has occurred.", file=sys.stderr)

        print(f"Crash log: {log_file}", file=sys.stderr)

        print("\n--- Error Details ---", file=sys.stderr)

        print(error_msg, file=sys.stderr)

        print("--- End of Crash Report ---\n", file=sys.stderr)

    @classmethod
    def handle_exception(cls, exc_type, exc_value, exc_tb, extra_info=None):
        """Handle an exception by logging it and showing error dialog."""

        error_msg, log_file = cls.write_crash_log(exc_type, exc_value, exc_tb, extra_info)

        cls.show_error_dialog(error_msg, log_file)

        reporter.send_crash_report(error_msg, log_file)

    @classmethod
    def excepthook(cls, exc_type, exc_value, exc_tb):
        """Global exception handler for sys.excepthook."""

        cls.handle_exception(exc_type, exc_value, exc_tb)

    @staticmethod
    def catch_and_report(fn):
        """Decorator: catch exceptions in slots/callbacks and show crash dialog."""

        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)

            except Exception:
                exc_type, exc_value, exc_tb = sys.exc_info()

                CrashHandler.handle_exception(exc_type, exc_value, exc_tb)

        return wrapper

    @staticmethod
    def show_log_dialog(parent=None):
        """Show dialog with last crash log details."""

        if not PYQT6 or not QApplication.instance():
            print("CrashHandler log viewer: Only available in GUI mode.")

            return

        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QPushButton,
            QTextEdit,
            QVBoxLayout,
        )

        last_summary = LOG_DIR / "last_crash_summary.txt"

        log_text = last_summary.read_text(encoding="utf-8") if last_summary.exists() else "No crash logs found."

        dlg = QDialog(parent)

        dlg.setWindowTitle("📝 Last Crash/Error Log")

        dlg.resize(600, 300)

        dlg.setModal(True)

        layout = QVBoxLayout(dlg)

        label = QLabel("Most recent crash/error:")

        label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))

        layout.addWidget(label)

        # Details box

        details = QTextEdit()

        details.setReadOnly(True)

        details.setFont(QFont("Consolas", 10))

        details.setPlainText(log_text)

        layout.addWidget(details, 1)

        # Buttons

        btn_row = QHBoxLayout()

        copy_btn = QPushButton("Copy Details")

        open_btn = QPushButton("Open Logs Folder")

        restart_btn = QPushButton("Restart App")

        ok_btn = QPushButton("OK")

        btn_row.addWidget(copy_btn)

        btn_row.addWidget(open_btn)

        btn_row.addWidget(restart_btn)

        btn_row.addStretch(1)

        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

        # Button callbacks

        clipboard = QApplication.instance().clipboard()

        def copy_details():
            clipboard.setText(log_text)

        def open_logs():
            import subprocess

            if os.name == "nt":
                subprocess.Popen(f'explorer "{LOG_DIR}"')

            else:
                subprocess.Popen(["xdg-open", str(LOG_DIR)])

        def restart_app():
            python = sys.executable

            os.execl(python, python, *sys.argv)

        # Connect signals

        copy_btn.clicked.connect(copy_details)

        open_btn.clicked.connect(open_logs)

        restart_btn.clicked.connect(restart_app)

        ok_btn.clicked.connect(dlg.accept)

        dlg.exec()

    @staticmethod
    def send_crash_report_via_email(error_msg, log_file):
        """Send crash report to support email."""

        # Configuration - replace with actual values

        SMTP_SERVER = ""  # e.g. "smtp.gmail.com"

        SMTP_PORT = 587

        USERNAME = ""  # e.g. "your@email.com"

        PASSWORD = ""  # app password, not your real password

        TO_EMAIL = ""  # e.g. "support@email.com"

        if not all([SMTP_SERVER, USERNAME, PASSWORD, TO_EMAIL]):
            return (
                False,
                "Crash reporting not configured. Please contact support or check logs manually.",
            )

        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()

        msg["Subject"] = "WorldStitch Crash Report"

        msg["From"] = USERNAME

        msg["To"] = TO_EMAIL

        msg.set_content(f"Crash occurred. See attached log.\n\n{error_msg[:1000]}...")

        try:
            with open(log_file, "rb") as f:
                log_data = f.read()

            msg.add_attachment(
                log_data,
                maintype="text",
                subtype="plain",
                filename=os.path.basename(log_file),
            )

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()

                server.login(USERNAME, PASSWORD)

                server.send_message(msg)

            return True, "Crash report sent successfully."

        except Exception as e:
            return False, f"Failed to send crash report: {e}"

    @staticmethod
    def attempt_recovery():
        """Try to autosave open editors to recovery folder."""

        try:
            from PyQt6.QtWidgets import QApplication

            from WorldStitch.gui.browse.view_browse import BrowseView
            from WorldStitch.gui.chat.view_chat import ChatView
            from WorldStitch.gui.gui import LoreMainApp

            qapp = QApplication.instance()

            if not qapp:
                print("No QApplication; cannot recover tabs.")

                return

            # Find the main app

            main_app = None

            for w in qapp.topLevelWidgets():
                if isinstance(w, LoreMainApp):
                    main_app = w

                    break

            if not main_app:
                print("No LoreMainApp found; skipping recovery.")

                return

            # Recover Browse tab

            browse_view = main_app.tabs.get("Browse", None)

            if browse_view and isinstance(browse_view, BrowseView):
                browse_view.save_all_unsaved_tabs_to_recovery_folder(str(RECOVERY_DIR))

                print(f"All open note editors saved to {RECOVERY_DIR}")

            else:
                print("No BrowseView found; skipping Browse recovery.")

            # Recover Chat tab

            chat_view = main_app.tabs.get("AI", None)

            if chat_view and isinstance(chat_view, ChatView):
                chat_view.save_chat_state_to_recovery_folder(str(RECOVERY_DIR))

                print(f"Chat tab state saved to {RECOVERY_DIR}")

            else:
                print("No ChatView found; skipping Chat recovery.")

        except Exception as e:
            print(f"Recovery failed: {e}")

    @staticmethod
    def cleanup_old_logs(max_logs=50, max_days=30):
        """

        Keep only the most recent max_logs in the logs folder,

        and delete logs older than max_days days.

        """

        import glob
        import time

        logs = sorted(
            glob.glob(str(LOG_DIR / "crash_*.log")),
            key=os.path.getmtime,
            reverse=True,
        )

        # Remove logs beyond the most recent max_logs

        for old_log in logs[max_logs:]:
            try:
                os.remove(old_log)

            except Exception:
                pass

        # Remove logs older than max_days

        now = time.time()

        for log in logs:
            try:
                if now - os.path.getmtime(log) > max_days * 86400:
                    os.remove(log)

            except Exception:
                pass


# Install as global exception handler

sys.excepthook = CrashHandler.excepthook

# Convenient aliases

catch_and_report_crashes = CrashHandler.catch_and_report

show_crash_log = CrashHandler.show_log_dialog

import threading


def _thread_exception_handler(args):
    """

    Ensures that all unhandled exceptions in threads are routed to CrashHandler.

    Args is a threading.ExceptHookArgs object (Python 3.8+).

    """

    CrashHandler.handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

    # Optionally, call the original excepthook if you want default printing

    # threading.excepthook_orig(args)  # Uncomment if you want old behavior too


# Save original for debug/reference (optional)

if hasattr(threading, "excepthook"):
    threading.excepthook_orig = threading.excepthook
    threading.excepthook = _thread_exception_handler
