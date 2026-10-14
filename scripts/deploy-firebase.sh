#!/usr/bin/env bash
# Put Firebase Hosting in front of the Cloud Run service, so the app is served
# at https://PROJECT.web.app. Run by deploy-cloudrun.sh, or on its own in
# Cloud Shell from the repository folder:
#
#   bash scripts/deploy-firebase.sh
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-southeast1}"
SERVICE="${SERVICE:-facefinder}"
FIREBASE="npx --yes firebase-tools@14"
cd "$(dirname "$0")/.."

# Firebase needs its own sign-in once per Cloud Shell; gcloud's is not enough.
if ! $FIREBASE projects:list --non-interactive >/dev/null 2>&1; then
  echo "Firebase needs you to sign in once. Follow the link below, approve, and paste the code back here."
  $FIREBASE login --no-localhost
fi

# The project must be a Firebase project and have a Hosting site named after it.
$FIREBASE projects:addfirebase "$PROJECT" >/dev/null 2>&1 || true
$FIREBASE hosting:sites:create "$PROJECT" --project "$PROJECT" --non-interactive >/dev/null 2>&1 || true

# firebase.json in the repo has no site name; deploy from a copy that does.
cat > firebase.deploy.json <<JSON
{
  "hosting": {
    "site": "$PROJECT",
    "public": "firebase/public",
    "ignore": ["**/.*"],
    "rewrites": [
      { "source": "**", "run": { "serviceId": "$SERVICE", "region": "$REGION" } }
    ]
  }
}
JSON
$FIREBASE deploy --only hosting --project "$PROJECT" --config firebase.deploy.json --non-interactive
rm -f firebase.deploy.json

echo
echo "Firebase Hosting is live: https://${PROJECT}.web.app"
