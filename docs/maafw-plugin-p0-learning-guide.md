# MaaFW 插件化 P0 产物学习指南

> 状态：学习文档
> 日期：2026-07-06
> 目的：帮助审核者理解本次 P0 产物的设计思路、原理和阅读顺序
> 适用：初次接触 MaaFW 插件化的开发者

本文档是本次 P0 产物的配套学习材料。它不重复审计文档的事实细节，而是讲解"为什么这么设计"、"原理是什么"、"怎么读这些文档"。如果你只想看事实，请直接读 docs/maafw-plugin-code-audit.md；如果你想理解设计决策的来龙去脉，请先读本文档。

## 1. 本次产物总览

### 1.1 产出了什么

本次 P0 产出 4 个文档（全部为新增，未修改任何运行代码）：

| 文档 | 一句话定位 | 阅读优先级 |
| --- | --- | --- |
| `docs/maafw-plugin-code-audit.md` | 现有代码的"体检报告" | 第 1 读 |
| `docs/maafw-plugin-p0-contract.md` | 新插件包的"接口合同" | 第 2 读 |
| `docs/maafw-plugin-p1-checklist.md` | 下一步的"施工单" | 第 3 读 |
| `docs/maafw-plugin-compatibility-gate.md` | 切换前的"安检流程" | 第 4 读 |

加上本学习文档，共 5 个文件。

### 1.2 没改什么

- 没有修改 `app/task/MaaFW/**` 任何文件
- 没有修改 `app/task/M9A/**` 任何文件
- 没有修改 `app/plugins/**` 任何文件
- 没有修改 `app/models/**` 任何文件
- 没有修改 `frontend/src/api/**`（OpenAPI 生成文件）
- 没有修改任何前端组件
- 没有执行 git add / commit / push
- 没有安装依赖、没有联网、没有访问外部目录

`git status` 确认：只有 5 个 untracked 新文档，无已跟踪文件修改。

### 1.3 为什么只写文档不写代码

P0 阶段的目标是"冻结最小 v1 服务面，不移动代码"（方案文档第 13 节 P0 定义）。这有两层原因：

**第一层：风险控制**。MaaFW 和 M9A 是当前正在使用的脚本类型，直接搬代码会导致运行中断。P0 先把"要搬什么、搬到哪里、怎么验证没搬错"想清楚，再用 P1-P7 逐步执行。

**第二层：契约优先**。MaaEnd 等外部消费者只依赖 interface 包。如果 interface 包的 DTO 还没冻结就开始写代码，后面 DTO 变动会导致消费者被迫跟进。P0 先冻结 DTO，让消费者能基于稳定契约规划自己的开发。

## 2. 架构原理：MaaFW 现有代码是怎么组织的

### 2.1 三进程模型

理解 MaaFW 插件化的关键，是先理解现有的三进程模型：

```
AUTO-MAS 主进程（FastAPI + Vue 前端）
  -> runner_worker.py 子进程   # 只在这里 import maa
      -> MaaFW Tasker（pipeline 执行引擎）
  -> agent 子进程              # 仅在项目声明 agent 时启动
```

**为什么要三进程？**

MaaFW 的 `maa` 包是一个 C++ 绑定的 Python 包，它会在 import 时加载原生 DLL。如果主进程直接 import maa，会导致：
1. DLL 冲突（主进程的其他依赖可能和不兼容）
2. 内存泄漏（maa 的 Tasker 对象不释放会拖垮主进程）
3. 崩溃传染（maa 崩溃会带崩整个 AUTO-MAS）

所以 AUTO-MAS 把 maa 隔离在 runner_worker.py 子进程里，通过 JSON 行协议（stdout 每行一个 JSON）和主进程通信。这就像浏览器用多进程隔离标签页一样——一个标签页崩溃不影响其他标签页。

**插件化后这个模型变不变？**

