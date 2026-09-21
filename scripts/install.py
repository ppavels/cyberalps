#!/usr/bin/env python3
"""One-time installation on the existing Preisli VPS, from a reviewed Git checkout."""
import argparse
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import subprocess

ROOT = Path('/opt/cyberalps')
STATE = Path('/var/lib/cyberalps-deploy')
REPO = 'https://github.com/ppavels/cyberalps.git'


def run(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True, help='Exact canonical domain, without https:// or path')
    args = parser.parse_args()
    domain = args.domain.lower().rstrip('.')
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain) or domain.endswith(('.example', '.invalid', '.test')) or domain in {'preisli.ch', 'www.preisli.ch'}:
        parser.error('Supply the real CyberAlps domain; never use the existing Preisli domain.')
    if os.geteuid() != 0:
        parser.error('Run this one-time installer as root on the target VPS.')
    if run('hostname') != 'v2202609399387523829':
        parser.error('Unexpected hostname. This installer targets the Preisli VPS only.')
    for program in ['git', 'docker', 'curl', 'systemctl', 'runuser']:
        if not shutil.which(program):
            parser.error('Required program missing: ' + program)
    run('docker', 'compose', 'version')
    try:
        account = pwd.getpwnam('cyberalps')
    except KeyError:
        run('useradd', '--system', '--home-dir', str(ROOT), '--shell', '/usr/sbin/nologin', '--user-group', 'cyberalps')
        account = pwd.getpwnam('cyberalps')
    run('usermod', '-aG', 'docker', 'cyberalps')
    for directory in [ROOT, STATE]:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chown(directory, account.pw_uid, account.pw_gid)
    if not (ROOT / '.git').is_dir():
        run('runuser', '-u', 'cyberalps', '--', 'git', 'clone', '--branch', 'main', REPO, str(ROOT))
    origin = run('runuser', '-u', 'cyberalps', '--', 'git', '-C', str(ROOT), 'remote', 'get-url', 'origin')
    if origin != REPO:
        raise RuntimeError('Existing checkout has an unexpected origin.')
    if run('runuser', '-u', 'cyberalps', '--', 'git', '-C', str(ROOT), 'status', '--porcelain'):
        raise RuntimeError('Existing checkout contains uncommitted changes.')
    envfile = ROOT / '.env.production'
    if not envfile.exists():
        with envfile.open('x') as file:
            file.write(f'PUBLIC_BASE_URL=https://{domain}\nADMIN_PASSWORD={secrets.token_urlsafe(32)}\n')
        envfile.chmod(0o600)
        os.chown(envfile, account.pw_uid, account.pw_gid)
    elif f'PUBLIC_BASE_URL=https://{domain}' not in envfile.read_text().splitlines():
        raise RuntimeError('Configured domain differs. Review .env.production before changing it.')
    network = subprocess.run(['docker', 'network', 'inspect', 'cyberalps_edge'], capture_output=True)
    if network.returncode:
        run('docker', 'network', 'create', 'cyberalps_edge')
    for name in ['cyberalps-update.service', 'cyberalps-update.timer']:
        shutil.copyfile(ROOT / 'deploy' / name, Path('/etc/systemd/system') / name)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'cyberalps-update.timer')
    run('systemctl', 'start', 'cyberalps-update.service')
    print('CyberAlps timer installed. Credentials are in /opt/cyberalps/.env.production (mode 0600).')
    print('The existing Caddy requires the reviewed Git changes described in deploy/INTEGRATION.md.')


if __name__ == '__main__':
    main()
