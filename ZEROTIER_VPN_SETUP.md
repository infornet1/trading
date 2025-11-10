# Using ZeroTier VPN for Bybit API Access

## ✅ Solution Overview

Your server is geo-blocked from Bybit API, but you have **ZeroTier VPN** connected to your business network outside USA. We can route Bybit API calls through your VPN!

**Your ZeroTier Setup:**
- Interface: `ztjlh4w6bx`
- Local IP: `172.28.104.47`
- Gateway: `172.28.10.10` (your business network)
- Status: ✅ Active and connected

---

## 🚀 Quick Setup (Recommended Method)

### **Method 1: SOCKS Proxy via SSH (Easiest)**

This creates an SSH tunnel through your business network.

**Requirements:**
- SSH server running on your gateway (`172.28.10.10`)
- SSH access (key or password)

**Setup:**

```bash
cd /var/www/dev/trading
python3 vpn_proxy_setup.py
```

The script will:
1. ✅ Check ZeroTier connection
2. ✅ Test gateway connectivity
3. ✅ Create SSH SOCKS tunnel
4. ✅ Test Bybit API access
5. ✅ Update .env automatically

**Once setup, your trading bot automatically uses the VPN!**

---

## 🔧 Alternative Methods

### **Method 2: Direct IP Routing**

Route only Bybit API IPs through VPN (lower latency).

```bash
cd /var/www/dev/trading
sudo ./setup_vpn_routing.sh
```

Choose **Option 1** for selective routing.

**Pros:**
- ✅ Low latency for other traffic
- ✅ No SSH tunnel needed
- ✅ Simple and fast

**Cons:**
- ⚠️ Routes reset on reboot
- ⚠️ Need to update if Bybit changes IPs

---

### **Method 3: Default Route Through VPN**

Route ALL traffic through your business network.

```bash
cd /var/www/dev/trading
sudo ./setup_vpn_routing.sh
```

Choose **Option 2** for full routing.

**Pros:**
- ✅ Works for all exchanges
- ✅ Simple configuration

**Cons:**
- ❌ Higher latency for everything
- ❌ Uses business bandwidth

---

## 📋 Step-by-Step: SOCKS Proxy Setup

### **Step 1: Prepare Gateway**

On your business gateway (`172.28.10.10`):

```bash
# Install SSH server (if not already installed)
sudo apt-get update
sudo apt-get install -y openssh-server

# Start SSH service
sudo systemctl start ssh
sudo systemctl enable ssh

# Check status
sudo systemctl status ssh
```

### **Step 2: Test SSH Access**

From your droplet:

```bash
# Test if you can SSH to gateway
ssh your_username@172.28.10.10

# If successful, you're ready!
```

### **Step 3: Run Setup Script**

```bash
cd /var/www/dev/trading
python3 vpn_proxy_setup.py
```

Enter your SSH username when prompted.

**Expected output:**
```
✅ ZeroTier is running
✅ Gateway 172.28.10.10 is reachable
✅ SSH tunnel created!
✅ Proxy works! Bybit API accessible
✅ BTC Price: $112,345.67
✅ Added SOCKS_PROXY to .env

Setup Complete!
```

### **Step 4: Test Trading Bot**

```bash
source venv/bin/activate
python3 bybit_trader.py
```

Should see:
```
Using SOCKS proxy: socks5://127.0.0.1:1080
✅ API Connected!
💰 Balance: $1234.56
💵 BTC Price: $112,345.67
```

---

## 🧪 Manual Testing

### **Test 1: Check ZeroTier**

```bash
# Check interface
ip addr show ztjlh4w6bx

# Check routes
ip route | grep zt

# Ping gateway
ping -c 3 172.28.10.10
```

### **Test 2: Test SSH Tunnel**

```bash
# Create tunnel manually
ssh -D 1080 -N -f your_username@172.28.10.10

# Check if running
ps aux | grep ssh

# Test with curl
curl --socks5 127.0.0.1:1080 https://api.bybit.com/v5/market/time
```

### **Test 3: Test Python with Proxy**

```bash
python3 << 'EOF'
import requests

proxies = {
    'http': 'socks5://127.0.0.1:1080',
    'https': 'socks5://127.0.0.1:1080'
}

response = requests.get(
    'https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT',
    proxies=proxies,
    timeout=10
)

if response.status_code == 200:
    data = response.json()
    price = data['result']['list'][0]['lastPrice']
    print(f"✅ Success! BTC: ${price}")
else:
    print(f"❌ Failed: {response.status_code}")
EOF
```

---

## 🔄 Making SSH Tunnel Persistent

The SSH tunnel needs to stay running for trading. Here's how to make it persistent:

### **Option A: Systemd Service (Recommended)**

Create service file:

```bash
sudo nano /etc/systemd/system/zerotier-proxy.service
```

Add:

```ini
[Unit]
Description=ZeroTier SOCKS Proxy for Trading
After=network.target zerotier-one.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/ssh -D 1080 -N -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes your_username@172.28.10.10
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Replace `your_username` with your SSH username.

Enable service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable zerotier-proxy
sudo systemctl start zerotier-proxy

# Check status
sudo systemctl status zerotier-proxy
```

### **Option B: Cron on Reboot**

