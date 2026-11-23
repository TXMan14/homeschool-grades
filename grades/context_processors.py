from .models import SchoolSettings


def school(request):
    if not request.user.is_authenticated:
        return {}
    return {"school": SchoolSettings.load()}
