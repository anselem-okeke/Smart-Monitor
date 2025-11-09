### Smart-Monitor: Containerized Deployment (Rich Ops Docs)

Smart-Monitor: Containerized Deployment (Rich Ops Docs)

This document explains exactly how the Docker Compose stack is meant to run your Smart-Monitor in a realistic environment, why each piece exists, and how to reason about lab vs production hardening. It also covers service-state collection from the host (the tricky bit), database initialization, health checks, observability, security posture, and operational runbooks. No code snippets are required to use this doc; commands are illustrative.

you ever see “unknown” again: it’s almost always not talking to host systemd correctly—verify sockets, D-Bus address, and that the shim mode is in effect.