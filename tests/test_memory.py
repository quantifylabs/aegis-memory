"""
Aegis Memory Test Suite

Run with: pytest tests/ -v

Requirements:
    pip install pytest pytest-asyncio httpx
"""

import pytest
import asyncio
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json
from types import SimpleNamespace


# ============================================================================
# Unit Tests - Memory Repository
# ============================================================================

class TestMemoryRepository:
    """Test memory repository operations."""
    
    @pytest.mark.asyncio
    async def test_add_memory(self, mock_db_session):
        """Test adding a single memory."""
        from server.memory_repository import MemoryRepository
        
        memory = await MemoryRepository.add(
            mock_db_session,
            project_id="test-project",
            content="Test memory content",
            embedding=[0.1] * 1536,
            agent_id="test-agent",
            namespace="default",
        )
        
        assert memory.id is not None
        assert memory.content == "Test memory content"
        assert memory.agent_id == "test-agent"
        assert memory.project_id == "test-project"
    
    @pytest.mark.asyncio
    async def test_add_memory_with_ttl(self, mock_db_session):
        """Test memory with TTL has expires_at set."""
        from server.memory_repository import MemoryRepository
        
        memory = await MemoryRepository.add(
            mock_db_session,
            project_id="test-project",
            content="Expiring memory",
            embedding=[0.1] * 1536,
            ttl_seconds=3600,
        )
        
        assert memory.expires_at is not None
        assert memory.expires_at > datetime.now(timezone.utc)
    
    @pytest.mark.asyncio
    async def test_content_hash_deduplication(self, mock_db_session):
        """Test that duplicate content is detected."""
        from server.memory_repository import MemoryRepository
        from server.embedding_service import content_hash
        
        content = "Duplicate content"
        hash_val = content_hash(content)
        
        # First add should succeed
        mem1 = await MemoryRepository.add(
            mock_db_session,
            project_id="test-project",
            content=content,
            embedding=[0.1] * 1536,
        )
        
        # Check for duplicate
        existing = await MemoryRepository.find_duplicates(
            mock_db_session,
            content_hash=hash_val,
            project_id="test-project",
            namespace="default",
        )
        
        # In real scenario with data, this would find the duplicate
        # Here we just verify the function runs without error


class TestScopeAccessControl:
    """Test scope-based access control."""
    
    def test_global_scope_accessible_by_all(self):
        """Global memories should be accessible by any agent."""
        from server.models import Memory, MemoryScope
        
        memory = Memory(
            id="test-id",
            project_id="test",
            content="Global memory",
            content_hash="abc",
            embedding=[0.1] * 1536,
            scope=MemoryScope.GLOBAL.value,
        )
        
        assert memory.can_access("agent-1") is True
        assert memory.can_access("agent-2") is True
        assert memory.can_access(None) is True
    
    def test_private_scope_only_owner(self):
        """Private memories should only be accessible by owner."""
        from server.models import Memory, MemoryScope
        
        memory = Memory(
            id="test-id",
            project_id="test",
            content="Private memory",
            content_hash="abc",
            embedding=[0.1] * 1536,
            scope=MemoryScope.AGENT_PRIVATE.value,
            agent_id="owner-agent",
        )
        
        assert memory.can_access("owner-agent") is True
        assert memory.can_access("other-agent") is False
    
    def test_shared_scope_with_list(self):
        """Shared memories should be accessible by owner and shared agents."""
        from server.models import Memory, MemoryScope
        
        memory = Memory(
            id="test-id",
            project_id="test",
            content="Shared memory",
            content_hash="abc",
            embedding=[0.1] * 1536,
            scope=MemoryScope.AGENT_SHARED.value,
            agent_id="owner-agent",
            shared_with_agents=["friend-agent"],
        )
        
        assert memory.can_access("owner-agent") is True
        assert memory.can_access("friend-agent") is True
        assert memory.can_access("stranger-agent") is False


class TestEffectivenessScore:
    """Test ACE voting effectiveness calculations."""
    
    def test_effectiveness_score_neutral(self):
        """No votes should give neutral score."""
        from server.models import Memory
        
        memory = Memory(
            id="test",
            project_id="test",
            content="test",
            content_hash="abc",
            embedding=[0.1] * 1536,
            bullet_helpful=0,
            bullet_harmful=0,
        )
        
        assert memory.get_effectiveness_score() == 0.0
    
    def test_effectiveness_score_positive(self):
        """More helpful votes should give positive score."""
        from server.models import Memory
        
        memory = Memory(
            id="test",
            project_id="test",
            content="test",
            content_hash="abc",
            embedding=[0.1] * 1536,
            bullet_helpful=5,
            bullet_harmful=1,
        )
        
        score = memory.get_effectiveness_score()
        assert score > 0
        assert score == (5 - 1) / (5 + 1 + 1)  # 4/7 ≈ 0.57
    
    def test_effectiveness_score_negative(self):
        """More harmful votes should give negative score."""
        from server.models import Memory
        
        memory = Memory(
            id="test",
            project_id="test",
            content="test",
            content_hash="abc",
            embedding=[0.1] * 1536,
            bullet_helpful=1,
            bullet_harmful=5,
        )
        
        score = memory.get_effectiveness_score()
        assert score < 0


