from .models import SchoolSettings, SchoolYear


def school(request):
    if not request.user.is_authenticated:
        return {}
    return {"school": SchoolSettings.load(), "current_year": SchoolYear.current()}
