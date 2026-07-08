# MaaFW 项目配置页 & 用户页 UX/UI 优化规格文档

> 状态：待实施
> 日期：2026-07-08
> 范围：`MaaFWScriptEdit.vue`、`MaaFWUserEdit.vue`、`MaaFWTaskOptionEditor.vue`、`MaaFWDescriptionView.vue`
> 约束：继续使用 Ant Design Vue，不新增 MaaFW 专属颜色系统；兼容亮色和暗色主题

---

## 一、项目配置页 (`MaaFWScriptEdit.vue`)

### 1.1 [P0] 首屏分步引导

**现状问题：** 页面在一个 `a-card` 中平铺 4 大区块（基本信息、控制方式、项目更新、运行配置），用户一进来看到大量表单字段，认知负担高。未读取 interface 时大部分区域为 disabled 空状态，视觉上很压抑。

**优化方案：** 按配置依赖链引入分步引导，使用 `a-steps` 组件在页面顶部显示进度。

**依赖链：**
```
Step 1: 选择项目目录 → 读取 interface
Step 2: 选择控制方式 + 游戏资源
Step 3: 配置项目更新（可选）
Step 4: 配置运行参数（可选）
```

**实现要点：**
- 在 `.config-card` 上方（面包屑下方）添加 `a-steps` 组件，`current` 绑定到当前步骤
- Step 1 完成条件：`previewData` 不为 null（interface 读取成功）
- Step 2 完成条件：`maafwConfig.Info.Controller` 和 `maafwConfig.Info.Resource` 均有值
- Step 3 和 Step 4 无强制完成条件，用户可跳过
- 未到达的步骤区域用 `a-collapse` 默认折叠，或用 `v-show` + 灰色遮罩 + "请先完成上一步"提示
- 已完成的步骤可点击回到任意步骤编辑
- 步骤之间切换使用 `<Transition>` 做淡入淡出，过渡时长 200ms

**交互细节：**
- `a-steps` 使用 `size="small"`，放在 card 内部标题下方
- 每个 step 的 `title` 文案：① 选择项目 ② 控制配置 ③ 更新设置 ④ 运行参数
- 当用户在 Step 1 成功读取 interface 后，自动推进到 Step 2 并展开对应区域
- 步骤状态：`wait` / `process` / `finish`，通过计算属性自动判定

---

### 1.2 [P0] interface 空状态引导增强

**现状问题：** 当前空状态只是一个 `a-empty` + "尚未读取 interface.json" 文字，缺少视觉引导和操作入口。

**优化方案：** 在 interface 未读取时，替换 `a-empty` 为自定义引导卡片。

**设计要求：**
- 引导卡片居中显示，包含一个插图（可用 Ant Design 的 `InboxOutlined` 或自定义 SVG 插图，放大到 64px）
- 标题："开始配置 MaaFW 项目"
- 描述文案："选择一个包含 `interface.json` 的项目目录，系统将自动解析可用的控制器、资源、任务和选项"
- 在引导卡片内放置一个放大的主按钮："选择项目目录"（`a-button type="primary" size="large"`），点击触发现有的 `selectMaaFWPath`
- 卡片整体使用虚线边框（`border: 1px dashed var(--ant-color-border)`），背景用极浅色（`var(--ant-color-fill-quaternary)`）
- 卡片最大宽度 480px，水平居中

**实现要点：**
- 替换现有的 `<a-empty class="interface-empty" description="尚未读取 interface.json" />`
- 在引导卡片下方可选显示"如何获取 interface.json？"的帮助链接（暂用 `#`，后续接入文档）

---

### 1.3 [P0] 项目目录按钮组布局优化

**现状问题：** 项目目录行有 4 个紧挨的按钮（输入框 + 选择文件夹 + 读取 interface + 准备运行环境），用 `a-input-group compact` 挤在一起。窄屏下溢出，视觉层级不清晰。

**优化方案：** 将主操作内嵌到输入框，次要操作下沉到独立行。

**布局变更：**
```
Before:
  [只读输入框 | 选择文件夹 | 读取 interface | 准备运行环境]  ← 全部挤在一行

After:
  [只读输入框 | 选择文件夹]  ← 主操作，类似 a-input-search 模式
  [读取 interface] [准备运行环境]  ← 次要操作，输入框下方独立行，右对齐
```

**实现要点：**
- 输入框 + "选择文件夹"按钮保留 `a-input-group compact`
- "读取 interface"和"准备运行环境"移到输入框下方，用 `<div class="path-secondary-actions">` 包裹
- 次要操作按钮使用 `a-button` 默认样式（不 type="primary"），size 用 `middle`
- "准备运行环境"按钮前添加 `a-divider type="vertical"` 或 `a-space :size="small"`
- 次要操作行在 768px 以下改为按钮全宽堆叠

**CSS 参考：**
```css
.path-secondary-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

@media (max-width: 768px) {
  .path-secondary-actions {
    flex-direction: column;
  }
  .path-secondary-actions .ant-btn {
    width: 100%;
  }
}
```

---

### 1.4 [P1] 即时保存视觉反馈

**现状问题：** 每个字段 blur 后调用 API 保存，但没有任何 UI 反馈。用户不知道数据是否已保存成功，保存失败也只是 logger 记录。

**优化方案：** 采用全局保存状态指示器 + 字段级微反馈。

**全局状态指示器（方案 A，推荐）：**
- 在页面头部（面包屑与 card 之间）添加一个固定的状态提示条
- 三种状态：
  - **已保存**：显示一个绿色小对勾 + "已自动保存"，3 秒后淡出
  - **保存中**：显示 `a-spin` 小号 loading + "保存中..."
  - **保存失败**：显示红色警告 + "保存失败，请重试"，持续显示直到用户修改字段或手动关闭
