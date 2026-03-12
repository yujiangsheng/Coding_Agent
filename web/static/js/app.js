/**
 * Turing Web UI — 前端交互逻辑 (VS Code 风格)
 *
 * 功能:
 * - SSE 流式聊天 (fetch + ReadableStream)
 * - Markdown 渲染 (marked.js + highlight.js)
 * - Command Palette (⌘⇧P)
 * - Activity Bar 面板切换
 * - 可拖拽侧栏/底部面板
 * - 底部输出面板 (Terminal-like)
 * - 通知系统 (Toast)
 * - 上下文菜单
 * - 快捷键系统
 */

// =========================================================================
// DOM 引用
// =========================================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  messages:         $('#messages'),
  chatContainer:    $('#chat-container'),
  welcomeScreen:    $('#welcome-screen'),
  userInput:        $('#user-input'),
  sendBtn:          $('#send-btn'),
  stopBtn:          $('#stop-btn'),
  sidebar:          $('#sidebar'),
  sash:             $('#sidebar-sash'),
  panelSash:        $('#panel-sash'),
  panelArea:        $('#panel-area'),
  panelBody:        $('#panel-body'),

  // Command Palette
  cmdPaletteOverlay: $('#command-palette-overlay'),
  cmdPaletteInput:   $('#command-palette-input'),
  cmdPaletteList:    $('#command-palette-list'),

  // Status bar
  statusIndicator:   $('#status-indicator'),
  statusbarMemory:   $('#statusbar-memory'),
  statusbarTasks:    $('#statusbar-tasks'),
  breadcrumbSession: $('#breadcrumb-session'),

  // Sidebar panels
  chatHistoryList:     $('#chat-history-list'),
  memorySearchInput:   $('#memory-search-input'),
  memorySearchResults: $('#memory-search-results'),
  strategiesList:      $('#strategies-list'),
  evolutionLog:        $('#evolution-log'),

  // Stats
  statWorking:     $('#stat-working'),
  statLongterm:    $('#stat-longterm'),
  statStrategies:  $('#stat-strategies'),
  statProjects:    $('#stat-projects'),
  statTasks:       $('#stat-tasks'),
  statSuccessRate: $('#stat-success-rate'),
  statEvoEvents:   $('#stat-evo-events'),

  // Badges
  badgeChat:       $('#badge-chat'),
  badgeMemory:     $('#badge-memory'),
  badgeEvolution:  $('#badge-evolution'),

  // Notifications
  notificationContainer: $('#notification-container'),

  // Context menu
  contextMenu:     $('#context-menu'),
};

// =========================================================================
// 状态
// =========================================================================

let isStreaming = false;
let abortController = null;
let messageCount = 0;
let currentAgentMsgEl = null;
let toolCallCount = 0;
let panelLogCount = 0;

// =========================================================================
// Marked.js 配置
// =========================================================================

if (typeof marked !== 'undefined') {
  marked.setOptions({
    breaks: true,
    gfm: true,
    highlight: function(code, lang) {
      if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
        try { return hljs.highlight(code, { language: lang }).value; } catch (_) {}
      }
      if (typeof hljs !== 'undefined') {
        try { return hljs.highlightAuto(code).value; } catch (_) {}
      }
      return code;
    },
  });
}

function renderMarkdown(text) {
  if (typeof marked === 'undefined') {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
  let html = marked.parse(text);
  // Add code headers with copy buttons
  html = html.replace(
    /<pre><code class="language-(\w+)">/g,
    '<pre><div class="code-header"><span>$1</span><button class="copy-btn" onclick="copyCode(this)"><i class="codicon codicon-copy"></i> 复制</button></div><code class="language-$1">'
  );
  html = html.replace(
    /<pre><code>/g,
    '<pre><div class="code-header"><span>code</span><button class="copy-btn" onclick="copyCode(this)"><i class="codicon codicon-copy"></i> 复制</button></div><code>'
  );
  return html;
}

window.copyCode = function(btn) {
  const code = btn.closest('pre').querySelector('code');
  if (!code) return;
  navigator.clipboard.writeText(code.textContent).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="codicon codicon-check"></i> 已复制';
    btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('copied'); }, 2000);
  });
};

// =========================================================================
// 工具函数
// =========================================================================

