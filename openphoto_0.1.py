#!/usr/bin/env python3
# openphoto_0.1.py
# OpenPhoto 0.1 — DiffusionBee-style desktop app (single file — no extra apps).
# FLUX image/video + Hugging Face LLM catalog/download/vibe-add + multi-provider LLM APIs.
# Stdlib only (tkinter + urllib).

from __future__ import annotations

import base64
import json
import os
import queue
import random
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "OpenPhoto 0.1"
APP_NAME = "OpenPhoto 0.1"
TITLEBAR_H = 55
SIDEBAR_W = 200
CARD_W, CARD_H = 280, 230
# System UI font stack (DiffusionBee: -apple-system / BlinkMacSystemFont)
import sys as _sys
UI_FONT = "Helvetica Neue" if _sys.platform == "darwin" else "Segoe UI"
UI_FONT_TEXT = UI_FONT

# Theme palettes (DiffusionBee light + dark counterpart)
LIGHT_THEME = {
    "BG": "#F2F2F2",
    "TOP": "#FFFFFF",
    "PANEL": "#F4F5F5",
    "PANEL_HOVER": "#EBECEC",
    "BORDER": "#E6E6E6",
    "TEXT": "#000000",
    "MUTED": "#6E6E73",
    "BLUE": "#3E7BFA",
    "BLUE_HOVER": "#3d6ffa",
    "ICON_BLUE": "#0A84FF",
    "SIDEBAR": "#F4F5F5",
    "SIDEBAR_SEL": "#E6E6E6",
    "INPUT_BG": "#F1F4FA",
    "CONTENT": "#F2F2F2",
    "OK": "#28c840",
    "WARN": "#c77c00",
    "ERR": "#ff5f57",
}
DARK_THEME = {
    "BG": "#090909",
    "TOP": "#0d0d0e",
    "PANEL": "#1a1b1f",
    "PANEL_HOVER": "#202228",
    "BORDER": "#2d3138",
    "TEXT": "#f4f4f5",
    "MUTED": "#a7a9b2",
    "BLUE": "#3E7BFA",
    "BLUE_HOVER": "#5b90ff",
    "ICON_BLUE": "#0A84FF",
    "SIDEBAR": "#0a0b0d",
    "SIDEBAR_SEL": "#1a1b1f",
    "INPUT_BG": "#111318",
    "CONTENT": "#090909",
    "OK": "#28c840",
    "WARN": "#febc2e",
    "ERR": "#ff5f57",
}

# Active theme tokens (mutated by apply_theme)
BG = LIGHT_THEME["BG"]
TOP = LIGHT_THEME["TOP"]
PANEL = LIGHT_THEME["PANEL"]
PANEL_HOVER = LIGHT_THEME["PANEL_HOVER"]
BORDER = LIGHT_THEME["BORDER"]
TEXT = LIGHT_THEME["TEXT"]
MUTED = LIGHT_THEME["MUTED"]
BLUE = LIGHT_THEME["BLUE"]
BLUE_HOVER = LIGHT_THEME["BLUE_HOVER"]
ICON_BLUE = LIGHT_THEME["ICON_BLUE"]
SIDEBAR = LIGHT_THEME["SIDEBAR"]
SIDEBAR_SEL = LIGHT_THEME["SIDEBAR_SEL"]
INPUT_BG = LIGHT_THEME["INPUT_BG"]
CONTENT = LIGHT_THEME["CONTENT"]
OK = LIGHT_THEME["OK"]
WARN = LIGHT_THEME["WARN"]
ERR = LIGHT_THEME["ERR"]
DARK_MODE = False


def apply_theme(dark: bool = False) -> None:
    """Swap module-level color tokens for light or dark mode."""
    global BG, TOP, PANEL, PANEL_HOVER, BORDER, TEXT, MUTED
    global BLUE, BLUE_HOVER, ICON_BLUE, SIDEBAR, SIDEBAR_SEL, INPUT_BG, CONTENT
    global OK, WARN, ERR, DARK_MODE
    palette = DARK_THEME if dark else LIGHT_THEME
    DARK_MODE = bool(dark)
    BG = palette["BG"]
    TOP = palette["TOP"]
    PANEL = palette["PANEL"]
    PANEL_HOVER = palette["PANEL_HOVER"]
    BORDER = palette["BORDER"]
    TEXT = palette["TEXT"]
    MUTED = palette["MUTED"]
    BLUE = palette["BLUE"]
    BLUE_HOVER = palette["BLUE_HOVER"]
    ICON_BLUE = palette["ICON_BLUE"]
    SIDEBAR = palette["SIDEBAR"]
    SIDEBAR_SEL = palette["SIDEBAR_SEL"]
    INPUT_BG = palette["INPUT_BG"]
    CONTENT = palette["CONTENT"]
    OK = palette["OK"]
    WARN = palette["WARN"]
    ERR = palette["ERR"]

HOME = Path.home() / ".openphoto"
LLM_DIR = HOME / "llms"


def os_pictures_dir() -> Path:
    """OS Pictures folder (macOS/Windows/Linux)."""
    if _sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Pictures"
    xdg = os.environ.get("XDG_PICTURES_DIR")
    if xdg:
        return Path(xdg).expanduser()
    return Path.home() / "Pictures"


def os_desktop_dir() -> Path:
    """OS Desktop folder (macOS/Windows/Linux)."""
    if _sys.platform == "win32":
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    xdg = os.environ.get("XDG_DESKTOP_DIR")
    if xdg:
        return Path(xdg).expanduser()
    return Path.home() / "Desktop"


OUTPUT_DIR = os_pictures_dir() / "OpenPhoto"
_LEGACY_OUTPUT_DIR = HOME / "outputs"
HISTORY_PATH = HOME / "history.json"
CONFIG_PATH = HOME / "config.json"
HF_VIBES_PATH = HOME / "hf_vibes.json"
HF_INSTALLED_PATH = HOME / "hf_installed.json"
HF_API = "https://huggingface.co"
HF_RESOLVE = "https://huggingface.co/{repo}/resolve/main/{file}"

# Pre-baked BFL FLUX catalog (api.bfl.ai) — latest + previous generations
# kind: image | video
# family: flux3 | flux2 | flux11 | flux1 | kontext | fill
# flags: flex_controls (steps/guidance), img2img, fill_mask
FLUX_MODELS: dict[str, dict[str, Any]] = {
    # —— FLUX 3 (multimodal video + audio; image API rolls out on same stack) ——
    "FLUX 3 Video": {
        "endpoint": "flux-3-video",
        "kind": "video",
        "family": "flux3",
        "label": "Latest — video + synced audio (t2v / i2v / v2v)",
    },
    "FLUX 3 Image (preview)": {
        "endpoint": "flux-3-image",
        "kind": "image",
        "family": "flux3",
        "label": "Latest image path (early access when enabled on key)",
        "img2img": True,
    },
    # —— FLUX.2 ——
    "FLUX.2 [pro] preview": {
        "endpoint": "flux-2-pro-preview",
        "kind": "image",
        "family": "flux2",
        "label": "Latest FLUX.2 [pro] advances",
        "img2img": True,
    },
    "FLUX.2 [pro]": {
        "endpoint": "flux-2-pro",
        "kind": "image",
        "family": "flux2",
        "label": "Pinned FLUX.2 [pro] snapshot",
        "img2img": True,
    },
    "FLUX.2 [max]": {
        "endpoint": "flux-2-max",
        "kind": "image",
        "family": "flux2",
        "label": "Highest quality FLUX.2",
        "img2img": True,
    },
    "FLUX.2 [flex]": {
        "endpoint": "flux-2-flex",
        "kind": "image",
        "family": "flux2",
        "label": "Typography / adjustable steps + guidance",
        "img2img": True,
        "flex_controls": True,
    },
    "FLUX.2 [klein] 9B preview": {
        "endpoint": "flux-2-klein-9b-preview",
        "kind": "image",
        "family": "flux2",
        "label": "Latest klein 9B (KV cache)",
        "img2img": True,
    },
    "FLUX.2 [klein] 9B": {
        "endpoint": "flux-2-klein-9b",
        "kind": "image",
        "family": "flux2",
        "label": "Pinned klein 9B",
        "img2img": True,
    },
    "FLUX.2 [klein] 4B": {
        "endpoint": "flux-2-klein-4b",
        "kind": "image",
        "family": "flux2",
        "label": "Fastest FLUX.2",
        "img2img": True,
    },
    # —— FLUX.1 Kontext (edit) ——
    "FLUX.1 Kontext [pro]": {
        "endpoint": "flux-kontext-pro",
        "kind": "image",
        "family": "kontext",
        "label": "Character / scene consistent edits",
        "img2img": True,
    },
    "FLUX.1 Kontext [max]": {
        "endpoint": "flux-kontext-max",
        "kind": "image",
        "family": "kontext",
        "label": "Highest quality Kontext edits",
        "img2img": True,
    },
    # —— FLUX1.1 ——
    "FLUX1.1 [pro] Ultra": {
        "endpoint": "flux-pro-1.1-ultra",
        "kind": "image",
        "family": "flux11",
        "label": "Ultra resolution FLUX1.1",
    },
    "FLUX1.1 [pro]": {
        "endpoint": "flux-pro-1.1",
        "kind": "image",
        "family": "flux11",
        "label": "Classic FLUX1.1 [pro]",
    },
    # —— FLUX.1 ——
    "FLUX.1 [pro]": {
        "endpoint": "flux-pro",
        "kind": "image",
        "family": "flux1",
        "label": "Original FLUX.1 [pro]",
    },
    "FLUX.1 [dev]": {
        "endpoint": "flux-dev",
        "kind": "image",
        "family": "flux1",
        "label": "Open-weight lineage FLUX.1 [dev]",
    },
    # —— Fill / inpaint ——
    "FLUX.1 Fill [pro]": {
        "endpoint": "flux-pro-1.0-fill",
        "kind": "image",
        "family": "fill",
        "label": "Inpaint / fill (mask + image)",
        "img2img": True,
        "fill_mask": True,
    },
    "FLUX.1 Fill": {
        "endpoint": "flux-fill",
        "kind": "image",
        "family": "fill",
        "label": "Fill / object removal",
        "img2img": True,
        "fill_mask": True,
    },
}

# Back-compat alias used by older call sites
FLUX2_MODELS = {k: v["endpoint"] for k, v in FLUX_MODELS.items()}

IMAGE_MODEL_NAMES = [k for k, v in FLUX_MODELS.items() if v["kind"] == "image"]
VIDEO_MODEL_NAMES = [k for k, v in FLUX_MODELS.items() if v["kind"] == "video"]
DEFAULT_FLUX_MODEL = "FLUX.2 [pro] preview"

FAMILY_ORDER = ("flux3", "flux2", "kontext", "flux11", "flux1", "fill")
FAMILY_TITLES = {
    "flux3": "FLUX 3 (latest multimodal)",
    "flux2": "FLUX.2",
    "kontext": "FLUX.1 Kontext",
    "flux11": "FLUX1.1",
    "flux1": "FLUX.1",
    "fill": "Fill / inpaint",
}

VIDEO_RESOLUTIONS = ["hd", "fhd"]
VIDEO_DURATIONS = ["5", "6", "8", "10", "12", "15", "20"]
VIDEO_MODES = [
    ("Text to video (t2v)", "t2v"),
    ("Image to video (i2v)", "i2v"),
    ("Video continue (v2v)", "v2v"),
]

SIZES = [
    ("Square 1K", 1024, 1024),
    ("Portrait 1K", 768, 1024),
    ("Landscape 1K", 1024, 768),
    ("Square 1.5K", 1536, 1536),
    ("Wide 2K", 1920, 1080),
    ("Portrait 2K", 1080, 1920),
]

LLM_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "o3-mini", "gpt-4o-mini"],
        "key_env": "OPENAI_API_KEY",
        "style": "openai",
    },
    "anthropic": {
        "label": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-haiku-latest"],
        "key_env": "ANTHROPIC_API_KEY",
        "style": "anthropic",
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "key_env": "GROQ_API_KEY",
        "style": "openai",
    },
    "together": {
        "label": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "models": ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo"],
        "key_env": "TOGETHER_API_KEY",
        "style": "openai",
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["openai/gpt-4o-mini", "anthropic/claude-sonnet-4", "google/gemini-2.5-flash"],
        "key_env": "OPENROUTER_API_KEY",
        "style": "openai",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "key_env": "DEEPSEEK_API_KEY",
        "style": "openai",
    },
    "xai": {
        "label": "xAI (Grok)",
        "base_url": "https://api.x.ai/v1",
        "models": ["grok-3", "grok-3-mini", "grok-2-image"],
        "key_env": "XAI_API_KEY",
        "style": "openai",
    },
    "gemini": {
        "label": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        "key_env": "GEMINI_API_KEY",
        "style": "gemini",
    },
    "ollama": {
        "label": "Ollama (local)",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["llama3.2", "mistral", "qwen2.5", "llava", "gemma3"],
        "key_env": "OLLAMA_API_KEY",
        "style": "openai",
    },
    "lmstudio": {
        "label": "LM Studio (local)",
        "base_url": "http://127.0.0.1:1234/v1",
        "models": ["local-model"],
        "key_env": "LMSTUDIO_API_KEY",
        "style": "openai",
    },
    "custom": {
        "label": "Custom OpenAI-compatible",
        "base_url": "http://127.0.0.1:8000/v1",
        "models": ["custom-model"],
        "key_env": "CUSTOM_LLM_API_KEY",
        "style": "openai",
    },
    "huggingface": {
        "label": "Hugging Face (local GGUF)",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": [],  # filled from downloaded / vibe catalog
        "key_env": "HF_TOKEN",
        "style": "openai",
    },
    "pollinations": {
        "label": "Pollinations (free, no key)",
        "base_url": "https://text.pollinations.ai",
        "models": ["openai", "unity", "midijourney", "flux"],
        "key_env": "POLLINATIONS_API_KEY",
        "style": "pollinations",
    },
}

# Free no-key image route (Pollinations) — used when BFL key is empty
FREE_IMAGE_API = "https://image.pollinations.ai/prompt/{prompt}"
# Map OpenPhoto FLUX labels → Pollinations model ids
FREE_FLUX_MODEL_MAP = {
    "FLUX 3 Image (preview)": "flux",
    "FLUX 3 Video": "flux",
    "FLUX.2 [pro] preview": "flux",
    "FLUX.2 [pro]": "flux",
    "FLUX.2 [max]": "flux",
    "FLUX.2 [flex]": "flux",
    "FLUX.2 [klein] 9B preview": "flux",
    "FLUX.2 [klein] 9B": "flux",
    "FLUX.2 [klein] 4B": "turbo",
    "FLUX.1 Kontext [pro]": "kontext",
    "FLUX.1 Kontext [max]": "kontext",
    "FLUX1.1 [pro] Ultra": "flux",
    "FLUX1.1 [pro]": "flux",
    "FLUX.1 [pro]": "flux",
    "FLUX.1 [dev]": "flux",
    "FLUX.1 Fill [pro]": "flux",
    "FLUX.1 Fill": "flux",
}

