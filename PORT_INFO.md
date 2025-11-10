# Dashboard Port Configuration

## 🔌 Port Information

The BTC Scalping Dashboard has been configured to use **port 5800** to avoid conflicts with existing services.

### Current Port Usage on This Server

The following ports were already in use:
- **Port 5000**: Existing Python service
- **Port 5001**: Existing Python service
- **Port 5002**: Existing Python service
- **Port 5005**: Existing Python service

Therefore, the dashboard uses:
- **Port 5800**: BTC Scalping Dashboard ✅ (Available)

## 🌐 Access URLs

### Local Access (on the server)
```
http://localhost:5800
```

### Remote Access (from another computer)

**Find your server's IP address:**
```bash
hostname -I
```

**Then access dashboard at:**
```
http://YOUR_SERVER_IP:5800
```

**Example:**
```
http://192.168.1.100:5800
```

### From Mobile Device

Make sure your phone/tablet is on the same network, then:
```
http://SERVER_IP:5800
```

## 🚀 Starting the Dashboard

```bash
cd /var/www/dev/trading
source venv/bin/activate
python dashboard.py
```

**You'll see:**
```
🚀 Starting Signal Tracker Dashboard...
📊 Dashboard URL: http://localhost:5800
📊 External Access: http://YOUR_SERVER_IP:5800
⌨️  Press Ctrl+C to stop

 * Serving Flask app 'dashboard'
 * Debug mode: on
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5800
 * Running on http://YOUR_IP:5800
```

## 🔧 Changing the Port (if needed)

If port 5800 conflicts with something in the future, you can change it:

**Edit `dashboard.py`:**
```python
# Find this line at the bottom:
app.run(host='0.0.0.0', port=5800, debug=True)

# Change 5800 to your desired port:
app.run(host='0.0.0.0', port=5900, debug=True)
```

**Also update the print statement:**
```python
print("📊 Dashboard URL: http://localhost:5900")
print("📊 External Access: http://YOUR_SERVER_IP:5900")
```

## 🛡️ Firewall Considerations

If accessing from external network (not just local WiFi):

**Allow port 5800 through firewall:**
```bash
sudo ufw allow 5800/tcp
```

**Or for iptables:**
```bash
sudo iptables -A INPUT -p tcp --dport 5800 -j ACCEPT
sudo iptables-save
```

**Note**: Only do this if you need external access and understand the security implications.

## ✅ Verification

**Check if dashboard is running:**
```bash
netstat -tlnp | grep ':5800'
```

**You should see:**
```
tcp  0  0  0.0.0.0:5800  0.0.0.0:*  LISTEN  PID/python
```

**Test from command line:**
```bash
curl http://localhost:5800
```

Should return HTML of the dashboard page.

## 📋 Quick Reference

| Service | Port | Access |
|---------|------|--------|
| BTC Monitor | N/A | Terminal only |
| Dashboard | 5800 | http://localhost:5800 |
| Email Alerts | 587 | SMTP (outgoing only) |

---

**Dashboard is configured and ready on port 5800!** 🎉
