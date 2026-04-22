# Infrastructure Module

Purpose:
- Local and server deployment assets (containers, runtime configs, observability).

Initial subdirectories:
- `docker/` compose files and container configs
- `monitoring/` metrics/logging dashboards and config

Scope note:
- Home-server-first setup with minimal operational overhead.

## Day 13 Deliverable

- Docker Compose stack added at [`docker/docker-compose.yml`](docker/docker-compose.yml)
- Backend image definition at [`docker/backend.Dockerfile`](docker/backend.Dockerfile)
- Usage guide at [`docker/README.md`](docker/README.md)
