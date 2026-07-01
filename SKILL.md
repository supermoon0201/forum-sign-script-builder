---
name: forum-sign-script-builder
description: Build or extend forum/community daily sign-in scripts in Python for repositories like QingLong automation projects. Use when Codex needs to add a new website sign script, refactor an existing sign script, choose between `httpx` and `nodriver`, handle Cloudflare/Turnstile/WAF/captcha/login flows, extract real sign-in/login APIs from HAR or frontend bundles, execute browser-side `fetch` inside a protected session, standardize env vars and notifications, or produce a script that follows existing repository conventions and reliably verifies real sign success rather than only login success or “already signed” status.
---

# Forum Sign Script Builder

实现新站点签到脚本时，先复用当前仓库已经验证过的套路，不要从零自由发挥。目标是产出一个可以长期运行、可定位失败原因、并且不会误报成功的脚本。

## 工作流

1. 先用 `fast-context` 搜索仓库内最相近的站点脚本，优先参考：
   - `right_sign.py`：纯 `httpx` 直连型
   - `nodeseek_sign_nodriver.py`：Cookie + Cloudflare 型
   - `onepoint3acres_sign_nodriver.py`：Turnstile + 页面状态校验型
   - `52pojie_sign_nodriver.py`：账号密码登录 + WAF 验证码型
   - `sehuatang_sign.py`：复杂验证码/回帖/签到组合型
2. 先判断站点模式，再选模板：
   - 只要接口可稳定复现、无需浏览器运行时上下文，优先 `httpx`
   - 遇到 Cloudflare、Turnstile、前端渲染态、浏览器指纹、人机验证、运行时 token，改用 `nodriver`
   - 如果直连请求 403/拦截，但浏览器里同接口 200，优先判断为“必须在浏览器受保护会话里发请求”，不要硬做 `httpx`
3. 先确认“权威成功信号”，再写签到逻辑：
   - 成功信号必须来自站点真实业务状态，例如用户积分页、已签到标记、已完成任务页、接口 JSON 字段、用户资料页余额
   - 不要把“按钮点击成功”“HTTP 200”“页面出现 success 字样”直接当成最终成功
   - 要区分“今天已签到”和“本次新签到成功”，不能把二者混成一个成功结论
4. 优先做可重复的最小闭环：
   - 登录态检查
   - 执行签到
   - 二次校验成功
   - 推送通知
5. 需要新脚本骨架时，运行 `scripts/init_site_sign.py`

## 强制约束

- 与用户交互用中文。
- 代码注释必须写中文。
- 任何作者信息统一写 `le.yang`。
- 文件命名遵守仓库风格：
  - `site_sign.py`：`httpx` 型
  - `site_sign_nodriver.py`：浏览器型
- 环境变量前缀使用站点缩写，全大写，例如 `NS_COOKIE`、`RIGHT_COOKIE`、`SHT_USERNAME`。
- 通知统一复用 Bark，可选环境变量固定为 `BARK_URL`。
- 若站点支持多账号，优先兼容 `&` 分隔；用户名/密码成对时必须校验数量一致。

## 实现规则

### 1. 先做站点勘察

至少确认这些问题：

- 登录方式是 Cookie 直注、账号密码登录，还是还要 2FA/TOTP。
- 签到是页面跳转、AJAX、`fetch`、表单提交，还是先做回帖/答题/验证码。
- 成功后的权威查询页面或接口是什么。
- 站点是否会返回“未签到”但文本里含“已签到”等误导性片段。
- 是否存在 Cloudflare、Turnstile、WAF、滑块、点选、旋转、图文验证码。
- 站点的登录接口和签到接口是否都要求验证码 token，还是只有其中一个要求。
- 前端是否把认证信息放在：
  - Cookie
  - `Authorization: Bearer <token>`
  - `localStorage` / `sessionStorage`
  - 运行时对象
- 直连接口是否被 Cloudflare / 站点风控拦截，而浏览器上下文里可以正常访问。
- 如果拿到的 HTML 标题是空、正文是乱码或像压缩流，要先确认是否是响应压缩解码问题，而不是急着判定站点改版。