不变。方案文档第 2 节红线第 1 条明确："MaaFW 的 maa binding 不能回到 AUTO-MAS 主进程内加载。继续保留三进程模型。"插件化只是把代码从 `app/task/MaaFW/` 搬到独立包，进程边界保留。

### 2.2 文件分层

`app/task/MaaFW/` 的 14 个文件按依赖方向自然分成 5 层：

```
第 5 层（编排层）：manager.py + AutoProxy.py
    ↑ 依赖 app.core / app.models / app.services
第 4 层（运行层）：runner.py + runner_worker.py + control_capabilities.py + window_service.py
    ↑ 依赖 maa
第 3 层（计划层）：run_plan.py + pipeline_override.py
    ↑ 依赖第 1 层模型
第 2 层（归一化层）：task_config.py
    ↑ 依赖第 1 层模型
第 1 层（模型层）：interface_models.py + interface_loader.py + interface_preview.py
    ↑ 零外部依赖（仅 pydantic + json5 + app.utils 日志）
```

**这个分层是插件化拆包的天然边界**：
- 第 1 层 → `automas-maafw-interface` 包（P1 先抽出）
- 第 3 层的 agent plan 部分 + project_updater → `automas-maafw-project` 包（P2 抽出）
- 第 3 层的 run plan 部分 + 第 4 层 → `automas-maafw-runner` 包（P3 抽出）
- 第 5 层 → `automas-script-maafw` 编排插件（P4 改写）

**为什么从底层开始拆？**因为底层依赖最少，拆出来后上层可以继续用旧实现运行。如果从上层开始拆，上层依赖的所有底层都得一起搬，等于一次性重写。

### 2.3 maa 依赖的集中性

审计发现一个关键事实：14 个文件中只有 4 个依赖 maa（runner.py、control_capabilities.py、window_service.py、AutoProxy.py）。其余 10 个文件零 maa 依赖。

**这意味着什么？**interface 包（第 1 层 + 第 2 层）可以做到"安装不拉 maa wheel"。这对 MaaEnd 等只消费解析器的场景至关重要——用户不需要安装几百 MB 的 maa 包就能解析 interface.json。

`__init__.py` 通过 `__getattr__` 懒加载实现这一点：只有真正访问 `MaaFWRunner` 等符号时才会触发 `import maa`，访问 `MaaFWInterface` 等纯模型符号时不会触发。这是 Python 的"延迟导入"模式，类似 Java 的类加载机制。

## 3. 契约设计原理：v1 DTO 为什么这么设计

### 3.1 extra="allow" 透传策略

所有 v1 DTO 都用 `model_config = ConfigDict(extra="allow")`。这是为了应对 PI V2（ProjectInterface 规范）继续漂移。

**什么是 PI V2 漂移？**MaaFW 的 interface.json 规范（PI V2）不是稳定的，MaaFW 团队会持续新增字段。如果我们的 DTO 用 `extra="forbid"`，每新增一个字段解析器就会报错；如果用 `extra="ignore"`，新字段会被静默丢弃，导致信息丢失。

`extra="allow"` 让未知字段透传到 `model_extra` 里，既不报错也不丢信息。这就像 HTTP 头的 `X-` 前缀——自定义头不被标准禁止，透传即可。

### 3.2 raw 字段保留策略

每个 DTO 都有 `raw: dict` 字段，保留原始 JSON 片段。

**为什么需要 raw？**因为显式建模不可能覆盖所有字段。如果某个项目在 option case 里放了一个自定义的 `magic_param` 字段，我们的 `OptionCase` 没有建模它，`extra="allow"` 会把它放到 `model_extra` 里，但消费者想访问时需要知道字段名。`raw` 让消费者能直接 `raw["magic_param"]` 访问，不用关心 Pydantic 的 extra 机制。

**这不是重复存储吗？**是的，`raw` 和 `model_extra` 有重叠。但 `raw` 是契约的一部分（消费者可以依赖），`model_extra` 是 Pydantic 的实现细节（消费者不应该依赖）。如果未来换掉 Pydantic，`raw` 仍然有效。

