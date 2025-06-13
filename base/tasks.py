import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

@shared_task
def send_email_with_template(data: dict, template_name: str, context: dict, recipient: list):
    template_name = f'emails/{template_name}'
    try:
        email_body = render_to_string(template_name, context)

        email = EmailMessage(
            subject=data['subject'],
            body=email_body,
            from_email=settings.EMAIL_HOST_USER,
            to=recipient,
        )
        email.content_subtype = 'html'
        email.send()
        logger.info('Email sent')
    except Exception as e:
        print("❌ EMAIL FAILED:", str(e))