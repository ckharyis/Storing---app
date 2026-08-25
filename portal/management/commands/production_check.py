from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fail unless the portal is configured for real-data production use."

    def handle(self, *args, **options):
        if settings.DEMO_MODE:
            raise CommandError("DEMO_MODE is enabled. Real applications must not be accepted.")
        if settings.PRODUCTION_COMPLIANCE_ACK != "CONFIRMED":
            raise CommandError("Legal/compliance acknowledgement is missing.")
        if not settings.USE_S3:
            raise CommandError("Private object storage is required.")
        if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
            raise CommandError("Production requires PostgreSQL, not SQLite.")
        if not settings.SITE_BASE_URL.startswith("https://"):
            raise CommandError("SITE_BASE_URL must use HTTPS.")
        if not settings.CSRF_TRUSTED_ORIGINS or any(not origin.startswith("https://") for origin in settings.CSRF_TRUSTED_ORIGINS):
            raise CommandError("CSRF_TRUSTED_ORIGINS must contain the production HTTPS origin.")
        call_command("check", "--deploy")
        self.stdout.write(self.style.SUCCESS("Production configuration checks passed."))
