import re
from dataclasses import dataclass

from llama_index.core import Document, StorageContext, VectorStoreIndex
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError, KnowledgeRetrievalError

from .documents import build_document_nodes, build_project_manual_nodes

_IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class KnowledgeStatus:
    schema: str
    table: str
    node_count: int
    embedding_model: str
    embedding_dimensions: int


class LlamaIndexKnowledgeStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _validate_configuration(self) -> None:
        missing: list[str] = []
        if self._settings.knowledge_database_url is None:
            missing.append("KNOWLEDGE_DATABASE_URL")
        if self._settings.dashscope_api_key is None:
            missing.append("DASHSCOPE_API_KEY")
        if not self._settings.qwen_embedding_base_url:
            missing.append("QWEN_EMBEDDING_BASE_URL")
        if missing:
            names = ", ".join(missing)
            raise KnowledgeConfigurationError(f"缺少知识库配置：{names}")
        for name, value in (
            ("KNOWLEDGE_SCHEMA", self._settings.knowledge_schema),
            ("KNOWLEDGE_TABLE", self._settings.knowledge_table),
        ):
            if not _IDENTIFIER_PATTERN.fullmatch(value):
                raise KnowledgeConfigurationError(f"{name} 只能包含小写字母、数字和下划线。")
        if self._settings.qwen_embedding_dimensions != 1024:
            raise KnowledgeConfigurationError("当前知识库要求 QWEN_EMBEDDING_DIMENSIONS=1024。")
        if not 1 <= self._settings.knowledge_top_k <= 20:
            raise KnowledgeConfigurationError("KNOWLEDGE_TOP_K 必须在 1 到 20 之间。")

    def _database_urls(self) -> tuple[URL, URL]:
        self._validate_configuration()
        secret = self._settings.knowledge_database_url
        assert secret is not None
        source = make_url(secret.get_secret_value())
        return (
            source.set(drivername="postgresql+psycopg2"),
            source.set(drivername="postgresql+asyncpg"),
        )

    def create_embedding_model(self) -> OpenAIEmbedding:
        self._validate_configuration()
        api_key = self._settings.dashscope_api_key
        assert api_key is not None
        assert self._settings.qwen_embedding_base_url is not None
        return OpenAIEmbedding(
            model_name=self._settings.qwen_embedding_model,
            api_key=api_key.get_secret_value(),
            api_base=self._settings.qwen_embedding_base_url,
            dimensions=self._settings.qwen_embedding_dimensions,
            embed_batch_size=10,
        )

    def create_vector_store(self) -> PGVectorStore:
        sync_url, async_url = self._database_urls()
        return PGVectorStore(
            connection_string=sync_url.render_as_string(hide_password=False),
            async_connection_string=async_url.render_as_string(hide_password=False),
            schema_name=self._settings.knowledge_schema,
            table_name=self._settings.knowledge_table,
            embed_dim=self._settings.qwen_embedding_dimensions,
            perform_setup=True,
            initialization_fail_on_error=True,
            use_jsonb=True,
            hnsw_kwargs={
                "hnsw_m": 16,
                "hnsw_ef_construction": 64,
                "hnsw_ef_search": 40,
                "hnsw_dist_method": "vector_cosine_ops",
            },
        )

    def initialize(self) -> None:
        try:
            self.create_vector_store().add([])
        except KnowledgeConfigurationError:
            raise
        except Exception as exc:
            raise KnowledgeRetrievalError("知识库数据库初始化失败。") from exc

    def rebuild(self) -> int:
        try:
            vector_store = self.create_vector_store()
            vector_store.clear()
            nodes = build_project_manual_nodes()
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            VectorStoreIndex(
                nodes,
                storage_context=storage_context,
                embed_model=self.create_embedding_model(),
                show_progress=False,
            )
            return len(nodes)
        except KnowledgeConfigurationError:
            raise
        except Exception as exc:
            raise KnowledgeRetrievalError("知识库重建失败。") from exc

    def add_document(self, document: Document) -> int:
        return self.add_nodes(build_document_nodes(document))

    def add_nodes(self, nodes: list[BaseNode]) -> int:
        try:
            vector_store = self.create_vector_store()
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            VectorStoreIndex(
                nodes,
                storage_context=storage_context,
                embed_model=self.create_embedding_model(),
                show_progress=False,
            )
            return len(nodes)
        except KnowledgeConfigurationError:
            raise
        except Exception as exc:
            raise KnowledgeRetrievalError("文档写入知识库失败。") from exc

    def delete_document(self, object_name: str) -> None:
        try:
            self.create_vector_store().delete_nodes(
                filters=MetadataFilters(
                    filters=[MetadataFilter(key="minio_object", value=object_name)]
                )
            )
        except KnowledgeConfigurationError:
            raise
        except Exception as exc:
            raise KnowledgeRetrievalError("文档向量清理失败。") from exc

    def create_retriever(self) -> BaseRetriever:
        vector_store = self.create_vector_store()
        index = VectorStoreIndex.from_vector_store(
            vector_store,
            embed_model=self.create_embedding_model(),
        )
        return index.as_retriever(similarity_top_k=self._settings.knowledge_top_k)

    def status(self) -> KnowledgeStatus:
        sync_url, _ = self._database_urls()
        table_name = f"data_{self._settings.knowledge_table}"
        statement = text(
            f'SELECT COUNT(*) FROM "{self._settings.knowledge_schema}"."{table_name}"'
        )
        try:
            with create_engine(sync_url).connect() as connection:
                node_count = int(connection.execute(statement).scalar_one())
        except Exception as exc:
            raise KnowledgeRetrievalError("无法读取知识库状态。") from exc
        return KnowledgeStatus(
            schema=self._settings.knowledge_schema,
            table=self._settings.knowledge_table,
            node_count=node_count,
            embedding_model=self._settings.qwen_embedding_model,
            embedding_dimensions=self._settings.qwen_embedding_dimensions,
        )
