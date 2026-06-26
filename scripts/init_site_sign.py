#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: le.yang
"""根据模板生成新的站点签到脚本骨架。"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="生成论坛签到脚本骨架")
    parser.add_argument("--site-name", required=True, help="站点文件名基名，例如 nodeseek 或 right")
    parser.add_argument("--site-title", help="站点展示名，默认等于 site-name")
    parser.add_argument("--mode", required=True, choices=["httpx", "nodriver"], help="脚本模式")
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


def main():
    """命令行入口。"""
    parser = build_parser()
    args = parser.parse_args()

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
    print(f"已生成脚本: {output_path}")


if __name__ == "__main__":
    main()
