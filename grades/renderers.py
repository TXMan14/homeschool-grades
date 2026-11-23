from django.forms.renderers import TemplatesSetting


class UIFormRenderer(TemplatesSetting):
    """Render every form with the app's own field and layout templates."""

    form_template_name = "grades/forms/form.html"
    field_template_name = "grades/forms/field.html"
