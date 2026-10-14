#!/usr/bin/env bash
# Deploy FaceFinder to Google Cloud: Cloud Run for the app, Firestore for the
# index, Gemini on Vertex AI for curation, Firebase Hosting for the public
# address in front. Run it in Google Cloud Shell, from the repository folder:
#
#   bash scripts/deploy-cloudrun.sh
#
# Safe to run again: every step checks what already exists. The first run asks
# for the OAuth client ID and secret once and keeps them in Secret Manager.
#
# Settings (optional, as environment variables before the command):
#   PROJECT        Google Cloud project id   (default: the one Cloud Shell is set to)
#   REGION         Cloud Run and Firestore    (default: asia-southeast1)
#   MIN_INSTANCES  1 keeps one copy always warm, so the first visit is instant
#                  but it is billed all day; 0 lets it sleep (default: 0)
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-southeast1}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"
SERVICE=facefinder
BASE_URL="https://${PROJECT}.web.app"

say() { printf '\n\033[1;35m== %s\033[0m\n' "$*"; }

if [ -z "$PROJECT" ]; then
  echo "No project selected. Run:  gcloud config set project YOUR-PROJECT-ID" >&2
  exit 1
fi
cd "$(dirname "$0")/.."
gcloud config set project "$PROJECT" >/dev/null

say "1/6  Checking billing on $PROJECT"
BILLING="$(gcloud billing projects describe "$PROJECT" --format='value(billingEnabled)' 2>/dev/null || echo unknown)"
# A linked account that is closed or past due still reads as enabled here, but
# Google refuses paid APIs. Check the account itself too.
ACCOUNT="$(gcloud billing projects describe "$PROJECT" --format='value(billingAccountName)' 2>/dev/null || true)"
if [ -n "$ACCOUNT" ] && [ "$(gcloud billing accounts describe "${ACCOUNT#billingAccounts/}" --format='value(open)' 2>/dev/null)" = "False" ]; then
  BILLING=False
fi
if [ "$BILLING" = unknown ]; then
  echo "Could not read the billing status; carrying on. If a later step says billing is required, see the link below."
elif [ "$BILLING" != "True" ]; then
  cat >&2 <<MSG
Billing is not working for project $PROJECT: no billing account is linked,
or the linked one is closed or has no valid payment method (Google then says
BILLING_DISABLED). Cloud Run, Firestore, Secret Manager and Gemini all need it.
  1. https://console.cloud.google.com/billing  ->  Payment overview: add a valid card
  2. https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT
     -> make sure the project is linked to that billing account
Wait two or three minutes after fixing it, then run this again.
MSG
  exit 1
fi

say "2/6  Switching on the Google Cloud services (takes a minute the first time)"
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  firestore.googleapis.com aiplatform.googleapis.com secretmanager.googleapis.com \
  firebase.googleapis.com firebasehosting.googleapis.com

say "3/6  Firestore database"
if ! gcloud firestore databases describe --database="(default)" >/dev/null 2>&1; then
  gcloud firestore databases create --database="(default)" --location="$REGION" --type=firestore-native
fi

say "4/6  Permissions and secrets"
NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA="${NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/datastore.user roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
    --role="$role" --condition=None --quiet >/dev/null
done
# Cloud Build deploys from source with the same account.
for role in roles/run.builder roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" \
    --role="$role" --condition=None --quiet >/dev/null 2>&1 || true
done

secret() {   # name, prompt; asks only if the secret does not exist yet
  if ! gcloud secrets describe "$1" >/dev/null 2>&1; then
    local value
    if [ "$1" = ff-session-secret ]; then
      value="$(openssl rand -hex 32)"
    else
      read -rsp "$2: " value; echo
    fi
    if ! printf %s "$value" | gcloud secrets create "$1" --data-file=- --replication-policy=automatic >/dev/null; then
      echo "Could not save the secret. If the error above says BILLING_DISABLED, fix billing (see the top of this script), wait a few minutes and run it again." >&2
      exit 1
    fi
  fi
}
secret ff-google-client-id     "Paste the OAuth client ID (APIs & Services > Credentials), then Enter"
secret ff-google-client-secret "Paste the OAuth client secret, then Enter (it stays hidden)"
secret ff-session-secret       ""

say "5/6  Building and deploying to Cloud Run (5 to 10 minutes)"
# Scans and exports run in background threads inside the instance, so the CPU
# must stay on between requests and there must be exactly one instance.
gcloud run deploy "$SERVICE" --source . --region "$REGION" \
  --allow-unauthenticated \
  --memory 4Gi --cpu 2 --no-cpu-throttling \
  --min-instances "$MIN_INSTANCES" --max-instances 1 --concurrency 40 \
  --timeout 3600 \
  --set-env-vars "STORE=firestore,GOOGLE_CLOUD_PROJECT=$PROJECT,GEMINI_LOCATION=global,PUBLIC_BASE_URL=$BASE_URL" \
  --set-secrets "GOOGLE_CLIENT_ID=ff-google-client-id:latest,GOOGLE_CLIENT_SECRET=ff-google-client-secret:latest,SESSION_SECRET=ff-session-secret:latest" \
  --quiet
RUN_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"

say "6/6  Firebase Hosting in front of Cloud Run"
if ! PROJECT="$PROJECT" REGION="$REGION" SERVICE="$SERVICE" bash scripts/deploy-firebase.sh; then
  cat <<MSG

Cloud Run is up at $RUN_URL, but Firebase Hosting did not deploy.
Fix what the error above says, then run only the Firebase part:
  bash scripts/deploy-firebase.sh
MSG
  exit 1
fi

cat <<MSG

Done.

  FaceFinder:       $BASE_URL
  Cloud Run direct: $RUN_URL

One last step by hand, the first time only. Google must know the sign-in
address. Open
  https://console.cloud.google.com/apis/credentials?project=$PROJECT
click the OAuth client, and under "Authorized redirect URIs" add
  $BASE_URL/oauth2/callback
then Save. Sign-in works a minute or two later.
MSG
