from __future__ import annotations

from pathlib import Path


def test_production_example_does_not_supply_placeholder_secrets() -> None:
    values = dict(
        line.split("=", 1)
        for line in Path(".env.production.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )

    assert values["POSTGRES_ADMIN_PASSWORD"] == ""
    assert values["DATABASE_PASSWORD"] == ""
    assert values["DATABASE_USER"] == "enterprise_bi_app"
    assert values["API_KEY"] == ""
    assert values["CORS_ORIGINS"] == ""
    assert values["BIND_ADDRESS"] == "127.0.0.1"


def test_production_topology_separates_database_and_limits_pre_auth_traffic() -> None:
    compose = Path("docker-compose.production.yml").read_text(encoding="utf-8")
    nginx = Path("frontend/nginx.conf").read_text(encoding="utf-8")

    assert "database:\n    internal: true" in compose
    assert "networks: [application, database]" in compose
    assert '"${BIND_ADDRESS:-127.0.0.1}:${APP_PORT:-8080}:80"' in compose
    assert "limit_req_zone $binary_remote_addr" in nginx
    assert "limit_req zone=api_pre_auth" in nginx
    assert "zone=system_routes:10m" in nginx
    assert "limit_req zone=system_routes" in nginx
    assert "--no-access-log" in compose
    assert "Content-Security-Policy" in nginx
    assert "script-src 'self'" in nginx
    assert "map $http_x_forwarded_proto $upstream_forwarded_proto" in nginx
    assert "https https;" in nginx
    assert "proxy_set_header X-Forwarded-Proto $upstream_forwarded_proto" in nginx
    assert "proxy_set_header X-Forwarded-For $remote_addr" in nginx
    assert "does not trust" in nginx


def test_production_api_uses_a_dedicated_non_superuser_database_role() -> None:
    compose = Path("docker-compose.production.yml").read_text(encoding="utf-8")
    initializer = Path("deploy/postgres/init-app-role.sql").read_text(
        encoding="utf-8"
    )

    assert "POSTGRES_PASSWORD: ${POSTGRES_ADMIN_PASSWORD" in compose
    assert "DATABASE_PASSWORD: ${DATABASE_PASSWORD" in compose
    assert "DATABASE_USER: ${DATABASE_USER:-enterprise_bi_app}" in compose
    assert "condition: service_completed_successfully" in compose
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE" in initializer
    assert "GRANT USAGE, CREATE ON SCHEMA public" in initializer


def test_local_container_dashboard_uses_csp_compatible_same_origin_api() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert 'VITE_API_URL: ""' in compose


def test_codeql_can_read_private_repository_workflow_metadata() -> None:
    workflow = Path(".github/workflows/codeql.yml").read_text(encoding="utf-8")

    permissions = workflow.split("permissions:\n", 1)[1].split("\njobs:", 1)[0]
    assert "  actions: read\n" in permissions
    assert "  contents: read\n" in permissions
    assert "  security-events: write\n" in permissions
