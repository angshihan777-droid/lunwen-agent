/**
 * app.js — 前端逻辑
 *
 * 新增功能：
 *   - SESSION_ID：每个浏览器生成唯一 ID，所有请求携带 X-Session-ID 头，实现多用户隔离
 *   - 历史对话：保存在 localStorage，左侧面板可切换查看
 *   - 新对话：保存当前对话后重置，替代原"清空记忆"
 *   - 多配置管理：API Key 配置命名保存到 localStorage，可随时切换加载
 */

const API = "";  // 同源留空；部署后改为域名

// ── Session ID（每个浏览器唯一，持久化到 localStorage） ──────
function _genId() {
  try { return crypto.randomUUID(); } catch (_) {
    return Date.now().toString(36) + Math.random().toString(36).slice(2);
  }
}
const SESSION_ID = (() => {
  let id = localStorage.getItem("session_id");
  if (!id) { id = _genId(); localStorage.setItem("session_id", id); }
  return id;
})();

/** 替代原生 fetch，自动附加 X-Session-ID 头 */
function apiFetch(path, options = {}) {
  const headers = { "X-Session-ID": SESSION_ID, ...(options.headers || {}) };
  return fetch(API + path, { ...options, headers });
}

// ── 全局状态 ──────────────────────────────────────────────────
let activePaperId  = "";
let uploadedPapers = [];
let selectedPapers = new Set();
let activeTab      = "plan";

// ── 历史对话状态 ──────────────────────────────────────────────
let currentConv  = null;   // 当前对话对象
let convHistory  = JSON.parse(localStorage.getItem("conv_history") || "[]");

function _createConv() {
  return {
    id:        _genId(),
    title:     "新对话",
    messages:  [],   // { role, text, isResult, time }
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

function _saveCurrentConv() {
  if (!currentConv) return;
  try {
    currentConv.updatedAt = new Date().toISOString();
    const idx = convHistory.findIndex(c => c.id === currentConv.id);
    if (idx >= 0) {
      convHistory[idx] = currentConv;
    } else {
      convHistory.unshift(currentConv);
    }
    if (convHistory.length > 30) convHistory.length = 30;
    localStorage.setItem("conv_history", JSON.stringify(convHistory));
  } catch (_) {}  // localStorage 满时静默失败，不阻断 UI 流程
}

/** 保存当前对话，重置为新对话并清空后端记忆 */
async function newConversation() {
  // BUG-016 fix：DOM 清空放在最前，任何存储异常都不会阻止新对话开启

  // ① 立即清空消息区，给用户即时反馈
  const msgsEl = document.getElementById("messages");
  if (msgsEl) msgsEl.innerHTML = "";
  _renderWelcomeMessage();
  _updateConvTitleDisplay();

  // ② 保存旧对话（包在 try/catch，localStorage 异常不影响新对话）
  const oldConv = currentConv;
  if (oldConv && oldConv.messages.length > 0) {
    try {
      oldConv.updatedAt = new Date().toISOString();
      const idx = convHistory.findIndex(c => c.id === oldConv.id);
      if (idx >= 0) convHistory[idx] = oldConv;
      else { convHistory.unshift(oldConv); if (convHistory.length > 30) convHistory.length = 30; }
      localStorage.setItem("conv_history", JSON.stringify(convHistory));
    } catch (_) {}
  }

  // ③ 创建新对话并刷新列表
  currentConv = _createConv();
  renderConvHistory();

  // ④ 重置后端 Memory（fire-and-forget）
  apiFetch("/reset", { method: "POST" }).catch(() => {});
}

/** 切换到历史对话（只读查看，后端记忆不恢复） */
function switchConversation(convId) {
  if (currentConv && currentConv.messages.length > 0) _saveCurrentConv();
  const conv = convHistory.find(c => c.id === convId);
  if (!conv) return;
  currentConv = conv;

  const container = document.getElementById("messages");
  container.innerHTML = "";

  conv.messages.forEach(msg => {
    if (msg.isResult) _appendResultRaw(msg.text);
    else _appendMessageRaw(msg.role, msg.text);
  });
  container.scrollTop = container.scrollHeight;
  renderConvHistory();
  _updateConvTitleDisplay();
}

/** 从历史中删除一条对话 */
function deleteConv(convId, evt) {
  evt.stopPropagation();
  convHistory = convHistory.filter(c => c.id !== convId);
  localStorage.setItem("conv_history", JSON.stringify(convHistory));
  // 如果删的是当前对话，开启新对话
  if (currentConv && currentConv.id === convId) newConversation();
  else renderConvHistory();
}

function _updateConvTitleDisplay() {
  const el = document.getElementById("conv-title-display");
  if (el) el.textContent = currentConv ? currentConv.title : "新对话";
}

function renderConvHistory() {
  const ul = document.getElementById("conv-history-list");
  if (!ul) return;
  if (!convHistory.length) {
    ul.innerHTML = '<li class="text-xs text-gray-400 text-center py-2">暂无历史</li>';
    return;
  }
  ul.innerHTML = convHistory.slice(0, 20).map(conv => {
    const isActive = currentConv && conv.id === currentConv.id;
    const d = new Date(conv.updatedAt);
    const timeStr = d.toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
    return `
      <li onclick="switchConversation('${escHtml(conv.id)}')"
        class="conv-item ${isActive ? "active" : ""}">
        <span class="flex-1 text-xs truncate ${isActive ? "text-blue-700 font-semibold" : "text-gray-600"}"
          title="${escHtml(conv.title)}">${escHtml(conv.title)}</span>
        <span class="text-xs text-gray-300 flex-shrink-0 del-conv" title="${timeStr}"
          onclick="deleteConv('${escHtml(conv.id)}', event)">×</span>
      </li>`;
  }).join("");
}

// ── 已保存 API 配置 ───────────────────────────────────────────
let savedConfigs    = JSON.parse(localStorage.getItem("saved_configs") || "[]");
let activeConfigName = "";   // 当前已切换生效的配置名（内存状态，刷新不保留）

/** 渲染左侧 LLM 配置面板 */
function renderConfigPanel() {
  const ul = document.getElementById("config-panel-list");
  if (!ul) return;
  if (!savedConfigs.length) {
    ul.innerHTML = '<li class="text-xs text-gray-400 text-center py-2">暂无配置<br>点击"+ 新增"保存</li>';
    return;
  }
  ul.innerHTML = savedConfigs.map((cfg, i) => {
    const active = cfg.name === activeConfigName;
    return `
      <li class="config-item flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer transition
          ${active ? "bg-blue-50 border border-blue-200" : "hover:bg-gray-50"}"
          onclick="applyConfigByIndex(${i})">
        <span class="w-1.5 h-1.5 rounded-full flex-shrink-0 ${active ? "bg-green-400" : "bg-gray-200"}"></span>
        <span class="flex-1 text-xs truncate ${active ? "text-blue-700 font-semibold" : "text-gray-600"}"
          title="${escHtml(cfg.name)}">${escHtml(cfg.name)}</span>
        <button onclick="deleteConfigByIndex(${i}, event)"
          class="del-cfg text-gray-300 hover:text-red-400 text-sm leading-none flex-shrink-0">×</button>
      </li>`;
  }).join("");
}

/**
 * 点击配置面板条目：一键切换并应用到服务器
 * silent=true 时不显示面板状态（用于页面加载时自动恢复，不打扰用户）
 */
async function applyConfigByIndex(idx, silent = false) {
  const cfg = savedConfigs[idx];
  if (!cfg) return false;
  _fillFormValues(cfg);

  function _showPanelStatus(msg, isErr) {
    if (silent) return;
    const el = document.getElementById("config-panel-status");
    if (!el) return;
    el.textContent = msg;
    el.className = `text-xs mb-1.5 ${isErr ? "text-red-500" : "text-green-600"}`;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 2000);
  }

  try {
    const res  = await apiFetch("/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ llm_provider: cfg.provider, llm_api_key: cfg.apiKey,
                             tavily_api_key: cfg.tavilyKey, llm_base_url: cfg.baseUrl,
                             llm_model: cfg.model }),
    });
    const data = await res.json();
    if (res.ok) {
      activeConfigName = cfg.name;
      localStorage.setItem("active_config_name", cfg.name);  // 持久化激活状态
      renderConfigPanel();
      _showPanelStatus(`✅ 已切换：${cfg.name}`, false);
      return true;
    } else {
      _showPanelStatus(`❌ ${data.detail}`, true);
      return false;
    }
  } catch (e) {
    _showPanelStatus(`❌ ${e.message}`, true);
    return false;
  }
}

