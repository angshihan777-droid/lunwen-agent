# 论文研究 Agent

一个基于 FastAPI、LangChain 和 RAG 的学术论文智能研究助手。项目支持上传 PDF 论文、结构化提取论文信息、生成中文摘要、多论文对比、研究缺口分析、连续问答、ArXiv 检索和网络检索，适合课程作业、论文阅读、文献综述和研究选题辅助。

## 功能特点

| 功能 | 说明 |
| --- | --- |
| PDF 论文上传 | 读取 PDF 文本，并为论文建立可检索的 RAG 索引 |
| 结构化提取 | 自动提取研究问题、方法、数据集、指标、结论和局限性，输出标准 JSON |
| 中文摘要 | 为单篇论文生成简明中文摘要 |
| 多轮问答 | 基于会话记忆持续追问论文内容 |
| 多论文对比 | 对多篇论文生成 Markdown 对比表 |
| 研究缺口分析 | 综合多篇论文，分析未解决问题和后续研究方向 |
| ArXiv 检索 | 按关键词搜索相关论文 |
| 网络检索 | 通过 Tavily 查询作者动态、引用背景和补充资料 |
| 多用户会话隔离 | 通过 `X-Session-ID` 区分不同浏览器会话的配置、论文和记忆 |

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 后端服务 | FastAPI、Uvicorn |
| Agent 框架 | LangChain、AgentExecutor、ReAct Agent |
| LLM 接入 | OpenAI、Anthropic、DeepSeek、自定义 OpenAI 兼容接口 |
| RAG | RecursiveCharacterTextSplitter、FAISS |
| PDF 解析 | PyMuPDF |
| 结构化输出 | Pydantic v2、PydanticOutputParser |
| 前端 | 原生 HTML、JavaScript、Tailwind CSS |
| 测试 | Pytest、FastAPI TestClient |
| 部署 | Docker、docker compose、Procfile |

## 项目结构

```text
lunwen-agent/
├── main.py                  # FastAPI 入口、路由和会话中间件
├── config.py                # LLM 配置和多会话配置隔离
├── requirements.txt         # Python 依赖
├── Dockerfile
├── docker-compose.yml
├── Procfile
├── frontend/
│   ├── index.html           # Web 主界面
│   └── app.js               # 前端交互、会话、上传和任务调用
├── agents/
│   └── research_agent.py    # ReAct Agent、普通聊天和步骤收集
├── tools/
│   ├── extract_tool.py      # 结构化提取
│   ├── summary_tool.py      # 摘要生成
│   ├── search_tool.py       # RAG 语义检索
│   ├── compare_tool.py      # 多论文对比
│   ├── gap_tool.py          # 研究缺口分析
│   ├── citation_tool.py     # 参考文献提取
│   ├── arxiv_tool.py        # ArXiv 检索
│   └── web_search_tool.py   # Tavily 网络检索
├── prompts/                 # 各任务 Prompt
├── rag/
│   ├── loader.py            # PDF 文本读取
│   ├── splitter.py          # 文本分块
│   └── vectorstore.py       # FAISS 索引管理
├── memory/
│   └── session_memory.py    # 会话记忆
├── schemas/
│   └── paper_schema.py      # 论文结构化输出模型
├── tests/                   # 单元测试和 API 测试
├── eval/                    # LLM 输出质量评估脚本
└── uploads/                 # 运行时上传目录，不纳入 Git
```

## 快速开始

### 1. 创建虚拟环境

```bash
python -m venv venv
```

Windows:

```bash
venv\Scripts\activate
```

macOS / Linux:

```bash
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

复制示例文件：

```bash
cp .env.example .env
```

然后填写需要使用的模型服务 Key。也可以不创建 `.env`，启动后直接在前端左侧的 LLM 配置面板中填写。

支持的配置项：

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_BASE_URL=
```

### 4. 启动服务

```bash
uvicorn main:app --reload --port 8000
```

打开浏览器访问：

```text
http://localhost:8000
```

## Docker 运行

首次构建并启动：

```bash
docker compose up --build
```

后台运行：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 返回前端页面 |
| `POST` | `/config` | 设置当前会话的 LLM 配置 |
| `POST` | `/models` | 查询模型配置 |
| `POST` | `/ping` | 测试模型连接 |
| `POST` | `/upload` | 上传 PDF 并构建索引 |
| `POST` | `/extract` | 结构化提取论文信息 |
| `POST` | `/summary` | 生成论文摘要 |
| `POST` | `/chat` | 多轮论文问答 |
| `POST` | `/compare` | 多论文对比 |
| `POST` | `/gap` | 研究缺口分析 |
| `POST` | `/arxiv` | ArXiv 检索 |
| `GET` | `/papers` | 获取当前会话论文列表 |
| `DELETE` | `/papers/{paper_id}` | 删除当前会话中的论文 |
| `POST` | `/reset` | 重置当前会话 |

多会话调用时建议传入：

```http
X-Session-ID: your-session-id
```

## 运行测试

```bash
python -m pytest tests/ -v
```

测试覆盖内容包括：

| 文件 | 覆盖内容 |
| --- | --- |
| `tests/test_session_isolation.py` | 多用户配置、论文和会话隔离 |
| `tests/test_rag_pipeline.py` | PDF 加载、文本分块和 metadata |
| `tests/test_api_endpoints.py` | API 可达性、参数校验和错误处理 |
| `tests/test_tool_logic.py` | 工具业务校验（对比/缺口至少 2 篇、论文不存在提示） |
| `tests/test_isolation_and_errors.py` | FAISS 会话隔离、TTL 淘汰、系统故障错误处理 |

## LLM 质量评估

启动服务后，可运行评估脚本：

```bash
python eval/eval.py --api-key sk-xxx --provider openai --model gpt-4o
```

评估内容包括结构化提取、摘要质量、多论文对比、研究缺口分析和多轮会话记忆效果。

## 设计说明

### 会话隔离

项目通过 `X-Session-ID` 识别用户会话，并使用 `ContextVar` 路由到独立的配置、论文列表、对话记忆和 FAISS 索引，避免不同浏览器或用户之间互相污染数据。向量索引同样按会话隔离，A 用户检索不会召回 B 用户上传的论文。

会话数据存放在带闲置过期（TTL）与容量上限的缓存中（默认 2 小时无访问即淘汰），避免长期运行时内存被不断新建的会话占满。

### RAG 检索

上传论文后，系统会使用 PyMuPDF 读取正文，按固定窗口切分为 LangChain `Document`，再写入 FAISS。问答和检索工具根据语义相似度召回相关片段，降低长论文直接塞入上下文带来的 token 压力。

### 专用工具和 Prompt

结构化提取、摘要、对比和研究缺口分析分别使用独立工具与 Prompt。这样可以针对每类任务约束输出格式，避免一个通用 Prompt 同时承担多种目标导致结果不稳定。

## 注意事项

- `.env`、`uploads/`、`venv/`、缓存文件和 PDF 文件不会提交到 Git。
- 若使用 OpenAI 兼容中转服务，请同时配置 `OPENAI_BASE_URL` 和对应 API Key。
- FAISS 索引和会话状态主要保存在运行时内存中，服务重启或会话闲置超时（默认 2 小时）后需要重新上传论文。
- 本项目 **未内置身份验证或访问控制**，仅供本地开发与演示使用。若需公网部署，请自行在网关或应用层补充鉴权，否则任何人都可调用上传与检索接口（消耗你的 API Key 额度）。
- Tavily Key 只在使用网络检索功能时需要。

## 许可证

当前项目未声明开源许可证。公开仓库如需允许他人复用代码，建议补充 `LICENSE` 文件。
