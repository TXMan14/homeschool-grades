"""Create sample students, courses and grades so you can explore the app.

    python manage.py load_demo_data

Delete the demo students afterwards from the Students page.
"""

import datetime
import random
from decimal import Decimal

from django.core.management.base import BaseCommand

from grades.models import (
    Assignment, AttendanceRecord, Category, Course, Enrollment, HoursLog, Rubric,
    RubricCriterion, SchoolSettings, SchoolYear, Skill, SkillMark, Student, Term, TermGrade,
)


class Command(BaseCommand):
    help = "Load demo data (3 students across elementary, middle and high school)."

    def handle(self, *args, **options):
        rnd = random.Random(42)
        settings = SchoolSettings.load()
        settings.school_name = settings.school_name if settings.school_name != "Our Home School" else "Maple Hill Academy"
        settings.administrator = settings.administrator or "Parent Name"
        settings.track_hours = True
        settings.track_attendance = True
        settings.save()

        years = []
        for start in (2024, 2025):
            year, _ = SchoolYear.objects.get_or_create(
                name=f"{start}-{start + 1}",
                defaults={"start_date": datetime.date(start, 8, 15),
                          "end_date": datetime.date(start + 1, 5, 31),
                          "is_current": start == 2025},
            )
            if not year.terms.exists():
                Term.objects.create(school_year=year, name="Semester 1", order=1,
                                    start_date=year.start_date, end_date=datetime.date(start, 12, 20))
                Term.objects.create(school_year=year, name="Semester 2", order=2,
                                    start_date=datetime.date(start + 1, 1, 6), end_date=year.end_date)
            years.append(year)

        rubric, _ = Rubric.objects.get_or_create(name="Essay (demo)")
        if not rubric.criteria.exists():
            for i, name in enumerate(["Thesis and ideas", "Organization", "Evidence", "Mechanics"], 1):
                RubricCriterion.objects.create(rubric=rubric, name=name, order=i)

        kids = [("Ava", 2, 2), ("Ben", 7, 2), ("Cole", 10, 2)]
        for first, grade_now, _ in kids:
            student, created = Student.objects.get_or_create(
                first_name=first, last_name="Demo",
                defaults={"birth_date": datetime.date(2025 - grade_now - 6, 4, 1),
                          "graduation_year": 2026 + (12 - grade_now)},
            )
            if not created:
                self.stdout.write(f"{student} already exists, skipping.")
                continue
            for offset, year in enumerate(years):
                level = grade_now - (len(years) - 1 - offset)
                Enrollment.objects.create(student=student, school_year=year, grade_level=level)
                terms = list(year.terms.all())
                if level <= 3:
                    self._checklist_course(student, year, terms, rnd)
                    self._letter_course(student, year, terms, "Mathematics", "math", rnd)
                else:
                    hs = level >= 9
                    for name, subject in [("English", "english"), ("Algebra" if hs else "Pre-Algebra", "math"),
                                          ("Biology" if hs else "Life Science", "science"),
                                          ("World History", "social")]:
                        self._weighted_course(student, year, terms, f"{name} {level}" if name == "English" else name,
                                              subject, hs, rnd, rubric)
                    if hs:
                        c = Course.objects.create(student=student, school_year=year, name="Physical Education",
                                                  subject="pe", grading_method=Course.LETTER, on_transcript=True,
                                                  credits=Decimal("0.5"), pass_fail=True)
                        for t in terms:
                            TermGrade.objects.create(course=c, term=t, letter="A")
                # Attendance for the current year.
                if year.is_current:
                    day = year.start_date
                    while day <= min(year.end_date, datetime.date.today()):
                        if day.weekday() < 5:
                            status = rnd.choices(["present", "half", "absent"], [92, 5, 3])[0]
                            AttendanceRecord.objects.create(student=student, date=day, status=status)
                        day += datetime.timedelta(days=1)
            self.stdout.write(self.style.SUCCESS(f"Created {student}"))

    def _checklist_course(self, student, year, terms, rnd):
        c = Course.objects.create(student=student, school_year=year, name="Reading & Phonics",
                                  subject="english", grading_method=Course.CHECKLIST)
        for i, name in enumerate(["Reads CVC words", "Knows sight words list 1", "Retells a story in order",
                                  "Writes a complete sentence", "Uses capital letters and periods"], 1):
            s = Skill.objects.create(course=c, name=name, order=i)
            for j, t in enumerate(terms):
                SkillMark.objects.create(skill=s, term=t, status=rnd.choice("PM") if j else rnd.choice("NP"))
        TermGrade.objects.create(course=c, term=terms[0], comment="Great progress with blending sounds.")

    def _letter_course(self, student, year, terms, name, subject, rnd):
        c = Course.objects.create(student=student, school_year=year, name=name, subject=subject,
                                  grading_method=Course.LETTER)
        for t in terms:
            TermGrade.objects.create(course=c, term=t, letter=rnd.choice("AAB"),
                                     comment="Working hard on math facts.")

    def _weighted_course(self, student, year, terms, name, subject, hs, rnd, rubric):
        c = Course.objects.create(
            student=student, school_year=year, name=name, subject=subject, on_transcript=hs,
            level=Course.HONORS if hs and subject == "english" else Course.REGULAR,
            completed=not year.is_current,
        )
        cats = [Category.objects.create(course=c, name=n, weight=w)
                for n, w in [("Tests", 50), ("Homework", 30), ("Projects", 20)]]
        skill = rnd.uniform(0.78, 0.97)
        for t in terms:
            for k in range(6):
                cat = cats[k % 3]
                possible = Decimal(100 if cat.name != "Homework" else 20)
                earned = (possible * Decimal(str(min(1.0, rnd.gauss(skill, 0.06))))).quantize(Decimal("1"))
                Assignment.objects.create(course=c, category=cat, term=t, title=f"{cat.name} {k + 1}",
                                          date=(t.start_date or year.start_date) + datetime.timedelta(days=7 * k),
                                          points_possible=possible, points_earned=earned)
        for k in range(20):
            HoursLog.objects.create(course=c, date=year.start_date + datetime.timedelta(days=7 * k),
                                    hours=Decimal("7.5"))
        return c
