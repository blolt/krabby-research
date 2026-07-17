#!/usr/bin/env bash
# Deploy FleetServiceStack via CDK. Requires an activated fleet/infra venv
# (see ./scripts/setup-venv.sh). Puts project-local Node + cdk CLI on PATH.
#
# Requires -c domainName=... -c hostedZoneName=... as arguments to this
# script (forwarded to `cdk deploy` via "$@"; see fleet/infra/fleet-service.md).
# app.py fails cleanly if they're missing.
#
# Example:
#   ./scripts/deploy-fleet-service.sh \
#     -c domainName={domain-name} \
#     -c hostedZoneName={hosted-zone-name}

set -euo pipefail

INFRA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$INFRA_DIR"

# Mirrors the Makefile pattern in krabby-research (VIRTUAL_ENV required).
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  cat >&2 <<'EOF'
No Python virtual environment found (VIRTUAL_ENV is unset).

From fleet/infra:
  ./scripts/setup-venv.sh
  source .venv/bin/activate

Then re-run this script.
EOF
  exit 1
fi

NODE_HOME="$INFRA_DIR/.tools/node"
NPM_GLOBAL="$INFRA_DIR/.tools/npm-global"
export PATH="$NODE_HOME/bin:$NPM_GLOBAL/node_modules/.bin:$PATH"

if [[ ! -x "$NODE_HOME/bin/node" ]] || ! command -v cdk >/dev/null 2>&1; then
  echo "Node/CDK toolkit missing under .tools/. Run: ./scripts/setup-venv.sh" >&2
  exit 1
fi

# Prove the active interpreter is the fleet infra venv (not a random host python).
EXPECTED_VENV="$INFRA_DIR/.venv"
if [[ "$(cd "$VIRTUAL_ENV" && pwd)" != "$(cd "$EXPECTED_VENV" && pwd)" ]]; then
  echo "VIRTUAL_ENV is '$VIRTUAL_ENV' but this script expects '$EXPECTED_VENV'." >&2
  echo "source $EXPECTED_VENV/bin/activate" >&2
  exit 1
fi

echo "Using python: $(command -v python) ($(python -V 2>&1))"
echo "Using node:   $(command -v node) ($(node -v))"
echo "Using cdk:    $(command -v cdk) ($(cdk --version))"

if ! command -v aws >/dev/null 2>&1; then
  echo "AWS CLI ('aws') not found on PATH. Install/configure AWS CLI v2 first." >&2
  exit 1
fi

echo "Using aws:    $(command -v aws) ($(aws --version 2>&1))"

# Fail fast if credentials/session are missing or expired.
export AWS_IDENTITY_JSON
if ! AWS_IDENTITY_JSON="$(aws sts get-caller-identity --output json 2>/dev/null)"; then
  cat >&2 <<'EOF'
AWS credentials are not working (sts:GetCallerIdentity failed).

Fix by ensuring you are logged in (e.g. AWS SSO) or have valid env/credentials:
  - env vars: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
  - shared credentials: ~/.aws/credentials
  - SSO: aws sso login --profile <name>
EOF
  exit 1
fi

AWS_ACCOUNT_ID="$(python - <<'PY'
import json, os, sys
print(json.loads(os.environ["AWS_IDENTITY_JSON"])["Account"])
PY
)"
AWS_ARN="$(python - <<'PY'
import json, os, sys
print(json.loads(os.environ["AWS_IDENTITY_JSON"])["Arn"])
PY
)"
# Last path segment of the ARN: the IAM username, or the SSO session name
# (often an email) for an assumed-role session -- the human-readable
# "who is this" part of the identity, for the confirmation prompt below.
AWS_USER="${AWS_ARN##*/}"

AWS_REGION_EFFECTIVE="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
if [[ -z "$AWS_REGION_EFFECTIVE" ]]; then
  AWS_REGION_EFFECTIVE="$(aws configure get region 2>/dev/null || true)"
fi
if [[ -z "$AWS_REGION_EFFECTIVE" ]]; then
  echo "AWS region is not set. Set AWS_REGION/AWS_DEFAULT_REGION or configure a default region." >&2
  exit 1
fi

echo "Logged in as: $AWS_USER"
echo "AWS account:  $AWS_ACCOUNT_ID"
echo "AWS region:   $AWS_REGION_EFFECTIVE"
read -r -p "Deploy FleetServiceStack to this account? [y/N] " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
  echo "Aborted." >&2
  exit 1
fi

echo "Deploying FleetServiceStack ..."

cdk deploy FleetServiceStack --require-approval never "$@"

