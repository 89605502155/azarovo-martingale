#!/bin/sh
# Install the commit-msg hook into this clone (run once per clone).
set -e
root="$(git rev-parse --show-toplevel)"
ln -sf "$root/scripts/commit-msg" "$root/.git/hooks/commit-msg"
chmod +x "$root/scripts/commit-msg" "$root/scripts/install_hooks.sh"
echo "installed: $root/.git/hooks/commit-msg"
