# Test Organization

This directory contains all tests for the Aegra project, organized by test type following pytest best practices.

## Structure

```
tests/
├── unit/                   # Fast, isolated tests (no external dependencies)
│   ├── test_middleware/    # Middleware unit tests
│   ├── test_utils/         # Utility function tests
│   └── test_models/        # Pydantic model tests
│
├── integration/            # Tests with DB or multiple components
│   ├── test_services/      # Service layer integration tests
│   └── test_api/           # API integration tests
│
├── e2e/                    # End-to-end tests (full system)
│   ├── test_assistants/    # Assistant feature tests
│   ├── test_runs/          # Run execution tests
│   ├── test_threads/       # Thread management tests
│   ├── test_streaming/     # Streaming functionality tests
│   ├── test_store/         # Store tests
│   └── test_human_in_loop/ # HITL tests
│
├── fixtures/               # Shared test fixtures
│   ├── auth.py            # Authentication fixtures
│   ├── database.py        # Database fixtures
│   ├── langgraph.py       # LangGraph mocks
│   └── clients.py         # Test client fixtures
│
├── conftest.py            # Global pytest configuration
└── pytest.ini             # Pytest settings and markers
```

## Test Categories

### Unit Tests (`tests/unit/`)
- **Purpose**: Test individual functions/classes in isolation
- **Dependencies**: Mocks only, no external services
- **Speed**: ⚡ Very fast (milliseconds)
- **Run with**: `pytest tests/unit/`

### Integration Tests (`tests/integration/`)
- **Purpose**: Test multiple components working together
- **Dependencies**: Real database, mocked external APIs
- **Speed**: 🐢 Slower (100ms-1s per test)
- **Run with**: `pytest tests/integration/`

### E2E Tests (`tests/e2e/`)
- **Purpose**: Test complete user workflows
- **Dependencies**: Full system, real database, real services
- **Speed**: 🐌 Slowest (1s-10s per test)
- **Run with**: `pytest tests/e2e/`

## Running Tests

### Run all tests
```bash
pytest
```

### Run by category
```bash
pytest tests/unit/          # Only unit tests
pytest tests/integration/   # Only integration tests
pytest tests/e2e/          # Only E2E tests
```

### Run by marker
```bash
pytest -m unit              # All unit tests
pytest -m integration       # All integration tests
pytest -m e2e              # All E2E tests
pytest -m "not slow"       # Skip slow tests
```

### Run specific test file
```bash
pytest tests/unit/test_middleware/test_double_encoded_json.py
```

### Run with verbose output
```bash
pytest -v
```

### Run with coverage
```bash
pytest --cov=src/agent_server --cov-report=html
```

## Test Markers

Tests can be marked with pytest markers for categorization:

- `@pytest.mark.unit` - Unit test
- `@pytest.mark.integration` - Integration test
- `@pytest.mark.e2e` - End-to-end test
- `@pytest.mark.slow` - Test takes > 1 second

## Fixtures

Shared fixtures are available from:
- `tests/conftest.py` - Global fixtures
- `tests/fixtures/` - Organized fixture modules
- `tests/{category}/conftest.py` - Category-specific fixtures

### Common Fixtures

```python
from tests.fixtures.auth import DummyUser
from tests.fixtures.database import DummySessionBase
from tests.fixtures.langgraph import FakeAgent, FakeGraph
from tests.fixtures.clients import create_test_app, make_client
```

## Writing New Tests

### Unit Test Example
```python
# tests/unit/test_utils/test_sse_utils.py
import pytest
from src.agent_server.utils import generate_event_id

@pytest.mark.unit
def test_generate_event_id():
    event_id = generate_event_id("run-123", 1)
    assert event_id == "run-123_event_1"
```

### Integration Test Example
```python
# tests/integration/test_services/test_assistant_service.py
import pytest
from tests.fixtures.database import DummySessionBase

@pytest.mark.integration
async def test_create_assistant():
    # Test with real database interactions
    pass
```

### E2E Test Example
```python
# tests/e2e/test_assistants/test_assistant_crud.py
import pytest
from tests.e2e._utils import get_e2e_client

@pytest.mark.e2e
async def test_full_assistant_workflow():
    client = get_e2e_client()
    # Test complete user workflow
    pass
```

## CI/CD Integration

Tests are run in stages for optimal speed:

1. **Unit Tests** (fast feedback)
2. **Integration Tests** (if unit tests pass)
3. **E2E Tests** (if integration tests pass)

This ensures fast failure detection and efficient resource usage.

## Best Practices

1. ✅ Keep unit tests fast and isolated
2. ✅ Use fixtures for common setup
3. ✅ Name tests descriptively: `test_<what>_<condition>_<expected>`
4. ✅ One assertion per test when possible
5. ✅ Use markers to categorize tests
6. ✅ Mock external dependencies in unit tests
7. ✅ Clean up resources in test teardown
8. ✅ Use `pytest.mark.parametrize` for multiple test cases

## Troubleshooting

### Import Errors
Make sure you're running pytest from the project root:
```bash
cd /path/to/aegra
pytest tests/
```

### Database Errors in Integration Tests
Ensure Docker Compose is running:
```bash
docker compose up -d
```

### Slow Tests
Run only fast tests during development:
```bash
pytest -m "not slow"
```
