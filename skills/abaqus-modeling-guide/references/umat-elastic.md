# 第六类模型：UMAT 三维线弹性材料

状态：新增实验性案例，尚未完成 Fortran 编译和 Abaqus 真机验证；不继承前五类案例的验证结论。通过配置校验不代表可以成功编译。

## 学什么

DLOAD 定义外部载荷如何变化，UMAT 定义材料应变变化后如何更新应力。这里用三维均匀小块拉伸学习材料子程序入口，不涉及混凝土损伤、塑性或开裂。

模板 `configs/umat_elastic.json`，类型 `umat_elastic`。默认 10×10×10 mm，E=30000 MPa，nu=0.2，右端位移 0.001 mm，网格尺寸 10 mm，C3D8 完全积分实体。材料参数仅为教学值。左右方向为 X；x=0 面 U1=0，y=0 面 U2=0，z=0 面 U3=0；其余侧向自由度可收缩。小变形静力，不使用壳/平面应力 UMAT。

当前校验限定 mm–MPa、0≤nu≤0.45、0<delta/L≤0.001，网格不能大于最短边。这些是该教学案例的使用范围，不是通用材料定律。

先确认对应版本的 Fortran 编译环境已配置。用户授权计算时说明会顺序提交两个作业，占用许可证：UMAT 和内置 Elastic 对照；任一步失败不生成成功报告。使用实际检测到的项目 Python：

```powershell
& "<检测到的项目 Python 绝对路径>" -m abaqus_codex validate --config configs/umat_elastic.json
& "<检测到的项目 Python 绝对路径>" -m abaqus_codex run --config configs/umat_elastic.json
```

代码阅读依次定位 `user_subroutines/elastic_umat.for.in` 中的 PROPS、DSTRAN、DDSDDE、STRESS 和 SSE：PROPS 传 E 与 nu；切线矩阵的剪切对角项使用 G，因为 UMAT 传入工程剪应变。这里只允许三维 NTENS=6。

## 预测和验证

默认理论应变=0.0001、轴向应力=3 MPa、右端反力=300 N。它们是理论值，不能充当实际结果。报告从实际 ODB 提取积分点平均 S11、左右 RF1，并与理论及内置材料对照；另有最大位移模和最大 Mises 应力。位移模包含侧向收缩，不能直接当 U1。

先比较应力与反力，再做位移加倍或 E 减半实验；变体必须仍在校验范围内。三维 UMAT 完整验证还需要剪切、体积变形、多轴、不同增量及版本测试。单次拉伸对照通过不等于材料子程序在任意情况下正确。

官方接口依据：[UMAT](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-umat.htm)。所用版本需另核对接口和编译器；项目现有版本限制继续生效。
