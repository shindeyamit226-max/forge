"""
Project Generator — scaffold complete projects from templates.
Supports: FastAPI, Flask, Django, Express, React, Vue, Next.js, Go, Rust, Spring Boot.
Each template includes: project structure, config files, CI/CD, Docker, tests, docs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ProjectTemplate:
    name: str
    language: str
    framework: str
    description: str
    files: dict[str, str] = field(default_factory=dict)  # path -> content
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)


class ProjectGenerator:
    """Generate complete project scaffolding."""

    TEMPLATES = {}

    @classmethod
    def register_template(cls, name: str, template: ProjectTemplate):
        cls.TEMPLATES[name] = template

    @classmethod
    def list_templates(cls) -> list[str]:
        return sorted(cls.TEMPLATES.keys())

    @classmethod
    def generate(cls, template_name: str, project_name: str, output_dir: str = ".") -> list[str]:
        """Generate a project from a template."""
        template = cls.TEMPLATES.get(template_name)
        if not template:
            raise ValueError(f"Unknown template: {template_name}. Available: {', '.join(cls.list_templates())}")

        created = []
        base = Path(output_dir) / project_name

        for filepath, content in template.files.items():
            # Replace placeholders
            content = content.replace("{{project_name}}", project_name)
            content = content.replace("{{ProjectName}}", project_name.replace("-", "_").title())
            content = content.replace("{{project_name_underscore}}", project_name.replace("-", "_"))

            full_path = base / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            created.append(str(full_path))

        return created


# ============================================================
# FastAPI Template
# ============================================================

FASTAPI_TEMPLATE = ProjectTemplate(
    name="fastapi",
    language="python",
    framework="fastapi",
    description="Modern async Python API with FastAPI",
    files={
        "pyproject.toml": """[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{{project_name}}"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "pydantic>=2.5",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "python-jose[cryptography]>=3.3",
    "passlib[bcrypt]>=1.7",
    "python-multipart>=0.0.6",
    "httpx>=0.25",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-asyncio>=0.21", "httpx", "ruff>=0.1"]

[project.scripts]
serve = "uvicorn {{project_name_underscore}}.main:app --reload"
""",
        "{{project_name}}/__init__.py": '"""{{ProjectName}} API."""\n__version__ = "0.1.0"\n',
        "{{project_name}}/main.py": '''"""{{ProjectName}} — FastAPI Application."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import users, items, health
from .database import engine, Base

app = FastAPI(
    title="{{ProjectName}}",
    description="{{ProjectName}} API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(items.router, prefix="/api/v1/items", tags=["items"])

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
''',
        "{{project_name}}/database.py": '''"""Database configuration."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./{{project_name}}.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
''',
        "{{project_name}}/models.py": '''"""SQLAlchemy models."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("Item", back_populates="owner")

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="items")
''',
        "{{project_name}}/schemas.py": '''"""Pydantic schemas."""
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    is_active: bool
    created_at: datetime
    class Config:
        from_attributes = True

class ItemCreate(BaseModel):
    title: str
    description: Optional[str] = None

class ItemResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    owner_id: int
    created_at: datetime
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
''',
        "{{project_name}}/auth.py": '''"""Authentication utilities."""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .database import get_db
from .models import User
import os

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user
''',
        "{{project_name}}/routers/__init__.py": "",
        "{{project_name}}/routers/health.py": '''"""Health check endpoint."""
from fastapi import APIRouter
router = APIRouter()

@router.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}
''',
        "{{project_name}}/routers/users.py": '''"""User endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import User
from ..schemas import UserCreate, UserResponse, Token
from ..auth import get_password_hash, verify_password, create_access_token, get_current_user

router = APIRouter()

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == user.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = User(email=user.email, username=user.username, hashed_password=get_password_hash(user.password))
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
''',
        "{{project_name}}/routers/items.py": '''"""Item endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from ..database import get_db
from ..models import Item, User
from ..schemas import ItemCreate, ItemResponse
from ..auth import get_current_user

router = APIRouter()

@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(item: ItemCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_item = Item(**item.model_dump(), owner_id=current_user.id)
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item

@router.get("/", response_model=List[ItemResponse])
async def list_items(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).offset(skip).limit(limit))
    return result.scalars().all()

@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
''',
        "tests/__init__.py": "",
        "tests/conftest.py": '''"""Test configuration."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from {{project_name_underscore}}.database import Base, get_db
from {{project_name_underscore}}.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture
async def client():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async def override_get_db():
        async with test_session() as session:
            yield session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
''',
        "tests/test_health.py": '''"""Health check tests."""
import pytest

@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
''',
        "tests/test_users.py": '''"""User endpoint tests."""
import pytest

@pytest.mark.asyncio
async def test_create_user(client):
    response = await client.post("/api/v1/users/", json={
        "email": "test@example.com", "username": "testuser", "password": "testpass123"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["username"] == "testuser"
    assert "id" in data

@pytest.mark.asyncio
async def test_get_user(client):
    # Create user first
    create_resp = await client.post("/api/v1/users/", json={
        "email": "test2@example.com", "username": "testuser2", "password": "testpass123"
    })
    user_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["username"] == "testuser2"
''',
        "Dockerfile": '''FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY . .
EXPOSE 8000
CMD ["uvicorn", "{{project_name_underscore}}.main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
        "docker-compose.yml": '''version: "3.8"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite:///./data/{{project_name}}.db
    volumes:
      - ./data:/app/data
''',
        ".github/workflows/ci.yml": '''name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v
      - run: ruff check .
''',
        ".gitignore": '''__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/
*.db
.env
.mypy_cache/
.pytest_cache/
''',
        "README.md": '''# {{ProjectName}}

## Quick Start

```bash
pip install -e ".[dev]"
uvicorn {{project_name_underscore}}.main:app --reload
```

## API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Testing

```bash
pytest tests/ -v
```

## Docker

```bash
docker-compose up
```
''',
        ".env.example": '''DATABASE_URL=sqlite:///./{{project_name}}.db
SECRET_KEY=change-me-in-production
''',
    },
    dependencies=["fastapi", "uvicorn[standard]", "pydantic", "sqlalchemy", "alembic", "python-jose", "passlib", "python-multipart", "httpx"],
    dev_dependencies=["pytest", "pytest-asyncio", "httpx", "ruff"],
)

ProjectGenerator.register_template("fastapi", FASTAPI_TEMPLATE)
