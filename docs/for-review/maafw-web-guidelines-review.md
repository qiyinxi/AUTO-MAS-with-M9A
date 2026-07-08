# MaaFW 前端 Web Interface Guidelines 审查报告

> 审查标准: [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines)
> 审查日期: 2026-07-08
> 审查范围: `MaaFWScriptEdit.vue`、`MaaFWUserEdit.vue`、`MaaFWTaskOptionEditor.vue`、`MaaFWDescriptionView.vue`

---

## MaaFWScriptEdit.vue

`MaaFWScriptEdit.vue:54` - decorative icon `QuestionCircleOutlined` missing `aria-hidden="true"` (repeats at lines 73, 228, 260, 297, 330, 391, 435, 460, 475, 567, 593)

`MaaFWScriptEdit.vue:11` - `<img>` decorative icon missing explicit `width`/`height` (CLS risk)

`MaaFWScriptEdit.vue:149` - loading text "正在读取 interface.json..." → "正在读取 interface.json…"

`MaaFWScriptEdit.vue:161` - loading text "正在准备 MaaFW 运行环境..." → "正在准备 MaaFW 运行环境…"

`MaaFWScriptEdit.vue:783` - `<img>` decorative icon missing explicit `width`/`height`

`MaaFWScriptEdit.vue:29` - icon-only button context (返回 has text label, but `<ArrowLeftOutlined>` inside button — OK here, the text "返回" is visible)

`MaaFWScriptEdit.vue:1644` - `handleCancel` navigates without unsaved-changes guard — no `beforeunload` or router guard for in-flight saves (`isSaving`)

`MaaFWScriptEdit.vue:79` - readonly input without `aria-readonly` or visual disabled indication; looks editable to screen readers

`MaaFWScriptEdit.vue:58` - input `placeholder="请输入脚本名称"` → "请输入脚本名称…" (end with …)

`MaaFWScriptEdit.vue:80` - input `placeholder="请选择 MaaFramework 项目目录"` → "请选择 MaaFramework 项目目录…"

`MaaFWScriptEdit.vue:339` - input `placeholder="请输入模拟器实例索引"` → "请输入模拟器实例索引…"

`MaaFWScriptEdit.vue:398` - input `placeholder="请选择实际启动的游戏 exe"` → "请选择实际启动的游戏 exe…"

`MaaFWScriptEdit.vue:574` - input `placeholder="留空时使用全局 Mirror 酱 CDK"` → "留空时使用全局 Mirror 酱 CDK…"

`MaaFWScriptEdit.vue:724` - select `placeholder="先读取 interface 后选择任务"` → "先读取 interface 后选择任务…"

✓ 按钮使用 `<a-button>` 语义组件 — pass
✓ 无 `transition: all` — pass (transitions list properties explicitly)
✓ 导航链接使用 `<router-link>` — pass
✓ `v-html` 未在此文件中使用 — pass

---

## MaaFWUserEdit.vue

`MaaFWUserEdit.vue:53` - decorative icon `QuestionCircleOutlined` missing `aria-hidden="true"` (repeats at lines 126, 144)

`MaaFWUserEdit.vue:29` - `<img>` missing explicit `width`/`height` (CLS risk)

`MaaFWUserEdit.vue:59` - input `placeholder="请输入用户名称"` → "请输入用户名称…"

`MaaFWUserEdit.vue:133` - input `placeholder="仅用于本地记录"` → "仅用于本地记录…"

`MaaFWUserEdit.vue:150` - input `placeholder="仅用于本地记录"` → "仅用于本地记录…"

`MaaFWUserEdit.vue:192` - loading text "正在读取 interface.json..." → "正在读取 interface.json…"

`MaaFWUserEdit.vue:210` - custom popup menu (`add-task-popup`) missing `role="menu"`, items missing `role="menuitem"` — not using semantic HTML for menu

`MaaFWUserEdit.vue:223-271` - `<button type="button">` with `@click` in custom menu — no `@keydown` handlers for keyboard navigation (arrow keys, Enter, Escape)

`MaaFWUserEdit.vue:210` - `@click.stop` on `<div>` wrapping the menu toggle — should be a `<button>` for the trigger action

`MaaFWUserEdit.vue:349` - `<div class="task-row" @click="selectTask">` — action on `<div>`, should be `<button>` or add `role="button" tabindex="0" @keydown.enter`

`MaaFWUserEdit.vue:374` - `@click.stop` on `<a-space>` — action propagation prevention on non-semantic element

`MaaFWUserEdit.vue:353` - `<img>` missing explicit `width`/`height`

`MaaFWUserEdit.vue:411` - `<img>` missing explicit `width`/`height`

`MaaFWUserEdit.vue:335-402` - `draggable` area covers entire `.task-row` — no drag handle separation, no `inert` on dragged elements, no `touch-action: manipulation` during drag

`MaaFWUserEdit.vue:44` - heading `<h3>` used for section titles inside a card — no `<h1>` on the page; heading hierarchy starts at h3 (acceptable for nested card content, but page-level h1 missing)

`MaaFWUserEdit.vue:1766` - `transition:` lists `background-color 0.2s ease, border-color 0.2s ease` — pass (explicit properties, not `all`)

