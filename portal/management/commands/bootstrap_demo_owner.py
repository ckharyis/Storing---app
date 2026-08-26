import os

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from portal.models import StaffProfile


class Command(BaseCommand):
    help = "Create the first demo owner during deployment when no owner exists."

    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            self.stdout.write("Skipping demo owner bootstrap outside demo mode.")
            return

        if StaffProfile.objects.filter(role=StaffProfile.Role.OWNER).exists():
            self.stdout.write("An owner already exists; demo bootstrap skipped.")
            return

        username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
        email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().casefold()
        password = os.getenv("INITIAL_ADMIN_PASSWORD", "")

        missing = [
            name
            for name, value in {
                "INITIAL_ADMIN_USERNAME": username,
                "INITIAL_ADMIN_EMAIL": email,
                "INITIAL_ADMIN_PASSWORD": password,
            }.items()
            if not value
        ]
        if missing:
            raise CommandError("Missing first-owner settings: " + ", ".join(missing))
        if len(username) > User._meta.get_field("username").max_length:
            raise CommandError("INITIAL_ADMIN_USERNAME is too long.")
        if len(password) < 16:
            raise CommandError("INITIAL_ADMIN_PASSWORD must contain at least 16 characters.")

        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("INITIAL_ADMIN_EMAIL must be a valid email address.") from exc

        candidate = User(username=username, email=email)
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise CommandError("INITIAL_ADMIN_PASSWORD is not strong enough: " + " ".join(exc.messages)) from exc

        with transaction.atomic():
            user, created = User.objects.get_or_create(username=username)
            user.email = email
            user.is_staff = True
            user.is_active = True
            user.set_password(password)
            user.save()
            StaffProfile.objects.update_or_create(user=user, defaults={"role": StaffProfile.Role.OWNER})

        action = "Created" if created else "Activated"
        self.stdout.write(self.style.SUCCESS(f"{action} the first demo owner. MFA enrollment is required at first login."))
