"""Journaled recovery vault. No deletion, cross-volume copy, ACL changes or SYSTEM.

File mutation is preceded by an atomic journal write. Journals have SHA-256 and
a per-vault HMAC, detecting edited JSON (not an attacker who controls the vault
and its secret key). Registry backup only exports; deletion remains the caller's
job. Calling restore on a registry record explicitly requests importing it.
"""
from __future__ import annotations

import copy
import ctypes
import errno
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import threading
from datetime import datetime, timezone
import uuid

from . import scanner


class RecoveryError(ValueError):
    """Unsafe path, invalid identifier or corrupt/untrusted recovery metadata."""


_ID = re.compile(r"^[0-9a-f]{32}$")
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_LOCK = threading.Lock()
MAX_ENTRIES = 10000
MAX_BYTES = 2 * 1024 ** 3
MAX_DEPTH = 64
MAX_MANIFEST = 16 * 1024 ** 2
_STATES = {'prepared', 'quarantined', 'quarantined_changed', 'verification_pending', 'backed_up', 'restoring', 'restored', 'failed'}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _normal(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _under(path, root):
    try:
        return os.path.commonpath([_normal(path), _normal(root)]) == _normal(root)
    except ValueError:
        return False


def _no_reparse(path):
    for node in (Path(path), *Path(path).parents):
        try:
            info = node.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RecoveryError('Symbolic links and reparse points are not accepted')


def _checked_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise RecoveryError('Invalid recovery identifier')
    return value


def _key(value):
    if not isinstance(value, str) or any(c in value for c in '\x00\r\n/[]'):
        raise RecoveryError('Invalid registry path')
    parts = value.strip().split('\\')
    aliases = {'HKCU': 'HKEY_CURRENT_USER', 'HKLM': 'HKEY_LOCAL_MACHINE',
               'HKEY_CURRENT_USER': 'HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE': 'HKEY_LOCAL_MACHINE'}
    hive = aliases.get(parts[0].upper())
    if not hive or len(parts) < 3 or parts[1].lower() != 'software':
        raise RecoveryError('Only application keys below HKCU/HKLM Software are accepted')
    if any(not p or p in ('.', '..') for p in parts):
        raise RecoveryError('Invalid registry components')
    shared = {'software', 'microsoft', 'windows', 'classes', 'tencent', 'google', 'mozilla', 'adobe',
              'uninstall', 'currentversion', 'wow6432node', 'policies', 'run', 'runonce'}
    if parts[-1].lower() in shared or any(p.lower() == 'policies' for p in parts):
        raise RecoveryError('Shared/policy registry roots cannot be removed')
    return '\\'.join([hive, *parts[1:]])


def _validate_reg(data, requested):
    if len(data) > MAX_MANIFEST or not data:
        raise RecoveryError('Empty or excessively large registry export')
    try:
        text = data.decode('utf-16') if data.startswith((b'\xff\xfe', b'\xfe\xff')) else data.decode('utf-8-sig')
    except UnicodeError as exc:
        raise RecoveryError('Invalid registry export encoding') from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() not in ('Windows Registry Editor Version 5.00', 'REGEDIT4'):
        raise RecoveryError('Not a registry export')
    requested = _key(requested).casefold()
    sections = 0
    for line in lines[1:]:
        value = line.strip()
        if value.startswith('['):
            if not value.endswith(']') or value.startswith('[-'):
                raise RecoveryError('Deletion or malformed registry section')
            actual = _key(value[1:-1]).casefold()
            if actual != requested and not actual.startswith(requested + '\\'):
                raise RecoveryError('Registry export contains an unrelated key')
            sections += 1
    if not sections:
        raise RecoveryError('Registry export has no application key')


class _FileTime(ctypes.Structure):
    _fields_ = [('low', ctypes.c_uint32), ('high', ctypes.c_uint32)]


class _WinInfo(ctypes.Structure):
    _fields_ = [('attributes', ctypes.c_uint32), ('creation', _FileTime),
                ('access', _FileTime), ('write', _FileTime), ('volume', ctypes.c_uint32),
                ('size_high', ctypes.c_uint32), ('size_low', ctypes.c_uint32),
                ('links', ctypes.c_uint32), ('index_high', ctypes.c_uint32), ('index_low', ctypes.c_uint32)]


class _WinHandle:
    def __init__(self, path, *, delete=False, parent=False):
        if os.name != 'nt':
            raise RecoveryError('Windows handle-bound recovery unavailable; source retained')
        self.handle = None
        self.api = api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        api.CreateFileW.restype = ctypes.c_void_p
        api.CloseHandle.argtypes = [ctypes.c_void_p]
        api.GetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.POINTER(_WinInfo)]
        api.SetFilePointerEx.argtypes = [ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint32]
        api.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
        api.SetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        access = 0x80 if parent else 0x80000000 | (0x10000 if delete else 0)
        sharing = 3 if parent else (1 if delete else 5)
        handle = api.CreateFileW(str(path), access, sharing, None, 3, 0x02200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle
        try:
            if self.info().attributes & 0x400:
                raise RecoveryError('Opened Windows object is a reparse point')
        except Exception:
            self.close()
            raise

    def info(self):
        value = _WinInfo()
        if not self.api.GetFileInformationByHandle(self.handle, ctypes.byref(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        return value

    def identity(self):
        value = self.info()
        return {'volume_serial': value.volume, 'file_id': f'{value.index_high:08x}{value.index_low:08x}',
                'kind': 'dir' if value.attributes & 0x10 else 'file'}

    def digest(self):
        before = self.info()
        size = before.size_low | before.size_high << 32
        if size > MAX_BYTES:
            raise RecoveryError('Recovery file exceeds bounded byte limit')
        if not self.api.SetFilePointerEx(self.handle, 0, None, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        digest, total = hashlib.sha256(), 0
        buffer, count = ctypes.create_string_buffer(128 * 1024), ctypes.c_uint32()
        while True:
            if not self.api.ReadFile(self.handle, buffer, len(buffer), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if not count.value:
                break
            total += count.value
            if total > size or total > MAX_BYTES:
                raise RecoveryError('Pinned file changed during hashing')
            digest.update(buffer.raw[:count.value])
        after = self.info()
        if total != size or (before.write.high, before.write.low, before.size_high, before.size_low) != (after.write.high, after.write.low, after.size_high, after.size_low):
            raise RecoveryError('Pinned file changed during hashing')
        return total, digest.hexdigest()

    def close(self):
        if self.handle is not None:
            self.api.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class _WindowsPinned:
    """Source identity stays open without write/delete sharing through the rename."""
    def __init__(self, path):
        self.path, self.parents, self.root = Path(path), [], None
        try:
            _no_reparse(self.path)
            for parent in reversed(self.path.parents):
                self.parents.append(_WinHandle(parent, parent=True))
            before = self.path.lstat()
            self.root = _WinHandle(self.path, delete=True)
            if int(self.root.identity()['file_id'], 16) != before.st_ino & ((1 << 64) - 1):
                raise RecoveryError('Source identity changed while opening its handle')
        except Exception:
            self.close()
            raise

    def fingerprint(self):
        rows, total, count, stack = [], 0, 0, [(self.path, '', 0)]
        while stack:
            node, relative, depth = stack.pop()
            count += 1
            if count > MAX_ENTRIES or depth > MAX_DEPTH:
                raise RecoveryError('Recovery tree exceeds bounded scan limit')
            _no_reparse(node)
            child = _WinHandle(node) if relative else None
            handle = child or self.root
            try:
                if handle.info().attributes & 0x10:
                    rows.append([relative, 'dir'])
                    with os.scandir(node) as children:
                        entries = []
                        for entry in children:
                            if count + len(stack) + len(entries) >= MAX_ENTRIES:
                                raise RecoveryError('Recovery tree exceeds bounded scan limit')
                            entries.append(entry)
                        entries.sort(key=lambda e: e.name)
                    for entry in reversed(entries):
                        stack.append((Path(entry.path), (relative + '/' + entry.name).lstrip('/'), depth + 1))
                else:
                    size, digest = handle.digest()
                    total += size
                    if total > MAX_BYTES:
                        raise RecoveryError('Recovery tree exceeds bounded byte limit')
                    rows.append([relative, 'file', size, digest])
            finally:
                if child:
                    child.close()
        return total, hashlib.sha256(_canonical(sorted(rows))).hexdigest()

    def probe(self):
        size, digest = self.fingerprint()
        return self.root.identity() | {'bytes': size, 'sha256': digest}

    def move_to(self, target):
        target = Path(target)
        _no_reparse(target)
        with _WinHandle(target.parent, parent=True) as parent:
            class Rename(ctypes.Structure):
                _fields_ = [('flags', ctypes.c_uint32), ('root', ctypes.c_void_p),
                            ('length', ctypes.c_uint32), ('name', ctypes.c_wchar * 1)]
            name = str(target).encode('utf-16-le')
            buffer = ctypes.create_string_buffer(max(ctypes.sizeof(Rename), Rename.name.offset + len(name) + 2))
            info = Rename.from_buffer(buffer)
            info.flags, info.root, info.length = 0, None, len(name)
            ctypes.memmove(ctypes.addressof(buffer) + Rename.name.offset, name, len(name))
            if not self.root.api.SetFileInformationByHandle(self.root.handle, 3, buffer, len(buffer)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.path = target

    def close(self):
        if self.root:
            self.root.close()
        for parent in reversed(self.parents):
            parent.close()
        self.parents = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _fingerprint(path):
    with _WindowsPinned(path) as pinned:
        return pinned.fingerprint()


class RecoveryStore:
    def __init__(self, root: Path | None = None):
        if root is None:
            root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'JiJianUninstall' / 'recovery'
        self.root = Path(os.path.abspath(os.fspath(root)))
        if not scanner.path_is_safe(str(self.root)):
            raise RecoveryError('Unsafe recovery root')
        _no_reparse(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        _no_reparse(self.root)
        with _LOCKS_LOCK:
            self._lock = _LOCKS.setdefault(_normal(self.root), threading.RLock())
        with self._lock:
            secret = self.root / '.vault-key'
            _no_reparse(secret)
            try:
                fd = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as out:
                    out.write(os.urandom(32))
                    out.flush()
                    os.fsync(out.fileno())
            if secret.stat().st_size != 32:
                raise RecoveryError('Invalid recovery store key')
            self._secret = secret.read_bytes()
            if len(self._secret) != 32:
                raise RecoveryError('Invalid recovery store key')

    def _session_dir(self, sid):
        _checked_id(sid)
        directory = self.root / sid
        _no_reparse(directory)
        if not directory.is_dir():
            raise RecoveryError('Recovery session does not exist')
        return directory

    def _write(self, sid, manifest):
        directory = self._session_dir(sid)
        payload = _canonical(manifest)
        envelope = {'schema': 1, 'payload': manifest, 'checksum': hashlib.sha256(payload).hexdigest(),
                    'signature': hmac.new(self._secret, payload, hashlib.sha256).hexdigest()}
        tmp = directory / ('.manifest-' + uuid.uuid4().hex + '.tmp')
        target = directory / 'manifest.json'
        _no_reparse(target)
        try:
            with tmp.open('xb') as stream:
                stream.write(_canonical(envelope))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, target)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _read(self, sid):
        path = self._session_dir(sid) / 'manifest.json'
        _no_reparse(path)
        if path.stat().st_size > MAX_MANIFEST:
            raise RecoveryError('Manifest too large')
        try:
            envelope = json.loads(path.read_text(encoding='utf-8'))
            manifest = envelope['payload']
            payload = _canonical(manifest)
            if (envelope.get('schema') != 1 or not isinstance(manifest, dict)
                    or not hmac.compare_digest(envelope['checksum'], hashlib.sha256(payload).hexdigest())
                    or not hmac.compare_digest(envelope['signature'], hmac.new(self._secret, payload, hashlib.sha256).hexdigest())):
                raise RecoveryError('Recovery manifest checksum/authentication failed')
            if manifest.get('session_id') != sid or not isinstance(manifest.get('items'), list):
                raise RecoveryError('Invalid session manifest')
            if len(manifest['items']) > MAX_ENTRIES:
                raise RecoveryError('Too many recovery records')
            seen = set()
            for record in manifest['items']:
                ident = _checked_id(record['item_id'])
                if ident in seen or record['status'] not in _STATES:
                    raise RecoveryError('Duplicate item or invalid status')
                seen.add(ident)
                if record['kind'] not in ('file', 'dir', 'registry'):
                    raise RecoveryError('Unknown recovery item kind')
                if (not isinstance(record.get('bytes'), int) or record['bytes'] < 0
                        or not isinstance(record.get('timestamp'), str)
                        or record.get('app_name') != manifest.get('app_name')
                        or not isinstance(record.get('content_sha256'), str)
                        or (record['content_sha256'] and not re.fullmatch(r'[0-9a-f]{64}', record['content_sha256']))):
                    raise RecoveryError('Invalid recovery record fields')
                expected = f'registry/{ident}.reg' if record['kind'] == 'registry' else f'payload/{ident}'
                if record['stored_path'] != expected:
                    raise RecoveryError('Recovery path traversal or unexpected payload')
                if record['kind'] == 'registry':
                    _key(record['original_path'])
                else:
                    self._source(record['original_path'], require_exists=False)
            return manifest
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            if isinstance(exc, RecoveryError):
                raise
            raise RecoveryError('Malformed recovery manifest') from exc

    def _source(self, path, require_exists=True):
        path = Path(os.fspath(path))
        if (not path.is_absolute() or str(path).startswith(('\\\\', '//'))
                or any(c in str(path) for c in '\x00\r\n')
                or ':' in os.path.splitdrive(str(path))[1]
                or not scanner.path_is_safe(str(path))):
            raise RecoveryError('Protected/shared/relative source path refused')
        _no_reparse(path)
        if _under(path, self.root) or _under(self.root, path):
            raise RecoveryError('Cannot quarantine the recovery vault or its ancestor')
        if require_exists and not path.exists():
            raise FileNotFoundError(str(path))
        return path

    def _stored(self, sid, record):
        directory = self._session_dir(sid)
        path = directory / record['stored_path']
        if not _under(path, directory) or path == directory:
            raise RecoveryError('Payload escapes the recovery session')
        _no_reparse(path)
        return path

    @staticmethod
    def _record(app, original, kind):
        ident = uuid.uuid4().hex
        return {'item_id': ident, 'original_path': str(original), 'kind': kind,
                'stored_path': f'registry/{ident}.reg' if kind == 'registry' else f'payload/{ident}',
                'bytes': 0, 'timestamp': _now(), 'app_name': app, 'status': 'prepared',
                'content_sha256': '', 'error': ''}

    @staticmethod
    def _failure(path, exc):
        return {'status': 'failed', 'original_path': str(path), 'error': f'{type(exc).__name__}: {exc}'}

    def create_session(self, app_name) -> str:
        if not isinstance(app_name, str) or not app_name.strip() or len(app_name) > 512:
            raise RecoveryError('A nonempty application name is required')
        with self._lock:
            sid = uuid.uuid4().hex
            directory = self.root / sid
            _no_reparse(self.root)
            directory.mkdir()
            (directory / 'payload').mkdir()
            (directory / 'registry').mkdir()
            self._write(sid, {'session_id': sid, 'app_name': app_name, 'timestamp': _now(), 'items': []})
            return sid

    def probe_identity(self, path) -> dict:
        """Read-only stable root ID + handle-hashed content; raises on uncertainty."""
        with self._lock:
            source = self._source(path)
            with _WindowsPinned(source) as pinned:
                return pinned.probe()

    def quarantine_path(self, session_id, path, expected_identity=None) -> dict:
        with self._lock:
            manifest = self._read(session_id)
            record, moved, verified = None, False, False
            try:
                source = self._source(path)
                if source.stat().st_dev != self.root.stat().st_dev:
                    raise OSError(errno.EXDEV, 'Cross-volume quarantine refused; source retained')
                with _WindowsPinned(source) as pinned:
                    identity = pinned.probe()
                    if expected_identity is not None and identity != expected_identity:
                        raise RecoveryError('Source differs from the scan-time approved identity/content')
                    size, digest = identity['bytes'], identity['sha256']
                    record = self._record(manifest['app_name'], source, identity['kind'])
                    record.update(bytes=size, content_sha256=digest, reviewed_identity=copy.deepcopy(identity))
                    manifest['items'].append(record)
                    self._write(session_id, manifest)
                    stored = self._stored(session_id, record)
                    if os.path.lexists(stored):
                        raise RecoveryError('Unexpected occupied quarantine destination')
                    if pinned.probe() != identity:
                        raise RecoveryError('Source changed after preparing the journal')
                    self._source(source)
                    pinned.move_to(stored)  # Object-bound FileRenameInfo, ReplaceIfExists=False.
                    moved = True
                    try:
                        actual = pinned.probe()
                    except (OSError, RecoveryError) as verification_error:
                        try:
                            self._source(source, require_exists=False)
                            pinned.move_to(source)
                            moved = False
                        except (OSError, RecoveryError) as rollback_error:
                            record.update(verification_pending=True, needs_review=True)
                            raise RecoveryError(f'Post-move verification failed; payload preserved for manual review; rollback refused: {rollback_error}') from verification_error
                        raise RecoveryError('Post-move verification failed; pinned object returned without overwrite') from verification_error
                    verified = True
                    changed = actual != identity
                    record.update(bytes=actual['bytes'], content_sha256=actual['sha256'],
                                  status='quarantined_changed' if changed else 'quarantined',
                                  needs_review=changed,
                                  error='Descendant content changed during move; preserved for review' if changed else '')
                    try:
                        self._write(session_id, manifest)
                    except OSError as journal_error:
                        try:
                            self._source(source, require_exists=False)
                            pinned.move_to(source)
                            moved = False
                        except (OSError, RecoveryError) as rollback_error:
                            record.update(verification_pending=True, needs_review=True, recovery_path=str(stored))
                            raise RecoveryError(f'Final journal write failed; payload preserved at {stored}; rollback refused: {rollback_error}') from journal_error
                        raise RecoveryError('Final journal write failed; pinned object returned without overwrite') from journal_error
                return copy.deepcopy(record)
            except (OSError, RecoveryError) as exc:
                if record is None:
                    return self._failure(path, exc)
                # Any exception after mutation is pending, never successful.
                record.update(status='verification_pending' if moved else 'failed',
                              verification_pending=moved, needs_review=moved,
                              recovery_path=str(self.root / session_id / record['stored_path']) if moved else '',
                              error=f'{type(exc).__name__}: {exc}')
                try:
                    self._write(session_id, manifest)
                except OSError:
                    pass
                return copy.deepcopy(record)

    def backup_registry(self, session_id, key) -> dict:
        with self._lock:
            manifest = self._read(session_id)
            record = None
            try:
                requested = _key(key)
                record = self._record(manifest['app_name'], requested, 'registry')
                manifest['items'].append(record)
                self._write(session_id, manifest)
                path = self._stored(session_id, record)
                result = subprocess.run([self._reg_exe(), 'export', requested, str(path), '/y'],
                                        capture_output=True, timeout=90,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode != 0:
                    raise RecoveryError(f'Registry export failed ({result.returncode}); do not delete key')
                _no_reparse(path)
                if not path.is_file() or path.stat().st_size > MAX_MANIFEST:
                    raise RecoveryError('Registry export missing or too large')
                data = path.read_bytes()
                _validate_reg(data, requested)
                record.update(status='backed_up', bytes=len(data), content_sha256=hashlib.sha256(data).hexdigest())
                self._write(session_id, manifest)
                return copy.deepcopy(record)
            except (OSError, RecoveryError, subprocess.SubprocessError) as exc:
                if record is None:
                    return self._failure(key, exc)
                record.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                self._write(session_id, manifest)
                return copy.deepcopy(record)

    @staticmethod
    def _reg_exe():
        return str(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'reg.exe')

    def list_sessions(self) -> list[dict]:
        with self._lock:
            _no_reparse(self.root)
            sessions = []
            for directory in sorted(self.root.iterdir()):
                if not _ID.fullmatch(directory.name):
                    continue
                try:
                    manifest = self._read(directory.name)
                    sessions.append({k: copy.deepcopy(v) for k, v in manifest.items() if k != 'items'} |
                                    {'item_count': len(manifest['items']),
                                     'recoverable_count': sum(i['status'] in ('prepared','quarantined','quarantined_changed','verification_pending','backed_up','restoring') for i in manifest['items'])})
                except (RecoveryError, OSError) as exc:
                    sessions.append({'session_id': directory.name, 'status': 'invalid', 'error': str(exc)})
            return sorted(sessions, key=lambda s: s.get('timestamp', ''), reverse=True)

    def items(self, session_id) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._read(session_id)['items'])

    def restore(self, session_id, item_id, allow_changed=False) -> dict:
        """Explicit restore. Registry imports may replace values; files never overwrite.

        Interrupted records whose content was not durably verified cannot pass the
        stored checksum. ``allow_changed=True`` is the caller's explicit consent to
        re-measure the preserved payload, journal what is actually stored, and then
        restore it. It is never used as an automatic fallback.
        """
        with self._lock:
            manifest = self._read(session_id)
            _checked_id(item_id)
            record = next((r for r in manifest['items'] if r['item_id'] == item_id), None)
            if record is None:
                raise RecoveryError('Recovery item does not exist')
            if record['status'] == 'restored':
                return copy.deepcopy(record)
            if record['status'] not in ('prepared', 'quarantined', 'quarantined_changed',
                                        'verification_pending', 'backed_up', 'restoring'):
                return copy.deepcopy(record) | {'status': 'failed', 'error': 'No restorable payload'}
            previous, mutated = record['status'], False
            try:
                stored = self._stored(session_id, record)
                if record['kind'] == 'registry':
                    if not stored.is_file() or stored.stat().st_size > MAX_MANIFEST:
                        raise RecoveryError('Registry backup missing or too large')
                    data = stored.read_bytes()
                    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), record['content_sha256']):
                        raise RecoveryError('Registry backup checksum mismatch')
                    _validate_reg(data, record['original_path'])
                    record['status'] = 'restoring'
                    self._write(session_id, manifest)
                    result = subprocess.run([self._reg_exe(), 'import', str(stored)], capture_output=True,
                                            timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if result.returncode != 0:
                        raise RecoveryError(f'Registry import failed ({result.returncode})')
                    mutated = True
                else:
                    original = self._source(record['original_path'], require_exists=False)
                    if os.path.lexists(original):
                        return copy.deepcopy(record) | {'status': 'conflict', 'error': 'Destination exists; nothing overwritten'}
                    if not original.parent.is_dir():
                        raise RecoveryError('Restore parent missing; create explicitly before retrying')
                    if original.parent.stat().st_dev != stored.stat().st_dev:
                        raise OSError(errno.EXDEV, 'Cross-volume restoration refused')
                    with _WindowsPinned(stored) as pinned:
                        size, digest = pinned.fingerprint()
                        matches = size == record['bytes'] and hmac.compare_digest(digest, record['content_sha256'])
                        if not matches:
                            if not allow_changed:
                                raise RecoveryError('Quarantine payload checksum mismatch; explicit review consent required')
                            # Re-measure what is actually preserved and make that the
                            # durable record before any restore mutation. Findings may
                            # reference a payload path, so the regex cannot be relaxed.
                            current = pinned.probe()
                            record.update(bytes=current['bytes'], content_sha256=current['sha256'],
                                          status='quarantined_changed', needs_review=False,
                                          reviewed_at=_now(),
                                          error='Payload re-measured under explicit user consent before restore')
                            self._write(session_id, manifest)
                        record['status'] = 'restoring'
                        self._write(session_id, manifest)
                        self._source(original, require_exists=False)
                        pinned.move_to(original)
                        mutated = True
                record.update(status='restored', restored_at=_now(), error='')
                self._write(session_id, manifest)
                return copy.deepcopy(record)
            except (OSError, RecoveryError, subprocess.SubprocessError) as exc:
                record.update(status='restored' if mutated else previous, error=f'{type(exc).__name__}: {exc}')
                try:
                    self._write(session_id, manifest)
                except OSError:
                    pass
                return copy.deepcopy(record) | {'status': 'restored' if mutated else 'failed'}
