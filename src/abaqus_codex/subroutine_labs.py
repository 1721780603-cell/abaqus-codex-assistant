"""Fixed, inspectable Abaqus/Standard user-subroutine teaching labs.

Export only: no Abaqus process or license is started by this module.
"""

from __future__ import annotations

from pathlib import Path


LABS = (
    "disp_ramp", "dflux_wall", "film_wall", "usdfld_elastic",
    "uvarm_stress_ratio", "uexpan_thermal_bar", "hetval_heated_wall",
)

# 中文标题只用于导出说明，不改变输入文件和子程序的物理参数。
LAB_TITLES = {
    "disp_ramp": "DISP：逐渐施加轴向位移",
    "dflux_wall": "DFLUX：墙面热流",
    "film_wall": "FILM：墙面对流换热",
    "usdfld_elastic": "USDFLD：场变量控制弹性模量",
    "uvarm_stress_ratio": "UVARM：输出应力比",
    "uexpan_thermal_bar": "UEXPAN：杆件自由热膨胀",
    "hetval_heated_wall": "HETVAL：墙内恒定体积热源",
}


def _truss(material: str, load: str, output: str = "U, RF",
           element_output: str = "S, E") -> str:
    return ("*HEADING\nTwo-node axial truss teaching lab\n"
            "*NODE\n1, 0., 0.\n2, 100., 0.\n"
            "*ELEMENT, TYPE=T2D2, ELSET=BAR\n1, 1, 2\n"
            "*SOLID SECTION, ELSET=BAR, MATERIAL=STEEL\n10.\n"
            "*MATERIAL, NAME=STEEL\n" + material +
            "*BOUNDARY\n1, 1, 2, 0.\n2, 2, 2, 0.\n"
            "*STEP, NAME=AXIAL, NLGEOM=NO\n*STATIC\n0.1, 1.0\n" + load +
            "*OUTPUT, FIELD\n*NODE OUTPUT\n" + output + "\n"
            "*ELEMENT OUTPUT\n" + element_output +
            "\n*END STEP\n")


def _wall(load: str, extra_material: str = "") -> str:
    # C3D8/DC3D8 face S4 consists of nodes 2,3,7,6 (x=0.1 m).
    return ("*HEADING\nOne-element steady heat-conduction teaching lab\n"
            "*NODE\n1, 0., 0., 0.\n2, 0.1, 0., 0.\n"
            "3, 0.1, 1., 0.\n4, 0., 1., 0.\n"
            "5, 0., 0., 1.\n6, 0.1, 0., 1.\n"
            "7, 0.1, 1., 1.\n8, 0., 1., 1.\n"
            "*ELEMENT, TYPE=DC3D8, ELSET=WALL\n1, 1,2,3,4,5,6,7,8\n"
            "*SOLID SECTION, ELSET=WALL, MATERIAL=THERMAL\n"
            "*MATERIAL, NAME=THERMAL\n*CONDUCTIVITY\n10.\n" + extra_material +
            "*BOUNDARY\n1, 11, 11, 20.\n4, 11, 11, 20.\n"
            "5, 11, 11, 20.\n8, 11, 11, 20.\n"
            "*STEP, NAME=STEADY\n*HEAT TRANSFER, STEADY STATE\n"
            "0.1, 1.0\n" + load +
            "*OUTPUT, FIELD\n*NODE OUTPUT\nNT, RFL\n"
            "*ELEMENT OUTPUT\nHFL\n*END STEP\n")


