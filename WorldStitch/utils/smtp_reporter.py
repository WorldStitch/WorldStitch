"""
SMTPReporter — Async email crash reporting for WorldStitch.

Sends detailed crash reports to a configured developer email address
via SMTP (e.g., Gmail, ProtonMail, or any SMTP server). Runs in a
background daemon thread and never blocks the UI or causes cascading crashes.

Configuration via environment variables:
    CRASH_REPORT_SMTP_HOST: SMTP server hostname (e.g., "smtp.gmail.com")
    CRASH_REPORT_SMTP_PORT: SMTP server port (default 587)
    CRASH_REPORT_SMTP_USER: Sender email address
    CRASH_REPORT_SMTP_PASSWORD: App password / auth token
    CRASH_REPORT_TO_EMAIL: Recipient email (the developer)
    APP_ENV: Environment identifier (development/production/test)

Usage:
    from WorldStitch.utils.smtp_reporter import reporter

    if reporter.is_configured():
        reporter.send_crash_report(error_msg, log_file)
"""

import logging
import os
import platform
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Logger for SMTP reporter itself
_logger = logging.getLogger("worldstitch_smtp_reporter")


class SMTPReporter:
    """Sends crash reports via SMTP in a background daemon thread."""

    def __init__(self):
        """Initialize reporter with config from environment variables."""
        self.smtp_host = os.getenv("CRASH_REPORT_SMTP_HOST", "").strip()
        self.smtp_port = int(os.getenv("CRASH_REPORT_SMTP_PORT", "587"))
        self.smtp_user = os.getenv("CRASH_REPORT_SMTP_USER", "").strip()
        self.smtp_password = os.getenv("CRASH_REPORT_SMTP_PASSWORD", "").strip()
        self.to_email = os.getenv("CRASH_REPORT_TO_EMAIL", "").strip()
        self.app_env = os.getenv("APP_ENV", "production").strip()

    def is_configured(self) -> bool:
        """
        Check if SMTP reporter has all required configuration.

        Returns
        -------
        bool
            True if all required env vars are set; False otherwise.
        """
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.to_email)

    def send_crash_report(self, error_msg: str, log_file: str) -> None:
        """
        Send a crash report email asynchronously in a daemon thread.

        The email includes system info, traceback, and last lines from
        audit.log and app.log. This method never raises and never blocks
        the UI.

        Parameters
        ----------
        error_msg : str
            Full error message / traceback from CrashHandler.write_crash_log()
        log_file : str
            Path to the crash log file
        """
        if not self.is_configured():
            _logger.warning(
                "SMTP reporter not configured. "
                "Set CRASH_REPORT_SMTP_HOST, CRASH_REPORT_SMTP_USER, "
                "CRASH_REPORT_SMTP_PASSWORD, and CRASH_REPORT_TO_EMAIL."
            )
            return

        # Extract exception type from error message for subject line
        exc_type = self._extract_exception_type(error_msg)

        # Start email send in background thread so it never blocks
        thread = threading.Thread(
            target=self._send_email_blocking,
            args=(error_msg, log_file, exc_type),
            daemon=True,
        )
        thread.start()

    def _extract_exception_type(self, error_msg: str) -> str:
        """
        Extract the exception type from the error message for the subject line.

        Parameters
        ----------
        error_msg : str
            Full traceback/error message

        Returns
        -------
        str
            Exception type name (e.g., "ValueError", "ImportError"),
            or "Unknown" if it cannot be determined.
        """
        lines = error_msg.split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith("-"):
                # Last non-dashed line should be "ExceptionType: message"
                if ":" in line:
                    exc_type = line.split(":")[0].strip()
                    return exc_type
        return "Unknown"

    def _send_email_blocking(self, error_msg: str, log_file: str, exc_type: str) -> None:
        """
        Send the email synchronously (called in a daemon thread).

        Never raises; all exceptions are logged and silently handled.

        Parameters
        ----------
        error_msg : str
            Full error message
        log_file : str
            Path to crash log
        exc_type : str
            Exception type for the subject line
        """
        try:
            subject = f"[WorldStitch Crash] {exc_type} — {self.app_env}"
            body = self._build_email_body(error_msg, log_file)

            # Create multipart message
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = self.to_email
            msg.attach(MIMEText(body, "plain"))

            # Connect and send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            _logger.info(f"Crash report sent to {self.to_email} for {exc_type}")
        except Exception as e:
            # Log the error but don't raise — we never want email sending
            # to cause another crash or interrupt the app
            _logger.exception(f"Failed to send crash report email: {e}")

    def _build_email_body(self, error_msg: str, log_file: str) -> str:
        """
        Build the email body with structured sections.

        Parameters
        ----------
        error_msg : str
            Full error message / traceback
        log_file : str
            Path to crash log file

        Returns
        -------
        str
            Formatted email body with sections for environment, error, logs, etc.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hostname = platform.node()
        python_version = platform.python_version()
        platform_info = platform.platform()

        # Extract first line of error for summary
        error_summary = error_msg.split("\n")[0] if error_msg else "Unknown error"

        # Resolve log directory relative to the project root, matching crash_handler.py
        _log_dir = Path(__file__).resolve().parent.parent.parent / "logs"

        # Read last 20 lines of audit.log if it exists
        audit_log_tail = self._read_log_tail(_log_dir / "audit.log", 20)

        # Read last 20 lines of app.log if it exists
        app_log_tail = self._read_log_tail(_log_dir / "app.log", 20)

        body = f"""WorldStitch CRASH REPORT
{"=" * 70}

TIMESTAMP
{"-" * 70}
{timestamp}

ENVIRONMENT
{"-" * 70}
App Environment: {self.app_env}
Python Version: {python_version}
Platform: {platform_info}
Hostname: {hostname}

ERROR SUMMARY
{"-" * 70}
{error_summary}

FULL TRACEBACK
{"-" * 70}
{error_msg}

CRASH LOG FILE
{"-" * 70}
{log_file}

AUDIT LOG (last 20 lines)
{"-" * 70}
{audit_log_tail}

APP LOG (last 20 lines)
{"-" * 70}
{app_log_tail}

{"=" * 70}
End of crash report.
"""
        return body

    @staticmethod
    def _read_log_tail(log_path: Path, max_lines: int) -> str:
        """
        Read the last N lines of a log file.

        Parameters
        ----------
        log_path : Path
            Path to the log file
        max_lines : int
            Number of lines to read from the end

        Returns
        -------
        str
            Last N lines of the file, or "(no log file)" if it doesn't exist.
        """
        if not log_path.exists():
            return "(no log file)"

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            # Get last max_lines
            tail_lines = lines[-max_lines:] if len(lines) > max_lines else lines
            return "".join(tail_lines).strip() or "(empty log)"
        except Exception as e:
            return f"(error reading log: {e})"


# Module-level singleton
reporter = SMTPReporter()
