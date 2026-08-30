# Repository boundaries

Repositories contain SQLAlchemy queries and transaction-specific persistence behavior. Services
depend on repository protocols or a unit of work and do not import ORM records. PostgreSQL-specific
upserts remain inside this package.
