# 独立拼图块滑块验证码

适用于丁翔等“独立可移动拼图块 `<img>` + 背景 `<canvas>` + 多个候选槽位”的平移滑块。

## 核心判断

先确认 DOM 是否同时存在：

- 背景 `canvas`
- 独立拼图块 `img`
- 滑块手柄
- 成功 token 隐藏字段

如果存在独立拼图块，**不要计算 Canvas 中两个异常块之间的距离**。Canvas 中可能同时绘制正确槽位和干扰槽位；真正需要拖动的是独立拼图块，答案是它的当前位置到匹配槽位的距离。

## 采样顺序

1. 把鼠标移动到手柄中心。
2. 发送 `mousePressed`。
3. 按住状态微移约 3px，触发展开拼图面板。
4. 等待 Canvas 和独立拼图块都有非零 DOM 尺寸。
5. 同一时刻采集：
   - `canvas.toDataURL()`
   - `canvas.width` 与 `canvas.getBoundingClientRect().width`
   - 独立拼图块 URL/二进制及透明通道
   - 独立拼图块当前中心相对 Canvas 左边界的位置
6. 保持鼠标按下，完成识别与剩余拖动。

每次刷新 challenge 后必须重新采样，禁止复用上一轮图片、位置或缩放比例。

## 槽位匹配

1. 从独立拼图块 alpha 通道提取外轮廓。
2. 对 Canvas 灰度图做轻度高斯模糊和 Canny 边缘检测。
3. 按面积、宽高、长宽比和有效拖动范围预筛闭合轮廓。
4. 用 `cv2.matchShapes`、Hu Moments、Chamfer 距离或边界 IoU匹配拼图轮廓与槽位轮廓。
5. 只接受达到质量门槛的最佳候选；低质量候选释放鼠标并刷新 challenge。

经验起点：

```python
piece_mask = (piece[:, :, 3] > 32).astype("uint8") * 255
piece_contour = max(piece_contours, key=cv2.contourArea)
shape_score = cv2.matchShapes(piece_contour, slot_contour, cv2.CONTOURS_MATCH_I1, 0)
accept = shape_score <= 0.12
```

阈值只作起点，必须用真实成功/失败样本校准。内部纹理只能作为轮廓分数接近时的次级判据。

## 坐标换算

禁止硬编码 `0.75` 或固定 Canvas 宽度。每轮计算：

```python
coordinate_scale = canvas_rect_width / canvas_native_width
piece_center_css = piece_rect_center_x - canvas_rect_left
target_center_css = (target_x + target_width / 2) * coordinate_scale
remaining_offset = target_center_css - piece_center_css
```

`piece_center_css` 必须在触发展开、微移之后读取。这样 `remaining_offset` 已经扣除了预拖距离，不要再额外减一次 3px。

## CDP 鼠标事件

使用 nodriver 自带的真实枚举：

```python
button = uc.cdp.input_.MouseButton.LEFT
```

不要用自制 duck/string 对象代替枚举。某些 CDP 序列化路径会出现 `mouseMoved` 正常、`mousePressed` 却没有生成 DOM `mousedown` 的情况。

事件序列必须明确按钮位：

```python
# 先移动到起点
dispatch_mouse_event(type_="mouseMoved", x=start_x, y=start_y)
# 按下
dispatch_mouse_event(type_="mousePressed", x=start_x, y=start_y,
                     button=button, buttons=1, click_count=1)
# 拖动过程
dispatch_mouse_event(type_="mouseMoved", x=x, y=y,
                     button=button, buttons=1)
# 释放
dispatch_mouse_event(type_="mouseReleased", x=end_x, y=end_y,
                     button=button, buttons=0, click_count=1)
```

轨迹优先确定性精确：使用 30～40 个平滑步进、末点校正和短暂停留。先保证 offset 命中，再加入极小纵向扰动；不要用大幅随机抖动掩盖坐标错误。

若面板不展开，注册捕获阶段事件探针，记录 `mousedown/mousemove/mouseup` 的 `target`、坐标、`buttons` 和 `isTrusted`。看到移动事件但没有 `mousedown` 时，先检查 CDP 枚举及 `buttons`，不要修改图像算法。

## 成功与重试

- 以站点成功 token 非空且长度合理为首要成功信号。
- 同时检查成功态 DOM，但不要只因元素存在就判定成功；必须检查可见状态或 token。
- 图像定位异常时鼠标仍处于按下状态：先发送 `mouseReleased`，再刷新 challenge。
- 验证失败后刷新组件；组件未恢复再重载登录页并重新填表。
- 每轮保存独立的 Canvas、拼图块、标注图、候选分数和最终 offset。
- 日常运行用 `KEEP_DEBUG=false`，调试时按 attempt 编号保存，避免覆盖关键失败样本。

## 最小验收

交付前至少完成：

1. 用多种背景样本验证轮廓匹配，不只测试单一图片。
2. 在真实页面确认 DOM 收到可信的 `mousedown → mousemove → mouseup`。
3. 在真实 challenge 中取得成功 token，而不是只输出预测距离。
4. 验证识别异常分支会释放鼠标并能进入下一轮。
5. 验证 Canvas/CSS 缩放变化时仍能命中。
