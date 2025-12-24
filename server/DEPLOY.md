# Deploying Aspect Code API to Google Cloud Run

## Prerequisites

1. Google Cloud project with billing enabled
2. `gcloud` CLI installed and authenticated
3. Neon PostgreSQL database with connection string

## Quick Deploy (Manual)

```bash
# From the server/ directory
cd server

# Set your project
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com run.googleapis.com secretmanager.googleapis.com

# Create secret for DATABASE_URL
echo -n "postgresql://user:pass@host/db?sslmode=require" | \
  gcloud secrets create DATABASE_URL --data-file=-

# Grant Cloud Run access to the secret
gcloud secrets add-iam-policy-binding DATABASE_URL \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Deploy (first time - will build and deploy)
gcloud run deploy aspectcode-api \
  --source . \
  --region us-central1 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 60s \
  --concurrency 2 \
  --min-instances 0 \
  --max-instances 5 \
  --set-env-vars ASPECT_CODE_MODE=prod \
  --set-secrets DATABASE_URL=DATABASE_URL:latest \
  --allow-unauthenticated
```

## CI/CD with Cloud Build

1. Connect your GitHub repo in Cloud Console > Cloud Build > Triggers
2. Create a trigger on push to `main` branch, using `server/cloudbuild.yaml`
3. Set substitution variable `_REGION=us-central1` (or your preferred region)

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Neon PostgreSQL connection string |
| `ASPECT_CODE_MODE` | No | `alpha`, `prod`, or `both` (default: `prod`) |
| `ASPECT_CODE_API_KEYS_RAW` | No | Comma-separated admin keys |
| `ASPECT_CODE_MIN_CLIENT_VERSION` | No | Minimum extension version (e.g., `0.1.0`) |
| `ASPECT_CODE_RATE_LIMIT` | No | Requests per minute per key (default: `60`) |

## Monitoring

```bash
# View logs
gcloud run services logs read aspectcode-api --region us-central1

# Check service status
gcloud run services describe aspectcode-api --region us-central1

# Get the service URL
gcloud run services describe aspectcode-api --region us-central1 --format='value(status.url)'
```

## Scaling Guidance

**Start with:**
- Memory: 1 GB
- CPU: 1
- Max instances: 5
- Concurrency: 2 (tree-sitter is CPU-bound)

**Scale up if:**
- OOM errors in logs → increase memory to 2 GB
- High latency under load → increase max instances
- Request timeouts → increase timeout (max 3600s)

## Cost Estimate (Alpha Stage)

- Cloud Run free tier: 2M requests/month, 360K GB-seconds
- Expected cost: $0-5/month for <1000 users
- Neon free tier: 0.5 GB storage, 100 hours compute/month

## Troubleshooting

**Container fails to start:**
```bash
gcloud run services logs read aspectcode-api --region us-central1 --limit 50
```

**Database connection fails:**
- Verify DATABASE_URL secret is accessible
- Check Neon dashboard for connection limits
- Ensure `?sslmode=require` in connection string

**Cold start too slow:**
- Set `--min-instances 1` (costs ~$15/month)
- Or accept 2-3s cold starts for alpha
