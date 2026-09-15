# -*- coding: utf-8 -*-
"""
eval/retrieval_eval.py — RAG 检索召回率评测（与 eval.py 的 LLM 质量评估互补）

区别：
- eval.py：评估"最终 LLM 输出"的结构与合理性，需要真实 LLM Key。
- retrieval_eval.py：只评估"检索这一层"能否召回正确证据段落，不需要 LLM，
  用本地 embedding 模型离线跑，给出可复现的召回数值。

真实链路对齐：
- 分块：直接调用项目 rag/splitter.py 的 split_text（chunk_size=800, overlap=100）。
- 检索：FAISS + 本地 embedding 模型 sentence-transformers/all-MiniLM-L6-v2。
- Top-K：5（与项目 search 默认 k=5 一致）。

数据集：QASPER dev（allenai 公开学术 QA），用人工标注的 evidence 段落作 ground truth。
指标：Recall@1 / Recall@3 / Recall@5 / MRR + 平均检索延迟。

口径说明（诚实交代）：
- 本地小模型 all-MiniLM-L6-v2 + 严格词覆盖匹配，是保守下限；
  线上换 OpenAI text-embedding 通常更高。
- 金标准判定：evidence 段落与某 chunk 的词覆盖率 >= 0.6 记为该 chunk 命中。

复现：
    pip install -r eval/requirements-eval.txt
    # 下载 QASPER 数据到 qasper_data/（见 eval/README.md）
    python eval/retrieval_eval.py
结果写入 eval/retrieval_result.json（UTF-8）。
"""
import json
import os
import re
import time
import sys

# 保证能从仓库根导入 rag 包
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from rag.splitter import split_text

from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

DATA_PATH = os.path.join(ROOT, "qasper_data", "qasper-dev-v0.3.json")
RESULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "retrieval_result.json")
EMB_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5
GOLD_COVERAGE_THRESHOLD = 0.6


class LocalEmb(Embeddings):
    """本地 MiniLM 的 LangChain Embeddings 包装（评测专用，不进主 requirements）。"""

    def __init__(self, name=EMB_MODEL):
        self.model = SentenceTransformer(name)

    def embed_documents(self, texts):
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text):
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


def norm(s):
    """归一化：小写、只留字母数字词，用于词集合比较。"""
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def reconstruct_full_text(paper):
    """把 QASPER 的分节段落拼回论文全文（含标题、摘要），模拟真实入库文本。"""
    parts = [paper.get("title", ""), paper.get("abstract", "")]
    for sec in paper.get("full_text", []):
        if sec.get("section_name"):
            parts.append(sec["section_name"])
        for para in sec.get("paragraphs", []):
            parts.append(para)
    return "\n\n".join(p for p in parts if p)


def collect_evidence(qa):
    """收集一个问题的所有文本型 evidence 段落（跳过表/图引用、过短与空标注）。"""
    ev = []
    for a in qa.get("answers", []):
        ans = a.get("answer", {})
        if ans.get("unanswerable"):
            continue
        for e in ans.get("highlighted_evidence", []) or ans.get("evidence", []):
            e = (e or "").strip()
            if not e or e.startswith("FLOAT SELECTED"):
                continue
            if len(e) < 40:
                continue
            ev.append(e)
    return ev


def gold_chunk_indices(chunks, evidence_list, thr=GOLD_COVERAGE_THRESHOLD):
    """对每个 evidence 段落，找出词覆盖率最高且 >= thr 的 chunk 作为金标准。"""
    gold = set()
    chunk_wordsets = [norm(c.page_content) for c in chunks]
    for ev in evidence_list:
        ev_words = norm(ev)
        if not ev_words:
            continue
        best_i, best_cov = -1, 0.0
        for i, cw in enumerate(chunk_wordsets):
            if not cw:
                continue
            cov = len(ev_words & cw) / len(ev_words)
            if cov > best_cov:
                best_cov, best_i = cov, i
        if best_i >= 0 and best_cov >= thr:
            gold.add(best_i)
    return gold


def main():
    if not os.path.exists(DATA_PATH):
        print(f"[错误] 未找到数据集 {DATA_PATH}，请先按 eval/README.md 下载 QASPER。")
        sys.exit(1)

    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print(f"加载本地 embedding 模型 {EMB_MODEL} ...", flush=True)
    emb = LocalEmb()

    r1 = r3 = r5 = 0
    mrr = 0.0
    n_q = 0
    n_papers = 0
    total_chunks = 0
    latencies = []

    for paper_id, paper in data.items():
        valid_qas = []
        for qa in paper.get("qas", []):
            ev = collect_evidence(qa)
            if ev:
                valid_qas.append((qa["question"], ev))
        if not valid_qas:
            continue

        full = reconstruct_full_text(paper)
        chunks = split_text(full, paper_id)
        if len(chunks) < 3:
            continue

        store = FAISS.from_documents(chunks, emb)

        for question, evidence_list in valid_qas:
            gold = gold_chunk_indices(chunks, evidence_list)
            if not gold:
                continue

            t0 = time.time()
            hits = store.similarity_search(question, k=TOP_K)
            latencies.append((time.time() - t0) * 1000)

            hit_idx = []
            for h in hits:
                for i, c in enumerate(chunks):
                    if c.page_content == h.page_content:
                        hit_idx.append(i)
                        break

            rank = None
            for pos, idx in enumerate(hit_idx):
                if idx in gold:
                    rank = pos + 1
                    break

            if rank is not None:
                if rank == 1:
                    r1 += 1
                if rank <= 3:
                    r3 += 1
                if rank <= 5:
                    r5 += 1
                mrr += 1.0 / rank
            n_q += 1

        n_papers += 1
        total_chunks += len(chunks)

    if n_q == 0:
        print("[错误] 没有可评测的问题，检查数据集是否完整。")
        sys.exit(1)

    result = {
        "papers": n_papers,
        "total_chunks": total_chunks,
        "avg_chunks": round(total_chunks / max(n_papers, 1), 1),
        "n_questions": n_q,
        "recall@1": round(r1 / n_q, 4),
        "recall@3": round(r3 / n_q, 4),
        "recall@5": round(r5 / n_q, 4),
        "mrr": round(mrr / n_q, 4),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
        "top_k": TOP_K,
        "chunk_size": 800,
        "chunk_overlap": 100,
        "embedding_model": "all-MiniLM-L6-v2 (local)",
        "dataset": "QASPER dev (allenai)",
    }

    print("=" * 50)
    for k, v in result.items():
        print(f"{k}: {v}")
    print("=" * 50)

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {RESULT_PATH}")


if __name__ == "__main__":
    main()
