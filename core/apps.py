from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = "Core Application"

    def ready(self):
        import core.auth_security  # noqa: F401
