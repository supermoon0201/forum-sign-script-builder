# Turnstile 站点接入专项参考

这个参考文件只针对一类站点：

- 登录接口或签到接口需要 `verificationToken`
- 站点启用了 Cloudflare Turnstile
- 直连脚本容易 403 / 被拦截
- 页面现成组件难以稳定接管，但真实业务接口是可复现的

若站点不是“浏览器内 `fetch` + 自渲染/接口驱动”这一类，而是 **页面上存在可见 Turnstile 复选框、需要真实鼠标点击、token 通过 hidden input 回填、并且会弹 Cloudflare 错误遮罩**，优先改读：

- `turnstile-visual-recovery.md`

## 1. 优先判断是不是“浏览器态接口站”

出现以下信号时，优先按“浏览器态接口站”处理：

- `requests` / `httpx` 访问首页或接口返回 403、访问已被拦截
- 浏览器 DevTools Network 里同一个接口却是 200
- 前端 JS 明确调用 `/api/auth/login`、`/api/checkin`、`/api/checkin/status`
- 登录后前端继续带 `Authorization: Bearer <token>`
- `verificationToken` 只在浏览器完成 Turnstile 后才能拿到

这种站点不要硬做纯 `httpx`，而应该：

1. 用 `nodriver` 进入同域页面
2. 在浏览器会话里解决 Turnstile
3. 在浏览器上下文里执行 `fetch`
4. 再用状态接口做二次复核

## 2. 勘察优先级

优先读这些证据：

1. HAR 中的真实请求
2. 浏览器 Network 的请求与响应体
3. 前端 bundle 中 `/api/...` 的调用代码
4. 页面 DOM 文本

至少确认：

- 登录接口路径、方法、字段名
- 签到接口路径、方法、字段名
- 状态接口路径、方法、返回字段
- `verificationToken` 字段名
- `Authorization` 是否必需
- 是 Cookie 鉴权、Bearer 鉴权，还是二者都参与

## 3. 页面内现成 Turnstile 难接管时的稳定策略

如果站点现成 Turnstile 组件：

- 在弹窗中
- 在 Shadow DOM 中
- 在复杂前端组件树中
- 自动提交时机不稳定

可采用更稳的办法：

1. 留在同域页面
2. 动态加载 `https://challenges.cloudflare.com/turnstile/v0/api.js`
3. 自己插入一个固定定位的容器
4. `turnstile.render(...)` 渲染新的组件
5. 用真实鼠标点击它
6. 从回调里拿 token
7. 把 token 送给真实业务接口

优点：

- 不依赖原页面的组件状态机
- 不依赖原表单按钮是否能被接管
- 登录、签到两条链路都能复用同一套 token 获取逻辑

## 4. 自渲染 Turnstile 的最小骨架

建议拆成三个函数：

- `get_verification_site_key(tab, action)`
- `render_turnstile_widget(tab, site_key)`
- `solve_turnstile_token(tab, site_key, action_name)`

其中：

- `get_verification_site_key`：优先从 `/api/settings/verification/public` 读取，不要一开始就硬编码
- `render_turnstile_widget`：把组件渲染到固定位置，便于统一点击坐标
- `solve_turnstile_token`：轮询 token、打印错误码、点击重试、超时退出

## 5. 浏览器内 fetch 的适用场景

推荐封装 `browser_fetch(tab, url, method, headers, body)`。

适合的场景：

- 需要复用浏览器里的 Cookie
- 需要复用 Cloudflare clearance
- 需要同源 `fetch`
- 需要复用前端已经建立的浏览器环境

返回值建议统一为：

```python
{
  "ok": bool,
  "status": int,
  "text": str,
  "data": dict | list | None
}
```

这样日志、异常和复核都更容易统一。

## 6. 结论必须分级

Turnstile 站点很容易把“登录成功”和“签到成功”混掉，所以结论建议严格区分：

- `login_ok`：只说明登录链路通了
- `already`：状态接口显示今天已签到，但本次没有执行新的签到动作
- `success`：本次确实调用了签到接口，且状态接口复核成功
- `failed`：调用失败或复核失败
- `unknown`：接口返回不足以判断

特别注意：

- `hasCheckedInToday = true` 只能证明当前状态，不一定证明是本次脚本刚完成的签到
- 登录成功拿到 token，也不能推断签到接口可用

## 7. 推荐日志顺序

对 Turnstile 站点，建议日志顺序固定为：

1. 读取验证码配置
2. 渲染 Turnstile
3. 获取 token
4. 调登录接口
5. 查签到前状态
6. 如果未签到，再重新取签到 token
7. 调签到接口
8. 查签到后状态
9. 输出最终分级结论

## 8. `mambo-hachimi` 类站点的抽象模式

这类站点通常具有以下共性：

- 登录页存在可见登录框，但真正提交前会弹出 Turnstile
- 登录接口是纯 JSON API
- 登录成功返回 Bearer Token
- 签到状态接口和签到接口都走 API
- 签到接口也要求 `verificationToken`
- 站点前端通过浏览器 `fetch` 驱动整个流程

因此更适合：

- `nodriver` + 浏览器内 `fetch`
- 而不是 DOM 点击驱动一整套表单流程
