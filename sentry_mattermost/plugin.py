from __future__ import absolute_import
import os
import json

from sentry import tagstore
from sentry.plugins.bases import notify
from sentry_plugins.base import CorePluginMixin
from sentry.http import safe_urlopen, is_valid_url
from sentry.utils.safe import safe_execute

try:
    from sentry.integrations import FeatureDescription, IntegrationFeatures
except ImportError:
    from sentry.integrations.base import FeatureDescription, IntegrationFeatures

import sentry_mattermost


def get_tags(event):
    tag_list = event.tags
    if not tag_list:
        return ()

    return (
        (tagstore.get_tag_key_label(k), tagstore.get_tag_value_label(k, v)) for k, v in tag_list
    )


class Mattermost(CorePluginMixin, notify.NotificationPlugin):
    title = 'Mattermost'
    slug = 'mattermost'
    description = 'Sends alerts to Mattermost channel based on Sentry alerts rules'
    version = sentry_mattermost.VERSION
    timeout = 10
    author = 'Radzhab'
    author_url = 'https://band.wb.ru'
    user_agent = 'sentry-mattermost/%s' % version
    feature_descriptions = [
        FeatureDescription(
            """
            Send notifications to Mattermost channel based on Sentry alerts rules
            """,
            IntegrationFeatures.ALERT_RULE,
        )
    ]

    def is_configured(self, project):
        channel_id = self.get_option("channel_id", project)
        token = os.getenv("MATTERMOST_TOKEN")
        return bool(channel_id and token)

    def get_mattermost_token(self):
        return os.getenv("MATTERMOST_TOKEN")

    def render_notification(self, data, customFormat):
        if customFormat:
            template = customFormat
        else:
            template = "#### {project_name} - {env}\n{tags}\n\n{culprit}\n[{title}]({link})"
        return template.format(**data)

    def create_payload(self, event):
        group = event.group
        project = group.project

        tags = []
        for tag_key, tag_value in get_tags(event):
            tags.append("`{}` ".format(tag_value))

        data = {
            "title": group.message_short,
            "link": group.get_absolute_url(),
            "id": event.event_id,
            "culprit": group.culprit,
            "env": event.get_environment().name,
            "project_slug": group.project.slug,
            "project_name": group.project.name,
            "tags": " ".join(tags),
            "level": event.get_tag("level"),
            "message": event.message,
            "release": event.release,
        }

        message_text = self.render_notification(data, self.get_option("custom_format", project))

        payload = {
            "channel_id": self.get_option("channel_id", project),
            "message": message_text,
            "username": self.get_option("bot_name", project) or "Sentry",
        }

        return payload

    def get_config(self, project, **kwargs):
        return [
            {
                "name": "mattermost_url",
                "label": "Mattermost URL",
                "type": "text",
                "required": False,
                "default": "https://band.wb.ru",
                "readonly": True,
                "help": "Your Mattermost instance URL (read-only).",
            },
            {
                "name": "channel_id",
                "label": "Channel ID",
                "type": "string",
                "required": True,
                "placeholder": "e.g. channel123456789",
                "help": "The ID of the Mattermost channel where notifications will be sent.",
            },
            {
                "name": "bot_name",
                "label": "Bot Name",
                "type": "string",
                "placeholder": "e.g. Sentry",
                "default": "Sentry",
                "required": False,
                "help": "The name used in channel when publishing notifications.",
            },
        ]

    def send_to_mattermost(self, channel_id, payload):
        token = self.get_mattermost_token()
        if not token:
            raise Exception("MATTERMOST_TOKEN environment variable is not set")

        # Базовый URL для Mattermost API
        mattermost_url = "https://band.wb.ru"
        api_url = f"{mattermost_url}/api/v4/posts"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        return safe_urlopen(
            url=api_url,
            json=payload,
            headers=headers,
            timeout=self.timeout,
            user_agent=self.user_agent
        )

    def notify(self, notification, raise_exception=False):
        event = notification.event
        group = event.group
        project = group.project

        if not self.is_configured(project):
            return

        channel_id = self.get_option("channel_id", project)
        if not channel_id:
            return

        payload = self.create_payload(event)
        return safe_execute(self.send_to_mattermost, channel_id, payload)