function now() {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    dom.chatContainer.scrollTo({
      top: dom.chatContainer.scrollHeight,
      behavior: 'smooth'
    });
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function truncate(str, max = 200) {
  return str.length > max ? str.slice(0, max) + '…' : str;
}

function setStatus(icon, text) {
  dom.statusIndicator.innerHTML = `<i class="codicon codicon-${icon}"></i> ${text}`;
  if (icon.includes('loading') || text.includes('处理')) {
    dom.statusIndicator.classList.add('streaming');
  } else {
    dom.statusIndicator.classList.remove('streaming');
  }
}

// =========================================================================
// 通知系统 (VS Code Toast Notifications)
// =========================================================================

function showNotification(message, type = 'info', duration = 4000) {
  const iconMap = {
    info: 'codicon-info',
    success: 'codicon-pass',
    warning: 'codicon-warning',
    error: 'codicon-error'
  };
  const toast = document.createElement('div');
  toast.className = 'notification-toast';
  toast.innerHTML = `
    <i class="codicon ${iconMap[type] || iconMap.info} notification-icon ${type}"></i>
    <div class="notification-body">${escapeHtml(message)}</div>
    <button class="notification-close" onclick="dismissNotification(this)">
      <i class="codicon codicon-close"></i>
    </button>
  `;
  dom.notificationContainer.appendChild(toast);

  if (duration > 0) {
    setTimeout(() => dismissNotification(toast.querySelector('.notification-close')), duration);
  }
}

window.dismissNotification = function(btnOrEl) {
  const toast = btnOrEl.closest ? btnOrEl.closest('.notification-toast') : btnOrEl;
  if (!toast) return;
  toast.classList.add('removing');
  setTimeout(() => toast.remove(), 150);
};

// =========================================================================
// 底部面板日志 (Output Panel)
// =========================================================================

function panelLog(text, type = 'info') {
  const iconMap = { info: '●', success: '✓', error: '✗', warning: '⚠' };
  const entry = document.createElement('div');
  entry.className = 'panel-log-entry';
  entry.innerHTML = `
    <span class="panel-log-time">[${now()}]</span>
    <span class="panel-log-icon ${type}">${iconMap[type] || '●'}</span>
    <span class="panel-log-text">${escapeHtml(text)}</span>
  `;
  dom.panelBody.appendChild(entry);
  dom.panelBody.scrollTop = dom.panelBody.scrollHeight;
  panelLogCount++;
  const badge = $('#panel-output-badge');
  if (badge) badge.textContent = panelLogCount;
}

// =========================================================================
// 消息渲染
// =========================================================================

function addUserMessage(text) {
  dom.welcomeScreen.classList.add('hidden');
  const el = document.createElement('div');
  el.className = 'msg msg-user';
  el.dataset.rawText = text;
  el.innerHTML = `
    <div class="msg-avatar"><i class="codicon codicon-account"></i></div>
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-name">You</span>
        <span class="msg-time">${now()}</span>
        <button class="edit-msg-btn icon-btn" title="编辑并重新发送">
          <i class="codicon codicon-edit"></i>
        </button>
      </div>
      <div class="msg-content">${escapeHtml(text)}</div>
    </div>
  `;
  el.querySelector('.edit-msg-btn').addEventListener('click', () => startEditMessage(el));
  dom.messages.appendChild(el);
  messageCount++;
  updateChatHistory(text);
  scrollToBottom();
  panelLog(`用户: ${truncate(text, 80)}`);
}

function startEditMessage(msgEl) {
  if (isStreaming) return;
  if (msgEl.querySelector('.edit-area')) return;

  const contentEl = msgEl.querySelector('.msg-content');
  const rawText = msgEl.dataset.rawText || contentEl.textContent;

  contentEl.style.display = 'none';

  const editArea = document.createElement('div');
  editArea.className = 'edit-area';
  editArea.innerHTML = `
    <textarea class="edit-textarea" rows="3">${escapeHtml(rawText)}</textarea>
    <div class="edit-actions">
      <button class="btn btn-secondary edit-cancel">取消</button>
      <button class="btn btn-primary edit-confirm">
        <i class="codicon codicon-send"></i> 重新发送
      </button>
    </div>
  `;
  contentEl.parentElement.appendChild(editArea);

  const textarea = editArea.querySelector('.edit-textarea');
  textarea.focus();
  textarea.setSelectionRange(textarea.value.length, textarea.value.length);
  autoResize(textarea);
  textarea.addEventListener('input', () => autoResize(textarea));

  editArea.querySelector('.edit-cancel').addEventListener('click', () => {
    editArea.remove();
    contentEl.style.display = '';
  });

  editArea.querySelector('.edit-confirm').addEventListener('click', () => {
    const newText = textarea.value.trim();
    if (!newText) return;
    removeMessagesFrom(msgEl);
    sendMessage(newText);
  });

  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      editArea.querySelector('.edit-confirm').click();
    } else if (e.key === 'Escape') {
      editArea.querySelector('.edit-cancel').click();
    }
  });
}

function removeMessagesFrom(startEl) {
  const parent = dom.messages;
  const children = Array.from(parent.children);
  const idx = children.indexOf(startEl);
  if (idx === -1) return;
  for (let i = children.length - 1; i >= idx; i--) {
    children[i].remove();
  }
}

function startAgentMessage() {
  const el = document.createElement('div');
  el.className = 'msg msg-agent';
  el.innerHTML = `
    <div class="msg-avatar">T</div>
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-name">Turing</span>
        <span class="msg-time">${now()}</span>
      </div>
      <div class="msg-content"></div>
    </div>
  `;
  dom.messages.appendChild(el);
  currentAgentMsgEl = el.querySelector('.msg-content');
  scrollToBottom();
  return currentAgentMsgEl;
}

function addThinking(text) {
  const el = document.createElement('div');
  el.className = 'thinking-line';
  el.innerHTML = `<span class="thinking-dot"><span></span><span></span><span></span></span> ${escapeHtml(text)}`;
  dom.messages.appendChild(el);
  scrollToBottom();
  panelLog(`思考: ${truncate(text, 100)}`);
}

function addToolCall(name, args) {
  toolCallCount++;
  const argsStr = truncate(JSON.stringify(args, null, 2), 500);
  const el = document.createElement('div');
  el.className = 'tool-block';
  el.innerHTML = `
    <div class="tool-header collapsed" onclick="this.classList.toggle('collapsed')">
      <i class="codicon codicon-chevron-down"></i>
      <span class="tool-name">${escapeHtml(name)}</span>
      <span class="tool-status">
        <i class="codicon codicon-loading codicon-modifier-spin"></i>
      </span>
    </div>
    <div class="tool-body"><div class="tool-args">参数:\n${escapeHtml(argsStr)}</div><div class="tool-result-area"></div></div>
  `;
  dom.messages.appendChild(el);
  scrollToBottom();
  panelLog(`工具调用: ${name}(...)`, 'info');
  return el;
}

function addToolResult(toolBlock, name, result) {
  if (!toolBlock) return;
  const statusEl = toolBlock.querySelector('.tool-status');
  const resultArea = toolBlock.querySelector('.tool-result-area');
  const hasError = result && result.error;

  if (statusEl) {
    statusEl.className = 'tool-status ' + (hasError ? 'error' : 'success');
    statusEl.innerHTML = hasError
      ? '<i class="codicon codicon-error"></i>'
      : '<i class="codicon codicon-check"></i>';
  }

  if (resultArea) {
    const resultStr = truncate(JSON.stringify(result, null, 2), 800);
    resultArea.textContent = '\n结果:\n' + resultStr;
  }
  scrollToBottom();
  panelLog(`工具结果: ${name} → ${hasError ? '失败' : '成功'}`, hasError ? 'error' : 'success');
}

function addReflection(data) {
  const outcome = data.outcome || 'unknown';
  const cls = outcome === 'success' ? 'success' : 'failure';
  const el = document.createElement('div');
  el.className = 'reflection-line';
  el.innerHTML = `
    <i class="codicon codicon-bookmark"></i>
    经验记录: <span class="tag ${cls}">${outcome}</span>
    (${data.actions_count || 0} 次工具调用)
  `;
  dom.messages.appendChild(el);
  scrollToBottom();
  panelLog(`反思完成: ${outcome}, ${data.actions_count || 0} 次工具调用`, outcome === 'success' ? 'success' : 'warning');
}

function addLoadingIndicator() {
  const el = document.createElement('div');
  el.className = 'loading-indicator';
  el.id = 'loading-indicator';
  el.innerHTML = `
    <div class="loading-dots"><span></span><span></span><span></span></div>
    <span>Turing 思考中...</span>
  `;
  dom.messages.appendChild(el);
  scrollToBottom();
  return el;
}

function removeLoadingIndicator() {
  const el = document.getElementById('loading-indicator');
  if (el) el.remove();
}

function addErrorMessage(text) {
  const el = document.createElement('div');
  el.className = 'thinking-line';
  el.style.color = 'var(--color-error)';
  el.innerHTML = `<i class="codicon codicon-error"></i> ${escapeHtml(text)}`;
  dom.messages.appendChild(el);
  scrollToBottom();
  panelLog(text, 'error');
}

