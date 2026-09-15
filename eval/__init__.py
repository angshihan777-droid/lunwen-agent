# eval/ — 评测目录（与 tests/ 分开，评测不进 CI 快速用例）
#
# eval.py            LLM 输出质量评估：对 3 篇演示论文跑全链路，输出 PASS/FAIL，需要真实 LLM Key。
# retrieval_eval.py  RAG 检索召回率评测：本地 embedding 离线跑 QASPER，给可复现召回数值，不需要 LLM。
