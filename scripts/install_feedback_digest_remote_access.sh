#!/bin/bash
# Install a least-privilege, forced-command SSH principal for the Mac worker.
set -euo pipefail

if [[ $# -ne 1 || ! -f "$1" ]]; then
  echo "usage: $0 /path/to/dedicated-ed25519.pub" >&2
  exit 64
fi
PUBLIC_KEY="$(tr -d '\r\n' < "$1")"
if [[ ! "$PUBLIC_KEY" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]]; then
  echo "only a dedicated ssh-ed25519 public key is accepted" >&2
  exit 64
fi

SOURCE="$(cd "$(dirname "$0")" && pwd)/feedback_digest_forced_command.sh"
install -o root -g root -m 0755 "$SOURCE" /usr/local/sbin/ai-lab-feedback-digest-command

if ! id feedback-digest >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /home/feedback-digest --shell /bin/sh feedback-digest
fi
install -d -o feedback-digest -g feedback-digest -m 0700 /home/feedback-digest/.ssh
printf 'restrict,command="sudo -n /usr/local/sbin/ai-lab-feedback-digest-command" %s\n' "$PUBLIC_KEY" \
  > /home/feedback-digest/.ssh/authorized_keys
chown feedback-digest:feedback-digest /home/feedback-digest/.ssh/authorized_keys
chmod 0600 /home/feedback-digest/.ssh/authorized_keys

cat > /etc/sudoers.d/ai-lab-feedback-digest <<'EOF'
Defaults:feedback-digest env_keep += "SSH_ORIGINAL_COMMAND"
feedback-digest ALL=(root) NOPASSWD: /usr/local/sbin/ai-lab-feedback-digest-command
EOF
chmod 0440 /etc/sudoers.d/ai-lab-feedback-digest
visudo -cf /etc/sudoers.d/ai-lab-feedback-digest

echo "installed restricted feedback-digest SSH principal"