// =========================================================================
// SSE 流式聊天
// =========================================================================

async function sendMessage(text) {
  if (isStreaming || !text.trim()) return;
  isStreaming = true;
  abortController = new AbortController();
  dom.sendBtn.disabled = true;
  dom.sendBtn.style.display = 'none';
  dom.stopBtn.classList.add('visible');
  setStatus('loading~spin', '处理中...');

  addUserMessage(text);
  dom.userInput.value = '';
  autoResize(dom.userInput);

  const loadingEl = addLoadingIndicator();
  let agentContentEl = null;
  let agentTextBuffer = '';
  let lastToolBlock = null;

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: abortController.signal,
    });

    if (!resp.ok) {
      removeLoadingIndicator();
      addErrorMessage(`请求失败: ${resp.status} ${resp.statusText}`);
      showNotification(`请求失败: ${resp.status}`, 'error');
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;

        let event;
        try { event = JSON.parse(jsonStr); } catch (_) { continue; }

        switch (event.type) {
          case 'thinking':
            removeLoadingIndicator();
            addThinking(event.content);
            break;

          case 'tool_call':
            removeLoadingIndicator();
            lastToolBlock = addToolCall(event.name, event.args);
            break;

          case 'tool_result':
            addToolResult(lastToolBlock, event.name, event.result);
            lastToolBlock = null;
            break;

          case 'text':
            removeLoadingIndicator();
            if (!agentContentEl) {
              agentContentEl = startAgentMessage();
            }
            agentTextBuffer += event.content;
            agentContentEl.innerHTML = renderMarkdown(agentTextBuffer);
            scrollToBottom();
            break;

          case 'reflection':
            addReflection(event.data);
            break;

          case 'error':
            removeLoadingIndicator();
            addErrorMessage(event.content);
            break;

          case 'done':
            removeLoadingIndicator();
            break;

          case 'stream_end':
            break;
        }
      }
    }
  } catch (err) {
    removeLoadingIndicator();
    if (err.name === 'AbortError') {
      panelLog('用户中断了生成', 'warning');
      showNotification('已停止生成', 'info', 2000);
    } else {
      addErrorMessage(`连接错误: ${err.message}`);
      showNotification(`连接错误: ${err.message}`, 'error');
    }
  } finally {
    isStreaming = false;
    abortController = null;
    dom.sendBtn.disabled = false;
    dom.sendBtn.style.display = '';
    dom.stopBtn.classList.remove('visible');
    setStatus('check', '就绪');
    agentContentEl = null;
    agentTextBuffer = '';
    lastToolBlock = null;
    refreshStats();
  }
}

function stopStreaming() {
  if (abortController) {
    abortController.abort();
  }
}

// =========================================================================
// Command Palette (VS Code ⌘⇧P)
// =========================================================================

const commands = [
  { id: 'new-session',    label: '新建会话',           icon: 'codicon-add',                  keybinding: '⌘N',   action: () => newSession() },
  { id: 'toggle-panel',   label: '切换底部面板',       icon: 'codicon-layout-panel',         keybinding: '⌃`',   action: () => togglePanel() },
  { id: 'toggle-sidebar', label: '切换侧栏',           icon: 'codicon-layout-sidebar-left',  keybinding: '⌘B',   action: () => toggleSidebar() },
  { id: 'clear-chat',     label: '清空当前对话',       icon: 'codicon-clear-all',            keybinding: '',      action: () => clearChat() },
  { id: 'index-project',  label: '索引项目到 RAG',     icon: 'codicon-folder-library',       keybinding: '',      action: () => openModal('modal-index') },
  { id: 'learn-ai',       label: '向 AI 工具学习',     icon: 'codicon-lightbulb',            keybinding: '',      action: () => openModal('modal-learn') },
  { id: 'focus-input',    label: '聚焦输入框',         icon: 'codicon-edit',                 keybinding: '⌘L',   action: () => dom.userInput.focus() },
  { id: 'panel-chat',     label: '切换到: 对话面板',   icon: 'codicon-comment-discussion',   keybinding: '',      action: () => switchPanel('chat') },
  { id: 'panel-memory',   label: '切换到: 记忆系统',   icon: 'codicon-database',             keybinding: '',      action: () => switchPanel('memory') },
  { id: 'panel-evolution', label: '切换到: 自我演化',  icon: 'codicon-pulse',                keybinding: '',      action: () => switchPanel('evolution') },
  { id: 'panel-explorer', label: '切换到: 探索',       icon: 'codicon-search',               keybinding: '',      action: () => switchPanel('explorer') },
  { id: 'panel-settings', label: '切换到: 设置',       icon: 'codicon-settings-gear',        keybinding: '',      action: () => switchPanel('settings') },
  { id: 'refresh-stats',  label: '刷新统计数据',       icon: 'codicon-refresh',              keybinding: '',      action: () => { refreshStats(); showNotification('已刷新统计数据', 'info', 2000); } },
  { id: 'shutdown',       label: '退出服务',           icon: 'codicon-close',                keybinding: '⌘Q',   action: () => shutdownServer() },
];

let cmdSelectedIndex = 0;

function openCommandPalette() {
  dom.cmdPaletteOverlay.classList.add('visible');
  dom.cmdPaletteInput.value = '';
  dom.cmdPaletteInput.focus();
  cmdSelectedIndex = 0;
  renderCommandList('');
}

function closeCommandPalette() {
  dom.cmdPaletteOverlay.classList.remove('visible');
  dom.cmdPaletteInput.value = '';
}

function renderCommandList(filter) {
  const lower = filter.toLowerCase();
  const filtered = commands.filter(c => c.label.toLowerCase().includes(lower) || c.id.includes(lower));
  if (cmdSelectedIndex >= filtered.length) cmdSelectedIndex = Math.max(0, filtered.length - 1);

  if (filtered.length === 0) {
    dom.cmdPaletteList.innerHTML = '<div class="command-palette-empty">没有匹配的命令</div>';
    return;
  }

  dom.cmdPaletteList.innerHTML = filtered.map((c, i) => `
    <div class="command-palette-item ${i === cmdSelectedIndex ? 'selected' : ''}" data-cmd-index="${i}">
      <i class="codicon ${c.icon}"></i>
      <span class="cmd-label">${escapeHtml(c.label)}</span>
      ${c.keybinding ? `<span class="cmd-keybinding">${c.keybinding}</span>` : ''}
    </div>
  `).join('');

  // Click handlers
  dom.cmdPaletteList.querySelectorAll('.command-palette-item').forEach((el, i) => {
    el.addEventListener('click', () => {
      closeCommandPalette();
      filtered[i].action();
    });
    el.addEventListener('mouseenter', () => {
      cmdSelectedIndex = i;
      dom.cmdPaletteList.querySelectorAll('.command-palette-item').forEach((e, j) => {
        e.classList.toggle('selected', j === i);
      });
    });
  });
}

