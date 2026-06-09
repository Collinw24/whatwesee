#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 HETZNER_SSH_HOST JOB_ID [GPU_SSH_HOST]" >&2
  exit 2
fi

HETZNER_SSH_HOST="$1"
JOB_ID="$2"
GPU_SSH_HOST="${3:-}"
SAFE_ID="$(printf '%s' "${JOB_ID}" | tr -c 'A-Za-z0-9_.-' '_')"
COMMENT="wws-vast-hetzner-${SAFE_ID}"
KEY_NAME="wws_hetzner_${SAFE_ID}"

echo "[vast-access] removing temporary key from ${HETZNER_SSH_HOST}"
ssh "${HETZNER_SSH_HOST}" "set -eu
if [ -f ~/.ssh/authorized_keys ]; then
  tmp=\"\$(mktemp)\"
  grep -Fv '${COMMENT}' ~/.ssh/authorized_keys > \"\${tmp}\" || true
  cat \"\${tmp}\" > ~/.ssh/authorized_keys
  rm -f \"\${tmp}\"
  chmod 600 ~/.ssh/authorized_keys
fi"

if [[ -n "${GPU_SSH_HOST}" ]]; then
  echo "[vast-access] removing temporary key from ${GPU_SSH_HOST}"
  ssh "${GPU_SSH_HOST}" "set -eu
rm -f ~/.ssh/${KEY_NAME} ~/.ssh/${KEY_NAME}.pub
if [ -f ~/.ssh/config ]; then
  python3 - <<'PY'
from pathlib import Path

path = Path.home() / '.ssh' / 'config'
text = path.read_text(encoding='utf-8') if path.exists() else ''
begin = '# BEGIN ${COMMENT}'
end = '# END ${COMMENT}'
if begin in text and end in text:
    before = text.split(begin, 1)[0].rstrip()
    after = text.split(end, 1)[1].lstrip()
    text = '\\n\\n'.join(part for part in (before, after.rstrip()) if part)
    path.write_text((text + '\\n') if text else '', encoding='utf-8')
PY
fi" || true
fi

echo "[vast-access] revoked"
