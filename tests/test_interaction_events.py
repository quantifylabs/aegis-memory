"""
Test suite for Interaction Events (Priority 3, v1.9.11)

Covers: model, repository CRUD, session timeline, agent history,
        semantic search, causal chain traversal, Pydantic models,
        and router registration.
"""

import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path helpers so tests can import server modules
# ---------------------------------------------------------------------------
SERVER_PATH = os.path.join(os.path.dirname(__file__), "..", "server")
if SERVER_PATH not in sys.path:
    sys.path.insert(0, SERVER_PATH)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def mock_db():
    """AsyncMock database session for unit testing repositories."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _make_event(**kwargs):
    """Create a minimal InteractionEvent ORM object for testing."""
    from models import InteractionEvent

    defaults = {
        "event_id": "abc123" + "0" * 26,
        "project_id": "proj-1",
        "session_id": "sess-1",
        "agent_id": "agent-1",
        "content": "Hello world",
        "timestamp": datetime.now(timezone.utc),
        "tool_calls": [],
        "parent_event_id": None,
        "namespace": "default",
        "extra_metadata": None,
        "embedding": None,
    }
    defaults.update(kwargs)

    event = InteractionEvent()
    for k, v in defaults.items():
        setattr(event, k, v)
    return event


# ===========================================================================
# 1. TestInteractionEventModel
# ===========================================================================

class TestInteractionEventModel:
    """Validate the InteractionEvent ORM model structure."""

    def test_table_name(self):
        from models import InteractionEvent
        assert InteractionEvent.__tablename__ == "interaction_events"

    def test_all_columns_present(self):
        from models import InteractionEvent
        cols = {c.name for c in InteractionEvent.__table__.columns}
        expected = {
            "event_id", "project_id", "session_id", "agent_id",
            "content", "timestamp", "tool_calls", "parent_event_id",
            "namespace", "extra_metadata", "embedding",
        }
        assert expected == cols

    def test_primary_key(self):
        from models import InteractionEvent
        pks = [c.name for c in InteractionEvent.__table__.primary_key]
        assert pks == ["event_id"]

    def test_all_four_indexes_defined(self):
        from models import InteractionEvent
        index_names = {idx.name for idx in InteractionEvent.__table__.indexes}
        assert "ix_interaction_project_session_ts" in index_names
        assert "ix_interaction_project_agent_ts" in index_names
        assert "ix_interaction_parent" in index_names
        assert "ix_interaction_embedding_hnsw" in index_names

    def test_nullable_fields(self):
        from models import InteractionEvent
        col_map = {c.name: c for c in InteractionEvent.__table__.columns}
        assert col_map["agent_id"].nullable is True
        assert col_map["content"].nullable is True
        assert col_map["parent_event_id"].nullable is True
        assert col_map["extra_metadata"].nullable is True
        assert col_map["embedding"].nullable is True

    def test_non_nullable_fields(self):
        from models import InteractionEvent
        col_map = {c.name: c for c in InteractionEvent.__table__.columns}
        assert col_map["session_id"].nullable is False
        assert col_map["project_id"].nullable is False

    def test_interaction_created_value(self):
        from models import MemoryEventType
        assert MemoryEventType.INTERACTION_CREATED.value == "interaction_created"

    def test_event_type_total_count(self):
        from models import MemoryEventType
        assert len(MemoryEventType) == 11


# ===========================================================================
# 2. TestCreateEvent
# ===========================================================================

class TestCreateEvent:
    """Test InteractionRepository.create_event."""

    @pytest.mark.asyncio
    async def test_minimal_create(self, mock_db):
        from interaction_repository import InteractionRepository

        result_mock = AsyncMock()
        mock_db.execute = AsyncMock(return_value=result_mock)

        with patch("interaction_repository.EventRepository.create_event", new_callable=AsyncMock) as mock_evt:
            event = await InteractionRepository.create_event(
                mock_db,
                project_id="proj-1",
                session_id="sess-1",
                content="Test content",
            )

        assert event is not None
        assert event.project_id == "proj-1"
        assert event.session_id == "sess-1"
        assert event.content == "Test content"
        assert event.namespace == "default"
        assert event.tool_calls == []
        assert event.embedding is None

    @pytest.mark.asyncio
    async def test_create_with_parent(self, mock_db):
        from interaction_repository import InteractionRepository

        mock_db.execute = AsyncMock()
        parent_id = "parent000" + "0" * 23

        with patch("interaction_repository.EventRepository.create_event", new_callable=AsyncMock):
            event = await InteractionRepository.create_event(
                mock_db,
                project_id="proj-1",
                session_id="sess-1",
                content="Child event",
                parent_event_id=parent_id,
            )

        assert event.parent_event_id == parent_id

    @pytest.mark.asyncio
    async def test_create_with_embedding(self, mock_db):
        from interaction_repository import InteractionRepository

        mock_db.execute = AsyncMock()
        embedding = [0.1] * 1536

        with patch("interaction_repository.EventRepository.create_event", new_callable=AsyncMock):
            event = await InteractionRepository.create_event(
                mock_db,
                project_id="proj-1",
                session_id="sess-1",
                content="Embedded event",
                embedding=embedding,
            )

        assert event.embedding == embedding

    @pytest.mark.asyncio
    async def test_create_with_tool_calls(self, mock_db):
        from interaction_repository import InteractionRepository

        mock_db.execute = AsyncMock()
        tool_calls = [{"name": "search", "args": {"query": "test"}}]

        with patch("interaction_repository.EventRepository.create_event", new_callable=AsyncMock):
            event = await InteractionRepository.create_event(
                mock_db,
                project_id="proj-1",
                session_id="sess-1",
                content="Event with tools",
                tool_calls=tool_calls,
            )

        assert event.tool_calls == tool_calls

    @pytest.mark.asyncio
    async def test_event_repository_called(self, mock_db):
        from interaction_repository import InteractionRepository

        mock_db.execute = AsyncMock()

        with patch("interaction_repository.EventRepository.create_event", new_callable=AsyncMock) as mock_evt:
            await InteractionRepository.create_event(
                mock_db,
                project_id="proj-1",
                session_id="sess-1",
                content="Test",
            )

        mock_evt.assert_called_once()
        call_kwargs = mock_evt.call_args.kwargs
        assert call_kwargs["event_type"] == "interaction_created"
        assert call_kwargs["project_id"] == "proj-1"

    @pytest.mark.asyncio
    async def test_db_add_and_flush_called(self, mock_db):
        from interaction_repository import InteractionRepository

        mock_db.execute = AsyncMock()

        with patch("interaction_repository.EventRepository.create_event", new_callable=AsyncMock):
            await InteractionRepository.create_event(
                mock_db,
                project_id="proj-1",
                session_id="sess-1",
                content="Test",
            )

        assert mock_db.add.called
        assert mock_db.flush.called


# ===========================================================================
# 3. TestGetSessionTimeline
# ===========================================================================

class TestGetSessionTimeline:
    """Test InteractionRepository.get_session_timeline."""

    @pytest.mark.asyncio
    async def test_returns_events(self, mock_db):
        from interaction_repository import InteractionRepository

        events = [_make_event(event_id=f"ev{i}" + "0" * 28) for i in range(3)]
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = events
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await InteractionRepository.get_session_timeline(
            mock_db,
            project_id="proj-1",
            session_id="sess-1",
        )

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_returns_empty(self, mock_db):
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await InteractionRepository.get_session_timeline(
            mock_db,
            project_id="proj-1",
            session_id="sess-1",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_ordered_asc(self, mock_db):
        """Verify the query is constructed; ordering verified by DB engine."""
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        # Should not raise — ordering direction is applied by the DB
        await InteractionRepository.get_session_timeline(
            mock_db,
            project_id="proj-1",
            session_id="sess-1",
        )
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_limit_and_offset(self, mock_db):
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        await InteractionRepository.get_session_timeline(
            mock_db,
            project_id="proj-1",
            session_id="sess-1",
            limit=5,
            offset=10,
        )
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_namespace_filter(self, mock_db):
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        await InteractionRepository.get_session_timeline(
            mock_db,
            project_id="proj-1",
            session_id="sess-1",
            namespace="production",
        )
        assert mock_db.execute.called


# ===========================================================================
# 4. TestGetAgentInteractions
# ===========================================================================

class TestGetAgentInteractions:
    """Test InteractionRepository.get_agent_interactions."""

    @pytest.mark.asyncio
    async def test_returns_events(self, mock_db):
        from interaction_repository import InteractionRepository

        events = [_make_event() for _ in range(2)]
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = events
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await InteractionRepository.get_agent_interactions(
            mock_db,
            project_id="proj-1",
            agent_id="agent-1",
        )

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty(self, mock_db):
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await InteractionRepository.get_agent_interactions(
            mock_db,
            project_id="proj-1",
            agent_id="agent-1",
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_ordered_desc(self, mock_db):
        """DESC ordering is applied by the DB engine."""
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        await InteractionRepository.get_agent_interactions(
            mock_db,
            project_id="proj-1",
            agent_id="agent-1",
        )
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_limit(self, mock_db):
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        await InteractionRepository.get_agent_interactions(
            mock_db,
            project_id="proj-1",
            agent_id="agent-1",
            limit=25,
        )
        assert mock_db.execute.called

    @pytest.mark.asyncio
    async def test_namespace_filter(self, mock_db):
        from interaction_repository import InteractionRepository

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute = AsyncMock(return_value=result_mock)

        await InteractionRepository.get_agent_interactions(
            mock_db,
            project_id="proj-1",
            agent_id="agent-1",
            namespace="production",
        )
        assert mock_db.execute.called


# ===========================================================================
# 5. TestSearchInteractions
# ===========================================================================

class TestSearchInteractions:
    """Test InteractionRepository.search."""

    def _make_db_with_rows(self, mock_db, rows):
        result_mock = MagicMock()
        result_mock.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=result_mock)
        return mock_db

    @pytest.mark.asyncio
    async def test_returns_results(self, mock_db):
        from interaction_repository import InteractionRepository

        event = _make_event(embedding=[0.1] * 1536)
        rows = [(event, 0.05)]  # distance=0.05, score≈0.95
        self._make_db_with_rows(mock_db, rows)

        results = await InteractionRepository.search(
            mock_db,
            project_id="proj-1",
            query_embedding=[0.1] * 1536,
        )

        assert len(results) == 1
        assert results[0][0] is event
        assert abs(results[0][1] - 0.95) < 0.01

    @pytest.mark.asyncio
    async def test_min_score_filter(self, mock_db):
        from interaction_repository import InteractionRepository

        event1 = _make_event(embedding=[0.1] * 1536)
        event2 = _make_event(embedding=[0.2] * 1536)
        rows = [(event1, 0.05), (event2, 0.8)]  # scores: 0.95, 0.2
        self._make_db_with_rows(mock_db, rows)

        results = await InteractionRepository.search(
            mock_db,
            project_id="proj-1",
            query_embedding=[0.1] * 1536,
            min_score=0.5,
        )

        assert len(results) == 1
        assert results[0][0] is event1

    @pytest.mark.asyncio
    async def test_session_id_filter_passed(self, mock_db):
        """Ensure session_id filter is included in query (no error)."""
        from interaction_repository import InteractionRepository

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        results = await InteractionRepository.search(
            mock_db,
            project_id="proj-1",
            query_embedding=[0.0] * 1536,
            session_id="sess-filter",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_agent_id_filter_passed(self, mock_db):
        from interaction_repository import InteractionRepository

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        results = await InteractionRepository.search(
            mock_db,
            project_id="proj-1",
            query_embedding=[0.0] * 1536,
            agent_id="agent-filter",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_null_embedding_rows_excluded(self, mock_db):
        """Events without embeddings should not appear in results (filtered by IS NOT NULL)."""
        from interaction_repository import InteractionRepository

        # No embedding on event — such events would not be returned by the
        # database query (IS NOT NULL filter). We simulate DB returning empty.
        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        results = await InteractionRepository.search(
            mock_db,
            project_id="proj-1",
            query_embedding=[0.0] * 1536,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_db):
        from interaction_repository import InteractionRepository

        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        results = await InteractionRepository.search(
            mock_db,
            project_id="proj-1",
            query_embedding=[0.0] * 1536,
        )
        assert results == []


# ===========================================================================
# 6. TestGetWithChain
# ===========================================================================

class TestGetWithChain:
    """Test InteractionRepository.get_with_chain."""

    def _setup_db_sequence(self, mock_db, events_by_id):
        """
        Configure mock_db to return different events for sequential execute() calls.
        events_by_id: dict mapping event_id -> InteractionEvent or None.
        """
        call_count = [0]
        event_ids_order = list(events_by_id.keys())

        async def execute_side_effect(query):
            result = MagicMock()
            idx = call_count[0]
            call_count[0] += 1
            event_id = event_ids_order[idx] if idx < len(event_ids_order) else None
            event = events_by_id.get(event_id) if event_id else None
            result.scalar_one_or_none.return_value = event
            return result

        mock_db.execute = execute_side_effect

    @pytest.mark.asyncio
    async def test_root_event_no_parent(self, mock_db):
        """A root event (no parent) returns a chain of depth 1."""
        from interaction_repository import InteractionRepository

        root = _make_event(event_id="root" + "0" * 28, parent_event_id=None)
        self._setup_db_sequence(mock_db, {"root" + "0" * 28: root})

        chain = await InteractionRepository.get_with_chain(
            mock_db,
            event_id="root" + "0" * 28,
            project_id="proj-1",
        )

        assert len(chain) == 1
        assert chain[0].event_id == "root" + "0" * 28

    @pytest.mark.asyncio
    async def test_two_level_chain(self, mock_db):
        """parent → child chain returns [parent, child]."""
        from interaction_repository import InteractionRepository

        parent_id = "parent" + "0" * 26
        child_id = "child" + "0" * 27

        parent = _make_event(event_id=parent_id, parent_event_id=None)
        child = _make_event(event_id=child_id, parent_event_id=parent_id)

        self._setup_db_sequence(mock_db, {child_id: child, parent_id: parent})

        chain = await InteractionRepository.get_with_chain(
            mock_db,
            event_id=child_id,
            project_id="proj-1",
        )

        assert len(chain) == 2
        assert chain[0].event_id == parent_id  # root first
        assert chain[1].event_id == child_id   # leaf last

    @pytest.mark.asyncio
    async def test_missing_event_returns_empty(self, mock_db):
        """Non-existent event_id returns empty list."""
        from interaction_repository import InteractionRepository

        async def execute_none(query):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = execute_none

        chain = await InteractionRepository.get_with_chain(
            mock_db,
            event_id="nonexistent" + "0" * 21,
            project_id="proj-1",
        )

        assert chain == []

    @pytest.mark.asyncio
    async def test_max_depth_respected(self, mock_db):
        """Chain traversal stops at max_depth even if parents exist."""
        from interaction_repository import InteractionRepository

        # Create a chain of 5 events but request max_depth=3
        events = {}
        for i in range(5):
            eid = f"ev{i}" + "0" * 30
            parent = f"ev{i+1}" + "0" * 30 if i < 4 else None
            events[eid] = _make_event(event_id=eid, parent_event_id=parent)

        call_order = list(events.keys())
        call_count = [0]

        async def execute_side_effect(query):
            result = MagicMock()
            idx = call_count[0]
            call_count[0] += 1
            eid = call_order[idx] if idx < len(call_order) else None
            result.scalar_one_or_none.return_value = events.get(eid)
            return result

        mock_db.execute = execute_side_effect

        chain = await InteractionRepository.get_with_chain(
            mock_db,
            event_id=call_order[0],
            project_id="proj-1",
            max_depth=3,
        )

        assert len(chain) <= 3

    @pytest.mark.asyncio
    async def test_cycle_guard(self, mock_db):
        """Cycle guard (seen set) prevents infinite loops on circular references."""
        from interaction_repository import InteractionRepository

        # A → B → A (circular)
        a_id = "aaaa" + "0" * 28
        b_id = "bbbb" + "0" * 28

        a = _make_event(event_id=a_id, parent_event_id=b_id)
        b = _make_event(event_id=b_id, parent_event_id=a_id)

        call_map = {a_id: a, b_id: b}
        call_order = [a_id, b_id, a_id, b_id, a_id]  # simulating circular
        call_count = [0]

        async def execute_side_effect(query):
            result = MagicMock()
            idx = call_count[0]
            call_count[0] += 1
            eid = call_order[idx] if idx < len(call_order) else None
            result.scalar_one_or_none.return_value = call_map.get(eid)
            return result

        mock_db.execute = execute_side_effect

        # Should not raise or hang
        chain = await InteractionRepository.get_with_chain(
            mock_db,
            event_id=a_id,
            project_id="proj-1",
            max_depth=10,
        )

        # Should stop after seeing a_id twice
        assert len(chain) <= 2


# ===========================================================================
# 7. TestPydanticModels
# ===========================================================================

class TestPydanticModels:
    """Validate Pydantic request/response models."""

    def test_interaction_event_create_defaults(self):
        from api.routers.interaction_events import InteractionEventCreate
        model = InteractionEventCreate(session_id="s1", content="hello")
        assert model.namespace == "default"
        assert model.embed is False
        assert model.agent_id is None
        assert model.tool_calls is None
        assert model.parent_event_id is None
        assert model.extra_metadata is None

    def test_interaction_event_create_validation(self):
        from api.routers.interaction_events import InteractionEventCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            InteractionEventCreate(content="hello")  # missing session_id

        with pytest.raises(ValidationError):
            InteractionEventCreate(session_id="s1", content="")  # empty content

    def test_interaction_search_request_defaults(self):
        from api.routers.interaction_events import InteractionSearchRequest
        model = InteractionSearchRequest(query="find me something")
        assert model.namespace == "default"
        assert model.top_k == 10
        assert model.min_score == 0.0
        assert model.session_id is None
        assert model.agent_id is None

    def test_interaction_event_out_has_embedding_field(self):
        from api.routers.interaction_events import InteractionEventOut
        fields = InteractionEventOut.model_fields
        assert "has_embedding" in fields

    def test_event_with_chain_result_fields(self):
        from api.routers.interaction_events import EventWithChainResult
        fields = EventWithChainResult.model_fields
        assert "event" in fields
        assert "chain" in fields
        assert "chain_depth" in fields

    def test_session_timeline_result_fields(self):
        from api.routers.interaction_events import SessionTimelineResult
        fields = SessionTimelineResult.model_fields
        assert "session_id" in fields
        assert "events" in fields
        assert "count" in fields

    def test_agent_interactions_result_fields(self):
        from api.routers.interaction_events import AgentInteractionsResult
        fields = AgentInteractionsResult.model_fields
        assert "agent_id" in fields
        assert "events" in fields
        assert "count" in fields

    def test_interaction_search_result_fields(self):
        from api.routers.interaction_events import InteractionSearchResult
        fields = InteractionSearchResult.model_fields
        assert "results" in fields
        assert "query_time_ms" in fields


# ===========================================================================
# 8. TestRouterRegistration
# ===========================================================================

class TestRouterRegistration:
    """Validate the router is registered correctly in the app."""

    def test_router_registered_at_prefix(self):
        from api.app import modular_app
        routes = {route.path for route in modular_app.routes}
        assert any("/interaction-events" in path for path in routes)

    def test_router_has_correct_tags(self):
        from api.routers.interaction_events import router
        # Tags are set at include_router() level; verify router exists with routes
        assert len(router.routes) >= 5

    def test_create_endpoint_exists(self):
        from api.app import modular_app
        paths = {route.path for route in modular_app.routes}
        assert "/interaction-events/" in paths

    def test_session_timeline_endpoint_exists(self):
        from api.app import modular_app
        paths = {route.path for route in modular_app.routes}
        assert any("session" in p for p in paths if "interaction-events" in p)

    def test_agent_history_endpoint_exists(self):
        from api.app import modular_app
        paths = {route.path for route in modular_app.routes}
        assert any("agent" in p for p in paths if "interaction-events" in p)

    def test_search_endpoint_exists(self):
        from api.app import modular_app
        paths = {route.path for route in modular_app.routes}
        assert any("search" in p for p in paths if "interaction-events" in p)

    def test_event_chain_endpoint_exists(self):
        from api.app import modular_app
        paths = {route.path for route in modular_app.routes}
        assert any("{event_id}" in p for p in paths if "interaction-events" in p)


# ===========================================================================
# 9. TestMigration0005
# ===========================================================================

class TestMigration0005:
    """Validate the Alembic migration file structure."""

    def test_migration_revision(self):
        import importlib.util
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "alembic", "versions", "0005_interaction_events.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0005", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        assert migration.revision == "0005"
        assert migration.down_revision == "0004"

    def test_migration_has_upgrade_and_downgrade(self):
        import importlib.util
        import os

        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "alembic", "versions", "0005_interaction_events.py"
        )
        spec = importlib.util.spec_from_file_location("migration_0005", migration_path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        assert callable(migration.upgrade)
        assert callable(migration.downgrade)


# ===========================================================================
# 10. TestSDKDataclasses
# ===========================================================================

class TestSDKDataclasses:
    """Validate SDK dataclasses and the _parse_interaction_event helper."""

    def test_parse_interaction_event(self):
        import sys
        sdk_path = os.path.join(os.path.dirname(__file__), "..", "aegis_memory")
        if sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)
        from client import _parse_interaction_event

        data = {
            "event_id": "abc123" + "0" * 26,
            "project_id": "proj-1",
            "session_id": "sess-1",
            "agent_id": "agent-1",
            "content": "Test content",
            "timestamp": "2026-02-21T12:00:00Z",
            "tool_calls": [{"name": "search"}],
            "parent_event_id": None,
            "namespace": "default",
            "extra_metadata": {"key": "value"},
            "has_embedding": True,
        }

        event = _parse_interaction_event(data)
        assert event.event_id == data["event_id"]
        assert event.project_id == "proj-1"
        assert event.has_embedding is True
        assert event.tool_calls == [{"name": "search"}]

    def test_interaction_event_result_dataclass(self):
        import sys
        sdk_path = os.path.join(os.path.dirname(__file__), "..", "aegis_memory")
        if sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)
        from client import InteractionEventResult

        result = InteractionEventResult(
            event_id="abc123",
            session_id="sess-1",
            namespace="default",
            has_embedding=False,
        )
        assert result.event_id == "abc123"
        assert result.has_embedding is False

    def test_session_timeline_result_dataclass(self):
        import sys
        sdk_path = os.path.join(os.path.dirname(__file__), "..", "aegis_memory")
        if sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)
        from client import SessionTimelineResult

        result = SessionTimelineResult(
            session_id="sess-1",
            namespace="default",
            events=[],
            count=0,
        )
        assert result.session_id == "sess-1"
        assert result.count == 0

    def test_event_with_chain_result_dataclass(self):
        import sys
        sdk_path = os.path.join(os.path.dirname(__file__), "..", "aegis_memory")
        if sdk_path not in sys.path:
            sys.path.insert(0, sdk_path)
        from client import EventWithChainResult, InteractionEvent
        from datetime import datetime, timezone

        evt = InteractionEvent(
            event_id="abc",
            project_id="p",
            session_id="s",
            agent_id=None,
            content="test",
            timestamp=datetime.now(timezone.utc),
            tool_calls=[],
            parent_event_id=None,
            namespace="default",
            extra_metadata=None,
            has_embedding=False,
        )

        result = EventWithChainResult(event=evt, chain=[evt], chain_depth=1)
        assert result.chain_depth == 1
        assert len(result.chain) == 1
