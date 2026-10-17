"""Regression guards preventing a missing mock from issuing a paid/live request."""

import asyncio

import httpx
import pytest


def test_unmocked_sync_upstream_is_blocked():
    with httpx.Client(trust_env=False) as client:
        with pytest.raises(
            pytest.fail.Exception, match="Live upstream HTTP is forbidden"
        ):
            client.get("https://api.github.com/repos/example/repo")


def test_unmocked_async_upstream_is_blocked():
    async def run():
        async with httpx.AsyncClient(trust_env=False) as client:
            with pytest.raises(
                pytest.fail.Exception, match="Live upstream HTTP is forbidden"
            ):
                await client.get("https://api.groq.com/openai/v1/models")

    asyncio.run(run())
