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
        print(f"[MATTERMOST DEBUG] is_configured: channel_id={channel_id}, token_exists={bool(token)}")
        return bool(channel_id and token)

    def get_mattermost_token(self):
        return os.getenv("MATTERMOST_TOKEN")

    def create_payload(self, event):
        group = event.group
        project = group.project
        
        # Получаем данные из event (аналогично gjson в Go коде)
        level = event.get_tag("level") or "error"
        title = group.title or "Unknown Error"  # заменил message_short на title
        event_id = event.event_id
        project_name = project.name
        project_id = str(project.id)
        platform = event.platform or "unknown"
        release = event.release or "unknown"
        environment = event.get_environment().name if event.get_environment() else "unknown"
        message = event.message or ""
        url = group.get_absolute_url()
        
        # Извлекаем runtime информацию если есть
        runtime_name = "unknown"
        runtime_build = "unknown"
        transaction = "unknown"
        
        if hasattr(event, 'data') and event.data:
            contexts = event.data.get('contexts', {})
            runtime = contexts.get('runtime', {})
            runtime_name = runtime.get('name', 'unknown')
            runtime_build = runtime.get('build', 'unknown')
            transaction = event.data.get('transaction', 'unknown')
        
        # Извлекаем metadata
        metadata_type = "unknown"
        metadata_filename = "unknown" 
        metadata_function = "unknown"
        metadata_value = "unknown"
        
        if hasattr(event, 'data') and event.data:
            metadata = event.data.get('metadata', {})
            metadata_type = metadata.get('type', 'unknown')
            metadata_filename = metadata.get('filename', 'unknown')
            metadata_function = metadata.get('function', 'unknown')
            metadata_value = metadata.get('value', 'unknown')

        # Формируем payload с attachments как в Go коде
        payload = {
            "channel_id": self.get_option("channel_id", project),
            "username": self.get_option("bot_name", project) or "Sentry",
            "attachments": [
                {
                    "author_name": "Sentry (https://sentry.wb.ru)",
                    "author_icon": "https://assets.stickpng.com/images/58482eedcef1014c0b5e4a76.png",
                    "title": "[{}] {}".format(level.upper(), title),
                    "fallback": "[{}] {}".format(level.upper(), title),
                    "pretext": "**Event ID**: {}".format(event_id),
                    "text": message,
                    "color": "#FF0000",
                    "title_link": url,
                    "fields": [
                        {
                            "short": False,
                            "title": "Project Info",
                            "value": "**Project Name**: {}\n**ProjectID**: {}".format(
                                project_name, project_id
                            )
                        },
                        {
                            "short": False,
                            "title": "Event Info", 
                            "value": "**Platform**: {}\n**Runtime**: {} [{}]\n**Release**: {}\n**Environment**: {}\n**Transaction**: {}".format(
                                platform, runtime_name, runtime_build, release, environment, transaction
                            )
                        },
                        {
                            "short": False,
                            "title": "Event Metadata",
                            "value": "**Type**: {}\n**Filename**: {}\n**Function**: {}\n**Description**: {}".format(
                                metadata_type, metadata_filename, metadata_function, metadata_value
                            )
                        }
                    ]
                }
            ]
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
            raise Exception("MM_BOT_TOKEN environment variable is not set")
        
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
            timeout=self.timeout
        )

    def notify(self, notification, raise_exception=False):
        print(f"[MATTERMOST DEBUG] notify called for event: {notification.event.event_id}")
        
        event = notification.event
        group = event.group
        project = group.project
        
        print(f"[MATTERMOST DEBUG] Project: {project.name}, Group: {group.id}")
        
        if not self.is_configured(project):
            print("[MATTERMOST DEBUG] Plugin not configured, skipping")
            return
            
        channel_id = self.get_option("channel_id", project)
        if not channel_id:
            print("[MATTERMOST ERROR] No channel_id configured")
            return
            
        print(f"[MATTERMOST DEBUG] Creating payload for channel: {channel_id}")
        payload = self.create_payload(event)
        
        print(f"[MATTERMOST DEBUG] Calling send_to_mattermost")
        return safe_execute(self.send_to_mattermost, channel_id, payload)