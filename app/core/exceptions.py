class AgentApplicationError(Exception):
    """Base exception safe to translate at the HTTP boundary."""


class ConfigurationError(AgentApplicationError):
    """Application configuration is invalid."""


class SessionError(AgentApplicationError):
    """A short-term session could not be created or accessed."""


class AgentExecutionError(AgentApplicationError):
    """The manager agent failed to execute."""


class KnowledgeConfigurationError(ConfigurationError):
    """Knowledge-base configuration is incomplete or invalid."""


class KnowledgeRetrievalError(AgentApplicationError):
    """Knowledge retrieval or indexing failed."""
