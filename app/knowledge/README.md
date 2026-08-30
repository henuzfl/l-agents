# Knowledge boundaries

- `domain`: document job state and value objects.
- `ingestion`: parsing and PDF processing entrypoints.
- `retrieval`: online search service and Agent tool entrypoints.
- `storage`: MinIO and pgvector adapters.

HTTP routes must call blocking document operations through a threadpool. Only the knowledge Agent
may receive the retrieval tool.
