"""Data model for a single-family home school gradebook.

Grading follows HSLDA's guidance:
* younger students: skills checklists and rubrics, optional letter grades;
* older students: assignment scores rolled into a course grade through
  weighted categories, credits by hours (about 120-180 hours = 1 credit),
  and a 4.0 GPA with optional honors weighting.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse


# --------------------------------------------------------------------------
# School-wide settings
# --------------------------------------------------------------------------


class SchoolSettings(models.Model):
    """Singleton row holding school info and optional features."""

    school_name = models.CharField(max_length=200, default="Our Home School")
    administrator = models.CharField(
        max_length=200, blank=True, help_text="Name that signs transcripts and report cards."
    )
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)

    track_hours = models.BooleanField(
        default=False, help_text="Log instructional hours per course and suggest credits."
    )
    track_attendance = models.BooleanField(default=False, help_text="Record daily attendance.")
    required_school_days = models.PositiveIntegerField(
        default=180, help_text="Used for the attendance summary on report cards."
    )
    hours_per_credit = models.PositiveIntegerField(
        default=150,
        validators=[MinValueValidator(1)],
        help_text="HSLDA suggests 120-180 hours for one high school credit.",
    )
    honors_bonus = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.50"),
        help_text="Grade points added for Honors courses on the weighted GPA.",
    )
    ap_bonus = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("1.00"),
        help_text="Grade points added for AP / Dual enrollment courses on the weighted GPA.",
    )
    show_weighted_gpa = models.BooleanField(
        default=True, help_text="Show the weighted GPA on transcripts alongside the unweighted GPA."
    )

    class Meta:
        verbose_name = "school settings"
        verbose_name_plural = "school settings"

    def __str__(self):
        return self.school_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class GradeScaleEntry(models.Model):
    """One row of the grading scale, e.g. A = 90% and up = 4.0 points."""

    letter = models.CharField(max_length=3, unique=True)
    min_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    grade_points = models.DecimalField(max_digits=3, decimal_places=2)

    class Meta:
        ordering = ["-min_percent"]
        verbose_name_plural = "grade scale"

    def __str__(self):
        return f"{self.letter} ({self.min_percent}%+ = {self.grade_points})"


# --------------------------------------------------------------------------
# Students, years and terms
# --------------------------------------------------------------------------


class Student(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    graduation_year = models.PositiveIntegerField(
        null=True, blank=True, help_text="Expected high school graduation year."
    )
    graduation_date = models.DateField(
        null=True, blank=True, help_text="Actual graduation date (printed on the transcript)."
    )
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-active", "first_name", "last_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self):
        return reverse("student_detail", args=[self.pk])


class SchoolYear(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text="For example 2025-2026.")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date must be after the start date.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            SchoolYear.objects.exclude(pk=self.pk).update(is_current=False)

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first() or cls.objects.first()


class Term(models.Model):
    """A grading period (quarter, semester, ...) within a school year."""

    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=50, help_text="For example Fall, Q1, Semester 1.")
    order = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["school_year", "order", "start_date"]
        unique_together = [("school_year", "name")]

    def __str__(self):
        return f"{self.name} ({self.school_year})"


GRADE_LEVEL_CHOICES = [(-1, "Pre-K"), (0, "Kindergarten")] + [
    (n, f"Grade {n}") for n in range(1, 13)
]


def grade_level_label(level):
    return dict(GRADE_LEVEL_CHOICES).get(level, str(level))


class Enrollment(models.Model):
    """A student's grade level for a given school year."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="enrollments")
    grade_level = models.SmallIntegerField(choices=GRADE_LEVEL_CHOICES)

    class Meta:
        ordering = ["school_year__start_date"]
        unique_together = [("student", "school_year")]

    def __str__(self):
        return f"{self.student} - {self.get_grade_level_display()} ({self.school_year})"

    @property
    def is_high_school(self):
        return self.grade_level >= 9


# --------------------------------------------------------------------------
# Courses and grading
# --------------------------------------------------------------------------


