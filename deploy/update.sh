#!/usr/bin/env bash
# Pull the latest code from GitHub and restart. Run as root inside the LXC.
set -euo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
APP_DIR="${APP_DIR:-/opt/homeschool-grades}"
[ "$(id -u)" -eq 0 ] || { echo "Please run as root."; exit 1; }

echo "==> Backing up the database first"
/usr/local/bin/hsg-backup || true

cd "$APP_DIR"
git pull --ff-only
# Static files live where Nginx can read them (fixes unstyled pages on early installs).
mkdir -p /var/www/homeschool-grades/static
chown -R hsg:hsg /var/www/homeschool-grades
chmod 755 /var/www/homeschool-grades /var/www/homeschool-grades/static
sed -i 's|^HSG_STATIC_ROOT=.*|HSG_STATIC_ROOT=/var/www/homeschool-grades/static|' /etc/homeschool-grades/env
"$APP_DIR/.venv/bin/pip" install -q -r requirements.txt
install -m 755 deploy/hsg-manage /usr/local/bin/hsg-manage
# pct enter shells leave /usr/local/bin off PATH, so link into /usr/bin too.
ln -sf /usr/local/bin/hsg-manage /usr/bin/hsg-manage
install -m 755 deploy/backup.sh /usr/local/bin/hsg-backup
ln -sf /usr/local/bin/hsg-backup /usr/bin/hsg-backup
install -m 644 deploy/homeschool-grades.service /etc/systemd/system/homeschool-grades.service
install -m 644 deploy/nginx.conf /etc/nginx/sites-available/homeschool-grades
systemctl daemon-reload
hsg-manage migrate --noinput
hsg-manage collectstatic --noinput -v0
systemctl restart homeschool-grades
nginx -t && systemctl reload nginx
echo "Updated to $(git log -1 --format='%h %s')"
