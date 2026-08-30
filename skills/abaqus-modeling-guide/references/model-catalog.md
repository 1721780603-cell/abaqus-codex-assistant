# 支持模型与提问顺序

只读取用户所选模型的部分。所有默认值都是流程教学值，不是工程设计推荐值。

## 快速选择

| 顺序 | 模型 | `model.type` | 适合学习 | 难度 |
|---:|---|---|---|---|
| 1 | 矩形板单向拉伸 | `rectangle` | 材料、位移边界、网格、理论核对 | 入门 |
| 2 | 中心圆孔板拉伸 | `plate_with_hole` | 应力集中、孔边局部网格 | 入门进阶 |
| 3 | 悬臂梁均布载荷弯曲 | `cantilever_bending` | 固定端、压力载荷、弯曲变形 | 入门进阶 |
| 4 | 方板双向拉伸 | `biaxial_tension` | 双向位移和双向应力状态 | 进阶 |
| 5 | 三维路面移动荷载 | `moving_load_road` | 动力分析、密度、DLOAD | 高级 |

前四个模型使用 mm–MPa 一致单位制。此时弹性模量和压力使用 MPa，几何和位移使用 mm。移动荷载使用 mm–MPa–s–tonne。

前四个二维模型都采用平面应力截面，主要单元为四节点减缩积分 `CPS4R`，必要位置允许三节点 `CPS3`。厚度由配置中的 `thickness` 赋给截面；它们不是壳模型或三维实体模型。向新手展示摘要时必须写出这些假设。

## 1. 矩形板单向拉伸

- 模板：`configs/rectangle_tension.json`
- 几何：`length=100`、`height=20`、`thickness=1`
- 材料：`youngs_modulus=210000`、`poisson_ratio=0.3`
- 约束与加载：左边 `U1=0`、左下角 `U2=0`，右边 `U1=right_edge_displacement=0.1`；其余面内自由度保持可动，以允许泊松收缩
- 网格：`mesh_size=2`
- 默认标识：`name=RectanglePlate2D`、`step_name=TensionStep`、`job_name=rectangle_tension_2d`、`num_cpus=1`

依次确认几何、材料、右边位移、网格和作业名。线弹性数量级可用 `E × 位移 / 长度` 核对远离边界的名义轴向应力，最大位移应接近施加位移但会包含泊松收缩分量。当前报告只给全模型最大 Mises 应力，不给截面平均 `S11` 或反力，因此理论值只能作数量级检查，不能擅自设成严格通过判据，也不能把边界附近局部峰值直接等同于名义应力。

## 2. 中心圆孔板拉伸

- 模板：`configs/plate_with_hole_tension.json`
- 几何：`length=100`、`height=50`、`thickness=1`、`hole_radius=5`
- 材料：`youngs_modulus=210000`、`poisson_ratio=0.3`
- 约束与加载：左边 `U1=0`、左下角 `U2=0`，右边 `U1=right_edge_displacement=0.1`
- 网格：`mesh_size=2`、`hole_mesh_size=0.5`
- 默认标识：`name=PlateWithHole2D`、`step_name=TensionStep`、`job_name=plate_with_hole_tension_2d`、`num_cpus=1`

孔直径必须小于板长和板高，孔边网格不能大于全局网格。第一次教学运行可用 `min(mesh_size, hole_radius / 4)` 作为孔边网格；之后再复制配置并逐次减半孔边网格，每次只启动一个作业。解释最大应力通常位于孔边且对网格敏感；在比较前与用户约定收敛指标，不把某个固定百分比冒充所有工程都适用的标准。

## 3. 悬臂梁均布载荷弯曲

- 模板：`configs/cantilever_bending.json`
- 几何：`length=100`、`height=20`、`thickness=1`
- 材料：`youngs_modulus=210000`、`poisson_ratio=0.3`
- 加载：左端固定，上边向下 `top_edge_pressure=1`
- 网格：`mesh_size=2`
- 默认标识：`name=CantileverBeam2D`、`step_name=BendingStep`、`job_name=cantilever_bending_2d`、`num_cpus=1`

明确压力单位为 MPa，而不是合力 N。结果解读要区分位移模与竖向挠度；固定端附近应力可能受到边界理想化影响。

## 4. 方板双向拉伸

- 模板：`configs/biaxial_tension.json`
- 几何：`length=100`、`height=100`、`thickness=1`
- 材料：`youngs_modulus=210000`、`poisson_ratio=0.3`
- 加载：`right_edge_displacement=0.1`、`top_edge_displacement=0.1`
- 网格：`mesh_size=5`
- 默认标识：`name=BiaxialPlate2D`、`step_name=BiaxialStep`、`job_name=biaxial_tension_2d`、`num_cpus=1`

分别确认水平和竖直位移，不把两者合成一个输入值。等双向加载时最大位移模可与两个方向位移的平方和开方进行数量级核对。

## 5. 三维路面移动荷载

- 模板：`configs/moving_load_road.json`
- 几何：`length=4000`、`width=2000`、`depth=600`
- 材料：`youngs_modulus=5000`、`poisson_ratio=0.35`、`density=2.4e-9`
- 轮载：`load_pressure=0.7`、`load_speed=10000`、`load_length=200`、`load_width=200`、`load_center_y=1000`
- 网格与时间：`mesh_size=200`、`max_time_increment=0.002`
- 默认标识：`name=MovingLoadRoad3D`、`step_name=MovingLoadStep`、`job_name=moving_load_road_3d`、`num_cpus=1`

必须先确认 Visual Studio、Intel Fortran Classic 与 Abaqus 版本匹配。速度 `10000 mm/s` 等于 `36 km/h`。接触区必须完整位于路面顶面，最大时间增量不能大于轮载经过自身长度所需时间的一半。该单层有限模型仅验证 DLOAD 流程，不能代替三级公路分层结构和规范设计。

## 通用校验边界

- 尺寸、弹性模量、载荷幅值和网格尺寸必须大于零；
- 泊松比必须位于 `-1 < ν < 0.5`；
- 网格尺寸不能大于模型最短边；
- 作业名必须以英文字母开头，只含字母、数字、下划线和短横线，最长 40 个字符；
- `num_cpus` 必须是大于等于 1 的整数；
- 单位名称会写入报告，但程序不会替用户完成隐式单位换算。
