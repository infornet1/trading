# Vizniago Email Setup — viznago.finance

## Overview

Custom `@viznago.finance` email addresses for the team using:
- **Cloudflare Email Routing** — inbound forwarding (free, built into Cloudflare)
- **Brevo (ex-Sendinblue)** — outbound SMTP relay (free tier: 300 emails/day)
- **Gmail "Send As"** — compose and reply from `@viznago.finance` inside Gmail

No mail server to maintain. Each team member keeps their personal Gmail but sends/receives as Vizniago.

---

## Step 1 — Cloudflare Email Routing (Inbound)

1. Go to **Cloudflare Dashboard → viznago.finance → Email → Email Routing**
2. Enable Email Routing → Cloudflare auto-adds the required MX records
3. Add address rules:

   | Custom address | Forwards to |
   |---|---|
   | `admin@viznago.finance` | your personal Gmail |
   | `team@viznago.finance` | shared inbox or alias |
   | `hello@viznago.finance` | support inbox |
   | `noreply@viznago.finance` | catch-all or discard |

4. Verify each destination email when prompted.

---

## Step 2 — Brevo SMTP Relay (Outbound)

1. Create a free account at **brevo.com**
2. Go to **Settings → Senders & IP → Domains → Add a Domain**
   - Enter `viznago.finance`
   - Brevo will provide DNS records to add in Cloudflare (SPF, DKIM)
3. Go to **Settings → SMTP & API → SMTP tab**
   - Note your SMTP credentials:
     - Server: `smtp-relay.brevo.com`
     - Port: `587` (TLS)
     - Login: your Brevo account email
     - Password: generated SMTP key

---

## Step 3 — Gmail "Send As" Setup (per team member)

1. Open Gmail → **Settings (⚙) → See all settings → Accounts and Import**
2. Under **"Send mail as"** → click **Add another email address**
3. Fill in:
   - Name: `Vizniago Fury` (or your name)
   - Email: `admin@viznago.finance` (your address)
   - Uncheck "Treat as alias"
4. Click **Next Step** → enter SMTP relay:
   - SMTP Server: `smtp-relay.brevo.com`
   - Port: `587`
   - Username: Brevo account email
   - Password: Brevo SMTP key
   - Select: **Secured connection using TLS**
5. Gmail sends a **verification code** to `admin@viznago.finance`
   → arrives via Cloudflare routing → forwarded to your personal Gmail
   → enter the code to confirm
6. Done — in Gmail compose, use the **From:** dropdown to pick `@viznago.finance`

---

## Step 4 — DNS Records on Cloudflare

Add all records under **viznago.finance → DNS**:

| Type | Name | Value | Purpose |
|------|------|-------|---------|
| MX | `@` | (auto-added by Cloudflare Email Routing) | Inbound mail |
| TXT | `@` | `v=spf1 include:spf.brevo.com ~all` | SPF — authorize Brevo to send |
| CNAME | `brevo._domainkey` | (provided by Brevo during domain verification) | DKIM signing |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@viznago.finance` | DMARC reporting |

> **Note:** SPF record must include both Cloudflare and Brevo entries if Cloudflare adds its own.
> Combined: `v=spf1 include:spf.brevo.com include:_spf.mx.cloudflare.net ~all`

---

## Limits & Scaling

| Tier | Limit | Cost |
|------|-------|------|
| Brevo Free | 300 emails/day, 9,000/month | $0 |
| Brevo Starter | 20,000/month | ~$9/mo |
| Cloudflare Email Routing | Unlimited forwarding | $0 always |

For transactional emails from the app (bot alerts, subscription confirmations) see `SAAS_PLAN.md` — those go through a separate Brevo API key, not the team SMTP relay.

---

## Team Address Conventions

| Address | Owner | Use |
|---------|-------|-----|
| `admin@viznago.finance` | Gustavo | Admin panel, server alerts |
| `team@viznago.finance` | Shared | Public-facing, partnerships |
| `hello@viznago.finance` | Support | User support, onboarding |
| `noreply@viznago.finance` | App | Automated bot notifications |

---

## Troubleshooting

**Emails going to spam:**
- Confirm SPF and DKIM records are both verified green in Brevo dashboard
- Add DMARC record if missing
- Warm up the domain: start with low volume for first 2 weeks

**Verification code not arriving:**
- Check Cloudflare Email Routing rules are active
- Check destination Gmail spam folder
- Confirm the forwarding destination is verified in Cloudflare

**"Send As" not showing in Gmail:**
- Gmail caches settings — try hard refresh or new browser tab
- Re-check SMTP credentials (Brevo SMTP key ≠ Brevo account password)

---

*Last updated: 2026-03-21*
