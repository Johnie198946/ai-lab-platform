"""Mailbox presentation and persisted-session publishing; never an Agent turn."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
PATHS = re.compile(r'MEDIA:\s*(?:"([^"\n]+)"|([^\s]+))|\[Image attached at:\s*([^\]\n]+)\]')


def content_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(content_text(item) for item in value if isinstance(item, (str, dict)))
    if isinstance(value, dict):
        return value.get('text', '') if isinstance(value.get('text'), str) else ''
    return ''


def visible_text(value):
    """Keep the message body, not machine-local attachment handles."""
    return PATHS.sub('', content_text(value)).strip()


def draft_text(row):
    text = row['text'] or '\n'.join(content_text(block.get('content')) for block in row.get('blocks', []))
    return text + ('\n\n附件：\n' + '\n'.join(f"{f['name']}: {f['path']}" for f in row['files']) if row['files'] else '')


def select_messages(db, session, cursor):
    rows = db.get_messages(session, include_compacted=True, limit=100001)
    if len(rows) > 100000:
        raise ValueError('Hermes session exceeds relay selection limit')
    eligible = []
    for row in rows:
        metadata = row.get('display_metadata') or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        if (row.get('role') not in {'user', 'assistant'} or row.get('display_kind') or
                row.get('hidden') or row.get('streaming') or row.get('tool_calls') or
                row.get('finish_reason') in {'error', 'tool_calls', 'length', 'cancelled', 'interrupted'} or
                metadata.get('quansyn_origin') or metadata.get('hidden') or metadata.get('streaming') or row.get('_compressed_summary')):
            continue
        text = visible_text(row.get('display_content')) if row.get('display_content') is not None else visible_text(row.get('content'))
        attachment_text = content_text(row.get('content'))
        if (not text.strip() and not PATHS.search(attachment_text)) or text.lstrip().startswith('/'):
            continue
        ident = int(row['id'])
        if ident > cursor:
            eligible.append({'id': ident, 'role': row['role'], 'text': text,
                             'attachment_text': attachment_text})
    eligible.sort(key=lambda row: row['id'])
    return eligible[-5:], max(0, len(eligible) - 5)


def attachment_paths(messages):
    paths = []
    for message in messages:
        for match in PATHS.finditer(message['text'] + '\n' + message.get('attachment_text', '')):
            value = next(group for group in match.groups() if group is not None).strip()
            if value not in paths:
                paths.append(value)
    if len(paths) > 10:
        raise ValueError('QuanSyn permits at most 10 attachments per batch')
    return paths


def read_attachment(value):
    path = Path(value)
    if not path.is_absolute() or any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('Unsafe local attachment path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        import stat
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_BYTES:
            raise ValueError('Attachment must be a nonempty regular file of at most 25 MB')
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    fingerprint = lambda st: (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    if fingerprint(before) != fingerprint(after) or len(data) != before.st_size:
        raise ValueError('Attachment changed while reading')
    return path, data, hashlib.sha256(data).hexdigest(), fingerprint(before)


def push_recent(owner, session, state_dir, request, db=None):
    """Serialize cursor updates across Desktop and gateway processes, atomically."""
    state_dir = Path(state_dir) / 'quansyn-relay-cursors'
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256((owner + '\0' + session).encode()).hexdigest()
    path = state_dir / (key + '.json')
    with (state_dir / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cursor = json.loads(path.read_text())['cursor'] if path.exists() else 0
        owned_db = db is None
        if owned_db:
            from hermes_state import SessionDB
            db = SessionDB(read_only=True)
        try:
            messages, skipped = select_messages(db, session, cursor)
        finally:
            if owned_db:
                db.close()
        if not messages:
            return {'success': True, 'noop': True, 'count': 0, 'skipped_count': 0}
        attachments = [read_attachment(value) for value in attachment_paths(messages)]
        signature = {'owner': owner, 'session': session, 'messages': messages,
                     'files': [{'path': str(p), 'hash': h} for p, _, h, _ in attachments]}
        request_id = 'relay-' + hashlib.sha256(json.dumps(signature, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        text = '\n\n'.join(f"[{m['role']}]\n{m['text']}" for m in messages)
        if len(text) > 250000 or len(text.encode()) > 500000:
            raise ValueError('QuanSyn batch exceeds content bounds')
        batch_path = state_dir / (request_id + '.batch')
        if batch_path.exists():
            refs = json.loads(batch_path.read_text())
        else:
            refs = []
            for p, data, expected, before in attachments:
                uploaded = request(owner, 'POST', '/files', data=data, filename=p.name)
                if not re.fullmatch(r'ga_[a-f0-9]{32}', str(uploaded.get('artifact_id') or '')):
                    raise ValueError('QuanSyn did not confirm uploaded artifact')
                refs.append({'artifact_id': uploaded['artifact_id']})
            # Keep exact remote refs on retry, including ambiguous publish failures.
            temp_batch = batch_path.with_suffix('.tmp-' + secrets.token_hex(6))
            temp_batch.write_text(json.dumps(refs))
            os.chmod(temp_batch, 0o600)
            with temp_batch.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(temp_batch, batch_path)
        for p, _, expected, before in attachments:
            _, _, actual, after = read_attachment(str(p))
            if expected != actual or before != after:
                raise ValueError('Attachment changed during upload')
        payload = {'request_id': request_id, 'direction': 'result', 'target': 'mac',
                   'text': text, 'blocks': [], 'files': refs}
        receipt = request(owner, 'POST', '/transfers', payload=payload)
        if not re.fullmatch(r'qs_[a-f0-9]{32}', str(receipt.get('id') or '')):
            raise ValueError('QuanSyn did not confirm a remote transfer ID')
        confirmed = request(owner, 'GET', '/transfers/' + receipt['id'])
        confirmed_refs = [item.get('artifact_id') for item in confirmed.get('files', [])]
        if (confirmed.get('id') != receipt['id'] or confirmed.get('direction') != 'result' or
                confirmed.get('target') != 'mac' or confirmed.get('text') != text or
                confirmed_refs != [item['artifact_id'] for item in refs]):
            raise ValueError('QuanSyn transfer readback did not match the published batch')
        temp = path.with_suffix('.tmp-' + secrets.token_hex(6))
        temp.write_text(json.dumps({'cursor': messages[-1]['id']}))
        os.chmod(temp, 0o600)
        with temp.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(state_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return {'success': True, 'noop': False, 'count': len(messages), 'skipped_count': skipped,
                'lossy': bool(skipped), 'result_id': receipt['id'], 'request_id': request_id,
                'receipt': f'已推送 {len(messages)} 条；永久跳过较早未推送消息 {skipped} 条。'}