- 使用 `a-alert` 组件，`banner` 模式，`closable`（仅在失败时可关闭）
- 位置：`.script-edit-header` 和 `.script-edit-content` 之间

**字段级微反馈（方案 B，可选叠加）：**
- 字段保存成功时，在输入框右侧显示一个小的 `CheckCircleFilled` 图标，1.5 秒后淡出
- 字段保存失败时，输入框边框变为红色，显示 `exclamation-circle` 图标

**实现要点（以方案 A 为主）：**
- 添加响应式状态 `saveStatus: 'idle' | 'saving' | 'saved' | 'error'`
- 每次字段变更时设置 `saveStatus = 'saving'`
- API 成功后设置 `saveStatus = 'saved'`，3 秒后回到 `'idle'`
- API 失败后设置 `saveStatus = 'error'`
- 使用 debounce 合并短时间内的多次保存（500ms 窗口）
- 全局指示器的 HTML：

```html
<div v-if="saveStatus !== 'idle'" class="save-status-bar">
  <a-alert
    v-if="saveStatus === 'saving'"
    type="info"
    :banner="true"
    message="保存中..."
    :closable="false"
    show-icon
  />
  <a-alert
    v-else-if="saveStatus === 'saved'"
    type="success"
    :banner="true"
    message="已自动保存"
    :closable="true"
    show-icon
    @close="saveStatus = 'idle'"
  />
  <a-alert
    v-else-if="saveStatus === 'error'"
    type="error"
    :banner="true"
    message="保存失败，请重试"
    :closable="true"
    show-icon
    @close="saveStatus = 'idle'"
  />
</div>
```

---

### 1.5 [P1] Agent 环境准备结果展示优化

**现状问题：** Agent 环境准备结果用 `a-alert` + 手写 `.agent-env-agent-line`（`<span>标签</span><code>值</code>`）展示，信息密度高但可读性差，代码路径用 `<code>` 标签显示但无法复制。

**优化方案：** 使用 `a-collapse` + `a-descriptions` 替代手写布局。

**具体要求：**
- 整体包裹在 `a-collapse` 中，默认展开
- 每个 agent 一个 `a-collapse-panel`，标题为 `agent.childExec` + `a-tag` 显示 `runtimeKind`
- panel 内容使用 `a-descriptions`（`size="small"`，`column="1"`），展示：
  - 解释器（`executable`）
  - 隔离 venv（`isolatedVenvPath`，如有）
  - 准备说明（`fallbackReason`，如有）
- 长路径（如 venv 路径）使用 `<code style="word-break: break-all">` 并附带一个复制按钮
- 日志区域用 `<pre>` 包裹，背景用 `var(--ant-color-fill-quaternary)`，添加一个"复制日志"按钮
- agent 列表为空时显示 `a-empty` 而非空白

**实现要点：**
- 替换现有的 `.agent-env-agent-item` 及其子元素
- 保留现有的 `agentEnvAlertType`、`agentEnvSummary`、`agentEnvDescription` 计算逻辑
- 新增 `copyToClipboard(text)` 工具函数（使用 `navigator.clipboard.writeText`）

---

### 1.6 [P1] 控制方式切换添加过渡

**现状问题：** ADB 和 Win32 两套配置通过 `v-if="isAdbController"` / `v-if="isDesktopController"` 直接替换，没有过渡效果，视觉上很突兀。

**优化方案：** 使用 Vue `<Transition>` 组件添加淡入淡出。

**实现要点：**
```html
<Transition name="control-fade" mode="out-in">
  <template v-if="isAdbController">
    <!-- ADB 配置区域 -->
  </template>
  <template v-else-if="isDesktopController">
    <!-- Win32 配置区域 -->
  </template>
</Transition>
```

```css
.control-fade-enter-active,
.control-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.control-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.control-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
```

- 确保 `mode="out-in"`，旧配置淡出后再淡入新配置

---

### 1.7 [P2] 区域视觉节奏优化

**现状问题：** 四个区域用相同的蓝色竖条 + 底部边框分隔，视觉上缺少节奏感。间距统一为 `margin-bottom: 24px`，区域之间缺少呼吸空间。

**优化方案：** 增大区域间距 + 交替微妙背景色。

**具体要求：**
- `.form-section` 的 `margin-bottom` 从 `24px` 改为 `40px`
- 奇数区域（基本信息、运行配置）保持白色背景
- 偶数区域（控制方式、项目更新）使用极浅灰背景 `var(--ant-color-fill-quaternary)`，加 `padding: 24px` + `border-radius: 8px`
- `.section-header h3::before` 竖条保留但颜色减轻：改为 `var(--ant-color-text-quaternary)` 或移除，让区域背景差异承担分隔职责

**CSS 变更：**
```css
.form-section {
  margin-bottom: 40px;
}

.form-section:nth-child(even) {
  padding: 24px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}
```

---

### 1.8 [P2] interface 摘要改为统计卡片

**现状问题：** interface 摘要用 `a-descriptions :column="4" bordered` 展示（项目、版本、控制器、资源、任务、预设、导入、Agent），看起来像数据表格，过于正式。

**优化方案：** 改用统计卡片网格（overview cards）。

**设计要求：**
- 8 个指标排列为 4 列 2 行网格（`display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px`）
- 每个卡片结构：
  ```
  ┌─────────────┐
  │  12         │  ← 大号数字，font-size: 24px，font-weight: 700
  │  任务       │  ← 小号标签，font-size: 13px，text-secondary 色
  └─────────────┘
  ```
