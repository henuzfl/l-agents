from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode

SOURCE_NAME = "项目使用手册"

PROJECT_MANUAL_SECTIONS: tuple[tuple[str, str], ...] = (
    (
        "项目定位",
        "Enterprise Agent 是基于 FastAPI、OpenAI Agents SDK 和 DeepSeek 的多 Agent 骨架。"
        "系统由一个 Manager 和 agent1 至 agent4 四个子 Agent 组成。Manager 负责理解请求、"
        "调用子 Agent 并生成最终回答。",
    ),
    (
        "会话记忆",
        "只有 Manager 使用 SQLite Session。Session ID 格式为 user_id:conversation_id。"
        "使用相同的 user_id 和 conversation_id 可以继续多轮对话。子 Agent 不创建 Session，"
        "也不能访问 Manager 的历史消息。",
    ),
    (
        "知识库检索",
        "agent1 是项目知识检索 Agent。Manager 遇到项目架构、配置、运行或使用方式的问题时"
        "调用 agent1。agent1 通过 search_knowledge_base 工具检索 pgvector 中的项目手册证据，"
        "并在回答中标注来源。知识库不提供公开检索接口。",
    ),
    (
        "启动与接口",
        "使用 uvicorn app.main:app --reload --port 8091 启动服务。根路径提供聊天页面，"
        "GET /health 用于健康检查，POST /api/v1/chat 用于聊天。端口 8000 在部分 Windows"
        "环境中可能属于系统保留范围。",
    ),
    (
        "开发与测试",
        "使用 python -m pip install -e .[dev] 安装依赖。运行 pytest 执行离线测试，"
        "运行 ruff check . 检查代码，运行 python -m compileall app 验证 Python 模块编译。"
        "自动测试不得调用真实模型、embedding 服务或外部数据库。",
    ),
    (
        "安全配置",
        "DeepSeek、千问和 PostgreSQL 凭据必须通过 .env 或运行环境提供，不能写入代码或提交到"
        "版本库。服务启动不会自动创建或重建知识库；管理员必须显式执行知识库 CLI。",
    ),
)


def build_project_manual_documents() -> list[Document]:
    return [
        Document(text=text, metadata={"source": SOURCE_NAME, "section": section})
        for section, text in PROJECT_MANUAL_SECTIONS
    ]


def build_project_manual_nodes(
    chunk_size: int = 512,
    chunk_overlap: int = 80,
) -> list[BaseNode]:
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.get_nodes_from_documents(build_project_manual_documents())
