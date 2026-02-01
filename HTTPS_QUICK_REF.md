# 🚀 Quick Reference: HTTPS WebSocket Streaming

## One-Command Start (with HTTPS)

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --generate-self-signed-cert
```

Then open: `https://localhost:8000`  
(Click "Advanced" → "Proceed" when you see security warning)

---

## Why HTTPS?

```
┌─────────────────────────────────────────────────────────┐
│  Modern browsers REQUIRE HTTPS for microphone access   │
│                                                         │
│  HTTP  → ❌ Microphone blocked (security policy)       │
│  HTTPS → ✅ Microphone allowed                         │
└─────────────────────────────────────────────────────────┘
```

---

## 3 Ways to Enable HTTPS

### 🔸 Option 1: Auto-Generated (Easiest)
```bash
--generate-self-signed-cert
```
- ✅ Zero setup
- ✅ Works immediately
- ⚠️ Browser warning (normal)

### 🔸 Option 2: Custom Certificate
```bash
--ssl-certfile cert.pem --ssl-keyfile key.pem
```
- ✅ Full control
- ⚠️ Browser warning (if self-signed)

### 🔸 Option 3: Let's Encrypt (Production)
```bash
--ssl-certfile /etc/letsencrypt/live/domain/fullchain.pem \
--ssl-keyfile /etc/letsencrypt/live/domain/privkey.pem
```
- ✅ Trusted by all browsers
- ✅ No warnings
- ✅ Free

---

## What You'll See

### ✅ Success (HTTPS Enabled):
```
SSL enabled with certificate: qwen_asr_cert.pem
⚠ Using self-signed certificate - browsers will show security warning
Starting WebSocket server at https://0.0.0.0:8000
```

Browser URL: `https://localhost:8000` 🔒

### ❌ Without HTTPS:
```
Starting WebSocket server at http://0.0.0.0:8000
```

Browser URL: `http://localhost:8000` ⚠️ (Microphone blocked)

---

## Browser Security Warning (Normal!)

```
┌────────────────────────────────────────────┐
│  🛡️ Your connection is not private        │
│                                            │
│  Attackers might be trying to steal your  │
│  information from localhost (for example,  │
│  passwords, messages, or credit cards)     │
│                                            │
│  NET::ERR_CERT_AUTHORITY_INVALID           │
│                                            │
│  [← Back to safety]  [Advanced]            │
└────────────────────────────────────────────┘
```

**What to do:**
1. Click **"Advanced"**
2. Click **"Proceed to localhost (unsafe)"**
3. This is NORMAL for self-signed certificates in testing

---

## Commands Comparison

| Scenario | Command |
|----------|---------|
| **Testing (quickest)** | `--generate-self-signed-cert` |
| **Custom cert** | `--ssl-certfile cert.pem --ssl-keyfile key.pem` |
| **Production** | Use Let's Encrypt + reverse proxy |
| **No HTTPS** | *(omit SSL flags)* ⚠️ Microphone won't work |

---

## Troubleshooting Quick Fixes

| Problem | Solution |
|---------|----------|
| "Cannot access microphone" | Add `--generate-self-signed-cert` |
| "Connection refused" | Check if port 8000 is available |
| "Certificate error" | Regenerate: delete `.pem` files and restart |
| "Still showing HTTP" | Clear browser cache, use `https://` in URL |

---

## Installation (If Missing Dependencies)

```bash
pip install cryptography
# or
./install_websocket.sh
```

---

## Testing Checklist

- [ ] Server shows "SSL enabled with certificate"
- [ ] Browser URL is `https://` (not `http://`)
- [ ] Clicked through security warning
- [ ] Microphone permission granted
- [ ] Can see real-time transcripts

---

## Production Deployment

```bash
# 1. Get Let's Encrypt certificate
sudo certbot certonly --standalone -d yourdomain.com

# 2. Start server
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --ssl-certfile /etc/letsencrypt/live/yourdomain.com/fullchain.pem \
    --ssl-keyfile /etc/letsencrypt/live/yourdomain.com/privkey.pem

# 3. Open in browser (no warning!)
open https://yourdomain.com
```

---

## Need More Help?

- 📖 Quick Start: `QUICKSTART_WEBSOCKET.md`
- 🔐 SSL Guide: `SSL_SETUP_GUIDE.md`
- 📡 Full Docs: `WEBSOCKET_STREAMING.md`
- ✅ Implementation: `HTTPS_SUPPORT.md`