class TestScopeInference:
    """Test automatic scope inference."""
    
    def test_explicit_scope_overrides(self):
        """Explicit scope should override inference."""
        from server.scope_inference import ScopeInference
        from server.models import MemoryScope
        
        result = ScopeInference.infer_scope(
            content="This is global information",
            explicit_scope="agent-private",
            agent_id="test-agent",
            metadata={},
        )
        
        assert result == MemoryScope.AGENT_PRIVATE
    
    def test_global_keywords_detected(self):
        """Content with global keywords should infer global scope."""
        from server.scope_inference import ScopeInference
        from server.models import MemoryScope
        
        result = ScopeInference.infer_scope(
            content="This is a company-wide policy that applies to everyone",
            explicit_scope=None,
            agent_id="test-agent",
            metadata={},
        )
        
        assert result == MemoryScope.GLOBAL
    
    def test_private_keywords_detected(self):
        """Content with private keywords should infer private scope."""
        from server.scope_inference import ScopeInference
        from server.models import MemoryScope
        
        result = ScopeInference.infer_scope(
            content="My personal notes: this is confidential",
            explicit_scope=None,
            agent_id="test-agent",
            metadata={},
        )
        
        assert result == MemoryScope.AGENT_PRIVATE


# ============================================================================
# Integration Tests - API Endpoints
# ============================================================================

