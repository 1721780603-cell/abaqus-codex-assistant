# 贡献指南

感谢参与 Abaqus Codex Assistant。

## 基本原则

- 每个 Pull Request 只解决一个清晰问题；
- 自写代码添加中文注释或中文文档字符串；
- 不提交 ODB、CAE、SIM、许可证文件、账号凭据或论文全文；
- 新增功能必须包含不依赖 Abaqus 许可证的离线测试；
- 涉及真实 Abaqus API 时，在 PR 中说明验证版本和结果；
- 不绕过 Abaqus 许可证、论文付费墙或机构认证。

## 本地测试

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实 Abaqus 测试请使用独立示例参数，不使用机密工程数据。

## 分支与 Pull Request

- 功能分支使用 `feature/简短名称`；
- 修复分支使用 `fix/简短名称`；
- Pull Request 应只解决一个清晰问题；
- PR 描述填写影响范围、测试和真实 Abaqus 验证信息；
- 合并前同步更新文档和 `CHANGELOG.md`。

当前支持范围见 [版本支持表](docs/version-support.md)，发布流程见 [发布清单](RELEASING.md)。