/** 从配置面板删除一条配置 */
function deleteConfigByIndex(idx, evt) {
  evt.stopPropagation();
  const cfg = savedConfigs[idx];
  if (!cfg) return;
  if (!confirm(`确认删除配置"${cfg.name}"？`)) return;
  const name = cfg.name;
  savedConfigs.splice(idx, 1);
  localStorage.setItem("saved_configs", JSON.stringify(savedConfigs));
  loadSavedConfigs();                                   // 同步更新设置面板下拉
  if (activeConfigName === name) activeConfigName = ""; // 激活配置被删则清空状态
  renderConfigPanel();
}

function _getCurrentFormValues() {
  return {
    provider:  document.getElementById("llm-provider").value,
    apiKey:    document.getElementById("llm-api-key").value.trim(),
    baseUrl:   (document.getElementById("llm-base-url")?.value || "").trim(),
    model:     document.getElementById("llm-model-input").value.trim(),
    tavilyKey: document.getElementById("tavily-api-key").value.trim(),
  };
}

/** 根据 provider + model 自动生成配置名称 */
function _autoConfigName(cfg) {
  const providerLabel = { openai:"OpenAI", deepseek:"DeepSeek", custom:"中转站", anthropic:"Anthropic" };
  const p = providerLabel[cfg.provider] || cfg.provider;
  return cfg.model ? `${p} · ${cfg.model}` : p;
}

function _fillFormValues(cfg) {
  document.getElementById("llm-provider").value    = cfg.provider  || "openai";
  document.getElementById("llm-api-key").value     = cfg.apiKey    || "";
  document.getElementById("llm-base-url").value    = cfg.baseUrl   || "";
  document.getElementById("llm-model-input").value = cfg.model     || "";
  document.getElementById("tavily-api-key").value  = cfg.tavilyKey || "";
  onProviderChange();
}

function loadSavedConfigs() {
  const select = document.getElementById("saved-config-select");
  if (!select) return;
  select.innerHTML = '<option value="">── 选择配置切换 ──</option>' +
    savedConfigs.map((c, i) =>
      `<option value="${i}">${escHtml(c.name)}</option>`
    ).join("");
}

/** 选择配置：填入表单并立即发送到服务器生效（设置面板下拉） */
async function loadSavedConfig() {
  const select = document.getElementById("saved-config-select");
  const idx = parseInt(select.value);
  if (isNaN(idx) || !savedConfigs[idx]) return;
  const cfg = savedConfigs[idx];
  _fillFormValues(cfg);
  setConfigStatus("切换中...", "text-gray-400");
  try {
    const res  = await apiFetch("/config", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ llm_provider: cfg.provider, llm_api_key: cfg.apiKey,
                             tavily_api_key: cfg.tavilyKey, llm_base_url: cfg.baseUrl,
                             llm_model: cfg.model }),
    });
    const data = await res.json();
    if (res.ok) {
      activeConfigName = cfg.name;
      localStorage.setItem("active_config_name", cfg.name);  // 持久化
      renderConfigPanel();
      setConfigStatus(`✅ 已切换到"${cfg.name}"`, "text-green-600");
    } else {
      setConfigStatus("❌ " + data.detail, "text-red-500");
    }
  } catch (e) { setConfigStatus("❌ " + e.message, "text-red-500"); }
}

