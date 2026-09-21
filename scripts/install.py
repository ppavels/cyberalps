#!/usr/bin/env python3
"""Install CyberAlps independently on its Netcup VPS from a reviewed Git checkout."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import subprocess
import sys

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
    if run('hostname').split('.')[0] != 'v2202609399387523829':
        addresses = json.loads(run('ip', '-json', 'address', 'show'))
        if not any(a.get('local') == '185.183.157.51' for device in addresses for a in device.get('addr_info', [])):
            parser.error('Unexpected host. This installer targets 185.183.157.51 only.')
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
    prefix = ['runuser', '-u', 'cyberalps', '--', 'git', '-C', str(ROOT)]
    run(*prefix, 'fetch', 'origin', 'refs/heads/main:refs/remotes/origin/main', 'refs/heads/deploy:refs/remotes/origin/deploy')
    if run(*prefix, 'rev-parse', 'origin/main') != run(*prefix, 'rev-parse', 'origin/deploy'):
        raise RuntimeError('Waiting for CI to approve the current CyberAlps main commit.')
    run(*prefix, 'merge', '--ff-only', 'origin/deploy')
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
        source = ROOT / 'deploy' / name
        target = Path('/etc/systemd/system') / name
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise RuntimeError('Existing systemd configuration differs; review it before replacing it.')
        shutil.copyfile(source, target)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable', '--now', 'cyberalps-update.timer')
    run('systemctl', 'is-enabled', '--quiet', 'cyberalps-update.timer')
    run('systemctl', 'is-active', '--quiet', 'cyberalps-update.timer')
    print('Installing the tested image through the CyberAlps updater...', flush=True)
    run('systemctl', 'start', 'cyberalps-update.service')
    print('CyberAlps installed. Credentials: /opt/cyberalps/.env.production (mode 0600).')
    print('Checking the public site and its actual deployed revision...', flush=True)
    revision = (STATE / 'deployed').read_text().strip()
    subprocess.run([sys.executable, str(ROOT / 'scripts/verify_live.py')], check=True,
                   env={**os.environ, 'EXPECTED_REVISION': revision, 'ROLLOUT_ATTEMPTS': '6'})


if __name__ == '__main__':
    main()
