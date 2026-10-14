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
# Both steps print their errors: a project that was never added to Firebase
# usually needs its terms accepted once at console.firebase.google.com.
if ! $FIREBASE hosting:sites:list --project "$PROJECT" --non-interactive 2>/dev/null | grep -q "$PROJECT"; then
  $FIREBASE projects:addfirebase "$PROJECT" --non-interactive 2>&1 | grep -v "already" || true
  if ! $FIREBASE hosting:sites:create "$PROJECT" --project "$PROJECT" --non-interactive; then
    cat <<MSG

Could not create the Firebase Hosting site. Do this once in the browser:
  1. https://console.firebase.google.com  ->  "Add Firebase to a Google Cloud project"
     (or "Create a project" -> pick $PROJECT), accept the terms, Analytics off.
  2. In that Firebase project: Build > Hosting > Get started, click through.
Then run:  bash scripts/deploy-firebase.sh
MSG
    exit 1
  fi
fi

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
