#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Utilities for checking and applying desktop updates."""

import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .constants import (
    APP_GITHUB_RELEASES_API_URL,
    APP_GITHUB_RELEASES_HTML_URL,
    APP_UPDATE_FEED_URL,
)

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
    remote_str = str(remote_version or "").strip()
    if not re.fullmatch(r"[vV]?\d+(?:\.\d+)*", remote_str):
        return False
    remote = _version_key(remote_str)
    local = _version_key(local_version)
    size = max(len(remote), len(local))
    remote += (0,) * (size - len(remote))
    local += (0,) * (size - len(local))
    return remote > local


def fetch_update_feed(feed_url: str = "", timeout: int = 8) -> dict:
    """Load and normalize update feed JSON (tries GitHub Releases API first, then fallback feed)."""
    if isinstance(feed_url, (list, tuple)):
        candidate_urls = [str(u).strip() for u in feed_url if str(u).strip()]
    else:
        url_str = str(feed_url or "").strip()
        if not url_str or url_str in (APP_UPDATE_FEED_URL, APP_GITHUB_RELEASES_API_URL):
            candidate_urls = []
            for u in (APP_GITHUB_RELEASES_API_URL, APP_UPDATE_FEED_URL):
                if u and u not in candidate_urls:
                    candidate_urls.append(u)
        else:
            candidate_urls = [url_str]

    last_exc = None
    for url in candidate_urls:
        try:
            headers = {
                "User-Agent": USER_AGENT,
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
            if "api.github.com" in url:
                headers["Accept"] = "application/vnd.github+json"
            request = Request(url, headers=headers)
            with urlopen(request, timeout=timeout, context=_ssl_context()) as response:
                data = json.loads(response.read().decode("utf-8"))
            info = normalize_update_info(data, url)
            if not info.get("sha256") and info.get("sha256_url"):
                try:
                    sha_req = Request(info["sha256_url"], headers={"User-Agent": USER_AGENT})
                    with urlopen(sha_req, timeout=min(timeout, 5), context=_ssl_context()) as sha_resp:
                        sha_text = sha_resp.read(4096).decode("utf-8", errors="ignore")
                    m = re.search(r"\b([a-fA-F0-9]{64})\b", sha_text)
                    if m:
                        info["sha256"] = m.group(1).lower()
                except Exception:
                    pass
            return info
        except Exception as exc:
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise UpdateError("Не удалось загрузить информацию об обновлениях.")


def normalize_update_info(payload: dict, feed_url: str = "") -> dict:
    """Normalize different feed field names (including GitHub Releases JSON) into a single structure."""
    if isinstance(payload, list) and payload:
        payload = payload[0]
    if not isinstance(payload, dict):
        raise UpdateError("Некорректный формат ответа сервера обновлений.")

    raw_version = str(
        payload.get("version")
        or payload.get("latest_version")
        or payload.get("tag_name")
        or ""
    ).strip()
    version = re.sub(r"^[vV]\s*", "", raw_version).strip()
    if not version:
        raise UpdateError("В update-feed.json не указана версия.")

    assets = payload.get("assets")
    is_github_payload = bool(payload.get("tag_name") or isinstance(assets, list))
    exe_asset = None
    sha256_asset_url = ""
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            aname = str(asset.get("name") or "").strip()
            burl = str(asset.get("browser_download_url") or asset.get("url") or "").strip()
            if aname.lower().endswith(".exe") and burl and exe_asset is None:
                exe_asset = asset
            if (
                aname.lower().endswith(".sha256")
                or aname.lower().endswith(".sha256sum")
                or ("sha256" in aname.lower() and aname.lower().endswith(".txt"))
            ) and burl and not sha256_asset_url:
                sha256_asset_url = burl

    raw_url = str(payload.get("url") or "").strip()
    if is_github_payload and "api.github.com" in raw_url:
        raw_url = ""

    download_url = str(
        payload.get("exe_url")
        or payload.get("download_url")
        or (exe_asset.get("browser_download_url") if exe_asset else "")
        or raw_url
        or payload.get("html_url")
        or ""
    ).strip()

    # Извлечение SHA256: 1) поле sha256/checksum, 2) digest ассета GitHub ("sha256:..."), 3) текст body
    sha256 = ""
    raw_sha = str(payload.get("sha256") or payload.get("checksum") or "").strip()
    m_sha = re.search(r"\b([a-fA-F0-9]{64})\b", raw_sha)
    if m_sha:
        sha256 = m_sha.group(1).lower()

    if not sha256 and exe_asset:
        digest_str = str(exe_asset.get("digest") or exe_asset.get("sha256") or "").strip()
        m_dig = re.search(r"\b([a-fA-F0-9]{64})\b", digest_str)
        if m_dig:
            sha256 = m_dig.group(1).lower()

    body = str(payload.get("body") or "").strip()
    if not sha256 and body:
        m_body = re.search(r"\b([a-fA-F0-9]{64})\b", body)
        if m_body:
            sha256 = m_body.group(1).lower()

    headline = str(payload.get("headline") or "").strip()
    if not headline and payload.get("name"):
        rel_name = str(payload.get("name") or "").strip()
        if rel_name and re.sub(r"^[vV]\s*", "", rel_name) != version:
            headline = rel_name

    notes = payload.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    elif not isinstance(notes, list):
        notes = []
    notes = [str(note).strip() for note in notes if str(note).strip()]

    if not notes and body:
        parsed_notes = []
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("```"):
                continue
            is_heading = line.startswith("#")
            line = re.sub(r"^#{1,6}\s*", "", line)
            line = re.sub(r"^[-*•]\s+", "", line)
            line = line.replace("**", "").strip()
            if not line:
                continue
            if re.fullmatch(r"(?:sha256\s*[:=]\s*)?[a-fA-F0-9]{64}(?:\s+\S+)?", line, flags=re.IGNORECASE):
                continue
            if is_heading and not headline and not parsed_notes and len(line) < 120:
                headline = line
                continue
            parsed_notes.append(line)
        notes = parsed_notes

    published_at = str(payload.get("published_at") or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T", published_at):
        published_at = published_at[:10]

    asset_size = int(exe_asset.get("size") or 0) if exe_asset else int(payload.get("size") or 0)
    html_url = str(payload.get("html_url") or APP_GITHUB_RELEASES_HTML_URL).strip()

    return {
        "feed_url": feed_url,
        "version": version,
        "download_url": download_url,
        "html_url": html_url,
        "sha256": sha256,
        "sha256_url": sha256_asset_url,
        "asset_size": asset_size,
        "headline": headline,
        "published_at": published_at,
        "notes": notes,
        "body": body,
        "history": payload.get("history") or [],
        "source": "github" if (is_github_payload or "github.com" in str(feed_url)) else "feed",
        "raw": payload,
    }


def _is_trusted_github_url(url: str) -> bool:
    """Return True if URL points to official GitHub release download domains."""
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    return (
        parsed.scheme == "https"
        and (
            host == "github.com"
            or host.endswith(".github.com")
            or host == "githubusercontent.com"
            or host.endswith(".githubusercontent.com")
        )
    )


def is_direct_download_url(url: str) -> bool:
    """Return True when URL points directly to an EXE file."""
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.path.lower().endswith(".exe")


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

    expected = str(info.get("sha256") or "").strip().lower()
    is_github_dl = _is_trusted_github_url(download_url)
    if expected:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", expected):
            raise UpdateError("Для обновления обязательна корректная SHA256.")
    elif not is_github_dl:
        raise UpdateError("Для обновления обязательна корректная SHA256.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".part")

    request = Request(download_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout, context=_ssl_context()) as response, temp_path.open("wb") as fh:
        total_header = response.headers.get("Content-Length")
        total_bytes = int(total_header) if total_header and total_header.isdigit() else int(info.get("asset_size") or 0)
        downloaded = 0

        while True:
            chunk = response.read(1024 * 512)
            if not chunk:
                break
            fh.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total_bytes)

    if expected:
        actual_sha256 = _sha256(temp_path)
        if actual_sha256 != expected:
            temp_path.unlink(missing_ok=True)
            raise UpdateError("Контрольная сумма обновления не совпадает.")
    else:
        # Для GitHub Releases без SHA256 проверяем размер (> 1 МБ) и PE-заголовок MZ
        actual_size = temp_path.stat().st_size
        with temp_path.open("rb") as fh:
            magic = fh.read(2)
        if actual_size <= 1_000_000 or magic != b"MZ":
            temp_path.unlink(missing_ok=True)
            raise UpdateError("Скачанный EXE-файл повреждён или имеет недопустимый размер.")

    temp_path.replace(destination)
    return destination


def create_windows_update_script(downloaded_exe: Path, target_exe: Path, pid_to_wait: int) -> Path:
    """Create a PowerShell script that replaces the running EXE and restarts the app."""
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

if (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{ throw 'Application is still running' }}
$backup = $target + '.previous'
Copy-Item -LiteralPath $target -Destination $backup -Force
try {{ Copy-Item -LiteralPath $source -Destination $target -Force }}
catch {{ Copy-Item -LiteralPath $backup -Destination $target -Force; throw }}
Start-Process -FilePath $target
Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
"""
    script_path.write_text(script, encoding="utf-8")
    return script_path


def launch_windows_update_script(script_path: Path, target_exe: Path = None) -> None:
    """Run the update script directly if target directory is writable, or with RunAs elevation as fallback."""
    target_path = Path(target_exe) if target_exe is not None else Path(sys.executable)
    target_dir = target_path.resolve().parent
    can_write = os.access(target_dir, os.W_OK)

    if can_write:
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
        try:
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-WindowStyle", "Hidden",
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    "-File", str(script_path),
                ],
                creationflags=creationflags,
                close_fds=True,
            )
            return
        except OSError:
            pass

    escaped_script = str(script_path).replace("'", "''")
    command = (
        "Start-Process -Verb RunAs -FilePath 'powershell.exe' "
        f"-ArgumentList @('-WindowStyle','Hidden','-NoProfile','-ExecutionPolicy','Bypass','-File','{escaped_script}')"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        check=True,
    )