### 3.3 scope 字段：作用域放在引用和选择上，不放在原始定义上

现有代码中，option 的作用域（task / global / controller / resource）是通过引用位置隐式确定的：
- `task.option` 引用的 option → task scope
- `global_option` 引用的 option → global scope
- `controller.option` 引用的 option → controller scope

**v1 为什么不把 scope 直接放在 OptionDefinition 上？**因为一个 option 可能被多个位置引用——同一个 option 完全可能同时出现在 `task.option` 和 `global_option` 里。如果在 `OptionDefinition` 上绑定单一 scope，就会丢失"一个定义、多处引用"的事实，消费者也无法判断这个 option 到底属于哪个层。

**v1 的设计**：作用域的权威载体是 `OptionReference`（解析器输出，描述"谁在哪个 scope 引用了这个 option"）和 `OptionSelection`（用户选择结果，标注这次选择属于哪个作用域）。`OptionDefinition` 上不绑定单一 scope，只输出 `scopes: list[str] | None` 供聚合展示（如"这个 option 出现在哪些作用域"）。

**为什么不直接把所有 scope 都列出来？**因为 `setting` / `pretask` / `hotkey` 三个预留 scope 当前 PI V2 规范中没有显式来源（没有任何字段表明某个 option 是 setting 类或 hotkey 类）。v1 不解析、不输出这三个 scope，避免做出超出当前规范的设计结论。它们留作 v2 待确认——如果未来 PI V2 规范新增了 setting/pretask/hotkey 的显式来源，再开 v2 服务名输出。

**降低消费门槛**：显式 scope 让消费者能直接 `ref.scope == "task"` 判断，不用解析整个 interface.json 推断。MaaEnd 这样的外部消费者只想知道"这个 option 是全局的还是任务级的"，不需要理解整个 interface 结构。

### 3.4 OptionSelection：结构化 option 选择结果

这是 v1 最重要的新增设计。

**旧格式的问题**：旧 option 值类型是 `str | list[str] | dict[str, str]`，一个 select 选中的 case 只存 case name（string）。但 PI V2 规范允许 case 携带 `args` 参数，这些参数对 runner/agent 很重要。旧格式把 args 丢了，或者需要 runner 再去 interface 里查 case 定义才能拿到 args。

**新格式的设计**：`OptionSelection` 包含 `value`（用户选择的原始值）、`args`（从 case.args 提取的参数）、`raw`（原始记录）。runner 或 agent adapter 直接用 `args` 就能拿到参数，不用再查 interface。

**兼容策略**：新格式不替换旧格式，而是并存。旧消费者继续读 `str | list[str] | dict[str, str]` 格式；新消费者读 `OptionSelection` 结构化格式。这就像 HTTP/1.1 和 HTTP/2 共存——旧客户端继续用 1.1，新客户端用 2，两者都能工作。

### 3.5 normalize_execution_payload：不压成字符串

方案文档第 4.1 节明确要求："normalize_execution_payload() 输出结构化 option 结果，由 runner 或 agent adapter 决定怎么注入给 agent；不要只传 task name，也不要把所有 option 提前压成一段不可逆字符串。"

**为什么不能压成字符串？**因为不同 agent 可能需要不同的参数格式。有的 agent 接受 JSON，有的接受命令行参数，有的接受环境变量。如果解析器提前把 option 压成 `"--option1=value1 --option2=value2"` 这样的字符串，runner 就失去了灵活注入的能力。

结构化 `ExecutionPayload` 让 runner 能根据 agent 的 runtime_kind 决定怎么注入：
- `project_python` → 转成 Python 字典
- `project_binary` → 转成命令行参数
- `isolated_venv` → 转成环境变量 + JSON 配置文件

### 3.6 import 合并：先合并后校验

