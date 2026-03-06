#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build release metadata and publish NeuroWings artifacts to the update server."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import posixpath
import re
import sys
from datetime import date
from pathlib import Path
from typing import Iterable, List


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERVER_HOST = "193.124.117.175"
DEFAULT_SERVER_PORT = 22
DEFAULT_SERVER_USER = "root"
DEFAULT_REMOTE_DIR = "/opt/max-control/public/downloads/neurowings"
DEFAULT_PUBLIC_BASE_URL = "https://193-124-117-175.nip.io/downloads/neurowings"
DEFAULT_APP_NAME = "НейроКрылья"
DOCUMENTATION_FILES = [
    ("README.md", "README.md"),
    ("CHANGELOG.md", "CHANGELOG.md"),
    ("installer/README.md", "installer/README.md"),
    ("installer/UPDATE_GUIDE.md", "installer/UPDATE_GUIDE.md"),
    ("installer/CHANGELOG.md", "installer/CHANGELOG.md"),
    ("models/README.txt", "models/README.txt"),
    ("docs/RELEASE_SYSTEM.md", "RELEASE_SYSTEM.md"),
]


class PublishError(RuntimeError):
    """Raised when the release cannot be published safely."""


def _version_key(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", str(value))]
    return tuple(parts or [0])


def normalize_version(value: str) -> str:
    return ".".join(str(part) for part in _version_key(value))


def versions_match(left: str, right: str) -> bool:
    lhs = _version_key(left)
    rhs = _version_key(right)
    size = max(len(lhs), len(rhs))
    lhs += (0,) * (size - len(lhs))
    rhs += (0,) * (size - len(rhs))
    return lhs == rhs


def extract_value(path: Path, pattern: str, field_name: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise PublishError(f"Не удалось найти {field_name} в {path}.")
    return match.group(1).strip()


def current_app_version() -> str:
    return extract_value(
        PROJECT_ROOT / "neurowings" / "core" / "constants.py",
        r'^APP_VERSION\s*=\s*"([^"]+)"',
        "APP_VERSION",
    )


def installer_version() -> str:
    return extract_value(
        PROJECT_ROOT / "installer" / "installer.nsi",
        r'!define\s+PRODUCT_VERSION\s+"([^"]+)"',
        "PRODUCT_VERSION",
    )


def _collect_release_notes(lines: Iterable[str]) -> List[str]:
    notes: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            note = stripped[2:].strip()
            if note:
                notes.append(note)
    return notes


def extract_release_notes(changelog_path: Path, version: str) -> List[str]:
    if not changelog_path.exists():
        return []

    lines = changelog_path.read_text(encoding="utf-8").splitlines()
    notes: List[str] = []
    capture = False
    current_section = ""
    ignored_sections = {"excluded"}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ["):
            match = re.match(r"## \[([^\]]+)\]", stripped)
            if not match:
                continue
            capture = versions_match(match.group(1), version)
            if capture:
                notes = []
                current_section = ""
            elif notes:
                break
            continue

        if capture and stripped.startswith("## ["):
            break
        if capture and stripped.startswith("### "):
            current_section = stripped[4:].strip().lower()
            continue
        if capture:
            if current_section in ignored_sections:
                continue
            notes.extend(_collect_release_notes([line]))

    return notes


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_feed(version: str, download_name: str, setup_name: str | None, headline: str, notes: List[str], base_url: str) -> dict:
    feed = {
        "app_name": DEFAULT_APP_NAME,
        "version": version,
        "published_at": str(date.today()),
        "headline": headline,
        "download_url": f"{base_url.rstrip('/')}/{download_name}",
        "sha256": "",
        "notes": notes,
    }
    if setup_name:
        feed["setup_url"] = f"{base_url.rstrip('/')}/{setup_name}"
    return feed


def collect_documentation_files() -> list[tuple[Path, str]]:
    docs: list[tuple[Path, str]] = []
    missing: list[str] = []
    for source_relative, target_relative in DOCUMENTATION_FILES:
        path = (PROJECT_ROOT / source_relative).resolve()
        if not path.exists():
            missing.append(source_relative)
            continue
        docs.append((path, target_relative.replace("\\", "/")))
    if missing:
        raise PublishError(
            "Не найдены обязательные файлы документации: " + ", ".join(missing)
        )
    return docs


def build_docs_manifest(
    version: str,
    docs_base_url: str,
    public_base_url: str,
    docs: list[tuple[Path, str]],
) -> dict:
    files = []
    for local_path, relative_path in docs:
        files.append(
            {
                "path": relative_path,
                "url": f"{docs_base_url.rstrip('/')}/{relative_path}",
                "sha256": sha256sum(local_path),
                "size": local_path.stat().st_size,
            }
        )
    return {
        "generated_at": str(date.today()),
        "version": version,
        "docs_base_url": docs_base_url.rstrip("/"),
        "update_feed_url": f"{public_base_url.rstrip('/')}/update-feed.json",
        "latest_exe_url": f"{public_base_url.rstrip('/')}/NeuroWings-latest.exe",
        "files": files,
    }


def ensure_paramiko():
    try:
        import paramiko  # type: ignore
    except ImportError as exc:
        raise PublishError(
            "Для публикации нужен пакет paramiko. Установите его командой "
            "'python -m pip install paramiko' или используйте build_and_publish.ps1."
        ) from exc
    return paramiko


def sftp_mkdir_p(sftp, remote_dir: str) -> None:
    remote_dir = remote_dir.rstrip("/")
    parts = [part for part in remote_dir.split("/") if part]
    current = ""
    for part in parts:
        current = f"{current}/{part}"
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def sftp_upload_bytes(sftp, remote_path: str, payload: bytes) -> None:
    temp_path = f"{remote_path}.tmp"
    try:
        sftp.remove(temp_path)
    except OSError:
        pass
    with sftp.file(temp_path, "wb") as remote_file:
        remote_file.write(payload)
    try:
        sftp.remove(remote_path)
    except OSError:
        pass
    sftp.rename(temp_path, remote_path)


def sftp_upload_file(sftp, local_path: Path, remote_path: str) -> None:
    temp_path = f"{remote_path}.tmp"
    try:
        sftp.remove(temp_path)
    except OSError:
        pass
    sftp.put(str(local_path), temp_path)
    try:
        sftp.remove(remote_path)
    except OSError:
        pass
    sftp.rename(temp_path, remote_path)


def upload_documentation(sftp, remote_dir: str, public_base_url: str, version: str) -> dict:
    docs = collect_documentation_files()
    docs_remote_dir = f"{remote_dir.rstrip('/')}/docs"
    docs_base_url = f"{public_base_url.rstrip('/')}/docs"
    sftp_mkdir_p(sftp, docs_remote_dir)

    for local_path, relative_path in docs:
        remote_path = posixpath.join(docs_remote_dir, relative_path)
        sftp_mkdir_p(sftp, posixpath.dirname(remote_path))
        sftp_upload_file(sftp, local_path, remote_path)

    manifest = build_docs_manifest(
        version=version,
        docs_base_url=docs_base_url,
        public_base_url=public_base_url,
        docs=docs,
    )
    sftp_upload_bytes(
        sftp,
        f"{docs_remote_dir}/index.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
    )
    return manifest


def publish(args) -> None:
    version = args.version or current_app_version()
    nsi_version = installer_version()
    if not versions_match(version, nsi_version):
        raise PublishError(
            f"Версия приложения ({version}) не совпадает с installer.nsi ({nsi_version})."
        )

    summary = {
        "mode": "docs-only" if args.docs_only else "release",
        "version": version,
        "remote_dir": args.remote_dir,
        "docs_url": f"{args.public_base_url.rstrip('/')}/docs/index.json",
    }

    exe_path: Path | None = None
    setup_path: Path | None = None
    feed: dict | None = None
    remote_exe_path = ""
    remote_latest_exe_path = ""
    remote_feed_path = f"{args.remote_dir.rstrip('/')}/update-feed.json"
    remote_setup_path: str | None = None
    remote_latest_setup_path: str | None = None

    if not args.docs_only:
        if not args.exe:
            raise PublishError("Для публикации релиза нужен --exe.")
        exe_path = Path(args.exe).resolve()
        if not exe_path.exists():
            raise PublishError(f"EXE не найден: {exe_path}")

        setup_path = Path(args.setup).resolve() if args.setup else None
        if setup_path and not setup_path.exists():
            raise PublishError(f"Setup не найден: {setup_path}")

        changelog_notes = extract_release_notes(PROJECT_ROOT / "CHANGELOG.md", version)
        notes = [note.strip() for note in (args.note or []) if note.strip()]
        if not notes:
            notes = changelog_notes
        if not notes:
            notes = [f"Обновление версии {version}."]

        headline = args.headline.strip() if args.headline else notes[0]
        upload_exe_name = f"NeuroWings-{version}.exe"
        upload_setup_name = f"NeuroWings-{version}-Setup.exe" if setup_path else None
        latest_exe_name = "NeuroWings-latest.exe"
        latest_setup_name = "NeuroWings-latest-Setup.exe" if setup_path else None
        feed = build_feed(
            version=version,
            download_name=upload_exe_name,
            setup_name=upload_setup_name,
            headline=headline,
            notes=notes,
            base_url=args.public_base_url,
        )
        feed["sha256"] = sha256sum(exe_path)
        feed["latest_url"] = f"{args.public_base_url.rstrip('/')}/{latest_exe_name}"

        remote_exe_path = f"{args.remote_dir.rstrip('/')}/{upload_exe_name}"
        remote_latest_exe_path = f"{args.remote_dir.rstrip('/')}/{latest_exe_name}"
        remote_setup_path = (
            f"{args.remote_dir.rstrip('/')}/{upload_setup_name}" if upload_setup_name else None
        )
        remote_latest_setup_path = (
            f"{args.remote_dir.rstrip('/')}/{latest_setup_name}" if latest_setup_name else None
        )

        summary.update(
            {
                "exe": str(exe_path),
                "setup": str(setup_path) if setup_path else None,
                "download_url": feed["download_url"],
                "feed": feed,
            }
        )

    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    password = args.server_password or os.getenv("NEUROWINGS_SERVER_PASSWORD")
    if not password:
        password = getpass.getpass(f"Пароль для {args.server_user}@{args.server_host}: ")

    paramiko = ensure_paramiko()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.server_host,
        port=args.server_port,
        username=args.server_user,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=15,
    )

    try:
        sftp = client.open_sftp()
        try:
            sftp_mkdir_p(sftp, args.remote_dir)
            if exe_path and feed:
                sftp_upload_file(sftp, exe_path, remote_exe_path)
                sftp_upload_file(sftp, exe_path, remote_latest_exe_path)
                if setup_path and remote_setup_path:
                    sftp_upload_file(sftp, setup_path, remote_setup_path)
                if setup_path and remote_latest_setup_path:
                    sftp_upload_file(sftp, setup_path, remote_latest_setup_path)
                sftp_upload_bytes(
                    sftp,
                    remote_feed_path,
                    json.dumps(feed, ensure_ascii=False, indent=2).encode("utf-8"),
                )
            docs_manifest = upload_documentation(
                sftp=sftp,
                remote_dir=args.remote_dir,
                public_base_url=args.public_base_url,
                version=version,
            )
            summary["docs_manifest"] = docs_manifest
        finally:
            sftp.close()
    finally:
        client.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("Публикация завершена.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", help="Path to the built EXE")
    parser.add_argument("--setup", help="Path to the setup EXE")
    parser.add_argument("--version", help="Release version; defaults to APP_VERSION")
    parser.add_argument("--headline", help="Short release headline")
    parser.add_argument("--note", action="append", default=[], help="Release note line")
    parser.add_argument("--docs-only", action="store_true", help="Upload only documentation")
    parser.add_argument("--server-host", default=DEFAULT_SERVER_HOST)
    parser.add_argument("--server-port", type=int, default=DEFAULT_SERVER_PORT)
    parser.add_argument("--server-user", default=DEFAULT_SERVER_USER)
    parser.add_argument("--server-password", help="Server password; optional if env or prompt is used")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR)
    parser.add_argument("--public-base-url", default=DEFAULT_PUBLIC_BASE_URL)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        publish(args)
    except PublishError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - operational failures
        print(f"[ERROR] Не удалось завершить публикацию: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
