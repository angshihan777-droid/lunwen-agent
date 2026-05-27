# tools/ — 所有 LangChain @tool 定义
# 每个文件对应一个独立工具，被 agents/research_agent.py 中的 ALL_TOOLS 列表统一注册。
#
# extract_tool   — 结构化信息提取（研究问题/方法/数据集/指标/结论/局限性）
# summary_tool   — 快速摘要生成（200-300 字中文段落）
# search_tool    — FAISS 语义检索（RAG，解决长文档 token 超限问题）
# compare_tool   — 多篇论文对比（输出 Markdown 表格）
# gap_tool       — 研究缺口识别（主动分析，差异化功能）
# citation_tool  — 参考文献提取（取论文末尾 3000 字）
# arxiv_tool     — ArXiv 论文搜索（免费，无需 Key）
# web_search_tool— Tavily 网络搜索（需要 Tavily API Key）
