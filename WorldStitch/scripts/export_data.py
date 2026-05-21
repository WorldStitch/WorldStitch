"""
export_data.py — Export or restore all WorldStitch user data.

Usage
-----
Export all data to a timestamped zip:
    python WorldStitch/scripts/export_data.py --output exports/

Restore from a previously exported zip:
    python WorldStitch/scripts/export_data.py --restore exports/worldstitch_export_20260414.zip --target ./restored_vault/

What is exported
----------------
- All vault markdown files (notes, folders)
- .dnd_meta/ structured model data (characters, maps, etc.)
- config/settings.json
- logs/audit.log
- WorldStitch/ai/ai_usage_log.csv
- Global user/group data (~/.worldstitch_ai/)

What is NOT exported
--------------------
- .env (contains secrets — never export)
- .venv/ (reinstall via pip)
- __pycache__/ and .pyc files
- .versions/ backup files (very large; use OS backup for these)
"""

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ── Project root (two levels up from this script) ──────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent


def _load_vault_path() -> Path:
    """Read VAULT_PATH from settings.json."""
    settings = PROJECT_ROOT / "WorldStitch" / "config" / "settings.json"
    if settings.exists():
        data = json.loads(settings.read_text(encoding="utf-8"))
        return Path(data.get("VAULT_PATH", "./Obsidian")).expanduser().resolve()
    return (PROJECT_ROOT / "Obsidian").resolve()


def export_data(output_dir: Path) -> Path:
    """
    Create a timestamped zip of all user data.
    Returns the path to the created zip file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    vault_path = _load_vault_path()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = output_dir / f"worldstitch_export_{timestamp}.zip"

    print("Exporting WorldStitch data...")
    print(f"  Vault: {vault_path}")
    print(f"  Output: {zip_path}")

    file_count = 0

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Vault markdown files
        if vault_path.exists():
            for p in vault_path.rglob("*"):
                if p.is_file() and not any(part.startswith(".") for part in p.parts if part not in (".dnd_meta",)):
                    arc = "vault/" + str(p.relative_to(vault_path))
                    zf.write(p, arc)
                    file_count += 1

            # 2. .dnd_meta structured data
            dnd_meta = vault_path / ".dnd_meta"
            if dnd_meta.exists():
                for p in dnd_meta.rglob("*.json"):
                    arc = "dnd_meta/" + str(p.relative_to(dnd_meta))
                    zf.write(p, arc)
                    file_count += 1

        # 3. settings.json
        settings_file = PROJECT_ROOT / "WorldStitch" / "config" / "settings.json"
        if settings_file.exists():
            zf.write(settings_file, "config/settings.json")
            file_count += 1

        # 4. audit.log
        audit_log = PROJECT_ROOT / "logs" / "audit.log"
        if audit_log.exists():
            zf.write(audit_log, "logs/audit.log")
            file_count += 1

        # 5. AI usage log
        ai_log = PROJECT_ROOT / "WorldStitch" / "ai" / "ai_usage_log.csv"
        if ai_log.exists():
            zf.write(ai_log, "logs/ai_usage_log.csv")
            file_count += 1

        # 6. Global user/group data
        global_dir = Path("~/.worldstitch_ai").expanduser()
        if global_dir.exists():
            for p in global_dir.glob("*.json"):
                zf.write(p, f"global/{p.name}")
                file_count += 1

        # 7. Export manifest
        manifest = {
            "exported_at": datetime.now().isoformat(),
            "vault_path": str(vault_path),
            "file_count": file_count,
            "version": "1.0",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"\nExport complete: {file_count} files, {size_mb:.1f} MB")
    print(f"  -> {zip_path}")
    return zip_path


def restore_data(zip_path: Path, target: Path) -> None:
    """
    Restore data from a previously exported zip.
    """
    if not zip_path.exists():
        print(f"ERROR: Export file not found: {zip_path}")
        sys.exit(1)

    target.mkdir(parents=True, exist_ok=True)
    print(f"Restoring from: {zip_path}")
    print(f"  Target: {target}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Read manifest
        try:
            manifest = json.loads(zf.read("manifest.json"))
            print(f"  Export date: {manifest.get('exported_at', '?')}")
            print(f"  Files: {manifest.get('file_count', '?')}")
        except KeyError:
            print("  Warning: no manifest found in export")

        # Extract vault files
        vault_target = target / "vault"
        for name in zf.namelist():
            if name.startswith("vault/"):
                dest = vault_target / name[6:]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))

        # Extract .dnd_meta
        meta_target = vault_target / ".dnd_meta"
        for name in zf.namelist():
            if name.startswith("dnd_meta/"):
                dest = meta_target / name[9:]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))

        # Extract settings
        if "config/settings.json" in zf.namelist():
            settings_dest = target / "settings.json"
            settings_dest.write_bytes(zf.read("config/settings.json"))
            print(f"  Restored: settings.json -> {settings_dest}")

        # Extract logs
        for name in zf.namelist():
            if name.startswith("logs/"):
                dest = target / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))

    print(f"\nRestore complete -> {target}")
    print("Next steps:")
    print(f"  1. Set VAULT_PATH={vault_target} in your .env")
    print("  2. Copy global/ files to ~/.worldstitch_ai/ if needed")
    print("  3. Launch the app")


def main():
    parser = argparse.ArgumentParser(description="WorldStitch data export/restore tool")
    parser.add_argument("--output", type=Path, help="Directory to write the export zip")
    parser.add_argument("--restore", type=Path, help="Path to a zip file to restore from")
    parser.add_argument("--target", type=Path, default=Path("./restored"), help="Restore destination directory")
    args = parser.parse_args()

    if args.restore:
        restore_data(args.restore, args.target)
    elif args.output:
        export_data(args.output)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
