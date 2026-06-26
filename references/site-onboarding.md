# 新站点接入清单

## 1. 先确认输入条件

- 站点域名
- 是否已有可用 Cookie
- 是否需要账号密码
- 是否需要二次验证码或 2FA
- 是否允许多账号
- 是否有稳定的签到页、积分页、任务页、资料页

## 2. 站点勘察顺序

1. 打开首页，确认未登录和已登录的区别
2. 找签到入口
3. 观察点击签到后：
   - 是页面跳转
   - 还是 AJAX / `fetch`
   - 还是表单提交
4. 记录所有必要参数：
   - `formhash`
   - token
   - 签到接口路径
   - `Referer`
   - 自定义 header
   - 验证 token 字段名，如 `verificationToken` / `recaptchaToken`
   - 认证头字段，如 `Authorization: Bearer <token>`
5. 确认权威成功信号：
   - 余额增加
   - 已签到标记
   - 已完成任务列表
   - 用户状态对象

补充勘察：

6. 区分这些状态：
   - 未登录
   - 今天已签到
   - 今天未签到
   - 本次刚签到成功
7. 确认接口在什么上下文里才能访问成功：
   - 直连 `requests/httpx`
   - 浏览器同源 `fetch`
   - 登录后带 `Authorization`
   - 需要 Cloudflare clearance

## 3. 何时必须改用 `nodriver`

出现任意一条就优先 `nodriver`：

- Cloudflare 5 秒盾
- Turnstile
- JS 生成 token
- 站点依赖浏览器上下文 `fetch`
- Cookie 直注后还要运行页面脚本才会得到登录态
- 滑块、点选、旋转、图文验证码
- 直连接口被 403/访问拦截，但浏览器 Network 中同接口 200

## 4. 实现时必须补的能力

### 所有脚本都要有

- `bark_notify`
- 登录态检查
- 核心签到函数
- 结果复核函数
- `main()`

### `httpx` 型建议有

- `build_client`
- `fetch_user_info`
- `refresh_balance_after_sign`
- `run_account`

### `nodriver` 型建议有

- `parse_cookie_string` / `inject_cookies`
- `get_page_text`
- `human_like_mouse_move`
- `handle_cloudflare`
- `is_logged_in`
- `do_sign`
- `browser_fetch`
- `solve_turnstile_token`
- `fetch_status`

## 5. 提交前核对

- 是否写了中文注释
- 是否包含 `Author: le.yang`
- 环境变量说明是否完整
- 是否避免了“未签到/已签到”误匹配
- 是否对 Cookie 失效给出明确提示
- 是否在签到后再次读取权威状态
- 是否在 `finally` 里释放浏览器
- 是否把“已签到”和“新签到成功”分开输出
- 是否把登录成功与签到成功分开验证
- 若使用浏览器内 `fetch`，是否说明了为什么不能退回 `httpx`

## 6. 推荐输出格式

建议文件头注释包含：

- 脚本用途
- 依赖安装方式
- 无头服务器额外依赖
- 环境变量清单

建议运行输出包含：

- 总标题
- 账号开始处理提示
- 页面/接口反馈预览
- 动作前状态
- 动作后状态
- 最终结论
- 失败账号汇总