- 卡片使用 `border: 1px solid var(--ant-color-border-secondary)` + `border-radius: 8px` + `padding: 16px`
- 768px 以下改为 2 列网格

**实现要点：**
- 替换现有的 `<a-descriptions>` 组件
- 数据数组：
```ts
const interfaceStats = computed(() => [
  { label: '任务', value: previewData.value?.tasks.length ?? 0 },
  { label: '预设', value: previewData.value?.presets.length ?? 0 },
  { label: '控制器', value: previewData.value?.controllers.length ?? 0 },
  { label: '资源', value: previewData.value?.resources.length ?? 0 },
  { label: '导入', value: previewData.value?.importCount ?? 0 },
  { label: 'Agent', value: previewData.value?.agentCount ?? 0 },
  { label: '版本', value: previewData.value?.project.version || '-' },
  { label: '项目', value: previewProjectTitle.value },
])
```

---

## 二、用户页 (`MaaFWUserEdit.vue`)

### 2.1 [P0] 添加任务菜单迁移到 `a-cascader`

**现状问题：** 当前的 `add-task-popup` 是完全自定义的三级弹出菜单，使用纯 `div` + click handler 实现。不支持键盘导航、没有动画、关闭逻辑靠 document click listener（`onMounted` / `onBeforeUnmount` 中注册/注销），存在可访问性和稳定性风险。

**优化方案：** 迁移到 Ant Design Vue 的 `a-cascader` 或 `a-cascader-panel`。

**数据结构映射：**
```
MaaFW interface 的任务分组结构：
  分组 (group)
    子分组 (sub-group, 可选)
      具体任务 (task)

映射到 a-cascader options：
  [
    {
      value: 'group1',
      label: '分组1',
      children: [
        {
          value: 'group1-sub1',
          label: '子分组1',
          children: [
            { value: 'task1', label: '任务1' },
            { value: 'task2', label: '任务2' },
          ]
        },
        // 或直接包含任务（无子分组时）:
        {
          value: 'task3',
          label: '任务3',
        }
      ]
    }
  ]
```

**实现要点：**
- 新增计算属性 `addTaskCascaderOptions`，将现有的 `addTaskMenuGroups` 逻辑转换为 cascader options 格式
- 使用 `a-cascader` 组件，配置：
  - `:options="addTaskCascaderOptions"`
  - `placeholder="添加任务"`
  - `change-on-select` 根据是否有子节点动态决定（无子节点的项直接触发添加）
  - `:change="handleCascaderChange"` — 选中叶子节点时调用 `addTaskToQueue`
  - `expand-trigger="hover"` — 鼠标悬停展开子菜单（减少点击次数）
- 删除以下自定义实现：
  - `addTaskMenuVisible` 状态
  - `toggleAddTaskMenu()` 方法
  - `handleAddTaskGroupClick()` / `handleAddTaskSecondClick()` 方法
  - `selectedAddTaskGroupKey` / `selectedAddTaskSecondKey` 状态
  - document click listener（`onMounted` / `onBeforeUnmount` 中注册/注销的部分）
  - `.add-task-popup` 及其所有子样式
- 替换为标准 `a-cascader` 按钮样式，保持 `type="primary"` + `PlusOutlined` 图标
- 按钮文字改为 "添加任务"（去掉 `({{ availableTasks.length }})` 数字，或保留作为 cascader 的 badge）
- 如果 `a-cascader` 的下拉面板宽度不够显示三级菜单，可通过 CSS 调整 `:deep(.ant-cascader-menus)` 的宽度

**兼容注意事项：**
- 保留现有的 `addTaskToQueue(taskName)` 方法不变，cascader 的 `change` 事件最终调用它
- 保留现有的 `availableTasks` 计算属性作为 cascader 数据源的基础

---

### 2.2 [P0] 拖拽排序与点击选中分离

**现状问题：** `draggable` 组件的拖拽区域覆盖整个 `.task-row`，与行的点击选中事件冲突。文档明确要求"拖拽必须有明确 handle，不能吞掉开关、select、option 按钮点击"。

**优化方案：** 在每行左侧添加明确的拖拽 handle。

**设计要求：**
- 在 `.task-row` 最左侧添加一个 `HolderOutlined`（六点拖拽图标）按钮
- handle 宽度 24px，高度 24px，颜色 `var(--ant-color-text-quaternary)`
- hover 时颜色加深为 `var(--ant-color-text-secondary)`
- handle 与任务图标/名称之间用 8px 间距
- handle 区域显示 `cursor: grab`，拖拽中显示 `cursor: grabbing`
- 行其余区域（图标 + 名称 + meta + 操作按钮）保持 `cursor: pointer`，点击触发选中

**实现要点：**
- 使用 `draggable` 的 `handle` prop：
```html
<draggable
  v-model="queuedTaskNames"
  :item-key="getTaskKey"
  :animation="200"
  handle=".task-drag-handle"
  ghost-class="task-row-ghost"
  chosen-class="task-row-chosen"
  drag-class="task-row-drag"
  class="task-queue-list"
  @end="handleTaskDragEnd"
>
  <template #item="{ element: taskName, index }">
    <div class="task-row" ...>
      <HolderOutlined class="task-drag-handle" />
      <!-- 现有的任务图标 + 名称 + meta + 操作按钮 -->
    </div>
  </template>
</draggable>
```

- 添加样式：
```css
.task-drag-handle {
  flex: 0 0 auto;
  color: var(--ant-color-text-quaternary);
  font-size: 16px;
  cursor: grab;
  padding: 4px;
  border-radius: 4px;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.task-drag-handle:hover {
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-tertiary);
}

.task-row-chosen .task-drag-handle {
  cursor: grabbing;
}
```
- 导入 `HolderOutlined` from `@ant-design/icons-vue`