INPUTS = {
    "disp_ramp": (
        _truss("*ELASTIC\n210000., 0.3\n",
               "*BOUNDARY, USER\n2, 1, 1, 0.1\n"),
        _truss("*ELASTIC\n210000., 0.3\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n"),
        "disp_ramp.for", "节点 2 的 U1=0.1 mm；S11=210 MPa；单端反力幅值=2100 N。",
        "mm、N、MPa；截面积 10 mm²；杆长 100 mm；规定轴向位移 0.1 mm。"
    ),
    "dflux_wall": (
        _wall("*DFLUX\n1, S4NU, 1000.\n"),
        _wall("*DFLUX\n1, S4, 1000.\n"),
        "dflux_wall.for", "右面温度=30 °C；热流幅值=1000 W/m²（另核对方向）。",
        "m、W、s、°C；导热系数 10 W/(m·K)；左面 20 °C；右面输入热流 1000 W/m²。"
    ),
    "film_wall": (
        _wall("*BOUNDARY, OP=MOD\n1, 11, 11, 100.\n"
              "4, 11, 11, 100.\n5, 11, 11, 100.\n"
              "8, 11, 11, 100.\n*FILM\n1, F4NU, 20., 100.\n"),
        _wall("*BOUNDARY, OP=MOD\n1, 11, 11, 100.\n"
              "4, 11, 11, 100.\n5, 11, 11, 100.\n"
              "8, 11, 11, 100.\n*FILM\n1, F4, 20., 100.\n"),
        "film_wall.for", "右面温度=60 °C；向外热流=4000 W/m²。",
        "m、W、s、°C；导热系数 10 W/(m·K)；左面 100 °C；环境 20 °C；换热系数 100 W/(m²·K)。"
    ),
    "usdfld_elastic": (
        _truss("*ELASTIC, DEPENDENCIES=1\n210000., 0.3, 0., 0.\n"
               "105000., 0.3, 0., 1.\n*USER DEFINED FIELD\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n", element_output="S, E, FV"),
        _truss("*ELASTIC\n105000., 0.3\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n"),
        "usdfld_elastic.for", "FV1=1；S11=105 MPa；单端反力幅值=1050 N。",
        "mm、N、MPa；截面积 10 mm²；杆长 100 mm；场变量为 1 时 E=105000 MPa。"
    ),
    "uvarm_stress_ratio": (
        _truss("*ELASTIC\n210000., 0.3\n*USER OUTPUT VARIABLES\n1\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n", element_output="S, E, UVARM"),
        _truss("*ELASTIC\n210000., 0.3\n",
               "*BOUNDARY\n2, 1, 1, 0.1\n"),
        "uvarm_stress_ratio.for",
        "S11=210 MPa；UVARM1=S11/(210 MPa)=1；内置对照的 S11 也应为 210 MPa。",
        "mm、N、MPa；截面积 10 mm²；杆长 100 mm；E=210000 MPa；U1=0.1 mm。"
    ),
    "uexpan_thermal_bar": (
        _truss("*ELASTIC\n210000., 0.3\n*EXPANSION, USER\n"
               "*INITIAL CONDITIONS, TYPE=TEMPERATURE\n1, 20.\n2, 20.\n",
               "*TEMPERATURE\n1, 70.\n2, 70.\n"),
        _truss("*ELASTIC\n210000., 0.3\n*EXPANSION\n1.0E-5\n"
               "*INITIAL CONDITIONS, TYPE=TEMPERATURE\n1, 20.\n2, 20.\n",
               "*TEMPERATURE\n1, 70.\n2, 70.\n"),
        "uexpan_thermal_bar.for",
        "自由端 U1=alpha × 50 °C × 100 mm=0.05 mm；S11 约为 0。",
        "mm、N、MPa、°C；热膨胀系数 1e-5 /°C；温度从 20 升至 70 °C；右端轴向自由。"
    ),
    "hetval_heated_wall": (
        _wall("", extra_material="*HEAT GENERATION\n"),
        _wall("*DFLUX\n1, BF, 1000.\n"),
        "hetval_heated_wall.for",
        "右面温度=20.5 °C；单元平均热流 HFL1=-50 W/m²。",
        "m、W、s、°C；导热系数 10 W/(m·K)；左面 20 °C；体积热源 1000 W/m³；右面绝热。"
    ),
}


def _lab_readme(name: str, filename: str, theory: str, units: str) -> str:
    """给初学者提供人工确认后的操作步骤，不生成可自动执行的脚本。"""
    return (
        "# {0}\n\n案例标识：`{1}`\n\n".format(LAB_TITLES[name], name) +
        "## 当前状态\n\n"
        "仅导出了实验文件，没有启动 Abaqus、占用许可证或运行 Fortran。"
        "此案例尚未完成真实 Abaqus/Fortran 验证，不能据此宣称计算正确。\n\n"
        "## 文件用途\n\n"
        "- `user.inp`：调用用户子程序的教学模型。\n"
        "- `reference.inp`：不调用用户子程序的内置功能对照模型。\n"
        "- `{0}`：可检查的 Fortran 源码。\n".format(filename) +
        "- `verification.md`：人工填写的验证记录，默认所有项目均未核对。\n\n"
        "## 输入与理论参考\n\n"
        "以下为固定教学参数和理论预期，不是本机计算结果：\n\n"
        "- 单位与参数：{0}\n- 理论预期：{1}\n\n".format(units, theory) +
        "反力比较必须记录节点、方向和正负号，不能把全模型求和当单端反力。"
        "传热案例核对温度与热流，不能套用位移或应力报告。\n\n"
        "## 人工确认后再求解\n\n"
        "1. 先核对输入文件、单位和假设；确认目标 Abaqus 年份、启动命令、"
        "许可证及匹配的 Fortran 编译环境。检测到安装不代表已经验证兼容。\n"
        "2. 在此实验目录打开 PowerShell。将下面占位路径替换成你已核对的"
        " Abaqus 启动命令绝对路径，不要直接复制别人的安装路径。\n"
        "3. 确认愿意占用许可证后，手动运行用户子程序作业；查看状态和日志，"
        "再手动运行对照作业。失败时先排查，不连续自动重试。\n\n"
        "```powershell\n"
        "$AbaqusCommand = '<已核对的 Abaqus 启动命令绝对路径>'\n"
        "& $AbaqusCommand job=user input=user.inp user={0} interactive\n".format(filename) +
        "```\n\n"
        "检查上一个作业后，再单独执行：\n\n"
        "```powershell\n"
        "& $AbaqusCommand job=reference input=reference.inp interactive\n"
        "```\n\n"
        "已有 `user.*` 或 `reference.*` 计算结果时，不在原目录重复提交；"
        "重新导出到新目录，保留原始证据。\n\n"
        "## 怎样判断是否通过\n\n"
        "分别检查两次作业的 `.sta`、`.msg`、`.dat`、`.log` 中实际产生的文件，"
        "确认编译/链接与求解状态，并核对 ODB 的分析步、结束时间和最终帧。"
        "有 ODB 或云图不代表分析完成。\n\n"
        "把实际结果、取值位置、单位、与理论/内置对照的差异填写到"
        " `verification.md`；误差容限需事先说明依据，不设通用通过百分比。"
        "理论接近零时应报告绝对误差，不能除以零计算相对误差。\n\n"
        "本程序不会自动读取本实验的 ODB、填写验证结果或标记通过。"
        "教学模型不代表工程设计，验证通过也不能直接推广到复杂构件。"
        "记录默认留在本机；共享前删除个人路径、许可证信息及凭据，"
        "不要上传商业软件、CAE 或 ODB 大文件。\n"
    )