function executeSelectedCommand() {
  const items = dom.cmdPaletteList.querySelectorAll('.command-palette-item');
  if (items.length === 0) return;
  const lower = dom.cmdPaletteInput.value.toLowerCase();
  const filtered = commands.filter(c => c.label.toLowerCase().includes(lower) || c.id.includes(lower));
  if (filtered[cmdSelectedIndex]) {
    closeCommandPalette();
    filtered[cmdSelectedIndex].action();
  }
}

// =========================================================================
// Sidebar 数据加载
// =========================================================================

async function refreshStats() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    const mem = data.memory || {};
    const evo = data.evolution || {};

    if (dom.statWorking)    dom.statWorking.textContent    = mem.working_items ?? 0;
    if (dom.statLongterm)   dom.statLongterm.textContent   = mem.long_term_items ?? 0;
    if (dom.statStrategies) dom.statStrategies.textContent = mem.persistent_strategies ?? 0;
    if (dom.statProjects)   dom.statProjects.textContent   = mem.persistent_projects ?? 0;

    const tasks = evo.total_tasks ?? 0;
    if (dom.statTasks)      dom.statTasks.textContent      = tasks;
    if (dom.statEvoEvents)  dom.statEvoEvents.textContent  = evo.evolution_log_entries ?? 0;

    dom.statusbarMemory.innerHTML = `<i class="codicon codicon-database"></i> 记忆: ${(mem.long_term_items ?? 0) + (mem.working_items ?? 0)}`;
    dom.statusbarTasks.innerHTML  = `<i class="codicon codicon-pulse"></i> 任务: ${tasks}`;

    const outcomes = evo.outcomes || {};
    const total = Object.values(outcomes).reduce((a, b) => a + b, 0);
    const success = outcomes.success || 0;
    if (dom.statSuccessRate) {
      dom.statSuccessRate.textContent = total > 0 ? `${success}/${total} (${Math.round(success/total*100)}%)` : '—';
    }

    // Update badges
    const memTotal = (mem.long_term_items ?? 0) + (mem.working_items ?? 0);
    if (dom.badgeMemory) dom.badgeMemory.textContent = memTotal > 0 ? memTotal : '';
    if (dom.badgeEvolution) dom.badgeEvolution.textContent = (evo.evolution_log_entries ?? 0) > 0 ? evo.evolution_log_entries : '';
  } catch (_) {}
}

async function searchMemory(query) {
  if (!query.trim()) {
    dom.memorySearchResults.innerHTML = '<div class="empty-hint">输入关键词搜索记忆</div>';
    return;
  }
  try {
    const resp = await fetch(`/api/memory/search?q=${encodeURIComponent(query)}`);
    const data = await resp.json();
    if (!data.results || data.results.length === 0) {
      dom.memorySearchResults.innerHTML = '<div class="empty-hint">未找到相关记忆</div>';
      return;
    }
    dom.memorySearchResults.innerHTML = data.results.map(r => `
      <div class="memory-result">
        <span class="memory-layer">${r.layer || '?'}</span>
        ${(r.tags || []).map(t => `<span class="memory-layer" style="background:var(--bg-active)">${escapeHtml(t)}</span>`).join('')}
        <div class="memory-content">${escapeHtml(truncate(r.content || '', 300))}</div>
      </div>
    `).join('');
  } catch (_) {
    dom.memorySearchResults.innerHTML = '<div class="empty-hint">搜索失败</div>';
  }
}

async function loadStrategies() {
  try {
    const resp = await fetch('/api/strategies');
    const data = await resp.json();
    if (!data.strategies || data.strategies.length === 0) {
      dom.strategiesList.innerHTML = '<div class="empty-hint">暂无策略模板</div>';
      return;
    }
    dom.strategiesList.innerHTML = data.strategies.map(s => {
      const rate = s.data ? (s.data.success_rate || 0) : 0;
      return `<div class="strategy-item">
        <span class="strategy-name">${escapeHtml(s.name)}</span>
        <span class="strategy-rate">${Math.round(rate * 100)}%</span>
      </div>`;
    }).join('');
  } catch (_) {}
}

async function loadEvolutionLog() {
  try {
    const resp = await fetch('/api/evolution');
    const data = await resp.json();
    if (!data.log || data.log.length === 0) {
      dom.evolutionLog.innerHTML = '<div class="empty-hint">暂无日志</div>';
      return;
    }
    dom.evolutionLog.innerHTML = data.log.slice(-5).reverse().map(entry => `
      <div class="memory-result">
        <span class="memory-layer">v${entry.version || '?'}</span>
        <div class="memory-content">
          任务: ${entry.total_tasks || 0} · 成功率: ${Math.round((entry.overall_success_rate || 0) * 100)}%
        </div>
      </div>
    `).join('');
  } catch (_) {}
}

// =========================================================================
// Chat history (sidebar)
// =========================================================================

function updateChatHistory(text) {
  const list = dom.chatHistoryList;
  const hint = list.querySelector('.empty-hint');
  if (hint) hint.remove();

  const item = document.createElement('div');
  item.className = 'tree-item';
  item.innerHTML = `
    <i class="codicon codicon-comment"></i>
    <span>${escapeHtml(truncate(text, 36))}</span>
    <span class="tree-badge">${now().slice(0, 5)}</span>
  `;
  list.appendChild(item);
}

// =========================================================================
// Activity Bar 面板切换
// =========================================================================

function switchPanel(panelId) {
  $$('.activity-item').forEach(el => el.classList.toggle('active', el.dataset.panel === panelId));
  $$('.sidebar-panel').forEach(el => el.classList.toggle('active', el.id === `panel-${panelId}`));

  // Ensure sidebar is visible
  dom.sidebar.style.display = '';

  if (panelId === 'memory') refreshStats();
  if (panelId === 'evolution') { refreshStats(); loadStrategies(); loadEvolutionLog(); }
}

// =========================================================================
// Toggle sidebar / panel
// =========================================================================

let sidebarVisible = true;
function toggleSidebar() {
  sidebarVisible = !sidebarVisible;
  dom.sidebar.style.display = sidebarVisible ? '' : 'none';
  dom.sash.style.display = sidebarVisible ? '' : 'none';
}

