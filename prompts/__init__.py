# prompts/ — 各功能模块的独立 Prompt 模板
# 每个工具对应一个 prompt，避免混用同一个大 prompt（Prompt Engineering 最佳实践）。
#
# extract_prompt.py  — 结构化提取 Prompt（配合 PydanticOutputParser 强约束输出）
# compare_prompt.py  — 论文对比 Prompt（输出 Markdown 表格）
# gap_prompt.py      — 研究缺口 Prompt（主动分析，分点输出）
