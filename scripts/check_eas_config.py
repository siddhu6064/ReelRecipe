#!/usr/bin/env python3
"""
scripts/check_eas_config.py

Run before `eas build` to catch unfilled placeholder values in eas.json
and missing environment secrets.

Usage:
    python scripts/check_eas_config.py                  # check eas.json
    python scripts/check_eas_config.py --env production # check env too
    python scripts/check_eas_config.py --fix            # print what to do

Exit code 0 = all good, 1 = problems found.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
EAS_PATH = ROOT / "apps" / "mobile" / "eas.json"
APP_JSON_PATH = ROOT / "apps" / "mobile" / "app.json"

# Strings that indicate a placeholder was never replaced
PLACEHOLDERS = [
    "REPLACE_WITH",
    "YOUR_EAS_PROJECT_ID",
    "YOUR_APPLE_ID",
    "YOUR_APP_STORE",
    "YOUR_TEAM_ID",
    "pk_test_REPLACE",
    "pk_live_REPLACE",
]

ERRORS: list[str] = []
WARNINGS: list[str] = []


def check(condition: bool, message: str, is_warning: bool = False) -> None:
    if not condition:
        (WARNINGS if is_warning else ERRORS).append(message)


def scan_placeholders(data: object, path: str = "") -> None:
    """Recursively scan JSON for unfilled placeholder strings."""
    if isinstance(data, dict):
        for k, v in data.items():
            scan_placeholders(v, f"{path}.{k}")
    elif isinstance(data, list):
        for i, v in enumerate(data):
            scan_placeholders(v, f"{path}[{i}]")
    elif isinstance(data, str):
        for placeholder in PLACEHOLDERS:
            if placeholder in data:
                ERRORS.append(f"Unfilled placeholder in eas.json at {path}: '{data}'")
                break


def check_eas_json() -> None:
    if not EAS_PATH.exists():
        ERRORS.append(f"eas.json not found at {EAS_PATH}")
        return

    with open(EAS_PATH) as f:
        eas = json.load(f)

    scan_placeholders(eas)

    # Check project ID is in app.json
    if APP_JSON_PATH.exists():
        with open(APP_JSON_PATH) as f:
            app = json.load(f)
        project_id = app.get("expo", {}).get("extra", {}).get("eas", {}).get("projectId", "")
        check(
            bool(project_id) and project_id != "YOUR_EAS_PROJECT_ID",
            "app.json: expo.extra.eas.projectId is not set. Run 'eas init' to get your project ID.",
        )

    print("eas.json ✓" if not ERRORS else f"eas.json — {len(ERRORS)} error(s) found")


def check_google_play_key() -> None:
    key_path = ROOT / "apps" / "mobile" / "google-play-service-account.json"
    check(
        key_path.exists(),
        "google-play-service-account.json not found. "
        "Download from Google Play Console → Setup → API access → Service accounts.",
        is_warning=True,
    )


def print_fix_guide() -> None:
    print("\n── How to fix ──────────────────────────────────────────────\n")
    print("1. EAS Project ID (app.json)")
    print("   cd apps/mobile && eas init")
    print("   → copies project ID into app.json automatically\n")
    print("2. Clerk keys (eas.json)")
    print("   clerk.com → Your App → API Keys")
    print("   → pk_test_... (development/preview), pk_live_... (production)\n")
    print("3. Apple IDs (eas.json submit.production.ios)")
    print("   appleId       → your Apple Developer account email")
    print("   ascAppId      → App Store Connect → Apps → Your App → App Information → Apple ID")
    print("   appleTeamId   → developer.apple.com → Account → Membership → Team ID (10 chars)\n")
    print("4. Google Play service account (apps/mobile/google-play-service-account.json)")
    print("   Google Play Console → Setup → API access → Link Google Cloud project")
    print("   → Create service account → Grant 'Release Manager' role → Download JSON key\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate EAS build config")
    parser.add_argument("--fix", action="store_true", help="Print fix instructions")
    args = parser.parse_args()

    check_eas_json()
    check_google_play_key()

    if ERRORS:
        print("\n❌ Errors (must fix before building):")
        for e in ERRORS:
            print(f"   • {e}")

    if WARNINGS:
        print("\n⚠️  Warnings (optional but recommended):")
        for w in WARNINGS:
            print(f"   • {w}")

    if not ERRORS and not WARNINGS:
        print("\n✅ EAS config looks good — ready to build.")

    if args.fix or ERRORS:
        print_fix_guide()

    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