```bash
crontab -e
```

Add:

```
@reboot sleep 30 && ssh -D 1080 -N -f -o ServerAliveInterval=60 your_username@172.28.10.10
```

---

## 📊 Performance Comparison

| Method | Latency | Reliability | Setup |
|--------|---------|-------------|-------|
| SOCKS Proxy | ~50-100ms | ⭐⭐⭐⭐⭐ | Easy |
| IP Routing | ~30-50ms | ⭐⭐⭐⭐ | Medium |
| Full VPN | ~100-200ms | ⭐⭐⭐⭐⭐ | Easy |

**Recommendation:** SOCKS Proxy (best balance)

---

## ⚠️ Troubleshooting

### **"Gateway unreachable"**

```bash
# Check ZeroTier status
sudo zerotier-cli status

# Check if gateway is online
ping 172.28.10.10

# Check routes
ip route | grep zt
```

### **"SSH tunnel failed"**

```bash
# Test SSH manually
ssh -v your_username@172.28.10.10

# Check SSH server on gateway
# (On gateway): sudo systemctl status ssh

# Check firewall
# (On gateway): sudo ufw status
```

### **"Proxy test failed"**

```bash
# Check if tunnel is running
ps aux | grep ssh | grep 1080

# Test tunnel directly
curl --socks5 127.0.0.1:1080 https://api.bybit.com/v5/market/time

# Check if gateway can access Bybit
# (On gateway): curl https://api.bybit.com/v5/market/time
```

### **"Still getting 403"**

**Possible causes:**
1. Gateway itself is geo-blocked
   - Test from gateway: `curl https://api.bybit.com/v5/market/time`
   - If blocked, gateway needs VPN too

2. Proxy not being used
   - Check .env has: `SOCKS_PROXY=socks5://127.0.0.1:1080`
   - Restart trading bot

3. SSH tunnel died
   - Check: `ps aux | grep ssh`
   - Restart: `python3 vpn_proxy_setup.py`

---

## 🔐 Security Considerations

### **SSH Key Authentication (Recommended)**

Instead of password, use SSH keys:

```bash
# Generate key (if you don't have one)
ssh-keygen -t ed25519

# Copy to gateway
ssh-copy-id your_username@172.28.10.10

# Now SSH tunnel won't ask for password
```

### **Firewall Rules**

On gateway, allow only your droplet:

```bash
# On gateway (172.28.10.10)
sudo ufw allow from 172.28.104.47 to any port 22
```

---

## 📝 Configuration Files

### **.env (Updated by script)**

```bash
BYBIT_API_KEY=ARW6cstJsLzNs22Sap
BYBIT_API_SECRET=68U863pD49Ou4M5z3zqaxVd9S56r1q1UkaTM
BYBIT_TESTNET=false
BYBIT_LEVERAGE=5

# VPN Proxy (added automatically)
SOCKS_PROXY=socks5://127.0.0.1:1080

TRADING_ENABLED=false
POSITION_SIZE_BTC=0.001
MAX_DAILY_LOSS_USD=50
```

### **bybit_trader.py (Already updated)**

The trader automatically detects `SOCKS_PROXY` in .env and uses it!

```python
# Automatically uses proxy if configured
trader = BybitTrader(paper_trading=False)
# All API calls now go through VPN!
```

---

## ✅ Quick Start Checklist

- [ ] ZeroTier running and connected
- [ ] Gateway (`172.28.10.10`) reachable
- [ ] SSH server on gateway
- [ ] SSH access working
- [ ] Run `python3 vpn_proxy_setup.py`
- [ ] Test with `python3 bybit_trader.py`
- [ ] Setup systemd service for persistence
- [ ] Profit! 🚀

---

## 🎯 Next Steps After Setup

1. **Test API Connection:**
   ```bash
   cd /var/www/dev/trading
   source venv/bin/activate
   python3 << 'EOF'
   from bybit_trader import BybitTrader
   trader = BybitTrader(paper_trading=False)
   balance = trader.get_balance()
   print(f"Balance: ${balance:.2f}")
   EOF
   ```

2. **Start Paper Trading:**
   ```bash
   # Monitor generates signals, trades are simulated
   python3 btc_monitor.py config_conservative.json
   ```

3. **Go Live (After Testing):**
   - Update `.env`: `TRADING_ENABLED=true`
   - Start with tiny positions (0.001 BTC)
   - Monitor closely for first week

---

## 📞 Support

**Scripts created:**
- `vpn_proxy_setup.py` - Automated SOCKS setup
- `setup_vpn_routing.sh` - IP routing setup
- `bybit_trader.py` - Updated with proxy support

**Files:**
- `.env` - Configuration (with SOCKS_PROXY)
- `ZEROTIER_VPN_SETUP.md` - This guide

**Your gateway:** `172.28.10.10`
**Your droplet:** `172.28.104.47`

---

## ✅ Summary

**Problem:** Bybit API geo-blocked
**Solution:** Route through ZeroTier VPN
**Method:** SOCKS proxy via SSH tunnel
**Status:** Ready to setup!

**Run this to get started:**
```bash
cd /var/www/dev/trading
python3 vpn_proxy_setup.py
```

**Your trading bot will work through your business network!** 🎉
