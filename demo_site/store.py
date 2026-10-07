"""In-memory submission store with idempotent writes."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import dataclass, field

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass
class Submission:
    reference: str
    username: str
    payload: dict


@dataclass
class Store:
    by_key: dict[str, Submission] = field(default_factory=dict)
    by_ref: dict[str, Submission] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @staticmethod
    def key(username: str, payload: dict) -> str:
        canon = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(f"{username}\n{canon}".encode()).hexdigest()

    def save(self, username: str, payload: dict) -> tuple[Submission, bool]:
        """Return (submission, created). A repeat of the same payload by the same
        user returns the existing record, so a retried submit never duplicates."""
        k = self.key(username, payload)
        with self.lock:
            existing = self.by_key.get(k)
            if existing:
                return existing, False
            ref = "WFB-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))
            sub = Submission(ref, username, payload)
            self.by_key[k] = sub
            self.by_ref[ref] = sub
            return sub, True

    def get(self, reference: str) -> Submission | None:
        return self.by_ref.get(reference)

    def __len__(self) -> int:
        return len(self.by_ref)
