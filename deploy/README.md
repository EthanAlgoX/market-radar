[English](README.md) · [简体中文](README.zh-CN.md)

# HTTPS deployment

Market Radar can run as a private, single-user service at **https://myaistock.top/market-radar/**. It uses one container, one backend worker and a persistent data directory. Nginx terminates HTTPS, protects the entire application with authentication and strips the `/market-radar/` prefix before proxying to the loopback-only port.

## Install

On a Linux server with Docker Compose and Nginx, check out a reviewed commit in `/opt/market-radar/app`. Prepare an independent data directory and a private environment file:

```bash
sudo install -d -m 700 -o 10001 -g 10001 /opt/market-radar/data
cd /opt/market-radar/app
cp deploy/runtime.env.example deploy/runtime.env
chmod 600 deploy/runtime.env
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml up -d --no-build
docker compose -f deploy/compose.yaml ps
curl --fail http://127.0.0.1:8788/health
```

The image installs dependencies from `backend/uv.lock` and `frontend/package-lock.json`; it does not include local databases, account sessions, environment files or API keys. Runtime writes go to `/data` and temporary storage. The backend has one process because collection jobs and databases assume a single writer.

## Add the HTTPS route

Adapt [nginx-subpath.conf.example](nginx-subpath.conf.example) and include it inside your domain's existing HTTPS server block. Set `auth_basic_user_file` to an independently managed password file or an existing workspace's password file. Keep the other applications' routes intact. Back up the site configuration first, run `nginx -t`, and reload only after validation succeeds.

The Compose default uses `127.0.0.1:8788`. If you change it, update `RADAR_HOST_PORT` and the Nginx upstream together. The app must be behind authentication because Settings, saved sessions and collected information are shared within this one-user workspace.

Set `RADAR_PUBLIC_URL` to the exact external HTTPS URL, including its path. The backend accepts that configured Host and Origin, plus loopback access for health checks. It does not derive trusted hosts from forwarding headers. Production assets and API calls support both a subpath and the original localhost root.

## Configure accounts and translation

Open **Settings → Translation API** to enter your own API base, key and model. Environment settings in `deploy/runtime.env` are an alternative; restart the app after editing that file. The default model is `deepseek-flash`. English and Chinese interface text work without an API; translating source content requires a configured provider.

Use the hosted callback shown in **Settings → Accounts** for Reddit:

```text
https://myaistock.top/market-radar/api/connections/reddit/callback
```

Register that exact address in the Reddit application's settings before authorizing. A local callback from another installation must be reconfigured. Headless server deployments support X Cookie JSON import; the isolated graphical X login remains a local-desktop feature. Each installation has its own database and encrypted account settings.

## Update, verify and recover

Build a new image with a distinct `RADAR_IMAGE` tag before replacing the app container. Keep the previous image and configuration for rollback. Verify `/market-radar/`, its assets, `/health`, `/api/connections` and a same-origin API request through HTTPS. Requests without authentication should return `401`; an unrelated Origin should return `403`. Check that other services retain their container IDs and start times.

Persistent data lives in `/opt/market-radar/data`. Back up the whole directory while the app is stopped, retaining the encryption key with encrypted credentials and any database WAL files. Do not put backups or the environment file in Git. For rollback, set `RADAR_IMAGE` to the previous image and recreate only this Compose app service; keep the data directory.

```bash
docker compose -f deploy/compose.yaml logs --tail 100 app
docker compose -f deploy/compose.yaml stop app
# Back up /opt/market-radar/data, then restart:
docker compose -f deploy/compose.yaml start app
```