function deleteSavedConfig() {
  const select = document.getElementById("saved-config-select");
  const idx = parseInt(select.value);
  if (isNaN(idx) || !savedConfigs[idx]) {
    setConfigStatus("⚠️ 请先选中要删除的配置", "text-yellow-600"); return;
  }
  const name = savedConfigs[idx].name;
  if (!confirm(`确认删除配置"${name}"？`)) return;
  savedConfigs.splice(idx, 1);
  localStorage.setItem("saved_configs", JSON.stringify(savedConfigs));
  loadSavedConfigs();
  if (activeConfigName === name) activeConfigName = "";  // 同步配置面板激活状态
  renderConfigPanel();
  setConfigStatus(`已删除配置"${name}"`, "text-gray-500");
}

/** 将表单内容以 "provider · model" 为名保存到本地（由 saveConfig 调用） */
function _localSaveConfig(cfg) {
  const name = _autoConfigName(cfg);
  cfg.name   = name;
  const idx  = savedConfigs.findIndex(c => c.name === name);
  if (idx >= 0) savedConfigs[idx] = cfg;
  else          savedConfigs.unshift(cfg);
  localStorage.setItem("saved_configs", JSON.stringify(savedConfigs));
  localStorage.setItem("active_config_name", name);  // 持久化激活状态
  loadSavedConfigs();
  activeConfigName = name;
  renderConfigPanel();
}

// ═══════════════════════════════════════════════════════════
//  PLAN MODE
// ═══════════════════════════════════════════════════════════
const PLANS = {
  extract: [
    { icon:"📖", text:"读取论文全文" },
    { icon:"🔍", text:"分析论文结构" },
    { icon:"🔬", text:"提取研究问题" },
    { icon:"🧪", text:"识别研究方法" },
    { icon:"📊", text:"收集数据集信息" },
    { icon:"📈", text:"整理评估指标" },
    { icon:"🎯", text:"归纳主要结论" },
    { icon:"⚠️", text:"识别研究局限性" },
    { icon:"📋", text:"生成结构化报告" },
  ],
  summary: [
    { icon:"📖", text:"读取论文内容" },
    { icon:"🧠", text:"理解研究背景" },
    { icon:"✨", text:"识别核心贡献" },
    { icon:"🎯", text:"提炼主要结论" },
    { icon:"✍️", text:"生成通俗摘要" },
  ],
  compare: [
    { icon:"📖", text:"读取各篇论文" },
    { icon:"📐", text:"对齐比较维度" },
    { icon:"🔄", text:"分析方法差异" },
    { icon:"📊", text:"对比实验结果" },
    { icon:"⚖️", text:"归纳各自优劣" },
    { icon:"📋", text:"生成 Markdown 对比表格" },
  ],
  gap: [
    { icon:"📖", text:"分析各篇论文贡献" },
    { icon:"✅", text:"梳理已解决问题" },
    { icon:"🔍", text:"识别研究边界" },
    { icon:"💡", text:"发现未解决问题" },
    { icon:"🔧", text:"分析技术瓶颈" },
    { icon:"🚀", text:"整理未来研究方向" },
  ],
  citation: [
    { icon:"📖", text:"读取论文全文" },
    { icon:"🔍", text:"定位参考文献区域" },
    { icon:"📋", text:"提取各文献条目" },
    { icon:"✍️", text:"格式化输出" },
  ],
  chat: [
    { icon:"🧠", text:"理解问题意图" },
    { icon:"🔍", text:"检索相关内容" },
    { icon:"💭", text:"综合分析推理" },
    { icon:"💬", text:"生成回答" },
  ],
};

let _planItems  = [];
let _planTimer  = null;
let _planCursor = 0;

function planStart(actionType, label, subLabel) {
  clearInterval(_planTimer);
  _planItems  = (PLANS[actionType] || [{ icon:"⚡", text:"执行任务" }])
                  .map(s => ({ ...s, status:"pending" }));
  _planCursor = 0;
  const badge   = document.getElementById("plan-status-badge");
  const taskHdr = document.getElementById("plan-task-header");
  badge.textContent = "● 运行中";
  badge.className   = "text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-600 font-medium animate-pulse";
  taskHdr.classList.remove("hidden");
  document.getElementById("plan-task-label").textContent = label;
  document.getElementById("plan-task-sub").textContent   = subLabel || "";
  _planRenderBody();
  const fence = Math.max(0, _planItems.length - 2);
  _planTimer = setInterval(() => {
    if (_planCursor < fence) {
      if (_planCursor > 0) _planItems[_planCursor - 1].status = "done";
      _planItems[_planCursor].status = "active";
      _planCursor++;
      _planRenderBody();
    } else {
      clearInterval(_planTimer);
      if (_planCursor < _planItems.length) {
        if (_planCursor > 0) _planItems[_planCursor - 1].status = "done";
        _planItems[_planCursor].status = "active";
        _planRenderBody();
      }
    }
  }, 720);
}

function planDone() {
  clearInterval(_planTimer);
  _planItems.forEach(i => i.status = "done");
  _planCursor = _planItems.length;
  _planRenderBody();
  const badge = document.getElementById("plan-status-badge");
  badge.textContent = "✅ 完成";
  badge.className   = "text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium";
}