---

### 2.3 [P1] 任务选项面板折叠/分组

**现状问题：** `MaaFWTaskOptionEditor` 将所有选项平铺渲染，无折叠功能。当选项超过 10 个时右侧面板很长，需要大量滚动。

**优化方案：** 在 `MaaFWTaskOptionEditor` 中添加分组折叠功能。

**分组规则：**
- 如果 interface 中 option 声明了分组信息（如 `group` 字段），按 group 聚合
- 如果没有显式分组，按 option 的首字母排序后每 5 个为一组（自动分组）
- 如果选项总数 <= 5，不启用折叠，直接平铺

**实现要点：**
- 新增计算属性 `optionGroups`，返回 `{ groupName: string, options: Option[] }[]`
- 使用 `a-collapse` 包裹分组：
```html
<a-collapse v-if="optionGroups.length > 1" :default-active-key="optionGroups.map(g => g.name)">
  <a-collapse-panel v-for="group in optionGroups" :key="group.name" :header="group.name">
    <div v-for="option in group.options" :key="option.name" class="option-item">
      <!-- 现有的选项渲染逻辑 -->
    </div>
  </a-collapse-panel>
</a-collapse>
```
- 分组标题使用 option 的分组名，如 "基本设置"、"高级选项"、"连接配置" 等
- 如果 option 无显式分组名，自动分组标题为 "选项 1-5"、"选项 6-10" 等（或直接按 scope 分组）
- `default-active-key` 默认全部展开，让用户可以折叠不需要查看的组

---

### 2.4 [P1] 任务选项搜索过滤

**现状问题：** 选项多时无搜索功能，用户只能滚动查找。

**优化方案：** 在任务选项面板顶部添加搜索框。

**实现要点：**
- 在 `.task-option-panel` 的 `.selected-task-header` 下方添加 `a-input-search`：
```html
<a-input-search
  v-if="visibleOptions.length > 5"
  v-model:value="optionSearchQuery"
  placeholder="搜索选项..."
  size="small"
  allow-clear
  class="option-search"
  style="margin-bottom: 16px"
/>
```
- 在 `visibleOptions` 计算属性中增加搜索过滤：
```ts
const filteredOptions = computed(() => {
  if (!optionSearchQuery.value) return visibleOptions.value
  const query = optionSearchQuery.value.toLowerCase()
  return visibleOptions.value.filter(opt =>
    getOptionLabel(opt).toLowerCase().includes(query) ||
    opt.name.toLowerCase().includes(query) ||
    opt.description?.toLowerCase().includes(query)
  )
})
```
- 搜索无结果时显示 `a-empty description="未找到匹配的选项"`
- 搜索框仅在选项数 > 5 时显示（避免选项少时视觉噪音）

---

### 2.5 [P1] 预设模板持久可访问

**现状问题：** 队列为空时显示预设模板卡片，一旦添加了任何任务就完全看不到预设。用户无法在已有队列基础上参考或重新应用预设。

**优化方案：** 在任务队列区域顶部保留预设入口。

**实现要点：**
- 无论队列是否为空，在"任务队列"标题行（`.column-header`）中添加一个"查看预设"按钮
- 按钮使用 `a-button type="link" size="small"`，文字为 "预设模板"
- 点击后弹出 `a-modal` 或 `a-drawer`，展示预设模板列表
- 模态框中展示与当前预设卡片相同的内容（预设名、描述、任务预览 chips）
- 模态框底部提供两个操作按钮：
  - "替换当前队列" — 清空当前队列，应用预设
  - "追加到队列" — 保留现有任务，将预设中的任务追加到队列末尾（自动去重）
- 当没有可用预设时（`presetTemplates.length === 0`），不显示"查看预设"按钮

**UI 变更：**
```html
<div class="column-header">
  <span>任务队列</span>
  <a-space>
    <a-button
      v-if="presetTemplates.length > 0 && orderedTasks.length > 0"
      type="link"
      size="small"
      @click="showPresetModal = true"
    >
      预设模板
    </a-button>
    <!-- 现有的添加任务按钮 -->
  </a-space>
</div>

<a-modal
  v-model:open="showPresetModal"
  title="预设模板"
  :footer="null"
  width="560px"
>
  <div class="preset-modal-list">
    <div v-for="template in presetTemplates" :key="template.preset.name" class="preset-card">
      <!-- 复用现有的预设卡片内容 -->
      <div class="preset-card-inner">
        <!-- preset-header, preset-tasks-preview -->
        <div class="preset-actions">
          <a-space>
            <a-button @click="applyPresetTemplate(template.preset.name); showPresetModal = false">
              替换当前队列
            </a-button>
            <a-button type="primary" @click="appendPresetTemplate(template.preset.name); showPresetModal = false">
              追加到队列
            </a-button>
          </a-space>
        </div>
      </div>
    </div>
  </div>
</a-modal>
```

- 新增 `appendPresetTemplate(presetName)` 方法：遍历预设的 `taskNames`，跳过已在 `queuedTaskNames` 中的任务，将其余追加到队列末尾
- 新增 `showPresetModal: ref(false)` 状态

---

### 2.6 [P1] 任务队列响应式断点优化

**现状问题：** 任务队列用 `a-col :span="12"` 固定左右对半分。768px 以下虽堆叠了，但中间态（900px-1100px 平板竖屏）每列约 400px，右侧选项面板很挤。

**优化方案：** 引入响应式断点，在 1200px 以下改为上下布局。

