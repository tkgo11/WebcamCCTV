"""Optional, local-first feature adapters kept independent from capture."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from .config import ScheduleConfig


def schedule_active(
    config: ScheduleConfig, now: datetime | None = None, *, locked: bool = False
) -> bool:
    if not config.enabled:
        return True
    now = now or datetime.now().astimezone()
    if locked and not config.record_when_locked:
        return False
    current = now.hour * 60 + now.minute
    start_h, start_m = map(int, config.start.split(":"))
    end_h, end_m = map(int, config.end.split(":"))
    start, end = start_h * 60 + start_m, end_h * 60 + end_m
    if start == end:
        return now.weekday() in config.weekdays
    if start < end:
        return now.weekday() in config.weekdays and start <= current <= end
    if current >= start:
        return now.weekday() in config.weekdays
    return current <= end and (now.weekday() - 1) % 7 in config.weekdays


class SecretStore:
    """OS keyring facade; secrets are never serialized into application config."""

    service = "WebcamCCTV"

    def set(self, name: str, value: str) -> None:
        keyring = import_module("keyring")
        keyring.set_password(self.service, name, value)

    def get(self, name: str) -> str | None:
        keyring = import_module("keyring")
        return cast(str | None, keyring.get_password(self.service, name))

    def delete(self, name: str) -> None:
        keyring = import_module("keyring")
        keyring.delete_password(self.service, name)


@dataclass(frozen=True)
class Notification:
    kind: str
    message: str


class Notifier:
    def __init__(self, deliver: Callable[[Notification], None] | None = None) -> None:
        self.deliver = deliver or (lambda event: None)
        self._last: dict[str, float] = {}

    def send(self, event: Notification, now: float, cooldown: float = 30) -> bool:
        if now - self._last.get(event.kind, float("-inf")) < cooldown:
            return False
        self.deliver(event)
        self._last[event.kind] = now
        return True


def encrypt_archive(source: Path, destination: Path, key: bytes) -> None:
    """Encrypt a file with AES-GCM using a caller-supplied key from SecretStore."""
    AESGCM = import_module("cryptography.hazmat.primitives.ciphers.aead").AESGCM
    nonce = os.urandom(12)
    payload = AESGCM(key).encrypt(nonce, source.read_bytes(), source.name.encode())
    destination.write_bytes(b"WCCTV1" + nonce + payload)


def model_fingerprint(model: Path) -> str:
    digest = hashlib.sha256()
    with model.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def redact(value: object) -> object:
    sensitive = {"password", "secret", "token", "key", "credential"}
    if isinstance(value, dict):
        private_fields = {"camera", "device", "directory", "path", "ai_model", "sync_directory"}
        return {
            key: (
                "<redacted>"
                if key.casefold() in private_fields
                or any(word in key.casefold() for word in sensitive)
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def write_diagnostics(destination: Path, config: Any, status: dict[str, object]) -> Path:
    from dataclasses import asdict

    payload = {
        "schema": 1,
        "platform": platform.platform(),
        "config": redact(asdict(config)),
        "status": redact(status),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return destination
