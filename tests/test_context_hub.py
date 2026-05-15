"""Context Hub integration tests (v2.3.0)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_prompt_create_and_get_active(async_client: AsyncClient):
    r = await async_client.post("/prompts/", json={
        "name": "executor_system",
        "content": "You are an executor. Task: {{task}}.",
        "description": "Default executor system prompt",
    })
    assert r.status_code == 201
    p = r.json()
    assert p["version"] == 1
    assert p["is_active"] is True
    assert "task" in p["variables"]
    assert p["integrity_hash"] is not None

    r2 = await async_client.get("/prompts/executor_system")
    assert r2.status_code == 200
    assert r2.json()["version"] == 1


@pytest.mark.asyncio
async def test_prompt_versioning(async_client: AsyncClient):
    await async_client.post("/prompts/", json={"name": "x", "content": "v1"})
    await async_client.post("/prompts/", json={"name": "x", "content": "v2"})
    versions = (await async_client.get("/prompts/x/versions")).json()
    assert len(versions) == 2
    # Latest is active
    active = (await async_client.get("/prompts/x")).json()
    assert active["version"] == 2

    # Activate v1
    await async_client.post("/prompts/x/activate/1")
    active = (await async_client.get("/prompts/x")).json()
    assert active["version"] == 1


@pytest.mark.asyncio
async def test_skill_create_and_match(async_client: AsyncClient):
    r = await async_client.post("/skills/", json={
        "name": "pdf-extract",
        "description": "Extract text and tables from PDF files",
        "skill_md": "# PDF Extract\n\nUse pdfplumber for tables.",
        "bundled_files": {"scripts/extract.py": "import pdfplumber\n# ..."},
    })
    assert r.status_code == 201
    assert r.json()["trust_level"] == "privileged"
    assert r.json()["integrity_hash"] is not None

    # Semantic match
    r2 = await async_client.post("/skills/search", json={"query": "how do I read a PDF document"})
    assert r2.status_code == 200
    matches = r2.json()
    assert any(m["name"] == "pdf-extract" for m in matches)


@pytest.mark.asyncio
async def test_subagent_requires_prompt(async_client: AsyncClient):
    r = await async_client.post("/subagents/", json={
        "name": "lonely", "description": "no prompt"
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_context_load_assembles_all_four(async_client: AsyncClient):
    # Seed: prompt
    await async_client.post("/prompts/", json={
        "name": "executor_system", "content": "You are an executor."
    })
    # Seed: skill
    await async_client.post("/skills/", json={
        "name": "api-paginate", "description": "Paginate REST APIs",
        "skill_md": "# Paginate\n\nLoop until next_token is None.",
    })
    # Seed: subagent
    await async_client.post("/subagents/", json={
        "name": "reviewer", "description": "Reviews executor output",
        "system_prompt": "You are a reviewer.", "parent_agent_id": "executor",
    })
    # Seed: a memory
    await async_client.post("/memories/add", json={
        "content": "API returns 100 items per page, use page_token",
        "agent_id": "executor",
    })

    # Load context
    r = await async_client.post("/context/load", json={
        "agent_id": "executor",
        "query": "paginate the orders API",
        "token_budget": 4000,
    })
    assert r.status_code == 200
    body = r.json()
    kinds = {i["kind"] for i in body["items"]}
    assert "prompt" in kinds
    assert "memory" in kinds
    assert "skill" in kinds
    assert "subagent" in kinds
    assert body["integrity_all_verified"] is True
    assert sum(body["tokens_used"].values()) <= body["tokens_budget"]
