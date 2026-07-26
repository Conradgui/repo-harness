# ADR-007 · `read_only` 不再接受 `excluded_commands` 豁免

**状态**：已执行
**日期**：2026-07-27
**性质**：行为变更 + 安全修复

---

## 处境

`excluded_commands` 是一份用户配置的命令白名单，含义是"这些命令不需要沙箱"。原先它在 `read_only` 模式下也生效——匹配的命令会**跳过隔离直接执行**。

这个豁免依赖一个判断：**能否从命令字符串看出它只会做一件事**。三轮修补，三次被绕过：

| 轮次 | 守卫 | 绕过方式 |
|---|---|---|
| 初版 | 匹配 `$(`、`${`、反引号、`\` 四种拼写 | `git status; rm -rf x`、`\|`、`>`、换行 |
| 第二版 | 单字符黑名单 `;&\|<>$`\\(){}!#` | `git status %X%` —— cmd.exe 展开后重新解析 |
| 第三版 | 补上 `%`、`^` | **`git status/../whoami`** |

第三次绕过不含任何 shell 元字符。它利用的是 git 自己的 dashed-external 分发：`git status/../whoami` → `git-status/../whoami` → 按字面路径解析成 `whoami` → 在 PATH 中找到并执行。cmd.exe 和 sh 上都成立，实测输出了当前用户名。

## 问题的性质

**这不是补丁没打全，是方案本身不成立。**

字符黑名单试图表达的是"这个命令只能做一件事"，但那不是字符串的属性——它取决于被调用程序自己的行为。git 会分发外部命令；别的程序可能有 `--exec`、插件目录、配置文件里的钩子。要穷举这些，等于要理解 PATH 上每个程序的语义。

## 决策

**`read_only` 模式下不再有任何豁免。该模式下不执行任何 shell 命令。**

这正是模式名字的字面含义。判断顺序改为先看模式、再看豁免：

```python
if mode == "off":
    return None
if mode == "read_only":
    raise RuntimeError("sandbox read_only blocks run_shell")
if mode != "required" and self._command_is_excluded(command):
    return None
```

`PermissionChecker` 同步简化——`read_only` 直接返回 deny，不再委托给匹配器。

## 代价

用户不能再用 `excluded_commands` 在 `read_only` 下开一个口子跑 `git status`。**这是有意的**：想跑命令就不该选 `read_only`，`best_effort` 才是"能隔离就隔离，不能就直接跑"的模式。

字符黑名单保留在 `_command_is_excluded` 里，服务于 `best_effort`。那个模式本来就不提供隔离保证——豁免在那里是便利，不是安全边界，文档已写明。

## 为什么不继续修补

考虑过在程序 token 上禁止路径分隔符。它能挡住这一个案例，但挡不住下一个——问题在于任何"从字符串推断行为"的方案都是在猜。**删掉一个不成立的安全边界，比维护一个看起来有效的更诚实。**

## 关联

- [ADR-002](002-安全边界用开关而非删除实现.md)：这次删的是**豁免**（一个判断），不是实现。`excluded_commands` 配置项仍在，语义收窄
- 三次绕过分别由第 5、7、8 轮 stage gate 发现；前两次我以为修好了，都是错的
