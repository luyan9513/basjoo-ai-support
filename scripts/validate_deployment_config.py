#!/usr/bin/env python3
"""Static PRE-AGENT-04 deployment gate; uses only the Python standard library."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def service_block(compose: str, service: str, next_service: str) -> str:
    pattern = rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  {re.escape(next_service)}:\n)"
    match = re.search(pattern, compose)
    if not match:
        raise AssertionError(f"cannot locate Compose service: {service}")
    return match.group(1)


def validate() -> list[str]:
    errors: list[str] = []
    compose = read("docker-compose.yml")
    next_config = read("frontend-nextjs/next.config.mjs")
    frontend_dockerfile = read("frontend-nextjs/Dockerfile")
    nginx_default = read("nginx/conf.d/default.conf")
    nginx_entrypoint = read("nginx/docker-entrypoint.sh")
    nginx_locations = read("nginx/conf.d/locations.conf")
    deploy = read("deploy.sh")
    installer = read("install-deploy.sh")

    if "image: qdrant/qdrant:v1.18.3" not in compose:
        errors.append("Qdrant image is not pinned to v1.18.3")
    if "qdrant-data:/qdrant/storage" not in compose:
        errors.append("Qdrant persistent volume mapping is missing")

    try:
        postgres = service_block(compose, "postgres", "qdrant")
        if 'profiles: ["experimental-db"]' not in postgres:
            errors.append("PostgreSQL is still enabled in the normal dev/prod profiles")
    except AssertionError as exc:
        errors.append(str(exc))

    backend_healthchecks = re.findall(
        r"urllib\.request\.urlopen\('http://localhost:8000/([^']+)'", compose
    )
    if backend_healthchecks != ["ready", "ready"]:
        errors.append("backend Compose healthchecks must use /ready")

    if re.search(r"ignoreDuringBuilds\s*:\s*true", next_config):
        errors.append("Next.js production build still ignores ESLint failures")
    if re.search(r"ignoreBuildErrors\s*:\s*true", next_config):
        errors.append("Next.js production build still ignores TypeScript failures")
    typecheck_position = frontend_dockerfile.find("RUN npm run typecheck")
    build_position = frontend_dockerfile.find("RUN npm run build")
    if typecheck_position < 0 or build_position < 0 or typecheck_position > build_position:
        errors.append("frontend image must run typecheck before next build")
    if "--mount=type=cache,target=/root/.npm" not in frontend_dockerfile:
        errors.append("frontend image does not persist the npm download cache")
    if "--fetch-retries=5" not in frontend_dockerfile:
        errors.append("frontend image does not use the bounded npm fetch retry policy")

    body_sizes = re.findall(
        r"client_max_body_size\s+([^;]+);", nginx_default + nginx_entrypoint
    )
    if not body_sizes or set(body_sizes) != {"105m"}:
        errors.append(f"Nginx body-size limits are not uniformly 105m: {body_sizes}")
    if "location = /ready" not in nginx_locations:
        errors.append("Nginx does not proxy the readiness endpoint")

    if 'BASJOO_ENABLE_SWAP=${BASJOO_ENABLE_SWAP:-0}' not in deploy:
        errors.append("deploy.sh still changes swap without explicit opt-in")
    if 'BASJOO_DESTRUCTIVE_UPDATE=${BASJOO_DESTRUCTIVE_UPDATE:-0}' not in installer:
        errors.append("installer lacks an explicit destructive-update opt-in")
    if 'BASJOO_CLEAN_UNTRACKED=${BASJOO_CLEAN_UNTRACKED:-0}' not in installer:
        errors.append("installer lacks a separate untracked-file cleanup opt-in")
    if "BASJOO_FORCE_CLEAN=${BASJOO_FORCE_CLEAN:-1}" in installer:
        errors.append("installer still enables destructive cleanup by default")
    if "wait_for_container basjoo-postgres" in installer:
        errors.append("installer still requires inactive experimental PostgreSQL")
    if "https://github.com/luyan9513/basjoo-ai-support.git" not in installer:
        errors.append("installer default repository does not point to this maintained fork")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: PRE-AGENT-04 deployment configuration gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
