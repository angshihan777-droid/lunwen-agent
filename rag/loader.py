"""
rag/loader.py — PDF 解析

使用 PyMuPDF（fitz）提取 PDF 中的纯文本。
每页文本之间用换行分隔，保留段落结构，方便后续分块。
"""

import fitz  # PyMuPDF


def load_pdf(file_path: str) -> tuple[str, int]:
    """
    读取 PDF 文件，返回 (全文文本, 页数)。

    :param file_path: PDF 文件的本地路径
    :return: (text, page_count)
    """
    doc = fitz.open(file_path)
    pages = []

    for page in doc:
        text = page.get_text("text")  # 提取纯文本，保留换行
        if text.strip():              # 跳过空白页
            pages.append(text)

    full_text = "\n\n".join(pages)
    page_count = len(doc)
    doc.close()

    return full_text, page_count
