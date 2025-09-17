from django.apps import AppConfig


class VerifyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'verify'

    def ready(self):
        # import signals so they are registered
        import verify.signals  # noqa: F401