class Course(models.Model):
    WEIGHTED = "weighted"
    LETTER = "letter"
    CHECKLIST = "checklist"
    GRADING_METHODS = [
        (WEIGHTED, "Assignments in weighted categories"),
        (LETTER, "Letter grade per term (entered directly)"),
        (CHECKLIST, "Skills checklist (no letter grade)"),
    ]

    REGULAR = "regular"
    HONORS = "honors"
    AP = "ap"
    LEVELS = [(REGULAR, "Regular"), (HONORS, "Honors"), (AP, "AP / Dual enrollment")]

    SUBJECTS = [
        ("english", "English / Language Arts"),
        ("math", "Mathematics"),
        ("science", "Science"),
        ("social", "History / Social Studies"),
        ("language", "Foreign Language"),
        ("arts", "Fine Arts"),
        ("pe", "Physical Education / Health"),
        ("bible", "Bible / Religion"),
        ("elective", "Elective"),
        ("other", "Other"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="courses")
    school_year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="courses")
    name = models.CharField(max_length=200)
    subject = models.CharField(max_length=20, choices=SUBJECTS, default="other")
    description = models.TextField(blank=True, help_text="Curriculum, texts and activities.")
    grading_method = models.CharField(max_length=20, choices=GRADING_METHODS, default=WEIGHTED)
    level = models.CharField(max_length=10, choices=LEVELS, default=REGULAR)
    on_transcript = models.BooleanField(
        default=False,
        help_text="Counts toward high school credit and GPA (also for courses like "
        "Algebra 1 taken in 8th grade).",
    )
    credits = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.00"),
        help_text="High school credits earned. 1.0 = full year, 0.5 = semester.",
    )
    pass_fail = models.BooleanField(
        default=False, help_text="Shows P/F on the transcript and is left out of the GPA."
    )
    final_grade_override = models.CharField(
        max_length=3, blank=True,
        help_text="Leave blank to calculate the final grade automatically. Use P or F for pass/fail.",
    )
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ["school_year__start_date", "student__first_name", "subject", "name"]

    def __str__(self):
        return f"{self.name} - {self.student.first_name} ({self.school_year})"

    def get_absolute_url(self):
        return reverse("course_detail", args=[self.pk])

    @property
    def is_weighted(self):
        return self.grading_method == self.WEIGHTED

    @property
    def is_letter(self):
        return self.grading_method == self.LETTER

    @property
    def is_checklist(self):
        return self.grading_method == self.CHECKLIST

    @property
    def total_category_weight(self):
        return sum((c.weight for c in self.categories.all()), Decimal("0"))


class Category(models.Model):
    """A weighted assignment category inside a course, e.g. Tests = 50%."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=100)
    weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percent of the course grade.",
    )

    class Meta:
        ordering = ["-weight", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return f"{self.name} ({self.weight}%)"


class Rubric(models.Model):
    """A reusable scoring rubric (for essays, projects, narrations...)."""

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    max_level = models.PositiveSmallIntegerField(
        default=4, validators=[MinValueValidator(2), MaxValueValidator(10)],
        help_text="Highest score per criterion (4 = Beginning, Developing, Proficient, Excellent).",
    )
    level_labels = models.CharField(
        max_length=300, blank=True, default="Beginning, Developing, Proficient, Excellent",
        help_text="Optional comma-separated labels, lowest first.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("rubric_detail", args=[self.pk])

    @property
    def labels(self):
        labels = [label.strip() for label in self.level_labels.split(",") if label.strip()]
        return {
            level: (labels[level - 1] if level - 1 < len(labels) else str(level))
            for level in range(1, self.max_level + 1)
        }

    @property
    def max_points(self):
        return self.max_level * self.criteria.count()


class RubricCriterion(models.Model):
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name="criteria")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="What excellent work looks like.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name_plural = "rubric criteria"

    def __str__(self):
        return self.name


class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="assignments")
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments"
    )
    term = models.ForeignKey(
        Term, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments"
    )
    title = models.CharField(max_length=200)
    date = models.DateField(null=True, blank=True)
    points_possible = models.DecimalField(
        max_digits=7, decimal_places=2, default=Decimal("100"), validators=[MinValueValidator(0)]
    )
    points_earned = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
        help_text="Leave blank until graded. Ungraded work doesn't count.",
    )
    rubric = models.ForeignKey(
        Rubric, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Optional: score this assignment with a rubric.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.category_id and self.course_id and self.category.course_id != self.course_id:
            raise ValidationError("That category belongs to a different course.")

    @property
    def is_graded(self):
        return self.points_earned is not None and self.points_possible > 0

    @property
    def percent(self):
        if not self.is_graded:
            return None
        return self.points_earned / self.points_possible * 100


class RubricScore(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="rubric_scores")
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE)
    level = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = [("assignment", "criterion")]


class TermGrade(models.Model):
    """Per-term letter grade (for letter-graded courses) and report card comment."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="term_grades")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="term_grades")
    letter = models.CharField(
        max_length=3, blank=True,
        help_text="Letter-graded courses: the grade. Weighted courses: optional override.",
    )
    comment = models.TextField(blank=True)

    class Meta:
        unique_together = [("course", "term")]


class Skill(models.Model):
    """A checklist item, e.g. 'Counts to 100' or 'Writes a complete sentence'."""

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=300)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class SkillMark(models.Model):
    NOT_YET = "N"
    PROGRESSING = "P"
    MASTERED = "M"
    STATUSES = [(NOT_YET, "Not yet"), (PROGRESSING, "Progressing"), (MASTERED, "Mastered")]

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="marks")
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="skill_marks")
    status = models.CharField(max_length=1, choices=STATUSES)

    class Meta:
        unique_together = [("skill", "term")]


# --------------------------------------------------------------------------
# Optional: hours and attendance
# --------------------------------------------------------------------------


class HoursLog(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="hours_logs")
    date = models.DateField()
    hours = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name_plural = "hours logs"


class AttendanceRecord(models.Model):
    PRESENT = "present"
    HALF = "half"
    ABSENT = "absent"
    EXCUSED = "excused"
    STATUSES = [
        (PRESENT, "Present"),
        (HALF, "Half day"),
        (ABSENT, "Absent"),
        (EXCUSED, "Excused / sick"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUSES, default=PRESENT)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-date"]
        unique_together = [("student", "date")]

    @property
    def day_value(self):
        return {self.PRESENT: Decimal("1"), self.HALF: Decimal("0.5")}.get(self.status, Decimal("0"))

