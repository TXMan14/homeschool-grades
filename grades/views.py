import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import grading
from .forms import (
    AssignmentForm,
    AttendanceDateForm,
    BulkSkillsForm,
    CategoryForm,
    CourseForm,
    EnrollmentForm,
    GradeScaleFormSet,
    HoursLogForm,
    QuickAssignmentForm,
    RubricCriterionForm,
    RubricForm,
    SchoolSettingsForm,
    SchoolYearForm,
    StudentForm,
    TermForm,
)
from .models import (
    Assignment,
    AttendanceRecord,
    Category,
    Course,
    Enrollment,
    HoursLog,
    Rubric,
    RubricCriterion,
    RubricScore,
    SchoolSettings,
    SchoolYear,
    Skill,
    SkillMark,
    Student,
    Term,
    TermGrade,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def edit_object(request, form_class, instance=None, *, title, success_url, initial=None,
                form_kwargs=None, on_save=None, cancel_url=None):
    """Generic create/update view rendering grades/form.html."""
    form_kwargs = form_kwargs or {}
    if request.method == "POST":
        form = form_class(request.POST, instance=instance, **form_kwargs)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=on_save is None)
                if on_save:
                    on_save(obj, form)
            messages.success(request, "Saved.")
            return redirect(success_url(obj) if callable(success_url) else success_url)
    else:
        form = form_class(instance=instance, initial=initial, **form_kwargs)
    return render(request, "grades/form.html", {
        "form": form, "title": title, "cancel_url": cancel_url or request.GET.get("next") or "/",
    })


def delete_object(request, obj, *, success_url, description=None):
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Deleted.")
        return redirect(success_url)
    return render(request, "grades/confirm_delete.html", {
        "object": obj, "description": description or str(obj),
        "cancel_url": request.GET.get("next") or success_url,
    })


def course_summary(course, settings, scale):
    terms = list(course.school_year.terms.all())
    grade = grading.course_grade(course, terms, scale, settings)
    return {"course": course, "grade": grade, "terms": terms}


# --------------------------------------------------------------------------
# Dashboard and students
# --------------------------------------------------------------------------


def dashboard(request):
    settings = SchoolSettings.load()
    scale = grading.grade_scale()
    year = SchoolYear.current()
    students = []
    for student in Student.objects.filter(active=True):
        enrollment = student.enrollments.filter(school_year=year).first() if year else None
        courses = []
        if year:
            for course in student.courses.filter(school_year=year).prefetch_related(
                "assignments", "categories", "term_grades"
            ):
                courses.append(course_summary(course, settings, scale))
        students.append({"student": student, "enrollment": enrollment, "courses": courses})
    return render(request, "grades/dashboard.html", {
        "year": year, "students": students, "needs_setup": not SchoolYear.objects.exists(),
    })


def student_list(request):
    return render(request, "grades/student_list.html", {"students": Student.objects.all()})


def student_create(request):
    return edit_object(request, StudentForm, title="Add student",
                       success_url=lambda s: s.get_absolute_url())


def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    return edit_object(request, StudentForm, student, title=f"Edit {student}",
                       success_url=student.get_absolute_url(),
                       cancel_url=student.get_absolute_url())


def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    return delete_object(request, student, success_url=reverse("student_list"),
                         description=f"{student} and ALL of their courses, grades and attendance")


def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    settings = SchoolSettings.load()
    scale = grading.grade_scale()
    enrollments = {e.school_year_id: e for e in student.enrollments.all()}
    years = []
    year_ids = set(enrollments) | set(student.courses.values_list("school_year_id", flat=True))
    for year in SchoolYear.objects.filter(id__in=year_ids):
        courses = [
            course_summary(c, settings, scale)
            for c in student.courses.filter(school_year=year).prefetch_related(
                "assignments", "categories", "term_grades")
        ]
        attendance = None
        if settings.track_attendance:
            attendance = grading.attendance_summary(student, year.start_date, year.end_date)
        years.append({
            "year": year, "enrollment": enrollments.get(year.id), "courses": courses,
            "attendance": attendance,
        })
    has_transcript = student.courses.filter(on_transcript=True).exists()
    return render(request, "grades/student_detail.html", {
        "student": student, "years": years, "has_transcript": has_transcript,
    })


