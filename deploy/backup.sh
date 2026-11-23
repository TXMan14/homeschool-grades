#!/usr/bin/env bash
# Safe online backup of the SQLite database; keeps 30 days.
set -euo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
DB=/var/lib/homeschool-grades/grades.sqlite3
DEST=/var/backups/homeschool-grades
mkdir -p "$DEST"
[ -f "$DB" ] || exit 0
OUT="$DEST/grades-$(date +%Y%m%d-%H%M%S).sqlite3"
sqlite3 "$DB" ".backup '$OUT'"
gzip "$OUT"
find "$DEST" -name 'grades-*.sqlite3.gz' -mtime +30 -delete
echo "Backup written to $OUT.gz"