**实现要点：**
- 将任务队列区域的 `a-row` / `a-col` 替换为 CSS Grid 或 flexbox 响应式布局
- 使用 `a-row` 的 `:gutter` 配合 `a-col` 的响应式 `:xs` / `:sm` / `:md` / `:lg` / `:xl` 属性：

```html
<a-row :gutter="24" class="task-editor-layout">
  <a-col :xs="24" :sm="24" :md="24" :lg="12" :xl="12" class="task-list-column">
    <!-- 任务队列 -->
  </a-col>
  <a-col :xs="24" :sm="24" :md="24" :lg="12" :xl="12" class="task-option-column">
    <!-- 任务配置 -->
  </a-col>
</a-row>
```

- `:lg` 断点为 992px，`:xl` 为 1200px。上述配置表示：
  - >= 992px：左右分栏（12:12）
  - < 992px：上下堆叠（24:24）
- 上下布局时，任务配置面板使用 `position: sticky; top: 16px` 避免滚动时丢失
- 上下布局时，任务配置面板默认收起/折叠，点击任务行后展开（减少页面长度）

**CSS 调整：**
```css
/* 上下布局时，选项面板添加上边框分隔 */
@media (max-width: 991px) {
  .task-option-column {
    margin-top: 16px;
    padding-top: 16px;
    border-top: 1px solid var(--ant-color-border-secondary);
  }
}
```

---

### 2.7 [P2] 账号密码备注行紧凑化

**现状问题：** "账号"和"密码"字段各占 `span=12`，备注独占一行，三者占了整整两行空间。但紧接着一个 `a-alert` 说"仅用于本地记录"，说明这些字段优先级低，视觉权重却很高。

**优化方案：** 将账号、密码、备注压缩到同一行（各 `span=8`），`a-alert` 放在行下方。

**HTML 变更：**
```html
<a-row :gutter="24">
  <a-col :span="8">
    <a-form-item label="账号">
      <a-input v-model:value="formData.Info.Account" autocomplete="off"
        placeholder="仅用于本地记录…" size="large"
        @blur="handleFieldSave('Info.Account', formData.Info.Account)" />
    </a-form-item>
  </a-col>
  <a-col :span="8">
    <a-form-item label="密码">
      <a-input-password v-model:value="formData.Info.Password" autocomplete="off"
        placeholder="仅用于本地记录…" size="large"
        @blur="handleFieldSave('Info.Password', formData.Info.Password)" />
    </a-form-item>
  </a-col>
  <a-col :span="8">
    <a-form-item label="备注">
      <a-input v-model:value="formData.Info.Note"
        placeholder="备注信息…" size="large"
        @blur="handleFieldSave('Info.Note', formData.Info.Note)" />
    </a-form-item>
  </a-col>
</a-row>
<a-alert class="account-record-alert" type="info" show-icon
  :message="accountRecordTooltip" style="margin-bottom: 24px" />
```

**注意事项：**
- 768px 以下需要堆叠为纵向（`xs=24`），避免字段挤压
- 备注改为 `a-input`（单行），原 `a-textarea` 在三等分布局中不合适；如果用户需要长文本备注，可改为 `a-input` + `allow-clear` + tooltip 提示"回车输入更多内容"

---

### 2.8 [P2] 通知区域紧凑化

**现状问题：** 4 个开关各占 `span=6`，下面 2 个输入框各占 `span=12`，整个通知区域占地大但信息密度低。

**优化方案：** 改为卡片式 toggle list。

**设计要求：**
- 每个通知渠道一行，布局：左侧渠道名称，右侧开关
- 渠道名称下方显示简短描述（一行小字）
- 开关打开后，下方展开该渠道的配置字段（收件地址、密钥等），使用 `<Transition>` 动画
- 行与行之间用细线分隔

**UI 结构：**
```html
<div class="notify-channel-list">
  <div class="notify-channel-item">
    <div class="notify-channel-header">
      <div class="notify-channel-info">
        <span class="notify-channel-name">启用通知</span>
      </div>
      <a-switch v-model:checked="formData.Notify.Enabled"
        checked-children="启用" un-checked-children="关闭"
        @change="handleFieldSave('Notify.Enabled', formData.Notify.Enabled)" />
    </div>
  </div>

  <div class="notify-channel-item">
    <div class="notify-channel-header">
      <div class="notify-channel-info">
        <span class="notify-channel-name">邮件通知</span>
        <span class="notify-channel-desc">发送运行结果到邮箱</span>
      </div>
      <a-switch v-model:checked="formData.Notify.IfSendMail"
        @change="handleFieldSave('Notify.IfSendMail', formData.Notify.IfSendMail)" />
    </div>
    <Transition name="notify-expand">
      <div v-if="formData.Notify.IfSendMail" class="notify-channel-config">
        <a-form-item label="收件地址">
          <a-input v-model:value="formData.Notify.ToAddress"
            placeholder="邮件收件地址" size="large"
            @blur="handleFieldSave('Notify.ToAddress', formData.Notify.ToAddress)" />
        </a-form-item>
      </div>
    </Transition>
  </div>

  <!-- Server 酱同理 -->
</div>
```

**CSS 参考：**
```css
.notify-channel-item {
  padding: 12px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.notify-channel-item:last-child {
  border-bottom: none;
}

.notify-channel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.notify-channel-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.notify-channel-name {
  font-weight: 600;
  font-size: 14px;
}

.notify-channel-desc {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.notify-channel-config {
  padding-top: 12px;
  padding-left: 0;
}

.notify-expand-enter-active,
.notify-expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.notify-expand-enter-from,
.notify-expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
}
```