function _planRenderBody() {
  const el = document.getElementById("plan-panel-body");
  if (!el) return;
  const total = _planItems.length;
  const done  = _planItems.filter(i => i.status === "done").length;
  const pct   = total ? Math.round(done / total * 100) : 0;
  const rows = _planItems.map(item => {
    if (item.status === "done") return `
      <div class="plan-done flex items-center gap-2 py-1">
        <span class="pi-icon text-sm">✅</span>
        <span class="pi-text text-xs">${item.icon} ${escHtml(item.text)}</span>
      </div>`;
    if (item.status === "active") return `
      <div class="plan-active flex items-center gap-2 py-1">
        <span class="pi-icon text-sm">⟳</span>
        <span class="pi-text text-xs">${item.icon} ${escHtml(item.text)}</span>
      </div>`;
    return `
      <div class="plan-pending flex items-center gap-2 py-1">
        <span class="pi-icon text-sm">○</span>
        <span class="pi-text text-xs">${item.icon} ${escHtml(item.text)}</span>
      </div>`;
  }).join("");
  el.innerHTML = `
    <div class="space-y-0">${rows}</div>
    <div class="plan-bar mt-3">
      <div class="plan-bar-fill" style="width:${pct}%"></div>
    </div>
    <div class="flex justify-between mt-1">
      <span class="text-xs text-gray-400">${done} / ${total} 步</span>
      <span class="text-xs text-gray-400">${pct}%</span>
    </div>`;
}

// ═══════════════════════════════════════════════════════════
//  报告草稿
// ═══════════════════════════════════════════════════════════
let reportItems = [];

const TYPE_ICON = {
  extract:"🔍", summary:"📝", compare:"📊",
  gap:"🔭", citation:"📖", chat:"💬",
};

function addToReport(type, label, paperLabel, content) {
  reportItems.push({
    id: Date.now(), type, label, paperLabel, content, included: true,
    time: new Date().toLocaleTimeString("zh-CN", { hour:"2-digit", minute:"2-digit" }),
  });
  _updateReportBadge();
  if (activeTab === "report") renderReportDraft();
}

function _updateReportBadge() {
  const badge = document.getElementById("report-count");
  badge.textContent = reportItems.length;
  badge.classList.toggle("hidden", reportItems.length === 0);
  badge.classList.remove("badge-pop");
  void badge.offsetWidth;
  badge.classList.add("badge-pop");
}

function toggleReportItem(id) {
  const item = reportItems.find(i => i.id === id);
  if (item) { item.included = !item.included; renderReportDraft(); }
}

function removeReportItem(id) {
  reportItems = reportItems.filter(i => i.id !== id);
  _updateReportBadge();
  renderReportDraft();
}

function clearReport() {
  reportItems = [];
  _updateReportBadge();
  renderReportDraft();
}

