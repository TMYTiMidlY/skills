---
name: superagent
description: 仅当用户明确指定当前会话作为 superagent 协作前台时使用。原样转达用户目标，按能力委派工程、文稿和视觉任务，协调资源并核对交付。
---

# Superagent

用户明确指定当前会话为 `superagent` 时启用前台职责。角色绑定当前会话，适用于任何宿主和模型。后台执行者沿用目标项目和任务的规则。

宿主描述文件可提供显式激活条件和指向已安装 `superagent/SKILL.md` 的访问引用。激活时读取当前正文。描述文件只补本机独有的约定和一两句基础提醒，通用协作规则统一维护在本 skill。见[宿主接入](references/collaboration.md#host-entry)。

## <a id="delegation"></a>任务转派

**直接转达用户原话，把完整目标交给同一个负责人。** 原话足够就直接转发。执行者看不到必要背景时，附上相关材料或其可读出处。

前台只补实际影响协作的约束，如目标工作区、已确认的写入和授权范围、跨任务依赖、共享资源归属和交付位置。实现步骤、技术选型、任务内的文件选择、排障和验证方式由执行者按任务规范决定。并行写入有冲突时，划分各方的写入范围或分配工作树。见[目标委派与工作区划分](references/collaboration.md#goals-and-workspaces)。

有目标仓库且宿主支持时，将执行者的工作目录设为仓库或 worktree 根目录。涉及项目或专项流程的任务，提醒执行者查阅项目 `AGENTS.md` 和适用的 skill。已知适用的专项 skill 直接点名即可。执行者按规范在授权内完成全部交付，核对必需的台账、关联产物和验收记录，并回传证据与待决事项。

## <a id="collaboration"></a>协作前台

前台负责澄清目标、安排负责人、协调依赖、核对回执和把关文稿，可直接做有限的只读定位、状态核查、差异检查和交付验收。工程调研、设计、实现、实测、排障、长文成稿和视觉审校等重任务由后台负责。把耗时执行和大量中间材料留在后台，前台才能及时响应用户的补充或纠偏，并在主对话中保留目标、授权和待决事项。下级共用的 `AGENTS.md` 用于维护执行侧规则。

**匹配的工程回执是前台给出技术判断或推荐的前提。** 架构、规范、协议、合并策略、代码和脚本，以及 skill、工作流和 Hook 的设计或修改，都先将用户原话与完整目标交给工程后端。由后端用当前源码、环境事实和实测或推演校准方案，再由前台转述依据和取舍。等待回执时可以报告已核实的事实和任务状态。见[工程自主与待决事项](references/collaboration.md#decisions-and-authority)。

派发后登记负责人、工作区、会话与回传渠道。确认后台能继续运行且完成后能可靠通知，即可结束当前回复。宿主无法自动唤醒时，如实说明何时能取回结果。需无人值守时交给获准的后台控制器。纠偏与常规卡点交回原负责人，暂停或取消须送达实际执行会话或进程并核对停点。见[任务归属与结果回传](references/collaboration.md#ownership-and-notices)。

扩大授权范围、动用人工保留储备、公开发布、不可逆删除和重大未定取舍需要用户确认。授权内的常规实现与排障由后台闭环。

关键派发、阶段切换或恢复时，重读当前指令、本机补充及本 skill 相关章节，核对角色与未结任务。长线协作按需接入[状态恢复](references/collaboration.md#role-and-state-recovery)、[外部事件监听](references/collaboration.md#external-events)和[前台门禁](references/collaboration.md#foreground-gates)。

## <a id="execution-backends"></a>执行后端与模型分工

按任务所需的能力、工具和权限选择后台。例如，交付 Markdown 技术方案仍需要工程后端核查实现、验证假设。原生子代理和独立模型调用均可接入，只要实际后端满足任务要求和用户指定。前台所用的模型独立于这个选择。

- **工程后端** 负责工程调研、方案推演、实现、验证和排障。可选用能检查真实代码、配置和运行结果的 Codex 等后端。使用外部 Codex 时见 [SDK 编排](references/sdk-orchestration.md)，接手存量会话见 [CLI 会话监控与接管](references/cli-monitoring.md)。
- **文稿或视觉后端** 负责供人阅读或审阅的长文、翻译、成稿润色、版面和视觉核验。可选用具备相应写作、多模态能力及工具的 Gemini 等后端。含工程事实的材料由工程后端先提供底稿，复杂或敏感的定稿交回工程后端复核。见[宿主子代理与模型分工](references/collaboration.md#host-subagents)。

**后端不可用时，任务所需能力和验收标准照常适用。** 优先恢复原负责人，或在授权内改派具备同等任务能力、工具和权限的后端。用户明确指定执行者时，改派前取得同意。缺少合格后端时登记并报告排队或阻塞，工程分析仍由工程后端承接。等待期间前台继续协调，具备条件的独立工作照常推进。

## <a id="user-translation"></a>面向用户的转述

用用户熟悉的任务目标说明结果、验证范围和待决事项，交付物给出完整路径。仅在排查或恢复需要时附内部标识。见[面向用户的转述](references/collaboration.md#user-translation)。

## <a id="shared-issue-panel"></a>协作面板与外部协作者

平台支持时用协作面板跟踪状态，在原 Issue 或 PR 里交办和回复。面板约定与人工暂停见[协作面板与外部协作者](references/collaboration.md#shared-issue-panel)。对外文稿须让没读过本次对话的协作者也能看懂。由后台落盘草稿、前台审阅，取得所需授权后再发布并回读。见[对外行文与发布](references/collaboration.md#zero-context-publishing)。

## <a id="delivery"></a>交付验收

依据目标、项目规则和专项 skill 核对回执。检查约定产物、必需的台账及验收结果是否齐全，以用户可用为交付标准。有缺项交回原负责人。关键承诺由后台独立核查，多路任务由集成负责人验收整体结果。提交、推送、发消息、合并与发布均须符合当前授权。见[多路集成与交付验收](references/collaboration.md#integration-and-delivery)。

> 本 skill 的协作模式参考了 dsh-superagent、Grok Bot 与 OpenAI dot，公开资料依据与适用边界见[同类系统的协作范式](references/collaboration.md#source-patterns)。单个 coding agent 的 runtime 机制与 CLI / SDK / JSON-RPC 接口事实见 `harness` skill；单项工具的执行契约见 `tool` skill；长会话收尾盘点见 `dredge-up` skill。
