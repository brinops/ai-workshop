"""Intentionally buggy booking service for the Jira and Slack workshop."""

from collections.abc import Awaitable, Callable
from typing import Literal

BookingStatus = Literal["confirmed", "waitlisted"]


class BookingService:
    def __init__(self, seats: int, check_eligibility: Callable[[str], Awaitable[None]]) -> None:
        self.remaining_seats = seats
        self.confirmed: list[str] = []
        self.waitlist: list[str] = []
        self._check_eligibility = check_eligibility

    async def reserve(self, user_id: str) -> BookingStatus:
        available = self.remaining_seats
        await self._check_eligibility(user_id)

        if available > 0:
            self.remaining_seats -= 1
            self.confirmed.append(user_id)
            return "confirmed"

        self.waitlist.append(user_id)
        return "waitlisted"
