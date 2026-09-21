# Integration with the existing Preisli VPS

Target: `v2202609399387523829`, `185.183.157.51` (VPS nano G11s).
The exact CyberAlps domain must be supplied before this is applied.

## One-time Git changes in ppavels/preisli

Keep all existing Preisli authentication, response headers, routes and backend networking. In `docker-compose.prod.yml`, add **only the web service** to the additional external network and pass the confirmed domain:

```yaml
services:
  web:
    environment:
      # Keep all existing environment entries.
      CYBERALPS_DOMAIN: ${CYBERALPS_DOMAIN:?Set the confirmed CyberAlps domain}
    networks:
      - backend
      - cyberalps_edge
networks:
  # Keep the existing backend definition.
  cyberalps_edge:
    external: true
    name: cyberalps_edge
```

These are additions, not a replacement Compose file. Set `CYBERALPS_DOMAIN` in Preisli's server-only environment file before its deployment. Do not add CyberAlps to the database network.

Append this site block to the existing `Caddyfile`:

```caddyfile
{$CYBERALPS_DOMAIN} {
    encode zstd gzip
    header {
        Strict-Transport-Security "max-age=31536000"
        -Server
    }
    reverse_proxy cyberalps-app:3002 {
        header_up X-Real-IP {remote_host}
        transport http {
            dial_timeout 5s
            response_header_timeout 15s
        }
    }
}
```

Use just the confirmed hostname initially. Add a `www` redirect only after its DNS has also been verified. Existing ports 80/443 remain with Preisli's Caddy. CyberAlps publishes no host ports. Caddy obtains and renews the new hostname's HTTPS certificate.

Commit the modifications in the Preisli repository and let its existing verification/promote/deploy process apply them. Never replace the private Preisli site block or put its password hash into this public repository. Verify that unauthenticated requests to Preisli still receive 401, its robots.txt disallows crawling and its sitemap returns 410 after the integration.

## One-time server bootstrap

Prerequisites: Docker Compose v2, Git, curl, systemd, Python 3.11+, the first successful CyberAlps CI release, and the actual DNS hostname.

Run the versioned installer from a reviewed checkout of this repository on the target server:

```sh
python3 scripts/install.py --domain ACTUAL_CYBERALPS_DOMAIN
```

The installer creates `/opt/cyberalps`, a dedicated service account, the `cyberalps_edge` network, a private environment file and an update timer. The administrator username is `owner`; the generated password is stored in `/opt/cyberalps/.env.production`. Do not commit, paste into chat or print this file into deployment logs.

For a Git-only bootstrap, invoke that same reviewed installer once through the existing root-owned BetRadar bootstrap mechanism after committing its narrowly scoped change in `ppavels/betradar`. That integration has **not** been applied here. Its exact revision and domain should be fixed in the bootstrap commit, and the one-time hook removed after success. No CI job needs an SSH private key.

## Deployment operation

The timer runs every two minutes. It requires a clean `main` checkout and the expected remote. It deploys only when `origin/main` equals the CI-promoted `origin/deploy`. It downloads the public GitHub release image, verifies SHA-256 and its Git revision label, backs up SQLite, fast-forwards the checkout and recreates only the CyberAlps service. It checks the running image revision and health before recording success. On failure it restores the previous image and saved Compose configuration.

The repository is currently public. Anonymous release downloads rely on it remaining public; making it private requires an explicit download-authentication design. No credentials are included in images or releases.

```sh
systemctl status cyberalps-update.timer cyberalps-update.service
journalctl -u cyberalps-update.service -n 60 --no-pager
docker stats --no-stream
```

Application memory is capped at 256 MiB, swap use disabled, CPU capped at 0.5 core, and one audit runs at a time with a queue of at most 12. These are configured limits, not measured peak consumption. Audit requests fetch at most one page plus robots.txt and /sitemap.xml, each response limited to 2 MiB. Frontend and image builds run on GitHub's runner, not the VPS.

## Retention and recovery

Live reports expire after 24 hours; contact requests after 30 days. Database snapshots in `/var/lib/cyberalps-deploy/backups` are private and retained for at most seven days (maximum seven snapshots). Backup pruning runs with the timer, including when there is no new deployment. If that timer is disabled, the operator must remove expired snapshots manually.

Keep database changes backward compatible with the previous image. Rollback deliberately does not overwrite the live database, which could destroy requests received during deployment. Restore a snapshot only during a separately planned recovery with the application stopped. Do not run `docker compose down --volumes` or global Docker pruning as part of this process.

To stop automatic updates without stopping the website:

```sh
systemctl disable --now cyberalps-update.timer
```

To roll back code normally, revert the problematic Git commit on `main`. CI publishes a new tested revision, then the timer installs it. Keep the current and previous image; cleanup only removes older images in the `cyberalps` image namespace.

## Before declaring deployment complete

- Confirm DNS A/AAAA reaches the target server and HTTPS works for the actual hostname.
- Check both `/de/` and `/en/`, contact submission and protected `/admin`.
- Check `/api/health` revision against the promoted Git commit.
- Confirm all existing Preisli privacy checks still pass and BetRadar stays running.
- Observe memory during an audit, not just at idle.

These live-server checks have not yet been performed.
