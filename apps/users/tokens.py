"""
Custom token generator for the one-time welcome / get-started link.

PasswordSetupTokenGenerator differs from Django's default reset generator in
two ways:
  1. The hash includes user.has_usable_password() so the token is
     automatically invalidated once the user sets their password.
  2. It uses PASSWORD_SETUP_TIMEOUT (default 7 days = 604 800 s) instead of
     the shorter PASSWORD_RESET_TIMEOUT (1 hour) used by forgot-password.
"""
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int


class PasswordSetupTokenGenerator(PasswordResetTokenGenerator):
    """
    One-time token for the welcome-email get-started link.

    Token is valid for PASSWORD_SETUP_TIMEOUT seconds (default: 7 days).
    It is automatically invalidated once the central admin sets a password.
    """

    # Use a different key_salt so setup tokens are distinct from reset tokens.
    key_salt = "apps.users.tokens.PasswordSetupTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        """
        Include has_usable_password in the hash so the token is invalidated
        after the user successfully sets their password.
        """
        return str(user.pk) + str(timestamp) + str(user.has_usable_password())

    def check_token(self, user, token):
        """
        Validate the token, using PASSWORD_SETUP_TIMEOUT as the TTL instead
        of PASSWORD_RESET_TIMEOUT.
        """
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split("-")
        except ValueError:
            return False
        try:
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False

        # Verify HMAC
        if not constant_time_compare(
            self._make_token_with_timestamp(user, ts, self.secret), token
        ):
            if not any(
                constant_time_compare(
                    self._make_token_with_timestamp(user, ts, fb), token
                )
                for fb in self.secret_fallbacks
            ):
                return False

        # Check TTL using our own setting
        timeout = getattr(settings, "PASSWORD_SETUP_TIMEOUT", 7 * 24 * 3600)
        if (self._num_seconds(self._now()) - ts) > timeout:
            return False

        return True


# Module-level singleton used throughout the app
password_setup_token_generator = PasswordSetupTokenGenerator()
