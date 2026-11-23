from django import forms
from django.forms import modelformset_factory

from .models import (
    Assignment,
    AttendanceRecord,
    Category,
    Course,
    Enrollment,
    GradeScaleEntry,
    HoursLog,
    Rubric,
    RubricCriterion,
    SchoolSettings,
    SchoolYear,
    Student,
    Term,
)


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(*args, **kwargs)


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            "first_name", "last_name", "birth_date", "gender",
            "graduation_year", "graduation_date", "active", "notes",
        ]
        widgets = {
            "birth_date": DateInput(),
            "graduation_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class SchoolYearForm(forms.ModelForm):
    TERM_PRESETS = [
        ("", "None (I'll add terms myself)"),
        ("year", "One term (full year)"),
        ("semesters", "Two semesters"),
        ("quarters", "Four quarters"),
    ]
    term_preset = forms.ChoiceField(
        choices=TERM_PRESETS, required=False, label="Create grading periods",
        help_text="Only used when creating a new year.",
    )

    class Meta:
        model = SchoolYear
        fields = ["name", "start_date", "end_date", "is_current"]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["term_preset"]


class TermForm(forms.ModelForm):
    class Meta:
        model = Term
        fields = ["name", "order", "start_date", "end_date"]
        widgets = {"start_date": DateInput(), "end_date": DateInput()}


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["school_year", "grade_level"]


class CourseForm(forms.ModelForm):
    copy_from = forms.ModelChoiceField(
        queryset=Course.objects.none(), required=False,
        label="Copy categories and skills from",
        help_text="Optional: reuse the setup of an existing course (for example a sibling's).",
    )

    class Meta:
        model = Course
        fields = [
            "student", "school_year", "name", "subject", "grading_method", "level",
            "on_transcript", "credits", "pass_fail", "final_grade_override",
            "completed", "description",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["copy_from"]
        else:
            self.fields["copy_from"].queryset = Course.objects.select_related(
                "student", "school_year"
            ).order_by("-school_year__start_date", "name")


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "weight"]


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = [
            "title", "category", "term", "date", "points_possible", "points_earned",
            "rubric", "notes",
        ]
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        course = course or self.instance.course
        self.fields["category"].queryset = course.categories.all()
        self.fields["term"].queryset = course.school_year.terms.all()
        if not course.categories.exists():
            self.fields["category"].help_text = "Add categories on the course page to weight grades."


class QuickAssignmentForm(AssignmentForm):
    class Meta(AssignmentForm.Meta):
        fields = ["title", "category", "term", "date", "points_earned", "points_possible"]


class HoursLogForm(forms.ModelForm):
    class Meta:
        model = HoursLog
        fields = ["date", "hours", "note"]
        widgets = {"date": DateInput()}


class RubricForm(forms.ModelForm):
    class Meta:
        model = Rubric
        fields = ["name", "description", "max_level", "level_labels"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class RubricCriterionForm(forms.ModelForm):
    class Meta:
        model = RubricCriterion
        fields = ["name", "description", "order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class SchoolSettingsForm(forms.ModelForm):
    class Meta:
        model = SchoolSettings
        fields = [
            "school_name", "administrator", "address", "phone", "email",
            "track_hours", "track_attendance", "required_school_days", "hours_per_credit",
            "honors_bonus", "ap_bonus", "show_weighted_gpa",
        ]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


GradeScaleFormSet = modelformset_factory(
    GradeScaleEntry, fields=["letter", "min_percent", "grade_points"], extra=2, can_delete=True
)


class AttendanceDateForm(forms.Form):
    date = forms.DateField(widget=DateInput())


class BulkSkillsForm(forms.Form):
    skills = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "One skill per line"}),
        label="Add skills",
    )


ATTENDANCE_CHOICES = AttendanceRecord.STATUSES
