---
name: lx-init
description: FOG 旧初始化兼容 Skill。新用户优先使用 tools/fog.py；本 Skill 仅保留旧触发词和旧命令兼容。
trigger_keywords:
  - lx-init
  - FOG 初始化
  - 初始化 FOG
  - 检查配置
location: project
---

# lx-init — 兼容入口

## 定位

新初始化入口是项目根目录的普通工具：

```bash
python tools/fog.py init
python tools/fog.py check
python tools/fog.py migrate-config
```

所有 Skill 如需配置，直接读取：

```text
config/fog_config.yaml
```

`lx-init` 不再生成 `.workbuddy/skills/*/assets/config.yaml`。旧 `assets/config.yaml` 文件不再作为运行入口。

## 兼容命令

```bash
python .workbuddy/skills/lx-init/scripts/config_wizard.py check
python .workbuddy/skills/lx-init/scripts/config_wizard.py init-workspace
python .workbuddy/skills/lx-init/scripts/config_wizard.py write-configs --dry-run
python .workbuddy/skills/lx-init/scripts/config_wizard.py apply
```

其中 `write-configs` 只输出跳过说明，不再写 per-Skill 配置。共享 Skill 读取 `config/fog_config.yaml`；内部不分享 Skill 的个人配置放在 `config/personal_config.yaml`。

## 安全规则

- 不读取、删除或覆盖 `workspace/` 下的业务文件
- 不写入真实 token、账号或 API Key 到任何可提交文件
- 配置缺失时只报告缺项，不生成假数据
