import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings

from . import grading
from .models import (
    Assignment, Category, Course, Enrollment, HoursLog, SchoolSettings, SchoolYear,
    Student, Term, TermGrade,
)

D = Decimal


class GradingTests(TestCase):
    def setUp(self):
        self.year = SchoolYear.objects.create(
            name="2025-2026", start_date=datetime.date(2025, 8, 15),
            end_date=datetime.date(2026, 5, 31), is_current=True)
        self.s1 = Term.objects.create(school_year=self.year, name="S1", order=1)
        self.s2 = Term.objects.create(school_year=self.year, name="S2", order=2)
        self.student = Student.objects.create(first_name="Ann", last_name="Lee")
        Enrollment.objects.create(student=self.student, school_year=self.year, grade_level=10)

    def course(self, **kw):
        defaults = dict(student=self.student, school_year=self.year, name="Algebra",
                        on_transcript=True)
        defaults.update(kw)
        return Course.objects.create(**defaults)

    def test_default_scale(self):
        self.assertEqual(grading.letter_for_percent(D("89.9")), "B")
        self.assertEqual(grading.letter_for_percent(D("90")), "A")
        self.assertEqual(grading.letter_for_percent(D("12")), "F")
        self.assertEqual(grading.points_for_letter("C"), D("2.0"))
        self.assertIsNone(grading.points_for_letter("P"))

    def test_weighted_categories(self):
        c = self.course()
        tests = Category.objects.create(course=c, name="Tests", weight=60)
        hw = Category.objects.create(course=c, name="Homework", weight=40)
        Assignment.objects.create(course=c, category=tests, term=self.s1, title="T1",
                                  points_possible=100, points_earned=80)
        Assignment.objects.create(course=c, category=hw, term=self.s1, title="H1",
                                  points_possible=10, points_earned=10)
        g = grading.course_grade(c)
        # 80% * .6 + 100% * .4 = 88
        self.assertEqual(grading.q(g.percent), D("88.00"))
        self.assertEqual(g.letter, "B")
        self.assertEqual(g.term_letters[self.s1.id], "B")
        self.assertNotIn(self.s2.id, g.term_letters)

    def test_empty_category_is_renormalized(self):
        c = self.course()
        tests = Category.objects.create(course=c, name="Tests", weight=50)
        Category.objects.create(course=c, name="Projects", weight=50)
        Assignment.objects.create(course=c, category=tests, title="T1",
                                  points_possible=50, points_earned=47)
        self.assertEqual(grading.q(grading.course_grade(c).percent), D("94.00"))

    def test_ungraded_ignored_and_override(self):
        c = self.course()
        Assignment.objects.create(course=c, title="A", points_possible=100, points_earned=70)
        Assignment.objects.create(course=c, title="B", points_possible=100)
        self.assertEqual(grading.course_grade(c).letter, "C")
        c.final_grade_override = "B"
        c.save()
        self.assertEqual(grading.course_grade(c).letter, "B")

    def test_letter_course_averages_terms(self):
        c = self.course(grading_method=Course.LETTER)
        TermGrade.objects.create(course=c, term=self.s1, letter="A")
        TermGrade.objects.create(course=c, term=self.s2, letter="B")
        # average 3.5 -> closest letter (tie resolves to the higher grade)
        self.assertIn(grading.course_grade(c).letter, ("A", "B"))
        TermGrade.objects.filter(term=self.s2).update(letter="A")
        self.assertEqual(grading.course_grade(c).letter, "A")

    def test_honors_weighting_and_transcript_gpa(self):
        a = self.course(name="English", level=Course.HONORS)
        Assignment.objects.create(course=a, title="x", points_possible=100, points_earned=95)
        b = self.course(name="History", credits=D("0.5"))
        Assignment.objects.create(course=b, title="x", points_possible=100, points_earned=85)
        pe = self.course(name="PE", pass_fail=True, credits=D("0.5"))
        Assignment.objects.create(course=pe, title="x", points_possible=100, points_earned=95)
        t = grading.build_transcript(self.student)
        # (4*1 + 3*.5) / 1.5 = 3.67 ; weighted (4.5*1 + 3*.5)/1.5 = 4.00
        self.assertEqual(t.gpa, D("3.67"))
        self.assertEqual(t.weighted_gpa, D("4.00"))
        self.assertEqual(t.total_credits, D("2.00"))
        self.assertEqual(t.years[0].rows[2]["letter"], "P")

    def test_failing_course_earns_no_credit(self):
        c = self.course()
        Assignment.objects.create(course=c, title="x", points_possible=100, points_earned=40)
        t = grading.build_transcript(self.student)
        self.assertEqual(t.total_credits, D("0"))
        self.assertEqual(t.gpa, D("0.00"))

    def test_suggested_credits_from_hours(self):
        c = self.course()
        HoursLog.objects.create(course=c, date=datetime.date(2025, 9, 1), hours=D("140"))
        self.assertEqual(grading.suggested_credits(grading.course_hours(c)), D("0.75"))
        HoursLog.objects.create(course=c, date=datetime.date(2025, 9, 2), hours=D("10"))
        self.assertEqual(grading.suggested_credits(grading.course_hours(c)), D("1"))


@override_settings(ALLOWED_HOSTS=["testserver"])
class PageTests(TestCase):
    def setUp(self):
        call_command("load_demo_data", stdout=open("/dev/null", "w"))
        User.objects.create_user("parent", password="pw")

    def test_login_required(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_all_main_pages_render(self):
        self.client.login(username="parent", password="pw")
        urls = ["/", "/students/", "/years/", "/rubrics/", "/attendance/", "/settings/",
                "/courses/new/", "/years/new/"]
        for s in Student.objects.all():
            urls += [f"/students/{s.pk}/", f"/reports/{s.pk}/transcript/"]
            for y in SchoolYear.objects.all():
                urls.append(f"/reports/{s.pk}/{y.pk}/report-card/")
        for c in Course.objects.all():
            urls.append(f"/courses/{c.pk}/")
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_quick_add_assignment(self):
        self.client.login(username="parent", password="pw")
        c = Course.objects.filter(grading_method=Course.WEIGHTED).first()
        n = c.assignments.count()
        r = self.client.post(f"/courses/{c.pk}/assignments/quick/", {
            "title": "Quiz", "category": c.categories.first().pk, "points_earned": "9",
            "points_possible": "10", "date": "2025-10-01",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.assignments.count(), n + 1)

    def test_settings_toggle(self):
        self.client.login(username="parent", password="pw")
        r = self.client.get("/settings/")
        self.assertContains(r, "track_attendance")
        self.assertTrue(SchoolSettings.load().track_attendance)
