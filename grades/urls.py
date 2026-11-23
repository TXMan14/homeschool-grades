from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("settings/", views.settings_view, name="settings"),
    # Students
    path("students/", views.student_list, name="student_list"),
    path("students/new/", views.student_create, name="student_create"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("students/<int:pk>/edit/", views.student_edit, name="student_edit"),
    path("students/<int:pk>/delete/", views.student_delete, name="student_delete"),
    path("students/<int:student_pk>/grade-level/", views.enrollment_create, name="enrollment_create"),
    path("grade-levels/<int:pk>/edit/", views.enrollment_edit, name="enrollment_edit"),
    # Years and terms
    path("years/", views.year_list, name="year_list"),
    path("years/new/", views.year_create, name="year_create"),
    path("years/<int:pk>/edit/", views.year_edit, name="year_edit"),
    path("years/<int:pk>/delete/", views.year_delete, name="year_delete"),
    path("years/<int:year_pk>/terms/new/", views.term_create, name="term_create"),
    path("terms/<int:pk>/edit/", views.term_edit, name="term_edit"),
    path("terms/<int:pk>/delete/", views.term_delete, name="term_delete"),
    # Courses
    path("courses/new/", views.course_create, name="course_create"),
    path("courses/<int:pk>/", views.course_detail, name="course_detail"),
    path("courses/<int:pk>/edit/", views.course_edit, name="course_edit"),
    path("courses/<int:pk>/delete/", views.course_delete, name="course_delete"),
    path("courses/<int:course_pk>/categories/add/", views.category_add, name="category_add"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("courses/<int:course_pk>/term-grades/", views.term_grades_save, name="term_grades_save"),
    path("courses/<int:course_pk>/assignments/quick/", views.assignment_quick_add, name="assignment_quick_add"),
    path("courses/<int:course_pk>/assignments/new/", views.assignment_create, name="assignment_create"),
    path("assignments/<int:pk>/edit/", views.assignment_edit, name="assignment_edit"),
    path("assignments/<int:pk>/delete/", views.assignment_delete, name="assignment_delete"),
    path("assignments/<int:pk>/rubric/", views.assignment_rubric, name="assignment_rubric"),
    path("courses/<int:course_pk>/skills/add/", views.skills_add, name="skills_add"),
    path("courses/<int:course_pk>/skills/marks/", views.skills_marks_save, name="skills_marks_save"),
    path("skills/<int:pk>/delete/", views.skill_delete, name="skill_delete"),
    path("courses/<int:course_pk>/hours/add/", views.hours_add, name="hours_add"),
    path("courses/<int:course_pk>/hours/apply-credits/", views.hours_apply_credits, name="hours_apply_credits"),
    path("hours/<int:pk>/delete/", views.hours_delete, name="hours_delete"),
    # Rubrics
    path("rubrics/", views.rubric_list, name="rubric_list"),
    path("rubrics/new/", views.rubric_create, name="rubric_create"),
    path("rubrics/<int:pk>/", views.rubric_detail, name="rubric_detail"),
    path("rubrics/<int:pk>/edit/", views.rubric_edit, name="rubric_edit"),
    path("rubrics/<int:pk>/delete/", views.rubric_delete, name="rubric_delete"),
    path("criteria/<int:pk>/edit/", views.criterion_edit, name="criterion_edit"),
    path("criteria/<int:pk>/delete/", views.criterion_delete, name="criterion_delete"),
    # Attendance
    path("attendance/", views.attendance, name="attendance"),
    path("attendance/<int:student_pk>/<int:year_pk>/", views.attendance_student, name="attendance_student"),
    # Reports
    path("reports/<int:student_pk>/<int:year_pk>/report-card/", views.report_card, name="report_card"),
    path("reports/<int:student_pk>/transcript/", views.transcript, name="transcript"),
]
