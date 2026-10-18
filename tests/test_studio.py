from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from qmrsmithbot.api.app import app
from qmrsmithbot.api.studio import ButtonDraft, button_view, revision


def test_studio_requires_session_and_asset_remains_same_origin():
    with TestClient(app) as client:
        assert client.get('/dashboard/assets/studio.js').status_code == 200
        assert client.get(f'/api/v1/projects/{uuid4()}/studio').status_code == 401
        assert client.put(f'/api/v1/projects/{uuid4()}/studio/buttons/{uuid4()}',json={}).status_code == 401


@pytest.mark.parametrize('payload', [
    {'kind':'url','title':'Link','url':'http://example.com'},
    {'kind':'url','title':'Link','url':'https://user:secret@example.com'},
    {'kind':'text','title':'Reply','text':'12345678:'+'T'*35},
    {'kind':'text','title':'Reply'},
    {'kind':'file','title':'File','text':'unexpected content'},
])
def test_button_payload_rejects_unsafe_or_incomplete_content(payload):
    with pytest.raises(ValueError):
        ButtonDraft(**payload).content()


def test_web_editor_cannot_inject_telegram_file_ids_or_change_internal_metadata():
    with pytest.raises(ValidationError):
        ButtonDraft(kind='file',title='File',file_id='untrusted')
    with pytest.raises(ValidationError):
        ButtonDraft(kind='section',title='Section',published={})
    item=SimpleNamespace(id=uuid4(),parent_id=None,deleted=False,
        draft={'kind':'file','title':'File','file_id':'bot-scoped-private','file_type':'document'},published=None)
    view=button_view(item)
    assert view['file_ready'] and view['pending'] and 'file_id' not in str(view)
    before=revision(item)
    item.draft={**item.draft,'file_id':'replaced-inside-child'}
    assert revision(item)!=before