function renderReportDraft() {
  const el = document.getElementById("report-tab-content");
  if (!el) return;
  if (!reportItems.length) {
    el.innerHTML = `
      <div class="text-center py-10 px-4">
        <div class="text-3xl mb-3">📄</div>
        <div class="text-xs text-gray-400 leading-relaxed">
          执行操作后，结果会自动<br>加入报告草稿
        </div>
      </div>`;
    return;
  }
  const itemsHtml = reportItems.map(item => {
    const icon    = TYPE_ICON[item.type] || "📄";
    const preview = (item.content || "").slice(0, 80).replace(/[\n{}"]/g, " ").trim();
    return `
      <div class="report-item ${item.included ? "" : "excluded"}">
        <div class="flex items-start gap-2">
          <input type="checkbox" ${item.included ? "checked" : ""}
            onchange="toggleReportItem(${item.id})"
            class="mt-0.5 w-3.5 h-3.5 rounded accent-blue-500 flex-shrink-0 cursor-pointer">
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between gap-1">
              <span class="text-xs font-semibold text-gray-700 truncate">${icon} ${escHtml(item.label)}</span>
              <button onclick="removeReportItem(${item.id})"
                class="text-gray-300 hover:text-red-400 text-sm leading-none flex-shrink-0 ml-1">×</button>
            </div>
            <div class="text-xs text-blue-600 truncate" title="${escHtml(item.paperLabel)}">${escHtml(item.paperLabel)}</div>
            <div class="text-xs text-gray-400 mt-1 leading-relaxed" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">
              ${escHtml(preview)}${item.content.length > 80 ? "…" : ""}
            </div>
            <div class="text-xs text-gray-300 mt-1">${item.time}</div>
          </div>
        </div>
      </div>`;
  }).join("");
  const included = reportItems.filter(i => i.included).length;
  el.innerHTML = `
    <div class="px-3 pt-3 flex-1 overflow-y-auto">${itemsHtml}</div>
    <div class="px-3 py-3 border-t border-gray-100 flex-shrink-0">
      <div class="text-xs text-gray-400 mb-2 text-center">已选 ${included} / ${reportItems.length} 条</div>
      <button onclick="exportMarkdown()"
        class="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg py-2 px-3 flex items-center justify-center gap-1">
        ↓ 导出 Markdown
      </button>
      <button onclick="clearReport()"
        class="w-full mt-1.5 text-xs text-gray-400 hover:text-red-400 py-1 text-center">
        清空草稿
      </button>
    </div>`;
}

function exportMarkdown() {
  const items = reportItems.filter(i => i.included);
  if (!items.length) {
    appendMessage("agent", "⚠️ 报告草稿为空或全部未勾选，请先执行一些分析操作。");
    return;
  }
  const date = new Date().toLocaleDateString("zh-CN");
  let md = `# 📚 论文研究报告\n\n> 生成时间：${date}　|　共 ${items.length} 个章节\n\n---\n\n`;
  items.forEach((item, idx) => {
    const icon = TYPE_ICON[item.type] || "📄";
    md += `## ${icon} ${item.label}`;
    if (item.paperLabel) md += `：${item.paperLabel}`;
    md += `\n\n`;
    md += item.type === "extract" ? _formatExtractMd(item.content) : item.content + "\n\n";
    if (idx < items.length - 1) md += "---\n\n";
  });
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url; a.download = `论文研究报告_${date.replace(/\//g, "-")}.md`;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

function _formatExtractMd(content) {
  try {
    const obj = JSON.parse(content);
    if ("research_problem" in obj) {
      return [
        ["研究问题", obj.research_problem], ["研究方法", obj.methodology],
        ["数据集", obj.dataset],            ["评估指标", obj.metrics],
        ["主要结论", obj.conclusion],       ["研究局限", obj.limitations],
      ].map(([k, v]) => `**${k}**\n\n${v || "未提及"}\n\n`).join("");
    }
  } catch (_) {}
  return content + "\n\n";
}

// ── Tab 切换 ──────────────────────────────────────────────────
function switchTab(tab) {
  activeTab = tab;
  document.getElementById("plan-tab-content").classList.toggle("hidden",   tab !== "plan");
  document.getElementById("report-tab-content").classList.toggle("hidden", tab !== "report");
  document.getElementById("tab-btn-plan").classList.toggle("active",   tab === "plan");
  document.getElementById("tab-btn-report").classList.toggle("active", tab === "report");
  if (tab === "report") renderReportDraft();
}

// ═══════════════════════════════════════════════════════════
//  设置面板
// ═══════════════════════════════════════════════════════════
function toggleSettings() {
  document.getElementById("settings-panel").classList.toggle("hidden");
}

function onProviderChange() {
  const provider = document.getElementById("llm-provider").value;
  document.getElementById("base-url-row").classList.toggle("hidden", provider !== "custom");
}

async function fetchModels() {
  const provider = document.getElementById("llm-provider").value;
  const apiKey   = document.getElementById("llm-api-key").value.trim();
  const baseUrl  = document.getElementById("llm-base-url")?.value.trim() || "";
  const statusEl = document.getElementById("model-fetch-status");
  if (!apiKey) { statusEl.textContent = "⚠️ 请先填写 API Key"; return; }
  statusEl.textContent = "拉取中...";
  try {
    const res  = await apiFetch("/models", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ llm_provider:provider, llm_api_key:apiKey,
                             llm_base_url:baseUrl, llm_model:"", tavily_api_key:"" }),
    });
    const data = await res.json();
    if (!res.ok) { statusEl.textContent = "❌ " + data.detail; return; }
    if (data.unsupported) {
      statusEl.textContent = "⚠️ 不支持模型列表，请手动输入";
      statusEl.className = "text-xs text-yellow-600 mt-1 block"; return;
    }
    const models = data.models || [];
    if (!models.length) { statusEl.textContent = "⚠️ 未找到模型，请手动输入"; return; }
    const select = document.getElementById("llm-model-select");
    select.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join("");
    select.classList.remove("hidden");
    document.getElementById("llm-model-input").value = models[0];
    statusEl.textContent = `✅ 共 ${models.length} 个模型`;
    statusEl.className = "text-xs text-gray-400 mt-1 block";
  } catch (e) { statusEl.textContent = "❌ " + e.message; }
}

async function testConnection() {
  const provider = document.getElementById("llm-provider").value;
  const apiKey   = document.getElementById("llm-api-key").value.trim();
  const baseUrl  = document.getElementById("llm-base-url")?.value.trim() || "";
  const model    = document.getElementById("llm-model-input").value.trim();
  if (!apiKey) { setConfigStatus("⚠️ 请先填写 API Key", "text-yellow-600"); return; }
  setConfigStatus("🔗 测试中...", "text-gray-400");
  try {
    const res  = await apiFetch("/ping", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ llm_provider:provider, llm_api_key:apiKey,
                             llm_base_url:baseUrl, llm_model:model, tavily_api_key:"" }),
    });
    const data = await res.json();
    if (data.ok) setConfigStatus(`✅ 连接成功：${data.reply}`, "text-green-600");
    else         setConfigStatus(`❌ ${data.detail}`, "text-red-500");
  } catch (e) { setConfigStatus("❌ " + e.message, "text-red-500"); }
}

async function saveConfig() {
  const cfg = _getCurrentFormValues();
  if (!cfg.apiKey) { setConfigStatus("⚠️ 请填写 API Key", "text-red-500"); return; }
  if (cfg.provider === "custom" && !cfg.baseUrl) { setConfigStatus("⚠️ 中转站需填 Base URL", "text-red-500"); return; }

  // BUG-016 fix：先存本地，无论后端是否成功面板都能立刻显示
  _localSaveConfig({ ...cfg });

  try {
    const res  = await apiFetch("/config", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ llm_provider: cfg.provider, llm_api_key: cfg.apiKey,
                             tavily_api_key: cfg.tavilyKey, llm_base_url: cfg.baseUrl,
                             llm_model: cfg.model }),
    });
    const data = await res.json();
    if (res.ok) {
      setConfigStatus("✅ " + data.message, "text-green-600");
      setTimeout(() => document.getElementById("settings-panel").classList.add("hidden"), 1200);
    } else {
      setConfigStatus("❌ " + data.detail, "text-red-500");
    }
  } catch (e) {
    setConfigStatus("⚠️ 配置已存到本地，后端连接失败：" + e.message, "text-yellow-600");
  }
}

function setConfigStatus(msg, cls) {
  const el = document.getElementById("config-status");
  el.textContent = msg;
  el.className   = `text-sm self-center ${cls}`;
}

