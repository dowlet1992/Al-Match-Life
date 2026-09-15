from markupsafe import Markup, escape


def render_csrf_input(token):
    """Build the trusted hidden field while escaping its dynamic value."""
    return Markup('<input type="hidden" name="csrf_token" value="{}">').format(
        escape(str(token or ""))
    )
