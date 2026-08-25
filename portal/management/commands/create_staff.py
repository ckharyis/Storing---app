import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from portal.models import StaffProfile


class Command(BaseCommand):
    help = "Create or update an invite-only staff account. Password is read from an environment variable."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--role", choices=["owner", "reviewer"], default="reviewer")
        parser.add_argument("--password-env", default="INITIAL_ADMIN_PASSWORD")

    def handle(self, *args, **options):
        password = os.getenv(options["password_env"], "")
        if len(password) < 12:
            raise CommandError(f"{options['password_env']} must contain a password of at least 12 characters.")
        user, created = User.objects.get_or_create(username=options["username"])
        user.email = options["email"].casefold()
        user.is_staff = True
        user.is_active = True
        user.set_password(password)
        user.save()
        StaffProfile.objects.update_or_create(user=user, defaults={"role": options["role"]})
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Updated'} staff account {user.username}. MFA enrollment is required at first login."))
