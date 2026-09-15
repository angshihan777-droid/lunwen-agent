# eval/ — 评测目录

本目录放"评测"脚本，和 `tests/`（单元测试）分开。评测跑得慢、要外部数据或模型，不进 CI 快速用例。

这里有两个互补的评测，评的是链路里不同的层：

| 脚本 | 评什么 | 需不需要 LLM | 数据 |
|---|---|---|---|
| `eval.py` | 最终 LLM 输出的结构与合理性（8 个工具全链路 PASS/FAIL） | 需要真实 Key | 3 篇内置演示论文 |
| `retrieval_eval.py` | RAG 检索层能否召回正确证据段落 | 不需要 | QASPER dev 公开数据集 |

---

## 一、LLM 输出质量评估：eval.py

先启动服务（会自动加载演示论文），再另开终端跑：

```bash
uvicorn main:app --port 8000
python eval/eval.py --api-key sk-xxx --provider deepseek --model deepseek-chat
```

---

## 二、RAG 检索召回率评测：retrieval_eval.py

只评"检索这一层"：给一个问题，FAISS 能不能把人工标注的证据段落捞进 Top-5。不掺 LLM，数值可复现。

### 真实链路对齐
- 分块：直接调用项目 `rag/splitter.py` 的 `split_text`（chunk_size=800 / overlap=100）。
- 检索：FAISS + 本地 embedding `all-MiniLM-L6-v2` + Top-5（与项目 `search` 默认 k=5 一致）。
- Ground truth：QASPER 人工标注的 evidence 段落；evidence 与某 chunk 词覆盖率 ≥ 0.6 记为该 chunk 命中。

### 复现步骤
```bash
# 1. 装评测依赖（单独，不污染主 requirements）
pip install -r eval/requirements-eval.txt

# 2. 下载 QASPER 数据集到 qasper_data/
#    官方源：https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz
#    解压后把 qasper-dev-v0.3.json 放到仓库根 qasper_data/ 下

# 3. 跑评测（全量，约几分钟）
python eval/retrieval_eval.py
```

结果写入 `eval/retrieval_result.json`。

### 全量真实结果（QASPER dev）

| 指标 | 数值 |
|---|---|
| 论文数 | 276 |
| 总切块数 | 12373（平均 44.8 块/篇） |
| 评测问题数 | 881 |
| Recall@1 | 0.1952 |
| Recall@3 | 0.4188 |
| Recall@5 | 0.5709 |
| MRR | 0.3239 |
| 平均检索延迟 | 14.74 ms |

### 口径说明（诚实交代，别往好里凑）
- 用的是**本地免费小模型** `all-MiniLM-L6-v2` + **严格词覆盖匹配**，这是**保守下限**；线上换 OpenAI `text-embedding` 通常会更高。
- 金标准是"和 chunk 词覆盖率 ≥ 0.6"的自动对齐，不是人工逐条核对，可能低估真实命中。
- 跳过了 unanswerable、图表引用（FLOAT SELECTED）和过短证据，避免噪声。

一句话：**这组数字是我这套离线口径下能复现的下限，不是最优值。**
