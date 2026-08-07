# 多 Agent 模拟用户验证复盘

> 目的：以多个隔离子 Agent 独立设计"真实用户操作"场景，主 Agent 用 Terminal 执行，再由独立 Agent 验证——检验 repo-harness 在"真实用户视角"下的可用性、安全性与过程质量，并记录 ADR 问答、过程性记录质量与结论。
> 记录日期：2026-08-07。当前 HEAD：`544eecf`。

## 一、流程与方法

```
第一批(3 子 Agent,隔离上下文,互不照搬)
  ├─ Agent A: 全新用户从零上手(10 场景 S01-S10)
  ├─ Agent B: Auto Issue Fix 用户(8 场景)
  └─ Agent C: REPL 与记忆系统用户(8 场景)
        ↓ 独立设计:操作/预期/判定标准
主 Agent 用 Terminal 真实执行 13 个场景,收集原始输出
        ↓
第二批(2 子 Agent,独立验证)
  ├─ Agent D: 逐场景判定 + 过程质量 + 缺陷分析
  └─ Agent E: 安全/计费/副作用审查 + 可信度
        ↓ 独立复核代码与结果
主 Agent 裁决:修复真实缺陷,判定误报,汇总资料
```

## 二、执行结果汇总

### 场景判定(13 个执行场景)

| 场景 | 结果 | 判定 |
|---|---|---|
| S01 模块入口 --help | exit 0, 参数齐全 | ✅ PASS |
| S02 双入口一致 | 均有效 | ✅ PASS |
| S03 未知厂商 probe(无 --smoke) | exit 1 "could not infer", 不写配置, 不联网 | ✅ PASS |
| S04 probe 识别 chat-completions + --write | 识别正确、endpoint 剥离、key 缺失不写配置 | ✅ PASS |
| S05 doctor 缺 key | exit 1 blocked, 不泄 secret | ✅ PASS |
| S06 错误 provider 名 | exit 2 invalid choice, 无 traceback | ✅ PASS |
| S08 --cwd 不存在路径 | one-shot 静默容忍(幽灵工作区) | ⚠️ **真实缺陷,已修** |
| SC-01 REPL /help | 曾误报 401,实证纯本地 | ✅ 无缺陷(测试环境干扰) |
| SC-03 记忆 G3 | 中文标记/非英文拦截/英文成功 | ✅ PASS |
| SC-04 memory pack export | exit 0, safe-transfer 仅 durable | ✅ PASS |
| SC-06 中断恢复 | from_session id 一致/history 保留 | ✅ PASS |
| AIF-1 dry-run | exit 0, 22 证据文件, 不碰 GitHub | ✅ PASS |
| AIF-2 未确认维护权限 | exit 1 拦截, 但先 fetch issue | ⚠️ **真实缺陷,已修** |

### 发现并修复的真实缺陷(2 个,commit `544eecf`)

1. **AIF-2 权限检查顺序**:`maintainer_access_confirmed` 检查在 `issue_view` 之后 → 未确认权限时仍发 `gh issue view`(网络副作用)。**修复**:检查前置,未确认时零网络触碰。新增测试断言无 backend 调用。
2. **S08 坏 cwd 静默容忍**:`--cwd` 指向不存在目录时,WorkspaceContext 把 repo_root 退化为幽灵路径,agent 在假工作区假装工作。**修复**:`build_agent` 显式拒绝不存在的 cwd(ValueError)。诊断命令(probe/doctor)不走此路径,不受影响。新增 2 测试。

### 判定为无缺陷的误报

**SC-01"REPL 启动即连 provider"是误判**:
- 用 `complete_model` spy 实证:`build_agent` 调用 0 次、`/help` 调用 0 次
- 之前的 401 来自测试管道喂入方式的环境干扰,非 REPL 缺陷
- 验证员 A 的代码分析(`/help` 直接返回 HELP_DETAILS)正确

## 三、ADR 问答(过程中的关键决策)

### ADR-Q1:多 Agent 模拟用户是否比单 Agent 更有价值?
**答**:是,但有边界。第二批独立验证抓到了主 Agent 的**误判**(SC-01 401)和**遗漏**(AIF-2 网络副作用)——这正是"杜绝思维惰性"的价值。边界:子 Agent 无法执行命令,必须由主 Agent 执行;场景设计质量依赖子 Agent 对代码的阅读深度。

### ADR-Q2:为什么"未确认维护权限"也要零网络触碰?
**答**:安全边界。AIF-2 之前的设计(先 fetch issue 再检查权限)产生"看似安全实则已联网"的副作用——违反"未授权即零接触"原则。检查前置是更严格的安全姿态(与 ADR-002 fail-closed 一致)。

### ADR-Q3:坏 cwd 应报错还是警告?
**答**:报错(ValueError)。幽灵工作区会导致文件写入落到错误位置,静默容忍比报错更危险。但只在 `build_agent`(需真实工作区的路径)校验,诊断命令(probe/doctor 可从任意目录运行)不校验——避免误伤。

### ADR-Q4:slash 命令应不依赖模型吗?
**答**:是(代码已如此)。`/help` 等纯本地元操作应始终可用,即使 provider 未配置。实测确认无缺陷,但建议未来补一个"REPL 启动不发起模型请求"的回归测试,防止回归。

## 四、过程性记录质量评估

**做得好的**:
- 子 Agent 隔离上下文、互不照搬(三个设计员独立产出 26 场景,无重复)
- 场景均给出可验证断言(退出码/输出关键词/副作用文件)
- 第二批独立验证抓出 2 真实缺陷 + 1 误判,交叉验证有效
- AIF-2 用 RecordingBackend 断言"零调用",S08 用 spy 实证"零模型请求"——证据链扎实

**不足**:
- 13/26 场景执行率(受限于避免真实 provider/网络副作用)
- 核心路径未覆盖:真实 one-shot 对话、approval 模式、sandbox read_only 拦截、G2 升级触发、--resume latest(建议后续补测)
- exit code 测量受 PowerShell 管道影响的风险(部分场景用重定向缓解)
- 临时诊断脚本散落在临时目录(工作区外,未清理)

## 五、结论性资料

1. **repo-harness 在"真实用户视角"下的核心路径(装配/provider 诊断/记忆治理/恢复/AIF 安全拦截)工作正常**,11/13 场景 PASS。
2. **发现并修复 2 个真实缺陷**(AIF 权限顺序、坏 cwd 静默容忍),均通过多 Agent 交叉验证确认。
3. **SC-01 误报已澄清**(slash 命令纯本地),避免了一次不必要的架构改动。
4. **建议后续补测**:真实 provider 对话、approval/sandbox 模式、G2 升级触发、--resume latest、REPL 不依赖模型的回归测试。
5. 本次验证证明了"多 Agent 模拟用户 + Terminal 执行 + 独立验证"流程的有效性——它发现了主 Agent 单独测试会遗漏的问题。

## 六、红线遵守

- ✅ 所有场景避免真实计费(AIF-2 修复后零网络触碰;probe 无 --smoke 不联网)
- ✅ 未对任何第三方 GitHub 仓库产生副作用(本地 fixture + 权限前置)
- ✅ 缺陷修复基于工程合理性(非看板),均有独立验证
- ✅ 误判被诚实纠正(SC-01 撤销了不必要改动)
