# Deploy Aspect Code API to Cloud Run
# Usage: ./deploy.ps1

Write-Host "Deploying Aspect Code API to Cloud Run..." -ForegroundColor Cyan

$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

Set-Location $PSScriptRoot

gcloud run deploy aspectcode-api `
  --source . `
  --region us-central1 `
  --allow-unauthenticated `
  --memory 1Gi `
  --cpu 1 `
  --concurrency 2 `
  --min-instances 0 `
  --max-instances 5 `
  --set-env-vars "ASPECT_CODE_MODE=both" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,ASPECT_CODE_API_KEYS_RAW=ASPECT_CODE_API_KEYS_RAW:latest" `
  --no-invoker-iam-check

if ($LASTEXITCODE -eq 0) {
  Write-Host "`n✅ Deployment successful!" -ForegroundColor Green
  Write-Host "API is live at: https://api.aspectcode.com" -ForegroundColor Green
} else {
  Write-Host "`n❌ Deployment failed!" -ForegroundColor Red
}
