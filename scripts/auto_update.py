#!/usr/bin/env python3
"""Deploy only the tested Git head. Fetch prebuilt images; never build on the VPS."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/cyberalps-deploy')
REPO = 'ppavels/cyberalps'
ENV = ROOT / '.env.production'


def command(*args, capture=True, env=None, timeout=180):
    result = subprocess.run(args, cwd=ROOT, env=env, check=True, timeout=timeout,
                            text=True, stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    return (result.stdout or '').strip()


def compose(revision, config, *args, capture=True):
    return command('docker', 'compose', '--project-name', 'cyberalps', '--project-directory', str(ROOT),
                   '--env-file', str(ENV), '-f', str(config), *args,
                   env={**os.environ, 'CYBERALPS_REVISION': revision}, capture=capture)


def healthy(revision, config):
    try:
        container = compose(revision, config, 'ps', '-q', 'app')
        if not container:
            return False
        result = command('docker', 'exec', container, 'python', '-c',
                         'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:3002/api/health", timeout=3).read().decode())', timeout=8)
        data = json.loads(result)
        return data.get('ok') is True and data.get('revision') == revision
    except (subprocess.SubprocessError, ValueError):
        return False


def wait_healthy(revision, config):
    for _ in range(15):
        if healthy(revision, config):
            return
        time.sleep(2)
    raise RuntimeError('The new container failed its revision and health check.')


def backup(previous, config):
    if not previous:
        return
    container = compose(previous, config, 'ps', '-q', 'app')
    if not container:
        raise RuntimeError('Existing container unavailable; cannot make the deployment backup.')
    destination = STATE / 'backups'
    destination.mkdir(mode=0o700, exist_ok=True)
    snapshot = destination / (time.strftime('%Y%m%d-%H%M%S', time.gmtime()) + '.sqlite3')
    code = 'import sqlite3; source=sqlite3.connect("/data/cyberalps.sqlite3"); target=sqlite3.connect("/data/deploy-backup.sqlite3"); source.backup(target); target.close(); source.close()'
    try:
        command('docker', 'exec', container, 'python', '-c', code)
        command('docker', 'cp', container + ':/data/deploy-backup.sqlite3', str(snapshot))
        snapshot.chmod(0o600)
    finally:
        command('docker', 'exec', container, 'python', '-c', 'from pathlib import Path; Path("/data/deploy-backup.sqlite3").unlink(missing_ok=True)')


def prune_backups():
    backups = sorted((STATE / 'backups').glob('*.sqlite3'), reverse=True)
    for index, file in enumerate(backups):
        if index >= 7 or file.stat().st_mtime < time.time() - 7 * 86400:
            file.unlink()


def load_image(revision):
    with tempfile.TemporaryDirectory(prefix='download-', dir=STATE) as directory:
        directory = Path(directory)
        asset = directory / 'cyberalps-image.tar.gz'
        checksum = directory / 'cyberalps-image.tar.gz.sha256'
        base = f'https://github.com/{REPO}/releases/download/build-{revision}/'
        for file in [checksum, asset]:
            command('curl', '--fail', '--silent', '--show-error', '--location', '--proto', '=https',
                    '--max-time', '180', '--max-filesize', '536870912', '--output', str(file), base + file.name, timeout=190)
        expected = checksum.read_text().split()[0]
        if not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise RuntimeError('Invalid image checksum.')
        with asset.open('rb') as file:
            actual = hashlib.file_digest(file, 'sha256').hexdigest()
        if actual != expected:
            raise RuntimeError('Downloaded image checksum does not match.')
        command('docker', 'load', '--input', str(asset), timeout=180)
        label = command('docker', 'image', 'inspect', 'cyberalps:' + revision,
                        '--format', '{{ index .Config.Labels "org.opencontainers.image.revision" }}')
        if label != revision:
            raise RuntimeError('The image revision does not match the tested commit.')


def deploy(revision, previous):
    active = STATE / 'active.compose.yml'
    candidate = ROOT / 'compose.prod.yml'
    if previous and not active.is_file():
        raise RuntimeError('The rollback configuration is missing.')
    backup(previous, active)
    command('git', 'merge', '--ff-only', revision)
    # Validate before touching the existing container. Never print the resolved secrets.
    compose(revision, candidate, 'config', '--quiet')
    try:
        compose(revision, candidate, 'up', '-d', '--no-build', '--pull', 'never', 'app', capture=False)
        wait_healthy(revision, candidate)
    except Exception:
        if previous:
            print('Deployment failed; restoring the previously healthy image.', flush=True)
            compose(previous, active, 'up', '-d', '--no-build', '--pull', 'never', 'app', capture=False)
            wait_healthy(previous, active)
        else:
            # No previous service exists on the first deployment. Keep its persistent data.
            compose(revision, candidate, 'stop', 'app', capture=False)
        raise
    shutil.copyfile(candidate, STATE / 'next.compose.yml')
    (STATE / 'next.compose.yml').replace(active)
    (STATE / 'deployed.tmp').write_text(revision + '\n')
    (STATE / 'deployed.tmp').replace(STATE / 'deployed')
    # Remove only old CyberAlps images; keep the current and previous version for rollback.
    images = command('docker', 'image', 'ls', 'cyberalps', '--format', '{{.Tag}}').splitlines()
    for tag in images:
        if re.fullmatch(r'[a-f0-9]{40}', tag) and tag not in {revision, previous}:
            try:
                command('docker', 'image', 'rm', 'cyberalps:' + tag)
            except subprocess.SubprocessError:
                pass
    print('Deployed CyberAlps ' + revision, flush=True)


def configure_shared_telegram():
    """Copy the owner's explicitly selected existing bot configuration once on this VPS."""
    if str(ROOT) != '/opt/cyberalps':
        return False
    text = ENV.read_text()
    values = dict(line.split('=', 1) for line in text.splitlines() if '=' in line and not line.lstrip().startswith('#'))
    keys = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID')
    if all(values.get(key, '').strip().strip("\"'") for key in keys):
        return False
    containers = command('docker', 'ps', '--filter', 'label=com.docker.compose.project=betradar',
                         '--filter', 'label=com.docker.compose.service=bot', '--format', '{{.ID}}').splitlines()
    if len(containers) != 1:
        raise RuntimeError('Expected one existing BetRadar bot to configure the requested Telegram destination.')
    template = '{{range .Config.Env}}{{$pair := split . "="}}{{if or (eq (index $pair 0) "TELEGRAM_BOT_TOKEN") (eq (index $pair 0) "TELEGRAM_CHAT_ID")}}{{println .}}{{end}}{{end}}'
    selected = command('docker', 'inspect', '--format', template, containers[0])
    credentials = dict(line.split('=', 1) for line in selected.splitlines() if '=' in line)
    token, chat = (credentials.get(key, '').strip() for key in keys)
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token) or not re.fullmatch(r'-?[0-9]+', chat):
        raise RuntimeError('Existing Telegram configuration is missing or invalid.')
    lines = [line for line in text.splitlines() if line.partition('=')[0].strip() not in keys]
    target = ENV.with_name('.env.production.tmp')
    try:
        with open(target, 'w', opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
            handle.write('\n'.join(lines) + '\nTELEGRAM_BOT_TOKEN=' + token + '\nTELEGRAM_CHAT_ID=' + chat + '\n')
        target.chmod(0o600)
        target.replace(ENV)
    finally:
        target.unlink(missing_ok=True)
    print('Configured CyberAlps notifications for the existing owner Telegram chat.', flush=True)
    return True


def main():
    os.umask(0o077)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / 'update.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        prune_backups()
        if not ENV.is_file():
            raise RuntimeError('Missing .env.production; run the installation step first.')
        allowed = {f'https://github.com/{REPO}.git', f'git@github.com:{REPO}.git'}
        if command('git', 'remote', 'get-url', 'origin') not in allowed:
            raise RuntimeError('Unexpected Git origin.')
        if command('git', 'branch', '--show-current') != 'main' or command('git', 'status', '--porcelain'):
            raise RuntimeError('Deployment requires a clean main checkout.')
        command('git', 'fetch', '--prune', 'origin', '+refs/heads/main:refs/remotes/origin/main', '+refs/heads/deploy:refs/remotes/origin/deploy')
        revision = command('git', 'rev-parse', 'origin/deploy')
        if not re.fullmatch(r'[a-f0-9]{40}', revision):
            raise RuntimeError('Invalid deployment revision.')
        if revision != command('git', 'rev-parse', 'origin/main'):
            print('Waiting for CI to approve the current main commit.', flush=True)
            return
        command('git', 'merge-base', '--is-ancestor', 'HEAD', revision)
        previous_file = STATE / 'deployed'
        previous = previous_file.read_text().strip() if previous_file.exists() else ''
        if previous and not re.fullmatch(r'[a-f0-9]{40}', previous):
            raise RuntimeError('Invalid saved deployment revision.')
        if previous == revision:
            changed = configure_shared_telegram()
            telegram_marker = STATE / 'telegram-configured'
            if changed or not telegram_marker.exists():
                compose(revision, ROOT / 'compose.prod.yml', 'up', '-d', '--no-build', '--pull', 'never', 'app', capture=False)
                wait_healthy(revision, ROOT / 'compose.prod.yml')
                telegram_marker.write_text('configured\n')
            if healthy(revision, STATE / 'active.compose.yml'):
                return
        if shutil.disk_usage(STATE).free < 1024**3:
            raise RuntimeError('At least 1 GB free disk space is needed for deployment.')
        load_image(revision)
        deploy(revision, previous)


if __name__ == '__main__':
    main()
