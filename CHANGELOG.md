# 变更日志

本项目遵循语义化版本思想：不兼容变更提升主版本，新功能提升次版本，兼容修复提升修订版本。Alpha 阶段的接口仍可能调整。

## [Unreleased]

### 计划

- 参数化批量分析；
- 结果曲线和 PDF 报告；
- 论文复现参数证据表；
- 更多 Abaqus 版本验证。

## [0.1.0-alpha] - 2026-08-10

### 新增

- Abaqus、Abaqus Python、abqpy 和 MCP 综合体检；
- 经用户确认的固定版本 Abaqus MCP 安装与注册；
- 五种最小使用场景配置；
- 二维平面应力矩形板拉伸建模与 Abaqus/Standard 自动求解；
- ODB 最大位移模和最大 Mises 应力提取；
- 结构化 JSON 结果与中文 Markdown 报告；
- 输入校验、20 项离线测试和 GitHub Actions；
- Windows/Linux CI、Issue/PR 模板、Dependabot 和发布维护文档；
- README、快速开始、安全说明、贡献指南和论文访问边界。

### 已验证

- Windows 11；
- Abaqus 2021；
- Abaqus Python 2.7.15；
- abqpy 2021.7.3；
- 默认示例最大位移模 0.10017984 mm、最大 Mises 应力 210 MPa。
