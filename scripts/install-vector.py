#!/usr/bin/env python3
"""Universal Vector installer for Linux, macOS, Windows, and WSL.

The script uses only Python's standard library for bootstrapping and delegates
Hermes core installation to the platform-native Hermes installer already shipped
in this repository.
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

REPO = "stoltembergg-png/hermes-agent"
BRANCH = "main"
PLUGIN = "vector-channels"
REMOTE_BASE = f"https://raw.githubusercontent.com/{REPO}/main/scripts"


def log(message: str) -> None:
    print(f"[vector-install] {message}")


def run(command: list[str], *, cwd: Path | None = None, dry_run: bool = False) -> None:
    log("$ " + " ".join(command))
    if not dry_run:
        subprocess.run(command, cwd=cwd, check=True)


def hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "hermes"
    return Path.home() / ".hermes"


def local_repository() -> Path | None:
    script_path = globals().get("__file__")
    if not script_path:
        return None
    candidate = Path(script_path).resolve().parent.parent
    if (candidate / "apps/desktop/src/plugins/vector-channels").is_dir():
        return candidate
    return None


def native_hermes_installer(source: Path) -> Path:
    if os.name == "nt":
        return source / "scripts/install.ps1"
    return source / "scripts/install.sh"


def ensure_hermes(source: Path, *, dry_run: bool) -> None:
    if shutil.which("hermes"):
        log("Hermes CLI found")
        return
    installer = native_hermes_installer(source)
    if not installer.exists():
        if dry_run:
            log(f"would invoke native Hermes installer for {platform.system()}")
            return
        raise RuntimeError(f"Hermes installer not found: {installer}")
    log("Hermes CLI not found; invoking the native Hermes installer")
    if os.name == "nt":
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            raise RuntimeError("PowerShell is required on Windows")
        run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer)],
            dry_run=dry_run,
        )
    else:
        shell = shutil.which("bash")
        if not shell:
            raise RuntimeError("bash is required on Linux/macOS/WSL")
        run([shell, str(installer)], dry_run=dry_run)


def acquire_source(explicit: Path | None, branch: str, temp_root: Path, *, dry_run: bool) -> Path:
    source = explicit or local_repository()
    if source:
        return source.resolve()
    target = temp_root / "hermes-agent"
    run(["git", "clone", "--depth", "1", "--branch", branch, f"https://github.com/{REPO}.git", str(target)], dry_run=dry_run)
    return target


def copy_tree(source: Path, destination: Path, *, dry_run: bool) -> None:
    if not source.is_dir():
        if dry_run:
            log(f"would copy {source} -> {destination}")
            return
        raise RuntimeError(f"required source directory missing: {source}")
    if dry_run:
        log(f"copy {source} -> {destination}")
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def install_frontend(source: Path, home: Path, *, dry_run: bool) -> None:
    node = shutil.which("node")
    npm = shutil.which("npm")
    plugin_source = source / "apps/desktop/src/plugins/vector-channels"
    if not node or not npm or not plugin_source.is_dir():
        if dry_run and not plugin_source.is_dir():
            log(f"would build frontend from {plugin_source}")
        log("Node.js 22+ or frontend source unavailable; frontend skipped")
        return
    if not dry_run:
        major = int(
            subprocess.check_output(
                [node, "--version"],
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            .lstrip("v")
            .split(".", 1)[0]
        )
        if major < 22:
            log("Node.js 22+ required; frontend skipped")
            return
    build = Path(tempfile.mkdtemp(prefix="vector-plugin-build-"))
    try:
        src = build / "src"
        src.mkdir()
        for filename in ("plugin.tsx", "api.ts", "vector-channels.css"):
            shutil.copy2(plugin_source / filename, src / filename)
        (build / "package.json").write_text(
            '{"name":"vector-channels-build","private":true,"type":"module",'
            '"scripts":{"build":"vite build"},"dependencies":{"react":"^18.3.0"},'
            '"devDependencies":{"typescript":"^5.5.0","vite":"^5.4.0"}}\n',
            encoding="utf-8",
        )
        (build / "vite.config.ts").write_text(
            "import { defineConfig } from 'vite';\n"
            "import { resolve } from 'path';\n"
            "export default defineConfig({build:{lib:{entry:resolve(__dirname,'src/plugin.tsx'),formats:['es'],fileName:'plugin'},outDir:'dist',emptyOutDir:true,rollupOptions:{external:['react','react-dom','@hermes/plugin-sdk']}}});\n",
            encoding="utf-8",
        )
        run([npm, "install", "--silent", "--no-audit", "--no-fund"], cwd=build, dry_run=dry_run)
        run([npm, "run", "build"], cwd=build, dry_run=dry_run)
        destination = home / "desktop-plugins" / PLUGIN
        if dry_run:
            log(f"install frontend build -> {destination}")
        elif (build / "dist/plugin.js").is_file():
            destination.mkdir(parents=True, exist_ok=True)
            for item in (build / "dist").iterdir():
                target = destination / item.name
                shutil.copytree(item, target, dirs_exist_ok=True) if item.is_dir() else shutil.copy2(item, target)
    finally:
        if not dry_run:
            shutil.rmtree(build, ignore_errors=True)


def install_hook(home: Path, *, dry_run: bool) -> None:
    hooks = home / "hooks"
    if os.name == "nt":
        path = hooks / "post-update.ps1"
        content = f"# Reinstall Vector after Hermes updates\npython -c \"import urllib.request; exec(compile(urllib.request.urlopen('{REMOTE_BASE}/install-vector.py').read(), 'install-vector.py', 'exec'))\"\n"
    else:
        path = hooks / "post-update.sh"
        content = f"#!/usr/bin/env bash\nset -eu\npython3 -c \"import urllib.request; exec(compile(urllib.request.urlopen('{REMOTE_BASE}/install-vector.py').read(), 'install-vector.py', 'exec'))\"\n"
    if dry_run:
        log(f"write update hook -> {path}")
        return
    hooks.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)


def install(source: Path, *, dry_run: bool) -> None:
    home = hermes_home()
    ensure_hermes(source, dry_run=dry_run)
    copy_tree(source / "plugins/vector-channels/dashboard", home / "plugins" / PLUGIN, dry_run=dry_run)
    copy_tree(source / "vector/src/vector", home / "vector", dry_run=dry_run)
    copy_tree(source / "vector/tests", home / "vector/tests", dry_run=dry_run)
    install_frontend(source, home, dry_run=dry_run)
    run(["hermes", "plugins", "enable", PLUGIN], dry_run=dry_run)
    install_hook(home, dry_run=dry_run)
    log(f"installation complete: {home}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="use an existing hermes-agent checkout")
    parser.add_argument("--branch", default=BRANCH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vector-install-") as temporary:
        source = acquire_source(args.source, args.branch, Path(temporary), dry_run=args.dry_run)
        install(source, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
