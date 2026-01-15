# Contributing to Meeting Bot API

Thank you for your interest in contributing! This document provides guidelines and best practices.

## 📋 Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Architecture Guidelines](#architecture-guidelines)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)

---

## 🚀 Getting Started

1. **Fork the repository**
2. **Clone your fork:**
   ```bash
   git clone https://github.com/your-username/meeting-note-tker.git
   cd meeting-note-tker
   ```
3. **Create a branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## 💻 Development Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install black flake8 mypy pytest pytest-asyncio

# Install Playwright
playwright install chromium

# Run the application
python run.py
```

---

## 🏗️ Architecture Guidelines

### Clean Architecture Principles

Follow the layered architecture:

```
API Layer (app/api/)
    ↓ depends on
Domain Layer (app/domain/)
    ↓ depends on
Infrastructure Layer (app/infrastructure/)
    ↓ uses
Core Layer (app/core/)
```

**Rules:**
- ✅ API layer can import from Domain and Schemas
- ✅ Domain layer should NOT import from API or Infrastructure
- ✅ Infrastructure implements interfaces defined in Domain
- ❌ Never circular dependencies

### Adding New Features

#### 1. New API Endpoint

```python
# app/api/v1/endpoints/your_feature.py
from fastapi import APIRouter, Depends
from app.api.v1.schemas.your_feature import YourRequest, YourResponse
from app.core.dependencies import get_meeting_bot_service

router = APIRouter()

@router.post("/your-endpoint", response_model=YourResponse)
async def your_endpoint(
    request: YourRequest,
    bot=Depends(get_meeting_bot_service)
):
    return bot.your_method(request)
```

Register in `app/api/v1/router.py`:
```python
from app.api.v1.endpoints import your_feature

api_router.include_router(your_feature.router, prefix="/your-feature", tags=["Your Feature"])
```

#### 2. New Business Logic

```python
# app/domain/services/your_service.py
from app.domain.models import YourModel
from app.infrastructure.your_infra import YourInfraService

class YourService:
    def __init__(self):
        self.infra = YourInfraService()
    
    async def your_business_logic(self, data):
        # Pure business logic here
        return result
```

#### 3. New Infrastructure Service

```python
# app/infrastructure/your_service/service.py
from app.core.logging import get_logger

logger = get_logger("your_service")

class YourInfraService:
    async def your_external_call(self):
        # External service integration
        pass
```

---

## 🎨 Code Style

### Python Style Guide

- **Formatter:** Black (line length: 100)
- **Linter:** Flake8
- **Type Hints:** Required for all functions

```bash
# Format code
black app/

# Lint
flake8 app/ --max-line-length=100

# Type check
mypy app/
```

### Naming Conventions

- **Files:** `snake_case.py`
- **Classes:** `PascalCase`
- **Functions/Variables:** `snake_case`
- **Constants:** `UPPER_CASE`
- **Private:** `_leading_underscore`

### Docstrings

Use Google-style docstrings:

```python
def example_function(param1: str, param2: int) -> bool:
    """
    Short description.
    
    Longer description if needed.
    
    Args:
        param1: Description of param1
        param2: Description of param2
    
    Returns:
        Description of return value
    
    Raises:
        ValueError: When param1 is empty
    """
    pass
```

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_your_feature.py

# Run with verbose output
pytest -v
```

### Writing Tests

```python
# tests/test_your_feature.py
import pytest
from app.domain.services.your_service import YourService

@pytest.mark.asyncio
async def test_your_feature():
    service = YourService()
    result = await service.your_method()
    assert result is not None

def test_your_sync_feature():
    # Synchronous test
    assert True
```

### Test Structure

```
tests/
├── api/            # API endpoint tests
├── domain/         # Business logic tests
├── infrastructure/ # Infrastructure tests
└── conftest.py     # Shared fixtures
```

---

## 🔄 Pull Request Process

### Before Submitting

1. **Update your branch:**
   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. **Run tests:**
   ```bash
   pytest
   ```

3. **Format and lint:**
   ```bash
   black app/
   flake8 app/
   ```

4. **Update documentation** if needed

### PR Checklist

- [ ] Code follows the style guide
- [ ] All tests pass
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] No breaking changes (or clearly documented)
- [ ] Commit messages are clear and descriptive

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested your changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests pass
- [ ] Documentation updated
```

### Commit Messages

Follow conventional commits:

```
feat: add manual meeting join API endpoint
fix: resolve authentication token refresh issue
docs: update API documentation
refactor: simplify email service interface
test: add tests for scheduler service
```

---

## 📝 Code Review Process

### What We Look For

1. **Correctness** - Does it work as intended?
2. **Tests** - Are there adequate tests?
3. **Design** - Does it follow clean architecture?
4. **Performance** - Any obvious performance issues?
5. **Security** - Any security concerns?
6. **Documentation** - Is it well documented?

### Review Timeline

- Initial review within 48 hours
- Follow-up responses within 24 hours
- Merge after approval from maintainers

---

## 🐛 Reporting Bugs

Use GitHub Issues with:

- **Title:** Clear, concise description
- **Environment:** OS, Python version, etc.
- **Steps to Reproduce:** Detailed steps
- **Expected Behavior:** What should happen
- **Actual Behavior:** What actually happens
- **Logs:** Relevant error messages or logs

---

## 💡 Feature Requests

Use GitHub Issues with `[Feature]` tag:

- **Use Case:** Why is this needed?
- **Proposed Solution:** How should it work?
- **Alternatives:** Other approaches considered

---

## 📞 Getting Help

- **Issues:** For bugs and feature requests
- **Discussions:** For questions and ideas
- **Documentation:** Check `/docs` directory

---

## 🙏 Thank You!

Your contributions make this project better for everyone. We appreciate your time and effort!
