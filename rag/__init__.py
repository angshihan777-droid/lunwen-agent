# rag/ — 长文档 RAG 管道（解决论文 token 超限问题）
# loader.py      — PyMuPDF 读取 PDF → 纯文本
# splitter.py    — RecursiveCharacterTextSplitter 分块（800 字/块，100 字重叠）
# vectorstore.py — FAISS 索引管理（增量写入 + 按 paper_id 过滤检索）