这是 interface 包最核心的算法，也是最容易出错的地方。

**为什么要"先合并后校验"？**因为 import 片段允许只提供局部内容。一个片段可能只有 options 没有 tasks，如果在校验阶段要求"每个片段必须有 task"，就会误判合法的片段。

正确顺序是：
1. 递归 DFS 合并所有片段（深度优先：先递归子 import，再合并当前片段）
2. 合并完成后，对最终结果做校验

这就像编译器的"先解析后类型检查"——先建 AST 再检查类型，而不是边解析边检查。

**硬冲突策略**：task.name / option key / preset.name 重名即 raise，不覆盖。这是为了防止两个片段意外定义同名 task 导致其中一个被静默吞掉。虽然这可能导致合并失败，但失败比静默丢数据更安全。

### 3.7 缓存签名：为什么要把 scan 目录纳入签名

interface_loader 的缓存签名不只是 interface.json 的 mtime，还包括所有 import 依赖文件和 scan_select 扫描目录下所有匹配文件的 mtime。

**为什么？**因为 scan_select 会在加载期扫描 `scan_dir` 目录，把匹配 `scan_filter` 的文件名作为 cases 填入 option。如果 scan_dir 下新增了文件，option 的 cases 就变了。如果缓存签名不包含 scan 目录文件，新增文件后缓存不会失效，用户看到的 option cases 是过期的。

这就是为什么 `_build_signature` 要把 `scan_select_specs`（所有 scan 目录下的文件 mtime）纳入签名。代价是签名计算变慢（要 stat 很多文件），但正确性比性能重要。

## 4. 兼容性设计原理：为什么用"只增不删"策略

### 4.1 只增不删的核心原则

v1 契约的所有新增字段（`OptionDefinition.scopes` / `OptionReference` / `OptionSelection.scope` / `value` / `args` / `raw`）都是"只增不删"的：
- 旧消费者读不到新字段 → 无影响（Pydantic 忽略未知字段）
- 新消费者读新字段 → 获得增强信息
- 旧格式继续可生成 → 旧消费者不受影响

**这就像 API 版本控制**：给 JSON 响应加字段是向后兼容的（旧客户端忽略新字段），删字段才是破坏性的。v1 契约遵循同样的原则。

### 4.2 双格式并存

option 值同时支持旧格式（`str | list[str] | dict[str, str]`）和新格式（`OptionSelection`）。

**为什么不直接换新格式？**因为前端、后端、配置文件里到处都有旧格式的读写代码。一次性换格式需要同步改所有地方，风险太高。双格式让迁移可以渐进进行：
- P1：新 interface 包输出双格式
- P4：前端组件开始消费新格式
- P6：评估是否移除旧格式

### 4.3 facade 默认不启用，且不新增旧配置项

P1 会新增一个只读 facade，作为旧路径旁路可用的显式测试 / 对照入口，让人工确认时可以调用新 service。它不会把现有 MaaFW 运行代码默认接入新 service；facade 默认不启用，且**不通过修改 `MaaFWConfig` / `M9AConfig` 旧配置项实现启用**（不引入 `UsePluginInterface` 之类的字段）。

**为什么不默认启用？**因为"能调用"不等于"调用结果一致"。即使 old/new 对照通过，也可能有边缘 case 不一致。默认不启用让迁移保持可控：
- 普通用户：继续用旧实现（facade 关闭）
- 开发 / 测试人员：通过非配置项的方式显式启用 facade（如环境变量 / feature flag / 测试入口），对照新解析器输出

**为什么不通过旧配置项启用？**因为 P1 的红线是"不新增旧配置项、不切换默认运行路径"。如果引入 `MaaFWConfig.UsePluginInterface` 之类的字段，就会污染旧配置结构，而且这个字段一旦发布就难回退。启用方式由人工确认（环境变量 / feature flag / 测试入口），不应导致 `MaaFWConfig` / `M9AConfig` 结构变更。

