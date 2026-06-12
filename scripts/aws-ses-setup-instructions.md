# AWS SES Setup Instructions for Zenith Grid Email

**Give these instructions to the Claude instance that has aws-cli access on MacBook.**

---

## Context

The Zenith Grid trading platform on `fedora.local` needs to send transactional emails (email verification for signup, password reset) via Amazon SES. The backend uses `boto3`; on the current self-hosted production box, credentials should come from the host/container environment rather than an EC2 instance role. All SES API calls go over HTTPS (port 443), so no SMTP/port 25 issues.

- **Region**: us-east-1
- **Sender email**: noreply@romerotechsolutions.com
- **Domain**: romerotechsolutions.com
- **Production host**: `louis@fedora.local`, app in `zenith-box`

---

## Step 1: Verify the sender domain in SES

```bash
# Verify the domain (returns DNS records you need to add)
aws ses verify-domain-identity --domain romerotechsolutions.com --region us-east-1

# Also set up DKIM for better deliverability
aws ses verify-domain-dkim --domain romerotechsolutions.com --region us-east-1

# Check verification status (may take a few minutes after DNS propagation)
aws ses get-identity-verification-attributes --identities romerotechsolutions.com --region us-east-1
```

You'll need to add the returned TXT record and CNAME records to DNS for romerotechsolutions.com. The domain won't be verified until these DNS records propagate.

---

## Step 2: Request SES production access (exit sandbox)

In sandbox mode, SES can only send to verified email addresses. You need production access to send to any email:

```bash
# Check current sending limits (if Max24HourSend is 200, you're in sandbox)
aws ses get-send-quota --region us-east-1

# Request production access
aws sesv2 put-account-details \
  --production-access-enabled \
  --mail-type TRANSACTIONAL \
  --website-url "https://tradebot.romerotechsolutions.com" \
  --use-case-description "Transactional emails for user signup verification and password resets for our trading platform. Low volume (< 50 emails/day)." \
  --contact-language EN \
  --region us-east-1
```

This may take up to 24 hours for AWS to approve. In the meantime, you can test by verifying a specific recipient email:

```bash
# Verify a test recipient (while in sandbox mode)
aws ses verify-email-identity --email-address your-test-email@example.com --region us-east-1
```

---

## Step 3: Provide SES credentials to production

The current production host is not EC2, so there is no instance role to attach. Create or use an IAM principal with SES send permissions and expose credentials to the `zenithgrid.service` environment, preferably via the host/user environment or a systemd user drop-in read by the service.

### Create an IAM user or role policy:

```bash
ROLE_NAME=ZenithGridSesSender  # or the IAM user/role used by production

aws iam put-role-policy --role-name $ROLE_NAME \
  --policy-name SES-SendEmail \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "*"
    }]
  }'
```

---

## Step 4: Verify it works

After DNS propagation and SES verification, test from the production host:

```bash
# SSH to fedora.local and test inside the app container
ssh louis@fedora.local
distrobox enter --name zenith-box
cd ~/ZenithGrid/backend
./venv/bin/python3 -c "
import boto3
client = boto3.client('ses', region_name='us-east-1')
print('SES connection OK')
print('Send quota:', client.get_send_quota())
"
```

No code changes are needed. If you change service environment variables, restart `zenithgrid.service` from the host with `systemctl --user restart zenithgrid`.

---

## Summary of DNS Records Needed

After running Step 1, you'll get:
1. **TXT record** for domain verification (from `verify-domain-identity`)
2. **3 CNAME records** for DKIM (from `verify-domain-dkim`)

Add these to your DNS provider for romerotechsolutions.com.

---

## Troubleshooting

- **"Email address is not verified"**: Domain DNS records haven't propagated yet, or still in sandbox sending to unverified recipient
- **"Access denied"**: IAM policy not attached to instance role, or instance profile not associated
- **"Throttling"**: Hit SES send limits (default sandbox: 200/day, 1/second)
