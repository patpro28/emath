import json
import os
import uuid
from urllib.parse import urljoin

from django.conf import settings
from martor.api import imgur_uploader
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage

def django_uploader(image):
    ext = os.path.splitext(image.name)[1]
    if ext not in settings.MARTOR_UPLOAD_SAFE_EXTS:
        ext = '.png'
    name = str(uuid.uuid4()) + ext
    default_storage.save(os.path.join(settings.MARTOR_UPLOAD_MEDIA_DIR, name), image)
    url_base = getattr(settings, 'MARTOR_UPLOAD_URL_PREFIX',
                       urljoin(settings.MEDIA_URL, settings.MARTOR_UPLOAD_MEDIA_DIR))
    if not url_base.endswith('/'):
        url_base += '/'
    return json.dumps({'status': 200, 'name': '', 'link': urljoin(url_base, name)})

@login_required
def martor_image_uploader(request):
    if request.method != 'POST' or 'markdown-image-upload' not in request.FILES:
        return HttpResponseBadRequest('Invalid request')

    image = request.FILES['markdown-image-upload']
    if request.user.is_staff:
        data = django_uploader(image)
    else:
        data = imgur_uploader(image)
    return HttpResponse(data, content_type='application/json')