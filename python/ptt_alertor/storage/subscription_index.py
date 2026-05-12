from __future__ import annotations

from collections import defaultdict

from ..models import User
from .user_repo import UserRepo


class SubscriptionIndex:
    """Reverse-lookup table: board -> set of channel IDs subscribed (keyword/author).

    Built from UserRepo on startup, kept in sync after every user mutation.
    """

    def __init__(self, user_repo: UserRepo) -> None:
        self.user_repo = user_repo
        self._by_board: dict[str, set[str]] = defaultdict(set)

    def rebuild(self) -> None:
        self._by_board.clear()
        for u in self.user_repo.iter_active():
            for s in u.subscribes:
                if not s.board:
                    continue
                if s.keywords or s.authors:
                    self._by_board[s.board.lower()].add(u.channel_id)

    def update_for_user(self, user: User) -> None:
        for boards in self._by_board.values():
            boards.discard(user.channel_id)
        if not user.enable or not user.channel_id:
            return
        for s in user.subscribes:
            if s.board and (s.keywords or s.authors):
                self._by_board[s.board.lower()].add(user.channel_id)

    def boards(self) -> list[str]:
        return [b for b, channels in self._by_board.items() if channels]

    def subscribers(self, board: str) -> set[str]:
        return set(self._by_board.get(board.lower(), set()))
