# Auth boundaries

Authentication is split into password hashing, JWT encoding, application rules, and persistence
ports. HTTP cookie and bearer handling stays at the API boundary. The service must not import
FastAPI or SQLAlchemy models.
