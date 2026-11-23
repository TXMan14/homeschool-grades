from django.contrib import admin

from . import models

admin.site.site_header = "Home School Grades - data admin"

for m in [
    models.SchoolSettings, models.GradeScaleEntry, models.Student, models.SchoolYear,
    models.Term, models.Enrollment, models.Category, models.Rubric, models.RubricCriterion,
    models.Assignment, models.RubricScore, models.TermGrade, models.Skill, models.SkillMark,
    models.HoursLog, models.AttendanceRecord,
]:
    admin.site.register(m)


class CategoryInline(admin.TabularInline):
    model = models.Category
    extra = 0


admin.site.register(models.Course, inlines=[CategoryInline],
                    list_display=["name", "student", "school_year", "grading_method", "on_transcript"],
                    list_filter=["student", "school_year", "grading_method"])
