#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: le.yang
"""
{{SITE_TITLE}} 青龙签到脚本。

青龙依赖：
pip3 install nodriver httpx pyvirtualdisplay

无头服务器（青龙 Docker）还需安装系统包 xvfb：
  apt-get install -y xvfb
  apk add xvfb

青龙环境变量：
{{ENV_PREFIX}}_COOKIE     必填，浏览器导出的 Cookie 字符串，多个账号用 & 分隔
{{ENV_PREFIX}}_USERNAME   可选，用户名。单账号直接填写，多账号优先用 JSON 数组
{{ENV_PREFIX}}_PASSWORD   可选，密码。单账号直接填写，多账号优先用 JSON 数组
{{ENV_PREFIX}}_HEADLESS   可选，true/false，默认 false
CHROMIUM_PATH            可选，Chromium/Chrome 可执行文件路径
BARK_URL                 可选，Bark 推送地址
"""
import asyncio
import json
import os
import random
import socket
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

import httpx
import nodriver as uc

# ----------------------------- 配置 -----------------------------
BASE_URL = "{{BASE_URL}}"
HOME_URL = f"{BASE_URL}{{HOME_PATH}}"
SIGN_URL = f"{BASE_URL}{{SIGN_PATH}}"

COOKIE_STR = os.getenv("{{ENV_PREFIX}}_COOKIE", "")
USERNAME_STR = os.getenv("{{ENV_PREFIX}}_USERNAME", "")
PASSWORD_STR = os.getenv("{{ENV_PREFIX}}_PASSWORD", "")
HEADLESS = os.getenv("{{ENV_PREFIX}}_HEADLESS", "false").lower() == "true"
BARK_URL = os.getenv("BARK_URL", "")
CHROMIUM_PATH = os.getenv("CHROMIUM_PATH", "").strip()

DEFAULT_CHROME_PATHS = [
    CHROMIUM_PATH,
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


# ----------------------------- 辅助函数 -----------------------------
class CDPEnumDuck:
    """兼容 nodriver CDP 鼠标按钮枚举。"""

    def __init__(self, val: str):
        self.val = val

    def to_json(self):
        return self.val


async def bark_notify(title: str, body: str):
    """通过 Bark 发送推送通知。"""
    if not BARK_URL:
        return

    try:
        url = f"{BARK_URL.rstrip('/')}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(url)
        print(f"📱 Bark 通知已发送: {title}")
    except Exception as e:
        print(f"⚠️ Bark 通知发送失败: {e}")


def parse_cookie_string(cookie_str: str) -> List[Dict]:
    """把浏览器导出的 Cookie 字符串转换为 nodriver 可注入的结构。"""
    cookie_list = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        cookie_list.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": "{{COOKIE_DOMAIN}}",
            "path": "/",
        })
    return cookie_list


def load_env_cookies() -> List[List[Dict]]:
    """从环境变量读取多账号 Cookie，多个账号用 & 分隔。"""
    if not COOKIE_STR.strip():
        return []

    accounts = []
    for cookie_str in COOKIE_STR.split("&"):
        cookies = parse_cookie_string(cookie_str.strip())
        if cookies:
            accounts.append(cookies)

    if accounts:
        print("📄 使用环境变量中的 Cookie。")
    return accounts


def _parse_str_list(val: str) -> List[str]:
    """解析单值或 JSON 数组格式的环境变量。"""
    val = val.strip()
    if not val:
        return []
    if val.startswith("["):
        try:
            result = json.loads(val)
            if isinstance(result, list):
                return [str(x) for x in result]
        except json.JSONDecodeError:
            pass
    return [val]


