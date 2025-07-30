from setuptools import setup, find_packages

setup(
    name="sentry-mattermost",
    version='0.0.4',
    author="Radzhab",
    author_email="deverlabs@gmail.com",
    description=("A Sentry plugin to send alerts to Mattermost channel."),
    keywords="sentry mattermost",
    url="https://band.wb.ru",
    packages=find_packages(exclude=['tests']),
    entry_points={
       'sentry.plugins': [
            'mattermost = sentry_mattermost.plugin:Mattermost'
        ],
    },
)