"""Serializable in-memory operation phases. No registry/filesystem/hardware writes."""
from __future__ import annotations
import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import uuid

PHASES = ('prepare', 'uninstall', 'scan', 'review', 'cleanup', 'complete', 'failed')
_NEXT = {'prepare': {'uninstall', 'failed'}, 'uninstall': {'scan', 'failed'},
         'scan': {'review', 'failed'}, 'review': {'cleanup', 'complete', 'failed'},
         'cleanup': {'complete', 'failed'}, 'complete': set(), 'failed': set()}


def _now():
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OperationSession:
    app_name: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    phase: str = 'prepare'
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    metadata: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.app_name, str) or not self.app_name.strip():
            raise ValueError('Application name required')
        if self.phase not in PHASES:
            raise ValueError('Unknown operation phase')
        if not isinstance(self.session_id, str) or not re.fullmatch(r'[0-9a-f]{32}', self.session_id):
            raise ValueError('Invalid operation session identifier')
        if not isinstance(self.metadata, dict) or not isinstance(self.history, list):
            raise ValueError('Invalid operation session metadata')
        json.dumps({'metadata': self.metadata, 'history': self.history}, allow_nan=False)
        self.metadata = copy.deepcopy(self.metadata)
        self.history = copy.deepcopy(self.history)
        if not self.history:
            self.history = [{'phase': self.phase, 'timestamp': self.created_at, 'note': ''}]

    def transition(self, phase: str, note: str = '', **metadata) -> dict:
        """Advance one phase, or fail from any active phase. Returns detached data."""
        with self._lock:
            if phase not in _NEXT[self.phase]:
                raise ValueError(f'Invalid operation transition: {self.phase} -> {phase}')
            json.dumps(metadata, allow_nan=False)
            detached = copy.deepcopy(metadata)
            self.phase = phase
            self.updated_at = _now()
            self.metadata.update(detached)
            self.history.append({'phase': phase, 'timestamp': self.updated_at, 'note': str(note)})
            return self.to_dict()

    def to_dict(self) -> dict:
        with self._lock:
            return copy.deepcopy({'session_id': self.session_id, 'app_name': self.app_name,
                                  'phase': self.phase, 'created_at': self.created_at,
                                  'updated_at': self.updated_at, 'metadata': self.metadata,
                                  'history': self.history})

    @classmethod
    def from_dict(cls, value: dict) -> 'OperationSession':
        if not isinstance(value, dict) or set(value) != {'session_id','app_name','phase','created_at','updated_at','metadata','history'}:
            raise ValueError('Invalid operation session data')
        if not isinstance(value['metadata'], dict) or not isinstance(value['history'], list):
            raise ValueError('Invalid operation session metadata')
        return cls(**copy.deepcopy(value))
