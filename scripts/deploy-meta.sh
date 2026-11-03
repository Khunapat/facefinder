#!/usr/bin/env bash
# Deploy the Meta edition of FaceFinder (Muse Spark instead of Gemini) as its
# own Cloud Run service, next to the Google one, with its own Firestore
# database. It does not touch the Google service, its data or Firebase Hosting.
# Run it in Google Cloud Shell, from the repository folder:
#
#   bash scripts/deploy-meta.sh
#
# The first run asks for the Meta Model API key once (hidden) and keeps it in
# Secret Manager as ff-meta-api-key. Before deploying it checks that the key
# works: it lists the Muse models and makes one small image call.
#
# Settings (optional, as environment variables before the command):
#   META_MODEL   the model id (default: muse-spark-1.1 if the key can use it)
#   CPU          2 or 4 (default: 4)
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-asia-southeast1}"
SERVICE=facefinder-meta
DB=meta
CPU="${CPU:-4}"
MEMORY="$([ "$CPU" -ge 4 ] && echo 8Gi || echo 4Gi)"
WORKERS="$([ "$CPU" -ge 4 ] && echo 6 || echo 4)"
SAMPLE_ALBUM="$(cat "$HOME/.facefinder-sample" 2>/dev/null || true)"
say() { printf '\n\033[1;35m== %s\033[0m\n' "$*"; }
cd "$(dirname "$0")/.."
gcloud config set project "$PROJECT" >/dev/null

say "1/5  The Meta Model API key"
if ! gcloud secrets describe ff-meta-api-key >/dev/null 2>&1; then
  read -rsp "Paste your Meta Model API key, then Enter (it stays hidden): " KEY; echo
  printf %s "$KEY" | gcloud secrets create ff-meta-api-key --data-file=- --replication-policy=automatic >/dev/null
fi
KEY="$(gcloud secrets versions access latest --secret=ff-meta-api-key)"

say "2/5  Checking the key with Meta"
MODELS="$(curl -s -H "Authorization: Bearer $KEY" https://api.meta.ai/v1/models || true)"
IDS="$(printf %s "$MODELS" | python3 -c 'import json,sys
try: print(" ".join(m["id"] for m in json.load(sys.stdin).get("data", [])))
except Exception: print("")')"
if [ -z "$IDS" ]; then
  echo "Meta did not list any models for this key. What it said:"; printf '%s\n' "$MODELS" | head -c 600; echo
  echo "Check the key, the credits and the card on the Meta Model API dashboard, then run this again."
  echo "To paste a new key: gcloud secrets versions add ff-meta-api-key --data-file=- , paste, Enter, Ctrl+D"
  exit 1
fi
echo "Models this key can use: $IDS"
if [ -z "${META_MODEL:-}" ]; then
  META_MODEL=muse-spark-1.1
  case " $IDS " in *" muse-spark-1.1 "*) ;; *)
    META_MODEL="$(printf '%s\n' $IDS | grep '^muse-spark' | grep -v open | sort -V | tail -1)";;
  esac
fi
echo "Using: $META_MODEL"
TEST="$(python3 - "$META_MODEL" <<'PY'
import json, sys
img = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCAAwAEADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDXooopn1QUUVj6h4p03T7gwM0k0ikhxEoO0+hJIH5elFrkTqRgrydjYorBsvGGm3TpHL5lszAZMgGzPpkfzIH4VvUNWFCpCorxdwooooNAooooAx/FOoTafoxaAlZJXEYdTgrkEk/kMfjXndd94wsmutG82NAzW7hycZbbjBx+hP09q4GtIbHh49y9rrtYK7jwXqE11YzWspL/AGYrsYn+E5wv4Y/X2rh67PwPZMlvcXjoAJSEjYjnAznHtnH4j2py2IwLl7ZWOpooorI98KKKKACub1DwXa3VwZbWc2u4ksmzcv4DIx3/APrV0lFNNoyqUoVFaauctZeB4UdHvLoygAFo412jPpnqR17A/SuoRFjRURQqqMKqjAA9KWihtsKdGFJe4gooopGp/9k="
print(json.dumps({"model": sys.argv[1], "messages": [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": img}},
    {"type": "text", "text": "Describe this tiny test image in a few words."}]}],
    "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": {
        "type": "object", "properties": {"description": {"type": "string"}},
        "required": ["description"], "additionalProperties": False}}}}))
PY
)"
ANSWER="$(curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d "$TEST" https://api.meta.ai/v1/chat/completions || true)"
echo "Test answer (send this line to Claude if anything looks wrong):"
printf '%s\n' "$ANSWER" | head -c 700; echo
printf %s "$ANSWER" | grep -q '"choices"' || { echo "The test call failed; nothing was deployed."; exit 1; }

say "3/5  A separate Firestore database for the Meta edition"
if ! gcloud firestore databases describe --database="$DB" >/dev/null 2>&1; then
  gcloud firestore databases create --database="$DB" --location="$REGION" --type=firestore-native
fi

say "4/5  Building and deploying $SERVICE (5 to 10 minutes)"
GOOGLE_URL="$(gcloud run services describe facefinder --region "$REGION" --format='value(status.url)' 2>/dev/null || true)"
BASE_URL="${GOOGLE_URL/https:\/\/facefinder-/https://$SERVICE-}"
gcloud run deploy "$SERVICE" --source . --region "$REGION" \
  --allow-unauthenticated \
  --memory "$MEMORY" --cpu "$CPU" --no-cpu-throttling \
  --min-instances 0 --max-instances 1 --concurrency 40 --timeout 3600 \
  --set-env-vars "STORE=firestore,FIRESTORE_DATABASE=$DB,GOOGLE_CLOUD_PROJECT=$PROJECT,AI_PROVIDER=meta,META_MODEL=$META_MODEL,PUBLIC_BASE_URL=$BASE_URL,INDEX_WORKERS=$WORKERS${SAMPLE_ALBUM:+,SAMPLE_ALBUM=$SAMPLE_ALBUM}" \
  --set-secrets "GOOGLE_CLIENT_ID=ff-google-client-id:latest,GOOGLE_CLIENT_SECRET=ff-google-client-secret:latest,SESSION_SECRET=ff-session-secret:latest,META_API_KEY=ff-meta-api-key:latest" \
  --quiet
RUN_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
if [ "$RUN_URL" != "$BASE_URL" ]; then
  gcloud run services update "$SERVICE" --region "$REGION" --update-env-vars "PUBLIC_BASE_URL=$RUN_URL" --quiet
fi

say "5/5  Done"
curl -s -o /dev/null -w "The Meta edition answers: %{http_code}\n" "$RUN_URL/api/me"
cat <<MSG

The Meta edition is at:  $RUN_URL

Google sign-in needs this address once (only the first time):
  https://console.cloud.google.com/apis/credentials?project=$PROJECT
  -> Web client 1 -> Authorized JavaScript origins -> Add URI:  $RUN_URL
                  -> Authorized redirect URIs      -> Add URI:  $RUN_URL/oauth2/callback
  -> Save
MSG
