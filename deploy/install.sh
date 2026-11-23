#!/usr/bin/env bash
# One-time setup for Home School Grades on a fresh Debian 12/13 LXC.
# Run as root:   bash /opt/homeschool-grades/deploy/install.sh
# Safe to re-run: it keeps your data, settings and secret key.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/TXMan14/homeschool-grades.git}"
APP_DIR="${APP_DIR:-/opt/homeschool-grades}"
DATA_DIR=/var/lib/homeschool-grades
ENV_DIR=/etc/homeschool-grades
BACKUP_DIR=/var/backups/homeschool-grades
APP_USER=hsg

[ "$(id -u)" -eq 0 ] || { echo "Please run as root."; exit 1; }

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip git nginx sqlite3 ca-certificates

echo "==> Getting the code"
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
git config --global --add safe.directory "$APP_DIR"

echo "==> Creating the app user and folders"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$DATA_DIR/static" "$ENV_DIR" "$BACKUP_DIR"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
chmod 750 "$DATA_DIR" "$BACKUP_DIR"

if [ ! -f "$ENV_DIR/env" ]; then
  echo "==> Writing $ENV_DIR/env"
  SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
  IPS=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v ':' | grep -v '^$' | paste -sd, -)
  HOST=$(hostname)
  TZ_NAME=$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || echo America/Chicago)
  sed -e "s|__SECRET__|$SECRET|" \
      -e "s|__HOSTS__|localhost,127.0.0.1,$HOST,$HOST.local${IPS:+,$IPS}|" \
      -e "s|__TZ__|${TZ_NAME:-America/Chicago}|" \
      "$APP_DIR/deploy/env.example" > "$ENV_DIR/env"
  chown root:"$APP_USER" "$ENV_DIR/env"
  chmod 640 "$ENV_DIR/env"
fi

echo "==> Python environment"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "==> Helper command: hsg-manage"
install -m 755 "$APP_DIR/deploy/hsg-manage" /usr/local/bin/hsg-manage

echo "==> Database and static files"
hsg-manage migrate --noinput
hsg-manage collectstatic --noinput -v0

echo "==> Services"
install -m 644 "$APP_DIR/deploy/homeschool-grades.service" /etc/systemd/system/homeschool-grades.service
install -m 644 "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/homeschool-grades
ln -sf /etc/nginx/sites-available/homeschool-grades /etc/nginx/sites-enabled/homeschool-grades
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl daemon-reload
systemctl enable --now homeschool-grades
systemctl restart homeschool-grades
systemctl reload nginx

echo "==> Nightly database backup (kept 30 days in $BACKUP_DIR)"
install -m 755 "$APP_DIR/deploy/backup.sh" /usr/local/bin/hsg-backup
cat > /etc/cron.d/homeschool-grades <<CRON
15 2 * * * root /usr/local/bin/hsg-backup >/dev/null 2>&1
CRON

if ! hsg-manage shell -c "from django.contrib.auth.models import User; import sys; sys.exit(0 if User.objects.exists() else 1)" 2>/dev/null; then
  echo
  echo "==> Create your login (you'll use this to sign in)"
  if [ -t 0 ]; then
    hsg-manage createsuperuser
  else
    echo "Run:  hsg-manage createsuperuser"
  fi
fi

IP=$(hostname -I | awk '{print $1}')
echo
echo "Done! Open http://$IP/ in your browser."
echo "To update later:  bash $APP_DIR/deploy/update.sh"