### 2. 只选一种主骨架

不要把 `httpx` 和 `nodriver` 混成一个难维护的脚本，除非站点真的要求：

- `httpx` 型：页面和接口稳定、token 可直接提取、无强浏览器依赖
- `nodriver` 型：必须在真实浏览器里拿 Cookie、执行 JS、穿透风控或验证码
- 若接口只有在浏览器会话里才能成功，主骨架仍算 `nodriver`，即使真正的签到动作最终是 `fetch('/api/checkin')`

参考细节见：

- `references/patterns.md`
- `references/site-onboarding.md`
- 遇到页面乱码、动态表单字段、奖励金额提取、验证码重试等问题时，读 `references/debugging-sign-pages.md`
- 如果站点是 Turnstile + JSON API + Bearer Token 组合，额外看 `references/turnstile-sites.md`
- 如果站点是 **可见 Turnstile 复选框 + hidden input 回填 + 视觉点击不稳定 + 会弹 Cloudflare 错误遮罩**，额外看 `references/turnstile-visual-recovery.md`
- 如果站点是 **登录前 WAF / Probe，登录后再触发极验或点选，最终业务走 App API**，额外看 `references/browser-risk-sites.md`
- 如果准备使用 `scripts/init_site_sign.py --preset ...` 生成脚本，落地前额外看 `references/preset-playbooks.md`

### 3. 成功判断必须保守

优先级从高到低：

1. 站点业务 JSON 的布尔字段或状态字段
2. 重新打开权威页面后读取“已签到/已完成/余额增加”
3. 重新拉用户状态对象，例如 `window.__config__`、`__NEXT_DATA__`
4. 兜底文本匹配

补充经验：

- 有些站点的“已签到”页只给状态，不给本次奖励金额；这时奖励金额和最新余额应优先去账单页、积分流水页、余额页取，不要硬从签到页文案里猜。
- 如果“当前余额”与“今日奖励”都能从同一个权威流水页取到，优先统一从该页解析，减少跨页口径不一致。

额外约束：

- “登录成功”不等于“签到成功”
- “今天已签到”不等于“本次脚本完成了一次新的签到动作”
- 如果正式实跑命中“已签到”，结论必须明确写成“已签到验证通过”，不能宣称“已完成签到闭环”

禁止事项：

- 只靠 `HTTP 200` 判断成功
- 只靠按钮点击无异常判断成功
- 对“未签到/未登录/未验证”做模糊匹配，导致误判为成功

### 4. 风控处理要分层

- Cloudflare 5 秒盾：先等待，再模拟鼠标活动，再考虑刷新
- Turnstile：等待组件出现、点击、等待 token 生效、再刷新权威状态
- 如果页面现成 Turnstile 组件难以稳定接管，可以在同域页面里自渲染一个等价 Turnstile 组件拿 token，再把 token 送给真实业务接口
- WAF 图文验证码：先本地算法，再大模型，最后才放弃
- 验证码失败后要刷新挑战，不要无限重复提交旧答案

补充经验：

- 对 **可见 Turnstile 复选框** 场景，优先把“真实复选框小方框”与“大容器/文案区/标题区”分开；如果只命中了祖先容器，默认继续等待，不要直接点。
- 对 **hidden input 回填型 Turnstile**，优先把 `cf-turnstile-response` / `cf_chl_widget_*_response` 的值长度作为挑战成功信号，不要只看页面上是否出现动画或勾选态。
- 对 **视觉点击型 Turnstile**，识别到真实复选框后优先单击一次并等待，不要在同一轮里连续多点扫描；连续补点很容易把 challenge 点进错误遮罩。
- 若出现 `Cloudflare人机验证服务加载失败` 一类遮罩，优先把它当作“可恢复状态”，执行：识别 `OK/确定` → 关闭遮罩 → 刷新登录页或同域页 → 重建 challenge → 再次等待真实复选框。

滑块 / 旋转拼图补充经验：

