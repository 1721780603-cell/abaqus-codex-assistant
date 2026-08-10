# 项目架构

## 主流程

```text
JSON 配置
   │
   ▼
Python 3 参数校验
   │
   ▼
abqpy 启动 Abaqus/CAE noGUI
   │
   ▼
Abaqus Python 2.7 建模、网格、边界条件、求解
   │
   ▼
读取 ODB 最后一帧的 U 和 S
   │
   ▼
results.json
   │
   ▼
Python 3 生成中文 report.md
```

## 模块职责

- `environment.py`：Abaqus 与自带 Python；
- `abqpy_environment.py`：abqpy 版本匹配；
- `mcp_environment.py`：MCP 文件、Codex 注册和导入验证；
- `mcp_setup.py`：经明确确认后的固定版本安装；
- `doctor.py`：综合体检；
- `configuration.py`：输入校验；
- `scenario.py`：最小化场景配置；
- `workflow.py`：创建独立运行目录并协调全流程；
- `abaqus_scripts/rectangle_tension.py`：Abaqus 2021/Python 2.7 端逻辑；
- `abaqus_scripts/plate_with_hole_tension.py`：中心圆孔板和孔边局部网格逻辑；
- `report.py`：中文 Markdown 报告；
- `cli.py`：统一命令行。

## 为什么分成两个 Python 环境

Abaqus 2021 自带 Python 2.7，现代开发工具通常使用 Python 3。主程序使用 Python 3 进行输入校验、命令编排和报告生成；真正的 Abaqus API 脚本保持 Python 2.7 兼容。这样既能获得现代开发体验，又不修改 Abaqus 安装目录。

## 结果可追溯性

每次运行创建唯一时间戳目录。公开输出中保存校验后的配置、结构化结果和报告；大型 ODB、CAE、SIM 及日志保存在 `work`，默认被 Git 忽略。
