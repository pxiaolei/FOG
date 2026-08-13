---
name: lx-update
description: FOG 同事侧安全更新工具。用户要求更新 FOG、同步共享 Skill、拉取最新版或检查 GitHub 更新时使用；只允许从 pxiaolei/FOG 的 main 分支做已确认的 fast-forward，不覆盖本地配置、业务文件或未提交改动。
---

# FOG 同事侧安全更新

本 Skill 只负责同事从共享 GitHub 仓更新本地 `FOG`。维护者从私人 `p-fog` 发布共享快照时使用 `lx-fogshare`，不要混用。

## 安全模型

- 唯一远端是 `pxiaolei/FOG`，唯一更新分支是 `main`。
- `check` 在临时 Git 仓检查远端，不修改当前仓的 HEAD、index、工作树或 refs。
- `apply` 只接受 `check` 返回的完整远端 commit，并且必须显式传入 `--confirmed <commit>`。
- 当前分支不是 `main`、工作区有 tracked/untracked 改动、分支领先或分叉时立即停止。
- 远端包含未在代码固定退役清单中的删除、符号链接、submodule、真实配置、业务 workspace 文件、缓存或运行产物时立即停止。
- 固定退役清单只用于移除已停止共享的 Skill 和其私有基础模块；`check` 必须逐文件展示删除，`apply` 仍需用完整远端 commit 显式确认，不接受任意路径删除。
- 只执行 fast-forward；不自动 stash、merge commit、reset、checkout、clean、安装、commit 或 push。
- `config/fog_config.yaml`、`workspace/` 业务文件和 Skill 本地配置必须保持 Git ignored；真实配置文件完全不参与更新，已有字段和值（包括 token、API Key、账号、目录和个人偏好）逐字段保留，更新后只做只读检查，不自动迁移或改写。

## 使用流程

先在 `FOG` 仓根目录检查：

```bash
python .workbuddy/skills/lx-update/scripts/update_fog.py check
```

若输出 `status: fast-forward-ready`，把同一份输出中的完整 `remote_commit` 原样用于确认：

```bash
python .workbuddy/skills/lx-update/scripts/update_fog.py apply --confirmed <remote_commit>
```

结果说明：

- `up-to-date`：本地已是远端版本，无需更新。
- `fast-forward-ready`：可按给出的 commit 更新。
- `blocked`：先处理输出列出的本地改动、分叉或远端安全问题；不要绕过。
- `applied`：HEAD 已更新到确认的 commit，Git 状态与 Skill 索引读回通过。
- `applied-with-warnings`：代码已快进，但配置检查仍有待补项；不要误称更新失败或重复拉取。

若配置模板新增字段，只先查看 `python tools/fog.py migrate-config --dry-run` 的计划。`lx-update` 不会自动把 example 合并进真实配置，也不会覆盖、清空或重排任何已有字段；真实 `config/fog_config.yaml` 的补键或改写必须另行取得用户明确授权。

## 执行契约

### 输入

- 位于官方 `pxiaolei/FOG` clone 的本地仓根目录。
- `check` 无写入确认；`apply` 必须提供本次检查得到的完整 `remote_commit`。

### 输出

- 本地/远端 commit、分支关系、逐文件变更和阻断原因。
- 更新后的 HEAD、Git 干净状态、Skill 索引校验与只读配置检查结果。

### 验收

- 未确认、确认 commit 不匹配或任何安全门禁失败时，工作树和 HEAD 不变。
- 真实更新只能是 `main` 到已确认 commit 的 fast-forward，且远端变更不含未授权删除或受保护路径。
- ignored 的真实配置、workspace 业务文件、缓存和输出字节级保留；配置内 token、API Key 等已有字段和值逐字段保留。
- 更新后 `HEAD == confirmed commit`、工作区干净且 `python tools/generate_skill_index.py --check` 通过；配置问题单独标记为待处理。
