# -*- coding: utf-8 -*-
"""面向土木工程初学者的接触选型教学，不执行 Abaqus 写操作。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContactScenario:
    """一个可复用、可测试的接触选型场景。"""

    key: str
    title: str
    examples: str
    recommendation: str
    reason: str
    avoid: str
    inputs: tuple[str, ...]
    checks: tuple[str, ...]


CONTACT_SCENARIOS = (
    ContactScenario(
        key="single_body",
        title="一个连续零件，没有独立界面",
        examples="整体浇筑梁、单块板、连续路面体",
        recommendation="不创建接触",
        reason="同一连续网格中的相邻单元已经通过公共节点传力。",
        avoid="不要为了“看起来完整”再加 Tie 或接触，否则可能重复约束。",
        inputs=(),
        checks=("确认几何确实连通", "检查是否存在未合并的小缝或重复面"),
    ),
    ContactScenario(
        key="perfect_bond",
        title="两个部件永久粘牢，不允许开裂或滑移",
        examples="不研究界面失效的钢板—混凝土、预制构件理想湿接缝",
        recommendation="Tie 约束（它是约束，不是普通接触）",
        reason="Tie 可把不匹配网格的两个表面绑定，界面不发生相对运动。",
        avoid="若研究脱空、滑移、开裂或粘结退化，不要使用 Tie。",
        inputs=("主/从表面", "位置容差", "是否调整初始间隙", "是否约束转动自由度"),
        checks=("未绑定节点警告", "初始间隙是否被意外消除", "界面附近应力突变"),
    ),
    ContactScenario(
        key="embedded_rebar",
        title="细长构件埋在实体中，并假定完全粘结",
        examples="钢筋—混凝土的理想粘结、加筋体的理想锚固",
        recommendation="Embedded Region（嵌入区域）",
        reason="嵌入节点的运动由宿主实体插值控制，适合不研究粘结滑移的钢筋。",
        avoid="钢筋拔出、锚固破坏或界面滑移问题不能用理想嵌入代替。",
        inputs=("宿主区域", "嵌入区域", "容差/是否允许部分嵌入"),
        checks=("钢筋是否全部落在宿主内", "是否出现未嵌入节点", "钢筋与混凝土网格是否合理"),
    ),
    ContactScenario(
        key="pair_contact",
        title="已知两表面会接触，允许分离或滑移",
        examples="基础—土体、桩—土、衬砌—围岩、梁端—支座、干接缝",
        recommendation="Surface-to-surface contact（接触对）",
        reason="接触区域明确时，可单独控制法向、摩擦、滑移方式和输出。",
        avoid="不要凭经验随手填写摩擦系数；Tie 也不能替代会开闭或滑移的界面。",
        inputs=("两个接触面", "法向行为", "摩擦系数或切向规律", "有限/小滑移", "初始间隙或过盈"),
        checks=("接触方向和初始穿透", "CPRESS/开闭状态", "滑移与剪切传力", "反力平衡和收敛"),
    ),
    ContactScenario(
        key="general_contact",
        title="接触对象很多、位置事先难以逐对确定或存在自接触",
        examples="块体碰撞、落石防护、构件倒塌、碎片、复杂装配碰撞",
        recommendation="General Contact（通用接触）",
        reason="它能用较少的配对定义覆盖多个外表面及自接触，Explicit 中尤其常用。",
        avoid="简单的单一界面不必一律使用通用接触；仍要排除不应接触的区域。",
        inputs=("Standard 或 Explicit", "接触域/排除项", "默认与局部接触属性", "厚度和初始间隙"),
        checks=("意外接触对", "穿透与稳定时间步", "接触能量", "接触力路径"),
    ),
    ContactScenario(
        key="cohesive_interface",
        title="界面开始粘结，但可能逐渐损伤、脱粘或开裂",
        examples="新老混凝土界面、胶层、FRP—混凝土、层间剥离、节段胶接缝",
        recommendation="Cohesive contact；胶层有明确厚度时考虑 cohesive elements",
        reason="黏聚模型用牵引—分离关系描述界面刚度、损伤起始和断裂能。",
        avoid="缺少界面强度、刚度和断裂能时，不应靠默认值给出工程结论。",
        inputs=("界面初始状态", "法/切向刚度", "损伤起始准则", "断裂能/损伤演化", "失效后摩擦"),
        checks=("损伤变量", "开裂位移", "界面耗散能", "网格和黏性稳定敏感性"),
    ),
    ContactScenario(
        key="simplified_connection",
        title="只关心连接的整体刚度、间隙或某几个自由度",
        examples="桥梁支座简化、弹簧、阻尼器、螺栓或铰的整体模型",
        recommendation="Connector / Spring / Coupling；细部承压才建立表面接触",
        reason="连接器直接表达自由度关系，常比画出全部接触细节更适合整体结构模型。",
        avoid="不要把连接器和真实接触重复叠加；局部承压、滑移和脱空需要细化模型。",
        inputs=("允许和约束的自由度", "刚度/阻尼/间隙", "连接点或耦合面", "失效规律"),
        checks=("连接器力和位移", "整体反力", "是否过约束", "局部模型适用性"),
    ),
)

_SCENARIOS_BY_KEY = {scenario.key: scenario for scenario in CONTACT_SCENARIOS}


def recommend_contact(key: str) -> ContactScenario:
    """按稳定键返回教学建议；未知场景必须显式失败。"""

    try:
        return _SCENARIOS_BY_KEY[key]
    except KeyError as error:
        raise ValueError("未知接触教学场景：{0}".format(key)) from error


def format_contact_selection_guide() -> str:
    """生成适合只读窗口展示的接触决策树和土木场景卡片。"""

    lines = [
        "土木工程新手：接触怎么选",
        "本页只帮助选型，不会修改 Abaqus 模型。",
        "先判断真实界面会不会开、会不会滑、会不会损伤，再选择功能。",
        "",
        "一分钟决策树",
        "1. 只有一个连续零件？→ 不创建接触。",
        "2. 两个部件永远粘牢，绝不允许相对运动？→ Tie。",
        "3. 钢筋埋在混凝土里，并假定完全粘结？→ Embedded Region。",
        "4. 已知两个面会开闭或滑移？→ Surface-to-surface contact。",
        "5. 接触对象很多、会碰撞或自接触？→ General Contact。",
        "6. 初始粘结但会脱粘/开裂？→ Cohesive contact；有实体胶层时考虑 cohesive elements。",
        "7. 只模拟支座、弹簧、铰或阻尼器的整体自由度？→ Connector / Spring / Coupling。",
        "",
        "法向与切向的基础判断",
        "• 普通承压接触常从 Hard contact + 允许分离开始。",
        "• Abaqus 默认切向是无摩擦；需要摩擦时必须说明摩擦系数来源并做敏感性分析。",
        "• 可能发生明显相对滑动或转动时用有限滑移；小滑移只用于运动确实很小的情况。",
        "• 接触不是边界条件：模型仍需消除刚体运动，但不要重复约束界面。",
        "",
    ]
    for index, scenario in enumerate(CONTACT_SCENARIOS, start=1):
        lines.extend(
            [
                "场景 {0}｜{1}".format(index, scenario.title),
                "土木例子：" + scenario.examples,
                "建议：" + scenario.recommendation,
                "为什么：" + scenario.reason,
                "不要这样做：" + scenario.avoid,
                "建模前要问：" + ("、".join(scenario.inputs) if scenario.inputs else "无额外接触参数"),
                "建模后要查：" + "、".join(scenario.checks),
                "",
            ]
        )
    lines.extend(
        [
            "新手提交给 Codex 的推荐描述",
            "请先不要建模。对象是【两个部件】，界面可能【分离/滑移/损伤】，",
            "分析使用【Standard/Explicit】，材料与单位制是【……】。",
            "请先说明推荐 Tie、嵌入、接触对、通用接触、黏聚界面或连接器中的哪一种，",
            "列出仍缺少的参数、假设和验收输出；我确认后再生成修改计划。",
            "",
            "工程提醒：接触、摩擦和界面损伤会显著影响结果与收敛。教学默认值不能直接用于设计。",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "CONTACT_SCENARIOS",
    "ContactScenario",
    "format_contact_selection_guide",
    "recommend_contact",
]
