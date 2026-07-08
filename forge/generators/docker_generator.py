"""Docker Generator — generate Dockerfiles, docker-compose, K8s manifests."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class DockerSpec:
    name: str
    language: str
    port: int = 8000
    env_vars: dict = field(default_factory=dict)
    volumes: list[str] = field(default_factory=list)
    services: list[dict] = field(default_factory=list)

class DockerGenerator:
    """Generate Docker configuration files."""

    @classmethod
    def generate(cls, spec: DockerSpec) -> dict[str, str]:
        files = {}
        files["Dockerfile"] = cls._dockerfile(spec)
        files["docker-compose.yml"] = cls._compose(spec)
        files[".dockerignore"] = cls._dockerignore(spec)
        files[".env.example"] = "\n".join(f"{k}={v}" for k, v in spec.env_vars.items()) or "# Add environment variables here\n"
        return files

    @classmethod
    def _dockerfile(cls, spec: DockerSpec) -> str:
        templates = {
            "python": f"""# Build stage
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# Runtime stage
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
EXPOSE {spec.port}
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:{spec.port}/health || exit 1
CMD ["uvicorn", "{spec.name}.main:app", "--host", "0.0.0.0", "--port", "{spec.port}"]
""",
            "node": f"""FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE {spec.port}
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:{spec.port}/health || exit 1
CMD ["node", "dist/index.js"]
""",
            "go": f"""FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app/server .

FROM alpine:3.19
RUN apk --no-cache add ca-certificates
WORKDIR /app
COPY --from=builder /app/server .
EXPOSE {spec.port}
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:{spec.port}/health || exit 1
CMD ["./server"]
""",
            "rust": f"""FROM rust:1.77 AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/{spec.name} /usr/local/bin/
EXPOSE {spec.port}
CMD ["{spec.name}"]
""",
            "java": f"""FROM eclipse-temurin:21-jdk-alpine AS builder
WORKDIR /app
COPY gradle ./gradle
COPY gradlew build.gradle ./
RUN ./gradlew build --no-daemon

FROM eclipse-temurin:21-jre-alpine
COPY --from=builder /app/build/libs/*.jar /app/app.jar
EXPOSE {spec.port}
CMD ["java", "-jar", "/app/app.jar"]
""",
        }
        return templates.get(spec.language, templates["python"])

    @classmethod
    def _compose(cls, spec: DockerSpec) -> str:
        services = [f"""version: "3.8"
services:
  {spec.name}:
    build: .
    ports:
      - "{spec.port}:{spec.port}"
    environment:"""]
        for k, v in spec.env_vars.items():
            services.append(f"      - {k}=${{{k}}}")
        if spec.volumes:
            services.append("    volumes:")
            for v in spec.volumes:
                services.append(f"      - {v}")
        services.append("    restart: unless-stopped")
        services.append("    healthcheck:")
        services.append(f'      test: ["CMD", "curl", "-f", "http://localhost:{spec.port}/health"]')
        services.append("      interval: 30s")
        services.append("      timeout: 3s")
        services.append("      retries: 3")
        return "\n".join(services)

    @classmethod
    def _dockerignore(cls, spec: DockerSpec) -> str:
        return """node_modules
.git
.env
*.md
.pytest_cache
__pycache__
.venv
venv
dist
build
*.egg-info
coverage
htmlcov
.mypy_cache
.ruff_cache
"""
