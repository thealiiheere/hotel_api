#!/usr/bin/env bash
# Runs ON the EC2 server (called by GitHub Actions over SSH after tests pass).
# Usage: bash /opt/hotel-api/deploy/deploy.sh [git-sha]
#
# Everything is inside main() so bash reads the whole script before running it:
# "git reset" below rewrites this very file, which is safe only after it has been parsed.
set -euo pipefail

main() {
  local app_dir=/opt/hotel-api
  local service=hotel-api
  local target=${1:-origin/main}

  cd "$app_dir"

  echo "==> Fetching code ($target)"
  git fetch --quiet origin main
  git reset --hard "$target"

  echo "==> Installing dependencies"
  .venv/bin/pip install --quiet --disable-pip-version-check -r requirements.txt

  # Settings (DATABASE_URL, SECRET_KEY) are read from $app_dir/.env
  echo "==> Running database migrations"
  .venv/bin/alembic upgrade head

  echo "==> Restarting service"
  sudo systemctl restart "$service"

  echo "==> Health check"
  for _ in $(seq 1 15); do
    if curl -fsS http://127.0.0.1:8000/health; then
      echo
      echo "==> Deployed $(git rev-parse --short HEAD)"
      return 0
    fi
    sleep 2
  done

  echo "Health check failed, recent logs:"
  sudo journalctl -u "$service" -n 50 --no-pager
  return 1
}

main "$@"
