# ── Stage 1: 依赖安装层（利用 Docker 层缓存，依赖不变时跳过此层）──────────
FROM python:3.10-slim AS deps

WORKDIR /app

# 安装系统依赖
# libglib2.0-0：PyMuPDF 渲染引擎需要
# libgl1：部分 PyMuPDF 版本的隐式依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 先只复制 requirements.txt，利用缓存：
# 只要 requirements.txt 不变，pip install 这一层就不会重跑
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ── Stage 2: 运行层（只复制源码，不带 venv/、__pycache__/ 等杂物）──────────
FROM deps AS runtime

WORKDIR /app

# 复制项目源码（.dockerignore 会排除不需要的文件）
COPY . .

# 创建 uploads 目录（挂载 volume 前必须存在）
RUN mkdir -p uploads

# 不以 root 运行（安全最佳实践）
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# 生产启动命令：
# --host 0.0.0.0 监听所有网卡（容器内必须，否则外部访问不到）
# --workers 1 保证内存中的 session 状态一致（多 worker 会各自独立内存）
# --no-access-log 减少无用日志
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-access-log"]
