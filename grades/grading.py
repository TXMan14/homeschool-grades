"""Grade calculations: weighted categories, letter grades, GPA, credits."""

from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from .models import AttendanceRecord, Course, GradeScaleEntry, SchoolSettings, TermGrade

TWO = Decimal("0.01")
NON_GPA_LETTERS = {"P", "F*", "I", "W", "IP", ""}


def q(value, places=TWO):
    if value is None:
        return None
    return Decimal(value).quantize(places, rounding=ROUND_HALF_UP)


def grade_scale():
    return list(GradeScaleEntry.objects.order_by("-min_percent"))


def letter_for_percent(percent, scale=None):
    if percent is None:
        return ""
    scale = scale if scale is not None else grade_scale()
    for entry in scale:
        if percent >= entry.min_percent:
            return entry.letter
    return scale[-1].letter if scale else ""


def points_for_letter(letter, scale=None):
    """Grade points for a letter, or None when it doesn't count toward GPA."""
    letter = (letter or "").strip().upper()
    if letter in NON_GPA_LETTERS:
        return None
    scale = scale if scale is not None else grade_scale()
    for entry in scale:
        if entry.letter.upper() == letter:
            return entry.grade_points
    return None


def weighted_percent(assignments, categories):
    """Course percentage from graded assignments and category weights.

    Each category's percent is total earned / total possible. Categories with
    no graded work are skipped and the remaining weights are re-normalized, so
    a grade is meaningful early in the year. Assignments without a category
    (or courses with no categories) are pooled by total points.
    """
    graded = [a for a in assignments if a.is_graded]
    if not graded:
        return None

    by_cat = {}
    for a in graded:
        by_cat.setdefault(a.category_id, [Decimal("0"), Decimal("0")])
        by_cat[a.category_id][0] += a.points_earned
        by_cat[a.category_id][1] += a.points_possible

    weights = {c.id: c.weight for c in categories if c.weight > 0}
    if not weights or set(by_cat) - set(weights) == set(by_cat):
        earned = sum(v[0] for v in by_cat.values())
        possible = sum(v[1] for v in by_cat.values())
        return earned / possible * 100 if possible else None

    total_weight = Decimal("0")
    total = Decimal("0")
    for cat_id, (earned, possible) in by_cat.items():
        if cat_id not in weights or not possible:
            continue
        total += earned / possible * 100 * weights[cat_id]
        total_weight += weights[cat_id]
    return total / total_weight if total_weight else None


@dataclass
class CourseGrade:
    percent: Decimal | None = None
    letter: str = ""
    points: Decimal | None = None
    weighted_points: Decimal | None = None
    term_letters: dict = field(default_factory=dict)  # term_id -> letter
    term_percents: dict = field(default_factory=dict)  # term_id -> percent
    term_comments: dict = field(default_factory=dict)  # term_id -> comment

    @property
    def display(self):
        if self.letter and self.percent is not None:
            return f"{self.letter} ({q(self.percent, Decimal('0.1'))}%)"
        return self.letter or "-"


def level_bonus(course, settings):
    if course.level == Course.HONORS:
        return settings.honors_bonus
    if course.level == Course.AP:
        return settings.ap_bonus
    return Decimal("0")


def course_grade(course, terms=None, scale=None, settings=None):
    """Calculate a course's per-term and final grades."""
    scale = scale if scale is not None else grade_scale()
    settings = settings or SchoolSettings.load()
    terms = terms if terms is not None else list(course.school_year.terms.all())
    result = CourseGrade()

    term_grades = {tg.term_id: tg for tg in course.term_grades.all()}
    for term_id, tg in term_grades.items():
        if tg.comment:
            result.term_comments[term_id] = tg.comment

    if course.is_checklist:
        result.letter = course.final_grade_override.strip()
    elif course.is_weighted:
        assignments = list(course.assignments.all())
        categories = list(course.categories.all())
        for term in terms:
            override = term_grades.get(term.id)
            pct = weighted_percent([a for a in assignments if a.term_id == term.id], categories)
            result.term_percents[term.id] = pct
            if override and override.letter:
                result.term_letters[term.id] = override.letter
            elif pct is not None:
                result.term_letters[term.id] = letter_for_percent(pct, scale)
        result.percent = weighted_percent(assignments, categories)
        result.letter = course.final_grade_override.strip() or letter_for_percent(result.percent, scale)
    else:  # letter grade per term
        pts = []
        for term in terms:
            tg = term_grades.get(term.id)
            if tg and tg.letter:
                result.term_letters[term.id] = tg.letter
                p = points_for_letter(tg.letter, scale)
                if p is not None:
                    pts.append(p)
        if course.final_grade_override.strip():
            result.letter = course.final_grade_override.strip()
        elif pts:
            avg = sum(pts) / len(pts)
            # Map the average grade points back to the closest letter.
            result.letter = min(scale, key=lambda e: abs(e.grade_points - avg)).letter if scale else ""

    if course.pass_fail:
        if result.letter and result.letter.upper() not in ("P", "F"):
            p = points_for_letter(result.letter, scale)
            result.letter = "P" if (p or 0) > 0 else "F"
        result.points = None
    else:
        result.points = points_for_letter(result.letter, scale)
    if result.points is not None:
        bonus = level_bonus(course, settings) if result.points > 0 else Decimal("0")
        result.weighted_points = result.points + bonus
    return result


