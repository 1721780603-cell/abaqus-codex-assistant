# 测试目录

这里保存环境检测、参数检查、场景配置和报告生成等功能的自动测试。

测试时应尽量避免每次都启动真实 Abaqus 求解，以减少运行时间和许可证占用。

普通测试只使用 Python 标准库，不要求 GitHub CI 安装 Abaqus。真实 Abaqus 端到端测试由有许可证的本机单独完成。

开发者在项目根目录可先执行 `python -m pip install -e ".[test]"`，再运行
`python -m unittest discover -s tests -v`。如果没有采用可编辑安装，则把项目根目录
的 `src` 加入 `PYTHONPATH` 后再运行测试。GitHub Actions 使用普通安装来模拟发布后的用户环境。

首次启动向导测试会模拟 GitHub CLI、Zotero 回环端点和 ScienceDirect 人工登录状态，不连接真实账号、网络服务或浏览器会话。
