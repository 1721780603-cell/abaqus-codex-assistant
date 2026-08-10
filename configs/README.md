# 配置文件

`rectangle_tension.json` 是二维矩形板拉伸示例。

`plate_with_hole_tension.json` 是二维中心圆孔板拉伸示例，增加了孔半径和孔边局部网格尺寸。

`cantilever_bending.json` 是二维悬臂梁弯曲示例，左端固定，上边界施加竖直向下的均布载荷。

`biaxial_tension.json` 是二维方板双向拉伸示例，右边界和上边界分别施加正方向位移。

`moving_load_road.json` 是三维单层路面单轮移动载荷教学示例，使用 mm–MPa–s–tonne 一致单位制，并需要 Intel Fortran 编译 DLOAD。

前四个二维示例采用 mm–MPa 一致单位制。移动载荷示例中的参数是流程教学值，不是三级公路正式设计值。

`user_profile.json` 是用户本机的场景选择，已被 `.gitignore` 排除。配置中不得加入密码、许可证服务器凭据、API Key、Cookie 或论文数据库会话信息。