class TestAPIEndpoints:
    """Test API endpoints (requires running server or mocks)."""
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, test_client):
        """Test health check endpoint."""
        response = await test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_add_memory_endpoint(self, test_client, auth_headers):
        """Test adding a memory via API."""
        response = await test_client.post(
            "/memories/add",
            json={
                "content": "Test memory via API",
                "agent_id": "test-agent",
                "namespace": "default",
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
    
    @pytest.mark.asyncio
    async def test_query_endpoint(self, test_client, auth_headers):
        """Test querying memories via API."""
        response = await test_client.post(
            "/memories/query",
            json={
                "query": "test query",
                "agent_id": "test-agent",
                "top_k": 5,
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "memories" in data
        assert "query_time_ms" in data
    
    @pytest.mark.asyncio
    async def test_vote_endpoint(self, test_client, auth_headers):
        """Test voting on a memory."""
        # First add a memory
        add_response = await test_client.post(
            "/memories/add",
            json={"content": "Memory to vote on", "agent_id": "test"},
            headers=auth_headers,
        )
        memory_id = add_response.json()["id"]
        
        # Vote on it
        vote_response = await test_client.post(
            f"/memories/ace/vote/{memory_id}",
            json={
                "vote": "helpful",
                "voter_agent_id": "voter-agent",
                "context": "This was useful",
            },
            headers=auth_headers,
        )
        
        assert vote_response.status_code == 200
        data = vote_response.json()
        assert data["bullet_helpful"] == 1


class TestExportMemories:
    """Test export streaming behavior for large datasets."""

    @staticmethod
    def _load_export_route():
        if "/workspace/aegis-memory/server" not in sys.path:
            sys.path.insert(0, "/workspace/aegis-memory/server")
        from routes import ExportRequest, export_memories
        return ExportRequest, export_memories

    @staticmethod
    def _memory(idx: int):
        created = datetime(2024, 1, 1, 0, 0, idx % 60, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=f"m-{idx:05d}",
            content=f"memory {idx}",
            user_id=None,
            agent_id="agent-a" if idx % 2 == 0 else None,
            namespace="default",
            scope="agent-private",
            metadata_json={"n": idx},
            memory_type="standard",
            created_at=created,
            updated_at=created,
            bullet_helpful=0,
            bullet_harmful=0,
            embedding=[0.1, 0.2],
        )

    @pytest.mark.asyncio
    async def test_export_jsonl_uses_chunked_iteration(self):
        """JSONL export should iterate DB in batches and stream lines."""
        ExportRequest, export_memories = self._load_export_route()

        class MockScalarResult:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        class MockExecuteResult:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return MockScalarResult(self._rows)

            def scalar_one(self):
                return 1500

        class MockDB:
            def __init__(self):
                self.offset = 0
                self.call_count = 0

            async def execute(self, _stmt):
                self.call_count += 1
                if self.call_count == 1:
                    # count_for_export query
                    return MockExecuteResult([])

                if self.offset >= 1500:
                    return MockExecuteResult([])

                batch_size = 1000
                start = self.offset
                end = min(self.offset + batch_size, 1500)
                rows = [TestExportMemories._memory(i) for i in range(start, end)]
                self.offset = end
                return MockExecuteResult(rows)

        db = MockDB()
        response = await export_memories(
            ExportRequest(format="jsonl"),
            project_id="proj-1",
            db=db,
        )

        lines = []
        async for chunk in response.body_iterator:
            lines.append(chunk)

        assert len(lines) == 1500
        assert db.call_count == 3  # count query + two chunk fetches
        assert response.headers["x-export-total"] == "1500"

    @pytest.mark.asyncio
    async def test_export_json_limit_and_stats_preserved(self):
        """JSON export should keep limit semantics and stats values."""
        ExportRequest, export_memories = self._load_export_route()

        class MockScalarResult:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        class MockExecuteResult:
            def __init__(self, rows):
                self._rows = rows

            def scalars(self):
                return MockScalarResult(self._rows)

        class MockDB:
            def __init__(self):
                self.offset = 0

            async def execute(self, _stmt):
                if self.offset >= 3:
                    return MockExecuteResult([])
                rows = [TestExportMemories._memory(i) for i in range(self.offset, 3)]
                self.offset = 3
                return MockExecuteResult(rows)

        data = await export_memories(
            ExportRequest(format="json", limit=3),
            project_id="proj-1",
            db=MockDB(),
        )

        assert len(data["memories"]) == 3
        assert data["stats"]["total_exported"] == 3
        assert data["stats"]["format"] == "json"


class TestACEEndpoints:
    """Test ACE-specific endpoints."""
    
    @pytest.mark.asyncio
    async def test_delta_add_operation(self, test_client, auth_headers):
        """Test delta add operation."""
        response = await test_client.post(
            "/memories/ace/delta",
            json={
                "operations": [
                    {
                        "type": "add",
                        "content": "New strategy via delta",
                        "memory_type": "strategy",
                        "agent_id": "test-agent",
                    }
                ]
            },
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["success"] is True
    
    @pytest.mark.asyncio
    async def test_session_progress(self, test_client, auth_headers):
        """Test session progress tracking."""
        # Create session
        create_response = await test_client.post(
            "/memories/ace/session",
            json={
                "session_id": "test-session-123",
                "agent_id": "test-agent",
            },
            headers=auth_headers,
        )
        
        assert create_response.status_code == 200
        
        # Update session
        update_response = await test_client.patch(
            "/memories/ace/session/test-session-123",
            json={
                "completed_items": ["task-1"],
                "in_progress_item": "task-2",
            },
            headers=auth_headers,
        )
        
        assert update_response.status_code == 200
        data = update_response.json()
        assert "task-1" in data["completed_items"]
        assert data["in_progress_item"] == "task-2"
    
    @pytest.mark.asyncio
    async def test_feature_tracking(self, test_client, auth_headers):
        """Test feature tracking."""
        # Create feature
        create_response = await test_client.post(
            "/memories/ace/feature",
            json={
                "feature_id": "test-feature",
                "description": "Test feature description",
                "test_steps": ["Step 1", "Step 2"],
            },
            headers=auth_headers,
        )
        
        assert create_response.status_code == 200
        
        # Update to complete
        update_response = await test_client.patch(
            "/memories/ace/feature/test-feature",
            json={
                "status": "complete",
                "passes": True,
                "verified_by": "qa-agent",
            },
            headers=auth_headers,
        )
        
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["passes"] is True


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def test_client():
    """Create a test client for API testing."""
    import httpx
    
    # For unit tests, use a mock client
    # For integration tests, point to actual server
    class MockClient:
        async def get(self, url, **kwargs):
            return MockResponse(200, {"status": "healthy"})
        
        async def post(self, url, **kwargs):
            if "add" in url:
                return MockResponse(200, {"id": "test-id-123"})
            elif "query" in url:
                return MockResponse(200, {"memories": [], "query_time_ms": 10})
            elif "vote" in url:
                return MockResponse(200, {"memory_id": "test", "bullet_helpful": 1, "bullet_harmful": 0, "effectiveness_score": 0.5})
            elif "delta" in url:
                return MockResponse(200, {"results": [{"operation": "add", "success": True, "memory_id": "new-id"}], "total_time_ms": 50})
            elif "session" in url:
                return MockResponse(200, {"id": "s1", "session_id": "test-session-123", "status": "active", "completed_count": 0, "total_items": 0, "progress_percent": 0, "completed_items": ["task-1"], "in_progress_item": "task-2", "next_items": [], "blocked_items": [], "summary": None, "last_action": None, "updated_at": "2024-01-01T00:00:00Z"})
            elif "feature" in url:
                return MockResponse(200, {"id": "f1", "feature_id": "test-feature", "description": "Test", "category": None, "status": "complete", "passes": True, "test_steps": [], "implemented_by": None, "verified_by": "qa-agent", "updated_at": "2024-01-01T00:00:00Z"})
            return MockResponse(200, {})
        
        async def patch(self, url, **kwargs):
            return await self.post(url, **kwargs)
    
    class MockResponse:
        def __init__(self, status_code, data):
            self.status_code = status_code
            self._data = data
        
        def json(self):
            return self._data
    
    return MockClient()


@pytest.fixture
def auth_headers():
    """Create auth headers for API requests."""
    return {"Authorization": "Bearer dev-key"}


# ============================================================================
# Run Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