- 对 **圆弧滑动 + 旋转拼图**，先逆前端运行规则：找 `guardword`/轨迹参数、滑块百分比 `p`、旋转角、轨迹圆心、拼图 CSS 尺寸和旋转中心；不要只做截图模板匹配。
- 若用户只关心轮廓，主判据就只用轮廓：边界命中率、双向 Chamfer 距离、膨胀边界 IoU、质心距离和角度距离；不要让内部纹理相关性主导结果。
- 截图像素与前端 CSS 像素可能不一致。用拼图截图尺寸反推 `coordinate_scale`，例如前端块为 `80px` 时，`scale=(piece_width+piece_height)/160`；旋转中心也用截图实际中心，而不是硬编码 `(40,40)`。否则 overlay 会明显滑不到槽位。
- 先做槽位预筛再评分：用拼图块面积、外接框长短边比例、宽高比过滤白云、飞鸟、高光、长线等背景伪轮廓；不要把所有白色轮廓都当候选槽。
- 候选质量要设门槛，避免误拖：例如 `hit_rate >= 0.70`、`border_iou >= 0.50`、`border_distance <= 1.20` 这类阈值；低质量候选直接刷新 challenge，不要为了“试试看”拖动。
- 每轮调试图分层保存：`visible_full/hidden_full/piece_full`、裁剪图、topN 轮廓 overlay、候选日志。overlay 只画槽位轮廓和拼图轮廓，避免内部图案误导判断。
- 状态机要处理“验证码 DOM 消失即已放行”的情况：每轮采样前、采样失败后、刷新后都先检查是否已离开验证页；不要因为拿不到旧 DOM 或旧 cookie 就误报失败。
- 对需要长期定时运行的脚本，默认不要无限保留中间图。提供 `KEEP_DEBUG` 与保留天数：调试时完整落盘，日常运行使用 runtime 临时目录并清理旧文件。
- 若目标是青龙/单文件部署，调通后把运行时 solver 合并进主脚本，避免部署时漏带 `research/` 辅助模块；研究脚本可以保留为备份，但正式脚本不要依赖它。
- 对 **前置 WAF + 登录极验** 的站点，必须把“WAF 已放行”和“登录验证码已通过”当成两个独立状态机；WAF 通过后先验证登录页 DOM 是否就绪，再开始填表单或发登录 AJAX。
- 对 **腾讯平移滑块**，优先尝试确定性精确拖动；先追求 `delta` 命中率，再考虑人类化轨迹。若随机抖动降低命中率，就默认关闭大幅随机扰动。
- 对 **登录极验 `risk_level2_3`**，若事件探针显示 `downs=1 / drag_moves>0 / ups=1`，但服务端稳定返回 `error_113` / `forbidden`，优先把它判成风控拒绝而不是纯偏移问题；这时不要盲目枚举大量 offset。
- 对 **登录验证码成功后还要调业务 API** 的站点，必须保存成功样本和回填参数快照，例如 challenge/validate/seccode、成功后页面状态、成功后 AJAX 返回；后续优先复用成功样本而不是重新猜策略。

### 5. 前端接口勘察规则

优先级如下：

1. HAR / 浏览器 Network 中的真实请求
2. 前端打包 JS 中对 `/api/...` 的调用代码
3. 页面 DOM / 文本

遇到打包前端时，至少确认：

- 登录接口路径、方法、请求体字段名
- 签到接口路径、方法、请求体字段名
- 状态接口路径、方法、返回字段
- 验证 token 字段名，例如 `verificationToken`、`recaptchaToken`
- 认证头来源，例如 `Authorization: Bearer <token>`

如果接口在浏览器里 200、脚本直连 403，要优先考虑：

- Cloudflare clearance 只能在浏览器态里生效
- 站点要求同源 `fetch`
- 登录后 token 只在浏览器运行时里存在
- 需要“浏览器内 `fetch` + 浏览器态 Cookie/Storage/JS 环境”

补充经验：

