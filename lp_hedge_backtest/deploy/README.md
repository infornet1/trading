# Deployment artifacts

## `viznago_api.service`

Systemd unit for the VIZNIAGO FURY FastAPI service.

### Install

```bash
sudo ln -sf \
  /var/www/dev/trading/lp_hedge_backtest/deploy/viznago_api.service \
  /etc/systemd/system/viznago_api.service

sudo systemctl daemon-reload
sudo systemctl enable viznago_api.service
sudo systemctl restart viznago_api.service
```

### Requirements

- User `viznago` must exist and own `/var/www/dev/trading/lp_hedge_backtest`.
- `api/.env` must contain all required environment variables (it is not tracked in Git).
- `api/.env.email` points the service at the encrypted email config (`/var/www/dev/trading/lp_hedge_email_config.json`).
- MariaDB must be running (`Wants=mariadb.service`).