---

## 三、两页共性问题

### 3.1 [P1] 返回按钮添加未保存变更确认

**现状问题：** 两页的返回按钮直接 `router.back()`，没有未保存更改的确认。

**优化方案：** 维护 dirty 状态，返回时检查。

**实现要点：**
- 添加 `hasUnsavedChanges: ref(false)` 状态
- 每次字段变更时设置为 `true`，保存成功后设置为 `false`
- 返回按钮点击时检查：
```ts
const handleCancel = async () => {
  if (hasUnsavedChanges.value) {
    const confirmed = await new Promise<boolean>(resolve => {
      Modal.confirm({
        title: '有未保存的更改',
        content: '确定要离开吗？未保存的更改将丢失。',
        okText: '离开',
        cancelText: '继续编辑',
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
    if (!confirmed) return
  }
  router.back()
}
```
- 导入 `Modal` from `ant-design-vue`

---

### 3.2 [P1] 面包屑优化

**现状问题：** 面包屑第二级显示"编辑 MaaFramework 项目/用户"，文字较长。不提供快速导航到同级其他脚本/用户。

**优化方案：** 缩短面包屑文字。

- 脚本编辑页：`脚本管理 / 项目配置`（去掉"编辑 MaaFramework"前缀，card title 已经显示了类型信息）
- 用户编辑页：`脚本管理 / 用户配置`（同上）

**实现要点：**
- 仅修改 `a-breadcrumb-item` 的文字内容，不改变路由逻辑

---

### 3.3 [P2] 组件拆分加速落地

**现状问题：** `M9AUserEdit/` 目录下已有拆分好的子组件（`M9AUserEditHeader`、`BasicInfoSection`、`TaskQueueSection`、`TaskOptionRenderer`、`NotifyConfigSection`），但路由仍指向旧的 1912 行 `MaaFWUserEdit.vue`。

**优化方案：** 将拆分策略从 M9A 专用扩展为 MaaFW 通用。

**拆分目标：**
```
MaaFWUserEdit.vue（容器，约 200 行）
  +-- MaaFWUserEditHeader.vue
  +-- BasicInfoSection.vue（用户名称、启用、天数、预设、账号密码折叠）
  +-- TaskQueueSection.vue（任务队列、添加菜单、拖拽、预设模板）
  +-- ExtraScriptSection.vue（已独立）
  +-- NotifyConfigSection.vue（通知渠道列表）
```

**注意事项：**
- 拆分时保持即时保存逻辑不变，通过 `defineProps` + `defineEmits` 传递 formData 和 save 回调
- 先拆分 UI 结构，不改变业务逻辑
- `TaskQueueSection` 是最重的部分，优先拆出

---

## 四、优先级与实施顺序总结

| 序号 | 优先级 | 改动项 | 涉及文件 | 复杂度 |
|------|--------|--------|----------|--------|
| 2.1 | P0 | 添加任务菜单迁移 a-cascader | MaaFWUserEdit.vue | 中 |
| 2.2 | P0 | 拖拽 handle 分离 | MaaFWUserEdit.vue | 低 |
| 1.1 | P0 | 分步引导 | MaaFWScriptEdit.vue | 中 |
| 1.2 | P0 | interface 空状态增强 | MaaFWScriptEdit.vue | 低 |
| 1.3 | P0 | 项目目录按钮组布局 | MaaFWScriptEdit.vue | 低 |
| 1.4 | P1 | 即时保存反馈 | 两个页面 | 中 |
| 2.3 | P1 | 任务选项折叠分组 | MaaFWTaskOptionEditor.vue | 中 |
| 2.4 | P1 | 任务选项搜索 | MaaFWTaskOptionEditor.vue | 低 |
| 2.5 | P1 | 预设模板持久可访问 | MaaFWUserEdit.vue | 中 |
| 2.6 | P1 | 任务队列响应式断点 | MaaFWUserEdit.vue | 低 |
| 1.5 | P1 | Agent 环境结果展示 | MaaFWScriptEdit.vue | 中 |
| 1.6 | P1 | 控制方式切换过渡 | MaaFWScriptEdit.vue | 低 |
| 3.1 | P1 | 返回未保存确认 | 两个页面 | 低 |
| 3.2 | P1 | 面包屑优化 | 两个页面 | 低 |
| 2.7 | P2 | 账号密码折叠 | MaaFWUserEdit.vue | 低 |
| 2.8 | P2 | 通知区域紧凑化 | MaaFWUserEdit.vue | 中 |
| 1.7 | P2 | 区域视觉节奏 | MaaFWScriptEdit.vue | 低 |
| 1.8 | P2 | interface 摘要统计卡片 | MaaFWScriptEdit.vue | 低 |
| 3.3 | P2 | 组件拆分落地 | MaaFWUserEdit.vue | 高 |

**建议实施批次：**
- 第一批（P0 全部）：2.1 → 2.2 → 1.3 → 1.2 → 1.1
- 第二批（P1 全部）：2.6 → 2.4 → 1.6 → 3.2 → 3.1 → 1.4 → 2.3 → 2.5 → 1.5
- 第三批（P2 全部）：2.7 → 2.8 → 1.7 → 1.8 → 3.3

---

## 五、设计约束

1. 继续使用 Ant Design Vue 组件库，不引入新的 UI 框架
2. 颜色使用 CSS 变量（`var(--ant-color-*)`），兼容亮色和暗色主题
3. 不新增 MaaFW 专属颜色系统、按钮系统或营销式布局
4. 字体使用系统默认 sans-serif（与现有保持一致）
5. 响应式断点沿用 Ant Design 标准：xs=480, sm=576, md=768, lg=992, xl=1200, xxl=1600
6. 所有过渡动画时长控制在 150-300ms，使用 `ease` 缓动
7. 组件拆分后保持即时保存逻辑不变
8. 不修改 `frontend/src/api/**` 中 OpenAPI 生成文件
9. 不修改后端 API 接口