// ═══════════════════════════════════════════════════════════
//  PDF 上传
// ═══════════════════════════════════════════════════════════
async function uploadFiles(input) {
  const files = input.files;
  if (!files.length) return;
  for (const file of files) {
    const userText = `上传论文：${file.name}`;
    appendMessage("user", userText);
    _convSave("user", userText, false);
    const loadingId = appendLoading();
    const form = new FormData();
    form.append("file", file);
    try {
      const res  = await apiFetch("/upload", { method:"POST", body:form });
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { detail:text }; }
      removeLoading(loadingId);
      if (res.ok) {
        if (!uploadedPapers.includes(data.paper_id)) uploadedPapers.push(data.paper_id);
        renderPaperList();
        setActivePaper(data.paper_id);
        let msg = `✅ ${data.message}\n- 字符数：${data.char_count.toLocaleString()}\n- 向量索引：${data.indexed ? "已建立" : "未建立"}`;
        if (data.index_note) msg += `\n- ⚠️ ${data.index_note}`;
        appendMessage("agent", msg);
        _convSave("agent", msg, false);
      } else {
        const errMsg = `❌ 上传失败：${data.detail}`;
        appendMessage("agent", errMsg);
        _convSave("agent", errMsg, false);
      }
    } catch (e) {
      removeLoading(loadingId);
      const errMsg = `❌ ${e.message}`;
      appendMessage("agent", errMsg);
      _convSave("agent", errMsg, false);
    }
  }
  input.value = "";
}

// ═══════════════════════════════════════════════════════════
//  论文暂存区 & 工作区
// ═══════════════════════════════════════════════════════════
function renderPaperList() {
  const ul = document.getElementById("paper-list");
  ul.innerHTML = "";
  if (!uploadedPapers.length) {
    ul.innerHTML = '<li class="text-xs text-gray-400 text-center py-2">暂无论文</li>';
    renderWorkspace(); return;
  }
  uploadedPapers.forEach(pid => {
    const isActive   = pid === activePaperId;
    const isSelected = selectedPapers.has(pid);
    const li = document.createElement("li");
    li.className = `paper-row flex items-center gap-1 px-2 py-1.5 rounded-lg transition ${isActive ? "bg-blue-100" : "hover:bg-gray-50"}`;
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = isSelected;
    cb.className = "w-3.5 h-3.5 rounded accent-blue-500 flex-shrink-0 cursor-pointer";
    cb.onclick = e => { e.stopPropagation(); togglePaperSelection(pid); };
    const nameSpan = document.createElement("span");
    nameSpan.className = `flex-1 text-xs truncate cursor-pointer ${isActive ? "text-blue-700 font-semibold" : "text-gray-600"}`;
    nameSpan.textContent = "📄 " + pid; nameSpan.title = pid;
    nameSpan.onclick = () => setActivePaper(pid);
    const del = document.createElement("button");
    del.className = "del-btn text-gray-300 hover:text-red-400 text-base leading-none px-0.5 flex-shrink-0";
    del.textContent = "×"; del.title = "删除";
    del.onclick = e => { e.stopPropagation(); deletePaper(pid); };
    li.appendChild(cb); li.appendChild(nameSpan); li.appendChild(del);
    ul.appendChild(li);
  });
  renderWorkspace();
}

function setActivePaper(pid) {
  activePaperId = pid;
  const label = document.getElementById("active-paper-label");
  if (label) label.textContent = pid ? `— ${pid}` : "";
  renderPaperList();
}

function togglePaperSelection(pid) {
  selectedPapers.has(pid) ? selectedPapers.delete(pid) : selectedPapers.add(pid);
  renderPaperList();
}

async function deletePaper(pid) {
  await apiFetch(`/papers/${pid}`, { method:"DELETE" }).catch(()=>{});
  uploadedPapers = uploadedPapers.filter(p => p !== pid);
  selectedPapers.delete(pid);
  if (activePaperId === pid) {
    activePaperId = uploadedPapers[0] || "";
    const label = document.getElementById("active-paper-label");
    if (label) label.textContent = activePaperId ? `— ${activePaperId}` : "";
  }
  renderPaperList();
}

function clearWorkspace() { selectedPapers.clear(); renderPaperList(); }

function renderWorkspace() {
  const section = document.getElementById("workspace-section");
  const list    = document.getElementById("workspace-list");
  const badge   = document.getElementById("workspace-badge");
  if (selectedPapers.size === 0) { section.classList.add("hidden"); return; }
  section.classList.remove("hidden");
  badge.textContent = selectedPapers.size;
  list.innerHTML = [...selectedPapers].map(pid => `
    <li class="ws-chip">
      <span class="flex-1 truncate text-blue-700" title="${escHtml(pid)}">${escHtml(pid)}</span>
      <button onclick="togglePaperSelection('${escHtml(pid)}')"
        class="text-blue-300 hover:text-red-400 leading-none">×</button>
    </li>`).join("");
}

