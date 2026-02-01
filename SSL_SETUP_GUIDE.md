# SSL/HTTPS Setup Guide for WebSocket Streaming

Modern browsers require HTTPS to access the microphone. This guide covers different ways to set up SSL for the WebSocket server.

## Option 1: Auto-Generated Self-Signed Certificate (Easiest)

**Best for:** Testing, development, local deployment

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --generate-self-signed-cert
```

**What happens:**
- Server automatically generates `qwen_asr_cert.pem` and `qwen_asr_key.pem`
- Valid for 365 days
- Works for `localhost` and `127.0.0.1`

**Browser warning:**
- You'll see "Your connection is not private"
- This is normal for self-signed certificates
- Click **"Advanced"** → **"Proceed to localhost (unsafe)"**

**Pros:**
- ✅ No setup required
- ✅ Works immediately
- ✅ Generated automatically

**Cons:**
- ⚠️ Browser security warning
- ⚠️ Not suitable for production
- ⚠️ Certificate not trusted by browsers

## Option 2: Manual Self-Signed Certificate

**Best for:** Custom configuration, longer validity

### Generate Certificate Manually:

```bash
# Generate private key and certificate (valid 365 days)
openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem -out cert.pem \
  -days 365 -nodes \
  -subj "/C=US/ST=CA/L=SF/O=Qwen3-ASR/CN=localhost"
```

### Start Server:

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --ssl-certfile cert.pem \
    --ssl-keyfile key.pem
```

**For longer validity (10 years):**
```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem -out cert.pem \
  -days 3650 -nodes \
  -subj "/CN=localhost"
```

## Option 3: Let's Encrypt (Free, Production)

**Best for:** Public servers with domain names

### Prerequisites:
- A domain name pointing to your server
- Server accessible from internet (port 80/443)

### Install Certbot:

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install certbot

# macOS
brew install certbot

# CentOS/RHEL
sudo yum install certbot
```

### Generate Certificate:

```bash
sudo certbot certonly --standalone -d yourdomain.com
```

### Start Server:

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --ssl-certfile /etc/letsencrypt/live/yourdomain.com/fullchain.pem \
    --ssl-keyfile /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

**Auto-renewal:**
```bash
# Add to crontab
0 0 * * * certbot renew --quiet
```

**Pros:**
- ✅ Trusted by all browsers (no warning)
- ✅ Free
- ✅ Auto-renewal available
- ✅ Production-ready

**Cons:**
- ⚠️ Requires domain name
- ⚠️ Requires public server
- ⚠️ Must renew every 90 days

## Option 4: Reverse Proxy (Nginx/Caddy)

**Best for:** Production deployments with existing infrastructure

### With Nginx:

**1. Run server without SSL (internal only):**
```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --host 127.0.0.1 \
    --port 8000
```

**2. Configure Nginx as SSL terminator:**

`/etc/nginx/sites-available/qwen-asr`:
```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/asr {
        proxy_pass http://127.0.0.1:8000/ws/asr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

**3. Enable and restart:**
```bash
sudo ln -s /etc/nginx/sites-available/qwen-asr /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### With Caddy (Simpler):

**1. Run server without SSL:**
```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --host 127.0.0.1 \
    --port 8000
```

**2. Create Caddyfile:**

```caddy
yourdomain.com {
    reverse_proxy /ws/asr localhost:8000 {
        transport http {
            keepalive off
        }
    }
    reverse_proxy localhost:8000
}
```

**3. Run Caddy:**
```bash
caddy run
```

Caddy automatically gets Let's Encrypt certificates!

## Option 5: Production Certificate from CA

**Best for:** Enterprise deployments

Purchase a certificate from a CA (e.g., DigiCert, GlobalSign), then:

```bash
qwen-asr-serve-websocket \
    --asr-model-path Qwen/Qwen3-ASR-1.7B \
    --ssl-certfile /path/to/your/certificate.crt \
    --ssl-keyfile /path/to/your/private.key
```

## Comparison Table

| Method | Difficulty | Cost | Browser Trust | Best For |
|--------|-----------|------|---------------|----------|
| Auto self-signed | ⭐ Easy | Free | ❌ No | Testing, dev |
| Manual self-signed | ⭐⭐ Moderate | Free | ❌ No | Custom setup |
| Let's Encrypt | ⭐⭐⭐ Medium | Free | ✅ Yes | Public servers |
| Reverse Proxy | ⭐⭐⭐⭐ Advanced | Free* | ✅ Yes | Production |
| CA Certificate | ⭐⭐ Moderate | $$ | ✅ Yes | Enterprise |

*If using Let's Encrypt for the proxy

## Security Best Practices

### For Testing:
```bash
# Quick and easy
--generate-self-signed-cert
```

### For Production:
1. Use Let's Encrypt or CA certificate
2. Enable HTTPS redirect
3. Use strong SSL configuration
4. Implement rate limiting
5. Add authentication
6. Monitor certificate expiry

### SSL Configuration (if using Nginx):
```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers HIGH:!aNULL:!MD5;
ssl_prefer_server_ciphers on;
add_header Strict-Transport-Security "max-age=31536000" always;
```

## Troubleshooting

### "Certificate not trusted" error
- **Cause:** Self-signed certificate
- **Solution:** Click "Advanced" → "Proceed" or use Let's Encrypt

### "ERR_SSL_PROTOCOL_ERROR"
- **Cause:** Certificate/key mismatch or invalid format
- **Solution:** Regenerate certificate and key together

### "Permission denied" on port 443
- **Cause:** Non-root user can't bind to privileged ports
- **Solution:** Use sudo or port > 1024 (e.g., 8443)

### Microphone still not working with HTTPS
- Check browser console for errors
- Verify HTTPS is actually enabled (look for 🔒 in address bar)
- Try different browser
- Check browser microphone permissions

### Certificate expired
- Let's Encrypt: `certbot renew`
- Self-signed: Regenerate with longer validity
- CA cert: Renew from provider

## Quick Commands Reference

```bash
# Development (easiest)
qwen-asr-serve-websocket --generate-self-signed-cert

# Custom self-signed
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
qwen-asr-serve-websocket --ssl-certfile cert.pem --ssl-keyfile key.pem

# Let's Encrypt (production)
sudo certbot certonly --standalone -d yourdomain.com
qwen-asr-serve-websocket --ssl-certfile /etc/letsencrypt/live/yourdomain.com/fullchain.pem --ssl-keyfile /etc/letsencrypt/live/yourdomain.com/privkey.pem

# Behind reverse proxy (no SSL on server)
qwen-asr-serve-websocket --host 127.0.0.1 --port 8000
# Configure Nginx/Caddy to handle SSL
```

## Additional Resources

- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [OpenSSL Documentation](https://www.openssl.org/docs/)
- [Nginx WebSocket Proxy](https://nginx.org/en/docs/http/websocket.html)
- [Caddy Reverse Proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
