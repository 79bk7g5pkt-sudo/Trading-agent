#!/usr/bin/env python3
"""
Pre-flight check for trading-agent before live cycles.
Run this on the VPS: python3 preflight_check.py

Checks:
1. main.py syntax is valid (catches the line-192 paren issue, indentation breaks)
2. Folder casing matches imports (catches Core/ vs core/ mismatch)
3. No invisible Unicode chars (U+200B etc.) in .py files
4. Binance API keys are reachable and account is accessible
5. Cron file has correct entries (catches the "0 -> bullet point" corruption)
"""

import ast
import os
import sys
import subprocess

BASE_DIR = os.path.expanduser("~/trading-agent")
ISSUES = []
WARNINGS = []


def check_syntax(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source, filename=filepath)
        return True
    except SyntaxError as e:
        ISSUES.append(f"SYNTAX ERROR in {filepath}: line {e.lineno}: {e.msg}")
        return False
    except UnicodeDecodeError as e:
        ISSUES.append(f"ENCODING ERROR in {filepath}: {e}")
        return False


def check_invisible_unicode(filepath):
    suspicious = ["\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0"]
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        for char in suspicious:
            if char in content:
                count = content.count(char)
                ISSUES.append(
                    f"INVISIBLE UNICODE in {filepath}: found {count}x "
                    f"U+{ord(char):04X} — likely pasted from GitHub web editor"
                )
    except Exception as e:
        WARNINGS.append(f"Could not scan {filepath} for unicode: {e}")


def check_folder_casing():
    # Common offenders based on past issues
    expected_lower = ["core", "utils", "config"]
    for name in expected_lower:
        upper_variant = name.capitalize()
        upper_path = os.path.join(BASE_DIR, upper_variant)
        lower_path = os.path.join(BASE_DIR, name)
        if os.path.isdir(upper_path) and not os.path.isdir(lower_path):
            ISSUES.append(
                f"FOLDER CASING: found '{upper_variant}/' but code likely imports "
                f"'{name}/' (lowercase) — GitHub capitalized it again after reset"
            )


def check_all_python_files():
    py_files = []
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "venv", ".venv")]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))

    if not py_files:
        ISSUES.append(f"No .py files found under {BASE_DIR} — check the path")
        return

    print(f"Scanning {len(py_files)} Python files...\n")
    for fp in py_files:
        ok = check_syntax(fp)
        check_invisible_unicode(fp)
        status = "OK" if ok else "FAIL"
        print(f"  [{status}] {os.path.relpath(fp, BASE_DIR)}")


def check_execute_decision_indentation():
    """Specifically flag the recurring execute_decision / _live_trade indentation bug."""
    main_path = os.path.join(BASE_DIR, "main.py")
    if not os.path.exists(main_path):
        return
    with open(main_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if "def execute_decision" in line or "def _live_trade" in line:
            def_indent = len(line) - len(line.lstrip())
            # peek at next non-blank line
            for j in range(i + 1, min(i + 5, len(lines))):
                nxt = lines[j]
                if nxt.strip() == "":
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent <= def_indent:
                    ISSUES.append(
                        f"INDENTATION: '{line.strip()}' at main.py:{i+1} appears to have "
                        f"no indented body (next line has indent {nxt_indent} <= {def_indent})"
                    )
                break


def check_line_192_paren():
    main_path = os.path.join(BASE_DIR, "main.py")
    if not os.path.exists(main_path):
        return
    with open(main_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) >= 192:
        line = lines[191]
        if line.count(")") > line.count("("):
            WARNINGS.append(
                f"main.py:192 has more ')' than '(' — this is the recurring "
                f"extra-paren bug, double check: {line.strip()}"
            )


def check_cron():
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False
        )
        cron_content = result.stdout
        if "•" in cron_content or "●" in cron_content:
            ISSUES.append(
                "CRON CORRUPTION: bullet character found in crontab — "
                "Termius autocorrect likely replaced a '0'. Rewrite cron via Python."
            )
        # crude check for trading-agent entries
        if "trading-agent" not in cron_content and "main.py" not in cron_content:
            WARNINGS.append("No trading-agent cron entry found in crontab -l")
    except FileNotFoundError:
        WARNINGS.append("crontab command not found — skipping cron check")


def check_binance_connectivity():
    try:
        from binance.client import Client
    except ImportError:
        WARNINGS.append("python-binance not importable in this environment — skipping live API check")
        return

    api_key = os.environ.get("BINANCE_API_KEY")
    api_secret = os.environ.get("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        WARNINGS.append(
            "BINANCE_API_KEY/SECRET not in environment for this check — "
            "remember your bot loads them inline in cron, not from env, so this "
            "check won't reflect the cron run. Test manually if needed."
        )
        return

    try:
        client = Client(api_key, api_secret)
        client.get_account()
        print("  [OK] Binance API reachable and account accessible")
    except Exception as e:
        ISSUES.append(f"BINANCE API: could not reach account: {e}")


def main():
    print(f"=== Pre-flight check: {BASE_DIR} ===\n")

    if not os.path.isdir(BASE_DIR):
        print(f"ERROR: {BASE_DIR} does not exist. Edit BASE_DIR in this script if your path differs.")
        sys.exit(1)

    check_all_python_files()
    check_folder_casing()
    check_execute_decision_indentation()
    check_line_192_paren()
    check_cron()
    check_binance_connectivity()

    print("\n=== Results ===")
    if not ISSUES and not WARNINGS:
        print("All checks passed. Safe to run live cycles.")
        sys.exit(0)

    if WARNINGS:
        print(f"\n{len(WARNINGS)} warning(s):")
        for w in WARNINGS:
            print(f"  ⚠ {w}")

    if ISSUES:
        print(f"\n{len(ISSUES)} BLOCKING issue(s) — do not run live:")
        for i in ISSUES:
            print(f"  ✗ {i}")
        sys.exit(1)
    else:
        print("\nNo blocking issues, but review warnings above.")
        sys.exit(0)


if __name__ == "__main__":
    main()

