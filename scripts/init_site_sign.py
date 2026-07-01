#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: le.yang
"""根据模板生成新的站点签到脚本骨架。"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


PRESET_CONFIGS = {
    "generic": {
        "mode": None,
        "risk_profile": None,
        "description": "通用站点；不主动覆盖模式与风控等级。",
        "hints": [
            "先确认权威成功判据，再决定 httpx 还是 nodriver。",
        ],
    },
    "browser-risk": {
        "mode": "nodriver",
        "risk_profile": "high",
        "description": "登录前 WAF / Probe，登录后极验或点选，最终业务走浏览器态或 App API。",
        "hints": [
            "先做 WAF 放行页与登录页 DOM 就绪判定，不要只看 URL。",
            "默认保留调试目录、结构化日志、成功快照。",
            "登录成功后做浏览器态 + API 双重复核。",
        ],
    },
    "turnstile-json-api": {
        "mode": "nodriver",
        "risk_profile": "high",
        "description": "Cloudflare Turnstile + 浏览器态 JSON API。",
        "hints": [
            "优先浏览器内 fetch，复用 Cookie / Storage / 同源环境。",
            "优先读取公开配置接口获取 siteKey，再渲染自定义 Turnstile 组件。",
        ],
    },
    "cookie-cloudflare": {
        "mode": "nodriver",
        "risk_profile": "standard",
        "description": "主要依赖 Cookie 注入，但首页或状态页有 Cloudflare/简单浏览器放行。",
        "hints": [
            "先注入 Cookie，再访问权威页判断是否真正已登录。",
            "若浏览器态可过、httpx 直连 403，不要强退化成 httpx。",
        ],
    },
    "simple-httpx": {
        "mode": "httpx",
        "risk_profile": "standard",
        "description": "接口稳定、可直连、无强浏览器依赖。",
        "hints": [
            "优先保持纯 httpx 闭环，避免过早引入浏览器复杂度。",
        ],
    },
}


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="生成论坛签到脚本骨架")
    parser.add_argument("--site-name", required=True, help="站点文件名基名，例如 nodeseek 或 right")
    parser.add_argument("--site-title", help="站点展示名，默认等于 site-name")
    parser.add_argument("--mode", required=True, choices=["httpx", "nodriver"], help="脚本模式")
    parser.add_argument(
        "--preset",
        default="generic",
        choices=sorted(PRESET_CONFIGS.keys()),
        help="站点模式预设；用于约束推荐工作流并给出生成后提示。",
    )
    parser.add_argument(
        "--risk-profile",
        default="standard",
        choices=["standard", "high"],
        help="站点风控等级；high 表示登录前后可能存在 WAF / 风控验证码 / 浏览器态 API",
    )
    parser.add_argument("--env-prefix", required=True, help="环境变量前缀，例如 NS 或 RIGHT")
    parser.add_argument("--base-url", default="https://example.com", help="站点基础 URL")
    parser.add_argument("--home-path", default="/", help="首页或权威页路径")
    parser.add_argument("--sign-path", default="/sign", help="签到页或签到接口路径")
    parser.add_argument("--cookie-domain", help="Cookie domain，nodriver 模式建议填写 .example.com")
    parser.add_argument("--output", default=".", help="输出目录")
    return parser


def normalize_site_name(value: str) -> str:
    """将站点名规范化为文件名可用格式。"""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_").lower()
    if not normalized:
        raise ValueError("site-name 不能为空")
    return normalized


def load_template(skill_dir: Path, mode: str) -> str:
    """读取对应模式的模板内容。"""
    template_name = "httpx_sign_template.py" if mode == "httpx" else "nodriver_sign_template.py"
    template_path = skill_dir / "assets" / "templates" / template_name
    return template_path.read_text(encoding="utf-8")


def render_template(template: str, replacements: dict[str, str]) -> str:
    """执行简单占位符替换。"""
    result = template
    for key, value in replacements.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


def build_output_path(output_dir: Path, site_name: str, mode: str) -> Path:
    """根据模式生成输出文件名。"""
    suffix = "_sign.py" if mode == "httpx" else "_sign_nodriver.py"
    return output_dir / f"{site_name}{suffix}"


def print_post_generation_hints(args, output_path: Path, env_prefix: str):
    """输出生成后的后续动作提示，减少首次建站时遗漏关键步骤。"""
    print(f"已生成脚本: {output_path}")
    preset = PRESET_CONFIGS[args.preset]
    print(f"预设模式：{args.preset} - {preset['description']}")
    for idx, hint in enumerate(preset["hints"], start=1):
        print(f"预设提示{idx}：{hint}")
    if args.mode != "nodriver":
        return

    print("建议后续动作：")
    print("1. 先补齐权威成功判据：已登录标记、未登录标记、已签到标记。")
    print("2. 登录/签到若命中浏览器风控，优先保持浏览器态 fetch，不要贸然退化成 httpx。")
    print("3. 先实现动作前权威状态、动作执行、动作后权威状态三段闭环。")
    print("4. 若站点存在 WAF / 极验 / 点选，先落盘截图、trace、overlay，再调 offset。")
    if args.risk_profile == "high":
        print("5. 当前选择的是 high 风控模式：")
        print(f"   - 推荐启用 {env_prefix}_KEEP_DEBUG=true")
        print(f"   - 推荐启用 {env_prefix}_DEBUG_RETENTION_DAYS=7")
        print(f"   - 推荐启用 {env_prefix}_LOGIN_WAIT_SECONDS=120")
        print("   - 优先实现登录页就绪判断、验证码成功快照、浏览器态/API 双重复核。")


def apply_preset_overrides(args) -> None:
    """根据预设覆盖或校验模式与风控等级。"""
    preset = PRESET_CONFIGS[args.preset]
    preset_mode = preset.get("mode")
    preset_risk = preset.get("risk_profile")
    if preset_mode and args.mode != preset_mode:
        raise ValueError(f"预设 {args.preset} 要求 mode={preset_mode}，当前为 {args.mode}")
    if preset_risk and args.risk_profile != preset_risk:
        print(f"ℹ️ 预设 {args.preset} 自动将 risk-profile 从 {args.risk_profile} 调整为 {preset_risk}")
        args.risk_profile = preset_risk


def main():
    """命令行入口。"""
    parser = build_parser()
    args = parser.parse_args()
    apply_preset_overrides(args)

    skill_dir = Path(__file__).resolve().parents[1]
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    site_name = normalize_site_name(args.site_name)
    site_title = args.site_title.strip() if args.site_title else site_name
    env_prefix = args.env_prefix.strip().upper()
    cookie_domain = args.cookie_domain or f".{args.base_url.split('://', 1)[-1].strip('/').split('/', 1)[0]}"

    template = load_template(skill_dir, args.mode)
    replacements = {
        "SITE_NAME": site_name,
        "SITE_TITLE": site_title,
        "ENV_PREFIX": env_prefix,
        "ENV_PREFIX_LOWER": env_prefix.lower(),
        "BASE_URL": args.base_url.rstrip("/"),
        "HOME_PATH": args.home_path if args.home_path.startswith("/") else f"/{args.home_path}",
        "SIGN_PATH": args.sign_path if args.sign_path.startswith("/") else f"/{args.sign_path}",
        "COOKIE_DOMAIN": cookie_domain,
        "LOGIN_REQUIRED_MARKER": "请先登录",
        "LOGIN_OK_MARKER": "个人中心",
        "ALREADY_SIGNED_MARKER": "今日已签到",
    }
    content = render_template(template, replacements)

    output_path = build_output_path(output_dir, site_name, args.mode)
    output_path.write_text(content, encoding="utf-8")
    print_post_generation_hints(args, output_path, env_prefix)


if __name__ == "__main__":
    main()