def load_env_credentials() -> List[Dict[str, str]]:
    """读取用户名密码形式的多账号配置。"""
    usernames = _parse_str_list(USERNAME_STR)
    passwords = _parse_str_list(PASSWORD_STR)
    if not usernames or not passwords:
        return []
    if len(usernames) != len(passwords):
        print("⚠️ {{ENV_PREFIX}}_USERNAME 与 {{ENV_PREFIX}}_PASSWORD 数量不匹配。")
        return []
    creds = [{"username": u, "password": p} for u, p in zip(usernames, passwords)]
    print(f"🔑 使用用户名密码登录，共 {len(creds)} 个账号。")
    return creds


def resolve_chromium_path() -> str:
    """解析可用的 Chromium/Chrome 路径。"""
    for path in DEFAULT_CHROME_PATHS:
        if path and os.path.exists(path):
            return path
    return CHROMIUM_PATH or "/usr/bin/chromium"


def _find_free_port() -> int:
    """找一个空闲本地端口，供 Chrome DevTools 使用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def _wait_for_devtools(host: str, port: int, timeout: float = 20.0) -> bool:
    """轮询 Chrome DevTools 端口直到就绪。"""
    loop = asyncio.get_event_loop()
    url = f"http://{host}:{port}/json/version"
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            await loop.run_in_executor(None, lambda: urllib.request.urlopen(url, timeout=1))
            return True
        except Exception:
            await asyncio.sleep(0.5)
    return False


async def start_browser_with_retry(chromium_path: str, use_chrome_headless: bool):
    """启动浏览器，必要时退回手动拉起 Chrome 再由 nodriver 接管。"""
    browser_args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--window-size=1280,800",
        "--disable-infobars",
        "--test-type",
        "--disable-dev-shm-usage",
    ]
    try:
        return await uc.start(
            headless=use_chrome_headless,
            sandbox=False,
            browser_executable_path=chromium_path,
            browser_args=browser_args,
        )
    except Exception as e:
        if "Failed to connect to browser" not in str(e):
            raise
        print("⚠️ nodriver 直接启动失败，退回手动启动 Chrome 再接管。")

    port = _find_free_port()
    args = [
        chromium_path,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        *browser_args,
        "--no-first-run",
        "--no-default-browser-check",
    ]
    env = os.environ.copy()
    display = env.get("DISPLAY", "").strip()
    if use_chrome_headless or not display:
        args.append("--headless")
    else:
        env["DISPLAY"] = display

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env=env,
    )
    await asyncio.sleep(3)
    ready = await _wait_for_devtools("127.0.0.1", port, timeout=20.0)
    if not ready:
        proc.kill()
        raise RuntimeError(f"Chrome 调试端口 {port} 在 20 秒内未就绪")

    browser = await uc.start(host="127.0.0.1", port=port)
    browser._process = proc  # noqa: SLF001
    return browser


async def inject_cookies(tab, cookies: List[Dict]):
    """向浏览器上下文注入当前账号 Cookie。"""
    for cookie in cookies:
        try:
            await tab.send(
                uc.cdp.network.set_cookie(
                    name=cookie["name"],
                    value=cookie["value"],
                    domain=cookie.get("domain", "{{COOKIE_DOMAIN}}"),
                    path=cookie.get("path", "/"),
                )
            )
        except Exception as e:
            print(f"⚠️ Cookie 注入失败: {cookie.get('name', '')}: {e}")


async def get_page_text(tab) -> str:
    """获取页面文本，便于打印失败原因。"""
    content = await tab.evaluate(
        """
        (function(){
            if (document.body) return document.body.innerText || document.body.textContent || "";
            if (document.documentElement) return document.documentElement.innerText || document.documentElement.textContent || "";
            return "";
        })()
        """
    )
    if not isinstance(content, str):
        content = str(content)
    return content


async def human_like_mouse_move(tab, start_x, start_y, end_x, end_y, steps=20):
    """模拟人类鼠标移动，用于 Cloudflare 等简单风控场景。"""
    for i in range(1, steps + 1):
        t = i / steps
        ease_t = 1 - (1 - t) * (1 - t)
        curr_x = int(start_x + (end_x - start_x) * ease_t + random.uniform(-2, 2))
        curr_y = int(start_y + (end_y - start_y) * ease_t + random.uniform(-2, 2))
        await tab.send(uc.cdp.input_.dispatch_mouse_event(type_="mouseMoved", x=curr_x, y=curr_y))
        await asyncio.sleep(random.uniform(0.01, 0.03))
    await tab.send(uc.cdp.input_.dispatch_mouse_event(type_="mouseMoved", x=int(end_x), y=int(end_y)))
    await asyncio.sleep(random.uniform(0.1, 0.2))


async def browser_fetch(tab, url: str, method: str = "GET", headers: Optional[Dict] = None, body: Optional[Dict] = None) -> Dict:
    """在浏览器上下文中发起 fetch，复用浏览器态 Cookie 与同源环境。"""
    payload = json.dumps(body) if body is not None else None
    script = f"""
    (async function() {{
        try {{
            const response = await fetch({json.dumps(url)}, {{
                method: {json.dumps(method)},
                headers: {json.dumps(headers or {})},
                credentials: 'include',
                body: {json.dumps(payload) if payload is not None else 'undefined'}
            }});
            const text = await response.text();
            let data = null;
            try {{ data = JSON.parse(text); }} catch (e) {{}}
            return JSON.stringify({{ ok: response.ok, status: response.status, text, data }});
        }} catch (e) {{
            return JSON.stringify({{ ok: false, status: 0, text: String(e), data: null }});
        }}
    }})()
    """
    result = await tab.evaluate(script, await_promise=True)
    raw = result if isinstance(result, str) else str(result)
    try:
        return json.loads(raw)
    except Exception:
        return {"ok": False, "status": 0, "text": raw, "data": None}


async def handle_cloudflare(tab, max_rounds=15):
    """处理基础 Cloudflare 5 秒盾。复杂场景请按站点另写专用逻辑。"""
    markers = (
        "Just a moment",
        "Checking your browser",
        "Please enable JavaScript",
        "Verifying you are human",
        "challenges.cloudflare.com",
    )
    for i in range(max_rounds):
        try:
            content = str(await tab.evaluate("document.documentElement ? document.documentElement.outerHTML : ''"))
            blocked = len(content) < 200 or any(marker in content for marker in markers)
            if not blocked:
                if i > 0:
                    print("✅ Cloudflare 盾已解开。")
                return
            if i % 3 == 0:
                print(f"🛡️ 遇到 Cloudflare 防护盾，正在等待放行 (已等 {i * 2} 秒)...")
            sx, sy = random.randint(100, 500), random.randint(100, 500)
            ex, ey = random.randint(100, 800), random.randint(100, 600)
            await human_like_mouse_move(tab, sx, sy, ex, ey, steps=15)
            await asyncio.sleep(2)
            if i == 8:
                print("🔄 Cloudflare 停留过久，刷新页面重试...")
                await tab.reload()
        except Exception:
            await asyncio.sleep(2)


async def get_verification_site_key(tab, settings_url: str, action: str) -> str:
    """从公开验证配置接口读取当前动作对应的 Turnstile siteKey。"""
    result = await browser_fetch(tab, settings_url)
    data = result.get("data") or {}
    action_conf = data.get(action) or {}
    site_key = str(action_conf.get("siteKey") or "").strip()
    if not site_key:
        raise RuntimeError(f"未找到动作 {action} 的验证配置 siteKey")
    return site_key


async def render_turnstile_widget(tab, site_key: str):
    """在同域页面动态渲染自定义 Turnstile 组件。"""
    script = f"""
    (async function() {{
        if (!window.turnstile) {{
            await new Promise((resolve, reject) => {{
                const script = document.createElement('script');
                script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
            }});
        }}
        const oldWrap = document.getElementById('codex-turnstile-wrap');
        if (oldWrap) oldWrap.remove();

        window.__codexTurnstileToken = '';
        window.__codexTurnstileError = '';

        const wrap = document.createElement('div');
        wrap.id = 'codex-turnstile-wrap';
        wrap.style.position = 'fixed';
        wrap.style.left = '50%';
        wrap.style.top = '80px';
        wrap.style.transform = 'translateX(-50%)';
        wrap.style.zIndex = '999999';
        wrap.style.background = '#ffffff';
        wrap.style.padding = '16px';
        wrap.style.border = '2px solid #ef4444';
        wrap.style.borderRadius = '12px';
        wrap.style.boxShadow = '0 8px 24px rgba(0,0,0,0.18)';
        document.body.appendChild(wrap);

        const inner = document.createElement('div');
        inner.id = 'codex-turnstile';
        wrap.appendChild(inner);

        window.turnstile.render('#codex-turnstile', {{
            sitekey: {json.dumps(site_key)},
            theme: 'light',
            callback: function(token) {{
                window.__codexTurnstileToken = token;
            }},
            'error-callback': function(err) {{
                window.__codexTurnstileError = String(err);
            }},
            'expired-callback': function() {{
                window.__codexTurnstileToken = '';
            }}
        }});
        return true;
    }})()
    """
    await tab.evaluate(script, await_promise=True)


async def get_turnstile_wrap_rect(tab) -> Optional[Dict]:
    """获取自定义 Turnstile 包裹容器坐标。"""
    result = await tab.evaluate(
        """
        (function() {
            const wrap = document.getElementById('codex-turnstile-wrap');
            if (!wrap) return null;
            const rect = wrap.getBoundingClientRect();
            return JSON.stringify({ x: rect.left, y: rect.top, w: rect.width, h: rect.height });
        })()
        """
    )
    raw = result if isinstance(result, str) else str(result)
    if not raw or raw == "null":
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def remove_turnstile_widget(tab):
    """清理自定义 Turnstile 组件。"""
    await tab.evaluate(
        """
        (function() {
            const wrap = document.getElementById('codex-turnstile-wrap');
            if (wrap) wrap.remove();
            return true;
        })()
        """
    )


async def solve_turnstile_token(tab, site_key: str, action_name: str, timeout_rounds: int = 12) -> str:
    """渲染并完成 Turnstile 验证，返回 verificationToken。"""
    print(f"🧩 开始为 {action_name} 渲染 Turnstile 组件...")
    await render_turnstile_widget(tab, site_key)
    await asyncio.sleep(3)
    last_err = ""
    for round_idx in range(timeout_rounds):
        rect = await get_turnstile_wrap_rect(tab)
        if rect:
            click_x = int(rect["x"] + 35 + random.uniform(-3, 3))
            click_y = int(rect["y"] + 50 + random.uniform(-3, 3))
            start_x = click_x - random.randint(120, 260)
            start_y = click_y - random.randint(40, 120)
            print(f"🤖 [{action_name}] 第 {round_idx + 1}/{timeout_rounds} 轮点击 Turnstile: X={click_x}, Y={click_y}")
            await human_like_mouse_move(tab, start_x, start_y, click_x, click_y, steps=25)
            duck_button = CDPEnumDuck("left")
            await tab.send(uc.cdp.input_.dispatch_mouse_event(type_="mousePressed", x=click_x, y=click_y, button=duck_button, click_count=1))
            await asyncio.sleep(random.uniform(0.08, 0.18))
            await tab.send(uc.cdp.input_.dispatch_mouse_event(type_="mouseReleased", x=click_x, y=click_y, button=duck_button, click_count=1))

        await asyncio.sleep(4)
        token = await tab.evaluate("window.__codexTurnstileToken || ''")
        error_text = await tab.evaluate("window.__codexTurnstileError || ''")
        if not isinstance(token, str):
            token = str(token)
        if not isinstance(error_text, str):
            error_text = str(error_text)
        if error_text and error_text != last_err:
            print(f"ℹ️ [{action_name}] Turnstile 错误码: {error_text}")
            last_err = error_text
        if token:
            print(f"✅ [{action_name}] Turnstile 验证成功，token 长度: {len(token)}")
            await remove_turnstile_widget(tab)
            return token
        print(f"⏳ [{action_name}] 当前尚未拿到 token，继续等待...")

    await remove_turnstile_widget(tab)
    raise RuntimeError(f"{action_name} 的 Turnstile 验证超时，未获取到 token")


async def is_logged_in(tab) -> bool:
    """通过权威页面判断 Cookie 是否仍然有效。"""
    try:
        await tab.get(HOME_URL)
        await handle_cloudflare(tab)
        await asyncio.sleep(2)
        content = await get_page_text(tab)
        print(f"📄 登录检查页面反馈: {content[:120]}")

        # 中文注释：这里必须替换成当前站点“已登录”和“未登录”的稳定标记。
        if "{{LOGIN_REQUIRED_MARKER}}" in content:
            return False
        if "{{LOGIN_OK_MARKER}}" in content:
            return True
        return False
    except Exception as e:
        print(f"⚠️ 登录检查异常: {e}")
        return False


async def login_with_credentials(tab, username: str, password: str) -> Tuple[bool, str]:
    """用户名密码登录占位函数。"""
    # 中文注释：如果站点是 Turnstile + JSON API 型，这里优先：
    # 1. 读验证配置接口拿 siteKey
    # 2. solve_turnstile_token()
    # 3. browser_fetch() 调真实登录接口
    # 4. 返回是否成功与摘要
    print(f"⚠️ 模板占位：尚未实现账号 {username} 的真实登录逻辑。")
    return False, "未实现用户名密码登录逻辑"


async def do_sign(tab, account_index: int) -> bool:
    """执行签到动作，并在函数内部做最小结果判断。"""
    label = f"第 {account_index + 1} 个账号"
    print(f"\n🎁 开始执行{label}的每日签到任务...")
    try:
        await tab.get(SIGN_URL)
        await handle_cloudflare(tab)
        await asyncio.sleep(2)

        # 中文注释：这里先查“动作前状态”，明确区分：
        # - 今天已签到
        # - 今天未签到
        # - 本次新签到成功
        # 若站点需要验证码 token，再单独为“签到动作”获取一次 token。
        content = await get_page_text(tab)
        print(f"📄 {label}签到页反馈: {content[:200]}")

        if "{{ALREADY_SIGNED_MARKER}}" in content:
            print(f"✅ {label}今日已签到（未执行新的签到动作）。")
            await bark_notify("{{SITE_NAME}} 今日已签到", f"{label} 未执行新的签到动作")
            return True

        # 中文注释：推荐结构：
        # 1. fetch_status_before_action()
        # 2. solve_turnstile_token()   # 若签到接口要求验证码
        # 3. browser_fetch() / 点击按钮 / 表单提交
        # 4. fetch_status_after_action()
        # 5. 只有 after_action 明确成功，才能判定为“本次新签到成功”
        return False
    except Exception as e:
        print(f"❌ {label}签到异常: {e}")
        await bark_notify("{{SITE_NAME}} 签到异常", str(e)[:80])
        return False


async def fetch_status_before_action(tab) -> str:
    """签到前读取权威状态占位函数。"""
    # 中文注释：这里应替换成当前站点最权威的状态接口或页面。
    return await get_page_text(tab)


async def fetch_status_after_action(tab) -> str:
    """签到后读取权威状态占位函数。"""
    # 中文注释：这里应替换成当前站点最权威的状态接口或页面。
    return await get_page_text(tab)


async def verify_sign_result(tab) -> str:
    """签到后重新读取权威状态，返回摘要。"""
    await tab.get(HOME_URL)
    await handle_cloudflare(tab)
    await asyncio.sleep(2)
    content = await get_page_text(tab)
    return content[:200]


# ----------------------------- 主流程 -----------------------------
async def main():
    print("=" * 60)
    print("{{SITE_TITLE}} 全自动签到脚本 (nodriver + env cookie)")
    print("=" * 60)

    cookie_accounts = load_env_cookies()
    cred_accounts = load_env_credentials()
    if not cookie_accounts and not cred_accounts:
        print("❌ 未配置 {{ENV_PREFIX}}_COOKIE 或 {{ENV_PREFIX}}_USERNAME/{{ENV_PREFIX}}_PASSWORD。")
        await bark_notify("{{SITE_NAME}} 签到失败", "未配置登录凭据")
        return

    virtual_display = None
    if HEADLESS:
        try:
            from pyvirtualdisplay import Display

            virtual_display = Display(visible=False, size=(1280, 800))
            virtual_display.start()
            print("🖥️ 已启动 Xvfb 虚拟显示器。")
        except Exception as e:
            print(f"⚠️ 启动 Xvfb 失败: {e}")
            print("⚠️ 退回纯无头模式，可能被风控拦截。")

    use_chrome_headless = HEADLESS and virtual_display is None
    chromium_path = resolve_chromium_path()
    failed_accounts = []
    account_tasks = []
    for cookies in cookie_accounts:
        account_tasks.append({"type": "cookie", "cookies": cookies})
    for cred in cred_accounts:
        account_tasks.append({"type": "password", "username": cred["username"], "password": cred["password"]})

    for idx, account in enumerate(account_tasks):
        print(f"\n👤 准备处理第 {idx + 1}/{len(account_tasks)} 个账号...")
        browser = None
        try:
            browser = await start_browser_with_retry(chromium_path, use_chrome_headless)
            tab = await browser.get(BASE_URL)
            await asyncio.sleep(2)

            if account["type"] == "cookie":
                await inject_cookies(tab, account["cookies"])
                if not await is_logged_in(tab):
                    print(f"❌ 第 {idx + 1} 个账号 Cookie 失效，请更新。")
                    await bark_notify("{{SITE_NAME}} 登录失败", f"第 {idx + 1} 个账号 Cookie 失效")
                    failed_accounts.append(idx + 1)
                    continue
            else:
                login_ok, login_message = await login_with_credentials(tab, account["username"], account["password"])
                print(f"📄 第 {idx + 1} 个账号登录反馈: {login_message}")
                if not login_ok:
                    failed_accounts.append(idx + 1)
                    continue

            print(f"✅ 第 {idx + 1} 个账号登录态有效。")
            before_preview = await fetch_status_before_action(tab)
            print(f"📄 第 {idx + 1} 个账号动作前状态: {before_preview[:200]}")
            sign_ok = await do_sign(tab, idx)
            after_preview = await fetch_status_after_action(tab)
            print(f"📄 第 {idx + 1} 个账号动作后状态: {after_preview[:200]}")
            verify_preview = await verify_sign_result(tab)
            print(f"📄 第 {idx + 1} 个账号最终复核反馈: {verify_preview}")
            if not sign_ok:
                failed_accounts.append(idx + 1)
        except Exception as e:
            print(f"❌ 第 {idx + 1} 个账号运行异常: {e}")
            await bark_notify("{{SITE_NAME}} 运行异常", str(e)[:80])
            failed_accounts.append(idx + 1)
        finally:
            if browser:
                try:
                    if not HEADLESS:
                        print("\n🛑 当前账号处理完毕，保持窗口开启 10 秒以便观察结果...")
                        await asyncio.sleep(10)
                    browser.stop()
                except Exception:
                    pass

    if virtual_display is not None:
        try:
            virtual_display.stop()
            print("🖥️ 已关闭 Xvfb 虚拟显示器。")
        except Exception:
            pass

    if failed_accounts:
        print(f"⚠️ 运行结束，失败账号: {failed_accounts}")
    else:
        print("🎉 所有账号处理完成。")


if __name__ == "__main__":
    uc.loop().run_until_complete(main())