# The instance itself only gets OS-level bootstrap (packages, system users,
# directories, Node, Caddy binary) from CDK UserData at first boot -- app code,
# the Caddyfile, and systemd units are pushed here, on every deploy, via SSM
# (there's no SSH access to this box; see FleetServiceSecurityGroup).
echo
echo "Pushing fleet service + portal onto the instance ..."

export STACK_OUTPUTS_JSON
STACK_OUTPUTS_JSON="$(aws cloudformation describe-stacks \
  --stack-name FleetServiceStack \
  --region "$AWS_REGION_EFFECTIVE" \
  --query "Stacks[0].Outputs" --output json)"

_stack_output() {
  STACK_OUTPUT_KEY="$1" python - <<'PY'
import json, os, sys

key = os.environ["STACK_OUTPUT_KEY"]
outputs = json.loads(os.environ["STACK_OUTPUTS_JSON"])
for o in outputs:
    if o["OutputKey"] == key:
        print(o["OutputValue"])
        break
else:
    print(f"error: output {key!r} not found in FleetServiceStack", file=sys.stderr)
    sys.exit(1)
PY
}

INSTANCE_ID="$(_stack_output FleetServiceInstanceId)"
SERVICE_ASSET_BUCKET="$(_stack_output FleetServiceAssetS3BucketName)"
SERVICE_ASSET_KEY="$(_stack_output FleetServiceAssetS3ObjectKey)"
PORTAL_ASSET_BUCKET="$(_stack_output FleetPortalAssetS3BucketName)"
PORTAL_ASSET_KEY="$(_stack_output FleetPortalAssetS3ObjectKey)"
PORTAL_AUTH_SECRET_ARN="$(_stack_output FleetPortalAuthSecretArn)"
TURN_AUTH_SECRET_ARN="$(_stack_output FleetTurnAuthSecretArn)"
DOMAIN_NAME="$(_stack_output FleetServiceDomainName)"
PUBLIC_IP="$(_stack_output FleetServicePublicIp)"
COGNITO_POOL_ID="$(_stack_output FleetCognitoUserPoolId)"
COGNITO_CLIENT_ID="$(_stack_output FleetCognitoUserPoolClientId)"

export REMOTE_SCRIPT
REMOTE_SCRIPT="$(cat <<REMOTE
set -euo pipefail

# coturn may already be present from UserData; install on older instances too.
dnf install -y coturn
getent group turnserver >/dev/null || groupadd --system turnserver
id -u turnserver >/dev/null 2>&1 || \
  useradd --system --no-create-home --shell /usr/sbin/nologin -g turnserver turnserver
systemctl disable --now coturn 2>/dev/null || true
systemctl disable --now turnserver 2>/dev/null || true

# --- fleet service ---
aws s3 cp "s3://${SERVICE_ASSET_BUCKET}/${SERVICE_ASSET_KEY}" /tmp/fleet-service.zip
rm -rf /opt/krabby-fleet-service/src
mkdir -p /opt/krabby-fleet-service/src
unzip -o -q /tmp/fleet-service.zip -d /opt/krabby-fleet-service/src
install -m 0644 /opt/krabby-fleet-service/src/deploy/Caddyfile /etc/caddy/Caddyfile
install -m 0644 /opt/krabby-fleet-service/src/deploy/caddy.service /etc/systemd/system/caddy.service
install -m 0644 /opt/krabby-fleet-service/src/systemd/krabby-fleet-service.service /etc/systemd/system/krabby-fleet-service.service
install -m 0644 /opt/krabby-fleet-service/src/deploy/coturn.service /etc/systemd/system/krabby-coturn.service
/usr/bin/pip3.11 install --quiet --upgrade /opt/krabby-fleet-service/src

TURN_AUTH_SECRET_VALUE="\$(aws secretsmanager get-secret-value \\
  --secret-id '${TURN_AUTH_SECRET_ARN}' \\
  --region '${AWS_REGION_EFFECTIVE}' \\
  --query SecretString --output text)"

# Render coturn conf (shared HMAC secret + public EIP for relay candidates).
umask 027
sed -e "s|__TURN_AUTH_SECRET__|\${TURN_AUTH_SECRET_VALUE}|g" \\
    -e "s|__TURN_REALM__|${DOMAIN_NAME}|g" \\
    -e "s|__TURN_EXTERNAL_IP__|${PUBLIC_IP}|g" \\
    /opt/krabby-fleet-service/src/deploy/turnserver.conf.in \\
    > /etc/krabby-fleet/turnserver.conf
chmod 0640 /etc/krabby-fleet/turnserver.conf
# turnserver package user needs read access to the conf.
if id turnserver >/dev/null 2>&1; then
  chown root:turnserver /etc/krabby-fleet/turnserver.conf
else
  chown root:root /etc/krabby-fleet/turnserver.conf
fi