这就像浏览器的"实验性功能"开关——默认关闭，用户主动开启表示愿意承担风险；而且开关不会污染正常的浏览器配置文件。

### 4.4 迁移只创建不覆盖

旧 MaaFWConfig / M9AConfig 迁移到新 PluginScriptConfig 时，迁移工具只创建新配置，不覆盖旧值。

**为什么不覆盖？**因为迁移可能出错。如果迁移工具把旧值覆盖了，用户就失去了回退的能力。只创建新配置意味着：
- 迁移成功 → 用户用新配置
- 迁移失败 → 用户继续用旧配置（旧值还在）
- 用户后悔 → 可以删掉新配置，回到旧配置

这就像数据库迁移的"蓝绿部署"——新版本和旧版本并存，确认新版本正常后再切换，出问题就回退。

## 5. 审计发现的关键事实解读

### 5.1 M9A 和 MaaFW 完全独立（现状审计，非最终设计结论）

审计最重要的发现：M9A 和 MaaFW 是完全独立的两条实现线，不存在 runner 逻辑复制。

**M9A 的运行方式（现状）**：启动 `M9A.exe` 进程 → 监控日志文件 → 等待完成事件。这是"外部程序驱动"模式。

**MaaFW 的运行方式（现状）**：Python agent + pipeline → runner 子进程 → MaaFW Tasker。这是"内嵌引擎驱动"模式。

**为什么这个发现很重要？**因为方案文档说"M9A 不再复制 MaaFW 运行逻辑"。审计确认 M9A 本来就没有复制 MaaFW 运行逻辑。

**但要注意区分现状和目标**：M9A 当前通过 `M9A.exe` 运行是审计事实，不能直接推出"M9A 最终作为 MaaFW project pack runtime"的设计结论。P1 不迁移 M9A runtime；M9A 后续是否迁入 MaaFW project pack / 共享 runner，必须另走兼容验收门（见 docs/maafw-plugin-compatibility-gate.md）。M9A 是否最终复用 MaaFWTaskBuilder、是否走 project pack SDK，这些都是 P4/P5 才决策的议题，不在 P0/P1 范围。

### 5.2 前端三套编辑器

审计发现前端有三套并存的编辑器实现：MaaFW（自包含 1907 行）、M9A（拆分子组件）、Plugin（基于 SchemaForm）。

**为什么不直接用 SchemaForm？**因为 SchemaForm 是为"平铺字段表单"设计的，不支持：
1. 可拖拽排序的任务队列
2. 递归嵌套的选项编辑器（option 的 case 可以有子 option）
3. controller/resource 联动过滤
4. preset 一键应用

这些是 MaaFW 任务构建的核心交互，SchemaForm 的抽象层次不够。

**插件化的解法**：新建共享组件层（MaaFWTaskBuilder / MaaFWTaskQueueEditor / MaaFWTaskOptionEditor / MaaFWDescriptionView），随 `automas-script-maafw` 分发。M9A pack 不复制这些组件，只注入模板和文案。这就像 React 组件库——基础组件由库提供，业务方只传 props。

### 5.3 M9A 有独立的 import 合并逻辑

M9A 的 `task_loader.py` 有自己独立的 import 合并和缓存逻辑，与 MaaFW 的 `interface_loader.py` 存在逻辑重叠但数据结构不同。

**为什么 M9A 要独立实现？**因为 M9A 有双路径加载：优先读 interface.json（支持 import 递归、scan_select），回退读 `resource/tasks/*.json`。MaaFW 的 interface_loader 只支持 interface.json 路径。

**插件化怎么处理？**P5 评估是否统一到 interface 包。本文档建议保持独立，因为 M9A 的双路径加载是 M9A 特有的回退机制，强行统一会引入不必要的复杂性。

### 5.4 版本号不一致

`res/version.json`（v5.4.0-beta.1）和 `pyproject.toml`（5.2.0）不同步。

