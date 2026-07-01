#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: le.yang
"""
{{SITE_TITLE}} 青龙签到脚本。

青龙依赖：
pip3 install httpx

青龙环境变量：
{{ENV_PREFIX}}_COOKIE     必填，浏览器导出的 Cookie 字符串，多个账号用 & 分隔
BARK_URL                  可选，Bark 推送地址
"""
import asyncio
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import time
import urllib.parse

import httpx

# ----------------------------- 配置 -----------------------------
BASE_URL = "{{BASE_URL}}"
HOME_URL = f"{BASE_URL}{{HOME_PATH}}"
SIGN_URL = f"{BASE_URL}{{SIGN_PATH}}"

COOKIE_STR = os.getenv("{{ENV_PREFIX}}_COOKIE", "")
BARK_URL = os.getenv("BARK_URL", "")
KEEP_DEBUG = os.getenv("{{ENV_PREFIX}}_KEEP_DEBUG", "false").strip().lower() == "true"
DEBUG_RETENTION_DAYS = int(os.getenv("{{ENV_PREFIX}}_DEBUG_RETENTION_DAYS", "7") or "7")

HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ----------------------------- 预设模式提示 -----------------------------
# {{PRESET_GUIDE}}


# ----------------------------- 辅助函数 -----------------------------
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


def now_ts() -> str:
    """返回当前 ISO 时间戳。"""
    return dt.datetime.now().astimezone().isoformat()


def mask_account_label(label: str) -> str:
    """对账号标签做最小脱敏。"""
    if len(label) <= 7:
        return label
    return f"{label[:3]}***{label[-3:]}"


def build_debug_dir(account_index: int, account_label: str) -> pathlib.Path:
    """构造当前账号调试目录。"""
    root = pathlib.Path.cwd() / "debug_{{ENV_PREFIX_LOWER}}"
    root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = mask_account_label(account_label).replace("/", "_").replace("\\", "_").replace(":", "_")
    debug_dir = root / f"{stamp}_{account_index + 1}_{suffix}"
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def cleanup_old_debug_dirs(root: pathlib.Path, retention_days: int):
    """清理过期调试目录。"""
    if retention_days <= 0 or not root.exists():
        return
    deadline = time.time() - retention_days * 86400
    for child in root.iterdir():
        try:
            if child.is_dir() and child.stat().st_mtime < deadline:
                shutil.rmtree(child, ignore_errors=True)
        except Exception as e:
            print(f"⚠️ 清理旧调试目录失败: {child}: {e}")


def append_jsonl(path: pathlib.Path, data: dict):
    """向 JSONL 文件追加结构化样本。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": now_ts(), **data}
        with path.open("a", encoding="utf-8") as fw:
            fw.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ 写入结构化日志失败: {path.name}: {e}")


def save_text(path: pathlib.Path, content: str):
    """保存文本快照。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"⚠️ 保存文本快照失败: {path.name}: {e}")