let panelVisible = false;
function togglePanel() {
  panelVisible = !panelVisible;
  dom.panelArea.classList.toggle('visible', panelVisible);
  dom.panelSash.style.display = panelVisible ? '' : 'none';
}

function clearChat() {
  dom.messages.innerHTML = '';
  dom.welcomeScreen.classList.remove('hidden');
  messageCount = 0;
  showNotification('对话已清空', 'info', 2000);
}

// =========================================================================
// Sidebar section collapse
// =========================================================================

function initSectionToggles() {
  $$('.section-title').forEach(el => {
    el.addEventListener('click', () => el.classList.toggle('collapsed'));
  });
}

// =========================================================================
// Sidebar resize (sash)
// =========================================================================

function initSashResize() {
  const sash = dom.sash;
  const sidebar = dom.sidebar;
  let startX = 0, startW = 0;

  sash.addEventListener('mousedown', (e) => {
    e.preventDefault();
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    sash.classList.add('dragging');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });

  function onMove(e) {
    const diff = e.clientX - startX;
    const newW = Math.max(170, Math.min(600, startW + diff));
    sidebar.style.width = newW + 'px';
  }

  function onUp() {
    sash.classList.remove('dragging');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
}

// =========================================================================
// Panel resize (horizontal sash)
// =========================================================================

function initPanelResize() {
  const sash = dom.panelSash;
  const panel = dom.panelArea;
  let startY = 0, startH = 0;

  sash.style.display = 'none'; // initially hidden

  sash.addEventListener('mousedown', (e) => {
    e.preventDefault();
    startY = e.clientY;
    startH = panel.offsetHeight;
    sash.classList.add('dragging');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });

  function onMove(e) {
    const diff = startY - e.clientY;
    const newH = Math.max(100, Math.min(500, startH + diff));
    panel.style.height = newH + 'px';
  }

  function onUp() {
    sash.classList.remove('dragging');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
}

// =========================================================================
// 自动增长 textarea
// =========================================================================

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

// =========================================================================
// Modal 管理
// =========================================================================

function openModal(id) {
  document.getElementById(id).style.display = 'flex';
}

function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

function initModals() {
  $$('.modal-close').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('.modal-overlay').style.display = 'none';
    });
  });

  $$('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.style.display = 'none';
    });
  });

  $('#btn-index-project').addEventListener('click', () => openModal('modal-index'));
  $('#btn-do-index').addEventListener('click', async () => {
    const path = $('#index-path-input').value.trim();
    if (!path) return;
    closeModal('modal-index');
    sendMessage(`/index ${path}`);
  });

  $('#btn-learn-ai').addEventListener('click', () => openModal('modal-learn'));
  $('#btn-do-learn').addEventListener('click', async () => {
    const tool = $('#learn-tool-select').value;
    const task = $('#learn-task-input').value.trim() || 'general';
    closeModal('modal-learn');
    sendMessage(`分析 ${tool} 在 ${task} 方面的策略`);
  });
}

// =========================================================================
// Context Menu
// =========================================================================

function showContextMenu(x, y, items) {
  const menu = dom.contextMenu;
  menu.innerHTML = items.map(item => {
    if (item.separator) return '<div class="context-menu-separator"></div>';
    return `
      <div class="context-menu-item" data-action="${item.id}">
        <i class="codicon ${item.icon || ''}"></i>
        <span>${escapeHtml(item.label)}</span>
        ${item.shortcut ? `<span class="menu-shortcut">${item.shortcut}</span>` : ''}
      </div>
    `;
  }).join('');

  // Position
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  menu.classList.add('visible');

  // Adjust if overflows
  requestAnimationFrame(() => {
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) menu.style.left = (x - rect.width) + 'px';
    if (rect.bottom > window.innerHeight) menu.style.top = (y - rect.height) + 'px';
  });

  // Click handlers
  menu.querySelectorAll('.context-menu-item').forEach(el => {
    el.addEventListener('click', () => {
      const action = el.dataset.action;
      hideContextMenu();
      const item = items.find(i => i.id === action);
      if (item && item.action) item.action();
    });
  });
}

function hideContextMenu() {
  dom.contextMenu.classList.remove('visible');
}

// =========================================================================
// 新会话
// =========================================================================

async function newSession() {
  try {
    await fetch('/api/new-session', { method: 'POST' });
    dom.messages.innerHTML = '';
    dom.welcomeScreen.classList.remove('hidden');
    dom.chatHistoryList.innerHTML = '<div class="empty-hint">发送第一条消息开始对话</div>';
    messageCount = 0;
    toolCallCount = 0;
    dom.breadcrumbSession.textContent = '新会话';
    refreshStats();
    showNotification('已创建新会话', 'info', 2000);
    panelLog('--- 新会话 ---');
  } catch (_) {}
}

async function shutdownServer() {
  if (!confirm('确定要退出服务吗？')) return;
  try {
    panelLog('正在关闭服务器...', 'warning');
    showNotification('服务器正在关闭...', 'warning', 3000);
    await fetch('/api/shutdown', { method: 'POST' });
    setStatus('circle-slash', '已断开');
    document.title = 'Turing — 已停止';
  } catch (_) {
    setStatus('circle-slash', '已断开');
  }
}

// =========================================================================
// 全局快捷键
// =========================================================================

function initKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    const isMac = navigator.platform.includes('Mac');
    const mod = isMac ? e.metaKey : e.ctrlKey;

    // ⌘⇧P / Ctrl+Shift+P — Command Palette
    if (mod && e.shiftKey && e.key === 'p') {
      e.preventDefault();
      if (dom.cmdPaletteOverlay.classList.contains('visible')) {
        closeCommandPalette();
      } else {
        openCommandPalette();
      }
      return;
    }

    // Escape — close overlays
    if (e.key === 'Escape') {
      if (dom.cmdPaletteOverlay.classList.contains('visible')) {
        closeCommandPalette();
        return;
      }
      hideContextMenu();
      // Stop streaming
      if (isStreaming) {
        stopStreaming();
        return;
      }
    }

    // ⌘N / Ctrl+N — New session
    if (mod && e.key === 'n') {
      e.preventDefault();
      newSession();
      return;
    }

    // ⌘B / Ctrl+B — Toggle sidebar
    if (mod && e.key === 'b') {
      e.preventDefault();
      toggleSidebar();
      return;
    }

    // Ctrl+` — Toggle panel
    if (e.ctrlKey && e.key === '`') {
      e.preventDefault();
      togglePanel();
      return;
    }

    // ⌘L / Ctrl+L — Focus input
    if (mod && e.key === 'l') {
      e.preventDefault();
      dom.userInput.focus();
      return;
    }

    // ⌘Q / Ctrl+Q — Shutdown server
    if (mod && e.key === 'q') {
      e.preventDefault();
      shutdownServer();
      return;
    }
  });

  // Command palette input handling
  dom.cmdPaletteInput.addEventListener('input', () => {
    cmdSelectedIndex = 0;
    renderCommandList(dom.cmdPaletteInput.value);
  });

  dom.cmdPaletteInput.addEventListener('keydown', (e) => {
    const items = dom.cmdPaletteList.querySelectorAll('.command-palette-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      cmdSelectedIndex = Math.min(cmdSelectedIndex + 1, items.length - 1);
      updateCmdSelection(items);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      cmdSelectedIndex = Math.max(cmdSelectedIndex - 1, 0);
      updateCmdSelection(items);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      executeSelectedCommand();
    }
  });

  // Click backdrop to close command palette
  dom.cmdPaletteOverlay.querySelector('.command-palette-backdrop').addEventListener('click', closeCommandPalette);
}