# Pre-baked Hugging Face LLMs for FLUX prompt vibes (download on demand into ~/.openphoto/llms)
# Not shipped as binaries — catalog is pre-installed; click Download LLMs to fetch weights.
HF_LLM_CATALOG: list[dict[str, Any]] = [
    {
        "id": "llama32-3b-q4",
        "name": "Llama 3.2 3B Instruct (Q4_K_M)",
        "repo": "bartowski/Llama-3.2-3B-Instruct-GGUF",
        "file": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_hint": "~2.0 GB",
        "vibe": "clean, modern, versatile FLUX prompting",
        "tags": ["flux", "general", "fast"],
    },
    {
        "id": "llama31-8b-q4",
        "name": "Llama 3.1 8B Instruct (Q4_K_M)",
        "repo": "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        "file": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "size_hint": "~4.9 GB",
        "vibe": "rich cinematic FLUX scene writing",
        "tags": ["flux", "cinematic"],
    },
    {
        "id": "qwen25-7b-q4",
        "name": "Qwen2.5 7B Instruct (Q4_K_M)",
        "repo": "bartowski/Qwen2.5-7B-Instruct-GGUF",
        "file": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "size_hint": "~4.7 GB",
        "vibe": "sharp detail, typography-aware, structured prompts",
        "tags": ["flux", "detail", "text"],
    },
    {
        "id": "qwen25-3b-q4",
        "name": "Qwen2.5 3B Instruct (Q4_K_M)",
        "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_hint": "~2.0 GB",
        "vibe": "fast vibe drafting for FLUX.2 / FLUX 3",
        "tags": ["flux", "fast"],
    },
    {
        "id": "phi35-mini-q4",
        "name": "Phi-3.5 Mini Instruct (Q4_K_M)",
        "repo": "bartowski/Phi-3.5-mini-instruct-GGUF",
        "file": "Phi-3.5-mini-instruct-Q4_K_M.gguf",
        "size_hint": "~2.4 GB",
        "vibe": "tight technical product & UI shot prompts",
        "tags": ["flux", "product"],
    },
    {
        "id": "gemma2-2b-q4",
        "name": "Gemma 2 2B IT (Q4_K_M)",
        "repo": "bartowski/gemma-2-2b-it-GGUF",
        "file": "gemma-2-2b-it-Q4_K_M.gguf",
        "size_hint": "~1.6 GB",
        "vibe": "lightweight everyday FLUX ideas",
        "tags": ["flux", "tiny"],
    },
    {
        "id": "mistral7b-q4",
        "name": "Mistral 7B Instruct v0.3 (Q4_K_M)",
        "repo": "bartowski/Mistral-7B-Instruct-v0.3-GGUF",
        "file": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
        "size_hint": "~4.4 GB",
        "vibe": "artistic mood, lighting, film-still vibes",
        "tags": ["flux", "art"],
    },
    {
        "id": "deepseek-r1-distill-8b-q4",
        "name": "DeepSeek R1 Distill Llama 8B (Q4_K_M)",
        "repo": "bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF",
        "file": "DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf",
        "size_hint": "~4.9 GB",
        "vibe": "reasoned multi-shot FLUX storyboard prompts",
        "tags": ["flux", "reason"],
    },
]

# DiffusionBee Homepage.vue categories + card copy (misc = OpenPhoto extras)
HOME_SECTIONS = [
    (
        "All AI Tools",
        [
            ("Text to image", "Generate images with text descriptions", "astronaut", "txt2img"),
            ("Image to image", "Transform images with text descriptions", "tree", "img2img"),
            ("Inpainting", "Add or remove objects from an image", "inpaint", "inpaint"),
            ("Upscaler", "Use AI to increase the resolution of an image.", "face", "upscale"),
            ("Training", "Train a model on your own images using DreamBooth.", "canvas", "training"),
        ],
    ),
    (
        "Pages",
        [
            ("Models", "Download, import and manage models", "astronaut", "models"),
            ("History", "View generated images", "tree", "history"),
            ("Settings", "", "face", "settings"),
        ],
    ),
    (
        "Miscellaneous",
        [
            ("Text to video", "FLUX 3 video + synced audio from a text prompt.", "illusion", "txt2vid"),
            ("LLM Prompt Lab", "Enhance prompts with any connected LLM provider.", "astronaut", "llm"),
            ("Download LLMs", "Hugging Face GGUF catalog, vibe add & download.", "face", "hf_llms"),
        ],
    ),
]

# Flat list for any legacy callers
TOOLS = [t for _, items in HOME_SECTIONS for t in items]

# DiffusionBee sidebar (ApplicationFrame + PagesRouter always_on)
# (key, icon glyph, label)
NAV_TABS = [
    ("home", "⌂", "Home"),
    ("txt2img", "🖼", "Text to image"),
    ("img2img", "🗂", "Image to image"),
    ("inpaint", "🖌", "Inpainting"),
    ("upscale", "⤢", "Upscaler"),
    ("models", "🧊", "Models"),
    ("history", "↺", "History"),
]

# Pages opened from home/sidebar that are not generation applets
PAGE_TABS = {"home", "models", "history", "settings", "training", "llms", "activity"}


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib)
# ---------------------------------------------------------------------------

def _http_json(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    body: Any = None,
    timeout: float = 120.0,
) -> dict:
    data = None
    hdrs = {"Accept": "application/json", "User-Agent": "OpenPhoto/0.1"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_body)
        except Exception:
            parsed = {"error": err_body}
        raise RuntimeError(f"HTTP {e.code}: {parsed}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error: {e.reason}") from e


def _download_bytes(url: str, timeout: float = 120.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "OpenPhoto/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_json(url: str, headers: Optional[dict] = None, timeout: float = 60.0) -> Any:
    hdrs = {"Accept": "application/json", "User-Agent": "OpenPhoto/0.1"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download_file(
    url: str,
    dest: Path,
    headers: Optional[dict] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    timeout: float = 600.0,
) -> Path:
    """Stream a file to disk (Hugging Face resolve URLs)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    hdrs = {"User-Agent": "OpenPhoto/0.1"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(partial, "wb") as f:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_progress:
                    on_progress(done, total)
    partial.replace(dest)
    return dest


# ---------------------------------------------------------------------------
# Hugging Face LLM catalog + vibe add + downloads (in-process)
# ---------------------------------------------------------------------------

class HuggingFaceLLMStore:
    """Pre-baked + vibe-added HF GGUF catalog; downloads into ~/.openphoto/llms."""

    def __init__(self, hf_token: str = ""):
        LLM_DIR.mkdir(parents=True, exist_ok=True)
        self.hf_token = (hf_token or os.environ.get("HF_TOKEN") or "").strip()
        self.vibes: list[dict[str, Any]] = []
        self.installed: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        self.vibes = []
        if HF_VIBES_PATH.exists():
            try:
                self.vibes = json.loads(HF_VIBES_PATH.read_text())
            except Exception:
                self.vibes = []
        self.installed = {}
        if HF_INSTALLED_PATH.exists():
            try:
                self.installed = json.loads(HF_INSTALLED_PATH.read_text())
            except Exception:
                self.installed = {}

    def save_vibes(self) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        HF_VIBES_PATH.write_text(json.dumps(self.vibes, indent=2))

    def save_installed(self) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        HF_INSTALLED_PATH.write_text(json.dumps(self.installed, indent=2))

    def catalog(self) -> list[dict[str, Any]]:
        """Pre-baked catalog + user vibe-adds (pre-installed entries, download optional)."""
        out = [dict(x, source="prebaked") for x in HF_LLM_CATALOG]
        for v in self.vibes:
            item = dict(v)
            item.setdefault("source", "vibe")
            out.append(item)
        return out

    def local_path(self, item: dict[str, Any]) -> Path:
        safe = item.get("id") or Path(item.get("file", "model.gguf")).stem
        return LLM_DIR / safe / Path(item["file"]).name

    def is_downloaded(self, item: dict[str, Any]) -> bool:
        p = self.local_path(item)
        if p.exists() and p.stat().st_size > 0:
            return True
        rec = self.installed.get(item.get("id", ""))
        if rec and Path(rec.get("path", "")).exists():
            return True
        return False

    def resolve_url(self, item: dict[str, Any]) -> str:
        repo = item["repo"].strip().strip("/")
        file = item["file"].strip().lstrip("/")
        return HF_RESOLVE.format(repo=repo, file=file)

    def _auth_headers(self) -> dict:
        h = {"User-Agent": "OpenPhoto/0.1"}
        if self.hf_token:
            h["Authorization"] = f"Bearer {self.hf_token}"
        return h

    def vibe_add(
        self,
        name: str,
        repo: str,
        file: str,
        vibe: str = "",
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Add a Hugging Face GGUF by repo/file with a FLUX prompt vibe."""
        repo = repo.strip()
        file = file.strip()
        # accept full HF URLs
        if "huggingface.co/" in repo:
            # https://huggingface.co/org/repo/resolve/main/file.gguf
            parts = repo.replace("https://", "").replace("http://", "").split("/")
            # huggingface.co / org / repo / ...
            try:
                i = parts.index("huggingface.co")
                org, model = parts[i + 1], parts[i + 2]
                repo = f"{org}/{model}"
                if "resolve" in parts:
                    ri = parts.index("resolve")
                    file = "/".join(parts[ri + 2 :]) or file
            except Exception:
                pass
        if file.endswith(".gguf") is False and "/" in file and file.split("/")[-1].endswith(".gguf"):
            pass
        if not repo or not file:
            raise RuntimeError("Need Hugging Face repo (org/name) and a .gguf filename.")
        mid = f"vibe-{uuid.uuid4().hex[:8]}"
        item = {
            "id": mid,
            "name": name.strip() or Path(file).stem,
            "repo": repo,
            "file": file,
            "size_hint": "custom",
            "vibe": vibe.strip() or "custom FLUX prompt vibe",
            "tags": tags or ["flux", "vibe"],
            "source": "vibe",
        }
        self.vibes.append(item)
        self.save_vibes()
        return item

    def download(
        self,
        item: dict[str, Any],
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> Path:
        url = self.resolve_url(item)
        dest = self.local_path(item)
        if dest.exists() and dest.stat().st_size > 0:
            if on_progress:
                on_progress(1, 1, "Already downloaded")
            return dest

        def prog(done: int, total: int):
            if on_progress:
                if total:
                    pct = int(100 * done / total)
                    mb = done / (1024 * 1024)
                    tot = total / (1024 * 1024)
                    on_progress(done, total, f"{pct}%  {mb:.1f}/{tot:.1f} MB")
                else:
                    on_progress(done, 0, f"{done / (1024 * 1024):.1f} MB")

        if on_progress:
            on_progress(0, 0, f"Connecting {item['repo']}…")
        path = _download_file(url, dest, headers=self._auth_headers(), on_progress=prog)
        self.installed[item["id"]] = {
            "id": item["id"],
            "name": item["name"],
            "repo": item["repo"],
            "file": item["file"],
            "path": str(path),
            "vibe": item.get("vibe", ""),
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.save_installed()
        if on_progress:
            on_progress(1, 1, f"Saved {path.name}")
        return path

    def list_repo_ggufs(self, repo: str) -> list[str]:
        """List .gguf files in a HF repo (for vibe add helper)."""
        repo = repo.strip().strip("/")
        url = f"{HF_API}/api/models/{repo}/tree/main"
        data = _http_get_json(url, headers=self._auth_headers())
        files = []
        if isinstance(data, list):
            for row in data:
                p = row.get("path") or ""
                if p.endswith(".gguf"):
                    files.append(p)
        return sorted(files)

    def downloaded_models(self) -> list[dict[str, Any]]:
        out = []
        for item in self.catalog():
            if self.is_downloaded(item):
                rec = dict(item)
                rec["path"] = str(self.local_path(item))
                out.append(rec)
        return out

    def sync_provider_models(self) -> list[str]:
        names = [m["name"] for m in self.downloaded_models()]
        LLM_PROVIDERS["huggingface"]["models"] = names or ["(download a GGUF in LLMs window)"]
        return names


# ---------------------------------------------------------------------------
# Config / history
# ---------------------------------------------------------------------------

@dataclass
class AppConfig:
    bfl_api_key: str = ""
    flux_model: str = DEFAULT_FLUX_MODEL
    video_model: str = "FLUX 3 Video"
    video_mode: str = "t2v"
    video_resolution: str = "hd"
    video_duration: int = 5
    video_audio: bool = True
    default_width: int = 1024
    default_height: int = 1024
    steps: int = 28
    guidance: float = 3.5
    seed: int = -1
    safety_tolerance: int = 2
    output_format: str = "png"
    llm_provider: str = "pollinations"
    llm_model: str = "openai"
    use_free_backend: bool = True  # no BFL key → Pollinations FLUX (free)
    pollinations_api_key: str = ""  # optional; not required
    llm_base_url: str = ""
    llm_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    together_api_key: str = ""
    openrouter_api_key: str = ""
    deepseek_api_key: str = ""
    xai_api_key: str = ""
    gemini_api_key: str = ""
    ollama_api_key: str = "ollama"
    custom_llm_api_key: str = ""
    custom_base_url: str = "http://127.0.0.1:8000/v1"
    hf_token: str = ""
    hf_active_llm: str = ""
    enhance_prompts: bool = True
    dark_mode: bool = False
    output_dir: str = str(OUTPUT_DIR)

    @classmethod
    def load(cls) -> "AppConfig":
        HOME.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cfg = cls()
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text())
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception:
                pass
        # Auto-export to OS Pictures (migrate legacy ~/.openphoto/outputs)
        try:
            out = Path(cfg.output_dir).expanduser()
        except Exception:
            out = _LEGACY_OUTPUT_DIR
        if not cfg.output_dir or out == _LEGACY_OUTPUT_DIR or out == HOME / "outputs":
            cfg.output_dir = str(OUTPUT_DIR)
        Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
        # env overrides when config empty
        if not cfg.bfl_api_key:
            cfg.bfl_api_key = os.environ.get("BFL_API_KEY", "")
        if not cfg.hf_token:
            cfg.hf_token = os.environ.get("HF_TOKEN", "")
        for key, meta in LLM_PROVIDERS.items():
            attr = f"{key}_api_key" if key != "custom" else "custom_llm_api_key"
            if key == "custom":
                attr = "custom_llm_api_key"
            elif key == "openai":
                attr = "openai_api_key"
            elif key == "anthropic":
                attr = "anthropic_api_key"
            elif key == "groq":
                attr = "groq_api_key"
            elif key == "together":
                attr = "together_api_key"
            elif key == "openrouter":
                attr = "openrouter_api_key"
            elif key == "deepseek":
                attr = "deepseek_api_key"
            elif key == "xai":
                attr = "xai_api_key"
            elif key == "gemini":
                attr = "gemini_api_key"
            elif key == "ollama":
                attr = "ollama_api_key"
            elif key in ("lmstudio", "huggingface", "pollinations"):
                continue
            if hasattr(cfg, attr) and not getattr(cfg, attr):
                setattr(cfg, attr, os.environ.get(meta["key_env"], getattr(cfg, attr)))
        LLM_DIR.mkdir(parents=True, exist_ok=True)
        return cfg

    def save(self) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2))

    def llm_key_for(self, provider: str) -> str:
        mapping = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "groq": self.groq_api_key,
            "together": self.together_api_key,
            "openrouter": self.openrouter_api_key,
            "deepseek": self.deepseek_api_key,
            "xai": self.xai_api_key,
            "gemini": self.gemini_api_key,
            "ollama": self.ollama_api_key or "ollama",
            "lmstudio": "lmstudio",
            "huggingface": self.hf_token or "hf",
            "pollinations": self.pollinations_api_key or "pollinations",
            "custom": self.custom_llm_api_key or "custom",
        }
        return mapping.get(provider, self.llm_api_key)

    def llm_base_for(self, provider: str) -> str:
        if provider == "custom" and self.custom_base_url:
            return self.custom_base_url.rstrip("/")
        if self.llm_base_url and provider == self.llm_provider:
            return self.llm_base_url.rstrip("/")
        return LLM_PROVIDERS[provider]["base_url"].rstrip("/")