---

## 六、Web Interface Guidelines 审查补充项

> 依据 Vercel Web Interface Guidelines 审查发现的问题，按优先级补充到优化方案中。

### 6.1 [P0] 任务行 `<div @click>` 语义问题

**审查发现：** `MaaFWUserEdit.vue:349` — `<div class="task-row" @click="selectTask">` 使用非语义元素绑定点击，缺少键盘访问支持。

**合并到 2.2：** 在拖拽 handle 分离的改动中，同时将 `.task-row` 改为语义化元素：
```html
<button
  type="button"
  class="task-row"
  :class="{ 'task-row-selected': selectedTask?.name === taskName }"
  @click="selectTask(taskName)"
>
  <HolderOutlined class="task-drag-handle" />
  <!-- 任务内容 -->
  <a-space @click.stop>
    <!-- 上下移按钮 -->
  </a-space>
</button>
```
- `button` 元素自带 `tabindex="0"`、键盘 Enter/Space 触发
- `.task-row` 需重置 `button` 默认样式：`border: none; background: inherit; text-align: left; width: 100%; font: inherit; color: inherit; cursor: pointer; padding: 0;`
- `draggable` 内部使用 `button` 作为 item 根元素是 vuedraggable 推荐写法

### 6.2 [P0] 自定义弹出菜单 ARIA 与键盘导航缺失

**审查发现：** `MaaFWUserEdit.vue:210-271` — `add-task-popup` 缺少 `role="menu"`，菜单项缺少 `role="menuitem"`，无键盘导航。

**合并到 2.1：** 迁移到 `a-cascader` 后此问题自动解决。`a-cascader` 内置：
- 正确的 ARIA role（`listbox` / `option`）
- 键盘导航（方向键、Enter、Escape）
- 焦点管理

### 6.3 [P0] 返回导航未保存变更确认

**审查发现：** `MaaFWScriptEdit.vue:1644` — `handleCancel` 直接 `router.push`，无 `beforeunload` guard。

**合并到 3.1：** 补充 `beforeunload` 作为额外安全网：
```ts
onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
})
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
const handleBeforeUnload = (e: BeforeUnloadEvent) => {
  if (isSaving.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
```

### 6.4 [P1] `<img>` 缺少 `width`/`height`（7 处）

**审查发现：** 所有 MaaFW 页面中的 `<img>` 标签均未声明尺寸，存在 CLS（Cumulative Layout Shift）风险。

**涉及位置：**
- `MaaFWScriptEdit.vue:11` — 面包屑 logo
- `MaaFWScriptEdit.vue:783` — 底部提示 logo
- `MaaFWUserEdit.vue:29` — card title logo
- `MaaFWUserEdit.vue:353` — 任务图标
- `MaaFWUserEdit.vue:411` — 选中任务图标
- `MaaFWTaskOptionEditor.vue:12,77` — 选项/输入图标

**优化方案：** 为所有 `<img>` 添加明确的 `width` 和 `height` 属性：
```html
<!-- 面包屑 logo -->
<img :src="..." :alt="..." width="22" height="22" class="breadcrumb-logo" />
<!-- 任务图标 -->
<img :src="..." alt="" width="28" height="28" class="task-icon" />
<!-- 选项图标 -->
<img :src="..." alt="" width="18" height="18" class="option-icon" />
<!-- Card title logo -->
<img src="@/assets/AUTO-MAS.ico" alt="MaaFramework" width="22" height="22" class="title-logo" />
```
- 尺寸值取自现有 CSS 的 `width/height` 声明（`.breadcrumb-logo` 22x22、`.task-icon` 28x28、`.option-icon` 18x18）
- 动态图标（来自 interface 的任务/选项图标）尺寸不固定时，使用 `aspect-ratio: 1` 的占位容器包裹

### 6.5 [P1] 装饰性图标缺少 `aria-hidden="true"`（约 13 处）

**审查发现：** `QuestionCircleOutlined` 作为装饰性信息图标，会被屏幕阅读器读出，造成干扰。

**涉及文件：** `MaaFWScriptEdit.vue`（10+处）、`MaaFWUserEdit.vue`（3处）、`MaaFWTaskOptionEditor.vue`（1处）

**优化方案：** 全局替换，给所有 `QuestionCircleOutlined` 添加 `aria-hidden="true"`：
```html
<QuestionCircleOutlined class="help-icon" aria-hidden="true" />
```

### 6.6 [P1] 邮件/密码输入缺少正确的 `type` 和 `autocomplete`

**审查发现：**
- `MaaFWUserEdit.vue:514` — 邮件收件地址缺少 `type="email"` 和 `autocomplete="email"`
- `MaaFWUserEdit.vue:525` — Server 酱密钥缺少 `autocomplete="off"`
- `MaaFWUserEdit.vue:130` — 账号输入缺少 `autocomplete="off"`

