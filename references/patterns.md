# 现有脚本模式总结

## 1. 先选技术路线

### `httpx` 型

适用特征：

- 签到接口可直接请求
- 页面 token 可从 HTML 正则提取
- 没有强制浏览器环境
- 不依赖前端运行时对象或 JS 挑战

仓库样本：

- `right_sign.py`

固定结构：

1. 读取环境变量
2. 构造 `httpx.AsyncClient`
3. 访问首页或资料页提取 `formhash`、UID、用户名、余额
4. 调签到接口
5. 再次访问权威页面刷新余额或连签状态
6. Bark 通知

### `nodriver` 型

适用特征：

- 需要真实浏览器执行 JS
- 站点有 Cloudflare / Turnstile / WAF / 复杂验证码
- 登录态需注 Cookie 或账号密码登录
- 成功状态来自浏览器运行时对象、DOM、前端接口
- 真实业务接口只能在浏览器会话里成功访问，离开浏览器上下文就 403 / 风控拦截
- 登录后认证信息除 Cookie 外，还依赖 `Authorization`、`localStorage`、`sessionStorage` 或前端运行时状态

仓库样本：

- `nodeseek_sign_nodriver.py`
- `onepoint3acres_sign_nodriver.py`
- `52pojie_sign_nodriver.py`
- `sehuatang_sign.py`

固定结构：

1. 读取环境变量
2. 启动浏览器，必要时加 Xvfb
3. 进入首页
4. 注入 Cookie 或执行登录
5. 处理 Cloudflare / Turnstile / WAF
6. 在浏览器上下文里执行真实业务动作（页面点击或浏览器内 `fetch`）
7. 重新读取权威状态
8. Bark 通知
9. 清理浏览器

## 2. 环境变量命名规则

- 站点前缀统一大写，例如 `RIGHT_`、`NS_`、`SHT_`
- 常见字段：
  - `PREFIX_COOKIE`
  - `PREFIX_USERNAME`
  - `PREFIX_PASSWORD`
  - `PREFIX_HEADLESS`
  - `PREFIX_DOMAIN`
  - `BARK_URL`
  - `CHROMIUM_PATH`
  - `LLM_API_BASE`
  - `LLM_API_KEY`
  - `LLM_MODEL`

多账号经验：

- 单一 Cookie 多账号：优先 `&` 分隔
- 用户名密码成对：必须校验数量一致
- 若密码可能含 `&`、`%`、`!` 等特殊字符，多账号优先用 JSON 数组，不要盲目按 `&` 分隔
- 多账号执行之间加随机等待，降低风控风险

## 3. 成功判断的真实经验

### 必须做权威复核

正确做法：

- `right_sign.py`：签到后再次拉积分页刷新恩山币
- `nodeseek_sign_nodriver.py`：签到后回到首页读取 `window.__config__.user.coin`
- `onepoint3acres_sign_nodriver.py`：刷新后重读 `__NEXT_DATA__`
- `52pojie_sign_nodriver.py`：访问已完成任务页验证今日签到记录
- `sehuatang_sign.py`：接口返回 + 页面余额双重视角

### 常见误判来源

- “未签到”里包含“签到”两个字
- JSON 文本里有 `"success"` 字段名，但布尔值其实是 `false`
- HTTP 200 只是接口可达，不代表业务成功
- 按钮点击成功，不代表 Turnstile token 已生成
- 登录成功，不代表签到成功
- 命中“今天已签到”，不代表脚本验证了“新签到动作”
- `amount` / `current` / `balance` 等字段语义可能不同，不要看名字就下结论

## 4. 风控与验证码处理策略

### Cloudflare

- 用 `outerHTML` 判定，不要只看 `innerText`
- 等待数轮，期间模拟鼠标移动
- 停留过久时刷新页面

### Turnstile

- 先找容器或 iframe
- 滚动进视口再点击
- 点击后等待 token 生效
- 最终用业务状态复核

进阶策略：

- 如果页面现成组件在 Shadow DOM、弹窗、闭包组件里难以稳定接管，可以在同域页面里自渲染一个新的 Turnstile 组件拿 token
- token 到手后优先走真实业务接口，而不是继续赌页面按钮状态
- 登录和签到可能分别需要不同 action 的 token，要分别验证，不要复用旧 token 假设它通用

### 图文/滑块/旋转验证码

- 优先本地算法，如 OpenCV、ddddocr
- 本地失败再降级大模型
- 旧验证码失败后要刷新挑战
- 提交答案前要做格式校验，例如 click 坐标范围

## 5. 代码风格要求

- 注释写中文
- 作者统一 `le.yang`
- 函数拆分清晰，按“配置 / 辅助函数 / 核心业务 / 主流程”组织
- 失败路径要打印可诊断信息
- 最终通知要包含站点名和摘要

## 6. `nodriver` 型新增推荐函数

- `browser_fetch`：在浏览器上下文里发起 `fetch`，复用 Cloudflare clearance、Cookie、Storage 与同源环境
- `get_verification_site_key`：从公开设置接口读取验证码配置，而不是把 siteKey 硬编码死
- `solve_turnstile_token`：统一处理 Turnstile 的渲染、点击、轮询 token、错误码输出
- `fetch_status_before_action` / `fetch_status_after_action`：把“动作前状态”和“动作后状态”明确拆开

## 7. 新增结论分级建议

脚本最终结论建议严格分成：

- `success`：本次确实完成了新的签到动作，且权威状态复核成功
- `already`：权威状态显示今天已签到，但本次没有执行新的签到动作
- `failed`：执行失败或复核失败
- `unknown`：接口返回或页面状态不够确定
