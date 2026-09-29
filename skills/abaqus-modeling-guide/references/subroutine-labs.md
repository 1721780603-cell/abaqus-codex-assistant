# 七个子程序教学实验

第 7–13 类通过 `abaqus-codex subroutine-lab --model <名称> --output <新的目录>` 导出固定实验包。导出仅写入新目录，不启动 Abaqus。实验包内有 `user.inp`、`reference.inp`、对应 `.for` 和 `README.md`。已有同名目录会报错，避免覆盖用户计算。

| 编号 | 名称 | 子程序 | 学什么 | 理论末帧对照 |
|---:|---|---|---|---|
| 7 | `disp_ramp` | DISP | 轴向位移从 0 渐增到 0.1 mm | 100 mm 杆、E=210000 MPa，S11=210 MPa，反力 2100 N |
| 8 | `dflux_wall` | DFLUX | x=0.1 m 表面输入 1000 W/m² 热流 | 左面 20 °C、k=10 W/(m K)，右面 30 °C |
| 9 | `film_wall` | FILM | 热端 100 °C、右面对 20 °C 环境换热 | h=100 W/(m² K)，右面 60 °C，热流 4000 W/m² |
| 10 | `usdfld_elastic` | USDFLD | 材料点场变量为 1 时 E 从 210000 变为 105000 MPa | S11=105 MPa，反力 1050 N，FV1=1 |
| 11 | `uvarm_stress_ratio` | UVARM | 读取计算得到的 S11 并输出无量纲应力比 | S11=210 MPa，UVARM1=S11/210=1 |
| 12 | `uexpan_thermal_bar` | UEXPAN | 20→70 °C 温升产生自由热膨胀 | 右端 U1=0.05 mm，S11 约为 0 |
| 13 | `hetval_heated_wall` | HETVAL | 恒定体积热源在一侧恒温、一侧绝热墙体中产生温升 | 右面 20.5 °C；单元平均 HFL1=-50 W/m² |

7、10、11、12 是二节点桁架，8、9、13 是单个 DC3D8 导热单元；它们是最小化接口实验，并不是实际建筑构件。`USDFLD` 案例只演示常量场变量对应的弹性模量表，不模拟损伤或历史依赖。`HETVAL` 案例不是实际水泥水化动力学模型。热传导的温度和热流不能拿力学应力报告解释。

七个实验需要 Abaqus/Standard、匹配的 Fortran 编译器和许可证。导出后先检查输入与单位，再按包内 README 确认是否求解。求解时先执行 user job，再执行 reference job，分别检查作业结束状态与 ODB 最后帧，比较理论值、数值值和对照值。这里没有真机求解证据，所以不能报告“已经通过验证”。

关键字及接口依据：Abaqus 官方 [DISP](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-disp.htm)、[DFLUX](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-dflux.htm)、[FILM](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-film.htm)、[USDFLD](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-usdfld.htm)、[UVARM](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-uvarm.htm)、[UEXPAN](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-uexpan.htm)、[HETVAL](https://docs.software.vt.edu/abaqusv2025/English/SIMACAESUBRefMap/simasub-c-hetval.htm)。
