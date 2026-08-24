# ADR 0001: SQLite with Write-Ahead Logging (WAL) for Self-Hosted Portability

## Status
Accepted

## Context
CareerQuest requires a persistent, low-overhead database engine to manage candidate profiles, application tracking pipelines, discovery digests, and historical snapshot vaults. The system is designed to be easily deployed on single-board computers, NAS devices, or self-hosted Portainer environments without requiring multi-container database infrastructure (e.g., PostgreSQL / MySQL).

## Decision
We chose SQLite with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and `PRAGMA synchronous=NORMAL` as the primary storage engine.

## Consequences
### Positive
* **Zero Configuration**: Eliminates external database dependency management, network connection pooling, and separate container maintenance.
* **Concurrency**: WAL mode allows concurrent read operations while writes are in progress without locking the database.
* **Portability**: All candidate data resides in a single `/app/data/career_quest.db` file, enabling instant backups and volume transfers.

### Negative
* High-scale distributed multi-server clustering is not natively supported (acceptable given the self-hosted, single-user/team target architecture).
