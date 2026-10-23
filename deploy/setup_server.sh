#!/usr/bin/env bash
# One-time EC2 bootstrap (Ubuntu). Safe to re-run: existing DB password and .env are kept.
# Usage on the server:  sudo bash setup_server.sh https://github.com/<owner>/<repo>.git
set -euo pipefail

REPO_URL=${1:?usage: setup_server.sh <git-repo-url>}
APP_DIR=/opt/hotel-api
APP_USER=ubuntu
DB_NAME=hotel_db
DB_USER=hotel_user

echo "==> Installing packages"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
  postgresql postgresql-contrib nginx python3-venv python3-pip git curl

systemctl enable --now postgresql nginx

echo "==> Getting the code"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Creating .env with generated secrets (only if missing)"
if [ ! -f "$APP_DIR/.env" ]; then
  DB_PASSWORD=$(openssl rand -hex 24)
  SECRET_KEY=$(openssl rand -hex 32)
  cat > "$APP_DIR/.env" <<EOF
DATABASE_URL=postgresql+psycopg://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME
SECRET_KEY=$SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=60
TIMEZONE=Asia/Tashkent
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"

  echo "==> Creating database role and database"
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DB_USER') THEN
    CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD';
  ELSE
    ALTER ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD';
  END IF;
END \$\$;
SQL
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 \
    || sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi
# Extension needed by the no-overlap exclusion constraint
sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS btree_gist"

echo "==> Python virtualenv"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> systemd service"
cp "$APP_DIR/deploy/hotel-api.service" /etc/systemd/system/hotel-api.service
systemctl daemon-reload
systemctl enable hotel-api

echo "==> Nginx"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/hotel-api
ln -sf /etc/nginx/sites-available/hotel-api /etc/nginx/sites-enabled/hotel-api
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> First deploy (migrations + start + health check)"
sudo -u "$APP_USER" bash "$APP_DIR/deploy/deploy.sh" origin/main
