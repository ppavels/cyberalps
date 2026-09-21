# CyberAlps

A responsive Alpine Dark website with German and English pages, a passive website checker and a private contact-request inbox. An independent project hosted on a small Netcup VPS.

## What is included

- Prerendered React pages at `/de/` and `/en/`, responsive navigation, an Alpine hero, services, process, FAQ and contact dialog.
- A real, bounded technical check: initial HTML, HTTPS, response headers, SEO metadata, robots.txt, sitemap XML and selected AI-search crawler permissions.
- Per-check evidence and transparent weighted scores. Unavailable checks are excluded. The initial sample report is clearly labelled **DEMO**.
- One audit worker, public-address DNS validation on every redirect, IP-pinned connections with normal TLS validation, response/time/queue/rate limits.
- SQLite contact requests at `/admin`, protected by HTTP Basic authentication; no email notifications or external AI service dependency.
- GitHub CI, prebuilt Docker release images and a separate systemd deployment timer with health checks and rollback.

The audit does not run page JavaScript, exploit vulnerabilities, measure Core Web Vitals or measure mentions inside AI-generated answers. It is a preliminary technical checklist. Server error messages and observed HTTP evidence are currently in English.

## Local development

Use Node.js 22.12+ and Python 3.11+.

```sh
npm ci --ignore-scripts
python3 -m app.server
```

In another terminal:

```sh
npm run dev
```

The Vite development server proxies `/api` to port 3002. To serve the production build locally:

```sh
npm run build
python3 -m app.server
```

Leave `PUBLIC_BASE_URL` unset for local HTTP development. Production requires the real HTTPS origin. Set `ADMIN_PASSWORD` locally to access `/admin`; administration is disabled when no password is configured. Never commit a real `.env.production` file.

## Verification

```sh
npm test
npm run build
```

The tests cover private-address and redirect rejection, DNS pinning/TLS host verification, bounded responses, scoring unknowns, crawler directives, invalid sitemaps, consent/origin validation, inbox authorization, queue overflow, rate limits and retention.

CI additionally checks English and German at 1440, 390 and 320 pixel widths, hydration errors, mobile navigation and real local form submissions. It saves screenshots as a workflow artifact and smoke-tests the production container with its memory limit before promoting the `deploy` branch. Playwright is pinned as a CI-only tool and is not included in the runtime image.

The first GitHub CI run passed all 19 Python tests, both languages at all three viewport sizes, real local form submissions and the production Docker smoke test with a 256 MiB limit. Screenshots are attached to [the workflow run](https://github.com/ppavels/cyberalps/actions/runs/35629320579). Live VPS rollout is checked separately.

## Deployment

See [deploy/INTEGRATION.md](deploy/INTEGRATION.md). Builds happen in GitHub Actions. The VPS downloads the tested image and never runs npm or a frontend build. No server SSH key needs to be stored in GitHub Actions.

The hostname is **cyberalps.ch**, server **185.183.157.51**. CyberAlps has its own installer, service account, container, database, backups, CI and update timer. It neither invokes another project nor waits for another project’s tests. The existing Caddy is only the shared HTTPS entrypoint.

## Data and limits

- Reports: 24 hours, unlisted random identifiers.
- Contact requests: 30 days, accessible only to the administrator.
- Private deployment backups: up to seven days, at most seven snapshots.
- Application container: 256 MiB, 0.5 CPU, no swap, no host ports.
- Only the shared HTTPS proxy and CyberAlps use `cyberalps_edge`; other application networks stay separate.

The privacy page describes the implementation's data handling. Add verified operator identity and business contact details before a commercial launch; none have been invented.

## Design assets

`public/alps.webp` is a generated Alpine image optimized to about 107 KB. The mark is an editable SVG/CSS mountain shield. No fabricated client logos or trust endorsements are used.