function updateCmdSelection(items) {
  items.forEach((el, i) => el.classList.toggle('selected', i === cmdSelectedIndex));
  const selected = items[cmdSelectedIndex];
  if (selected) selected.scrollIntoView({ block: 'nearest' });
}

// =========================================================================
// Title bar menu dropdowns
// =========================================================================

function initTitleBarMenus() {
  const menuConfig = {
    file: [
      { id: 'new-session', icon: 'codicon-add', label: '新建会话', shortcut: '⌘N', action: () => newSession() },
      { separator: true },
      { id: 'index-project', icon: 'codicon-folder-library', label: '索引项目...', action: () => openModal('modal-index') },
      { separator: true },
      { id: 'shutdown', icon: 'codicon-close', label: '退出', shortcut: '⌘Q', action: () => shutdownServer() },
    ],
    edit: [
      { id: 'clear-chat', icon: 'codicon-clear-all', label: '清空对话', action: () => clearChat() },
    ],
    view: [
      { id: 'toggle-sidebar', icon: 'codicon-layout-sidebar-left', label: '切换侧边栏', shortcut: '⌘B', action: () => toggleSidebar() },
      { id: 'toggle-panel', icon: 'codicon-layout-panel', label: '切换面板', shortcut: '⌃`', action: () => togglePanel() },
      { separator: true },
      { id: 'cmd-palette', icon: 'codicon-terminal', label: '命令面板...', shortcut: '⌘⇧P', action: () => openCommandPalette() },
    ],
    help: [
      { id: 'about', icon: 'codicon-info', label: '关于 Turing', action: () => { switchPanel('settings'); } },
      { id: 'shortcuts', icon: 'codicon-record-keys', label: '快捷键参考', action: () => { switchPanel('settings'); } },
    ],
  };

  $$('.titlebar-menu-item').forEach(el => {
    el.addEventListener('click', (e) => {
      const menuId = el.dataset.menu;
      const items = menuConfig[menuId];
      if (!items) return;

      $$('.titlebar-menu-item').forEach(m => m.classList.remove('open'));
      el.classList.add('open');

      const rect = el.getBoundingClientRect();
      showContextMenu(rect.left, rect.bottom, items);
    });
  });
}

// =========================================================================
// 初始化
// =========================================================================

function init() {
  // Send message
  dom.sendBtn.addEventListener('click', () => {
    const text = dom.userInput.value.trim();
    if (text) sendMessage(text);
  });

  // Enter to send, Shift+Enter for newline
  dom.userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const text = dom.userInput.value.trim();
      if (text) sendMessage(text);
    }
  });

  // Stop button
  dom.stopBtn.addEventListener('click', stopStreaming);

  // Auto-resize textarea
  dom.userInput.addEventListener('input', () => autoResize(dom.userInput));

  // Activity bar
  $$('.activity-item').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.panel) switchPanel(btn.dataset.panel);
    });
  });

  // Sidebar sections
  initSectionToggles();

  // Sash resize
  initSashResize();
  initPanelResize();

  // Modals
  initModals();

  // New session / clear buttons
  $('#btn-new-session').addEventListener('click', newSession);
  const clearBtn = $('#btn-clear-chat');
  if (clearBtn) clearBtn.addEventListener('click', clearChat);

  // Memory search (debounced)
  let searchTimer = null;
  dom.memorySearchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      searchMemory(dom.memorySearchInput.value);
    }, 400);
  });

  // Refresh buttons
  $('#btn-refresh-memory').addEventListener('click', () => {
    refreshStats();
    showNotification('记忆数据已刷新', 'info', 2000);
  });
  $('#btn-refresh-evolution').addEventListener('click', () => {
    refreshStats();
    loadStrategies();
    loadEvolutionLog();
    showNotification('演化数据已刷新', 'info', 2000);
  });

  // Welcome hint buttons
  $$('.hint-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const prompt = btn.dataset.prompt;
      if (prompt) {
        dom.userInput.value = prompt;
        sendMessage(prompt);
      }
    });
  });

  // Title bar buttons
  $('#btn-toggle-panel').addEventListener('click', togglePanel);
  $('#btn-toggle-sidebar-vis').addEventListener('click', toggleSidebar);
  $('#open-command-palette').addEventListener('click', openCommandPalette);
  $('#btn-shutdown').addEventListener('click', shutdownServer);

  // Panel buttons
  $('#btn-close-panel').addEventListener('click', () => { panelVisible = false; dom.panelArea.classList.remove('visible'); dom.panelSash.style.display = 'none'; });
  $('#btn-clear-panel').addEventListener('click', () => { dom.panelBody.innerHTML = ''; panelLogCount = 0; const badge = $('#panel-output-badge'); if (badge) badge.textContent = ''; });

  // Keyboard shortcuts
  initKeyboardShortcuts();

  // Title bar menus
  initTitleBarMenus();

  // Close context menu on click outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.context-menu') && !e.target.closest('.titlebar-menu-item')) {
      hideContextMenu();
      $$('.titlebar-menu-item').forEach(m => m.classList.remove('open'));
    }
  });

  // Right-click context menu on chat area
  dom.chatContainer.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    showContextMenu(e.clientX, e.clientY, [
      { id: 'copy', icon: 'codicon-copy', label: '复制', shortcut: '⌘C', action: () => document.execCommand('copy') },
      { separator: true },
      { id: 'clear', icon: 'codicon-clear-all', label: '清空对话', action: () => clearChat() },
      { id: 'new', icon: 'codicon-add', label: '新建会话', shortcut: '⌘N', action: () => newSession() },
    ]);
  });

  // Initial stats
  refreshStats();

  // Focus input
  dom.userInput.focus();

  // Initial panel log
  panelLog('Turing Web UI 已启动', 'success');

  // File Explorer initialization
  initFileExplorer();
}

