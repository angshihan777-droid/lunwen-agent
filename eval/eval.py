"""
eval/eval.py — LLM 输出质量评估脚本

在真实 LLM 上运行，针对 3 篇内置演示论文评估所有核心功能。
评估策略：检查结构完整性 + 内容合理性，不要求"标准答案"（LLM 输出无法完全确定）。

使用方法：
    # 先启动服务（会自动加载演示论文）
    uvicorn main:app --port 8000

    # 在另一个终端运行评估
    python eval/eval.py --api-key sk-xxx --provider openai --model gpt-4o
    python eval/eval.py --api-key sk-xxx --provider deepseek --model deepseek-chat
"""

import argparse
import json
import sys
import time

import httpx

BASE_URL = "http://localhost:8000"
SESSION_ID = "eval-session-" + str(int(time.time()))
HEADERS = {"X-Session-ID": SESSION_ID, "Content-Type": "application/json"}

# 3 篇演示论文（服务启动时自动加载）
DEMO_PAPERS = [
    "demo_multiagent_survey",
    "demo_transformer_attention",
    "demo_bert_pretraining",
]

# 评估结果统计
results: list[dict] = []


def _check(name: str, passed: bool, detail: str = ""):
    """记录一条评估结果并打印。"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}  {name}")
    if detail and not passed:
        print(f"         → {detail}")
    results.append({"name": name, "passed": passed, "detail": detail})


def setup_config(api_key: str, provider: str, model: str):
    """向服务写入 API Key 配置。"""
    print(f"\n{'='*60}")
    print(f"配置 LLM: provider={provider}, model={model}")
    resp = httpx.post(f"{BASE_URL}/config", headers=HEADERS, json={
        "llm_provider": provider,
        "llm_api_key": api_key,
        "llm_model": model,
        "tavily_api_key": "",
    })
    assert resp.status_code == 200, f"配置失败：{resp.text}"
    print("配置成功\n")


def eval_papers_loaded():
    """检查 3 篇演示论文是否全部加载。"""
    print("【检查】演示论文加载状态")
    resp = httpx.get(f"{BASE_URL}/papers", headers=HEADERS)
    papers = resp.json().get("papers", [])
    for pid in DEMO_PAPERS:
        _check(f"演示论文已加载: {pid}", pid in papers,
               f"当前论文列表: {papers}")


def eval_extract(paper_id: str):
    """评估结构化提取：检查 6 个字段是否存在且非空。"""
    print(f"\n【提取】{paper_id}")
    try:
        resp = httpx.post(f"{BASE_URL}/extract", headers=HEADERS,
                          json={"paper_id": paper_id}, timeout=60)
        _check("HTTP 200", resp.status_code == 200, resp.text[:200])
        if resp.status_code != 200:
            return

        result = resp.json().get("result", "")
        # 解析 JSON
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            _check("输出可解析为 JSON", False, f"原始输出：{result[:300]}")
            return

        _check("输出可解析为 JSON", True)

        required_fields = ["research_problem", "methodology", "dataset",
                           "metrics", "conclusion", "limitations"]
        for field in required_fields:
            val = data.get(field, "")
            _check(f"字段非空: {field}", bool(val and len(str(val)) > 5),
                   f"实际值：{str(val)[:100]}")

    except Exception as e:
        _check(f"提取接口可达", False, str(e))


def eval_summary(paper_id: str):
    """评估摘要生成：检查长度和中文比例。"""
    print(f"\n【摘要】{paper_id}")
    try:
        resp = httpx.post(f"{BASE_URL}/summary", headers=HEADERS,
                          json={"paper_id": paper_id}, timeout=60)
        _check("HTTP 200", resp.status_code == 200, resp.text[:200])
        if resp.status_code != 200:
            return

        result = resp.json().get("result", "")
        _check("摘要长度 ≥ 100 字", len(result) >= 100,
               f"实际长度：{len(result)} 字")
        _check("摘要长度 ≤ 800 字（未失控）", len(result) <= 800,
               f"实际长度：{len(result)} 字")

        # 简单检查是否包含中文（证明 prompt 的中文指令有效）
        chinese_chars = sum(1 for c in result if '一' <= c <= '鿿')
        _check("摘要包含中文内容", chinese_chars > 20,
               f"中文字符数：{chinese_chars}")

    except Exception as e:
        _check("摘要接口可达", False, str(e))


def eval_compare():
    """评估多篇对比：检查是否输出 Markdown 表格。"""
    print(f"\n【对比】{DEMO_PAPERS[0]} vs {DEMO_PAPERS[1]} vs {DEMO_PAPERS[2]}")
    try:
        resp = httpx.post(f"{BASE_URL}/compare", headers=HEADERS,
                          json={"paper_ids": DEMO_PAPERS}, timeout=90)
        _check("HTTP 200", resp.status_code == 200, resp.text[:200])
        if resp.status_code != 200:
            return

        result = resp.json().get("result", "")
        _check("输出包含 Markdown 表格（|）", "|" in result,
               f"输出片段：{result[:300]}")
        _check("表格有表头分隔线（---）", "---" in result,
               f"输出片段：{result[:300]}")

        # 检查对比维度是否涵盖核心字段
        keywords = ["方法", "数据", "结论", "局限"]
        found = [kw for kw in keywords if kw in result]
        _check(f"包含核心对比维度（找到 {len(found)}/{len(keywords)} 个）",
               len(found) >= 2, f"找到：{found}")

    except Exception as e:
        _check("对比接口可达", False, str(e))


def eval_gap():
    """评估研究缺口：检查是否分点输出、有论据。"""
    print(f"\n【缺口分析】{' + '.join(DEMO_PAPERS)}")
    try:
        resp = httpx.post(f"{BASE_URL}/gap", headers=HEADERS,
                          json={"paper_ids": DEMO_PAPERS}, timeout=90)
        _check("HTTP 200", resp.status_code == 200, resp.text[:200])
        if resp.status_code != 200:
            return

        result = resp.json().get("result", "")
        _check("输出长度 ≥ 200 字（非敷衍回答）", len(result) >= 200,
               f"实际长度：{len(result)} 字")

        # 检查是否分点（数字列表或 Markdown 列表）
        has_numbered = any(f"{i}." in result or f"{i}、" in result
                           for i in range(1, 6))
        has_bullet = "- " in result or "• " in result
        _check("分点结构化输出", has_numbered or has_bullet,
               f"输出片段：{result[:300]}")

        # 检查是否引用了具体论文
        mentions_paper = any(p in result for p in DEMO_PAPERS)
        _check("引用了具体论文名称", mentions_paper,
               f"输出片段：{result[:400]}")

    except Exception as e:
        _check("缺口接口可达", False, str(e))


def eval_chat():
    """评估多轮对话：验证上下文连续性。"""
    print(f"\n【多轮对话】上下文连续性测试")
    try:
        # 第 1 轮：介绍一个概念
        resp1 = httpx.post(f"{BASE_URL}/chat", headers=HEADERS, json={
            "message": "请用一句话解释 Transformer 的核心思想，记住你说的内容",
            "paper_id": "demo_transformer_attention",
        }, timeout=30)
        _check("第 1 轮对话正常", resp1.status_code == 200, resp1.text[:200])

        # 第 2 轮：引用第 1 轮
        resp2 = httpx.post(f"{BASE_URL}/chat", headers=HEADERS, json={
            "message": "你上一句话说的是什么？",
            "paper_id": "",
        }, timeout=30)
        _check("第 2 轮对话正常", resp2.status_code == 200, resp2.text[:200])

        if resp2.status_code == 200:
            answer2 = resp2.json().get("result", "")
            # 宽松检查：第 2 轮应该回忆了 Transformer 相关内容
            keywords = ["Transformer", "注意力", "attention", "自注意力", "transformer"]
            recalled = any(kw.lower() in answer2.lower() for kw in keywords)
            _check("第 2 轮能回忆第 1 轮内容（Memory 有效）", recalled,
                   f"第 2 轮回答：{answer2[:300]}")

    except Exception as e:
        _check("对话接口可达", False, str(e))


def print_summary():
    """打印评估总结。"""
    print(f"\n{'='*60}")
    print("评估结果汇总")
    print(f"{'='*60}")

    passed = sum(1 for r in results if r["passed"])
    total  = len(results)
    rate   = passed / total * 100 if total > 0 else 0

    print(f"通过：{passed}/{total}  ({rate:.1f}%)\n")

    failed = [r for r in results if not r["passed"]]
    if failed:
        print("未通过项目：")
        for r in failed:
            print(f"  ✗ {r['name']}")
            if r["detail"]:
                print(f"    {r['detail']}")
    else:
        print("全部通过 🎉")

    print(f"{'='*60}")
    return passed == total


def main():
    parser = argparse.ArgumentParser(description="论文研究 Agent 评估脚本")
    parser.add_argument("--api-key",  required=True,  help="LLM API Key")
    parser.add_argument("--provider", default="openai",
                        choices=["openai", "anthropic", "deepseek", "custom"],
                        help="LLM provider")
    parser.add_argument("--model",    default="",     help="模型名称（留空用默认）")
    parser.add_argument("--base-url", default="",     help="中转站 URL（custom 时填）")
    parser.add_argument("--skip-llm", action="store_true",
                        help="只检查论文加载，跳过 LLM 相关评估（用于快速烟测）")
    args = parser.parse_args()

    print("论文研究 Agent — 输出质量评估")
    print(f"服务地址：{BASE_URL}")
    print(f"会话 ID：{SESSION_ID}")

    # 1. 配置 LLM
    setup_config(args.api_key, args.provider, args.model)

    # 2. 检查演示论文
    eval_papers_loaded()

    if args.skip_llm:
        print("\n（--skip-llm 已跳过 LLM 功能评估）")
        print_summary()
        return

    # 3. 逐一评估每篇论文的提取 + 摘要
    for pid in DEMO_PAPERS:
        eval_extract(pid)
        eval_summary(pid)

    # 4. 多论文功能
    eval_compare()
    eval_gap()

    # 5. 对话记忆
    eval_chat()

    # 6. 打印总结
    all_passed = print_summary()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
