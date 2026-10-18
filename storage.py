"""Сховище FSM у SQLite: стани діалогів (очікування квитанції, тексту вакансії тощо)
не втрачаються при перезапуску бота."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from database.models import FsmState, async_session


class SQLiteStorage(BaseStorage):
    @staticmethod
    def _k(key: StorageKey) -> str:
        return f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.thread_id}:{key.destiny}"

    async def set_state(self, key: StorageKey, state: Optional[State | str] = None) -> None:
        value = state.state if isinstance(state, State) else state
        async with async_session() as session:
            row = await session.get(FsmState, self._k(key))
            if row is None:
                if value is None:
                    return
                session.add(FsmState(key=self._k(key), state=value, data="{}"))
            else:
                row.state = value
                if value is None and row.data in ("", "{}"):
                    await session.delete(row)
            await session.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        async with async_session() as session:
            row = await session.get(FsmState, self._k(key))
            return row.state if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        async with async_session() as session:
            row = await session.get(FsmState, self._k(key))
            if row is None:
                if not data:
                    return
                session.add(FsmState(key=self._k(key), state=None, data=payload))
            else:
                row.data = payload
                if not data and row.state is None:
                    await session.delete(row)
            await session.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        async with async_session() as session:
            row = await session.get(FsmState, self._k(key))
            if row is None or not row.data:
                return {}
            try:
                return json.loads(row.data)
            except json.JSONDecodeError:
                return {}

    async def close(self) -> None:
        return None
