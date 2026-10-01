import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Message:
    role: str  # 'user', 'assistant', 'tool', 'system'
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    session_id: str
    profile_id: str
    messages: list[Message] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class StateManager:
    """
    Handles persistent state for O.L.I.V.I.A.
    Inspired by Hermes' state_dbfile and state_sessions.
    """

    def __init__(self, storage_path: str = "C:/Users/mathe/AppData/Local/olivia/state.db"):
        self.storage_path = storage_path
        # In a full implementation, this would initialize a SQLite connection
        self.sessions: dict[str, Session] = {}

    def create_session(self, profile_id: str = "default") -> Session:
        session_id = str(uuid.uuid4())
        session = Session(session_id=session_id, profile_id=profile_id)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def add_message(self, session_id: str, role: str, content: str, metadata: dict | None = None):
        if session_id in self.sessions:
            msg = Message(role=role, content=content, metadata=metadata or {})
            self.sessions[session_id].messages.append(msg)
            return msg
        return None

    def save_state(self):
        # Placeholder for actual DB write
        pass

    def load_state(self):
        # Placeholder for actual DB read
        pass