- 登录页表单字段不要假设字段名固定，也不要假设属性顺序固定；像 V2EX 这类站点会把用户名、密码、验证码字段名做成动态哈希，应该先解析真实 `<input>` 标签，再按 `type`、`placeholder`、`name` 语义识别字段。
- 如果需要提取页面文本做判断，先去掉 `<script>`、`style`、HTML 注释，再做文本匹配；否则很容易把内联脚本、广告脚本、模板字符串混进正文，污染日志与状态判断。
- 若站点返回压缩响应，优先确认运行环境是否具备对应解码能力；在青龙等最小环境里，必要时主动禁用 `br`，只保留 `gzip, deflate`，避免正文乱码导致整条登录/签到链路误判。

### 6. 日志与通知要可诊断

至少打印：

- 当前账号编号
- 登录态检查结果
- 关键接口路径与关键字段名
- 签到接口或页面反馈前 100~300 字符
- 权威校验结果
- 失败原因摘要
- 若只是命中“已签到”，要明确打印“未执行新的签到动作”
- 若登录页/状态页解析失败，要额外打印页面标题、关键响应头（至少 `content-encoding` / `content-type`）和前几十字节诊断信息，便于区分“站点改版”和“压缩解码异常”

通知内容至少包含：

- 站点名
- 成功 / 已签到 / 失败 / 结果未知
- 当前余额或积分（能拿到则带上）
- 今日签到奖励金额（能从权威页拿到则带上）
- 如果是“已签到”，通知文案要和“新签到成功”区分开

验证码/登录补充规则：

- 账号密码 + 图形验证码站点，默认至少支持有限次重试（如 2~3 次），每次重试都要重新获取登录页字段和新验证码，不能重复提交旧 `once` 或旧验证码答案。
- 验证码识别失败时，日志里要区分“字段解析失败”“验证码识别失败”“登录提交后校验未通过”三种阶段，避免把所有失败都归类为“登录失败”。
- 若验证码体系包含 **WAF 放行页 → 登录极验 → 业务 API** 三段链路，日志必须明确分段输出，至少区分：
  - `waf-not-passed`
  - `login-page-not-ready`
  - `risk-challenge-opened`
  - `risk-challenge-forbidden`
  - `ajax-login-success`
  - `api-checkin-success`
- 若登录滑块是浏览器端 canvas 差分题，默认保存 `bg/full/mask/overlay/trace` 五类调试产物，再允许继续调 offset；没有这些调试图时，不要盲改轨迹。

## 资源使用

### 模板

- `assets/templates/httpx_sign_template.py`
- `assets/templates/nodriver_sign_template.py`

### 脚手架

- `scripts/init_site_sign.py`

示例：

```powershell
python scripts/init_site_sign.py --site-name example --mode httpx --env-prefix EXAMPLE --output "C:\path\to\repo"
python scripts/init_site_sign.py --site-name example --mode nodriver --env-prefix EXAMPLE --output "C:\path\to\repo"
```

### 参考资料

- `references/patterns.md`：现有脚本共性、选型规则、命名规范
- `references/site-onboarding.md`：新增站点时的勘察与落地清单

## 交付标准

产出新站点脚本前，必须自检：

1. 是否沿用了仓库里已验证的结构，而不是发明全新风格。
2. 是否有中文注释。
3. 是否有 `Author: le.yang`。
4. 是否能解释为什么选 `httpx` 或 `nodriver`。
5. 是否实现了“执行动作后再二次校验”的权威成功判断。
6. 是否覆盖 Cookie 失效、验证码失败、接口异常、多账号边界。
7. 是否给出需要的环境变量列表。
8. 是否明确区分了“登录成功”“已签到”“本次新签到成功”三种结论。
9. 若站点需要浏览器态 `fetch`，是否避免误退化成 `httpx` 直连。
10. 若新增了验证码/图像求解辅助模块，正式交付是否已确认部署形态：单文件脚本应内联运行时求解代码；多文件脚本应明确列出必须同步部署的辅助文件。

如果时间允许，优先用测试账号或临时输出做最小验证；如果无法实跑，必须明确缺少什么前提。
