"""
SetupWizard — first-launch account creation screen.

Shown when no users exist in the database. Replaces the login screen
on first run. Creates the owner/admin account and immediately logs in.
No default credentials, no .env passwords, no bootstrapping.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from WorldStitch.models.user import User


class SetupWizard(QDialog):
    """
    First-launch setup screen. Creates the owner account.

    After accept(), self.user holds the created User object.
    """

    def __init__(self, storage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.user: User | None = None

        self.setWindowTitle("Welcome to WorldStitch — Initial Setup")
        self.setMinimumWidth(440)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(28, 28, 28, 28)

        # Header
        title = QLabel("Welcome to WorldStitch")
        title.setStyleSheet("font-size: 20pt; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "No accounts exist yet. Create your owner account to get started.\n"
            "This account will have full admin access."
        )
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # Form
        form = QFormLayout()
        form.setSpacing(10)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Your display name")
        form.addRow("Name:", self.username_input)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("you@example.com")
        form.addRow("Email:", self.email_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Minimum 8 characters")
        form.addRow("Password:", self.password_input)

        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_input.setPlaceholderText("Repeat password")
        form.addRow("Confirm:", self.confirm_input)

        layout.addLayout(form)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        # Create button
        self.btn_create = QPushButton("Create Account & Continue")
        self.btn_create.setFixedHeight(38)
        self.btn_create.setStyleSheet(
            "QPushButton { background: #2ecc71; color: white; font-size: 11pt; "
            "border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background: #27ae60; }"
        )
        self.btn_create.clicked.connect(self._on_create)
        layout.addWidget(self.btn_create)

        # Allow Enter key to submit
        self.confirm_input.returnPressed.connect(self._on_create)

    def _on_create(self):
        username = self.username_input.text().strip()
        email = self.email_input.text().strip()
        password = self.password_input.text()
        confirm = self.confirm_input.text()

        if not username:
            self.error_label.setText("Please enter your name.")
            return
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            self.error_label.setText("Please enter a valid email address.")
            return
        if len(password) < 8:
            self.error_label.setText("Password must be at least 8 characters.")
            return
        if password != confirm:
            self.error_label.setText("Passwords do not match.")
            return

        # Check email not already taken (shouldn't happen in setup, but be safe)
        if self.storage.get_user_by_email(email):
            self.error_label.setText("An account with that email already exists.")
            return

        try:
            from WorldStitch.managers.user_manager import UserManager

            mgr = UserManager(self.storage)
            self.user = mgr.create_user(
                email=email,
                username=username,
                password=password,
                roles=["admin"],
            )
            self.accept()
        except Exception as exc:
            self.error_label.setText(f"Failed to create account: {exc}")
