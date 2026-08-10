# 三维路面移动载荷与 DLOAD 入门

## 这个示例解决什么问题

`configs/moving_load_road.json` 建立一个单层三维弹性路面。Fortran `DLOAD` 根据当前时间和顶面积分点坐标，让一个矩形压力区沿 X 正方向匀速移动。

这是“用户子程序能否编译、载荷能否移动、动力结果能否读取”的最小教学示例，不是三级公路设计模型。

## 文件如何配合

```text
moving_load_road.json
        │ 参数校验并计算载荷起点、分析时长
        ▼
moving_pressure_dload.for.in
        │ 生成本次运行专用 moving_pressure_dload.for
        ▼
moving_load_road.py
        │ 三维建模、动力求解、遍历全部 ODB 帧
        ▼
results.json + report.md
```

用户不能在 JSON 中传入任意脚本路径。模型类型只会映射到项目内置的 Abaqus 脚本和 DLOAD 模板。

## 默认教学参数

| 参数 | 默认值 | 含义 |
|---|---:|---|
| 路面尺寸 | 4000 × 2000 × 600 mm | 单层有限长实体 |
| 弹性模量 | 5000 MPa | 教学线弹性材料 |
| 泊松比 | 0.35 | 教学线弹性材料 |
| 密度 | 2.4×10⁻⁹ tonne/mm³ | 与 mm–MPa–s 一致 |
| 接触压力 | 0.7 MPa | 教学轮载压力 |
| 接触区 | 200 × 200 mm | 单个矩形轮印 |
| 速度 | 10000 mm/s | 约 36 km/h |
| 最大时间增量 | 0.002 s | 每个轮印长度约 10 个增量 |

## 运行

```powershell
.\.venv\Scripts\python.exe -m abaqus_codex run --config .\configs\moving_load_road.json
```

运行前需要 Abaqus/Standard、Visual Studio C++ 工具链和与 Abaqus 匹配的 Intel Fortran Classic。项目不会分发这些商业软件，也不会绕过许可证。

默认配置已在 Abaqus 2021、Visual Studio 2019 和 Intel Fortran 19.1.3.311 中完成真实编译、链接和求解。Abaqus 的 [DLOAD 官方文档](https://docs.software.vt.edu/abaqusv2024/English/SIMACAESUBRefMap/simasub-c-dload.htm)说明了 `TIME`、`COORDS` 和返回压力 `F` 的含义。

## 如何看结果

动力报告遍历全部输出帧，给出：

- 全程最大位移模及发生时间；
- 全程最大竖向位移绝对值、U3 符号及发生时间；
- 全程最大 Mises 应力及发生时间。

默认示例的最大响应接近入口或出口，说明有限模型存在端部效应。不要只凭一个极值判断道路性能。

## 为什么还不是正式三级公路模型

公路等级不能直接转换成一个 DLOAD 压力值。正式分析至少还要根据项目采用的现行标准和实测资料确定：

- 沥青路面或水泥混凝土路面；
- 各结构层厚度、密度、模量、阻尼和层间接触；
- 轴载、单双轮、轮胎接地尺寸与压力分布；
- 设计速度、路面不平度和车辆悬架；
- 边界距离、吸收边界、网格和时间增量收敛性。

桥梁汽车荷载与路面轮胎接触荷载也不是同一个概念。交通运输部发布的 [JTG D60—2015](https://xxgk.mot.gov.cn/2020/jigou/glj/202006/t20200623_3312312.html)将高速公路与三级公路列为不同公路等级；若研究对象改为桥梁，应重新选择模型和规范荷载。

## 推荐的下一步

先把单层模型改成三层路面，并保持轮载不变。每增加一层，只检查一次材料、网格和层间连接，再进行结果对比；暂时不要同时加入双轮、随机不平度和复杂材料。