# Fleet service env: TURN host (DNS) + same auth secret for minting credentials.
cat > /etc/krabby-fleet/service.env <<ENV
KRABBY_FLEET_TURN_AUTH_SECRET=\${TURN_AUTH_SECRET_VALUE}
KRABBY_FLEET_TURN_HOST=${DOMAIN_NAME}
ENV
chown root:krabby-fleet /etc/krabby-fleet/service.env
chmod 0640 /etc/krabby-fleet/service.env

# --- portal (Next.js standalone) ---
aws s3 cp "s3://${PORTAL_ASSET_BUCKET}/${PORTAL_ASSET_KEY}" /tmp/fleet-portal.zip
rm -rf /opt/krabby-fleet-portal-src
mkdir -p /opt/krabby-fleet-portal-src
unzip -o -q /tmp/fleet-portal.zip -d /opt/krabby-fleet-portal-src
cd /opt/krabby-fleet-portal-src
# Build-time placeholders; runtime values come from /etc/krabby-fleet/portal.env.
# DevDependencies (typescript) are required for \`next build\`.
export AUTH_SECRET=build-placeholder
export AUTH_URL="https://${DOMAIN_NAME}"
export AUTH_COGNITO_ID="${COGNITO_CLIENT_ID}"
export AUTH_COGNITO_ISSUER="https://cognito-idp.${AWS_REGION_EFFECTIVE}.amazonaws.com/${COGNITO_POOL_ID}"
export FLEET_SERVICE_URL="http://127.0.0.1:8080"
/usr/local/bin/npm ci
/usr/local/bin/npm run build
bash scripts/assemble-standalone.sh /opt/krabby-fleet-portal-src /opt/krabby-fleet-portal
install -m 0644 /opt/krabby-fleet-portal-src/systemd/krabby-fleet-portal.service \\
  /etc/systemd/system/krabby-fleet-portal.service
chown -R krabby-fleet:krabby-fleet /opt/krabby-fleet-portal

AUTH_SECRET_VALUE="\$(aws secretsmanager get-secret-value \\
  --secret-id '${PORTAL_AUTH_SECRET_ARN}' \\
  --region '${AWS_REGION_EFFECTIVE}' \\
  --query SecretString --output text)"
umask 027
cat > /etc/krabby-fleet/portal.env <<ENV
AUTH_SECRET=\${AUTH_SECRET_VALUE}
AUTH_URL=https://${DOMAIN_NAME}
AUTH_COGNITO_ID=${COGNITO_CLIENT_ID}
AUTH_COGNITO_ISSUER=https://cognito-idp.${AWS_REGION_EFFECTIVE}.amazonaws.com/${COGNITO_POOL_ID}
FLEET_SERVICE_URL=http://127.0.0.1:8080
ENV
chown root:krabby-fleet /etc/krabby-fleet/portal.env
chmod 0640 /etc/krabby-fleet/portal.env

systemctl daemon-reload
systemctl enable caddy krabby-fleet-service krabby-fleet-portal krabby-coturn
systemctl restart krabby-coturn krabby-fleet-service krabby-fleet-portal caddy
REMOTE
)"

# JSON built with python (not CLI shorthand) so embedded newlines/quotes in
# the multi-line script above can't be misparsed by --parameters shorthand.
# executionTimeout covers npm ci + next build on a cold instance.
export SSM_PARAMS_JSON
SSM_PARAMS_JSON="$(python - <<'PY'
import json, os
print(json.dumps({
    "commands": [os.environ["REMOTE_SCRIPT"]],
    "executionTimeout": ["3600"],
}))
PY
)"

COMMAND_ID="$(aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "krabby-fleet service+portal+coturn app deploy" \
  --region "$AWS_REGION_EFFECTIVE" \
  --parameters "$SSM_PARAMS_JSON" \
  --query "Command.CommandId" --output text)"

echo "Waiting for SSM command $COMMAND_ID to finish on $INSTANCE_ID ..."
aws ssm wait command-executed \
  --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" --region "$AWS_REGION_EFFECTIVE" || true

SSM_STATUS="$(aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" --region "$AWS_REGION_EFFECTIVE" \
  --query "Status" --output text)"

if [[ "$SSM_STATUS" != "Success" ]]; then
  echo "App deploy failed on the instance (status: $SSM_STATUS):" >&2
  aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" --region "$AWS_REGION_EFFECTIVE" \
    --query "StandardErrorContent" --output text >&2
  exit 1
fi

echo "[ok] krabby-fleet-service + krabby-fleet-portal + krabby-coturn deployed and restarted."
echo "     Caddy: /api/auth* + UI -> portal:3000; other /api/* -> service:8080"
echo "     TURN:  UDP/TCP 3478 + relay 49152-65535/udp (ICE via GET /api/teleop/ice-servers)"