@dataclass
class HistoryItem:
    id: str
    mode: str
    prompt: str
    model: str
    width: int
    height: int
    path: str
    created_at: str
    seed: int = -1
    status: str = "done"
    meta: dict = field(default_factory=dict)


class HistoryStore:
    def __init__(self, path: Path = HISTORY_PATH):
        self.path = path
        self.items: list[HistoryItem] = []
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.items = []
            return
        try:
            raw = json.loads(self.path.read_text())
            self.items = [HistoryItem(**x) for x in raw]
        except Exception:
            self.items = []

    def save(self) -> None:
        HOME.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(i) for i in self.items], indent=2))

    def add(self, item: HistoryItem) -> None:
        self.items.insert(0, item)
        self.save()


# ---------------------------------------------------------------------------
# Backend: BFL FLUX protocols (image + video) — all in-process
# ---------------------------------------------------------------------------

def flux_meta(model_key: str) -> dict[str, Any]:
    if model_key in FLUX_MODELS:
        return FLUX_MODELS[model_key]
    # raw endpoint fallback
    return {
        "endpoint": model_key if model_key.startswith("flux-") else "flux-2-pro",
        "kind": "video" if "video" in model_key else "image",
        "family": "custom",
        "img2img": True,
    }


class FluxBackend:
    """FLUX client: BFL when keyed; otherwise free Pollinations FLUX (no API key)."""

    API = "https://api.bfl.ai/v1"

    def __init__(self, api_key: str, use_free_backend: bool = True):
        self.api_key = api_key.strip()
        self.use_free_backend = use_free_backend

    def ready(self) -> bool:
        """True if any generation path is available (BFL key or free backend)."""
        return bool(self.api_key) or bool(self.use_free_backend)

    def using_free(self) -> bool:
        return not bool(self.api_key) and bool(self.use_free_backend)

    def generate(
        self,
        prompt: str,
        model_key: str = DEFAULT_FLUX_MODEL,
        width: int = 1024,
        height: int = 1024,
        seed: int = -1,
        input_image: Optional[str] = None,
        input_images: Optional[list[str]] = None,
        mask_image: Optional[str] = None,
        steps: Optional[int] = None,
        guidance: Optional[float] = None,
        safety_tolerance: int = 2,
        output_format: str = "png",
        # FLUX 3 video
        video_mode: str = "t2v",
        video_resolution: str = "hd",
        video_duration: int = 5,
        generate_audio: bool = True,
        start_video: Optional[str] = None,
        keyframes: Optional[list] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> dict:
        meta = flux_meta(model_key)
        kind = meta.get("kind", "image")

        # No BFL key → free Pollinations FLUX path (no signup)
        if not self.api_key:
            if not self.use_free_backend:
                raise RuntimeError("BFL API key missing and free backend disabled.")
            return self._generate_free(
                prompt=prompt,
                model_key=model_key,
                width=width,
                height=height,
                seed=seed,
                kind=kind,
                on_status=on_status,
            )

        endpoint = meta["endpoint"]
        url = f"{self.API}/{endpoint}"

        if kind == "video":
            payload = self._video_payload(
                prompt=prompt,
                video_mode=video_mode,
                video_resolution=video_resolution,
                video_duration=video_duration,
                generate_audio=generate_audio,
                seed=seed,
                input_image=input_image,
                start_video=start_video,
                keyframes=keyframes,
            )
        else:
            payload = self._image_payload(
                prompt=prompt,
                meta=meta,
                width=width,
                height=height,
                seed=seed,
                input_image=input_image,
                input_images=input_images,
                mask_image=mask_image,
                steps=steps,
                guidance=guidance,
                safety_tolerance=safety_tolerance,
                output_format=output_format,
            )

        if on_status:
            on_status(f"Submitting to {model_key}…")

        created = _http_json(
            "POST",
            url,
            headers={"x-key": self.api_key},
            body=payload,
            timeout=180.0,
        )
        request_id = created.get("id")
        polling_url = created.get("polling_url")
        if not request_id or not polling_url:
            raise RuntimeError(f"Unexpected BFL response: {created}")

        if on_status:
            on_status(f"Queued ({str(request_id)[:8]}…) — polling")

        timeout = 900 if kind == "video" else 300
        poll_every = 1.0 if kind == "video" else 0.6
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(poll_every)
            result = _http_json(
                "GET",
                polling_url,
                headers={"x-key": self.api_key},
            )
            status = result.get("status", "")
            if on_status:
                on_status(f"{model_key}: {status}")
            if status == "Ready":
                sample = (result.get("result") or {}).get("sample")
                if not sample:
                    raise RuntimeError(f"Ready but no sample URL: {result}")
                return {
                    "id": request_id,
                    "url": sample,
                    "raw": result,
                    "model": model_key,
                    "endpoint": endpoint,
                    "kind": kind,
                }
            if status in ("Error", "Failed"):
                raise RuntimeError(f"{model_key} failed: {result}")
        raise RuntimeError(f"{model_key} timed out waiting for result")

    def _generate_free(
        self,
        prompt: str,
        model_key: str,
        width: int,
        height: int,
        seed: int,
        kind: str,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """Keyless FLUX-style generation via Pollinations (image.pollinations.ai)."""
        import urllib.parse

        free_model = FREE_FLUX_MODEL_MAP.get(model_key, "flux")
        # Pollinations caps; keep reasonable
        w = max(256, min(int(width), 1280))
        h = max(256, min(int(height), 1280))
        # snap to multiples of 16
        w = (w // 16) * 16
        h = (h // 16) * 16
        if seed is None or int(seed) < 0:
            seed = random.randint(0, 2**31 - 1)

        note = ""
        if kind == "video":
            note = " (free mode: cinematic still — BFL key unlocks FLUX 3 video)"
            if on_status:
                on_status("Free mode: generating cinematic still (no key)…")
        elif on_status:
            on_status(f"Free FLUX via Pollinations ({free_model}) — no API key…")

        q = urllib.parse.quote(prompt.strip()[:1800] or "abstract light")
        params = (
            f"width={w}&height={h}&model={urllib.parse.quote(free_model)}"
            f"&seed={int(seed)}&nologo=true&enhance=false&safe=false"
        )
        url = FREE_IMAGE_API.format(prompt=q) + "?" + params
        if on_status:
            on_status("Downloading free FLUX result…")

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OpenPhoto/0.1", "Accept": "image/*"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180.0) as resp:
                data = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"Free FLUX HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Free FLUX network error: {e.reason}") from e

        if not data or len(data) < 100:
            raise RuntimeError("Free FLUX returned an empty image.")

        if on_status:
            on_status(f"Free FLUX ready{note}")

        return {
            "id": f"free-{uuid.uuid4().hex[:10]}",
            "url": "",
            "data": data,
            "raw": {"provider": "pollinations", "model": free_model, "note": note.strip()},
            "model": model_key,
            "endpoint": f"pollinations:{free_model}",
            "kind": "image",
            "free": True,
        }

    def _image_payload(
        self,
        prompt: str,
        meta: dict,
        width: int,
        height: int,
        seed: int,
        input_image: Optional[str],
        input_images: Optional[list[str]],
        mask_image: Optional[str],
        steps: Optional[int],
        guidance: Optional[float],
        safety_tolerance: int,
        output_format: str,
    ) -> dict[str, Any]:
        endpoint = meta["endpoint"]
        payload: dict[str, Any] = {"prompt": prompt}

        # Ultra uses aspect_ratio more often; still accept width/height when set
        if "ultra" in endpoint:
            # map common sizes to aspect_ratio; keep wh as fallback
            payload["width"] = int(width)
            payload["height"] = int(height)
        else:
            payload["width"] = int(width)
            payload["height"] = int(height)

        if seed is not None and int(seed) >= 0:
            payload["seed"] = int(seed)
        if safety_tolerance is not None:
            payload["safety_tolerance"] = int(safety_tolerance)
        if output_format in ("png", "jpeg"):
            payload["output_format"] = output_format

        if meta.get("flex_controls"):
            if steps is not None:
                payload["steps"] = int(steps)
            if guidance is not None:
                payload["guidance"] = float(guidance)

        if input_image:
            # Kontext / fill / flux2 img2img
            if "kontext" in endpoint:
                payload["input_image"] = input_image
            elif meta.get("fill_mask"):
                payload["image"] = input_image
                if mask_image:
                    payload["mask"] = mask_image
                else:
                    # without mask, still send as image for fill-style endpoints
                    payload["input_image"] = input_image
            else:
                payload["input_image"] = input_image

        if input_images:
            for i, img in enumerate(input_images[:8], start=2):
                payload[f"input_image_{i}"] = img

        return payload

    def _video_payload(
        self,
        prompt: str,
        video_mode: str,
        video_resolution: str,
        video_duration: int,
        generate_audio: bool,
        seed: int,
        input_image: Optional[str],
        start_video: Optional[str],
        keyframes: Optional[list],
    ) -> dict[str, Any]:
        mode = video_mode if video_mode in ("t2v", "i2v", "v2v") else "t2v"
        payload: dict[str, Any] = {
            "mode": mode,
            "prompt": prompt,
            "resolution": video_resolution if video_resolution in ("hd", "fhd") else "hd",
            "duration": int(video_duration) if video_duration else 5,
            "generate_audio": bool(generate_audio),
        }
        if seed is not None and int(seed) >= 0:
            payload["seed"] = int(seed)
        if mode == "i2v":
            if keyframes:
                payload["keyframes"] = keyframes
            elif input_image:
                payload["keyframes"] = [input_image]
            else:
                raise RuntimeError("Image-to-video needs an input image (or keyframes).")
        if mode == "v2v":
            if not start_video:
                raise RuntimeError("Video continuation needs a start_video clip.")
            payload["start_video"] = start_video
        return payload

    def save_result(
        self,
        sample_url: str,
        out_dir: Path,
        stem: str,
        kind: str = "image",
        data: Optional[bytes] = None,
    ) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        if data is None:
            data = _download_bytes(sample_url)
        ext = ".png"
        if kind == "video" or data[4:8] == b"ftyp" or data[:4] == b"\x00\x00\x00":
            if b"ftyp" in data[:64] or kind == "video":
                ext = ".mp4"
        if data[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = ".webp"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif data[:4] == b"GIF8":
            ext = ".gif"
        path = out_dir / f"{stem}{ext}"
        path.write_bytes(data)
        return path


# Alias for clarity / DiffusionBee-style naming
Flux2Backend = FluxBackend


# ---------------------------------------------------------------------------
# Backend: multi-LLM engine
# ---------------------------------------------------------------------------

class LLMBackend:
    """Talks to OpenAI-compatible, Anthropic, Gemini, and local LLM servers."""

    def __init__(self, config: AppConfig):
        self.cfg = config

    def list_providers(self) -> list[tuple[str, str]]:
        return [(k, v["label"]) for k, v in LLM_PROVIDERS.items()]

    def chat(
        self,
        messages: list[dict],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        provider = provider or self.cfg.llm_provider
        model = model or self.cfg.llm_model
        meta = LLM_PROVIDERS.get(provider)
        if not meta:
            raise RuntimeError(f"Unknown LLM provider: {provider}")

        style = meta["style"]
        if style == "openai":
            return self._openai_chat(provider, model, messages, temperature)
        if style == "anthropic":
            return self._anthropic_chat(model, messages, temperature)
        if style == "gemini":
            return self._gemini_chat(model, messages, temperature)
        if style == "pollinations":
            return self._pollinations_chat(model, messages)
        raise RuntimeError(f"Unsupported LLM style: {style}")

    def enhance_prompt(self, prompt: str, mode: str = "txt2img", vibe: str = "") -> str:
        # Short free-LLM ask first (long system prompts can 402 on anonymous APIs)
        short = (
            "Rewrite into one rich FLUX image prompt under 80 words. "
            "Return only the prompt.\n"
            f"Vibe: {vibe or 'cinematic natural light'}\n"
            f"Idea: {prompt}"
        )
        if mode in ("txt2vid", "video"):
            short = (
                "Rewrite into one FLUX 3 video prompt under 80 words with camera motion. "
                "Return only the prompt.\n"
                f"Vibe: {vibe or 'cinematic'}\n"
                f"Idea: {prompt}"
            )
        try:
            if self.cfg.llm_provider == "pollinations":
                out = self._pollinations_chat(self.cfg.llm_model, [{"role": "user", "content": short}])
            else:
                out = self.chat([{"role": "user", "content": short}])
            out = (out or "").strip().strip('"')
            if out and len(out) > 12:
                return out
        except Exception:
            pass
        # Always-available offline enhancer (no API key)
        return self._local_vibe_enhance(prompt, mode, vibe)

    def _local_vibe_enhance(self, prompt: str, mode: str, vibe: str) -> str:
        base = prompt.strip().rstrip(".")
        vibe = (vibe or "clean modern FLUX look").strip()
        extras = (
            "high detail, coherent composition, natural materials, "
            "soft volumetric light, 50mm lens, shallow depth of field"
        )
        if mode in ("txt2vid", "video"):
            extras = "slow camera push-in, ambient motion, cinematic color grade, 24fps feel"
        if mode in ("img2img", "inpaint", "canvas"):
            extras = "preserve identity and layout, subtle edit, consistent lighting"
        return f"{base}, {vibe}, {extras}"

    def _pollinations_chat(self, model: str, messages: list[dict]) -> str:
        """Free text generation — no API key required (anonymous Pollinations)."""
        import urllib.parse

        system = ""
        user_bits = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                user_bits.append(m.get("content", ""))
        user = "\n".join(user_bits).strip() or "Hello"
        if system:
            prompt = f"{system.strip()}\n\nUser request:\n{user}"
        else:
            prompt = user
        # keep URL short — anonymous endpoint is picky about huge prompts
        prompt = prompt[:2200]
        q = urllib.parse.quote(prompt)
        urls = [
            f"https://text.pollinations.ai/{q}",
            f"https://text.pollinations.ai/{q}?model={urllib.parse.quote(model or 'openai')}",
        ]
        last_err: Optional[Exception] = None
        for url in urls:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 OpenPhoto/0.1",
                    "Accept": "text/plain",
                    "Referer": "https://pollinations.ai/",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=120.0) as resp:
                    return resp.read().decode("utf-8", errors="replace").strip()
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:300]
                last_err = RuntimeError(f"Free LLM HTTP {e.code}: {body}")
                continue
            except urllib.error.URLError as e:
                last_err = RuntimeError(f"Free LLM network error: {e.reason}")
                continue
        raise last_err or RuntimeError("Free LLM failed")

    def _openai_chat(self, provider, model, messages, temperature) -> str:
        base = self.cfg.llm_base_for(provider)
        key = self.cfg.llm_key_for(provider)
        body = {"model": model, "messages": messages, "temperature": temperature}
        headers = {"Authorization": f"Bearer {key}"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://localhost/openphoto"
            headers["X-Title"] = APP_NAME
        data = _http_json("POST", f"{base}/chat/completions", headers=headers, body=body)
        return data["choices"][0]["message"]["content"]

    def _anthropic_chat(self, model, messages, temperature) -> str:
        key = self.cfg.anthropic_api_key or self.cfg.llm_key_for("anthropic")
        system = ""
        chat_msgs = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_msgs.append({"role": m["role"], "content": m["content"]})
        body = {
            "model": model,
            "max_tokens": 1024,
            "temperature": temperature,
            "messages": chat_msgs,
        }
        if system:
            body["system"] = system
        data = _http_json(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
            body=body,
        )
        parts = data.get("content") or []
        return "".join(p.get("text", "") for p in parts if p.get("type") == "text")

    def _gemini_chat(self, model, messages, temperature) -> str:
        key = self.cfg.gemini_api_key or self.cfg.llm_key_for("gemini")
        # flatten to gemini contents
        contents = []
        system = ""
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
                continue
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        data = _http_json("POST", url, body=body)
        cands = data.get("candidates") or []
        if not cands:
            raise RuntimeError(f"Gemini empty response: {data}")
        parts = cands[0].get("content", {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)


# ---------------------------------------------------------------------------
# Job engine (DiffusionBee-style async queue)
# ---------------------------------------------------------------------------

@dataclass
class GenJob:
    id: str
    mode: str
    prompt: str
    model: str
    width: int
    height: int
    seed: int = -1
    input_image: Optional[str] = None
    start_video: Optional[str] = None
    video_mode: str = "t2v"
    video_resolution: str = "hd"
    video_duration: int = 5
    generate_audio: bool = True
    enhance: bool = False
    status: str = "queued"
    message: str = ""
    result_path: str = ""
    error: str = ""


class DiffusionEngine:
    """Central backend: all BFL FLUX protocols + LLMs + history (DiffusionBee-style)."""

    def __init__(self, config: AppConfig, history: HistoryStore, hf_store: Optional["HuggingFaceLLMStore"] = None):
        self.cfg = config
        self.history = history
        self.hf_store = hf_store
        self.active_vibe = ""
        self.flux = FluxBackend(config.bfl_api_key, use_free_backend=config.use_free_backend)
        self.llm = LLMBackend(config)
        self._q: queue.Queue[GenJob] = queue.Queue()
        self._listeners: list[Callable[[GenJob], None]] = []
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()
        self.jobs: dict[str, GenJob] = {}

    def reload_keys(self) -> None:
        self.flux = FluxBackend(self.cfg.bfl_api_key, use_free_backend=self.cfg.use_free_backend)
        self.llm = LLMBackend(self.cfg)
        if self.hf_store is not None:
            self.hf_store.hf_token = self.cfg.hf_token

    def resolve_vibe(self) -> str:
        if self.active_vibe:
            return self.active_vibe
        if self.hf_store and self.cfg.hf_active_llm:
            for item in self.hf_store.catalog():
                if item.get("name") == self.cfg.hf_active_llm:
                    return item.get("vibe", "")
        return ""

    def on_job(self, cb: Callable[[GenJob], None]) -> None:
        self._listeners.append(cb)

    def _emit(self, job: GenJob) -> None:
        for cb in list(self._listeners):
            try:
                cb(job)
            except Exception:
                pass

    def enqueue(self, **kwargs) -> GenJob:
        job = GenJob(id=uuid.uuid4().hex[:12], **kwargs)
        self.jobs[job.id] = job
        self._q.put(job)
        self._emit(job)
        return job

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.4)
            except queue.Empty:
                continue
            try:
                self._run(job)
            except Exception as e:
                job.status = "error"
                job.error = str(e)
                job.message = str(e)
                self._emit(job)

    def _run(self, job: GenJob) -> None:
        job.status = "running"
        job.message = "Starting…"
        self._emit(job)

        prompt = job.prompt.strip()
        if not prompt:
            raise RuntimeError("Prompt is empty")

        if job.enhance and job.mode != "llm":
            job.message = "Enhancing prompt with LLM…"
            self._emit(job)
            try:
                prompt = self.llm.enhance_prompt(prompt, job.mode, vibe=self.resolve_vibe())
                job.message = f"Enhanced prompt ready"
                self._emit(job)
            except Exception as e:
                job.message = f"LLM enhance skipped: {e}"
                self._emit(job)

        if job.mode == "llm":
            job.message = "Chatting with LLM…"
            self._emit(job)
            out = self.llm.chat([{"role": "user", "content": prompt}])
            out_dir = Path(self.cfg.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"llm_{job.id}.txt"
            path.write_text(out)
            job.result_path = str(path)
            job.status = "done"
            job.message = "LLM response saved"
            self.history.add(
                HistoryItem(
                    id=job.id,
                    mode="llm",
                    prompt=job.prompt,
                    model=f"{self.cfg.llm_provider}/{self.cfg.llm_model}",
                    width=0,
                    height=0,
                    path=str(path),
                    created_at=datetime.now().isoformat(timespec="seconds"),
                    meta={"response_preview": out[:400]},
                )
            )
            self._emit(job)
            return

        seed = job.seed if job.seed >= 0 else self.cfg.seed
        if seed < 0:
            seed = random.randint(0, 2**31 - 1)

        def status_cb(msg: str):
            job.message = msg
            self._emit(job)

        meta = flux_meta(job.model)
        use_flex = bool(meta.get("flex_controls"))
        is_video = meta.get("kind") == "video" or job.mode in ("txt2vid", "video")

        result = self.flux.generate(
            prompt=prompt,
            model_key=job.model,
            width=job.width,
            height=job.height,
            seed=seed,
            input_image=job.input_image,
            start_video=job.start_video,
            steps=self.cfg.steps if use_flex else None,
            guidance=self.cfg.guidance if use_flex else None,
            safety_tolerance=self.cfg.safety_tolerance,
            output_format=self.cfg.output_format,
            video_mode=job.video_mode or self.cfg.video_mode,
            video_resolution=job.video_resolution or self.cfg.video_resolution,
            video_duration=job.video_duration or self.cfg.video_duration,
            generate_audio=job.generate_audio if job.generate_audio is not None else self.cfg.video_audio,
            on_status=status_cb,
        )

        out_dir = Path(self.cfg.output_dir)
        kind = result.get("kind") or ("video" if is_video else "image")
        prefix = "flux3" if kind == "video" or meta.get("family") == "flux3" else "flux"
        path = self.flux.save_result(
            result.get("url") or "",
            out_dir,
            f"{prefix}_{job.id}",
            kind=kind,
            data=result.get("data"),
        )
        job.result_path = str(path)
        job.status = "done"
        job.message = f"Saved {path.name}"
        self.history.add(
            HistoryItem(
                id=job.id,
                mode=job.mode,
                prompt=prompt,
                model=job.model,
                width=job.width,
                height=job.height,
                path=str(path),
                created_at=datetime.now().isoformat(timespec="seconds"),
                seed=seed,
                meta={
                    "bfl_id": result.get("id"),
                    "original_prompt": job.prompt,
                    "kind": kind,
                    "endpoint": result.get("endpoint"),
                },
            )
        )
        self._emit(job)

    def shutdown(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------------------
# UI previews
# ---------------------------------------------------------------------------

class ToolPreview(tk.Canvas):
    def __init__(self, master, kind, height=140, **kwargs):
        super().__init__(master, height=height, bg=SIDEBAR, highlightthickness=0, **kwargs)
        self.kind = kind
        self.bind("<Configure>", self._redraw)

    def _redraw(self, _event=None):
        self.delete("all")
        w = max(self.winfo_width(), 10)
        h = max(self.winfo_height(), 10)
        k = self.kind
        if k == "astronaut":
            self._astronaut(w, h)
        elif k == "tree":
            self._tree(w, h)
        elif k == "canvas":
            self._canvas_scene(w, h)
        elif k == "illusion":
            self._illusion(w, h)
        elif k == "inpaint":
            self._inpaint(w, h)
        else:
            self._face(w, h)

    def _gradient_rect(self, x0, y0, x1, y1, c1, c2, steps=36):
        def rgb(c): return tuple(int(c[i:i+2], 16) for i in (1,3,5))
        a, b = rgb(c1), rgb(c2)
        for i in range(steps):
            t = i / max(steps-1, 1)
            c = "#%02x%02x%02x" % tuple(int(a[j]*(1-t)+b[j]*t) for j in range(3))
            yy0 = y0 + (y1-y0)*i/steps
            yy1 = y0 + (y1-y0)*(i+1)/steps + 1
            self.create_rectangle(x0, yy0, x1, yy1, fill=c, outline="")

    def _astronaut(self, w, h):
        self._gradient_rect(0,0,w,h,"#06142d","#9cd5ec")
        self.create_oval(-w*.1, h*.58, w*1.15, h*1.15, fill="#f6f8fb", outline="")
        self.create_oval(w*.58,h*.02,w*.78,h*.34,fill="#eeeeea",outline="")
        self.create_oval(w*.615,h*.07,w*.735,h*.19,fill="#18222b",outline="#b9c3c9",width=2)
        self.create_polygon(w*.62,h*.27,w*.76,h*.27,w*.83,h*.66,w*.53,h*.67,
                            fill="#e7e6df",outline="#bfc3c6",width=2)
        self.create_oval(w*.18,h*.35,w*.71,h*.94,fill="#743c1f",outline="#2a160c",width=3)
        self.create_polygon(w*.18,h*.42,w*.10,h*.22,w*.32,h*.13,w*.39,h*.49,
                            fill="#7c4325",outline="#2a160c",width=3)
        self.create_oval(w*.12,h*.28,w*.18,h*.34,fill="#111",outline="")
        self.create_line(w*.10,h*.36,w*.38,h*.42,fill="#275cff",width=5)
        self.create_line(w*.71,h*.58,w*.95,h*.48,fill="#2e1a11",width=9)
        self.create_arc(w*.68,h*.55,w*.98,h*.90,start=220,extent=130,style="arc",outline="#26120c",width=8)

    def _tree(self, w, h):
        self.create_rectangle(0,0,w/2,h,fill="#f5d9c4",outline="")
        self.create_rectangle(w/2,0,w,h,fill="#b8d7de",outline="")
        colors=["#f05033","#ff8c21","#ffd643","#54c72d","#19a7d8","#354bd4"]
        for i,c in enumerate(colors):
            y=h*.08+i*h*.045
            self.create_arc(w*.06,y,w*.47,h*.65,start=10+i*12,extent=100,
                            style="arc",outline=c,width=8)
        self.create_polygon(w*.22,h*.38,w*.33,h*.28,w*.39,h*.66,w*.19,h*.66,
                            fill="#d84c43",outline="#733")
        self.create_oval(w*.06,h*.62,w*.45,h*.90,fill="#38a834",outline="#176b1e",width=3)
        self.create_rectangle(w*.73,h*.44,w*.78,h*.87,fill="#96524f",outline="")
        for x,y,r,c in [(0.73,.31,.20,"#64d33e"),(.82,.28,.19,"#84e83f"),
                        (.66,.38,.16,"#45b933"),(.84,.42,.15,"#77cc35")]:
            self.create_oval(w*(x-r),h*(y-r),w*(x+r),h*(y+r),fill=c,outline="")
        self.create_oval(w*.52,h*.73,w*.98,h*1.04,fill="#83c945",outline="")
        self.create_text(w*.5,h*.5,text="➜",fill="#ff3d15",font=("Arial",42,"bold"))

    def _canvas_scene(self, w, h):
        self.create_rectangle(0,0,w,h,fill="#ece9e4",outline="")
        self.create_rectangle(w*.45,0,w,h,fill="#72543c",outline="")
        self.create_rectangle(w*.75,0,w,h*.35,fill="#d9f0f8",outline="#222",width=4)
        self.create_oval(w*.55,h*.14,w*.81,h*.90,fill="#b4c1ca",outline="")
        self.create_oval(w*.62,h*.16,w*.73,h*.32,fill="#dfba9b",outline="")
        self.create_polygon(w*.57,h*.38,w*.77,h*.34,w*.82,h,w*.51,h,
                            fill="#5f432d",outline="")
        self.create_oval(w*.63,h*.31,w*.75,h*.46,fill="#202a3c",outline="")
        self.create_oval(w*.75,h*.70,w*.84,h*.89,fill="#83b64f",outline="")
        self.create_rectangle(w*.15,h*.45,w*.47,h*.98,fill="#f8f8f8",
                              outline="#8fb5ff",width=2)
        self.create_text(w*.31,h*.72,text="+",fill="#444",font=("Arial",18))

    def _illusion(self, w, h):
        self._gradient_rect(0,0,w,h,"#a1bad0","#f1d9b7")
        cx=w*.50
        for i in range(6):
            r=(i+1)*w*.09
            self.create_arc(cx-r,h*.44-r,cx+r,h*.44+r,start=12,extent=155,
                            style="arc",outline="#f7f7ee",width=16)
        self.create_rectangle(0,h*.69,w,h,fill="#677b3b",outline="")
        for x in [0.08,.20,.33,.72,.87]:
            self.create_rectangle(w*x,h*.53,w*(x+.08),h*.78,fill="#9b7f5d",outline="#403626")
            self.create_polygon(w*(x-.03),h*.54,w*(x+.12),h*.54,w*(x+.08),h*.40,w*(x+.02),h*.38,
                                fill="#4d4a4a",outline="")

    def _inpaint(self, w, h):
        self._gradient_rect(0,0,w,h,"#0f3f38","#8b6445")
        self.create_rectangle(0,h*.67,w,h,fill="#334334",outline="")
        self.create_rectangle(w*.22,h*.55,w*.82,h*.76,fill="#17625f",outline="#233",width=4)
        self.create_rectangle(w*.28,h*.48,w*.75,h*.55,fill="#18554f",outline="")
        self.create_oval(w*.40,h*.08,w*.64,h*.72,fill="#ee29df",outline="")
        self.create_oval(w*.45,h*.14,w*.59,h*.31,fill="#f04be9",outline="")
        self.create_oval(w*.48,h*.17,w*.52,h*.22,fill="#ede0ea",outline="")
        self.create_oval(w*.55,h*.17,w*.59,h*.22,fill="#ede0ea",outline="")

    def _face(self, w, h):
        self._gradient_rect(0,0,w,h,"#644333","#243a3c")
        self.create_oval(w*.21,-h*.20,w*.88,h*1.25,fill="#e4c0aa",outline="")
        self.create_arc(w*.15,-h*.28,w*.93,h*.62,start=20,extent=210,
                        fill="#c9a06e",outline="#c9a06e",width=10)
        for x in (.44,.69):
            self.create_oval(w*(x-.055),h*.31,w*(x+.055),h*.43,fill="#eaf5f3",outline="")
            self.create_oval(w*(x-.022),h*.335,w*(x+.022),h*.39,fill="#4a9ca1",outline="")
            self.create_oval(w*(x-.008),h*.345,w*(x+.008),h*.38,fill="#111",outline="")
        self.create_arc(w*.47,h*.54,w*.73,h*.77,start=190,extent=150,style="arc",outline="#a86f66",width=3)
        self.create_line(w*.86,h*.72,w*.94,h*.63,fill="white",width=16,arrow="last",arrowshape=(18,22,10))
        self.create_line(w*.86,h*.85,w*.75,h*.95,fill="white",width=16,arrow="last",arrowshape=(18,22,10))


# ---------------------------------------------------------------------------
# Hugging Face LLM download + vibe-add window (same .py — not a separate app)
# ---------------------------------------------------------------------------

class LLMDownloadWindow(tk.Toplevel):
    def __init__(self, app: "App"):
        super().__init__(app)
        self.app = app
        self.title(f"Download LLMs — {APP_TITLE}")
        self.geometry("1080x760")
        self.configure(bg=BG)
        self._busy = False
        self.store = app.hf_store
        self.store.hf_token = app.cfg.hf_token
        self.store.sync_provider_models()

        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=24, pady=(20, 8))
        tk.Label(head, text="Download LLMs", bg=BG, fg=TEXT, font=("Arial", 26, "bold")).pack(anchor="w")
        tk.Label(
            head,
            text="Pre-baked Hugging Face GGUFs for FLUX vibes · download into ~/.openphoto/llms · vibe-add any repo",
            bg=BG, fg=MUTED, font=("Arial", 13),
        ).pack(anchor="w", pady=(4, 0))

        # Vibe add strip
        vibe_box = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        vibe_box.pack(fill="x", padx=24, pady=(12, 8))
        tk.Label(vibe_box, text="Vibe add (Hugging Face)", bg=PANEL, fg=TEXT,
                 font=("Arial", 14, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        form = tk.Frame(vibe_box, bg=PANEL)
        form.pack(fill="x", padx=14, pady=(0, 12))

        self.vibe_name = tk.StringVar()
        self.vibe_repo = tk.StringVar()
        self.vibe_file = tk.StringVar()
        self.vibe_text = tk.StringVar(value="cinematic FLUX prompt vibe")

        def field(parent, label, var, width=36, row=0, col=0):
            tk.Label(parent, text=label, bg=PANEL, fg=MUTED, font=("Arial", 11)).grid(
                row=row, column=col, sticky="w", padx=(0, 8)
            )
            tk.Entry(
                parent, textvariable=var, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                relief="flat", width=width,
            ).grid(row=row + 1, column=col, sticky="w", padx=(0, 14), pady=(2, 0))

        field(form, "Display name", self.vibe_name, 22, 0, 0)
        field(form, "HF repo (org/name or URL)", self.vibe_repo, 34, 0, 1)
        field(form, ".gguf file", self.vibe_file, 34, 0, 2)
        field(form, "Vibe", self.vibe_text, 28, 0, 3)

        btns = tk.Frame(vibe_box, bg=PANEL)
        btns.pack(fill="x", padx=14, pady=(0, 12))
        tk.Button(
            btns, text="Vibe add", command=self._vibe_add,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 12, "bold"), padx=14, pady=7,
        ).pack(side="left")
        tk.Button(
            btns, text="List .gguf in repo", command=self._list_repo,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 12), padx=12, pady=7,
        ).pack(side="left", padx=8)
        tk.Label(
            btns, text="Tip: paste a full huggingface.co/…/resolve/main/….gguf URL into repo",
            bg=PANEL, fg=MUTED, font=("Arial", 11),
        ).pack(side="left", padx=8)

        # Catalog list
        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=24, pady=8)

        left = tk.Frame(mid, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Catalog (pre-installed + vibes)", bg=BG, fg=MUTED,
                 font=("Arial", 12)).pack(anchor="w")
        self.listbox = tk.Listbox(
            left, bg=PANEL, fg=TEXT, selectbackground=BLUE, font=("Menlo", 12),
            relief="flat", highlightthickness=1, highlightbackground=BORDER,
            activestyle="none",
        )
        self.listbox.pack(fill="both", expand=True, pady=(6, 0))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        right = tk.Frame(mid, bg=PANEL, width=340, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)
        tk.Label(right, text="Selected LLM", bg=PANEL, fg=TEXT,
                 font=("Arial", 14, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.detail = tk.Label(
            right, text="Pick a model from the catalog.",
            bg=PANEL, fg=MUTED, font=("Arial", 12), justify="left", wraplength=300,
        )
        self.detail.pack(anchor="w", padx=14, pady=(0, 12))

        self.progress = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=14, pady=(4, 6))
        self.status = tk.Label(right, text="Ready", bg=PANEL, fg=MUTED, font=("Arial", 11),
                               wraplength=300, justify="left")
        self.status.pack(anchor="w", padx=14)

        self.dl_btn = tk.Button(
            right, text="Download", command=self._download_selected,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 13, "bold"), padx=16, pady=10,
        )
        self.dl_btn.pack(anchor="w", padx=14, pady=(16, 6))
        tk.Button(
            right, text="Use vibe for enhance", command=self._use_vibe,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 12), padx=12, pady=8,
        ).pack(anchor="w", padx=14, pady=4)
        tk.Button(
            right, text="Reveal folder", command=lambda: self._reveal(LLM_DIR),
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 12), padx=12, pady=8,
        ).pack(anchor="w", padx=14, pady=4)
        tk.Label(
            right,
            text="Weights stay local. Point Ollama / LM Studio / llama.cpp at ~/.openphoto/llms after download.",
            bg=PANEL, fg=MUTED, font=("Arial", 11), wraplength=300, justify="left",
        ).pack(anchor="w", padx=14, pady=(18, 14))

        self._items: list[dict[str, Any]] = []
        self._selected: Optional[dict[str, Any]] = None
        self.refresh()

    def refresh(self):
        self.store.load()
        self.store.sync_provider_models()
        self._items = self.store.catalog()
        self.listbox.delete(0, "end")
        for item in self._items:
            mark = "✓" if self.store.is_downloaded(item) else "·"
            src = item.get("source", "prebaked")
            self.listbox.insert(
                "end",
                f"{mark}  {item['name']}  [{src}]  {item.get('size_hint', '')}  —  {item.get('vibe', '')[:40]}",
            )

    def _on_select(self, _evt=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        item = self._items[sel[0]]
        self._selected = item
        state = "Downloaded" if self.store.is_downloaded(item) else "Not downloaded"
        self.detail.configure(
            text=(
                f"{item['name']}\n\n"
                f"Repo: {item['repo']}\n"
                f"File: {item['file']}\n"
                f"Size: {item.get('size_hint', '?')}\n"
                f"Status: {state}\n\n"
                f"Vibe: {item.get('vibe', '')}\n"
                f"Tags: {', '.join(item.get('tags') or [])}"
            ),
            fg=TEXT,
        )
        self.dl_btn.configure(text="Re-download" if self.store.is_downloaded(item) else "Download")

    def _vibe_add(self):
        try:
            item = self.store.vibe_add(
                name=self.vibe_name.get(),
                repo=self.vibe_repo.get(),
                file=self.vibe_file.get(),
                vibe=self.vibe_text.get(),
                tags=["flux", "vibe"],
            )
            self.status.configure(text=f"Vibe added: {item['name']}", fg=OK)
            self.refresh()
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def _list_repo(self):
        repo = self.vibe_repo.get().strip()
        if not repo:
            messagebox.showwarning(APP_NAME, "Enter a Hugging Face repo first.")
            return

        def work():
            try:
                self.after(0, lambda: self.status.configure(text="Listing repo…", fg=WARN))
                files = self.store.list_repo_ggufs(repo)
                def done():
                    if not files:
                        self.status.configure(text="No .gguf files found (check repo / HF token).", fg=ERR)
                        return
                    # pick first Q4_K_M if present
                    pick = next((f for f in files if "Q4_K_M" in f or "q4_k_m" in f), files[0])
                    self.vibe_file.set(pick)
                    self.status.configure(text=f"Found {len(files)} GGUF(s). Selected {Path(pick).name}", fg=OK)
                self.after(0, done)
            except Exception as e:
                self.after(0, lambda: self.status.configure(text=str(e), fg=ERR))

        threading.Thread(target=work, daemon=True).start()

    def _download_selected(self):
        if self._busy:
            return
        if not self._selected:
            messagebox.showwarning(APP_NAME, "Select an LLM from the catalog.")
            return
        item = self._selected
        self._busy = True
        self.dl_btn.configure(state="disabled")
        self.progress["value"] = 0

        def work():
            try:
                def prog(done, total, msg):
                    def ui():
                        self.status.configure(text=msg, fg=WARN)
                        if total:
                            self.progress["value"] = min(100, int(100 * done / total))
                    self.after(0, ui)

                path = self.store.download(item, on_progress=prog)

                def done():
                    self._busy = False
                    self.dl_btn.configure(state="normal")
                    self.progress["value"] = 100
                    self.status.configure(text=f"Ready: {path}", fg=OK)
                    self.app.cfg.hf_active_llm = item["name"]
                    self.app.cfg.save()
                    self.refresh()
                    self._on_select()
                    if self.app.status_pill:
                        self.app.status_pill.configure(text=self.app._backend_status_text())
                self.after(0, done)
            except Exception as e:
                def fail():
                    self._busy = False
                    self.dl_btn.configure(state="normal")
                    self.status.configure(text=str(e), fg=ERR)
                    messagebox.showerror(APP_NAME, f"Download failed:\n{e}")
                self.after(0, fail)

        threading.Thread(target=work, daemon=True).start()

    def _use_vibe(self):
        if not self._selected:
            messagebox.showwarning(APP_NAME, "Select an LLM first.")
            return
        self.app.cfg.hf_active_llm = self._selected["name"]
        self.app.active_vibe = self._selected.get("vibe", "")
        self.app.engine.active_vibe = self.app.active_vibe
        self.app.cfg.save()
        self.status.configure(
            text=f"Active vibe: {self.app.active_vibe}",
            fg=OK,
        )
        if self.app.status_pill:
            self.app.status_pill.configure(text=self.app._backend_status_text())
        messagebox.showinfo(
            APP_NAME,
            f"Vibe set for prompt enhance:\n{self.app.active_vibe}\n\n"
            f"Local file (if downloaded):\n{self.store.local_path(self._selected)}",
        )

    def _reveal(self, path: Path):
        import sys
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "darwin":
                os.system(f'open "{path}"')
            elif sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as e:
            messagebox.showinfo(APP_NAME, f"LLM folder:\n{path}\n\n({e})")


# ---------------------------------------------------------------------------
# Tool workspace window
# ---------------------------------------------------------------------------

class ToolWorkspace(tk.Toplevel):
    def __init__(self, app: "App", title: str, mode: str):
        super().__init__(app)
        self.app = app
        self.mode = mode
        self.is_video = mode in ("txt2vid", "video")
        self.title(f"{title} - {APP_TITLE}")
        self.geometry("980x720")
        self.configure(bg=CONTENT)
        self.input_image_path: Optional[str] = None
        self.start_video_path: Optional[str] = None
        self.result_path: Optional[str] = None
        self._photo = None

        head = tk.Frame(self, bg=CONTENT)
        head.pack(fill="x", padx=28, pady=(22, 8))
        tk.Label(head, text=title, bg=CONTENT, fg=TEXT, font=(UI_FONT, 24, "bold")).pack(anchor="w")
        tk.Label(
            head,
            text="OpenPhoto · DiffusionBee layout · FLUX + multi-LLM",
            bg=CONTENT, fg=MUTED, font=(UI_FONT, 13),
        ).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self, bg=CONTENT)
        body.pack(fill="both", expand=True, padx=28, pady=10)

        # TwoColAppletLayout: left form max ~350px feel via pack
        left = tk.Frame(body, bg=CONTENT, width=350)
        left.pack(side="left", fill="both", expand=False)
        left.pack_propagate(False)

        tk.Label(left, text="Prompt", bg=CONTENT, fg=MUTED, font=(UI_FONT, 12)).pack(anchor="w")
        self.prompt = tk.Text(
            left, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            relief="solid", borderwidth=1, highlightthickness=0,
            font=(UI_FONT, 14), height=8, wrap="word",
        )
        self.prompt.pack(fill="both", expand=True, pady=(6, 12))
        self.prompt.insert("1.0", "Describe what you want to create or edit…")

        opts = tk.Frame(left, bg=CONTENT)
        opts.pack(fill="x", pady=(0, 10))

        model_label = "FLUX 3 video model" if self.is_video else "FLUX model"
        tk.Label(opts, text=model_label, bg=BG, fg=MUTED, font=("Arial", 11)).grid(row=0, column=0, sticky="w")
        model_values = VIDEO_MODEL_NAMES if self.is_video else IMAGE_MODEL_NAMES
        default_model = app.cfg.video_model if self.is_video else app.cfg.flux_model
        if default_model not in model_values and model_values:
            default_model = model_values[0]
        self.model_var = tk.StringVar(value=default_model)
        self.model_menu = ttk.Combobox(
            opts, textvariable=self.model_var, values=model_values,
            state="readonly", width=28,
        )
        self.model_menu.grid(row=1, column=0, sticky="w", padx=(0, 14))

        if self.is_video:
            tk.Label(opts, text="Mode", bg=BG, fg=MUTED, font=("Arial", 11)).grid(row=0, column=1, sticky="w")
            vmode_labels = [n for n, _ in VIDEO_MODES]
            self.vmode_var = tk.StringVar(value=vmode_labels[0])
            ttk.Combobox(opts, textvariable=self.vmode_var, values=vmode_labels, state="readonly", width=22).grid(
                row=1, column=1, sticky="w", padx=(0, 14)
            )
            tk.Label(opts, text="Resolution", bg=BG, fg=MUTED, font=("Arial", 11)).grid(row=0, column=2, sticky="w")
            self.vres_var = tk.StringVar(value=app.cfg.video_resolution)
            ttk.Combobox(opts, textvariable=self.vres_var, values=VIDEO_RESOLUTIONS, state="readonly", width=10).grid(
                row=1, column=2, sticky="w", padx=(0, 14)
            )
            tk.Label(opts, text="Seconds", bg=BG, fg=MUTED, font=("Arial", 11)).grid(row=2, column=0, sticky="w", pady=(10, 0))
            self.vdur_var = tk.StringVar(value=str(app.cfg.video_duration))
            ttk.Combobox(opts, textvariable=self.vdur_var, values=VIDEO_DURATIONS, state="readonly", width=10).grid(
                row=3, column=0, sticky="w", padx=(0, 14)
            )
            self.audio_var = tk.BooleanVar(value=app.cfg.video_audio)
            tk.Checkbutton(
                opts, text="Generate audio", variable=self.audio_var,
                bg=BG, fg=TEXT, selectcolor=PANEL, activebackground=BG, activeforeground=TEXT,
                font=("Arial", 11),
            ).grid(row=3, column=1, sticky="w")
            self.size_var = tk.StringVar(value="")
        else:
            tk.Label(opts, text="Size", bg=BG, fg=MUTED, font=("Arial", 11)).grid(row=0, column=1, sticky="w")
            size_labels = [f"{n} ({w}×{h})" for n, w, h in SIZES]
            default_size = next(
                (f"{n} ({w}×{h})" for n, w, h in SIZES
                 if w == app.cfg.default_width and h == app.cfg.default_height),
                size_labels[0],
            )
            self.size_var = tk.StringVar(value=default_size)
            ttk.Combobox(opts, textvariable=self.size_var, values=size_labels, state="readonly", width=22).grid(
                row=1, column=1, sticky="w", padx=(0, 14)
            )

        tk.Label(opts, text="Seed (-1 random)", bg=BG, fg=MUTED, font=("Arial", 11)).grid(
            row=0 if not self.is_video else 2, column=2 if not self.is_video else 2, sticky="w",
            pady=(10, 0) if self.is_video else 0,
        )
        self.seed_var = tk.StringVar(value=str(app.cfg.seed))
        tk.Entry(opts, textvariable=self.seed_var, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                 relief="flat", width=12).grid(
            row=1 if not self.is_video else 3, column=2, sticky="w"
        )

        self.enhance_var = tk.BooleanVar(value=app.cfg.enhance_prompts)
        tk.Checkbutton(
            left, text="Enhance prompt with LLM before generate",
            variable=self.enhance_var, bg=BG, fg=TEXT, selectcolor=PANEL,
            activebackground=BG, activeforeground=TEXT, font=("Arial", 12),
        ).pack(anchor="w", pady=(4, 8))

        if mode in ("img2img", "inpaint", "canvas", "upscale") or self.is_video:
            row = tk.Frame(left, bg=BG)
            row.pack(fill="x", pady=(0, 8))
            tk.Button(
                row, text="Load input image…", command=self._pick_image,
                bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
                relief="flat", font=("Arial", 12), padx=12, pady=6,
            ).pack(side="left")
            self.img_lbl = tk.Label(row, text="No image selected", bg=BG, fg=MUTED, font=("Arial", 12))
            self.img_lbl.pack(side="left", padx=12)
            if self.is_video:
                tk.Button(
                    row, text="Load start video…", command=self._pick_video,
                    bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
                    relief="flat", font=("Arial", 12), padx=12, pady=6,
                ).pack(side="left", padx=(8, 0))
                self.vid_lbl = tk.Label(row, text="No clip", bg=BG, fg=MUTED, font=("Arial", 12))
                self.vid_lbl.pack(side="left", padx=12)

        btns = tk.Frame(left, bg=BG)
        btns.pack(fill="x", pady=(8, 0))
        self.gen_btn = tk.Button(
            btns, text="Generate" if mode != "llm" else "Run LLM",
            command=self._generate, bg=BLUE, fg="#FFFFFF",
            activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 14, "bold"), padx=22, pady=10,
        )
        self.gen_btn.pack(side="left")
        tk.Button(
            btns, text="Enhance only", command=self._enhance_only,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 12), padx=14, pady=10,
        ).pack(side="left", padx=10)

        self.status = tk.Label(left, text="Ready", bg=BG, fg=MUTED, font=("Arial", 12))
        self.status.pack(anchor="w", pady=(14, 0))

        right = tk.Frame(body, bg=PANEL, width=360, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", padx=(18, 0))
        right.pack_propagate(False)
        tk.Label(right, text="Output", bg=PANEL, fg=TEXT, font=("Arial", 14, "bold")).pack(
            anchor="w", padx=16, pady=(16, 8)
        )
        self.preview = tk.Label(right, text="Waiting for generation…", bg=PANEL, fg=MUTED,
                                font=("Arial", 12), wraplength=300, justify="center")
        self.preview.pack(expand=True, fill="both", padx=12, pady=(12, 4))

        dl = tk.Frame(right, bg=PANEL)
        dl.pack(fill="x", padx=12, pady=(0, 14))
        self.save_desktop_btn = tk.Button(
            dl, text="Save to Desktop", command=self._save_to_desktop,
            bg="black", fg=BLUE, activebackground="#111111", activeforeground=BLUE_HOVER,
            relief="flat", font=("Arial", 12, "bold"), padx=10, pady=7, state="disabled",
        )
        self.save_desktop_btn.pack(side="left")
        self.save_as_btn = tk.Button(
            dl, text="Download / Save As…", command=self._save_as,
            bg="black", fg=BLUE, activebackground="#111111", activeforeground=BLUE_HOVER,
            relief="flat", font=("Arial", 12, "bold"), padx=10, pady=7, state="disabled",
        )
        self.save_as_btn.pack(side="left", padx=(8, 0))

        self.app.engine.on_job(self._on_job)
        self._watching: Optional[str] = None

    def _pick_image(self):
        path = filedialog.askopenfilename(
            title="Select input image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif"), ("All", "*.*")],
        )
        if path:
            self.input_image_path = path
            self.img_lbl.configure(text=Path(path).name, fg=TEXT)

    def _pick_video(self):
        path = filedialog.askopenfilename(
            title="Select start video",
            filetypes=[("Video", "*.mp4 *.mov *.webm"), ("All", "*.*")],
        )
        if path:
            self.start_video_path = path
            if hasattr(self, "vid_lbl"):
                self.vid_lbl.configure(text=Path(path).name, fg=TEXT)

    def _parse_size(self) -> tuple[int, int]:
        label = self.size_var.get() if hasattr(self, "size_var") else ""
        for n, w, h in SIZES:
            if label.startswith(n):
                return w, h
        return self.app.cfg.default_width, self.app.cfg.default_height

    def _seed(self) -> int:
        try:
            return int(self.seed_var.get().strip())
        except Exception:
            return -1

    def _as_input_payload(self) -> Optional[str]:
        if not self.input_image_path:
            return None
        raw = Path(self.input_image_path).read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        return b64

    def _as_video_payload(self) -> Optional[str]:
        if not self.start_video_path:
            return None
        raw = Path(self.start_video_path).read_bytes()
        return base64.b64encode(raw).decode("ascii")

    def _video_mode_code(self) -> str:
        label = getattr(self, "vmode_var", None)
        if not label:
            return "t2v"
        chosen = label.get()
        for name, code in VIDEO_MODES:
            if name == chosen:
                return code
        return "t2v"

    def _generate(self):
        prompt = self.prompt.get("1.0", "end").strip()
        if prompt.startswith("Describe what you want"):
            prompt = ""
        if not prompt:
            messagebox.showwarning(APP_NAME, "Enter a prompt first.")
            return
        if self.mode != "llm" and not self.app.engine.flux.ready():
            messagebox.showwarning(
                APP_NAME,
                "No image backend available. Enable free backend in Settings, or add a BFL key.",
            )
            self.app._select_tab("settings")
            return
        if self.mode in ("img2img", "inpaint", "canvas", "upscale") and not self.input_image_path:
            messagebox.showwarning(APP_NAME, "Load an input image for this mode.")
            return

        vmode = self._video_mode_code() if self.is_video else "t2v"
        if self.is_video and vmode == "i2v" and not self.input_image_path:
            messagebox.showwarning(APP_NAME, "Image-to-video needs an input image.")
            return
        if self.is_video and vmode == "v2v" and not self.start_video_path:
            messagebox.showwarning(APP_NAME, "Video continuation needs a start clip.")
            return

        w, h = self._parse_size()
        try:
            vdur = int(self.vdur_var.get()) if self.is_video else self.app.cfg.video_duration
        except Exception:
            vdur = 5

        job = self.app.engine.enqueue(
            mode=self.mode,
            prompt=prompt,
            model=self.model_var.get(),
            width=w,
            height=h,
            seed=self._seed(),
            input_image=self._as_input_payload() if self.mode != "llm" else None,
            start_video=self._as_video_payload() if self.is_video else None,
            video_mode=vmode,
            video_resolution=self.vres_var.get() if self.is_video else self.app.cfg.video_resolution,
            video_duration=vdur,
            generate_audio=bool(self.audio_var.get()) if self.is_video else self.app.cfg.video_audio,
            enhance=bool(self.enhance_var.get()) and self.mode != "llm",
        )
        self._watching = job.id
        self.status.configure(text=f"Job {job.id}: queued", fg=WARN)
        self.gen_btn.configure(state="disabled")

    def _enhance_only(self):
        prompt = self.prompt.get("1.0", "end").strip()
        if not prompt or prompt.startswith("Describe what you want"):
            messagebox.showwarning(APP_NAME, "Enter a prompt to enhance.")
            return

        def work():
            try:
                self.after(0, lambda: self.status.configure(text="Enhancing…", fg=WARN))
                out = self.app.engine.llm.enhance_prompt(
                    prompt, self.mode, vibe=self.app.engine.resolve_vibe()
                )
                def apply():
                    self.prompt.delete("1.0", "end")
                    self.prompt.insert("1.0", out)
                    self.status.configure(text="Prompt enhanced", fg=OK)
                self.after(0, apply)
            except Exception as e:
                self.after(0, lambda: self.status.configure(text=str(e), fg=ERR))

        threading.Thread(target=work, daemon=True).start()

    def _on_job(self, job: GenJob):
        if job.id != self._watching:
            return

        def ui():
            color = {"queued": WARN, "running": WARN, "done": OK, "error": ERR}.get(job.status, MUTED)
            self.status.configure(text=f"{job.status}: {job.message or job.error}", fg=color)
            if job.status in ("done", "error"):
                self.gen_btn.configure(state="normal")
            if job.status == "done" and job.result_path:
                self._show_result(job.result_path)
                self.app.refresh_history_views()

        self.after(0, ui)

    def _show_result(self, path: str):
        p = Path(path)
        self.result_path = str(p)
        self.save_desktop_btn.configure(state="normal")
        self.save_as_btn.configure(state="normal")
        if p.suffix.lower() == ".txt":
            text = p.read_text()[:1200]
            self.preview.configure(text=text, image="", compound="center")
            self._photo = None
            return
        if p.suffix.lower() in (".mp4", ".mov", ".webm"):
            self._photo = None
            self.preview.configure(
                text=f"Video saved:\n{p.name}\n\n{p}",
                image="",
                compound="center",
            )
            return
        try:
            img = tk.PhotoImage(file=str(p))
            while img.width() > 320 or img.height() > 420:
                img = img.subsample(2, 2)
            self._photo = img
            self.preview.configure(image=img, text="")
        except Exception:
            self.preview.configure(text=f"Saved:\n{p}", image="")

    def _copy_result_to(self, dest: Path) -> bool:
        if not self.result_path:
            messagebox.showwarning(APP_NAME, "Generate something first.")
            return False
        src = Path(self.result_path)
        if not src.is_file():
            messagebox.showerror(APP_NAME, f"File not found:\n{src}")
            return False
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            self.status.configure(text=f"Downloaded: {dest.name}", fg=OK)
            return True
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not save file:\n{e}")
            return False

    def _save_to_desktop(self):
        if not self.result_path:
            messagebox.showwarning(APP_NAME, "Generate something first.")
            return
        src = Path(self.result_path)
        dest = os_desktop_dir() / src.name
        if dest.exists():
            stem, suffix = src.stem, src.suffix
            n = 1
            while dest.exists():
                dest = os_desktop_dir() / f"{stem}_{n}{suffix}"
                n += 1
        if self._copy_result_to(dest):
            messagebox.showinfo(APP_NAME, f"Saved to Desktop:\n{dest}")

    def _save_as(self):
        if not self.result_path:
            messagebox.showwarning(APP_NAME, "Generate something first.")
            return
        src = Path(self.result_path)
        ext = src.suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            filetypes = [
                ("Images", "*.png *.jpg *.jpeg *.webp *.gif"),
                ("All files", "*.*"),
            ]
        elif ext in (".mp4", ".mov", ".webm"):
            filetypes = [("Video", "*.mp4 *.mov *.webm"), ("All files", "*.*")]
        elif ext == ".txt":
            filetypes = [("Text", "*.txt"), ("All files", "*.*")]
        else:
            filetypes = [("All files", "*.*")]
        path = filedialog.asksaveasfilename(
            title="Download / Save As",
            initialdir=str(os_desktop_dir()),
            initialfile=src.name,
            defaultextension=ext or ".png",
            filetypes=filetypes,
        )
        if not path:
            return
        if self._copy_result_to(Path(path)):
            messagebox.showinfo(APP_NAME, f"Saved:\n{path}")


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        # DiffusionBee default ~770×550; slightly larger for comfort, same min
        self.geometry("1100x720")
        self.minsize(770, 550)

        self.cfg = AppConfig.load()
        apply_theme(self.cfg.dark_mode)
        self.configure(bg=CONTENT)
        self.history = HistoryStore()
        self.hf_store = HuggingFaceLLMStore(self.cfg.hf_token)
        self.hf_store.sync_provider_models()
        self.active_vibe = ""
        if self.cfg.hf_active_llm:
            for item in self.hf_store.catalog():
                if item.get("name") == self.cfg.hf_active_llm:
                    self.active_vibe = item.get("vibe", "")
                    break
        self.engine = DiffusionEngine(self.cfg, self.history, self.hf_store)
        self.engine.active_vibe = self.active_vibe
        self._llm_window: Optional[LLMDownloadWindow] = None

        self.active_tab = "home"
        self.nav_buttons = []  # (key, frame, label_widget, label_text)
        self.pages = {}
        self.title_label = None
        self.history_list = None
        self.activity_list = None
        self.status_pill = None
        self.theme_btn = None
        self._sidebar_open = True

        self._shell = tk.Frame(self, bg=CONTENT)
        self._shell.pack(fill="both", expand=True)
        self._build_shell()
        self._select_tab("home")
        self.engine.on_job(self._on_engine_job)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(50, self._show_splash)

    def _on_close(self):
        self.engine.shutdown()
        self.destroy()

    def _set_dark_mode(self, dark: bool, rebuild: bool = True):
        dark = bool(dark)
        if self.cfg.dark_mode == dark and DARK_MODE == dark:
            return
        self.cfg.dark_mode = dark
        self.cfg.save()
        apply_theme(dark)
        if rebuild:
            self._rebuild_shell()

    def _toggle_dark_mode(self):
        self._set_dark_mode(not self.cfg.dark_mode, rebuild=True)

    def _rebuild_shell(self):
        """Rebuild chrome after theme change so colors refresh."""
        tab = self.active_tab
        if self._llm_window is not None:
            try:
                self._llm_window.destroy()
            except Exception:
                pass
            self._llm_window = None
        for w in self._shell.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass
        self.nav_buttons = []
        self.pages = {}
        self.title_label = None
        self.history_list = None
        self.activity_list = None
        self.status_pill = None
        self.theme_btn = None
        self.configure(bg=CONTENT)
        self._shell.configure(bg=CONTENT)
        self._build_shell()
        if not self._sidebar_open:
            self.sidebar.pack_forget()
        target = tab if tab in self.pages else "home"
        self._select_tab(target)
        try:
            self.refresh_history_views()
        except Exception:
            pass

    def _show_splash(self):
        """DiffusionBee SplashScreen — centered logo."""
        splash = tk.Frame(self, bg=CONTENT)
        splash.place(x=0, y=0, relwidth=1, relheight=1)
        wrap = tk.Frame(splash, bg=CONTENT)
        wrap.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(
            wrap, text="OpenPhoto", bg=CONTENT, fg=TEXT,
            font=(UI_FONT, 42, "bold"),
        ).pack()
        tk.Label(
            wrap, text="0.1", bg=CONTENT, fg=MUTED,
            font=(UI_FONT, 18),
        ).pack(pady=(4, 0))
        tk.Label(
            wrap, text="DiffusionBee-compatible workspace", bg=CONTENT, fg=MUTED,
            font=(UI_FONT, 12),
        ).pack(pady=(18, 0))

        def fade():
            try:
                splash.destroy()
            except Exception:
                pass
        self.after(1400, fade)

    def _build_shell(self):
        """ApplicationFrame layout: sidebar 200px + titlebar 55px + content."""
        # Sidebar
        self.sidebar = tk.Frame(self._shell, bg=SIDEBAR, width=SIDEBAR_W)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        drag = tk.Frame(self.sidebar, bg=SIDEBAR, height=TITLEBAR_H)
        drag.pack(fill="x")
        drag.pack_propagate(False)
        collapse = tk.Label(
            drag, text="☰", bg=SIDEBAR, fg=MUTED, font=(UI_FONT, 14),
            cursor="hand2",
        )
        collapse.pack(side="right", padx=12, pady=15)
        collapse.bind("<Button-1>", lambda e: self._toggle_sidebar())

        tk.Label(
            self.sidebar, text="Tools", bg=SIDEBAR, fg=MUTED,
            font=(UI_FONT, 12, "bold"), anchor="w",
        ).pack(fill="x", padx=15, pady=(4, 8))

        for key, icon, label in NAV_TABS:
            row = tk.Frame(self.sidebar, bg=SIDEBAR, cursor="hand2")
            row.pack(fill="x", padx=15, pady=2)
            inner = tk.Frame(row, bg=SIDEBAR)
            inner.pack(fill="x", padx=0, pady=7)
            ic = tk.Label(inner, text=icon, bg=SIDEBAR, fg=ICON_BLUE, font=(UI_FONT, 13), width=2)
            ic.pack(side="left", padx=(10, 4))
            lb = tk.Label(
                inner, text=label, bg=SIDEBAR, fg=TEXT,
                font=(UI_FONT, 14), anchor="w",
            )
            lb.pack(side="left", fill="x")
            for w in (row, inner, ic, lb):
                w.bind("<Button-1>", lambda e, k=key: self._select_tab(k))
                w.bind("<Enter>", lambda e, r=row, k=key: self._nav_hover(r, k, True))
                w.bind("<Leave>", lambda e, r=row, k=key: self._nav_hover(r, k, False))
            self.nav_buttons.append((key, row, lb, label))

        # Right column: title bar + content
        self._right = tk.Frame(self._shell, bg=CONTENT)
        self._right.pack(side="left", fill="both", expand=True)

        top = tk.Frame(self._right, bg=TOP, height=TITLEBAR_H, highlightbackground=BORDER, highlightthickness=1)
        top.pack(side="top", fill="x")
        top.pack_propagate(False)

        self.title_label = tk.Label(
            top, text=f"Home - {APP_TITLE}", bg=TOP, fg=TEXT,
            font=(UI_FONT, 15, "bold"),
        )
        self.title_label.pack(side="left", padx=16)

        # MainToolbar-ish: theme toggle + status + ⋮
        tools = tk.Frame(top, bg=TOP)
        tools.pack(side="right", padx=10)
        self.theme_btn = tk.Label(
            tools,
            text="Light" if self.cfg.dark_mode else "Dark",
            bg=TOP, fg=BLUE, font=(UI_FONT, 12, "bold"),
            cursor="hand2", padx=10,
        )
        self.theme_btn.pack(side="left", padx=(0, 4))
        self.theme_btn.bind("<Button-1>", lambda e: self._toggle_dark_mode())
        self.status_pill = tk.Label(
            tools, text=self._backend_status_text(), bg=TOP, fg=MUTED,
            font=(UI_FONT, 11),
        )
        self.status_pill.pack(side="left", padx=8)
        menu_btn = tk.Label(
            tools, text="⋮", bg=TOP, fg=MUTED, font=(UI_FONT, 18),
            cursor="hand2", padx=10,
        )
        menu_btn.pack(side="left")
        menu_btn.bind("<Button-1>", lambda e: self._open_overflow_menu())

        holder = tk.Frame(self._right, bg=CONTENT)
        holder.pack(fill="both", expand=True)

        canvas = tk.Canvas(holder, bg=CONTENT, highlightthickness=0)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        self.content = tk.Frame(canvas, bg=CONTENT)
        self.content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=self.content, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.main_canvas = canvas
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self.pages["home"] = self._build_home_page(self.content)
        self.pages["history"] = self._build_history_page(self.content)
        self.pages["models"] = self._build_models_page(self.content)
        self.pages["settings"] = self._build_settings_page(self.content)
        self.pages["training"] = self._build_placeholder_page(self.content, "Training")
        self.pages["llms"] = self._build_llms_page(self.content)
        self.pages["activity"] = self._build_activity_page(self.content)
        # Generation applets open as styled workspaces (TwoColAppletLayout analogue)

    def _toggle_sidebar(self):
        self._sidebar_open = not self._sidebar_open
        if self._sidebar_open:
            self.sidebar.pack(side="left", fill="y", before=self._right)
        else:
            self.sidebar.pack_forget()

    def _open_overflow_menu(self):
        m = tk.Menu(self, tearoff=0, font=(UI_FONT, 13))
        m.add_command(label="Home", command=lambda: self._select_tab("home"))
        m.add_command(label="Settings", command=lambda: self._select_tab("settings"))
        m.add_command(label="Download LLMs", command=self.open_llm_downloads)
        m.add_command(label="Activity", command=lambda: self._select_tab("activity"))
        m.add_separator()
        m.add_command(
            label="Switch to Light mode" if self.cfg.dark_mode else "Switch to Dark mode",
            command=self._toggle_dark_mode,
        )
        m.add_separator()
        m.add_command(label="About OpenPhoto 0.1", command=lambda: messagebox.showinfo(
            APP_NAME, f"{APP_NAME}\nDiffusionBee-compatible GUI\nFLUX + Hugging Face LLMs",
        ))
        try:
            m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            m.grab_release()

    def _backend_status_text(self) -> str:
        if self.cfg.bfl_api_key:
            flux = "FLUX (BFL)"
        elif self.cfg.use_free_backend:
            flux = "FLUX free"
        else:
            flux = "FLUX off"
        return flux

    def _nav_hover(self, row, key, entering):
        if key == self.active_tab:
            return
        row.configure(bg=PANEL_HOVER if entering else SIDEBAR)
        for child in row.winfo_children():
            child.configure(bg=PANEL_HOVER if entering else SIDEBAR)
            for c2 in child.winfo_children():
                try:
                    c2.configure(bg=PANEL_HOVER if entering else SIDEBAR)
                except Exception:
                    pass

    def _select_tab(self, key):
        # Generation tools → open DiffusionBee-style applet workspace
        if key in ("txt2img", "img2img", "inpaint", "upscale", "txt2vid", "llm"):
            titles = {
                "txt2img": "Text to image",
                "img2img": "Image to image",
                "inpaint": "Inpainting",
                "upscale": "Upscaler",
                "txt2vid": "Text to video",
                "llm": "LLM Prompt Lab",
            }
            self.active_tab = key
            self._paint_sidebar_selection(key)
            if self.title_label is not None:
                self.title_label.configure(text=f"{titles.get(key, key)} - {APP_TITLE}")
            self.open_tool(titles.get(key, key), key)
            # keep Home visible underneath
            if "home" in self.pages:
                for page_key, page in self.pages.items():
                    if page_key == "home":
                        page.pack(fill="both", expand=True)
                    else:
                        page.pack_forget()
            return

        if key == "hf_llms":
            self.open_llm_downloads()
            return

        self.active_tab = key
        label_text = next((lab for k, _, _, lab in self.nav_buttons if k == key), key.title())
        self._paint_sidebar_selection(key)
        if self.title_label is not None:
            self.title_label.configure(text=f"{label_text} - {APP_TITLE}")

        for page_key, page in self.pages.items():
            if page_key == key:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()

        if key == "history":
            self.refresh_history_views()
        if key == "activity":
            self.refresh_activity()
        if key == "llms":
            self.open_llm_downloads()

        self.main_canvas.yview_moveto(0)
        self.content.update_idletasks()
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def _paint_sidebar_selection(self, key):
        for tab_key, row, _lb, _label in self.nav_buttons:
            active = tab_key == key
            bg = SIDEBAR_SEL if active else SIDEBAR
            row.configure(bg=bg)
            for child in row.winfo_children():
                child.configure(bg=bg)
                for c2 in child.winfo_children():
                    try:
                        c2.configure(bg=bg)
                    except Exception:
                        pass

    def _build_home_page(self, parent):
        """Homepage.vue — All AI Tools / Pages / Miscellaneous card grid."""
        page = tk.Frame(parent, bg=CONTENT)
        wrap = tk.Frame(page, bg=CONTENT)
        wrap.pack(fill="both", expand=True, padx=20, pady=20)

        for section_title, items in HOME_SECTIONS:
            tk.Label(
                wrap, text=section_title, bg=CONTENT, fg=MUTED,
                font=(UI_FONT, 15, "bold"),
            ).pack(anchor="w", pady=(8, 6))

            grid = tk.Frame(wrap, bg=CONTENT)
            grid.pack(anchor="w", fill="x", pady=(0, 16))
            for idx, (title, desc, kind, mode) in enumerate(items):
                self._make_card(grid, 0, idx, title, desc, kind, mode)

        tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=(8, 20))
        return page

    def _build_placeholder_page(self, parent, label):
        page = tk.Frame(parent, bg=BG)
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=30, pady=(34, 20))
        tk.Label(header, text=label, bg=BG, fg=TEXT, font=("Arial", 28, "bold")).pack(anchor="w")
        tk.Label(
            header, text=f"Browse and manage your {label.lower()} from here.",
            bg=BG, fg=MUTED, font=("Arial", 16),
        ).pack(anchor="w", pady=(8, 22))
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")
        body = tk.Frame(page, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        body.pack(fill="both", expand=True, padx=30, pady=(18, 30), ipady=80)
        tk.Label(body, text=label, bg=PANEL, fg=TEXT, font=("Arial", 22, "bold")).pack(pady=(60, 8))
        tk.Label(body, text="Coming soon in this build.", bg=PANEL, fg=MUTED, font=("Arial", 15)).pack()
        return page

    def _build_history_page(self, parent):
        page = tk.Frame(parent, bg=BG)
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=30, pady=(34, 20))
        tk.Label(header, text="Generation History", bg=BG, fg=TEXT, font=("Arial", 28, "bold")).pack(anchor="w")
        tk.Label(
            header, text="Outputs from FLUX image/video and LLM runs saved on disk.",
            bg=BG, fg=MUTED, font=("Arial", 16),
        ).pack(anchor="w", pady=(8, 22))
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")

        box = tk.Frame(page, bg=BG)
        box.pack(fill="both", expand=True, padx=30, pady=(10, 30))
        lb = tk.Listbox(
            box, bg=PANEL, fg=TEXT, selectbackground=BLUE, font=("Arial", 13),
            relief="flat", highlightthickness=1, highlightbackground=BORDER, height=22,
        )
        lb.pack(fill="both", expand=True)
        page._history_lb = lb  # type: ignore[attr-defined]
        return page

    def _build_activity_page(self, parent):
        page = tk.Frame(parent, bg=BG)
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=30, pady=(34, 20))
        tk.Label(header, text="Activity", bg=BG, fg=TEXT, font=("Arial", 28, "bold")).pack(anchor="w")
        tk.Label(header, text="Live job queue from the OpenPhoto / DiffusionBee-style engine.",
                 bg=BG, fg=MUTED, font=("Arial", 16)).pack(anchor="w", pady=(8, 22))
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")
        lb = tk.Listbox(
            page, bg=PANEL, fg=TEXT, selectbackground=BLUE, font=("Menlo", 12),
            relief="flat", highlightthickness=1, highlightbackground=BORDER, height=22,
        )
        lb.pack(fill="both", expand=True, padx=30, pady=(10, 30))
        page._activity_lb = lb  # type: ignore[attr-defined]
        return page

    def _build_models_page(self, parent):
        page = tk.Frame(parent, bg=BG)
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=30, pady=(34, 20))
        tk.Label(header, text="Models", bg=BG, fg=TEXT, font=("Arial", 28, "bold")).pack(anchor="w")
        tk.Label(
            header, text="Pre-baked FLUX 3 → FLUX.1 stack + Hugging Face LLMs (all protocols in this .py).",
            bg=BG, fg=MUTED, font=("Arial", 16),
        ).pack(anchor="w", pady=(8, 12))
        tk.Button(
            header, text="Download LLMs (Hugging Face)",
            command=self.open_llm_downloads,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 13, "bold"), padx=14, pady=8,
        ).pack(anchor="w", pady=(0, 16))
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")

        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=30, pady=(12, 30))

        for family in FAMILY_ORDER:
            names = [(n, m) for n, m in FLUX_MODELS.items() if m.get("family") == family]
            if not names:
                continue
            box = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            box.pack(fill="x", pady=(0, 12))
            tk.Label(
                box, text=FAMILY_TITLES.get(family, family),
                bg=PANEL, fg=TEXT, font=("Arial", 16, "bold"),
            ).pack(anchor="w", padx=18, pady=(16, 8))
            for name, meta in names:
                kind = meta.get("kind", "image")
                note = meta.get("label", "")
                tk.Label(
                    box,
                    text=f"• {name}  →  /v1/{meta['endpoint']}  [{kind}]  —  {note}",
                    bg=PANEL, fg=MUTED, font=("Menlo", 11),
                ).pack(anchor="w", padx=24, pady=2)
            tk.Label(box, text="", bg=PANEL).pack(pady=6)

        hf = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        hf.pack(fill="x", pady=(0, 12))
        tk.Label(hf, text="Hugging Face LLMs (pre-baked catalog)", bg=PANEL, fg=TEXT,
                 font=("Arial", 16, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        for item in HF_LLM_CATALOG:
            mark = "✓" if self.hf_store.is_downloaded(item) else "·"
            tk.Label(
                hf,
                text=f"{mark} {item['name']}  →  {item['repo']}/{item['file']}",
                bg=PANEL, fg=MUTED, font=("Menlo", 11),
            ).pack(anchor="w", padx=24, pady=2)
        tk.Label(hf, text="", bg=PANEL).pack(pady=6)

        llms = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        llms.pack(fill="x")
        tk.Label(llms, text="LLM providers", bg=PANEL, fg=TEXT,
                 font=("Arial", 16, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        for key, meta in LLM_PROVIDERS.items():
            models = ", ".join((meta["models"] or ["—"])[:3])
            tk.Label(
                llms,
                text=f"• {meta['label']}  ({key})  —  {models}",
                bg=PANEL, fg=MUTED, font=("Arial", 13),
            ).pack(anchor="w", padx=24, pady=2)
        tk.Label(llms, text="", bg=PANEL).pack(pady=8)
        return page

    def _build_settings_page(self, parent):
        page = tk.Frame(parent, bg=BG)
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=30, pady=(34, 12))
        tk.Label(header, text="Settings", bg=BG, fg=TEXT, font=("Arial", 28, "bold")).pack(anchor="w")
        tk.Label(
            header, text="API keys & defaults. Saved to ~/.openphoto/config.json",
            bg=BG, fg=MUTED, font=("Arial", 15),
        ).pack(anchor="w", pady=(8, 16))
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")

        form = tk.Frame(page, bg=BG)
        form.pack(fill="both", expand=True, padx=30, pady=18)

        self._settings_vars: dict[str, tk.Variable] = {}

        def row(label, key, show=None, width=64):
            r = tk.Frame(form, bg=BG)
            r.pack(fill="x", pady=6)
            tk.Label(r, text=label, bg=BG, fg=MUTED, font=("Arial", 12), width=28, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(getattr(self.cfg, key, "")))
            ent = tk.Entry(r, textvariable=var, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                           relief="flat", width=width, show=show or "")
            ent.pack(side="left", fill="x", expand=True, ipady=6)
            self._settings_vars[key] = var

        dark = tk.BooleanVar(value=self.cfg.dark_mode)
        self._settings_vars["dark_mode"] = dark
        tk.Checkbutton(
            form, text="Dark mode",
            variable=dark, bg=BG, fg=TEXT, selectcolor=PANEL,
            activebackground=BG, activeforeground=TEXT, font=("Arial", 13, "bold"),
            command=lambda: self._set_dark_mode(dark.get(), rebuild=True),
        ).pack(anchor="w", pady=(0, 12))

        row("BFL API key (optional)", "bfl_api_key", show="•")
        row("Default image model", "flux_model")
        row("Default video model", "video_model")
        row("Video mode (t2v/i2v/v2v)", "video_mode", width=12)
        row("Video resolution (hd/fhd)", "video_resolution", width=12)
        row("Video duration (sec)", "video_duration", width=12)
        row("Default width", "default_width", width=12)
        row("Default height", "default_height", width=12)
        row("Flex steps", "steps", width=12)
        row("Flex guidance", "guidance", width=12)
        row("Safety tolerance 0–6", "safety_tolerance", width=12)
        row("Output format (png/jpeg)", "output_format", width=12)
        row("Default seed (-1 random)", "seed", width=12)
        row("LLM provider id", "llm_provider")
        row("LLM model", "llm_model")
        row("Custom LLM base URL", "custom_base_url")
        row("Hugging Face token (HF_TOKEN)", "hf_token", show="•")
        row("Active HF LLM name", "hf_active_llm")
        row("OpenAI key", "openai_api_key", show="•")
        row("Anthropic key", "anthropic_api_key", show="•")
        row("Groq key", "groq_api_key", show="•")
        row("Together key", "together_api_key", show="•")
        row("OpenRouter key", "openrouter_api_key", show="•")
        row("DeepSeek key", "deepseek_api_key", show="•")
        row("xAI key", "xai_api_key", show="•")
        row("Gemini key", "gemini_api_key", show="•")

        out_row = tk.Frame(form, bg=BG)
        out_row.pack(fill="x", pady=6)
        tk.Label(
            out_row, text="Output directory", bg=BG, fg=MUTED,
            font=("Arial", 12), width=28, anchor="w",
        ).pack(side="left")
        self._output_dir_var = tk.StringVar(value=str(self.cfg.output_dir))
        self._settings_vars["output_dir"] = self._output_dir_var
        tk.Entry(
            out_row, textvariable=self._output_dir_var, bg=INPUT_BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", width=48,
        ).pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(
            out_row, text="Choose folder…", command=self._choose_output_dir,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 12, "bold"), padx=12, pady=6,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            out_row, text="Pictures", command=self._reset_output_to_pictures,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 12), padx=10, pady=6,
        ).pack(side="left", padx=(6, 0))

        enhance = tk.BooleanVar(value=self.cfg.enhance_prompts)
        self._settings_vars["enhance_prompts"] = enhance
        tk.Checkbutton(
            form, text="Enhance prompts with LLM by default",
            variable=enhance, bg=BG, fg=TEXT, selectcolor=PANEL,
            activebackground=BG, activeforeground=TEXT, font=("Arial", 13),
        ).pack(anchor="w", pady=10)

        free_be = tk.BooleanVar(value=self.cfg.use_free_backend)
        self._settings_vars["use_free_backend"] = free_be
        tk.Checkbutton(
            form, text="Use free FLUX backend when no BFL key (Pollinations — no signup)",
            variable=free_be, bg=BG, fg=TEXT, selectcolor=PANEL,
            activebackground=BG, activeforeground=TEXT, font=("Arial", 13),
        ).pack(anchor="w", pady=4)

        vaudio = tk.BooleanVar(value=self.cfg.video_audio)
        self._settings_vars["video_audio"] = vaudio
        tk.Checkbutton(
            form, text="FLUX 3 video: generate synchronized audio by default",
            variable=vaudio, bg=BG, fg=TEXT, selectcolor=PANEL,
            activebackground=BG, activeforeground=TEXT, font=("Arial", 13),
        ).pack(anchor="w", pady=4)

        tk.Label(
            form,
            text="Tip: leave BFL key empty to generate with free FLUX. Default LLM is Pollinations (no key).",
            bg=BG, fg=MUTED, font=("Arial", 12), wraplength=720, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        tk.Button(
            form, text="Save settings", command=self._save_settings,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 14, "bold"), padx=20, pady=10,
        ).pack(anchor="w", pady=(12, 30))
        return page

    def _choose_output_dir(self):
        current = ""
        if hasattr(self, "_output_dir_var"):
            current = self._output_dir_var.get().strip()
        initial = current or str(self.cfg.output_dir) or str(OUTPUT_DIR)
        path = filedialog.askdirectory(
            title="Choose output folder",
            initialdir=initial if Path(initial).is_dir() else str(os_pictures_dir()),
        )
        if not path:
            return
        Path(path).mkdir(parents=True, exist_ok=True)
        if hasattr(self, "_output_dir_var"):
            self._output_dir_var.set(path)
        self.cfg.output_dir = path
        self.cfg.save()
        messagebox.showinfo(APP_NAME, f"Output folder set to:\n{path}")

    def _reset_output_to_pictures(self):
        path = str(OUTPUT_DIR)
        Path(path).mkdir(parents=True, exist_ok=True)
        if hasattr(self, "_output_dir_var"):
            self._output_dir_var.set(path)
        self.cfg.output_dir = path
        self.cfg.save()
        messagebox.showinfo(APP_NAME, f"Output folder reset to Pictures:\n{path}")

    def _save_settings(self):
        for key, var in self._settings_vars.items():
            val = var.get()
            if key in (
                "default_width", "default_height", "steps", "seed",
                "video_duration", "safety_tolerance",
            ):
                try:
                    val = int(val)
                except Exception:
                    continue
            elif key == "guidance":
                try:
                    val = float(val)
                except Exception:
                    continue
            elif key in ("enhance_prompts", "video_audio", "use_free_backend", "dark_mode"):
                val = bool(val)
            elif key == "output_dir":
                val = str(val).strip() or str(OUTPUT_DIR)
                Path(val).mkdir(parents=True, exist_ok=True)
            setattr(self.cfg, key, val)
        theme_changed = bool(self.cfg.dark_mode) != DARK_MODE
        self.cfg.save()
        self.engine.reload_keys()
        if theme_changed:
            apply_theme(self.cfg.dark_mode)
            self._rebuild_shell()
        elif self.status_pill:
            self.status_pill.configure(text=self._backend_status_text())
        messagebox.showinfo(APP_NAME, "Settings saved.")

    def _make_card(self, grid, row, col, title, desc, kind, mode):
        """DiffusionBee .select_app — 280×230, image + bottom desc + Open."""
        outer = tk.Frame(
            grid, bg=SIDEBAR, width=CARD_W, height=CARD_H,
            highlightbackground=BORDER, highlightthickness=1, cursor="hand2",
        )
        outer.grid(row=row, column=col, sticky="nw", padx=5, pady=5)
        outer.grid_propagate(False)
        outer.pack_propagate(False)

        preview = ToolPreview(outer, kind, height=118)
        preview.place(x=0, y=0, relwidth=1, height=118)

        bottom = tk.Frame(outer, bg=SIDEBAR)
        bottom.place(x=0, rely=1.0, anchor="sw", relwidth=1.0)

        textbox = tk.Frame(bottom, bg=SIDEBAR)
        textbox.pack(fill="x", padx=15, pady=(10, 0))
        tk.Label(
            textbox, text=title, bg=SIDEBAR, fg=TEXT,
            font=(UI_FONT, 15, "bold"), anchor="w",
        ).pack(anchor="w")
        if desc:
            tk.Label(
                textbox, text=desc, bg=SIDEBAR, fg=MUTED,
                font=(UI_FONT, 13), justify="left", wraplength=240, anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        btn = tk.Label(
            bottom, text="Open", bg=BLUE, fg="#FFFFFF",
            font=(UI_FONT, 13, "bold"), padx=10, pady=3, cursor="hand2",
        )
        btn.pack(anchor="w", padx=15, pady=(8, 12))
        btn.bind("<Button-1>", lambda e, t=title, m=mode: self._home_open(t, m))
        btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=BLUE_HOVER))
        btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=BLUE))

        for w in (outer, preview, bottom, textbox):
            w.bind("<Button-1>", lambda e, t=title, m=mode: self._home_open(t, m))

    def _home_open(self, title, mode):
        if mode in ("models", "history", "settings", "training", "home"):
            self._select_tab(mode)
            return
        if mode == "hf_llms":
            self.open_llm_downloads()
            return
        self.open_tool(title, mode)

    def open_tool(self, title, mode="txt2img"):
        if mode == "hf_llms":
            self.open_llm_downloads()
            return
        if mode == "training":
            self._select_tab("training")
            return
        ToolWorkspace(self, title, mode)

    def open_llm_downloads(self):
        if self._llm_window is not None and self._llm_window.winfo_exists():
            self._llm_window.lift()
            self._llm_window.focus_force()
            self._llm_window.refresh()
            return
        self._llm_window = LLMDownloadWindow(self)

    def _build_llms_page(self, parent):
        page = tk.Frame(parent, bg=BG)
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=30, pady=(34, 20))
        tk.Label(header, text="Hugging Face LLMs", bg=BG, fg=TEXT, font=("Arial", 28, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="Pre-baked FLUX prompt LLMs from Hugging Face. Download weights or vibe-add any GGUF.",
            bg=BG, fg=MUTED, font=("Arial", 16),
        ).pack(anchor="w", pady=(8, 12))
        tk.Button(
            header, text="Open Download LLMs window",
            command=self.open_llm_downloads,
            bg=BLUE, fg="#FFFFFF", activebackground=BLUE_HOVER, activeforeground="#FFFFFF",
            relief="flat", font=("Arial", 14, "bold"), padx=18, pady=10,
        ).pack(anchor="w", pady=(4, 16))
        tk.Frame(header, bg=BORDER, height=1).pack(fill="x")

        wrap = tk.Frame(page, bg=BG)
        wrap.pack(fill="both", expand=True, padx=30, pady=(12, 30))
        box = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True)
        tk.Label(box, text="Catalog (pre-installed entries)", bg=PANEL, fg=TEXT,
                 font=("Arial", 16, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        for item in self.hf_store.catalog():
            mark = "✓ downloaded" if self.hf_store.is_downloaded(item) else "ready to download"
            tk.Label(
                box,
                text=f"• {item['name']}  —  {item.get('vibe', '')}  [{mark}]",
                bg=PANEL, fg=MUTED, font=("Arial", 13),
            ).pack(anchor="w", padx=24, pady=2)
        tk.Label(
            box,
            text=f"\nLocal folder: {LLM_DIR}",
            bg=PANEL, fg=MUTED, font=("Menlo", 11),
        ).pack(anchor="w", padx=18, pady=(8, 16))
        return page

    def refresh_history_views(self):
        self.history.load()
        for key in ("history", "recent", "gallery"):
            page = self.pages.get(key)
            lb = getattr(page, "_history_lb", None) if page else None
            if not lb:
                continue
            lb.delete(0, "end")
            for item in self.history.items[:200]:
                lb.insert(
                    "end",
                    f"{item.created_at}  |  {item.mode:8}  |  {item.model:28}  |  {Path(item.path).name}  |  {item.prompt[:60]}",
                )

    def refresh_activity(self):
        page = self.pages.get("activity")
        lb = getattr(page, "_activity_lb", None) if page else None
        if not lb:
            return
        lb.delete(0, "end")
        for job in list(self.engine.jobs.values())[::-1][:100]:
            lb.insert("end", f"{job.id}  {job.status:8}  {job.mode:8}  {job.message or job.error}")

    def _on_engine_job(self, job: GenJob):
        def ui():
            if self.active_tab == "activity":
                self.refresh_activity()
            if job.status == "done":
                self.refresh_history_views()
        self.after(0, ui)


if __name__ == "__main__":
    App().mainloop()
