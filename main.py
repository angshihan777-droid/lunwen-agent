"""
main.py — FastAPI 入口

所有 API endpoints 定义在这里。
启动命令：uvicorn main:app --reload --port 8000
"""

import asyncio
import contextvars
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import update_config, session_config, get_llm, _current_session
from rag.loader import load_pdf
from rag.splitter import split_text
import rag.vectorstore as vs
from tools.extract_tool import paper_texts, extract_tool
from tools.summary_tool import summary_tool
from tools.compare_tool import compare_tool
from tools.gap_tool import gap_tool
from memory.session_memory import reset_memory
from agents.research_agent import run_agent, run_chat

# ── 日志配置 ───────────────────────────────
# 工具/服务层的系统故障通过 logging 落盘，便于排查；不再静默吞掉。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ── 应用初始化 ──────────────────────────────────────────────
app = FastAPI(
    title="论文研究 Agent",
    description="基于 LangChain 的学术论文智能研究助手",
    version="1.0.0",
)

# ── 会话隔离中间件 ───────────────────────────────────────────
# 前端每次请求携带 X-Session-ID 头；中间件把它写入 ContextVar，
# 使当前请求全链路（config / memory / paper_texts）都隔离在该会话下。
@app.middleware("http")
async def session_middleware(request: Request, call_next):
    session_id = request.headers.get("X-Session-ID", "__default__")
    token = _current_session.set(session_id)
    try:
        response = await call_next(request)
    finally:
        _current_session.reset(token)
    return response

# 上传文件存放目录
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 上传大小上限：整机内存有限，流式落盘时超过即中止，避免大文件打爆内存/磁盘
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
UPLOAD_CHUNK_BYTES = 1024 * 1024  # 每次从上传流读取的块大小

# 挂载前端静态文件
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.on_event("startup")
async def load_demo_paper():
    """启动时自动生成并加载 3 篇演示论文，覆盖所有核心功能的演示需求。"""
    demos = [
        ("demo_multiagent_survey",  _create_demo_pdf),
        ("demo_transformer_attention", _create_demo_transformer_pdf),
        ("demo_bert_pretraining",      _create_demo_bert_pdf),
    ]
    for demo_id, creator_fn in demos:
        demo_path = UPLOAD_DIR / f"{demo_id}.pdf"
        if not demo_path.exists():
            creator_fn(str(demo_path))
        try:
            full_text, _ = load_pdf(str(demo_path))
            if full_text.strip():
                paper_texts[demo_id] = full_text
        except Exception:
            pass