**优化方案：**
```html
<!-- 邮件收件地址 -->
<a-input
  v-model:value="formData.Notify.ToAddress"
  type="email"
  inputmode="email"
  autocomplete="email"
  placeholder="邮件收件地址…"
  size="large"
  :disabled="!formData.Notify.IfSendMail"
  @blur="handleFieldSave('Notify.ToAddress', formData.Notify.ToAddress)"
/>

<!-- Server 酱密钥 -->
<a-input-password
  v-model:value="formData.Notify.ServerChanKey"
  autocomplete="off"
  placeholder="Server 酱 SendKey…"
  size="large"
  :disabled="!formData.Notify.IfServerChan"
  @blur="handleFieldSave('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
/>

<!-- 账号 -->
<a-input
  v-model:value="formData.Info.Account"
  autocomplete="off"
  placeholder="仅用于本地记录…"
  size="large"
  @blur="handleFieldSave('Info.Account', formData.Info.Account)"
/>
```

### 6.7 [P1] 自建 HTML sanitizer 建议迁移到 DOMPurify

**审查发现：** `MaaFWDescriptionView.vue:85-131` — 自建 sanitizer 功能正常，但不处理 `style` 属性注入和 CSS-based XSS。

**优化方案：** 长期考虑将 `sanitizeHtml()` 替换为 DOMPurify。短期内，在自建 sanitizer 中增加 `style` 属性剥离：
```ts
// 在 walk 函数的属性清理逻辑中添加
if (attrName === 'style') {
  child.removeAttribute(attr.name)
  continue
}
```

### 6.8 [P2] placeholder/loading 文本省略号格式

**审查发现：** 5 处 placeholder 使用 `...`（三个句点），2 处 loading 使用 `...`，应使用 `…`（U+2026 HORIZONTAL ELLIPSIS）。

**涉及位置（代表性）：**
- `MaaFWScriptEdit.vue:149,161` — loading text
- `MaaFWUserEdit.vue:192` — loading text
- `MaaFWScriptEdit.vue:58,80` — placeholder
- `MaaFWUserEdit.vue:59,133,150` — placeholder

**优化方案：** 全局搜索替换 `...` 为 `…`（仅在 placeholder 和 loading 文本中，不在代码逻辑中）。

### 6.9 [P2] 错误消息缺少修复建议

**审查发现：** `MaaFWTaskOptionEditor.vue:130` — `"不支持的配置项类型：${option.type}"` 只描述问题，没有告诉用户如何解决。

**优化方案：**
```ts
:message="`不支持的配置项类型：${option.type}，请联系脚本作者或升级 AUTO-MAS`"
```

### 6.10 [P2] readonly 输入缺少 `aria-readonly`

**审查发现：** `MaaFWScriptEdit.vue:79` — 项目目录输入框使用 `readonly`，但屏幕阅读器无法感知此状态。

**优化方案：** 添加 `aria-readonly="true"`：
```html
<a-input
  v-model:value="formData.path"
  placeholder="请选择 MaaFramework 项目目录…"
  size="large"
  class="path-input"
  readonly
  aria-readonly="true"
/>
```

---

## 七、更新后的优先级与实施顺序总结

| 序号 | 优先级 | 改动项 | 来源 |
|------|--------|--------|------|
| 2.1 | P0 | 添加任务菜单迁移 a-cascader | UX优化 + 6.2 |
| 2.2 | P0 | 拖拽 handle 分离 + 任务行语义化 | UX优化 + 6.1 |
| 1.1 | P0 | 分步引导 | UX优化 |
| 1.2 | P0 | interface 空状态增强 | UX优化 |
| 1.3 | P0 | 项目目录按钮组布局 | UX优化 |
| 6.3 | P0 | 返回未保存确认 + beforeunload | 审查补充 |
| 6.5 | P1 | 装饰性图标 aria-hidden | 审查补充 |
| 6.4 | P1 | img 缺少 width/height | 审查补充 |
| 6.6 | P1 | 邮件/密码输入 type/autocomplete | 审查补充 |
| 1.4 | P1 | 即时保存反馈 | UX优化 |
| 2.3 | P1 | 任务选项折叠分组 | UX优化 |
| 2.4 | P1 | 任务选项搜索 | UX优化 |
| 2.5 | P1 | 预设模板持久可访问 | UX优化 |
| 2.6 | P1 | 任务队列响应式断点 | UX优化 |
| 1.5 | P1 | Agent 环境结果展示 | UX优化 |
| 1.6 | P1 | 控制方式切换过渡 | UX优化 |
| 3.1 | P1 | 返回未保存确认 (Modal) | UX优化 |
| 3.2 | P1 | 面包屑优化 | UX优化 |
| 6.7 | P1 | sanitizer 增强 | 审查补充 |
| 6.8 | P2 | placeholder/loading 省略号格式 | 审查补充 |
| 6.9 | P2 | 错误消息修复建议 | 审查补充 |
| 6.10 | P2 | readonly 输入 aria-readonly | 审查补充 |
| 2.7 | P2 | 账号密码备注行紧凑化 | UX优化 |
| 2.8 | P2 | 通知区域紧凑化 | UX优化 |
| 1.7 | P2 | 区域视觉节奏 | UX优化 |
| 1.8 | P2 | interface 摘要统计卡片 | UX优化 |
| 3.3 | P2 | 组件拆分落地 | UX优化 |

**建议实施批次（更新版）：**
- 第一批（P0 全部）：6.5 → 6.8 → 2.2(含6.1) → 2.1(含6.2) → 1.3 → 1.2 → 1.1 → 6.3
- 第二批（P1 全部）：6.4 → 6.6 → 2.6 → 2.4 → 1.6 → 3.2 → 1.4 → 2.3 → 2.5 → 1.5 → 3.1 → 6.7
- 第三批（P2 全部）：6.9 → 6.10 → 2.7 → 2.8 → 1.7 → 1.8 → 3.3

**说明：** 6.5（aria-hidden）和 6.8（省略号）改动极小且零风险，可随第一批顺手修复。