**为什么？**因为 `check-version-json.yml` 只强制 PR 改动 `res/version.json`，不校验 `pyproject.toml` 同步。`build-app.yml` 只读 `res/version.json` 作为版本真相源。

**对插件化的影响**：MaaFW 插件包需要声明 `min_auto_mas_version`，应以 `res/version.json` 为准。如果用 `pyproject.toml` 的版本号，会低估实际版本。

### 5.5 TaskExecuteBase 只抽象 3 个方法

`TaskExecuteBase` 基类只抽象 `main_task` / `final_task` / `on_crash`，`check` / `prepare` 是子类约定钩子。

**这意味着什么？**`check` / `prepare` 没有统一的签名约束，各 Manager 子类可以自由定义参数。这给 ScriptAdapterHooks 的设计带来了挑战——`ScriptAdapterHooks.check` 的签名是 `(runtime) -> str`，但各 Manager 的 `check` 签名不一致。

**插件化的处理**：编排插件（`automas-script-maafw`）的 `ScriptAdapterHooks` 实现需要适配各 Manager 的 check/prepare 签名，把差异封装在适配层里，不让基础包感知。

## 6. 文档阅读指南

### 6.1 docs/maafw-plugin-code-audit.md（代码审计）

**怎么读**：从第 1 节"审计总览"开始，先看"关键架构事实"（第 1.3 节），这 7 条是理解全局的钥匙。然后按需查阅第 2-6 节的文件审计细节。

**重点章节**：
- 第 2.1 节"文件迁移映射总表"——一眼看清 14 个文件的归属和风险
- 第 2.6 节"P0 契约冻结关键点"——哪些是必须冻结的
- 第 2.7-2.9 节"DTO 字段 / import 合并算法 / option 归一化规则"——契约的技术细节
- 第 7 节"模块边界观察"——为什么这么分层

**不用记的**：具体行数和函数签名（这些在代码里查即可），重点是理解"哪些文件能独立迁移、哪些有耦合点"。

### 6.2 docs/maafw-plugin-p0-contract.md（v1 契约）

**怎么读**：从第 1 节"契约总览"开始，先看 7 个服务的职责和冻结严格度。然后重点读第 2 节"maafw.interface.v1"（这是最详细的）。第 3-8 节按需查阅。

**重点章节**：
- 第 2.3 节"import 合并契约"——核心算法
- 第 2.5 节"option 作用域"——作用域承载位置的设计理由（OptionDefinition 不绑定单一 scope）
- 第 2.6 节"核心 DTO"——OptionDefinition / OptionReference / OptionCase / OptionSelection 的字段和冻结理由
- 第 2.10 节"value / args / raw 保留策略"——只增不删原则
- 第 10 节"待人工确认事项"——需要你决策的 6 个问题

**和审计文档的关系**：契约文档第 2.13 节"与现有代码的映射"表把 v1 DTO 和现有代码的类一一对应，审计文档提供了这些类的完整字段。两份文档交叉阅读效果最好。

### 6.3 docs/maafw-plugin-p1-checklist.md（任务清单）

**怎么读**：从第 1 节"P0 任务清单"开始，确认 P0 哪些已完成、哪些待人工确认。然后读第 2 节"P1 任务清单"，按 P1-1 到 P1-7 的顺序理解下一步施工计划。第 3 节"前端共享组件方案"是 P4 才实现的，现在只需理解设计思路。

**重点章节**：
- 第 2.1 节"P1-1 创建 interface 包脚手架"——下一步第一个任务
- 第 3 节"前端共享组件方案"——MaaFWTaskBuilder 等组件的 props/emits 设计
- 第 5 节"开工护栏检查清单"——每个任务开工前的必检项
- 第 6 节"待人工确认事项"——需要你决策的 6 个问题

### 6.4 docs/maafw-plugin-compatibility-gate.md（兼容验收门）

