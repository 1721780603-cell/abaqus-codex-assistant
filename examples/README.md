# 示例：二维矩形板拉伸

默认示例使用平面应力单元，左边限制水平位移、左下角限制竖直刚体位移、右边施加水平拉伸位移。

```powershell
.\.venv\Scripts\abaqus-codex.exe run --config .\configs\rectangle_tension.json
```

建议初学者先保持默认参数运行，核对报告中的 210 MPa，再依次只修改一个参数，观察结果变化。不要同时修改几何、材料、边界条件和单位制。