def save_success_snapshot(debug_dir: pathlib.Path, stage: str, payload: dict):
    """保存成功快照。"""
    try:
        path = debug_dir / f"success_snapshot_{stage}.json"
        path.write_text(json.dumps({"ts": now_ts(), **payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"💾 已固化成功快照[{stage}]: {path}")
    except Exception as e:
        print(f"⚠️ 保存成功快照失败[{stage}]: {e}")


def build_client(cookie: str) -> httpx.AsyncClient:
    """构建带 Cookie 的 httpx 客户端。"""
    headers = {**HEADERS_BASE, "Cookie": cookie}
    return httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True)


def extract_with_patterns(html: str, patterns: list[str]) -> str:
    """按顺序尝试多个正则，返回第一个命中的分组。"""
    for pattern in patterns:
        matched = re.search(pattern, html, re.S)
        if matched:
            return matched.group(1)
    return ""


# ----------------------------- 核心业务 -----------------------------
async def fetch_user_info(client: httpx.AsyncClient) -> dict:
    """访问权威页面，提取用户信息、表单 token 和积分。"""
    # {{API_VERIFY_GUIDE}}
    resp = await client.get(HOME_URL)
    resp.raise_for_status()
    html = resp.text

    user = extract_with_patterns(html, [
        r'title="访问我的空间"[^>]*>([^<\\s]+)',
        r'class="username"[^>]*>([^<]+)',
    ])
    uid = extract_with_patterns(html, [
        r"discuz_uid\\s*=\\s*'(\\d+)'",
        r"uid=(\\d+)",
    ])
    formhash = extract_with_patterns(html, [
        r"formhash=([a-zA-Z0-9]+)",
        r'name="formhash"\\s+value="([a-zA-Z0-9]+)"',
    ])
    credits = extract_with_patterns(html, [
        r"积分[:：]?\\s*(\\d+)",
        r"金币[:：]?\\s*(\\d+)",
    ])

    return {
        "user": user,
        "uid": uid,
        "formhash": formhash,
        "credits": credits,
        "html": html,
    }


async def do_sign(client: httpx.AsyncClient, formhash: str) -> tuple[bool, str]:
    """发送签到请求，返回是否成功和原始反馈摘要。"""
    # {{SIGN_IMPL_GUIDE}}
    resp = await client.post(
        SIGN_URL,
        content=f"formhash={formhash}",
        headers={
            "Referer": HOME_URL,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    resp.raise_for_status()
    text = resp.text
    print(f"📄 签到原始反馈: {text[:300]}")

    # 中文注释：这里的 success 只是兜底信号，真正结论仍要以权威页面复核为准。
    signed = any([
        '"success":true' in text.lower(),
        "签到成功" in text,
        "已签到" in text,
    ])
    return signed, text[:120]


async def verify_sign_result(client: httpx.AsyncClient, old_credits: str) -> tuple[bool, str]:
    """签到后重新读取权威页面，复核是否真的成功。"""
    info = await fetch_user_info(client)
    new_credits = info.get("credits", "")
    html = info.get("html", "")

    if "今日已签到" in html or "已经签到" in html:
        return True, new_credits

    if old_credits.isdigit() and new_credits.isdigit() and int(new_credits) > int(old_credits):
        return True, new_credits

    return False, new_credits or old_credits


async def fetch_authoritative_status(client: httpx.AsyncClient) -> dict:
    """读取动作前后权威状态占位函数。"""
    info = await fetch_user_info(client)
    return {
        "user": info.get("user") or "",
        "uid": info.get("uid") or "",
        "credits": info.get("credits") or "",
        "has_login_marker": "{{LOGIN_OK_MARKER}}" in (info.get("html") or ""),
        "has_signed_marker": "{{ALREADY_SIGNED_MARKER}}" in (info.get("html") or ""),
    }


async def run_account(cookie: str, idx: int):
    """处理单个账号的完整签到流程。"""
    label = f"第 {idx + 1} 个账号"
    debug_dir = build_debug_dir(idx, label)
    print(f"\n{'=' * 40}")
    print(f"👤 开始处理{label}，调试目录: {debug_dir}")

    async with build_client(cookie) as client:
        try:
            info = await fetch_user_info(client)
        except Exception as e:
            print(f"❌ {label}获取用户信息失败: {e}")
            await bark_notify("{{SITE_NAME}} 签到失败", f"{label} 获取用户信息失败: {e}")
            return

        user = info.get("user") or "未知"
        uid = info.get("uid") or ""
        formhash = info.get("formhash") or ""
        credits = info.get("credits") or "未知"
        save_text(debug_dir / "00_user_info.html", info.get("html") or "")
        append_jsonl(debug_dir / "run_samples.jsonl", {"phase": "user-info", "user": user, "uid": uid, "credits": credits})
        print(f"✅ {label}用户信息: 用户名={user}, UID={uid}, 当前积分={credits}")

        if not uid or not formhash:
            print(f"❌ {label}未拿到登录态或 formhash，Cookie 可能失效。")
            await bark_notify("{{SITE_NAME}} 签到失败", f"{label} Cookie 失效")
            return

        auth_before = await fetch_authoritative_status(client)
        print(f"🧭 {label}权威状态(动作前): {auth_before}")

        try:
            rough_ok, preview = await do_sign(client, formhash)
        except Exception as e:
            print(f"❌ {label}签到请求异常: {e}")
            await bark_notify("{{SITE_NAME}} 签到异常", f"{label} {e}")
            return

        try:
            final_ok, latest_credits = await verify_sign_result(client, str(credits))
        except Exception as e:
            print(f"⚠️ {label}签到后复核失败: {e}")
            final_ok, latest_credits = rough_ok, str(credits)

        auth_after = await fetch_authoritative_status(client)
        print(f"🧭 {label}权威状态(动作后): {auth_after}")
        append_jsonl(
            debug_dir / "run_samples.jsonl",
            {
                "phase": "sign",
                "before": auth_before,
                "rough_ok": rough_ok,
                "preview": preview,
                "after": auth_after,
                "final_ok": final_ok,
                "latest_credits": latest_credits,
            },
        )

        summary = f"用户名：{user}，UID：{uid}，积分：{latest_credits}"
        if final_ok:
            print(f"🌟 {label}签到成功！{summary}")
            save_success_snapshot(
                debug_dir,
                "sign",
                {"before": auth_before, "preview": preview, "after": auth_after, "summary": summary},
            )
            await bark_notify("{{SITE_NAME}} 签到成功", summary)
        else:
            print(f"⚠️ {label}签到结果未明确成功，请手动确认。反馈：{preview}，{summary}")
            await bark_notify("{{SITE_NAME}} 签到结果未知", f"{preview}，{summary}")


# ----------------------------- 主流程 -----------------------------
async def main():
    print("=" * 60)
    print("{{SITE_TITLE}} 全自动签到脚本")
    print("=" * 60)

    cleanup_old_debug_dirs(pathlib.Path.cwd() / "debug_{{ENV_PREFIX_LOWER}}", DEBUG_RETENTION_DAYS)
    if not COOKIE_STR.strip():
        print("❌ 未配置 {{ENV_PREFIX}}_COOKIE 环境变量。")
        await bark_notify("{{SITE_NAME}} 签到失败", "未配置 Cookie")
        return

    cookies = [item.strip() for item in COOKIE_STR.split("&") if item.strip()]
    print(f"📄 共检测到 {len(cookies)} 个账号。")

    for idx, cookie in enumerate(cookies):
        await run_account(cookie, idx)

    print("\n🎉 所有账号处理完成。")


if __name__ == "__main__":
    asyncio.run(main())
