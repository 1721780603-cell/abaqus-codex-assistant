# GitHub 仓库设置清单

以下设置需要在远程仓库创建后由管理员启用，不能仅通过普通仓库文件生效。

## 基础设置

- 仓库可见性：公开；
- 默认分支：`main`；
- 启用 Issues；
- 建议启用 Discussions，用于初学者问答；
- 仓库描述明确写明“非官方社区项目”；
- Topics 建议：`abaqus`、`finite-element-analysis`、`python`、`codex`、`education`。

## `main` 分支规则

- 禁止删除和强制推送；
- 要求通过 Pull Request 合并；
- 要求 `Python tests` 状态检查通过；
- 建议要求分支与 `main` 保持最新；
- 项目只有一名维护者时，可暂不要求第二人批准，避免把自己锁在规则外。

## 安全设置

- 启用 Dependency graph；
- 启用 Dependabot alerts 和 security updates；
- 启用 Private vulnerability reporting；
- 定期检查 Actions 权限，默认使用只读 `GITHUB_TOKEN`；
- 不在 Actions Secret 中保存 Abaqus 许可证或机构账号。

## 发布设置

首个公开版本使用 `v0.1.0-alpha` 标签。Release 说明应列出支持范围、真实验证环境、关键结果和已知限制，不上传 ODB、CAE 或商业软件文件。