`MaaFWUserEdit.vue:451` - destructive action (delete task) uses `a-popconfirm` — pass (has confirmation)

`MaaFWUserEdit.vue:514` - email input `placeholder="邮件收件地址"` — missing `type="email"` and `inputmode="email"`; no `autocomplete="email"`

`MaaFWUserEdit.vue:525` - password input missing `autocomplete="off"` (non-auth field, password managers may auto-fill)

`MaaFWUserEdit.vue:130` - account input `placeholder="仅用于本地记录"` — missing `autocomplete="off"`

✓ 上移/下移按钮有 `aria-label` — pass (lines 379, 392)
✓ 无 `transition: all` — pass
✓ 无 `outline-none` — pass
✓ 通知开关使用 `<a-switch>` 语义组件 — pass
✓ 预设卡片使用 `<a-button>` — pass

---

## MaaFWTaskOptionEditor.vue

`MaaFWTaskOptionEditor.vue:19` - decorative icon `QuestionCircleOutlined` missing `aria-hidden="true"`

`MaaFWTaskOptionEditor.vue:12` - `<img>` missing explicit `width`/`height`

`MaaFWTaskOptionEditor.vue:77` - `<img>` missing explicit `width`/`height`

`MaaFWTaskOptionEditor.vue:112` - input `placeholder` from dynamic content — OK (data-driven)

`MaaFWTaskOptionEditor.vue:85-98` - `<a-input-number>` for integer/decimal inputs — missing `inputmode="numeric"` (handled by Ant Design internally, but explicit is better)

`MaaFWTaskOptionEditor.vue:9` - `.map()` over `visibleOptions` renders all items — if option count > 50, should virtualize (unlikely for game task options, but worth noting)

`MaaFWTaskOptionEditor.vue:130` - warning alert for unsupported type — error message states problem only, no fix/next step: "不支持的配置项类型：${option.type}" → add "请联系脚本作者或升级 AUTO-MAS"

✓ 递归组件使用 `lineage` 防循环 — pass
✓ 无 `transition: all` — pass
✓ 无 `v-html` — pass (description rendered by `MaaFWDescriptionView`)

---

## MaaFWDescriptionView.vue

`MaaFWDescriptionView.vue:7` - `v-html` usage — documented as sanitized, pass with caveat

`MaaFWDescriptionView.vue:11` - `<img>` missing explicit `width`/`height` (preview image in modal)

`MaaFWDescriptionView.vue:85-131` - custom HTML sanitizer — functional but doesn't handle `style` attribute injection or CSS-based XSS; consider using a battle-tested library like DOMPurify

`MaaFWDescriptionView.vue:158` - `window.electronAPI?.openUrl?.(link.href)` — optional chaining on potentially undefined API, OK

✓ links get `target="_blank" rel="noreferrer noopener"` — pass
✓ images sanitized to block non-http/data URIs — pass
✓ markdown rendering with sanitization — pass

---

## 汇总统计

| 类别 | 数量 |
|------|------|
| Accessibility (aria, keyboard, semantic HTML) | 8 |
| Focus States | 0 (Ant Design handles) |
| Forms (autocomplete, type, placeholder) | 9 |
| Animation (prefers-reduced-motion, transition) | 0 violations |
| Typography (...) | 5 |
| Content Handling (truncation, empty states) | 0 (handled) |
| Images (width/height, lazy) | 7 |
| Navigation & State (unsaved changes) | 2 |
| Touch & Interaction (drag, touch-action) | 1 |
| Anti-patterns | 0 (`transition: all` not found) |

**总计: 32 findings**

### 高优先级 (P0)

1. `MaaFWUserEdit.vue:349` — `<div @click>` 应改为 `<button>` 或添加 `role="button" tabindex="0"` + 键盘处理
2. `MaaFWUserEdit.vue:210-271` — 自定义弹出菜单缺少键盘导航和 ARIA role
3. `MaaFWUserEdit.vue:335` — draggable 区域与点击选中冲突，缺少 drag handle
4. `MaaFWScriptEdit.vue:1644` / `MaaFWUserEdit.vue` — 返回导航缺少未保存变更确认

### 中优先级 (P1)

5. 所有文件 — `<img>` 缺少 `width`/`height`（7 处）— CLS 风险
6. 所有文件 — 装饰性图标缺少 `aria-hidden="true"`（约 13 处）
7. `MaaFWUserEdit.vue:514` — 邮件输入缺少 `type="email"` 和 `autocomplete="email"`
8. `MaaFWUserEdit.vue:525` — 密码输入缺少 `autocomplete="off"`
9. `MaaFWDescriptionView.vue:85` — 自建 sanitizer 建议迁移到 DOMPurify

### 低优先级 (P2)

10. 所有文件 — placeholder 文本缺少尾部 `…`（5 处）
11. 所有文件 — loading 文本缺少尾部 `…`（2 处）
12. `MaaFWTaskOptionEditor.vue:130` — 错误消息缺少修复建议
13. `MaaFWScriptEdit.vue:79` — readonly 输入缺少 `aria-readonly`
