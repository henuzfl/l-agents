import argparse
from collections.abc import Callable, Sequence

from app.core.config import Settings
from app.core.exceptions import KnowledgeConfigurationError, KnowledgeRetrievalError

from .store import LlamaIndexKnowledgeStore

StoreFactory = Callable[[Settings], LlamaIndexKnowledgeStore]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the project knowledge base.")
    parser.add_argument("command", choices=("init", "rebuild", "status"))
    return parser


def run_command(
    command: str,
    settings: Settings,
    store_factory: StoreFactory = LlamaIndexKnowledgeStore,
) -> str:
    store = store_factory(settings)
    if command == "init":
        store.initialize()
        return "知识库数据库初始化完成。"
    if command == "rebuild":
        node_count = store.rebuild()
        return f"知识库重建完成，共写入 {node_count} 个节点。"
    status = store.status()
    return (
        f"知识库状态：{status.schema}.{status.table}，节点 {status.node_count}，"
        f"模型 {status.embedding_model}，维度 {status.embedding_dimensions}。"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(run_command(args.command, Settings()))
    except (KnowledgeConfigurationError, KnowledgeRetrievalError) as exc:
        print(f"错误：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
