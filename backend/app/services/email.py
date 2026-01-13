"""Email service for sending transactional emails."""

from typing import TYPE_CHECKING

import structlog

from app.core.config import settings

# Make sendgrid optional - app can run without it
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False
    if TYPE_CHECKING:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

logger = structlog.get_logger()


async def send_invitation_email(
    to_email: str,
    workspace_name: str,
    inviter_name: str,
    invitation_url: str,
    role: str,
    message: str | None = None,
) -> bool:
    """Send a workspace invitation email.

    Args:
        to_email: Recipient email address
        workspace_name: Name of the workspace
        inviter_name: Name of the person who sent the invitation
        invitation_url: URL to accept the invitation
        role: Role being offered (admin, member)
        message: Optional personal message from the inviter

    Returns:
        True if email was sent successfully, False otherwise
    """
    if not SENDGRID_AVAILABLE:
        logger.warning("sendgrid_not_installed", hint="Install with: uv add sendgrid")
        return False

    if not settings.sendgrid_api_key:
        logger.warning("sendgrid_api_key_not_configured")
        return False

    subject = f"You've been invited to join {workspace_name}"

    # Build email content
    personal_message = ""
    if message:
        personal_message = f"""
        <p style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <em>"{message}"</em>
        </p>
        """

    role_display = "an administrator" if role == "admin" else "a team member"

    # Build HTML email content
    body_style = (
        "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
        "line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;"
    )
    button_style = (
        "background-color: #000; color: #fff; padding: 12px 30px; "
        "text-decoration: none; border-radius: 5px; display: inline-block; font-weight: 500;"
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="{body_style}">
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #1a1a1a; margin-bottom: 5px;">You're Invited!</h1>
    </div>
    <p>Hi there,</p>
    <p>
        <strong>{inviter_name}</strong> has invited you to join
        <strong>{workspace_name}</strong> as {role_display}.
    </p>
    {personal_message}
    <div style="text-align: center; margin: 30px 0;">
        <a href="{invitation_url}" style="{button_style}">
            Accept Invitation
        </a>
    </div>
    <p style="color: #666; font-size: 14px;">
        This invitation will expire in 7 days.
        If you didn't expect this invitation, you can safely ignore this email.
    </p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="color: #999; font-size: 12px; text-align: center;">
        Sent from AI CRM
    </p>
</body>
</html>"""

    mail = Mail(
        from_email=settings.sendgrid_from_email or "noreply@example.com",
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )

    try:
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        response = sg.send(mail)

        if response.status_code in (200, 201, 202):
            logger.info(
                "invitation_email_sent",
                to_email=to_email,
                workspace=workspace_name,
                status_code=response.status_code,
            )
            return True
        else:
            logger.error(
                "invitation_email_failed",
                to_email=to_email,
                status_code=response.status_code,
            )
            return False

    except Exception as e:
        logger.error(
            "invitation_email_error",
            to_email=to_email,
            error=str(e),
        )
        return False
