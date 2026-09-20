# 土木工程接触选型

用户询问接触、界面、粘结、支座、钢筋或土—结构相互作用时使用本页。先帮助判断物理关系，不直接生成接触代码，也不把教学假设当成工程参数。

## 先问清四件事

1. 两侧是同一个连续零件，还是两个独立部件？
2. 界面是否允许张开、闭合或脱空？
3. 界面是否允许切向滑移，摩擦数据来自哪里？
4. 界面是否会粘结、损伤、脱粘，或者只需整体连接刚度？

还需确认 Abaqus/Standard 或 Abaqus/Explicit、单位制、初始间隙/过盈和主要验收量。每次只追问一个尚未回答、且会改变选型的问题。

## 选型表

| 真实物理关系 | 优先考虑 | 土木例子 | 不能忽略的限制 |
|---|---|---|---|
| 单一连续网格，没有独立界面 | 不创建接触 | 整体浇筑梁、单块板 | 检查是否存在意外缝隙或重复面 |
| 两部件永久粘牢，不允许相对运动 | Tie | 理想湿接缝、不研究滑移的钢板—混凝土 | Tie 会阻止开裂、脱空和滑移；它是约束，不是普通接触 |
| 细长构件埋在实体中并假定完全粘结 | Embedded Region | 理想粘结钢筋—混凝土 | 拔出、锚固破坏和粘结滑移不能用理想嵌入 |
| 两个已知表面会开闭或滑移 | Surface-to-surface contact | 基础—土、桩—土、衬砌—围岩、梁端—支座 | 需要法向、切向、滑移方式和初始间隙；摩擦系数必须有来源 |
| 很多潜在接触、自接触或碰撞 | General Contact | 块体碰撞、倒塌、碎片、复杂装配 | 仍要检查/排除不应接触的区域；简单单界面不必一律使用 |
| 初始粘结但会损伤、开裂或脱粘 | Cohesive contact | FRP—混凝土、新老混凝土、层间剥离 | 需要界面刚度、强度、损伤起始和断裂能；有明确胶层厚度时考虑 cohesive elements |
| 只关心连接的整体自由度、刚度或间隙 | Connector / Spring / Coupling | 支座、弹簧、阻尼器、铰、整体螺栓 | 局部承压、滑移和脱空需要表面接触或局部精细模型 |

普通承压接触可从 Hard contact、允许分离开始；Abaqus 默认切向无摩擦。可能发生明显相对滑动或转动时优先有限滑移，小滑移只用于相对运动确实很小的场景。不要把 Rough friction、Tie 或额外边界条件作为“让模型收敛”的通用补丁。

## 回答格式

先输出：

- 推荐类型与一句物理理由；
- 当前假设；
- 仍缺的参数及其数据来源；
- 建模后要检查的量，例如接触压力、开闭状态、滑移、剪切传力、反力平衡、界面损伤和能量；
- 当前项目能否执行，还是只能整理为后续开发任务。

若用户要求实际创建接触，必须明确说明当前白名单执行器尚未支持任意接触写入；可以形成结构化需求，但不能声称已修改 Abaqus。教学值不能直接用于生产设计。

## 官方依据

- [About Contact Interactions](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEITNRefMap/simaitn-c-contactoverview.htm)
- [About Mechanical Contact Properties](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEITNRefMap/simaitn-c-contactmechanical.htm)
- [Defining tie constraints](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-t-itnhelptied.htm)
- [Contact Cohesive Behavior](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEITNRefMap/simaitn-c-cohesivebehavior.htm)
