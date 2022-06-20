from MySQLdb import DatabaseError
from django.apps import AppConfig


class EducationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'education'

    def ready(self) -> None:
        from . import signals