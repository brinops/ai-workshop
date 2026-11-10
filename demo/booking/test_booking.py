"""Run with --runxfail to see the known booking failure."""

import asyncio

import pytest

from demo.booking.service import BookingService


def test_sequential_bookings_use_the_waitlist() -> None:
    async def check_eligibility(user_id: str) -> None:
        pass

    async def book() -> tuple[str, str]:
        service = BookingService(seats=1, check_eligibility=check_eligibility)
        return await service.reserve("user-1"), await service.reserve("user-2")

    assert asyncio.run(book()) == ("confirmed", "waitlisted")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Both reservations act on the same seat snapshot.")
def test_last_seat_is_confirmed_only_once() -> None:
    async def book_concurrently() -> tuple[str, str]:
        entered = {user: asyncio.Event() for user in ("user-1", "user-2")}
        release = {user: asyncio.Event() for user in entered}

        async def check_eligibility(user_id: str) -> None:
            entered[user_id].set()
            await release[user_id].wait()

        service = BookingService(seats=1, check_eligibility=check_eligibility)
        async with asyncio.timeout(5), asyncio.TaskGroup() as group:
            first = group.create_task(service.reserve("user-1"))
            second = group.create_task(service.reserve("user-2"))
            # Both calls read the seat count before either may confirm.
            await entered["user-1"].wait()
            await entered["user-2"].wait()
            release["user-1"].set()
            first_status = await first
            release["user-2"].set()
            return first_status, await second

    assert asyncio.run(book_concurrently()) == ("confirmed", "waitlisted")
