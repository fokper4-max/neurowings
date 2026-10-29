#!/usr/bin/env python3
"""Capture/replay exact official wheel identities. Never import the application."""
import argparse
import json
from pathlib import Path
import re
import urllib.parse

SOURCE_COMMIT = '02a5a4754794c186ab34a000f055dd7d9a849075'
BOOTSTRAP = {'pip', 'setuptools'}

def canonical(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name):
        raise ValueError('Invalid package name')
    return re.sub(r'[-_.]+', '-', name).lower()

def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+!_-]*', value):
        raise ValueError('Invalid package version')
    return value

def package(row):
    if set(row) != {'name', 'version', 'url', 'sha256'}:
        raise ValueError('Unexpected wheel fields')
    name, ver = canonical(row['name']), version(row['version'])
    url = row['url']
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise ValueError('Invalid wheel URL')
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in {'files.pythonhosted.org', 'download.pytorch.org'}
            or parsed.port not in {None, 443} or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.path.endswith('.whl')):
        raise ValueError('Official HTTPS wheel URL required')
    sha = row['sha256']
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
        raise ValueError('Exact SHA256 wheel digest required')
    return {'name': name, 'version': ver, 'url': url, 'sha256': sha}

def installed(path):
    result = {}
    for row in json.loads(Path(path).read_text(encoding='utf-8-sig')):
        name = canonical(row['name'])
        if name in result:
            raise ValueError('Duplicate installed distribution')
        result[name] = version(row['version'])
    return result

def validate(lock):
    if set(lock) != {'schema', 'source_commit', 'python', 'platform', 'bootstrap', 'packages'}:
        raise ValueError('Unexpected lock fields')
    if (lock['schema'], lock['source_commit'], lock['python'], lock['platform']) != (1, SOURCE_COMMIT, '3.11.9', 'win_amd64'):
        raise ValueError('Lock source/platform binding changed')
    bootstrap = lock['bootstrap']
    if not isinstance(bootstrap, dict) or not set(bootstrap) <= BOOTSTRAP:
        raise ValueError('Unexpected Python bootstrap distribution')
    for name, ver in bootstrap.items():
        canonical(name); version(ver)
    if not isinstance(lock['packages'], list) or not 1 <= len(lock['packages']) <= 256:
        raise ValueError('Invalid wheel count')
    rows = [package(row) for row in lock['packages']]
    names = [row['name'] for row in rows]
    if len(set(names)) != len(names) or set(names) & set(bootstrap):
        raise ValueError('Duplicate wheel or bootstrap distribution')
    indexed = {row['name']: row for row in rows}
    required = {'pyqt5', 'numpy', 'opencv-python', 'torch', 'torchvision',
                'ultralytics', 'psutil', 'openai', 'certifi', 'pyinstaller'}
    if not required <= set(indexed) or indexed['pyinstaller']['version'] != '6.22.3':
        raise ValueError('Frozen application build dependencies or PyInstaller pin missing')
    for name in ('torch', 'torchvision'):
        parsed = urllib.parse.urlsplit(indexed[name]['url'])
        if parsed.hostname != 'download.pytorch.org' or not parsed.path.startswith('/whl/cpu/'):
            raise ValueError('Exact official CPU-only framework wheels required')
    return {**lock, 'packages': sorted(rows, key=lambda row: row['name'])}

def capture(reports, installed_path):
    wheels = {}
    for report in reports:
        data = json.loads(Path(report).read_text(encoding='utf-8-sig'))
        for row in data['install']:
            info = row['download_info']
            meta = row['metadata']
            wheel = package({'name': meta['name'], 'version': meta['version'], 'url': info['url'],
                             'sha256': info['archive_info']['hashes']['sha256']})
            wheels[wheel['name']] = wheel
    current = installed(installed_path)
    selected = []
    bootstrap = {}
    for name, ver in current.items():
        if name in wheels and wheels[name]['version'] == ver:
            selected.append(wheels[name])
        elif name in BOOTSTRAP:
            bootstrap[name] = ver
        else:
            raise ValueError('Installed distribution has no matching wheel identity')
    return validate({'schema': 1, 'source_commit': SOURCE_COMMIT, 'python': '3.11.9',
                     'platform': 'win_amd64', 'bootstrap': bootstrap, 'packages': selected})

def verify(lock, installed_path):
    expected = dict(lock['bootstrap'])
    expected.update({row['name']: row['version'] for row in lock['packages']})
    if installed(installed_path) != expected:
        raise ValueError('Clean locked environment differs from saved wheel lock')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['capture', 'render', 'verify'])
    parser.add_argument('--report', action='append', default=[])
    parser.add_argument('--installed')
    parser.add_argument('--lock', required=True)
    parser.add_argument('--requirements')
    args = parser.parse_args()
    if args.mode == 'capture':
        lock = capture(args.report, args.installed)
        Path(args.lock).write_text(json.dumps(lock, sort_keys=True, indent=2)+'\n', encoding='utf-8')
    else:
        lock = validate(json.loads(Path(args.lock).read_text(encoding='utf-8-sig')))
    if args.mode == 'verify':
        verify(lock, args.installed)
    else:
        if not args.requirements:
            parser.error('--requirements required')
        text = ''.join(f"{row['name']} @ {row['url']} --hash=sha256:{row['sha256']}\n" for row in lock['packages'])
        Path(args.requirements).write_text(text, encoding='utf-8')
    print(f"Wheel lock {args.mode} accepted: {len(lock['packages'])} exact wheels; no application/model imports")

if __name__ == '__main__':
    main()