// ═══════════════════════════════════════════════════════════
//  快捷操作
// ═══════════════════════════════════════════════════════════
async function quickAction(action) {
  if (action === "compare" || action === "gap") {
    const ids = [...selectedPapers];
    if (ids.length < 2) {
      appendMessage("agent", "⚠️ 请先在论文列表中 **勾选至少 2 篇**（出现在工作区后），再执行此操作。");
      return;
    }
    const label    = action === "compare" ? "📊 对比论文" : "🔭 研究缺口分析";
    const subLabel = ids.join(" · ");
    const userMsg  = `${label}：${subLabel}`;
    appendMessage("user", userMsg);
    _convSave("user", userMsg, false);
    planStart(action, label, subLabel);
    const loadingId = appendLoading();
    try {
      const res  = await apiFetch(`/${action}`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ paper_ids: ids }),
      });
      const text = await res.text();
      let data;
      try { data = JSON.parse(text); } catch { data = { detail:text }; }
      removeLoading(loadingId); planDone();
      if (res.ok) {
        appendResult(data.result);
        _convSave("agent", data.result, true);
        addToReport(action, label, subLabel, data.result);
      } else {
        appendMessage("agent", "❌ " + data.detail);
        _convSave("agent", "❌ " + data.detail, false);
      }
    } catch (e) {
      removeLoading(loadingId); planDone();
      appendMessage("agent", "❌ " + e.message);
      _convSave("agent", "❌ " + e.message, false);
    }
    return;
  }

  if (!activePaperId) {
    appendMessage("agent", "⚠️ 请先在左侧点击选中一篇论文。"); return;
  }

  if (action === "citation") {
    const userMsg = `提取参考文献：${activePaperId}`;
    appendMessage("user", userMsg);
    _convSave("user", userMsg, false);
    planStart("citation", "📖 提取参考文献", activePaperId);
    await _chat(
      `请提取论文 ${activePaperId} 的参考文献，使用 citation_tool`,
      { type:"citation", label:"📖 参考文献", paperLabel: activePaperId }
    );
    planDone();
    return;
  }

  const endpointMap = { extract:"/extract", summary:"/summary" };
  const labelMap    = { extract:"🔍 提取关键信息", summary:"📝 生成摘要" };
  const userMsg     = `${labelMap[action]}：${activePaperId}`;
  appendMessage("user", userMsg);
  _convSave("user", userMsg, false);
  planStart(action, labelMap[action], activePaperId);
  const loadingId = appendLoading();
  try {
    const res  = await apiFetch(endpointMap[action], {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ paper_id: activePaperId }),
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { detail:text }; }
    removeLoading(loadingId); planDone();
    if (res.ok) {
      appendResult(data.result);
      _convSave("agent", data.result, true);
      addToReport(action, labelMap[action], activePaperId, data.result);
    } else {
      appendMessage("agent", "❌ " + data.detail);
      _convSave("agent", "❌ " + data.detail, false);
    }
  } catch (e) {
    removeLoading(loadingId); planDone();
    appendMessage("agent", "❌ " + e.message);
    _convSave("agent", "❌ " + e.message, false);
  }
}

// ═══════════════════════════════════════════════════════════
//  对话
// ═══════════════════════════════════════════════════════════
async function sendMessage() {
  const input = document.getElementById("chat-input");
  const text  = input.value.trim();
  if (!text) return;
  input.value = "";
  appendMessage("user", text);
  _convSave("user", text, false);
  const labelPreview = text.slice(0, 30) + (text.length > 30 ? "…" : "");
  planStart("chat", "💬 对话问答", labelPreview);
  await _chat(text, { type:"chat", label:"💬 " + labelPreview, paperLabel: activePaperId || "" });
  planDone();
}

async function _chat(message, reportMeta = null) {
  const loadingId = appendLoading();
  try {
    const res  = await apiFetch("/chat", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ message, paper_id: activePaperId }),
    });
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { detail:text }; }
    removeLoading(loadingId);
    if (res.ok) {
      appendResult(data.result);
      _convSave("agent", data.result, true);
      if (reportMeta) addToReport(reportMeta.type, reportMeta.label, reportMeta.paperLabel, data.result);
    } else {
      appendMessage("agent", "❌ " + data.detail);
      _convSave("agent", "❌ " + data.detail, false);
    }
  } catch (e) {
    removeLoading(loadingId);
    appendMessage("agent", "❌ " + e.message);
    _convSave("agent", "❌ " + e.message, false);
  }
}

// ═══════════════════════════════════════════════════════════
//  历史消息保存辅助
// ═══════════════════════════════════════════════════════════
function _convSave(role, text, isResult) {
  if (!currentConv) return;
  // 用第一条用户消息作为对话标题
  if (role === "user" && currentConv.messages.filter(m => m.role === "user").length === 0) {
    currentConv.title = text.slice(0, 22) + (text.length > 22 ? "…" : "");
    _updateConvTitleDisplay();
  }
  currentConv.messages.push({ role, text, isResult, time: new Date().toISOString() });
  _saveCurrentConv();
  // BUG-014 fix：必须在 _saveCurrentConv() 之后渲染，
  // 此时 currentConv 已被加入 convHistory，侧边栏才能正确显示当前对话
  renderConvHistory();
}

// ═══════════════════════════════════════════════════════════
//  输出格式化
// ═══════════════════════════════════════════════════════════
function formatAgentResult(text) {
  const trimmed = (text || "").trim();
  if (trimmed.startsWith("{")) {
    try {
      const obj = JSON.parse(trimmed);
      if ("research_problem" in obj || "methodology" in obj) return buildExtractCard(obj);
    } catch (_) {}
  }
  return marked.parse(text || "");
}

function buildExtractCard(obj) {
  const fields = [
    { key:"research_problem", label:"研究问题", icon:"🔬", border:"#3b82f6", bg:"#eff6ff", lc:"#1d4ed8" },
    { key:"methodology",      label:"研究方法", icon:"🧪", border:"#8b5cf6", bg:"#f5f3ff", lc:"#6d28d9" },
    { key:"dataset",          label:"数据集",   icon:"📊", border:"#10b981", bg:"#ecfdf5", lc:"#065f46" },
    { key:"metrics",          label:"评估指标", icon:"📈", border:"#f59e0b", bg:"#fffbeb", lc:"#92400e" },
    { key:"conclusion",       label:"主要结论", icon:"🎯", border:"#06b6d4", bg:"#ecfeff", lc:"#155e75" },
    { key:"limitations",      label:"研究局限", icon:"⚠️", border:"#ef4444", bg:"#fef2f2", lc:"#991b1b" },
  ];
  return `<div class="extract-card">${fields.map(f => `
    <div class="extract-field" style="border-left-color:${f.border};background:${f.bg};">
      <div class="extract-label" style="color:${f.lc};">${f.icon} ${f.label}</div>
      <div class="extract-value">${escHtml(obj[f.key] || "未提及")}</div>
    </div>`).join("")}</div>`;
}