**怎么读**：从第 1 节"验收门总览"开始，看 6 个对照对象的验收要求。然后按需查阅第 2-7 节的对照表细节。第 8 节"验收流程"和第 9 节"已知风险"是理解切换条件的关键。

**重点章节**：
- 第 2.2 节"interface 解析结果对照表"——最详细的字段级对照
- 第 8 节"验收流程"——阶段门和切换条件
- 第 10 节"待人工确认事项"——需要你决策的 5 个问题

**和契约文档的关系**：兼容验收门的"已知差异（允许）"部分和契约文档的"与现有代码的映射"表呼应——契约文档说"新增了什么字段"，验收门说"新增字段不影响旧消费者"。

## 7. 设计决策的原理总结

### 7.1 为什么从底层开始拆包

interface 包（第 1 层）零外部依赖，拆出来后：
- MaaEnd 等外部消费者可以独立安装
- 旧 MaaFW 代码继续用旧实现运行（facade 默认不启用）
- 新 interface 包可以独立测试

如果从上层（编排层）开始拆，上层依赖的所有底层都得一起搬，等于一次性重写 14 个文件，风险极高。

### 7.2 为什么 interface 包冻结最严

因为 interface 包是"公共契约"。MaaEnd、MaaFW runner、M9A pack、前端组件层都依赖它。如果 interface 包的 DTO 频繁变动，所有消费者都被迫跟进。

其他包（project / runner）的消费者较少（主要是 script-maafw 编排插件），变动影响面小。所以 interface 包冻结最严，其他包可以稍微宽松。

### 7.3 为什么用 Pydantic 而不是 dataclass

Pydantic 提供：
1. `extra="allow"` 透传未知字段（dataclass 不支持）
2. `model_validator` 自动校验（dataclass 需要手动写）
3. JSON 序列化/反序列化（dataclass 需要 dataclasses-json 等额外库）
4. 类型提示和 IDE 自动补全（和 dataclass 一样）

MaaFW 的 interface.json 是嵌套 JSON，Pydantic 的嵌套模型天然适合。dataclass 更适合简单的数据容器。

### 7.4 为什么用 JSON 行协议而不是 gRPC / WebSocket

JSON 行协议（stdout 每行一个 JSON）的优点：
1. 零依赖（不需要 gRPC / WebSocket 库）
2. 可调试（直接看 stdout 就能理解通信）
3. 跨语言（任何能读写 stdio 的语言都能用）
4. 进程隔离（子进程崩溃不会带崩主进程的通信层）

缺点是性能不如二进制协议，但 MaaFW 的通信量不大（主要是日志和结果），JSON 行足够了。

### 7.5 为什么 controller 按插件族拆分

ADB 和 Win32 控制器的差异很大：
- ADB 需要 adbPath、address、模拟器能力
- Win32 需要 hWnd、窗口扫描、句柄匹配

如果把它们放在一起，用户只装了 ADB 但代码里还有 Win32 的依赖，导致包体积增大。按插件族拆分让用户只装需要的控制器：
- 只用 ADB → 装 `automas-maafw-controller-adb`
- 只用桌面 → 装 `automas-maafw-controller-desktop`
- 都用 → 两个都装

这就像 Linux 内核的模块化驱动——按需加载，不装就不占空间。

### 7.6 M9A 的 project pack 路径是设计目标，不是 P1 范围

**口径说明**：M9A 的最终形态是 project pack，这是方案文档的设计目标。但 P0/P1 不迁移 M9A runtime，M9A 后续是否真的迁入 MaaFW project pack / 共享 runner，必须另走兼容验收门。本节讲的是"为什么有这个设计目标"，不是"P1 就这么做"。

**设计目标的理由**：
1. M9A 当前运行逻辑由 M9A.exe 处理，不需要独立的 runner（现状审计事实）
2. M9A 只需要声明自己的默认值、任务语义、周月规则、文案和页面
3. project pack SDK 比 ScriptAdapter 简单得多（只声明元数据，不开放 run plan hook）