def enrollment_create(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)

    def save(obj, form):
        obj.student = student
        obj.save()

    current = SchoolYear.current()
    return edit_object(
        request, EnrollmentForm, Enrollment(student=student),
        title=f"Set grade level for {student}",
        success_url=student.get_absolute_url(), on_save=save,
        initial={"school_year": current.pk if current else None},
        cancel_url=student.get_absolute_url(),
    )


def enrollment_edit(request, pk):
    enrollment = get_object_or_404(Enrollment, pk=pk)
    return edit_object(request, EnrollmentForm, enrollment, title=f"Edit grade level",
                       success_url=enrollment.student.get_absolute_url(),
                       cancel_url=enrollment.student.get_absolute_url())


# --------------------------------------------------------------------------
# School years and terms
# --------------------------------------------------------------------------


def year_list(request):
    return render(request, "grades/year_list.html", {
        "years": SchoolYear.objects.prefetch_related("terms"),
    })


def _split_dates(start, end, parts):
    span = (end - start).days + 1
    bounds = []
    for i in range(parts):
        s = start + datetime.timedelta(days=span * i // parts)
        e = start + datetime.timedelta(days=span * (i + 1) // parts - 1)
        bounds.append((s, e))
    return bounds


def year_create(request):
    def save(year, form):
        year.save()
        preset = form.cleaned_data.get("term_preset")
        names = {
            "year": ["Full year"],
            "semesters": ["Semester 1", "Semester 2"],
            "quarters": ["Quarter 1", "Quarter 2", "Quarter 3", "Quarter 4"],
        }.get(preset, [])
        for i, (name, (s, e)) in enumerate(
            zip(names, _split_dates(year.start_date, year.end_date, len(names) or 1)), start=1
        ):
            Term.objects.create(school_year=year, name=name, order=i, start_date=s, end_date=e)

    today = timezone.localdate()
    start_year = today.year if today.month >= 7 else today.year - 1
    return edit_object(
        request, SchoolYearForm, title="Add school year", success_url=reverse("year_list"),
        on_save=save, cancel_url=reverse("year_list"),
        initial={
            "name": f"{start_year}-{start_year + 1}",
            "start_date": datetime.date(start_year, 8, 15),
            "end_date": datetime.date(start_year + 1, 5, 31),
            "is_current": not SchoolYear.objects.exists(),
            "term_preset": "semesters",
        },
    )


def year_edit(request, pk):
    year = get_object_or_404(SchoolYear, pk=pk)
    return edit_object(request, SchoolYearForm, year, title=f"Edit {year}",
                       success_url=reverse("year_list"), cancel_url=reverse("year_list"))


def year_delete(request, pk):
    year = get_object_or_404(SchoolYear, pk=pk)
    return delete_object(request, year, success_url=reverse("year_list"),
                         description=f"{year} and ALL courses and grades in it")


def term_create(request, year_pk):
    year = get_object_or_404(SchoolYear, pk=year_pk)

    def save(term, form):
        term.school_year = year
        term.save()

    return edit_object(request, TermForm, Term(school_year=year),
                       title=f"Add grading period to {year}", on_save=save,
                       success_url=reverse("year_list"), cancel_url=reverse("year_list"),
                       initial={"order": year.terms.count() + 1})


def term_edit(request, pk):
    term = get_object_or_404(Term, pk=pk)
    return edit_object(request, TermForm, term, title=f"Edit {term}",
                       success_url=reverse("year_list"), cancel_url=reverse("year_list"))


def term_delete(request, pk):
    term = get_object_or_404(Term, pk=pk)
    return delete_object(request, term, success_url=reverse("year_list"),
                         description=f"{term} (assignments stay, but lose their term)")


# --------------------------------------------------------------------------
# Courses
# --------------------------------------------------------------------------


def _copy_course_setup(source, target):
    for cat in source.categories.all():
        Category.objects.create(course=target, name=cat.name, weight=cat.weight)
    for skill in source.skills.all():
        Skill.objects.create(course=target, name=skill.name, order=skill.order)


DEFAULT_CATEGORIES = [("Tests & quizzes", 40), ("Daily work", 30), ("Projects & papers", 30)]


def course_create(request):
    def save(course, form):
        course.save()
        source = form.cleaned_data.get("copy_from")
        if source:
            _copy_course_setup(source, course)
        elif course.is_weighted:
            for name, weight in DEFAULT_CATEGORIES:
                Category.objects.create(course=course, name=name, weight=weight)

    initial = {}
    student_id = request.GET.get("student")
    if student_id:
        initial["student"] = student_id
        student = Student.objects.filter(pk=student_id).first()
        year = SchoolYear.current()
        if student and year:
            enrollment = student.enrollments.filter(school_year=year).first()
            if enrollment:
                if enrollment.grade_level >= 9:
                    initial["on_transcript"] = True
                elif enrollment.grade_level <= 3:
                    initial["grading_method"] = Course.CHECKLIST
    year = SchoolYear.current()
    if year:
        initial["school_year"] = year.pk
    return edit_object(request, CourseForm, title="Add course", on_save=save, initial=initial,
                       success_url=lambda c: c.get_absolute_url())


def course_edit(request, pk):
    course = get_object_or_404(Course, pk=pk)
    return edit_object(request, CourseForm, course, title=f"Edit {course.name}",
                       success_url=course.get_absolute_url(),
                       cancel_url=course.get_absolute_url())


def course_delete(request, pk):
    course = get_object_or_404(Course, pk=pk)
    return delete_object(request, course, success_url=course.student.get_absolute_url(),
                         description=f"{course} and all of its assignments and grades")


def course_detail(request, pk):
    course = get_object_or_404(
        Course.objects.select_related("student", "school_year"), pk=pk
    )
    settings = SchoolSettings.load()
    scale = grading.grade_scale()
    terms = list(course.school_year.terms.all())
    grade = grading.course_grade(course, terms, scale, settings)
    term_grades = {tg.term_id: tg for tg in course.term_grades.all()}

    context = {
        "course": course, "grade": grade, "terms": terms,
        "term_rows": [
            {"term": t, "letter": grade.term_letters.get(t.id, ""),
             "percent": grade.term_percents.get(t.id),
             "record": term_grades.get(t.id)}
            for t in terms
        ],
    }

    if course.is_weighted:
        today = timezone.localdate()
        current_term = next(
            (t for t in terms if t.start_date and t.end_date and t.start_date <= today <= t.end_date),
            terms[0] if terms else None,
        )
        context["quick_form"] = QuickAssignmentForm(course=course, initial={
            "date": today, "term": current_term, "points_possible": 100,
        })
        context["assignments"] = course.assignments.select_related("category", "term", "rubric")
        context["categories"] = course.categories.all()
        context["category_form"] = CategoryForm()
    if course.is_checklist:
        marks = {(m.skill_id, m.term_id): m.status
                 for m in SkillMark.objects.filter(skill__course=course)}
        context["skill_rows"] = [
            {"skill": s, "cells": [(t, marks.get((s.id, t.id), "")) for t in terms]}
            for s in course.skills.all()
        ]
        context["skill_statuses"] = SkillMark.STATUSES
        context["bulk_skills_form"] = BulkSkillsForm()
    if settings.track_hours:
        hours = grading.course_hours(course)
        context.update({
            "hours_total": hours,
            "hours_suggested_credits": grading.suggested_credits(hours, settings),
            "hours_logs": course.hours_logs.all()[:20],
            "hours_form": HoursLogForm(initial={"date": timezone.localdate(), "hours": 1}),
        })
    return render(request, "grades/course_detail.html", context)


@require_POST
def category_add(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    form = CategoryForm(request.POST)
    if form.is_valid():
        cat = form.save(commit=False)
        cat.course = course
        cat.save()
        messages.success(request, f"Added category {cat.name}.")
    else:
        messages.error(request, "Category needs a name and a weight between 0 and 100.")
    return redirect(course.get_absolute_url())


def category_edit(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    return edit_object(request, CategoryForm, cat, title=f"Edit category",
                       success_url=cat.course.get_absolute_url(),
                       cancel_url=cat.course.get_absolute_url())


def category_delete(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    return delete_object(request, cat, success_url=cat.course.get_absolute_url(),
                         description=f"category {cat.name} (its assignments become uncategorized)")


@require_POST
def term_grades_save(request, course_pk):
    """Save letter grades and comments for each term of a course."""
    course = get_object_or_404(Course, pk=course_pk)
    for term in course.school_year.terms.all():
        letter = request.POST.get(f"letter_{term.id}", "").strip().upper()[:3]
        comment = request.POST.get(f"comment_{term.id}", "").strip()
        tg, _ = TermGrade.objects.get_or_create(course=course, term=term)
        tg.letter = letter
        tg.comment = comment
        tg.save()
    messages.success(request, "Term grades and comments saved.")
    return redirect(course.get_absolute_url())


# --------------------------------------------------------------------------
# Assignments and rubric scoring
# --------------------------------------------------------------------------


@require_POST
def assignment_quick_add(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    form = QuickAssignmentForm(request.POST, course=course)
    if form.is_valid():
        a = form.save(commit=False)
        a.course = course
        a.save()
        messages.success(request, f"Added {a.title}.")
    else:
        for field, errors in form.errors.items():
            messages.error(request, f"{field}: {' '.join(errors)}")
    return redirect(course.get_absolute_url())


def assignment_create(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)

    def save(a, form):
        a.course = course
        a.save()

    def after(a):
        if a.rubric_id:
            return reverse("assignment_rubric", args=[a.pk])
        return course.get_absolute_url()

    return edit_object(request, AssignmentForm, Assignment(course=course),
                       title=f"Add assignment to {course.name}", on_save=save,
                       form_kwargs={"course": course}, success_url=after,
                       initial={"date": timezone.localdate()},
                       cancel_url=course.get_absolute_url())


def assignment_edit(request, pk):
    a = get_object_or_404(Assignment, pk=pk)
    return edit_object(request, AssignmentForm, a, title=f"Edit {a.title}",
                       form_kwargs={"course": a.course},
                       success_url=a.course.get_absolute_url(),
                       cancel_url=a.course.get_absolute_url())


def assignment_delete(request, pk):
    a = get_object_or_404(Assignment, pk=pk)
    return delete_object(request, a, success_url=a.course.get_absolute_url())


def assignment_rubric(request, pk):
    a = get_object_or_404(Assignment.objects.select_related("rubric", "course"), pk=pk)
    if not a.rubric:
        raise Http404("This assignment has no rubric.")
    rubric = a.rubric
    criteria = list(rubric.criteria.all())
    scores = {s.criterion_id: s for s in a.rubric_scores.all()}
    if request.method == "POST":
        total = Decimal("0")
        all_scored = True
        for c in criteria:
            raw = request.POST.get(f"level_{c.id}", "")
            comment = request.POST.get(f"comment_{c.id}", "").strip()[:300]
            if raw.isdigit() and 1 <= int(raw) <= rubric.max_level:
                RubricScore.objects.update_or_create(
                    assignment=a, criterion=c,
                    defaults={"level": int(raw), "comment": comment},
                )
                total += int(raw)
            else:
                RubricScore.objects.filter(assignment=a, criterion=c).delete()
                all_scored = False
        a.points_possible = Decimal(rubric.max_level * len(criteria))
        a.points_earned = total if all_scored and criteria else None
        a.save()
        messages.success(request, "Rubric scores saved." if all_scored
                         else "Saved. The grade counts once every criterion is scored.")
        return redirect(a.course.get_absolute_url())
    rows = [{"criterion": c, "score": scores.get(c.id)} for c in criteria]
    return render(request, "grades/assignment_rubric.html", {
        "assignment": a, "rubric": rubric, "rows": rows,
        "levels": list(rubric.labels.items()),
    })


# --------------------------------------------------------------------------
# Checklists (skills)
# --------------------------------------------------------------------------


@require_POST
def skills_add(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    form = BulkSkillsForm(request.POST)
    if form.is_valid():
        start = course.skills.count()
        lines = [l.strip() for l in form.cleaned_data["skills"].splitlines() if l.strip()]
        for i, line in enumerate(lines, start=1):
            Skill.objects.create(course=course, name=line[:300], order=start + i)
        messages.success(request, f"Added {len(lines)} skill(s).")
    return redirect(course.get_absolute_url())


@require_POST
def skills_marks_save(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    valid = {code for code, _ in SkillMark.STATUSES}
    terms = list(course.school_year.terms.all())
    for skill in course.skills.all():
        for term in terms:
            value = request.POST.get(f"mark_{skill.id}_{term.id}", "")
            if value in valid:
                SkillMark.objects.update_or_create(skill=skill, term=term,
                                                   defaults={"status": value})
            else:
                SkillMark.objects.filter(skill=skill, term=term).delete()
    messages.success(request, "Checklist saved.")
    return redirect(course.get_absolute_url())


def skill_delete(request, pk):
    skill = get_object_or_404(Skill, pk=pk)
    return delete_object(request, skill, success_url=skill.course.get_absolute_url())


# --------------------------------------------------------------------------
# Hours
# --------------------------------------------------------------------------


@require_POST
def hours_add(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    form = HoursLogForm(request.POST)
    if form.is_valid():
        log = form.save(commit=False)
        log.course = course
        log.save()
        messages.success(request, f"Logged {log.hours} hours.")
    else:
        messages.error(request, "Enter a date and a positive number of hours.")
    return redirect(course.get_absolute_url())


def hours_delete(request, pk):
    log = get_object_or_404(HoursLog, pk=pk)
    return delete_object(request, log, success_url=log.course.get_absolute_url(),
                         description=f"{log.hours} hours on {log.date}")


@require_POST
def hours_apply_credits(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk)
    course.credits = grading.suggested_credits(grading.course_hours(course))
    course.save(update_fields=["credits"])
    messages.success(request, f"Credits set to {course.credits}.")
    return redirect(course.get_absolute_url())


# --------------------------------------------------------------------------
# Rubrics
# --------------------------------------------------------------------------


def rubric_list(request):
    return render(request, "grades/rubric_list.html", {
        "rubrics": Rubric.objects.prefetch_related("criteria"),
    })


def rubric_create(request):
    return edit_object(request, RubricForm, title="New rubric",
                       success_url=lambda r: r.get_absolute_url(),
                       cancel_url=reverse("rubric_list"))


def rubric_edit(request, pk):
    rubric = get_object_or_404(Rubric, pk=pk)
    return edit_object(request, RubricForm, rubric, title=f"Edit {rubric}",
                       success_url=rubric.get_absolute_url(),
                       cancel_url=rubric.get_absolute_url())


def rubric_delete(request, pk):
    rubric = get_object_or_404(Rubric, pk=pk)
    return delete_object(request, rubric, success_url=reverse("rubric_list"))


def rubric_detail(request, pk):
    rubric = get_object_or_404(Rubric, pk=pk)
    if request.method == "POST":
        form = RubricCriterionForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.rubric = rubric
            c.save()
            messages.success(request, f"Added {c.name}.")
            return redirect(rubric.get_absolute_url())
    else:
        form = RubricCriterionForm(initial={"order": rubric.criteria.count() + 1})
    return render(request, "grades/rubric_detail.html", {
        "rubric": rubric, "form": form, "levels": list(rubric.labels.items()),
    })


def criterion_edit(request, pk):
    c = get_object_or_404(RubricCriterion, pk=pk)
    return edit_object(request, RubricCriterionForm, c, title=f"Edit criterion",
                       success_url=c.rubric.get_absolute_url(),
                       cancel_url=c.rubric.get_absolute_url())


def criterion_delete(request, pk):
    c = get_object_or_404(RubricCriterion, pk=pk)
    return delete_object(request, c, success_url=c.rubric.get_absolute_url())


# --------------------------------------------------------------------------
# Attendance
# --------------------------------------------------------------------------


def attendance(request):
    settings = SchoolSettings.load()
    if not settings.track_attendance:
        messages.info(request, "Attendance tracking is off. Turn it on in Settings.")
        return redirect("settings")
    try:
        day = datetime.date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        day = timezone.localdate()
    students = list(Student.objects.filter(active=True))
    if request.method == "POST":
        valid = {code for code, _ in AttendanceRecord.STATUSES}
        for s in students:
            status = request.POST.get(f"status_{s.id}", "")
            note = request.POST.get(f"note_{s.id}", "").strip()[:300]
            if status in valid:
                AttendanceRecord.objects.update_or_create(
                    student=s, date=day, defaults={"status": status, "note": note})
            elif status == "":
                AttendanceRecord.objects.filter(student=s, date=day).delete()
        messages.success(request, f"Attendance saved for {day:%A, %B %-d}.")
        nxt = day + datetime.timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += datetime.timedelta(days=1)
        return redirect(f"{reverse('attendance')}?date={nxt.isoformat()}")
    records = {r.student_id: r for r in AttendanceRecord.objects.filter(date=day)}
    year = SchoolYear.current()
    rows = []
    for s in students:
        summary = grading.attendance_summary(s, year.start_date, year.end_date) if year else None
        rows.append({"student": s, "record": records.get(s.id), "summary": summary})
    return render(request, "grades/attendance.html", {
        "day": day, "rows": rows, "statuses": AttendanceRecord.STATUSES, "year": year,
        "prev": day - datetime.timedelta(days=1), "next": day + datetime.timedelta(days=1),
        "date_form": AttendanceDateForm(initial={"date": day}),
    })


def attendance_student(request, student_pk, year_pk):
    student = get_object_or_404(Student, pk=student_pk)
    year = get_object_or_404(SchoolYear, pk=year_pk)
    records = student.attendance.filter(date__gte=year.start_date, date__lte=year.end_date)
    return render(request, "grades/attendance_student.html", {
        "student": student, "year": year, "records": records.order_by("date"),
        "summary": grading.attendance_summary(student, year.start_date, year.end_date),
    })


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


def report_card(request, student_pk, year_pk):
    student = get_object_or_404(Student, pk=student_pk)
    year = get_object_or_404(SchoolYear, pk=year_pk)
    settings = SchoolSettings.load()
    scale = grading.grade_scale()
    all_terms = list(year.terms.all())
    term_id = request.GET.get("term")
    # A term report card shows grading periods up to and including the chosen one.
    if term_id and term_id.isdigit():
        chosen = next((t for t in all_terms if t.id == int(term_id)), None)
        terms = all_terms[: all_terms.index(chosen) + 1] if chosen else all_terms
    else:
        chosen = None
        terms = all_terms
    show_final = chosen is None or chosen == all_terms[-1]

    courses = student.courses.filter(school_year=year).prefetch_related(
        "assignments", "categories", "term_grades", "skills__marks")
    graded, checklists = [], []
    for course in courses:
        grade = grading.course_grade(course, all_terms, scale, settings)
        comments = [(t, grade.term_comments[t.id]) for t in terms if t.id in grade.term_comments]
        entry = {"course": course, "grade": grade, "comments": comments,
                 "term_letters": [grade.term_letters.get(t.id, "") for t in terms]}
        if course.is_checklist:
            marks = {(m.skill_id, m.term_id): m.get_status_display()
                     for s in course.skills.all() for m in s.marks.all()}
            entry["skills"] = [
                {"skill": s, "marks": [marks.get((s.id, t.id), "") for t in terms]}
                for s in course.skills.all()
            ]
            checklists.append(entry)
        else:
            graded.append(entry)

    end = (chosen.end_date if chosen and chosen.end_date else year.end_date)
    attendance = None
    if settings.track_attendance:
        attendance = grading.attendance_summary(student, year.start_date, end)
    hours = None
    if settings.track_hours:
        hours = [(c, grading.course_hours(c)) for c in courses]
        hours = [h for h in hours if h[1]]
    return render(request, "grades/report_card.html", {
        "student": student, "year": year, "terms": terms, "all_terms": all_terms,
        "chosen": chosen, "show_final": show_final, "graded": graded, "checklists": checklists,
        "enrollment": student.enrollments.filter(school_year=year).first(),
        "attendance": attendance, "hours": hours, "scale": grading.scale_ranges(scale),
        "today": timezone.localdate(),
    })


def transcript(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    return render(request, "grades/transcript.html", {
        "t": grading.build_transcript(student),
        "scale": grading.scale_ranges(),
        "today": timezone.localdate(),
    })


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def settings_view(request):
    school = SchoolSettings.load()
    if request.method == "POST":
        form = SchoolSettingsForm(request.POST, instance=school)
        formset = GradeScaleFormSet(request.POST, prefix="scale")
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = SchoolSettingsForm(instance=school)
        formset = GradeScaleFormSet(prefix="scale")
    return render(request, "grades/settings.html", {"form": form, "formset": formset})
