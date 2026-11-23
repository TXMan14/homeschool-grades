# Home School Grades

A small, self-hosted gradebook for one home school family. It follows
[HSLDA's grading guidance](https://hslda.org/teaching-my-kids/grading):

- **Younger students:** skills checklists (Not yet / Progressing / Mastered),
  rubrics, and optional letter grades.
- **Older students:** assignment scores roll up into a course grade through
  **weighted categories** (for example Tests 50%, Homework 30%, Projects 20%).
- **High school:** credits (HSLDA suggests 120-180 hours per credit, 150 by
  default), a **4.0 GPA**, and optional **Honors (+0.5)** and **AP / Dual
  enrollment (+1.0)** weighting.
- **Printable report cards** (per grading period or full year) and a
  **cumulative high school transcript**. Use the browser's *Print → Save as PDF*.
- **Optional** instructional-hours logging (with suggested credits) and
  daily attendance. Both are off until you turn them on in **Settings**.

It's a single-user app: one parent login, and no student accounts.

Stack: Python 3.11+ · Django 5.2 LTS · SQLite · Gunicorn · Nginx.
No JavaScript build step, no external services.

---

## Install on a Proxmox LXC (Debian 12 or 13)

1. In Proxmox, create a Debian 12 or 13 container. 1 CPU, 512 MB RAM and a 4 GB
   disk are plenty. Unprivileged is fine. Give it a static IP or a DHCP reservation.
2. Open the container console (`pct enter <id>` on the Proxmox host, or the
   web console) and run, as root:

   ```bash
   apt-get update && apt-get install -y git
   git clone https://github.com/TXMan14/homeschool-grades.git /opt/homeschool-grades
   bash /opt/homeschool-grades/deploy/install.sh
   ```

   The script installs packages, creates the `hsg` service user, writes
   `/etc/homeschool-grades/env` with a random secret key, sets up Gunicorn +
   Nginx, schedules a nightly backup, and asks you to create your login.
3. Browse to `http://<container-ip>/` and sign in.

### First-time setup in the app

1. **Settings:** set your school name and administrator name. Choose whether to
   track hours and attendance, and adjust the grading scale if you want
   (add rows like B+ = 87% = 3.3).
2. **School years → Add school year:** choose semesters or quarters and the
   grading periods are created for you.
3. **Students → Add student**, then **Set grade level** for the year.
4. **Add course** for each student. For grade 9 and up, "On transcript" is
   ticked automatically. Weighted courses start with three default categories,
   which you can edit. *Copy categories and skills from* reuses a sibling's setup.

Want to look around first? `hsg-manage load_demo_data` creates three sample
students. Delete them from the Students page afterwards.

### Reaching it by name

The installer allows `localhost`, the container's hostname and its IPs. To use
another name (for example `grades.home.lan`), add it to `DJANGO_ALLOWED_HOSTS`
in `/etc/homeschool-grades/env`, then run `systemctl restart homeschool-grades`.
If you put it behind HTTPS (Nginx Proxy Manager, Caddy, Traefik...), also set
`DJANGO_CSRF_TRUSTED_ORIGINS=https://grades.example.com` and
`DJANGO_SECURE_COOKIES=true`.

---

## Updating

Push changes to GitHub, then inside the container run:

```bash
bash /opt/homeschool-grades/deploy/update.sh
```

It backs up the database, pulls, installs requirements, migrates, collects
static files and restarts the service.

## Backups

- The database is one file: `/var/lib/homeschool-grades/grades.sqlite3`.
- `hsg-backup` runs nightly at 2:15 and writes compressed copies to
  `/var/backups/homeschool-grades/`, keeping 30 days. Run it by hand anytime.
- Proxmox container backups (vzdump) capture everything as well.
- To restore: `systemctl stop homeschool-grades`, then `gunzip -c <backup> > /var/lib/homeschool-grades/grades.sqlite3`,
  `chown hsg:hsg` the file, and start the service again.

## Handy commands (inside the container)

| Task | Command |
| --- | --- |
| Change your password | `hsg-manage changepassword <username>` (or Settings → Change your password) |
| Create another login | `hsg-manage createsuperuser` |
| View logs | `journalctl -u homeschool-grades -f` |
| Restart | `systemctl restart homeschool-grades` |

## How grades are calculated

- **Weighted courses:** each category's percent is total points earned / total
  possible. The course percent is the weighted average of those categories.
  Categories with no graded work yet are skipped, and the other weights are
  scaled up, so early-year grades are meaningful. Ungraded (blank) assignments
  don't count. Period grades use only that period's assignments. The final
  grade uses the whole year. You can override any period or final grade.
- **Letter-graded courses:** you enter a letter each period. The final grade is
  the letter closest to the average grade points, unless you override it.
- **Checklist courses:** skills are marked each period. There's no letter grade
  unless you set a final grade override.
- **Rubrics:** attach a rubric to an assignment and score each criterion. The
  total becomes the assignment's points.
- **GPA:** credit-weighted average of grade points for transcript courses.
  Pass/fail courses and grades like P, I, W, IP are left out. The weighted GPA
  adds the Honors / AP bonus to passing grades. Failing grades earn no credit.
- **Credits from hours:** hours logged ÷ hours per credit, rounded down to the
  nearest quarter credit. Press *Use this* on the course page to apply it.

## Local development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py load_demo_data   # optional
python manage.py runserver
python manage.py test grades
```
