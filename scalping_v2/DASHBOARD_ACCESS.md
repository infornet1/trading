# Scalping v2 Dashboard - Access Guide

## ✅ Dashboard is Now Accessible!

### Correct URLs:

**Primary (Recommended):**
- **HTTPS (External):** https://dev.ueipab.edu.ve:5900/scalping/
- **HTTPS (Local):** https://localhost:5900/scalping/

**Direct Access (HTTP only):**
- **HTTP (Internal):** http://localhost:5902/

### Important Notes:

1. **Use HTTPS URL** - The dashboard runs on HTTP internally (port 5902) but nginx proxies it as HTTPS on port 5900
2. **The `/scalping/` path is required** - This distinguishes it from the ADX dashboard
3. **Port 5902 is HTTP only** - If you access port 5902 directly via HTTPS, you'll get errors

### Dashboard Features:

- **Real-time Status** - Bot status, balance, positions
- **Scalping Indicators** - EMA, RSI, Stochastic, Volume, ATR
- **Trade History** - Recent trades with P&L
- **Performance Metrics** - Win rate, profit factor, drawdown
- **Risk Management** - Daily limits, circuit breaker status

### API Endpoints:

- `GET /health` - Health check
- `GET /api/status` - Full status (account, positions, indicators)
- `GET /api/indicators` - Current scalping indicators
- `GET /api/trades?limit=10` - Recent trades
- `GET /api/performance` - Performance statistics
- `GET /api/risk` - Risk management status

### Nginx Configuration:

Location: `/etc/nginx/sites-available/dashboard-5900`

The configuration proxies:
- Port 5900 (HTTPS) + path `/` → Port 5901 (ADX Dashboard)
- Port 5900 (HTTPS) + path `/scalping/` → Port 5902 (Scalping Dashboard)

### Troubleshooting:

**If dashboard doesn't load:**
```bash
# Check if service is running
systemctl status scalping-dashboard

# Check nginx
sudo nginx -t
sudo systemctl status nginx

# Test direct access
curl http://localhost:5902/health

# Test via nginx proxy
curl -k https://localhost:5900/scalping/health

# View logs
journalctl -u scalping-dashboard -f
```

---

**Last Updated:** 2025-11-02 00:43
**Status:** ✅ Working