// =========================================================================
// File Explorer & Code Viewer
// =========================================================================

let explorerRootPath = '';
let expandedDirs = new Set();
let openFileTabs = []; // [{path, name, language, content, lineCount}]
let activeFileTab = null;

function initFileExplorer() {
  const collapseBtn = $('#btn-explorer-up');
  const homeBtn = $('#btn-explorer-home');
  const refreshBtn = $('#btn-explorer-refresh');

  if (collapseBtn) collapseBtn.addEventListener('click', () => {
    expandedDirs.clear();
    loadExplorerRoot();
  });
  if (homeBtn) homeBtn.addEventListener('click', () => loadExplorerRoot());
  if (refreshBtn) refreshBtn.addEventListener('click', () => reloadExplorer());

  // Chat tab click — switch back to chat view
  const chatTab = document.querySelector('#editor-tabs .tab[data-tab="chat"]');
  if (chatTab) chatTab.addEventListener('click', () => switchToChatTab());

  // Code viewer buttons
  const copyBtn = $('#btn-code-copy');
  const wrapBtn = $('#btn-code-wrap');
  if (copyBtn) copyBtn.addEventListener('click', copyViewerCode);
  if (wrapBtn) wrapBtn.addEventListener('click', toggleWordWrap);

  // Load root directory
  loadExplorerRoot();
}

async function loadExplorerRoot() {
  const tree = $('#explorer-tree');
  const pathDisplay = $('#explorer-path-display');
  if (!tree) return;

  tree.innerHTML = '<div class="empty-hint">加载中...</div>';

  try {
    const resp = await fetch('/api/files/list?path=');
    const data = await resp.json();

    if (!resp.ok) {
      tree.innerHTML = '<div class="empty-hint">加载失败</div>';
      return;
    }

    explorerRootPath = data.path || '';
    if (pathDisplay) pathDisplay.textContent = explorerRootPath;

    tree.innerHTML = '';
    renderTreeItems(tree, data.items || [], 0);
  } catch (e) {
    tree.innerHTML = '<div class="empty-hint">网络错误</div>';
  }
}

function renderTreeItems(container, items, depth) {
  if (!items || items.length === 0) {
    const hint = document.createElement('div');
    hint.className = 'empty-hint';
    hint.style.paddingLeft = (20 + depth * 16) + 'px';
    hint.textContent = '空目录';
    container.appendChild(hint);
    return;
  }

  items.forEach(item => {
    if (item.is_dir) {
      const group = document.createElement('div');
      group.className = 'explorer-dir-group';

      const el = document.createElement('div');
      el.className = 'explorer-item';
      el.style.paddingLeft = (4 + depth * 16) + 'px';
      el.dataset.path = item.path;

      const isExpanded = expandedDirs.has(item.path);
      el.innerHTML = `<i class="codicon codicon-chevron-${isExpanded ? 'down' : 'right'} tree-toggle"></i><i class="codicon codicon-folder${isExpanded ? '-opened' : ''} folder-icon"></i><span>${escapeHtml(item.name)}</span>`;

      const childrenDiv = document.createElement('div');
      childrenDiv.className = 'explorer-children';
      childrenDiv.style.display = isExpanded ? '' : 'none';

      el.addEventListener('click', () => toggleTreeDir(item.path, el, childrenDiv, depth + 1));

      group.appendChild(el);
      group.appendChild(childrenDiv);
      container.appendChild(group);

      // If was expanded, auto-load children
      if (isExpanded) {
        loadTreeChildren(item.path, childrenDiv, depth + 1);
      }
    } else {
      const el = document.createElement('div');
      el.className = 'explorer-item';
      el.style.paddingLeft = (4 + depth * 16) + 'px';
      el.dataset.path = item.path;
      const langClass = getFileLangClass(item.name);
      el.innerHTML = `<i class="codicon tree-toggle-spacer"></i><i class="codicon codicon-file file-icon ${langClass}"></i><span>${escapeHtml(item.name)}</span>`;
      el.addEventListener('click', () => openFile(item.path));
      container.appendChild(el);
    }
  });
}

async function toggleTreeDir(path, el, childrenDiv, childDepth) {
  const isExpanded = expandedDirs.has(path);

  if (isExpanded) {
    // Collapse
    expandedDirs.delete(path);
    childrenDiv.style.display = 'none';
    const toggle = el.querySelector('.tree-toggle');
    if (toggle) { toggle.classList.replace('codicon-chevron-down', 'codicon-chevron-right'); }
    const folder = el.querySelector('.folder-icon');
    if (folder) { folder.classList.replace('codicon-folder-opened', 'codicon-folder'); }
  } else {
    // Expand
    expandedDirs.add(path);
    childrenDiv.style.display = '';
    const toggle = el.querySelector('.tree-toggle');
    if (toggle) { toggle.classList.replace('codicon-chevron-right', 'codicon-chevron-down'); }
    const folder = el.querySelector('.folder-icon');
    if (folder) { folder.classList.replace('codicon-folder', 'codicon-folder-opened'); }
    // Load children if not yet loaded
    if (childrenDiv.children.length === 0) {
      await loadTreeChildren(path, childrenDiv, childDepth);
    }
  }
}

async function loadTreeChildren(path, container, depth) {
  container.innerHTML = '<div class="empty-hint" style="padding-left:' + (20 + depth * 16) + 'px">加载中...</div>';
  try {
    const resp = await fetch('/api/files/list?path=' + encodeURIComponent(path));
    const data = await resp.json();
    if (!resp.ok) {
      container.innerHTML = '<div class="empty-hint" style="padding-left:' + (20 + depth * 16) + 'px">加载失败</div>';
      return;
    }
    container.innerHTML = '';
    renderTreeItems(container, data.items || [], depth);
  } catch (e) {
    container.innerHTML = '<div class="empty-hint" style="padding-left:' + (20 + depth * 16) + 'px">网络错误</div>';
  }
}

async function reloadExplorer() {
  // Reload root while preserving expanded state
  const tree = $('#explorer-tree');
  if (!tree) return;
  tree.innerHTML = '<div class="empty-hint">加载中...</div>';
  try {
    const resp = await fetch('/api/files/list?path=');
    const data = await resp.json();
    if (!resp.ok) {
      tree.innerHTML = '<div class="empty-hint">加载失败</div>';
      return;
    }
    tree.innerHTML = '';
    renderTreeItems(tree, data.items || [], 0);
  } catch (e) {
    tree.innerHTML = '<div class="empty-hint">网络错误</div>';
  }
}

