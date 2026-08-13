---
name: lx-init
description: FOG 旧初始化兼容 Skill。仅当用户明确提到 lx-init、FOG 初始化、初始化 FOG 或检查配置等旧入口时使用；新用户优先使用 tools/fog.py，本 Skill 只保留旧命令兼容。
---

# lx-init — 兼容入口

## 定位

新初始化入口是项目根目录的普通工具：

```bash
python tools/fog.py init                  # 默认 preview
python tools/fog.py init --confirmed      # 创建配置与 workspace
python tools/fog.py check
python tools/fog.py migrate-config        # 默认 preview
python tools/fog.py migrate-config --confirmed
```

所有 Skill 如需配置，直接读取：

```text
config/fog_config.yaml
```

`lx-init` 不再生成 `.workbuddy/skills/*/assets/config.yaml`。旧 `assets/config.yaml` 文件不再作为运行入口。

## 兼容命令

```bash
python .workbuddy/skills/lx-init/scripts/config_wizard.py check
python .workbuddy/skills/lx-init/scripts/config_wizard.py init-workspace --confirmed
python .workbuddy/skills/lx-init/scripts/config_wizard.py write-configs --dry-run
python .workbuddy/skills/lx-init/scripts/config_wizard.py apply --confirmed
# 已存在的初始化报告仅在显式确认覆盖时更新：
python .workbuddy/skills/lx-init/scripts/config_wizard.py apply --confirmed --overwrite
```

其中 `write-configs` 只输出跳过说明，不再写 per-Skill 配置。共享 Skill 读取 `config/fog_config.yaml`；内部不分享 Skill 的个人配置放在 `config/personal_config.yaml`。

## 安全规则

- 不读取、删除或覆盖 `workspace/` 下的业务文件
- 不写入真实 token、账号或 API Key 到任何可提交文件
- 配置缺失时只报告缺项，不生成假数据
- `init-workspace` 和 `apply` 默认只 preview，不创建目录、`.gitkeep` 或初始化报告；真实落盘必须追加 `--confirmed`，且不能与 `--dry-run` 同时使用。`apply` 的报告路径必须位于项目内；报告已存在时还必须追加 `--overwrite`，并在创建 workspace 前先阻断未授权覆盖。

## 执行契约

### 输入

- 用户明确要求的旧初始化/检查动作和当前项目根目录。
- 现有 `config/fog_config.yaml`、`config/personal_config.yaml` 与 workspace 状态。

### 输出

- 兼容命令对应的检查结果、缺失配置项和可执行的新入口命令。
- 不生成真实凭证，不覆盖业务目录。

### 验收

- `tools/fog.py init` 和 `migrate-config` 默认只 preview；创建目录、创建配置或备份并更新配置都必须显式 `--confirmed`。配置迁移使用不覆盖既有备份的序号路径并写后读回；读回不一致时恢复本次备份。
- `tools/fog.py check` 能明确区分已配置、缺失和不可访问项。
- 初始化不删除或覆盖 `workspace/`，且任何配置写入都不包含占位假密钥。