def course_hours(course):
    total = course.hours_logs.aggregate(total=Sum("hours"))["total"]
    return total or Decimal("0")


def suggested_credits(hours, settings=None):
    """Hours -> credits, rounded down to the nearest quarter credit."""
    settings = settings or SchoolSettings.load()
    if not hours:
        return Decimal("0")
    quarters = int(Decimal(hours) / settings.hours_per_credit * 4)
    return Decimal(quarters) / 4


@dataclass
class TranscriptYear:
    school_year: object
    grade_level: str
    rows: list
    credits: Decimal
    gpa: Decimal | None
    weighted_gpa: Decimal | None


@dataclass
class Transcript:
    student: object
    years: list
    total_credits: Decimal
    gpa: Decimal | None
    weighted_gpa: Decimal | None
    credits_by_subject: OrderedDict


def gpa(rows):
    """Credit-weighted GPA over rows with numeric points."""
    counted = [r for r in rows if r["points"] is not None and r["credits"] > 0]
    total_credits = sum((r["credits"] for r in counted), Decimal("0"))
    if not total_credits:
        return None, None
    unweighted = sum((r["points"] * r["credits"] for r in counted), Decimal("0")) / total_credits
    weighted = sum((r["weighted_points"] * r["credits"] for r in counted), Decimal("0")) / total_credits
    return q(unweighted), q(weighted)


def earned_credits(row):
    """Failing grades don't earn credit."""
    letter = (row["letter"] or "").upper()
    if letter.startswith("F") or not letter:
        return Decimal("0")
    return row["credits"]


def build_transcript(student):
    settings = SchoolSettings.load()
    scale = grade_scale()
    enrollments = {e.school_year_id: e for e in student.enrollments.all()}
    courses = (
        student.courses.filter(on_transcript=True)
        .select_related("school_year")
        .prefetch_related("assignments", "categories", "term_grades", "school_year__terms")
        .order_by("school_year__start_date", "subject", "name")
    )

    years = OrderedDict()
    for course in courses:
        years.setdefault(course.school_year, []).append(course)

    all_rows = []
    transcript_years = []
    by_subject = OrderedDict((label, Decimal("0")) for _, label in Course.SUBJECTS)
    for school_year, year_courses in years.items():
        rows = []
        for course in year_courses:
            grade = course_grade(course, list(school_year.terms.all()), scale, settings)
            row = {
                "course": course,
                "letter": grade.letter,
                "percent": grade.percent,
                "points": grade.points,
                "weighted_points": grade.weighted_points,
                "credits": course.credits,
            }
            row["earned"] = earned_credits(row)
            rows.append(row)
            by_subject[course.get_subject_display()] += row["earned"]
        enrollment = enrollments.get(school_year.id)
        year_gpa, year_wgpa = gpa(rows)
        transcript_years.append(
            TranscriptYear(
                school_year=school_year,
                grade_level=enrollment.get_grade_level_display() if enrollment else "",
                rows=rows,
                credits=sum((r["earned"] for r in rows), Decimal("0")),
                gpa=year_gpa,
                weighted_gpa=year_wgpa,
            )
        )
        all_rows.extend(rows)

    total_gpa, total_wgpa = gpa(all_rows)
    return Transcript(
        student=student,
        years=transcript_years,
        total_credits=sum((r["earned"] for r in all_rows), Decimal("0")),
        gpa=total_gpa,
        weighted_gpa=total_wgpa,
        credits_by_subject=OrderedDict((k, v) for k, v in by_subject.items() if v),
    )


def attendance_summary(student, start_date, end_date):
    records = student.attendance.filter(date__gte=start_date, date__lte=end_date)
    summary = {code: 0 for code, _ in AttendanceRecord.STATUSES}
    days = Decimal("0")
    for r in records:
        summary[r.status] += 1
        days += r.day_value
    summary["days_attended"] = days
    summary["recorded"] = records.count()
    return summary


def term_grade_obj(course, term):
    obj, _ = TermGrade.objects.get_or_create(course=course, term=term)
    return obj


def scale_ranges(scale=None):
    """[(letter, min, max, points)] for printing a grading key, e.g. B = 80-89."""
    scale = scale if scale is not None else grade_scale()
    rows, upper = [], None
    for entry in scale:
        if upper is None:
            top = Decimal("100")
        else:
            top = upper - (1 if upper == upper.to_integral_value() else Decimal("0.01"))
        rows.append({"letter": entry.letter, "min": entry.min_percent, "max": top,
                     "points": entry.grade_points})
        upper = entry.min_percent
    return rows
