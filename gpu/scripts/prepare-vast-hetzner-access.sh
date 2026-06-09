#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 GPU_SSH_HOST HETZNER_SSH_HOST JOB_ID" >&2
  echo "Example: $0 root@10.0.0.1 user@staging-host.example.com my-job-001" >&2
  exit 2
fi

GPU_SSH_HOST="$1"
HETZNER_SSH_HOST="$2"
JOB_ID="$3"
SAFE_ID="$(printf '%s' "${JOB_ID}" | tr -c 'A-Za-z0-9_.-' '_')"
KEY_NAME="wws_hetzner_${SAFE_ID}"
COMMENT="wws-vast-hetzner-${SAFE_ID}"

if [[ "${HETZNER_SSH_HOST}" == *@* ]]; then
  HETZNER_USER="${HETZNER_SSH_HOST%@*}"
  HETZNER_HOST="${HETZNER_SSH_HOST#*@}"
else
  HETZNER_USER="${USER:-collin}"
  HETZNER_HOST="${HETZNER_SSH_HOST}"
fi

echo "[vast-access] creating temporary key on ${GPU_SSH_HOST}"
PUB_KEY="$(
  ssh "${GPU_SSH_HOST}" "set -eu
mkdir -p ~/.ssh
chmod 700 ~/.ssh
if [ ! -f ~/.ssh/${KEY_NAME} ]; then
  ssh-keygen -t ed25519 -N '' -C '${COMMENT}' -f ~/.ssh/${KEY_NAME} >/dev/null
fi
cat ~/.ssh/${KEY_NAME}.pub"
)"

echo "[vast-access] authorizing temporary key on ${HETZNER_SSH_HOST}"
printf '%s\n' "${PUB_KEY}" | ssh "${HETZNER_SSH_HOST}" "set -eu
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
tmp=\"\$(mktemp)\"
cat > \"\${tmp}\"
if ! grep -Fq '${COMMENT}' ~/.ssh/authorized_keys; then
  cat \"\${tmp}\" >> ~/.ssh/authorized_keys
fi
rm -f \"\${tmp}\""

echo "[vast-access] writing Hetzner SSH config on ${GPU_SSH_HOST}"
ssh "${GPU_SSH_HOST}" "set -eu
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/config
chmod 600 ~/.ssh/config
python3 - <<'PY'
from pathlib import Path

path = Path.home() / '.ssh' / 'config'
text = path.read_text(encoding='utf-8') if path.exists() else ''
begin = '# BEGIN ${COMMENT}'
end = '# END ${COMMENT}'
block = '''# BEGIN ${COMMENT}
Host ${HETZNER_HOST}
  HostName ${HETZNER_HOST}
  User ${HETZNER_USER}
  IdentityFile ~/.ssh/${KEY_NAME}
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
# END ${COMMENT}
'''
if begin in text and end in text:
    before = text.split(begin, 1)[0].rstrip()
    after = text.split(end, 1)[1].lstrip()
    text = '\\n\\n'.join(part for part in (before, block.rstrip(), after.rstrip()) if part)
else:
    text = '\\n\\n'.join(part for part in (text.rstrip(), block.rstrip()) if part)
path.write_text(text + '\\n', encoding='utf-8')
PY"

echo "[vast-access] testing GPU -> Hetzner SSH"
ssh "${GPU_SSH_HOST}" "ssh -o BatchMode=yes -o ConnectTimeout=10 ${HETZNER_SSH_HOST} 'true'"
echo "[vast-access] ready"
