from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


@dataclass
class ChatRecord:
    chat_id: int
    title: str
    chat_type: str
    enabled: bool = True
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def touch(self, title: str | None = None, chat_type: str | None = None) -> None:
        if title:
            self.title = title
        if chat_type:
            self.chat_type = chat_type
        self.updated_at = datetime.now(timezone.utc).isoformat()


class ChatStore:
    """Thread-safe JSON storage for chats the bot is part of."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: Dict[int, ChatRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = []
        for entry in raw:
            record = ChatRecord(**entry)
            self._records[record.chat_id] = record

    def _flush(self) -> None:
        payload = [asdict(record) for record in self._records.values()]
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def upsert(self, *, chat_id: int, title: str, chat_type: str) -> ChatRecord:
        with self._lock:
            record = self._records.get(chat_id)
            if record is None:
                record = ChatRecord(chat_id=chat_id, title=title, chat_type=chat_type)
                self._records[chat_id] = record
            else:
                record.touch(title, chat_type)
            self._flush()
            return record

    def remove(self, chat_id: int) -> None:
        with self._lock:
            if chat_id in self._records:
                self._records.pop(chat_id)
                self._flush()

    def set_enabled(self, chat_id: int, enabled: bool) -> bool:
        with self._lock:
            record = self._records.get(chat_id)
            if not record:
                return False
            record.enabled = enabled
            record.touch()
            self._flush()
            return True

    def list_all(self) -> List[ChatRecord]:
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.title.lower())

    def enabled_chat_ids(self) -> List[int]:
        with self._lock:
            return [record.chat_id for record in self._records.values() if record.enabled]

    def get(self, chat_id: int) -> ChatRecord | None:
        with self._lock:
            return self._records.get(chat_id)
