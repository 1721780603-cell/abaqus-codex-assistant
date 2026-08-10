# 版本支持表

“已验证”表示维护者在真实 Abaqus 环境中完成建模、Standard 求解、ODB 读取和报告生成，不表示厂商官方认证。

| 环境 | 状态 | 说明 |
|---|---|---|
| Windows 11 + Abaqus 2021 | 已验证 | 第一阶段默认示例完整通过 |
| Abaqus Python 2.7.15 | 已验证 | Abaqus 2021 自带环境 |
| abqpy 2021.7.3 | 已验证 | 与 Abaqus 2021 大版本匹配 |
| Python 3.10 | CI 测试 | 主程序最低支持版本 |
| Python 3.13 | 本机与 CI 测试 | 主程序开发环境 |
| Windows 10 | 社区测试 | 尚未完成维护者真实验证 |
| Abaqus 2022–2025 | 未验证 | 欢迎提供脱敏测试结果和 PR |
| Linux | 未支持 | 当前安装器和调用流程以 Windows 为主 |

新增“已验证”组合必须在 Pull Request 中记录 Abaqus 版本、Python 版本、`.sta` 成功标记和默认示例关键结果。
