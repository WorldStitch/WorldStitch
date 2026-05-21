# WorldStitch/auth/signup_dialog.py
"""
SignupDialog — self-service account creation using an invite code.

Flow:
  1. User enters invite code, email, username, password, confirm-password.
  2. Dialog validates the invite code against the DB.
  3. On success: UserManager.create_user() is called, invite is redeemed,
     and self.user holds the newly created User object.

The dialog is shown from LoginDialog when the user clicks
"Sign Up with Invite Code".
"""

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from WorldStitch.models.user import User


class SignupDialog(QDialog):
    """
    Self-registration dialog for users with an invite code.

    Parameters
    ----------
    storage : StorageBackend
        Used by InviteManager for code validation.
    invite_mgr : InviteManager
        Inject from AppContext.invites.
    user_mgr : UserManager
        Inject from AppContext.users.
    parent : QWidget, optional
    """

    def __init__(self, storage, invite_mgr, user_mgr, parent=None):
        super().__init__(parent)
        self.storage = storage
        self._invites = invite_mgr
        self._users = user_mgr
        self.user: Optional[User] = None

        self.setWindowTitle("WorldStitch — Create Account")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(28, 28, 28, 28)

        # Header
        title = QLabel("Create Your Account")
        title.setStyleSheet("font-size: 18pt; font-weight: 700; background: transparent;")
        layout.addWidget(title)

        sub = QLabel("Enter your invite code and account details below.")
        sub.setStyleSheet("font-size: 10pt; background: transparent;")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        layout.addSpacing(8)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(div)

        layout.addSpacing(4)

        # ── Fields ────────────────────────────────────────────────────────
        def _field(label_text: str, placeholder: str, echo_password: bool = False) -> QLineEdit:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 10pt; font-weight: 600; background: transparent;")
            layout.addWidget(lbl)
            field = QLineEdit()
            field.setPlaceholderText(placeholder)
            if echo_password:
                field.setEchoMode(QLineEdit.EchoMode.Password)
            layout.addWidget(field)
            return field

        self.code_input = _field("Invite Code", "XXXX-XXXX-XXXX")
        self.email_input = _field("Email", "you@example.com")
        self.username_input = _field("Username", "Your display name")
        self.pw_input = _field("Password", "Minimum 8 characters", echo_password=True)
        self.pw2_input = _field("Confirm Password", "Repeat your password", echo_password=True)

        # Allow pressing Enter on last field to submit
        self.pw2_input.returnPressed.connect(self._on_submit)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #EF4444; font-size: 9pt; background: transparent;")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        layout.addSpacing(8)

        # Submit button
        self.btn_create = QPushButton("Create Account")
        self.btn_create.setMinimumHeight(40)
        self.btn_create.clicked.connect(self._on_submit)
        layout.addWidget(self.btn_create)

        # Back link
        btn_back = QPushButton("Already have an account? Log in")
        btn_back.setProperty("secondary", "true")
        btn_back.setMinimumHeight(36)
        btn_back.clicked.connect(self.reject)
        layout.addWidget(btn_back)

    # ── Validation & submission ───────────────────────────────────────────

    def _on_submit(self) -> None:
        self._hide_error()

        code = self.code_input.text().strip().upper()
        email = self.email_input.text().strip()
        username = self.username_input.text().strip()
        pw = self.pw_input.text()
        pw2 = self.pw2_input.text()

        # — Field presence —
        if not code:
            return self._show_error("Please enter your invite code.")
        if not email or "@" not in email:
            return self._show_error("Please enter a valid email address.")
        if not username or len(username) < 2:
            return self._show_error("Username must be at least 2 characters.")
        if len(pw) < 8:
            return self._show_error("Password must be at least 8 characters.")
        if pw != pw2:
            return self._show_error("Passwords do not match.")

        # — Invite code validation —
        invite = self._invites.validate(code)
        if invite is None:
            return self._show_error(
                "Invite code is invalid, expired, or already used.\nAsk your Game Master for a new one."
            )

        # — Email uniqueness —
        if self._users.get_user_by_email(email):
            return self._show_error("That email address is already registered.")

        # — Create account —
        try:
            new_user = self._users.create_user(
                email=email,
                username=username,
                password=pw,
                roles=["player"],
            )
            self._invites.redeem(code, new_user.id)
            self.user = new_user
            self.accept()
        except Exception as exc:
            self._show_error(f"Account creation failed: {exc}")

    def _show_error(self, msg: str) -> None:
        self.error_label.setText(msg)
        self.error_label.setVisible(True)

    def _hide_error(self) -> None:
        self.error_label.setVisible(False)
        self.error_label.setText("")