def _create_demo_pdf(path: str):
    """用 PyMuPDF 生成一份仿学术论文格式的演示 PDF。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return

    DEMO_CONTENT = [
        ("Multi-Agent Systems: A Survey on Coordination and Collaboration",
         28, True),
        ("Abstract", 14, True),
        (
            "Multi-agent systems (MAS) have emerged as a powerful paradigm for solving "
            "complex problems that are beyond the capability of single agents. This survey "
            "provides a comprehensive review of coordination mechanisms, communication "
            "protocols, and collaborative learning strategies in modern MAS. We analyze "
            "over 150 papers from 2018-2024, categorize existing approaches, and identify "
            "key research gaps. Our findings suggest that while significant progress has "
            "been made in homogeneous agent settings, heterogeneous multi-agent "
            "coordination under partial observability remains largely unsolved.",
            11, False,
        ),
        ("1. Introduction", 14, True),
        (
            "The field of multi-agent systems has witnessed exponential growth following "
            "the success of reinforcement learning in single-agent environments. Agents "
            "must coordinate actions, share knowledge, and resolve conflicts to achieve "
            "collective goals. Unlike centralized systems, MAS operates under decentralized "
            "control, making coordination both challenging and essential.\n\n"
            "Key challenges include: (1) scalability — most algorithms degrade as agent "
            "count grows; (2) non-stationarity — each agent's environment changes as "
            "other agents learn; (3) credit assignment — determining each agent's "
            "contribution to collective outcomes.",
            11, False,
        ),
        ("2. Research Problem", 14, True),
        (
            "This survey addresses the following research questions:\n"
            "  RQ1: What coordination mechanisms achieve the best trade-off between "
            "communication overhead and task performance?\n"
            "  RQ2: How do state-of-the-art algorithms scale with the number of agents?\n"
            "  RQ3: Which domains have seen the most significant real-world deployments?\n\n"
            "We focus specifically on cooperative MAS where agents share a common "
            "objective function, as opposed to competitive or mixed-motive settings.",
            11, False,
        ),
        ("3. Methodology", 14, True),
        (
            "We conducted a systematic literature review following PRISMA guidelines. "
            "Papers were collected from ACL, NeurIPS, ICML, ICLR, and AAMAS between "
            "2018 and 2024. Inclusion criteria: (a) proposes a novel MAS algorithm or "
            "framework; (b) evaluated on at least one standard benchmark; "
            "(c) peer-reviewed.\n\n"
            "Classification dimensions:\n"
            "  - Communication: explicit message-passing vs. implicit through actions\n"
            "  - Learning: centralized training with decentralized execution (CTDE) vs. "
            "fully decentralized\n"
            "  - Scalability: tested on >10 agents vs. small-scale settings\n\n"
            "Datasets used across surveyed papers: SMAC (StarCraft Multi-Agent Challenge), "
            "Google Research Football, Cooperative Navigation, Multi-Robot Warehouse.",
            11, False,
        ),
        ("4. Results & Key Findings", 14, True),
        (
            "4.1 Coordination Mechanisms\n"
            "CTDE methods (QMIX, MAPPO, HAPPO) dominate benchmark leaderboards, "
            "achieving 85-95% win rates on SMAC hard scenarios. However, they require "
            "centralized state access during training — impractical for many real-world "
            "deployments.\n\n"
            "4.2 Communication Protocols\n"
            "Attention-based communication (ATOC, TarMAC) outperforms broadcast by 23% "
            "on average but adds 40% latency overhead. Emergent communication protocols "
            "show promise but remain brittle under distribution shift.\n\n"
            "4.3 Scalability\n"
            "Only 12% of surveyed papers test on >20 agents. Mean-field approximations "
            "(MF-Q, MF-AC) scale to 100+ agents but sacrifice per-agent expressiveness. "
            "Graph neural network approaches show the best scaling characteristics.",
            11, False,
        ),
        ("5. Research Gaps & Limitations", 14, True),
        (
            "Despite significant progress, major gaps remain:\n\n"
            "Gap 1 — Heterogeneous agents: Most benchmarks assume homogeneous agents "
            "with identical action spaces. Real deployments (logistics, disaster response) "
            "involve agents with different capabilities.\n\n"
            "Gap 2 — Partial observability at scale: Existing CTDE methods assume global "
            "state during training. Truly decentralized learning under partial observability "
            "is understudied.\n\n"
            "Gap 3 — Sim-to-real transfer: Only 8% of papers report physical robot "
            "experiments. The gap between simulation and reality for multi-robot systems "
            "is poorly characterized.\n\n"
            "Gap 4 — Safety and robustness: Adversarial agents and Byzantine failures "
            "are rarely considered in cooperative MAS literature.",
            11, False,
        ),
        ("6. Conclusion", 14, True),
        (
            "This survey provides the most comprehensive review of cooperative multi-agent "
            "systems to date. While CTDE methods have achieved remarkable results in "
            "simulation, real-world deployment faces fundamental challenges around "
            "heterogeneity, scalability, and safety. Future work should prioritize "
            "benchmarks that reflect real deployment conditions and develop algorithms "
            "that remain effective when centralized training is unavailable.\n\n"
            "We release a curated dataset of 150+ papers with standardized metadata at "
            "github.com/mas-survey/dataset to facilitate future meta-analyses.",
            11, False,
        ),
        ("References", 14, True),
        (
            "[1] Rashid et al. (2018). QMIX: Monotonic Value Function Factorisation. ICML.\n"
            "[2] Yu et al. (2021). The Surprising Effectiveness of MAPPO in Cooperative MAS. NeurIPS.\n"
            "[3] Jiang & Lu (2018). Learning Attentional Communication. NeurIPS.\n"
            "[4] Yang et al. (2018). Mean Field Multi-Agent Reinforcement Learning. ICML.\n"
            "[5] Wang et al. (2020). ROMA: Multi-Agent RL with Emergent Roles. ICML.\n"
            "[6] Kuba et al. (2021). HAPPO: Trust Region Policy Optimisation in MARL. ICLR.\n"
            "[7] Papoudakis et al. (2021). Benchmarking Multi-Agent Deep RL Algorithms. NeurIPS.",
            10, False,
        ),
    ]

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    y = 60

    for text, size, bold in DEMO_CONTENT:
        fontname = "helv"
        color = (0, 0, 0)
        if bold:
            color = (0.1, 0.1, 0.5) if size > 20 else (0, 0, 0)

        # 逐段写入，自动换行
        rect = fitz.Rect(50, y, 545, 800)
        rc = page.insert_textbox(
            rect,
            text + "\n",
            fontsize=size,
            fontname=fontname,
            color=color,
        )
        # rc < 0 表示页面放不下，新开一页
        if rc < 0:
            page = doc.new_page(width=595, height=842)
            y = 60
            rect = fitz.Rect(50, y, 545, 800)
            rc = page.insert_textbox(rect, text + "\n", fontsize=size,
                                     fontname=fontname, color=color)

        # 估算下一段起始 y（按行数和字号）
        lines = text.count("\n") + max(1, len(text) // 70)
        y += lines * (size * 1.4) + 10
        if y > 760:
            page = doc.new_page(width=595, height=842)
            y = 60

    doc.save(path)
    doc.close()


def _write_demo_pdf(path: str, title: str, sections: list):
    """通用 demo PDF 生成器。sections = [(heading, body), ...]"""
    try:
        import fitz
    except ImportError:
        return

    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)
    y    = 55

    def ensure_space(needed=50):
        nonlocal page, y
        if y + needed > 800:
            page = doc.new_page(width=595, height=842)
            y = 55

    # 标题
    rect = fitz.Rect(50, y, 545, y + 80)
    page.insert_textbox(rect, title + "\n", fontsize=20,
                        fontname="helv", color=(0.1, 0.1, 0.5))
    y += 65

    for heading, body in sections:
        ensure_space(55)
        # 小节标题
        rect = fitz.Rect(50, y, 545, y + 25)
        page.insert_textbox(rect, heading + "\n", fontsize=13,
                            fontname="helv", color=(0, 0, 0))
        y += 22
        # 正文
        ensure_space(30)
        rect = fitz.Rect(50, y, 545, 800)
        rc = page.insert_textbox(rect, body + "\n\n", fontsize=10,
                                 fontname="helv", color=(0.1, 0.1, 0.1))
        if rc < 0:
            page = doc.new_page(width=595, height=842)
            y = 55
            rect = fitz.Rect(50, y, 545, 800)
            page.insert_textbox(rect, body + "\n\n", fontsize=10,
                                fontname="helv", color=(0.1, 0.1, 0.1))
        lines = body.count("\n") + max(1, len(body) // 80)
        y += lines * 14 + 18
        if y > 760:
            page = doc.new_page(width=595, height=842)
            y = 55

    doc.save(path)
    doc.close()


def _create_demo_transformer_pdf(path: str):
    """演示论文 2：Transformer — Attention Is All You Need（精简版）"""
    _write_demo_pdf(path,
        "Attention Is All You Need: A Transformer-Based Sequence Transduction Model",
        [
            ("Abstract",
             "The dominant sequence transduction models are based on complex recurrent or "
             "convolutional neural networks. We propose the Transformer, a model architecture "
             "based solely on attention mechanisms, dispensing with recurrence and convolutions "
             "entirely. Experiments on two machine translation tasks show the Transformer "
             "generalizes well to other tasks, achieving 28.4 BLEU on WMT 2014 English-German "
             "and 41.0 BLEU on English-French, outperforming the previous state-of-the-art at "
             "a fraction of the training cost."),
            ("1. Research Problem",
             "Recurrent models (RNNs, LSTMs) process sequences token by token, preventing "
             "parallelization and struggling with long-range dependencies. Convolutional "
             "approaches require many layers to relate distant positions. This paper asks: "
             "can we build a seq2seq model with no recurrence or convolution, relying "
             "entirely on attention?"),
            ("2. Methodology",
             "The Transformer uses an encoder-decoder structure.\n"
             "  Encoder: 6 identical layers, each with (a) multi-head self-attention and "
             "(b) position-wise feed-forward network. Residual connections + layer norm.\n"
             "  Decoder: 6 layers with additional cross-attention over encoder output.\n"
             "  Multi-Head Attention: h=8 heads, d_model=512, d_k=d_v=64. Queries, keys, "
             "and values are linearly projected h times in parallel.\n"
             "  Positional Encoding: sine/cosine functions injected at input embeddings "
             "to preserve sequence order without recurrence."),
            ("3. Dataset & Experimental Setup",
             "Training data:\n"
             "  - WMT 2014 English-German: 4.5 million sentence pairs\n"
             "  - WMT 2014 English-French: 36 million sentence pairs\n"
             "Byte-pair encoding (BPE) vocabulary of 37,000 tokens (EN-DE) shared between "
             "source and target. Adam optimizer with warmup schedule (4,000 warmup steps). "
             "Trained on 8 NVIDIA P100 GPUs; base model 100k steps (12 hours), big model "
             "300k steps (3.5 days)."),
            ("4. Results & Metrics",
             "BLEU scores on newstest2014:\n"
             "  - EN-DE: 28.4 BLEU (+2.0 over previous best ensemble)\n"
             "  - EN-FR: 41.0 BLEU (new single-model SOTA)\n"
             "Training cost: Transformer base = 3.3e18 FLOPs vs 1.0e19 FLOPs for "
             "ConvS2S. Big model: 2.8× cheaper than prior SOTA.\n"
             "English constituency parsing: 92.7 F1 (WSJ23), competitive with "
             "task-specific RNN grammar parsers despite no task-specific tuning."),
            ("5. Conclusions",
             "The Transformer is the first transduction model relying entirely on "
             "self-attention. It trains significantly faster than architectures based on "
             "recurrent or convolutional layers. Attention heads learn interpretable "
             "linguistic structures (syntactic and semantic roles). The architecture "
             "generalizes beyond translation, providing a strong foundation for future "
             "pre-trained language models (BERT, GPT, etc.)."),
            ("6. Limitations",
             "1. Quadratic complexity: Self-attention is O(n^2) in sequence length, "
             "making very long documents expensive.\n"
             "2. Fixed context window: Cannot natively handle sequences longer than "
             "a preset maximum.\n"
             "3. No inductive position bias: Positional encoding is hand-crafted; "
             "learned relative positions may generalize better.\n"
             "4. Large memory footprint: Storing all attention matrices requires "
             "significant GPU memory for long sequences."),
            ("References",
             "[1] Bahdanau et al. (2015). Neural Machine Translation by Jointly Learning to Align and Translate.\n"
             "[2] Luong et al. (2015). Effective Approaches to Attention-Based NMT.\n"
             "[3] Wu et al. (2016). Google's Neural Machine Translation System.\n"
             "[4] Gehring et al. (2017). Convolutional Sequence to Sequence Learning.\n"
             "[5] Ba et al. (2016). Layer Normalization."),
        ]
    )


def _create_demo_bert_pdf(path: str):
    """演示论文 3：BERT — Pre-training of Deep Bidirectional Transformers（精简版）"""
    _write_demo_pdf(path,
        "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        [
            ("Abstract",
             "We introduce BERT (Bidirectional Encoder Representations from Transformers), "
             "a new language representation model that pre-trains deep bidirectional "
             "representations by jointly conditioning on both left and right context in "
             "all layers. BERT can be fine-tuned with just one additional output layer to "
             "create state-of-the-art models for a wide range of NLP tasks without "
             "substantial task-specific architecture modifications."),
            ("1. Research Problem",
             "Existing language models are unidirectional (GPT: left-to-right; ELMo: "
             "shallow concatenation of two directions), limiting the quality of contextual "
             "representations. The question is: can deep bidirectional pre-training yield "
             "a universal language representation that transfers to diverse NLP tasks "
             "via minimal fine-tuning rather than task-specific architectures?"),
            ("2. Methodology",
             "Architecture: 12-layer (BERT-Base) or 24-layer (BERT-Large) Transformer "
             "encoder. BERT-Large: L=24, H=1024, A=16, 340M parameters.\n\n"
             "Pre-training objectives (trained jointly):\n"
             "  (a) Masked Language Model (MLM): 15% of input tokens are randomly masked; "
             "model predicts them using bidirectional context. Avoids left-to-right bias.\n"
             "  (b) Next Sentence Prediction (NSP): Binary classification of whether "
             "sentence B actually follows sentence A. Teaches inter-sentence understanding.\n\n"
             "Fine-tuning: A single additional classification layer is added on top of "
             "[CLS] token. All parameters are jointly fine-tuned end-to-end."),
            ("3. Dataset & Experimental Setup",
             "Pre-training corpus:\n"
             "  - BooksCorpus: 800M words (long coherent text)\n"
             "  - English Wikipedia: 2,500M words (text only, no lists/tables)\n"
             "Total: ~3.3B words. WordPiece vocabulary of 30,522 tokens.\n"
             "Pre-training: 1M steps, batch 256 sequences × 512 tokens = 131K tokens/batch.\n"
             "Hardware: 16 TPU v3 chips (BERT-Base: 4 days; BERT-Large: ~18 days).\n\n"
             "Fine-tuning benchmarks: GLUE, SQuAD 1.1/2.0, SWAG, NER (CoNLL-2003)."),
            ("4. Results & Metrics",
             "GLUE benchmark:\n"
             "  BERT-Large: 80.5 average (previous SOTA: 72.8, +7.7 improvement)\n"
             "SQuAD 1.1 (reading comprehension):\n"
             "  F1: 93.2, EM: 86.7 — surpassing human performance (F1: 91.2)\n"
             "SQuAD 2.0: F1 86.3 (+5.1 over prior SOTA)\n"
             "SWAG (commonsense inference): 86.3% (+27.1% over ESIM+ELMo)\n"
             "Named Entity Recognition (CoNLL-2003): 92.8 F1\n"
             "Ablation: Removing NSP drops SQuAD by 1.0 F1; removing bidirectionality "
             "drops MNLI by 5.6%."),
            ("5. Conclusions",
             "BERT demonstrates that unsupervised deep bidirectional pre-training is "
             "critical for strong language understanding. The masked LM objective enables "
             "truly bidirectional representations. A single pre-trained BERT model can "
             "be fine-tuned for 11 different NLP tasks, setting new state-of-the-art on "
             "most of them. This shifts the NLP paradigm from feature-based to "
             "fine-tuning-based transfer learning."),
            ("6. Limitations",
             "1. Encoder-only: BERT cannot generate text autoregressively; unsuitable "
             "for open-ended generation tasks (GPT is better here).\n"
             "2. 512 token limit: Cannot process documents longer than 512 tokens natively.\n"
             "3. Compute cost: Pre-training requires 16 TPUs for days; inaccessible "
             "to most researchers.\n"
             "4. MLM discrepancy: [MASK] tokens seen during pre-training don't appear "
             "at fine-tuning, creating a mismatch.\n"
             "5. NSP may be too easy: Later work (RoBERTa) found NSP hurts performance "
             "and removed it."),
            ("References",
             "[1] Vaswani et al. (2017). Attention Is All You Need. NeurIPS.\n"
             "[2] Radford et al. (2018). Improving Language Understanding by Generative Pre-Training. OpenAI.\n"
             "[3] Peters et al. (2018). Deep Contextualized Word Representations (ELMo). NAACL.\n"
             "[4] Liu et al. (2019). RoBERTa: A Robustly Optimized BERT Pretraining. arXiv.\n"
             "[5] Rajpurkar et al. (2016). SQuAD: 100,000+ Questions for Reading Comprehension."),
        ]
    )


# ── Request / Response 模型 ─────────────────────────────────
# Pydantic BaseModel 用于 FastAPI 自动解析请求体 + 生成 /docs 文档

class ConfigRequest(BaseModel):
    llm_provider: str        # openai / deepseek / custom / anthropic
    llm_api_key: str
    tavily_api_key: str = ""
    llm_base_url: str = ""   # 中转站时填写
    llm_model: str = ""      # 用户选择的模型名


class ChatRequest(BaseModel):
    message: str
    paper_id: str = ""  # 可选，指定当前在看哪篇论文


class PaperIdsRequest(BaseModel):
    paper_ids: list[str]  # 多篇论文的 ID 列表


class SinglePaperRequest(BaseModel):
    paper_id: str


# ── Endpoints ────────────────────────────────────────────────
#
# 路由总览：
#   GET  /                 → 前端主页
#   POST /config           → 保存 LLM API Key（会话隔离）
#   POST /models           → 获取该 provider 的模型列表
#   POST /ping             → 连通性测试（验证 Key + 模型是否可用）
#   POST /upload           → 上传 PDF，构建 FAISS 索引
#   GET  /papers           → 列出已上传论文
#   DELETE /papers/{id}    → 删除指定论文
#   POST /extract          → 结构化信息提取（F2）
#   POST /summary          → 快速摘要生成（F3）
#   POST /chat             → 多轮对话问答（F4）
#   POST /compare          → 多篇论文对比（F5）
#   POST /gap              → 研究缺口识别（F6）
#   POST /arxiv            → ArXiv 搜索
#   POST /reset            → 重置对话记忆

@app.get("/")
async def index():
    """返回前端主页"""
    return FileResponse("frontend/index.html")


@app.post("/config")
async def save_config(req: ConfigRequest):
    """
    保存用户的 API Key 到内存。
    前端设置面板"保存"按钮调用这个接口。
    """
    if not req.llm_api_key:
        raise HTTPException(status_code=400, detail="LLM API Key 不能为空")
    if req.llm_provider not in ("openai", "deepseek", "custom", "anthropic"):
        raise HTTPException(status_code=400, detail="llm_provider 不支持，可选：openai / deepseek / custom / anthropic")

    update_config(
        llm_provider=req.llm_provider,
        llm_api_key=req.llm_api_key,
        tavily_api_key=req.tavily_api_key,
        llm_base_url=req.llm_base_url,
        llm_model=req.llm_model,
    )
    # 切换 LLM 时重置记忆，避免旧 key 的记忆混入
    reset_memory()
    return {"status": "ok", "message": f"配置已保存，使用 {req.llm_provider}"}


@app.post("/models")
async def fetch_models(req: ConfigRequest):
    """
    根据用户填写的 provider / api_key / base_url，
    调用对应 OpenAI 兼容接口的 GET /models，返回模型列表。
    Anthropic 不支持此接口，直接返回固定列表。
    """
    import httpx

    if req.llm_provider == "anthropic":
        # Anthropic 无 /models 端点，返回常用 Claude 模型
        return {"models": [
            "claude-opus-4-5",
            "claude-sonnet-4-5",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]}

    if req.llm_provider == "deepseek":
        candidates = ["https://api.deepseek.com/v1"]
    elif req.llm_provider == "custom":
        raw = req.llm_base_url.rstrip("/")
        if not raw:
            raise HTTPException(status_code=400, detail="使用中转站时请填写 Base URL")
        # 同时尝试带 /v1 和不带 /v1 两种路径，兼容不同代理
        with_v1    = raw if raw.endswith("/v1") else raw + "/v1"
        without_v1 = raw[:-3] if raw.endswith("/v1") else raw
        candidates = [with_v1, without_v1]
    else:
        candidates = ["https://api.openai.com/v1"]

    last_error = ""
    async with httpx.AsyncClient(timeout=15, verify=False) as client:
        for base_url in candidates:
            try:
                resp = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {req.llm_api_key}"},
                )
                if resp.status_code == 200:
                    # body 可能为空（代理返回 200 但无内容），需要防御
                    try:
                        data = resp.json()
                    except Exception:
                        last_error = f"{base_url}/models 返回 200 但响应体为空，API Key 可能无效"
                        continue
                    models = [m["id"] for m in data.get("data", [])]
                    chat_models = [m for m in models if not any(
                        kw in m.lower() for kw in ["embed", "whisper", "tts", "dall", "moderat"]
                    )]
                    return {"models": sorted(chat_models)}
                last_error = f"HTTP {resp.status_code} from {base_url}/models：{resp.text[:200]}"
            except httpx.RequestError as e:
                last_error = str(e)

    # 所有路径都失败——返回特殊标志让前端提示手动输入
    return {"models": [], "unsupported": True, "detail": f"该服务不支持模型列表接口，请手动输入模型名。（{last_error}）"}


@app.post("/ping")
async def ping_connection(req: ConfigRequest):
    """
    发送一条最简单的 chat 请求验证 API Key 和模型是否可用。
    成功返回 {"ok": true, "reply": "..."}, 失败返回 {"ok": false, "detail": "..."}

    ⚠️ 副作用：此接口会临时覆盖当前会话的 config（用传入的参数）。
    前端调用时机是"保存前的连通性测试"，保存动作紧随其后，所以实际上
    ping 完之后 /config 会立刻再写一次正式配置，副作用不可见。
    若单独调用 /ping 而不调用 /config，当前会话 config 会被修改。
    """
    # 写入 config 进行测试（前端调用链路：ping → 成功 → /config 保存）
    update_config(
        llm_provider=req.llm_provider,
        llm_api_key=req.llm_api_key,
        tavily_api_key=req.tavily_api_key,
        llm_base_url=req.llm_base_url,
        llm_model=req.llm_model,
    )
    try:
        llm = get_llm()
        result = llm.invoke('Reply with exactly: connection ok')
        return {"ok": True, "reply": result.content.strip()}
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@app.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    """
    上传 PDF 论文：
    1. 保存文件到 uploads/
    2. 用 PyMuPDF 提取文本
    3. 分块并建立 FAISS 索引
    4. 返回 paper_id 供后续接口使用

    解析与建索引是同步阻塞的重活，直接在事件循环里跑会卡住整个服务（其他请求排队）。
    这里用线程池执行；由于 _current_session 是 ContextVar，线程默认拿不到当前会话，
    故通过 contextvars.copy_context() 把会话上下文一并带入工作线程，保证隔离不丢。
    """
    # file.filename 完全由客户端控制，可能含 ../ 或绝对路径。
    # 只取最后一段文件名，剥掉所有目录成分，防止写出 uploads/ 之外（路径穿越）。
    filename = Path(file.filename or "").name
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持 PDF 文件")

    # 用文件名（去掉 .pdf）作为 paper_id，保证可读性
    paper_id = Path(filename).stem

    file_path = UPLOAD_DIR / filename

    # 流式落盘：逐块从上传流读取写入磁盘，全程只驻留一个 chunk；
    # 累计超过 MAX_UPLOAD_BYTES 立即中止并删除半成品，避免大文件打爆内存/磁盘。
    total = 0
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    f.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过大小上限（{MAX_UPLOAD_BYTES // (1024 * 1024)} MB）",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    def _process() -> dict:
        # 该函数在工作线程内、当前会话上下文下执行；文件已在上方流式落盘
        full_text, page_count = load_pdf(str(file_path))
        if not full_text.strip():
            raise HTTPException(status_code=422, detail="PDF 中未能提取到文本（可能是扫描件）")

        # 存入当前会话的文本存储（供 Tools 使用）
        paper_texts[paper_id] = full_text

        # 分块并写入当前会话的 FAISS 索引
        # 若中转站不支持 embedding 接口，跳过索引但上传仍然成功
        api_key  = session_config["llm_api_key"]
        base_url = session_config.get("llm_base_url", "")
        indexed  = False
        index_note = ""
        if api_key:
            try:
                documents = split_text(full_text, paper_id)
                vs.add_documents(documents, api_key, base_url)
                indexed = True
            except Exception as e:
                # 索引失败不阻断上传：结构化记录原因，前端可见，且日志留痕
                index_note = f"RAG 索引跳过（{type(e).__name__}：{str(e)[:100]}）"
                logging.getLogger("lunwen_agent.upload").warning(
                    "会话论文 %s 建索引失败：%s", paper_id, e
                )
        return {
            "page_count": page_count,
            "char_count": len(full_text),
            "indexed": indexed,
            "index_note": index_note,
        }

    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    info = await loop.run_in_executor(None, lambda: ctx.run(_process))

    return {
        "paper_id": paper_id,
        "filename": filename,
        "page_count": info["page_count"],
        "char_count": info["char_count"],
        "indexed": info["indexed"],
        "index_note": info["index_note"],
        "message": f"上传成功：{filename}，共 {info['page_count']} 页",
    }


def _direct_response(tool_name: str, result: str) -> dict:
    """直接工具调用的统一响应格式（含可视化步骤）"""
    preview = result[:150] + ("..." if len(result) > 150 else "")
    steps = [
        {"type": "tool_start", "tool": tool_name, "input": ""},
        {"type": "tool_end",   "output": preview},
    ]
    return {"result": result, "steps": steps}


@app.post("/extract")
async def extract(req: SinglePaperRequest):
    """对指定论文执行结构化信息提取（F2）"""
    _require_api_key()
    if req.paper_id not in paper_texts:
        raise HTTPException(status_code=404, detail=f"论文 {req.paper_id} 未找到，请先上传")
    try:
        result = extract_tool.invoke({"paper_id": req.paper_id})
        return _direct_response("extract_tool", result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/summary")
async def summary(req: SinglePaperRequest):
    """为指定论文生成摘要（F3）"""
    _require_api_key()
    if req.paper_id not in paper_texts:
        raise HTTPException(status_code=404, detail=f"论文 {req.paper_id} 未找到，请先上传")
    try:
        result = summary_tool.invoke({"paper_id": req.paper_id})
        return _direct_response("summary_tool", result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    多轮对话问答（F4），Memory 自动维护历史。
    每次调用时把当前论文列表注入 Agent Prompt，让模型知道自己的工作上下文。
    """
    _require_api_key()
    message = req.message
    if req.paper_id:
        message = f"（当前论文：{req.paper_id}）{message}"

    # ── 构建动态上下文，注入到 Agent Prompt 的 {context} 占位符 ──
    papers = list(paper_texts.keys())
    if papers:
        paper_list = "\n".join(f"  - {p}" for p in papers)
        context = f"已加载论文（共 {len(papers)} 篇）：\n{paper_list}"
    else:
        context = "当前没有已加载的论文。"
    if req.paper_id and req.paper_id in paper_texts:
        context += f"\n\n用户当前聚焦论文：{req.paper_id}"

    try:
        # 使用轻量级单次 LLM 调用（原 ReAct Agent 需 2-3 次调用，慢 2-3 倍）
        # 工具调用任务（提取/摘要/对比/缺口）已有专用 endpoint，不走 /chat
        raw = run_chat(message, context=context)
        return {"result": raw["output"], "steps": raw["steps"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/compare")
async def compare(req: PaperIdsRequest):
    """对比多篇论文，输出 Markdown 表格（F5）"""
    _require_api_key()
    if len(req.paper_ids) < 2:
        raise HTTPException(status_code=400, detail="对比至少需要 2 篇论文")
    for pid in req.paper_ids:
        if pid not in paper_texts:
            raise HTTPException(status_code=404, detail=f"论文 {pid} 未找到，请先上传")
    try:
        ids_str = ",".join(req.paper_ids)
        result = compare_tool.invoke({"paper_ids": ids_str})
        return _direct_response("compare_tool", result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gap")
async def gap(req: PaperIdsRequest):
    """识别多篇论文的研究缺口（F6）"""
    _require_api_key()
    if len(req.paper_ids) < 2:
        raise HTTPException(status_code=400, detail="缺口分析至少需要 2 篇论文")
    for pid in req.paper_ids:
        if pid not in paper_texts:
            raise HTTPException(status_code=404, detail=f"论文 {pid} 未找到，请先上传")
    try:
        ids_str = ",".join(req.paper_ids)
        result = gap_tool.invoke({"paper_ids": ids_str})
        return _direct_response("gap_tool", result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/arxiv")
async def arxiv_search(query: str):
    """ArXiv 论文搜索"""
    _require_api_key()
    try:
        return _agent_response(run_agent(f"请在 ArXiv 上搜索：{query}，使用 arxiv_tool"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/papers")
async def list_papers():
    """返回当前已上传的所有论文 ID 列表"""
    return {"papers": list(paper_texts.keys())}


@app.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str):
    """从内存中移除指定论文（FAISS 索引保持原样，不影响运行）"""
    paper_texts.pop(paper_id, None)
    return {"status": "ok"}


@app.post("/reset")
async def reset():
    """重置对话记忆（新对话时调用）"""
    reset_memory()
    return {"status": "ok", "message": "对话记忆已清空"}


# ── 工具函数 ─────────────────────────────────────────────────

def _require_api_key():
    """检查 API Key 是否已设置，未设置则返回 400"""
    if not session_config["llm_api_key"]:
        raise HTTPException(
            status_code=400,
            detail="请先在设置面板填写 API Key",
        )
