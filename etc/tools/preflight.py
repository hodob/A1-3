"""Zero-provider-token deployment preflight for the AI Debate Harness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def _result(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def collect_static_checks(root: Path = ROOT) -> list[dict]:
    checks: list[dict] = []

    required = [
        "public/index.html", "public/styles.css", "public/app.js", "public/robots.txt",
        "api/analyze_topic.py", "api/context_step.py", "api/create_motion.py",
        "api/debate_step.py", "api/neutral_summary.py", "api/health.py", "api/_base.py",
        "src/web_app/api.py", "src/web_app/live_service.py", "src/web_app/session_token.py",
        "vercel.json", "pyproject.toml", "requirements.txt", "config.json", ".env.example", ".vercelignore",
    ]
    missing = [name for name in required if not (root / name).exists()]
    checks.append(_result("required_files", not missing, "missing=" + ",".join(missing) if missing else "all present"))

    try:
        config = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
        duration = config.get("functions", {}).get("api/*.py", {}).get("maxDuration", 0)
        rewrites = config.get("rewrites", [])
        checks.append(_result("vercel_json", duration >= 120 and bool(rewrites), f"maxDuration={duration}, rewrites={len(rewrites)}"))
    except Exception as exc:
        checks.append(_result("vercel_json", False, type(exc).__name__))

    public_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (root / "public").glob("*") if path.is_file()
    ).lower()
    forbidden = [token for token in ("api_key", "authorization", "bearer ", "sk-") if token in public_text]
    checks.append(_result("frontend_secret_scan", not forbidden, "found=" + ",".join(forbidden) if forbidden else "clean"))

    env_example = (root / ".env.example").read_text(encoding="utf-8", errors="replace") if (root / ".env.example").exists() else ""
    env_keys = {
        line.split("=", 1)[0].strip()
        for line in env_example.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    try:
        runtime = json.loads((root / "config.json").read_text(encoding="utf-8"))
        serialized = json.dumps(runtime).lower()
        split_ok = env_keys == {"DEBATER_API_KEY", "SESSION_SECRET"} and all(
            key in runtime for key in ("web_mode", "provider")
        ) and all(key in runtime.get("provider", {}) for key in ("url", "model")) and not any(
            marker in serialized for marker in ("api_key", "session_secret", "secret")
        )
        detail = "secrets=.env, runtime=config.json" if split_ok else f"env_keys={sorted(env_keys)}"
    except Exception as exc:
        split_ok, detail = False, type(exc).__name__
    checks.append(_result("config_secret_split", split_ok, detail))

    try:
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        pinned = 'requires-python = "~=3.12.0"' in pyproject
        checks.append(_result("python_runtime_pin", pinned, "Python ~=3.12.0" if pinned else "Python version not pinned"))
    except Exception as exc:
        checks.append(_result("python_runtime_pin", False, type(exc).__name__))

    return checks


def _run(command: list[str], root: Path) -> dict:
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    detail = (result.stdout + result.stderr).strip()
    if len(detail) > 1200:
        detail = detail[-1200:]
    return _result(" ".join(command), result.returncode == 0, detail or "OK")


def run_preflight(root: Path = ROOT, *, run_tests: bool = True) -> dict:
    checks = collect_static_checks(root)
    if run_tests:
        checks.append(_run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], root))
        checks.append(_run([sys.executable, "-m", "compileall", "-q", "api", "src", "etc/tools"], root))
        node = shutil.which("node")
        checks.append(_run([node, "--check", "public/app.js"], root) if node else _result("node --check public/app.js", True, "SKIPPED: node not installed"))
    return {"status": "PASS" if all(x["ok"] for x in checks) else "FAIL", "provider_calls": 0, "provider_tokens": 0, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run zero-token deployment preflight checks")
    parser.add_argument("--static-only", action="store_true", help="Skip unittest/compile/Node subprocess checks")
    args = parser.parse_args(argv)
    report = run_preflight(ROOT, run_tests=not args.static_only)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
