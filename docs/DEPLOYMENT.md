# Deployment

## Target

- Public hostname: `quant.tglauner.com`
- Host model: one DigitalOcean droplet
- Web tier: Apache
- App tier: local Gunicorn service bound to `127.0.0.1:8008`
- Process manager: `systemd`
- App root: `/opt/tgir_quantlib_tools`

## Current Repo Deployment Assets

- Apache vhost template: `deploy/apache/tgir-quantlib-tools.conf.template`
- systemd service template: `deploy/systemd/tgir-quantlib-tools.service.template`
- production env example: `deploy/env/production.env.example`
- GitHub Actions deploy workflow: `.github/workflows/deploy_digitalocean.yml`

## Live Check Status

I attempted a direct SSH probe against `quant.tglauner.com` from this environment. It failed before authentication with:

```text
ssh: Could not resolve hostname quant.tglauner.com: nodename nor servname provided, or not known
```

I then retried against the droplet IP and the sandbox blocked outbound SSH:

```text
ssh: connect to host 45.55.196.120 port 22: Operation not permitted
```

That means I could not verify the droplet's live Apache or systemd state from here. The most likely causes are:

- DNS for `quant.tglauner.com` is not in place yet
- the domain is private or split-horizon
- the SSH target is actually an IP or different hostname stored outside this repo
- this Codex environment does not permit outbound SSH even when the IP is known

## Recommended Production Layout

```text
/opt/tgir_quantlib_tools/
  current -> /opt/tgir_quantlib_tools/releases/<release-id>
  releases/
  shared/
    .env
    debug/
```

Apache should terminate TLS on `quant.tglauner.com` and reverse proxy to local Gunicorn on `127.0.0.1:8008`.

## One-Time Droplet Bootstrap

### 1. Base packages

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip apache2 certbot python3-certbot-apache
```

### 2. Apache modules

```bash
sudo a2enmod proxy proxy_http headers rewrite ssl
sudo systemctl restart apache2
```

### 3. App directories

```bash
sudo mkdir -p /opt/tgir_quantlib_tools/releases
sudo mkdir -p /opt/tgir_quantlib_tools/shared/debug
sudo chown -R www-data:www-data /opt/tgir_quantlib_tools
```

### 4. Shared environment

Create `/opt/tgir_quantlib_tools/shared/.env` with at least:

```dotenv
FLASK_SECRET_KEY=<long-random-secret>
APP_LOGIN_USERNAME=<username>
APP_LOGIN_PASSWORD=<strong-password>
FLASK_DEBUG=0
```

Set permissions:

```bash
sudo chown www-data:www-data /opt/tgir_quantlib_tools/shared/.env
sudo chmod 600 /opt/tgir_quantlib_tools/shared/.env
```

### 5. systemd service

Install the repo template as `/etc/systemd/system/tgir-quantlib-tools.service`:

```bash
sudo cp deploy/systemd/tgir-quantlib-tools.service.template /etc/systemd/system/tgir-quantlib-tools.service
sudo systemctl daemon-reload
sudo systemctl enable tgir-quantlib-tools
```

### 6. Apache vhost

Install the repo template as `/etc/apache2/sites-available/tgir-quantlib-tools.conf`:

```bash
sudo cp deploy/apache/tgir-quantlib-tools.conf.template /etc/apache2/sites-available/tgir-quantlib-tools.conf
sudo a2ensite tgir-quantlib-tools.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

### 7. TLS certificate

DNS must point `quant.tglauner.com` to the droplet first.

```bash
sudo certbot --apache -d quant.tglauner.com
```

## GitHub Actions Secrets

The deploy workflow already expects these GitHub environment or repository secrets:

- `DO_HOST`
- `DO_USER`
- `DO_SSH_KEY`
- `DO_APP_ROOT`
- `DO_HEALTHCHECK_URL`

Recommended values:

- `DO_HOST`: droplet public IP until `quant.tglauner.com` DNS is stable, or the final hostname after that
- `DO_APP_ROOT`: `/opt/tgir_quantlib_tools`
- `DO_HEALTHCHECK_URL`: `https://quant.tglauner.com/health`

## Deployment Flow

The existing workflow in `.github/workflows/deploy_digitalocean.yml` is structurally fine for this app:

1. Run unit-test gates on `main`
2. Package the repo
3. Upload the tarball to the droplet
4. Create `/opt/tgir_quantlib_tools/releases/<git-sha>`
5. Build a fresh `.venv`
6. Install `requirements-production.txt`
7. Symlink shared `.env` and `debug/`
8. Repoint `current`
9. Restart `tgir-quantlib-tools`
10. Check local health on `127.0.0.1:8008`
11. Check public health on `https://quant.tglauner.com/health`

## What Should Exist On The Droplet

Once deployed correctly, these commands should succeed:

```bash
apachectl -S
systemctl status tgir-quantlib-tools --no-pager
ls -la /etc/apache2/sites-enabled
ls -la /opt/tgir_quantlib_tools
curl -fsS http://127.0.0.1:8008/health
curl -fsS https://quant.tglauner.com/health
```

Expected shape:

- Apache has a vhost for `quant.tglauner.com`
- TLS cert paths resolve under `/etc/letsencrypt/live/quant.tglauner.com/`
- Gunicorn listens only on `127.0.0.1:8008`
- `current` points to a release directory
- `shared/.env` exists and is readable by `www-data`

## Suggested Verification Plan

### Phase 1: DNS and SSH

1. Confirm `quant.tglauner.com` resolves to the droplet IP
2. Confirm SSH target and user
3. Re-run the read-only inspection:

```bash
ssh <user>@<host> '
  hostname
  whoami
  apachectl -S
  systemctl status tgir-quantlib-tools --no-pager --full | head -n 40
  ls -la /etc/apache2/sites-enabled
  ls -la /opt/tgir_quantlib_tools
'
```

### Phase 2: Apache and service correctness

1. Verify Apache site file path and enabled symlink
2. Verify `ProxyPass` targets `127.0.0.1:8008`
3. Verify cert paths match `quant.tglauner.com`
4. Verify the systemd service uses `/opt/tgir_quantlib_tools/current/.venv/bin/gunicorn`

### Phase 3: first release

1. Put the shared `.env` in place
2. Run GitHub Actions deploy or perform the same steps manually
3. Hit `/health`
4. Log in and test:
   - `/dashboard`
   - `/trade/bermudan_swaption`
   - `/quantlib-data-model`

## Rollback

Rollback is a symlink flip plus service restart:

```bash
sudo ls -1 /opt/tgir_quantlib_tools/releases
sudo ln -sfn /opt/tgir_quantlib_tools/releases/<previous-release> /opt/tgir_quantlib_tools/current
sudo systemctl restart tgir-quantlib-tools
curl -fsS http://127.0.0.1:8008/health
curl -fsS https://quant.tglauner.com/health
```
