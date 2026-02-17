# AWS SES Setup Instructions for Zenith Grid Email

**Give these instructions to the Claude instance that has aws-cli access on MacBook.**

---

## Context

The Zenith Grid trading platform on EC2 needs to send transactional emails (email verification for signup, password reset) via Amazon SES. The backend uses `boto3` with IAM instance role auth (no API keys needed in code). All SES API calls go over HTTPS (port 443), so no SMTP/port 25 issues.

- **Region**: us-east-1
- **Sender email**: noreply@romerotechsolutions.com
- **Domain**: romerotechsolutions.com
- **EC2 instance**: the one running ZenithGrid (tagged with "trade" in name)

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

## Step 3: Attach SES permission to the EC2 instance role

The EC2 instance needs an IAM role with SES send permissions.

### Find the EC2 instance:

```bash
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=*trade*" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text --region us-east-1)

echo "Instance ID: $INSTANCE_ID"
```

### Check if instance already has an IAM role:

```bash
PROFILE_ARN=$(aws ec2 describe-instances \
  --instance-ids $INSTANCE_ID \
  --query "Reservations[0].Instances[0].IamInstanceProfile.Arn" \
  --output text --region us-east-1)

echo "Instance Profile ARN: $PROFILE_ARN"
```

### If NO instance profile (shows "None"):

```bash
# Create the IAM role
aws iam create-role --role-name ZenithGridEC2Role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Create instance profile and attach role
aws iam create-instance-profile --instance-profile-name ZenithGridEC2Profile
aws iam add-role-to-instance-profile \
  --instance-profile-name ZenithGridEC2Profile \
  --role-name ZenithGridEC2Role

# Associate profile with EC2 instance
aws ec2 associate-iam-instance-profile \
  --instance-id $INSTANCE_ID \
  --iam-instance-profile Name=ZenithGridEC2Profile
```

### If instance already has a profile, find the role name:

```bash
ROLE_NAME=$(echo $PROFILE_ARN | awk -F'/' '{print $NF}')
# Note: instance profile name and role name might differ
# You may need to look it up:
aws iam get-instance-profile --instance-profile-name $ROLE_NAME \
  --query "InstanceProfile.Roles[0].RoleName" --output text
```

### Attach SES send policy to the role:

```bash
ROLE_NAME=ZenithGridEC2Role  # <-- adjust if your role has a different name

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

After DNS propagation and SES verification, test from the EC2 instance:

```bash
# SSH to EC2 and test
ssh testbot
cd ZenithGrid/backend
./venv/bin/python3 -c "
import boto3
client = boto3.client('ses', region_name='us-east-1')
print('SES connection OK')
print('Send quota:', client.get_send_quota())
"
```

No code changes or backend restarts needed on EC2. The `boto3` library is already installed and the app picks up IAM role credentials automatically.

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