def _verification_record(name: str) -> str:
    """只生成空白人工记录，避免将导出成功误写成求解或验证成功。"""
    return (
        "# 验证记录：{0}\n\n".format(LAB_TITLES[name]) +
        "案例标识：`{0}`\n\n".format(name) +
        "状态：未运行 / 未核对（由验证者依据证据手动更新）。\n\n"
        "## 本次环境\n\n"
        "- 日期：待填写\n"
        "- 应用版本 / 源码提交：待填写\n"
        "- 项目 Python 版本：待填写\n"
        "- Abaqus 年份及补丁：待填写\n"
        "- 启动命令已核对到目标版本：未核对\n"
        "- 操作系统、Fortran 和 Visual Studio 版本：待填写\n"
        "- 输入是否修改（若修改请列出）：待填写\n"
        "- 单位制与模型假设：待填写\n\n"
        "## 作业证据\n\n"
        "| 检查项 | 用户子程序 user | 内置对照 reference |\n"
        "|---|---|---|\n"
        "| 作业状态 | 未运行 | 未运行 |\n"
        "| Fortran 编译/链接 | 未核对 | 不适用 |\n"
        "| 求解完成证据（日志文件名及关键行） | 待填写 | 待填写 |\n"
        "| 本次 ODB、分析步、最终帧时间 | 待填写 | 待填写 |\n"
        "| 输出变量及取值位置 | 待填写 | 待填写 |\n\n"
        "## 数值核对\n\n"
        "按 README 的理论参考逐项添加记录；不要将理论值填作实际结果。\n\n"
        "| 变量、位置与单位 | 理论预期 | user 实测 | reference 实测 | 误差及容限依据 | 结论 |\n"
        "|---|---|---|---|---|---|\n"
        "| 待填写 | 待填写 | 未提取 | 未提取 | 待填写 | 未核对 |\n\n"
        "## 结论与下一步\n\n"
        "- 编译与作业流程：未核对\n"
        "- 与理论及内置对照的一致性：未核对\n"
        "- 网格/增量敏感性：未检查\n"
        "- 物理验证（实验或独立证据）：未完成\n"
        "- 失败项、缺失证据与下一步：待填写\n\n"
        "记录不自动上传；对外分享前脱敏，不能包含许可证、账号或密钥。\n"
    )


def export_lab(name: str, destination: Path) -> Path:
    """Create a new lab directory; refuse to merge into existing user data."""
    if name not in INPUTS:
        raise ValueError("Unknown lab: {0}; choose from {1}".format(name, ", ".join(LABS)))
    if destination.exists():
        raise FileExistsError("实验目录已存在，请选择新目录：{0}".format(destination))
    source = Path(__file__).resolve().parent / "user_subroutines" / INPUTS[name][2]
    if not source.is_file():
        raise FileNotFoundError("缺少子程序模板：{0}".format(source))
    generated, reference, filename, theory, units = INPUTS[name]
    destination.mkdir(parents=True)
    (destination / "user.inp").write_text(generated, encoding="ascii", newline="\n")
    (destination / "reference.inp").write_text(reference, encoding="ascii", newline="\n")
    (destination / filename).write_text(source.read_text(encoding="ascii"),
                                        encoding="ascii", newline="\n")
    (destination / "README.md").write_text(
        _lab_readme(name, filename, theory, units),
        encoding="utf-8", newline="\n")
    (destination / "verification.md").write_text(
        _verification_record(name),
        encoding="utf-8", newline="\n")
    return destination
