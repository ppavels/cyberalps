# Independent CyberAlps deployment

Domain: `cyberalps.ch`. VPS: `185.183.157.51`.

CyberAlps owns its build, image, container, SQLite data, backup directory, service account and systemd timer. No BetRadar hook or other application test suite is involved.

## Branches

- `main`: all source changes.
- `deploy`: the exact main commit approved by CyberAlps CI, advanced automatically. Never edit this branch by hand.
- The temporary `diagnostics/rollout` branch is removed by the cleanup step after this release passes. Its only purpose was public DNS/HTTPS inspection; it never deployed an application.

## First installation (once, on the VPS)

Docker Compose, Git, curl, Python 3.11+ and systemd must be installed. Wait for the CyberAlps build to pass, then run from a checkout of this repository as root:

```sh
python3 scripts/install.py --domain cyberalps.ch
```

The installer checks the target server, creates `/opt/cyberalps` and a dedicated account, waits for `main` to match the tested `deploy` revision, writes a private environment file if missing, creates the application network, installs its own systemd units and runs its own updater. The shared HTTPS proxy must already be connected to `cyberalps_edge` with the route in `deploy/Caddyfile`. This infrastructure step is already configured on the current VPS. The installer does not invoke, build or restart another application.

The installer finishes by checking public HTTPS, the deployed Git revision, both languages, protected administration and an actual audit of our own site. A failed check is a failed installation result, not a success message.

The shared Caddy owns ports 80/443. CyberAlps does not expose another public port. The shared proxy’s Git-managed configuration already includes this route and network for future proxy replacements. On a new server, add `deploy/Caddyfile` to that server’s proxy configuration and attach the proxy to `cyberalps_edge` once. No other application is needed to build or update CyberAlps.

Credentials are generated on the server in `/opt/cyberalps/.env.production`, mode 0600. Admin username: `owner`. Never paste the password into chat, commit it or print it into CI logs.

## Updates

Push code to `main`. CyberAlps CI builds and tests its own application, publishes a prebuilt image and advances `deploy`. The independent `cyberalps-update.timer` checks every two minutes, verifies the downloaded image checksum and revision, backs up SQLite, updates only the CyberAlps container and checks its actual health. Failed updates restore the previous image. Builds run in GitHub Actions, not on the 2 GB VPS.

```sh
systemctl status cyberalps-update.timer cyberalps-update.service
journalctl -u cyberalps-update.service -n 60 --no-pager
curl --fail https://cyberalps.ch/api/health
```

The repository and release assets are public; private repository migration needs authenticated image downloads.

## DNS and HTTPS

A must resolve to `185.183.157.51`. If AAAA is present, it must reach this same VPS; an address belonging to another hosting provider must be corrected or removed. The installer does not modify DNS. Caddy obtains and renews HTTPS certificates.

## Limits and recovery

Application limit: 256 MiB RAM, 0.5 CPU, no swap; one audit worker and bounded queue. These are configured limits, not measured peak usage. Reports expire after 24 hours, leads after 30 days. Private SQLite snapshots in `/var/lib/cyberalps-deploy/backups` expire after seven days (maximum seven snapshots); the updater also prunes these when there is no new release.

Revert an application commit on `main` for a normal rollback through CI. Keep migrations compatible with the previous image. The deployment rollback does not overwrite the live database. Do not remove Docker volumes or run global image pruning.

To stop automatic updates while keeping the website running:

```sh
systemctl disable --now cyberalps-update.timer
```