// ═══════════════════════════════════════════════════════════
//  消息渲染（不写入历史，纯 DOM 操作）
// ═══════════════════════════════════════════════════════════
function _appendMessageRaw(role, text) {
  const container = document.getElementById("messages");
  const wrapper = document.createElement("div");
  wrapper.className = `flex items-start gap-2 ${role === "user" ? "flex-row-reverse" : ""}`;
  const avatar = document.createElement("span");
  avatar.className = "text-xl mt-0.5 flex-shrink-0";
  avatar.textContent = role === "user" ? "👤" : "🤖";
  const bubble = document.createElement("div");
  bubble.className = `px-4 py-3 text-sm max-w-2xl prose ${role === "user" ? "bubble-user" : "bubble-agent"}`;
  bubble.innerHTML = marked.parse(text || "");
  wrapper.appendChild(avatar); wrapper.appendChild(bubble);
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
}

function _appendResultRaw(text) {
  const container = document.getElementById("messages");
  const wrapper = document.createElement("div");
  wrapper.className = "flex items-start gap-2";
  const avatar = document.createElement("span");
  avatar.className = "text-xl mt-0.5 flex-shrink-0";
  avatar.textContent = "🤖";
  const bubble = document.createElement("div");
  bubble.className = "px-4 py-3 text-sm max-w-2xl prose bubble-agent";
  bubble.innerHTML = formatAgentResult(text);
  wrapper.appendChild(avatar); wrapper.appendChild(bubble);
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
}

/** 渲染消息（不写历史，供外部调用） */
function appendMessage(role, text) { _appendMessageRaw(role, text); }
function appendResult(text)        { _appendResultRaw(text); }

function appendLoading() {
  const id = "loading-" + Date.now();
  const container = document.getElementById("messages");
  const wrapper = document.createElement("div");
  wrapper.id = id; wrapper.className = "flex items-start gap-2";
  wrapper.innerHTML = `
    <span class="text-xl mt-0.5">🤖</span>
    <div class="bubble-agent px-4 py-3 text-sm flex gap-1 items-center">
      <span class="dot-flashing">●</span>
      <span class="dot-flashing" style="animation-delay:.2s">●</span>
      <span class="dot-flashing" style="animation-delay:.4s">●</span>
    </div>`;
  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeLoading(id) { document.getElementById(id)?.remove(); }

function escHtml(str) {
  return String(str)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

// ═══════════════════════════════════════════════════════════
//  欢迎消息
// ═══════════════════════════════════════════════════════════
function _renderWelcomeMessage() {
  const container = document.getElementById("messages");
  container.innerHTML = "";
  const wrapper = document.createElement("div");
  wrapper.className = "flex items-start gap-2";
  wrapper.innerHTML = `
    <span class="text-xl mt-0.5">🤖</span>
    <div class="bubble-agent px-4 py-3 text-sm max-w-xl">
      你好！我是<b>论文研究助手</b>，可以帮你提取、摘要、对比和分析学术论文。<br><br>
      已预加载 3 篇演示论文：<br>
      · <code>demo_multiagent_survey</code> — 多智能体系统综述<br>
      · <code>demo_transformer_attention</code> — Transformer 架构<br>
      · <code>demo_bert_pretraining</code> — BERT 预训练<br><br>
      💡 <b>推荐体验</b>：勾选 Transformer + BERT → 工作区「对比」，
      完成后右侧「报告草稿」会自动收集结果，可一键导出 Markdown。
    </div>`;
  container.appendChild(wrapper);
}

// ═══════════════════════════════════════════════════════════
//  页面加载
// ═══════════════════════════════════════════════════════════
window.addEventListener("load", async () => {
  // ── 1. 恢复 LLM 配置到后端（最关键：后端内存重启后会丢失配置）──
  loadSavedConfigs();
  const lastActiveName = localStorage.getItem("active_config_name");
  if (lastActiveName && savedConfigs.length) {
    const idx = savedConfigs.findIndex(c => c.name === lastActiveName);
    if (idx >= 0) {
      activeConfigName = lastActiveName;  // 先更新显示状态
      renderConfigPanel();               // 面板立刻高亮，不等 await
      applyConfigByIndex(idx, true);     // 静默推送到后端（不阻塞页面渲染）
    }
  }
  renderConfigPanel();  // 无激活配置时也要渲染面板列表

  // ── 2. 初始化对话：恢复最近一条，或新建 ──────────────────────
  if (convHistory.length > 0) {
    currentConv = convHistory[0];
    const container = document.getElementById("messages");
    container.innerHTML = "";
    currentConv.messages.forEach(msg => {
      if (msg.isResult) _appendResultRaw(msg.text);
      else              _appendMessageRaw(msg.role, msg.text);
    });
    if (container.children.length === 0) _renderWelcomeMessage();
    else container.scrollTop = container.scrollHeight;
  } else {
    currentConv = _createConv();
    _renderWelcomeMessage();
  }
  _updateConvTitleDisplay();
  renderConvHistory();

  // ── 3. 报告草稿 ────────────────────────────────────────────
  renderReportDraft();

  // ── 4. 拉取当前会话已有论文列表 ────────────────────────────
  try {
    const res  = await apiFetch("/papers");
    const data = await res.json();
    uploadedPapers = data.papers || [];
    if (uploadedPapers.length) {
      renderPaperList();
      setActivePaper(uploadedPapers[0]);
    }
  } catch (_) {}
});
