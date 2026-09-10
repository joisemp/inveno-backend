"""
Email helpers for the users app.

send_welcome_email() sends the one-time get-started email to a newly created
central admin so they can set their password and access the platform.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.users.tokens import password_setup_token_generator

logger = logging.getLogger(__name__)


def send_welcome_email(user) -> None:
    """
    Send a welcome / get-started email to *user*.

    The email contains a link to the frontend's /get-started page that
    embeds a uid + token so the user can set their password.

    In development the email is printed to the terminal (console backend).
    The token is valid for PASSWORD_SETUP_TIMEOUT seconds (default 7 days).
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = password_setup_token_generator.make_token(user)

    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    get_started_url = f"{frontend_url}/get-started?uid={uid}&token={token}"

    try:
        full_name = user.profile.full_name
        org_name = user.profile.org.name if user.profile.org else "Inveno"
    except Exception:
        full_name = user.email
        org_name = "Inveno"

    context = {
        "full_name": full_name,
        "org_name": org_name,
        "get_started_url": get_started_url,
    }

    subject = f"Welcome to {org_name} — set your password to get started"
    text_body = render_to_string("emails/welcome.txt", context)
    html_body = render_to_string("emails/welcome.html", context)

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.attach_alternative(html_body, "text/html")
    email.send()

    logger.info("Welcome email sent to %s", user.email)
