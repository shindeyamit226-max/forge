"""CI/CD Generator — generate GitHub Actions, GitLab CI, CircleCI, Jenkins."""
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class CiSpec:
    name: str
    language: str
    platform: str = "github"  # github, gitlab, circleci, jenkins
    python_version: str = "3.12"
    node_version: str = "20"
    test_command: str = "pytest tests/ -v"
    lint_command: str = "ruff check ."
    deploy_target: str = ""  # aws, gcp, azure, docker

class CiGenerator:
    """Generate CI/CD configuration files."""

    @classmethod
    def generate(cls, spec: CiSpec) -> dict[str, str]:
        generators = {
            "github": cls._github_actions,
            "gitlab": cls._gitlab_ci,
            "circleci": cls._circleci,
            "jenkins": cls._jenkins,
        }
        gen = generators.get(spec.platform, cls._github_actions)
        return gen(spec)

    @classmethod
    def _github_actions(cls, spec: CiSpec) -> dict[str, str]:
        files = {}

        # Main CI workflow
        if spec.language == "python":
            files[".github/workflows/ci.yml"] = f"""name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python ${{{{ matrix.python-version }}}}
        uses: actions/setup-python@v5
        with:
          python-version: ${{{{ matrix.python-version }}}}
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Lint
        run: {spec.lint_command}
      - name: Test
        run: {spec.test_command}
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Build package
        run: |
          pip install build
          python -m build
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: package
          path: dist/

  docker:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t {spec.name}:${{{{ github.sha }}}} .
      - name: Login to registry
        run: echo "${{{{ secrets.DOCKER_PASSWORD }}}}" | docker login -u "${{{{ secrets.DOCKER_USERNAME }}}}" --password-stdin
"""
        elif spec.language in ("javascript", "typescript", "node"):
            files[".github/workflows/ci.yml"] = f"""name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node-version: [18, 20, 22]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{{{ matrix.node-version }}}}
          cache: npm
      - run: npm ci
      - run: npm run lint
      - run: npm test
      - run: npm run build

  docker:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t {spec.name} .
"""

        # Release workflow
        files[".github/workflows/release.yml"] = f"""name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          generate_release_notes: true
"""

        # Dependabot
        files[".github/dependabot.yml"] = """version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
"""

        return files

    @classmethod
    def _gitlab_ci(cls, spec: CiSpec) -> dict[str, str]:
        if spec.language == "python":
            return {".gitlab-ci.yml": f"""image: python:{spec.python_version}

stages:
  - test
  - build
  - deploy

test:
  stage: test
  script:
    - pip install -e ".[dev]"
    - {spec.lint_command}
    - {spec.test_command}
  coverage: '/TOTAL.*\\s(\\d+)%/'

build:
  stage: build
  script:
    - pip install build
    - python -m build
  artifacts:
    paths:
      - dist/
"""}
        return {".gitlab-ci.yml": "stages:\n  - test\n  - build\n"}

    @classmethod
    def _circleci(cls, spec: CiSpec) -> dict[str, str]:
        return {".circleci/config.yml": f"""version: 2.1
jobs:
  test:
    docker:
      - image: cimg/python:{spec.python_version}
    steps:
      - checkout
      - run: pip install -e ".[dev]"
      - run: {spec.test_command}
workflows:
  test:
    jobs:
      - test
"""}

    @classmethod
    def _jenkins(cls, spec: CiSpec) -> dict[str, str]:
        return {"Jenkinsfile": f"""pipeline {{
    agent any
    stages {{
        stage('Test') {{
            steps {{
                sh 'pip install -e ".[dev]"'
                sh '{spec.test_command}'
            }}
        }}
        stage('Build') {{
            steps {{
                sh 'python -m build'
            }}
        }}
    }}
}}
"""}
