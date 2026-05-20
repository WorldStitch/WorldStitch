# Dev Workflow Reference — MythosEngine

# WHEN: Do this whenever a new route is added, major manager logic changes,
# or after refactors. Always before committing.

# -----------------------------
# 🧪 TESTING & DEBUGGING
# -----------------------------

# Run all tests (quick pass/fail)
pytest -q

# Run tests with short tracebacks and warnings
pytest -q --tb=short -ra --disable-warnings

# Run type checker
mypy MythosEngine/models/ MythosEngine/managers/ MythosEngine/storage/

# Lint + format
ruff check .
ruff format .

# -----------------------------
# 🚀 RUNNING LOCALLY
# -----------------------------

# Start backend (from project root)
python -m uvicorn server.app:app --host 127.0.0.1 --port 8741 --reload

# Start frontend (from frontend/)
npm run electron:dev

# Or use the convenience launcher
Launch_MythosEngine.bat

# -----------------------------
# 💾 COMMIT FLOW
# -----------------------------

# Stage specific files
git add <files>

# Commit with message (be specific)
git commit -m "fix: description of what changed"

# Push to remote
git push

# -----------------------------
# ✅ CHECKPOINT CHECKLIST
# -----------------------------

# [ ] New route has require_permission() guard?
# [ ] Manager methods use PermissionChecker before mutating?
# [ ] Tests pass?
# [ ] No unused imports?
# [ ] All changes committed?
