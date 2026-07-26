# nethack_agent_player

让 Agent（LLM）通过 NLE 接口逐回合玩 NetHack。游戏跑在后台的 `play.py`，Agent 通过
`/tmp` 文件 IPC（封装在 `agent_helper.py`）逐回合读状态、发动作。完整流程见 [SKILL.md](SKILL.md)。

## 安装

nle 在 macOS 无 wheel，需从源码编译。详见 [docs/setup.md](docs/setup.md)（`brew install
python@3.13 cmake bison flex` → 建 `.venv` → `pip install nle gymnasium`，需 bison/flex
PATH + CFLAGS）。

## 运行

```bash
./start_game_mac.sh                       # 启动并等待自由选择角色
python3 agent_helper.py --choose bar-hum-mal-neu
```

然后每回合用 `agent_helper.py` 发动作（纯 /tmp IPC，任意 python3 即可）：

```bash
python3 agent_helper.py --read           # 读当前状态
python3 agent_helper.py goto:28,4        # 自动寻路到坐标
python3 agent_helper.py north            # 单步
```

动作全集与决策规则见 [SKILL.md](SKILL.md)；IPC 协议见 [docs/ipc.md](docs/ipc.md)。

## state 格式

`play.py` 输出**解析后的特征摘要**（非原始 TTY）：状态行 + 消息 + 累计地图 + `Features:`
（玩家坐标、楼梯、怪物、可走方向）+ 库存。示例与字段见 [docs/ipc.md](docs/ipc.md)。

## 角色

格式 `<role>-<race>-<gender>-<align>`，如 `val-hum-fem-neu`、`wiz-hum-mal-neu`。
选项见 [docs/character_select.md](docs/character_select.md)。

## 参考

- [NetHack Wiki](https://nethackwiki.com/wiki/Main_Page)
- [NLE GitHub](https://github.com/facebookresearch/nle)
