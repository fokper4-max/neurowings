#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilities for checking and applying desktop updates."""

import hashlib
import json
import re
import ssl
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:  # pragma: no cover - fallback when certifi is unavailable
    certifi = None


USER_AGENT = "NeuroWings-Updater/1.0"


class UpdateError(RuntimeError):
    """Raised when update metadata or download is invalid."""


def _version_key(version: str) -> tuple:
    parts = [int(part) for part in re.findall(r"\d+", str(version))]
    return tuple(parts or [0])


def is_newer_version(remote_version: str, local_version: str) -> bool:
    """Return True if remote_version is newer than local_version."""
    remote = _version_key(remote_version)
    local = _version_key(local_version)
    size = max(len(remote), len(local))
    remote += (0,) * (size - len(remote))
    local += (0,) * (size - len(local))
    return remote > local


def fetch_update_feed(feed_url: str, timeout: int = 5) -> dict:
    """Load and normalize update feed JSON."""
    request = Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        data = json.loads(response.read().decode("utf-8"))
    return normalize_update_info(data, feed_url)


def normalize_update_info(payload: dict, feed_url: str = "") -> dict:
    """Normalize different feed field names into a single structure."""
    version = str(payload.get("version") or payload.get("latest_version") or "").strip()
    if not version:
        raise UpdateError("В update-feed.json не указана версия.")

    download_url = str(
        payload.get("url")
        or payload.get("exe_url")
        or payload.get("download_url")
        or ""
    ).strip()
    notes = payload.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    elif not isinstance(notes, list):
        notes = []

    return {
        "feed_url": feed_url,
        "version": version,
        "download_url": download_url,
        "sha256": str(payload.get("sha256") or payload.get("checksum") or "").strip().lower(),
        "headline": str(payload.get("headline") or "").strip(),
        "published_at": str(payload.get("published_at") or "").strip(),
        "notes": [str(note).strip() for note in notes if str(note).strip()],
        "history": payload.get("history") or [],
        "raw": payload,
    }


def is_direct_download_url(url: str) -> bool:
    """Return True when URL points directly to an EXE file."""
    return urlparse(url).path.lower().endswith(".exe")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ssl_context():
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def download_update(info: dict, destination: Path, progress_callback=None, timeout: int = 30) -> Path:
    """Download the update EXE to destination."""
    download_url = info.get("download_url", "").strip()
    if not download_url:
        raise UpdateError("В update-feed.json не указана ссылка на EXE файл.")
    if not is_direct_download_url(download_url):
        raise UpdateError("Ссылка на обновление должна вести прямо на .exe файл.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".part")

    request = Request(download_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout, context=_ssl_context()) as response, temp_path.open("wb") as fh:
        total_header = response.headers.get("Content-Length")
        total_bytes = int(total_header) if total_header and total_header.isdigit() else 0
        downloaded = 0

        while True:
            chunk = response.read(1024 * 512)
            if not chunk:
                break
            fh.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total_bytes)

    temp_path.replace(destination)

    expected_sha256 = info.get("sha256", "").strip().lower()
    if expected_sha256:
        actual_sha256 = _sha256(destination)
        if actual_sha256 != expected_sha256:
            destination.unlink(missing_ok=True)
            raise UpdateError("Контрольная сумма обновления не совпадает.")

    return destination


def create_windows_update_script(downloaded_exe: Path, target_exe: Path, pid_to_wait: int) -> Path:
    """Create an elevated PowerShell script that replaces the running EXE."""
    script_dir = Path.home() / "AppData" / "Local" / "Temp" / "neurowings-updater"
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / "apply_update.ps1"

    source = str(downloaded_exe).replace("'", "''")
    target = str(target_exe).replace("'", "''")
    script = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid_to_wait}
$source = '{source}'
$target = '{target}'

for ($i = 0; $i -lt 600; $i++) {{
    if (-not (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue)) {{
        break
    }}
    Start-Sleep -Milliseconds 500
}}

Copy-Item -LiteralPath $source -Destination $target -Force
Start-Process -FilePath $target
Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
"""
    script_path.write_text(script, encoding="utf-8")
    return script_path


def launch_windows_update_script(script_path: Path) -> None:
    """Run the update script with elevation."""
    escaped_script = str(script_path).replace("'", "''")
    command = (
        "Start-Process -Verb RunAs -FilePath 'powershell.exe' "
        f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','{escaped_script}')"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=True,
    )