如果 M9A 注册独立脚本类型，就需要实现完整的 ScriptAdapterHooks（9 个方法），但 M9A 的运行逻辑和 MaaFW 不同（M9A 是进程驱动，MaaFW 是引擎驱动），强行套 MaaFW 的 hooks 会出现大量"空实现"。

project pack 让 M9A 只声明差异（默认队列、周月规则、文案），共性（任务构建、选项编辑、说明查看）由共享组件层处理。这是"组合优于继承"的设计原则。

**但落地时机在 P5+**：P0/P1 只冻结契约、抽 interface 包，不动 M9A runtime。M9A 是否最终走 project pack 路径、是否复用 MaaFWTaskBuilder，由 P4/P5 的兼容验收门结果决定。如果验收门发现 M9A 的双路径加载（interface.json + resource/tasks/*.json 回退）和 MaaFW interface_loader 差异过大，可能保持 M9A 独立实现，不强行统一。

## 8. 常见问题预答

### Q1: 为什么 P0/P1 不写代码？

因为 P0 的定义就是"契约盘点，不移动代码"（方案文档第 13 节）。P1 才开始抽 interface 包。P0 先把契约冻结，让 P1 有据可依。

### Q2: 这些文档会随实现更新吗？

会。P1 实现过程中可能发现契约需要调整（比如某个字段名不合理），届时更新契约文档并记录变更原因。但 1.0 后 v1 DTO 只增不改。

### Q3: facade 什么时候启用？

facade 默认不启用。只有 old/new 对照通过并经人工确认后，才允许通过**非旧配置项**的方式启用（环境变量 / feature flag / 测试入口），**不引入 `MaaFWConfig.UsePluginInterface` 之类的字段**，不切换默认运行路径。启用后旧路径仍保留作为 fallback。

### Q4: M9A 的 interface.json 和 MaaFW 的 interface.json 格式一样吗？

是的，都是 PI V2 规范。但 M9A 的 task_loader 有双路径加载（interface.json 优先，resource/tasks/*.json 回退），MaaFW 的 interface_loader 只支持 interface.json。

### Q5: 为什么不统一 M9A 和 MaaFW 的 import 合并逻辑？

因为 M9A 有双路径加载的回退机制，MaaFW 没有。强行统一会引入不必要的复杂性。P5 会评估是否统一。

### Q6: 前端共享组件什么时候实现？

P4。P0/P1 只设计不实现。P4 时共享组件层随 `automas-script-maafw` 落地，P5 时 M9A pack 复用共享组件。

### Q7: 计划表（PlanConfig）什么时候做？

当前阶段不做。方案文档第 2 节红线第 11 条明确："当前阶段不实现计划表，不新增 MaaFWPlanConfig、QueueMode、PlanId、PLAN_BOOK、planTypeRegistry、MaaFWPlanTable。" 计划表是 P4+ 的独立议题，和插件化解耦。

### Q8: 为什么不直接用 SchemaForm 做任务构建器？

SchemaForm 是为平铺字段表单设计的，不支持可拖拽排序的任务队列、递归嵌套的选项编辑器、controller/resource 联动过滤、preset 一键应用。这些是 MaaFW 任务构建的核心交互，需要专用组件。

## 9. 下一步行动建议

1. **审核 4 份文档**：按第 6 节的阅读指南顺序阅读。
2. **决策待确认事项**：契约文档第 10 节 6 个问题、checklist 文档第 6 节 6 个问题、验收门文档第 10 节 5 个问题。
3. **提供本地样例**：P1 对照测试需要 M9A 和 MaaEnd 的 interface.json 样例。
4. **确认 emulator 服务能力**：P0-5 需要审计 app/services/emulator 相关代码。
5. **批准 P1 开工**：P0 审核通过后，P1-1（创建 interface 包脚手架）是第一个施工任务。
