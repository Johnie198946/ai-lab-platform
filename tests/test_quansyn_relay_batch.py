"""Synthetic fixtures only; no real session data or remote services."""
import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).parents[1] / 'agency/hermes-plugins/ai-lab-capabilities/quansyn_relay.py'
spec = importlib.util.spec_from_file_location('relay_batch_test', PATH)
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class DB:
    def __init__(self, messages):
        self.messages = messages
    def get_messages(self, session, **kw):
        assert session == 'current'
        assert kw['include_compacted'] is True
        return self.messages


def rows(count=8):
    return [{'id': i, 'role': 'user' if i % 2 else 'assistant', 'content': f'content {i}'} for i in range(1, count + 1)]


def test_latest_five_chronological_cursor_noop(tmp_path):
    calls = []
    def request(owner, method, path, **kw):
        if method == 'GET':
            return {'id': 'qs_' + 'a' * 32, **calls[-1]}
        calls.append(kw['payload'])
        return {'id': 'qs_' + 'a' * 32}
    result = relay.push_recent('owner', 'current', tmp_path, request, DB(rows()))
    assert result['count'] == 5 and result['skipped_count'] == 3 and result['lossy']
    assert '永久跳过' in result['receipt']
    assert calls[0]['text'] == '\n\n'.join(f"[{r['role']}]\n{r['content']}" for r in rows()[3:])
    assert 'reply_to' not in calls[0]
    assert relay.push_recent('owner', 'current', tmp_path, request, DB(rows()))['noop']
    assert len(calls) == 1


def test_failed_publish_preserves_cursor_and_idempotency(tmp_path):
    ids = []
    payloads = []
    def request(owner, method, path, **kw):
        if method == 'GET':
            return {'id': 'qs_' + 'a' * 32, **payloads[-1]}
        payloads.append(kw['payload'])
        ids.append(kw['payload']['request_id'])
        if len(ids) == 1:
            raise ValueError('offline')
        return {'id': 'qs_' + 'a' * 32}
    with pytest.raises(ValueError):
        relay.push_recent('owner', 'current', tmp_path, request, DB(rows()))
    assert not list(tmp_path.rglob('*.json'))
    relay.push_recent('owner', 'current', tmp_path, request, DB(rows()))
    assert ids[0] == ids[1]


def test_filter_roles_hidden_tools_commands_and_origin():
    messages = rows(1)
    variants = [dict(role='system'), dict(role='tool'), dict(display_kind='hidden'),
                dict(display_kind='error'), dict(streaming=True), dict(tool_calls=[{}]),
                dict(content='/push'), dict(content='/pull'), dict(finish_reason='error'),
                dict(display_metadata={'quansyn_origin': True})]
    messages += [{'id': i + 2, 'role': 'assistant', 'content': 'excluded', **variant}
                 for i, variant in enumerate(variants)]
    chosen, skipped = relay.select_messages(DB(messages), 'current', 0)
    assert [row['id'] for row in chosen] == [1] and skipped == 0


def test_attachment_all_or_nothing_and_hash_key(tmp_path):
    attachment = tmp_path / 'image.png'
    attachment.write_bytes(b'synthetic-image')
    message = {'id': 1, 'role': 'user', 'content': f'[Image attached at: {attachment}]\nMEDIA: {attachment}'}
    calls = []
    uploaded_bodies = []
    def request(owner, method, path, **kw):
        if path == '/files':
            uploaded_bodies.append(kw['data'].read())
        calls.append((path, kw))
        if method == 'GET':
            return {'id': 'qs_' + 'a' * 32, **calls[-2][1]['payload']}
        return {'artifact_id': 'ga_' + 'b' * 32} if path == '/files' else {'id': 'qs_' + 'a' * 32}
    result = relay.push_recent('owner', 'current', tmp_path / 'state', request, DB([message]))
    assert [path for path, _ in calls] == ['/files', '/transfers', '/transfers/' + 'qs_' + 'a' * 32]
    assert uploaded_bodies == [b'synthetic-image']
    assert calls[1][1]['payload']['files'] == [{'artifact_id': 'ga_' + 'b' * 32}]
    assert str(attachment) not in calls[1][1]['payload']['text']
    attachment.write_bytes(b'changed')
    another = relay.push_recent('owner', 'current', tmp_path / 'other', request, DB([message]))
    assert result['request_id'] != another['request_id']
    attachment.unlink()
    with pytest.raises(OSError):
        relay.push_recent('owner', 'current', tmp_path / 'missing', request, DB([message]))
    assert not list((tmp_path / 'missing').rglob('*.json'))


@pytest.mark.parametrize('kind', ['change', 'upload_failure', 'publish_failure', 'unconfirmed'])
def test_attachment_failure_never_moves_cursor(tmp_path, kind):
    file = tmp_path / 'input.txt'
    file.write_text('synthetic')
    published = []
    def request(owner, method, path, **kw):
        if path == '/files':
            if kind == 'change':
                file.write_text('changed')
            if kind == 'upload_failure':
                raise ValueError('offline')
            return {'artifact_id': 'ga_' + 'b' * 32}
        if method == 'GET':
            return {'id': 'qs_' + 'a' * 32, **published[-1]}
        if kind == 'publish_failure':
            raise ValueError('offline')
        if kind == 'unconfirmed':
            return {}
        published.append(kw['payload'])
        return {'id': 'qs_' + 'a' * 32}
    with pytest.raises(ValueError):
        relay.push_recent('owner', 'current', tmp_path / 'state', request,
                          DB([{'id': 1, 'role': 'assistant', 'content': f'MEDIA: {file}'}]))
    assert not list((tmp_path / 'state').rglob('*.json'))


def test_unsafe_large_and_too_many_attachments(tmp_path):
    file = tmp_path / 'target'; file.write_text('synthetic')
    link = tmp_path / 'link'; link.symlink_to(file)
    with pytest.raises(ValueError):
        relay.read_attachment(str(link))
    with file.open('wb') as stream:
        stream.truncate(26 * 1024 * 1024)
    path, digest, fingerprint = relay.read_attachment(str(file))
    assert path == file and len(digest) == 64 and fingerprint[3] == 26 * 1024 * 1024
    with pytest.raises(ValueError):
        relay.attachment_paths([{'text': '\n'.join(f'MEDIA: /tmp/{i}' for i in range(11))}])


def test_display_text_retains_underlying_attachment_handles(tmp_path):
    file = tmp_path / 'image.png'; file.write_bytes(b'synthetic')
    messages, _ = relay.select_messages(DB([{'id': 1, 'role': 'user', 'display_content': 'visible',
                                            'content': f'visible\nMEDIA: {file}'}]), 'current', 0)
    assert messages[0]['text'] == 'visible'
    assert relay.attachment_paths(messages) == [str(file)]


def test_readback_mismatch_never_moves_cursor(tmp_path):
    payload = []
    def request(owner, method, path, **kw):
        if method == 'GET':
            return {'id': 'qs_' + 'a' * 32, **payload[-1], 'text': 'tampered'}
        payload.append(kw['payload'])
        return {'id': 'qs_' + 'a' * 32}
    with pytest.raises(ValueError, match='readback'):
        relay.push_recent('owner', 'current', tmp_path, request, DB(rows(1)))
    assert not list(tmp_path.rglob('*.json'))