function getFileLangClass(name) {
  const ext = name.split('.').pop().toLowerCase();
  const map = {
    py: 'python', js: 'javascript', ts: 'typescript', jsx: 'javascript', tsx: 'typescript',
    html: 'html', htm: 'html', css: 'css', json: 'json', md: 'markdown',
    yml: 'yaml', yaml: 'yaml',
  };
  return map[ext] || '';
}

async function openFile(path) {
  // Check if already open
  const existing = openFileTabs.find(t => t.path === path);
  if (existing) {
    switchToFileTab(existing.path);
    return;
  }

  try {
    const resp = await fetch('/api/files/read?path=' + encodeURIComponent(path));
    const data = await resp.json();

    if (!resp.ok) {
      showNotification(data.error || '无法打开文件', 'error');
      return;
    }

    const tabData = {
      path: data.path,
      name: data.name,
      language: data.language,
      content: data.content,
      lineCount: data.line_count,
      size: data.size,
    };

    openFileTabs.push(tabData);
    addFileTab(tabData);
    switchToFileTab(tabData.path);
    panelLog(`打开文件: ${tabData.name}`, 'info');
  } catch (e) {
    showNotification('打开文件失败', 'error');
  }
}

function addFileTab(tabData) {
  const tabsBar = $('#editor-tabs');
  if (!tabsBar) return;

  const actionsDiv = tabsBar.querySelector('.tabs-actions');
  const tab = document.createElement('div');
  tab.className = 'tab';
  tab.dataset.tab = 'file';
  tab.dataset.filePath = tabData.path;

  const iconClass = getFileLangClass(tabData.name);
  tab.innerHTML = `
    <i class="tab-icon codicon codicon-file ${iconClass ? 'file-icon ' + iconClass : ''}"></i>
    <span class="tab-label">${escapeHtml(tabData.name)}</span>
    <button class="tab-close" title="Close"><i class="codicon codicon-close"></i></button>
  `;

  tab.addEventListener('click', (e) => {
    if (!e.target.closest('.tab-close')) {
      switchToFileTab(tabData.path);
    }
  });

  tab.querySelector('.tab-close').addEventListener('click', (e) => {
    e.stopPropagation();
    closeFileTab(tabData.path);
  });

  tabsBar.insertBefore(tab, actionsDiv);
}

function switchToFileTab(path) {
  const tabData = openFileTabs.find(t => t.path === path);
  if (!tabData) return;

  activeFileTab = path;

  // Update tab active state
  $$('#editor-tabs .tab').forEach(t => t.classList.remove('active'));
  const tab = document.querySelector(`#editor-tabs .tab[data-file-path="${CSS.escape(path)}"]`);
  if (tab) tab.classList.add('active');

  // Show code viewer, hide chat
  const viewer = $('#code-viewer-container');
  const chat = $('#chat-container');
  const inputArea = document.querySelector('.input-area');
  if (viewer) viewer.style.display = 'flex';
  if (chat) chat.style.display = 'none';
  if (inputArea) inputArea.style.display = 'none';

  // Populate viewer
  $('#code-viewer-filename').textContent = tabData.name;
  $('#code-viewer-lang').textContent = tabData.language || 'text';
  $('#code-viewer-size').textContent = formatFileSize(tabData.size);

  // Line numbers
  const gutter = $('#code-viewer-gutter');
  gutter.innerHTML = '';
  for (let i = 1; i <= tabData.lineCount; i++) {
    const span = document.createElement('span');
    span.className = 'line-num';
    span.textContent = i;
    gutter.appendChild(span);
  }

  // Code content with syntax highlighting
  const codeEl = $('#code-viewer-code');
  codeEl.textContent = tabData.content;
  codeEl.className = '';
  codeEl.removeAttribute('data-highlighted');
  if (typeof hljs !== 'undefined') {
    const lang = tabData.language && tabData.language !== 'plaintext' ? tabData.language : null;
    if (lang && hljs.getLanguage(lang)) {
      codeEl.className = 'language-' + lang;
      hljs.highlightElement(codeEl);
    } else if (lang) {
      // Language not registered, try auto-detection
      const result = hljs.highlightAuto(tabData.content);
      codeEl.innerHTML = result.value;
      codeEl.className = 'hljs language-' + (result.language || 'plaintext');
    } else {
      // plaintext — still apply hljs for consistent styling
      codeEl.className = 'language-plaintext';
    }
  }

  // Update breadcrumb
  const parts = tabData.path.split('/');
  const breadcrumb = document.querySelector('.breadcrumb');
  if (breadcrumb) {
    breadcrumb.innerHTML = parts.map((p, i) =>
      (i > 0 ? '<i class="codicon codicon-chevron-right"></i>' : '') +
      `<span>${escapeHtml(p)}</span>`
    ).join('');
  }
}

function switchToChatTab() {
  activeFileTab = null;

  // Update tab active state
  $$('#editor-tabs .tab').forEach(t => t.classList.remove('active'));
  const chatTab = document.querySelector('#editor-tabs .tab[data-tab="chat"]');
  if (chatTab) chatTab.classList.add('active');

  // Show chat, hide code viewer
  const viewer = $('#code-viewer-container');
  const chat = $('#chat-container');
  const inputArea = document.querySelector('.input-area');
  if (viewer) viewer.style.display = 'none';
  if (chat) chat.style.display = '';
  if (inputArea) inputArea.style.display = '';

  // Restore breadcrumb
  const breadcrumb = document.querySelector('.breadcrumb');
  if (breadcrumb) {
    breadcrumb.innerHTML = '<span>Turing</span><i class="codicon codicon-chevron-right"></i><span>Chat</span><i class="codicon codicon-chevron-right"></i><span id="breadcrumb-session">新会话</span>';
  }
}

function closeFileTab(path) {
  openFileTabs = openFileTabs.filter(t => t.path !== path);
  const tab = document.querySelector(`#editor-tabs .tab[data-file-path="${CSS.escape(path)}"]`);
  if (tab) tab.remove();

  if (activeFileTab === path) {
    // Switch to last file tab or chat
    if (openFileTabs.length > 0) {
      switchToFileTab(openFileTabs[openFileTabs.length - 1].path);
    } else {
      switchToChatTab();
    }
  }
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function copyViewerCode() {
  const codeEl = $('#code-viewer-code');
  if (!codeEl) return;
  navigator.clipboard.writeText(codeEl.textContent).then(() => {
    showNotification('代码已复制到剪贴板', 'success', 2000);
  });
}

function toggleWordWrap() {
  const pre = $('#code-viewer-pre');
  if (!pre) return;
  pre.classList.toggle('word-wrap');
}

document.addEventListener('DOMContentLoaded', init);
