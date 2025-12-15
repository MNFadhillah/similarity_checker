import os
import sys

# path ke root project
sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "similarity_checker.settings"
)

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
