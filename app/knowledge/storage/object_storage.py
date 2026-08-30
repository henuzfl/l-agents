from io import BytesIO

from minio import Minio

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError, KnowledgeRetrievalError


class MinioDocumentStorage:
    def __init__(self, settings: Settings, client: Minio | None = None) -> None:
        if not settings.minio_endpoint:
            raise KnowledgeConfigurationError("缺少 MinIO 配置：MINIO_ENDPOINT")
        if not settings.minio_access_key:
            raise KnowledgeConfigurationError("缺少 MinIO 配置：MINIO_ACCESS_KEY")
        if settings.minio_secret_key is None:
            raise KnowledgeConfigurationError("缺少 MinIO 配置：MINIO_SECRET_KEY")
        self._bucket = settings.minio_bucket
        self._client = client or Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key.get_secret_value(),
            secure=settings.minio_secure,
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def upload(self, object_name: str, content: bytes, content_type: str) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
            self._client.put_object(
                self._bucket,
                object_name,
                BytesIO(content),
                length=len(content),
                content_type=content_type,
            )
        except Exception as exc:
            raise KnowledgeRetrievalError("原始文档上传 MinIO 失败。") from exc

    def download(self, object_name: str) -> bytes:
        response = None
        try:
            response = self._client.get_object(self._bucket, object_name)
            return response.read()
        except Exception as exc:
            raise KnowledgeRetrievalError("无法从 MinIO 读取原始文档。") from exc
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def delete(self, object_name: str) -> None:
        try:
            self._client.remove_object(self._bucket, object_name)
        except Exception as exc:
            raise KnowledgeRetrievalError("MinIO 原始文档删除失败。") from exc

    def delete_assets(self, object_name: str) -> None:
        asset_prefix = f"{object_name.rsplit('/', 1)[0]}/assets/"
        try:
            for item in self._client.list_objects(
                self._bucket,
                prefix=asset_prefix,
                recursive=True,
            ):
                self._client.remove_object(self._bucket, item.object_name)
        except Exception as exc:
            raise KnowledgeRetrievalError("MinIO 文档图片清理失败。") from exc
