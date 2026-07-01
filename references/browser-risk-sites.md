# 浏览器高风控站点经验

适用于这类站点：

- 登录前先过 WAF / Probe / 腾讯验证码
- 登录后再触发极验 / 点选 / 二次风控
- 最终签到和任务走 App API，而不是只靠 Web 页面

## 1. 先拆阶段，不要把所有验证码混成一个问题

至少拆成三段：

1. **前置放行**：WAF / Probe / TencentCaptcha / Cloudflare
2. **登录风险验证**：极验 `risk_level2_3` / `risk_level2_4` / 短信 / 点选
3. **业务动作**：签到、任务、评论、分享、状态复核

每一段都要有独立的“成功判据”。不要因为第一段失败，就继续硬跑第二段。

## 2. WAF 放行判据必须是“登录页 DOM 就绪”，不是 URL 没变

对类似什么值得买这类站点，WAF 通过后 URL 可能仍是登录页，但真实状态完全不同。必须同时检查：

- 页面标题是否变成真实登录页标题
- `inputCount` 是否足够
- 是否存在 `JSEncrypt` / `initGeetestTool` / `window.login_obj`
- 是否仍包含 `TencentCaptcha` / `TCaptcha`
- 正文是否还是空白、`Safety check`、或白屏容器

若登录页 **DOM 未就绪**，应直接判定“WAF 未真正放行”，不要继续填表单或发 AJAX 登录。

## 3. 腾讯平移滑块优先用确定性精确拖动

对腾讯平移滑块，不要默认套“人类化随机轨迹”。先优先尝试：

- CDP 精确拖动
- 固定步数
- 极小纵向扰动
- 末端稳定收尾
- 不加大幅 overshoot

经验结论：

- 这类题更像“像素命中率”问题，而不是“像不像人”问题
- 随机抖动常把本来正确的 `delta` 拖偏

## 4. 腾讯刷新按钮要按模态框相对坐标点真实控件

当腾讯题面进入这些状态时：

- `Safety check`
- 白屏
- 失去蓝色手柄
- `Refreshing too often ...`

不要靠文本匹配去点“刷新”。文本节点和容器很容易误命中整块遮罩。优先做法：

- 先识别验证码白色模态框
- 再按模态框左下角相对坐标点击真实刷新按钮

## 5. 登录极验要区分三种失败

### A. 识别失败

- 没拿到 `bg/full` canvas
- 差分没找到缺口
- 按钮几何缺失

处理：刷新 challenge，重新采样。

### B. 事件没打进页面

典型信号：

- `events=0`
- `downs=0`
- `drag_moves=0`

处理：前置浏览器窗口、切换系统鼠标、重试当前 challenge。

### C. 事件打进去了，但服务端 forbidden

典型信号：

- `downs=1`
- `drag_moves > 0`
- `ups=1`
- 同时返回 `error_113` / `网络不给力` / `forbidden`

处理重点：

- 先把它当成**风控拒绝**，不是简单的“offset 算错”
- 不要无脑枚举几十个偏移
- 同一 challenge 最多补拖一次
- 出现 `error_113` 后刷新 challenge，再重新评估轨迹或环境

## 6. 极验 `risk_level2_3` 先落盘 canvas 与 overlay，再调偏移

必须保存：

- `geetest_bg_XX.png`
- `geetest_full_XX.png`
- `geetest_mask_XX.png`
- `geetest_overlay_XX.png`
- `geetest_trace_XX.json`
- `geetest_samples.jsonl`

并且在 overlay 里至少画出：

- 缺口框
- 缺口左边缘线
- 缺口中心线
- 实际目标拖动线

如果没有这些图，就不要盲调 `offset`。

## 7. 同一 challenge 上最多补拖一次

对极验滑块，第一拖后：

- 若无结果、无错误框、按钮仍在：允许同题补拖一次
- 若出现 `error_113` / `请点击此处重试`：直接刷新 challenge

不要在同一题面上无限拖动。这样只会污染状态，让后续判断更乱。

## 8. 成功样本要固化

一旦登录验证码成功，要保存成功快照，例如：

- `geetest_success_snapshot_risk_level2_3.json`
- `geetest_success_snapshot_risk_level2_4.json`

这样下次扩展同类站点时，可以优先复用：

- 偏移分布
- 事件形态
- 成功后页面变化
- 结果回填字段

## 9. 类似 SMZDM 的站点要做“双重成功复核”

对“浏览器登录 + App API 签到”类站点，至少做两层复核：

1. **浏览器态复核**
   - Cookie 已拿到
   - 用户页或前端状态显示已登录

2. **App API 复核**
   - 例如 `/v1/user/info`
   - 再验证 `/v1/user/checkin`

不要只因为 Web 登录成功就宣称脚本完成。

## 10. 任务接口为空时，不要硬造“任务失败”

像什么值得买这类站点，`/v1/user/daily_task/list` 可能返回空列表。应输出：

- 任务数为 0
- 本轮未发现可执行任务

不要把“站点今天无任务”误报成“脚本任务失败”。
