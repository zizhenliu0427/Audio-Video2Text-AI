import os
import sys
import json
import base64
import hashlib
import argparse
import subprocess
import platform
from pathlib import Path
from typing import List, Tuple, Optional
from getpass import getpass

from cryptography.fernet import Fernet

from openai import OpenAI, AuthenticationError, APIStatusError


CONFIG_DIR = Path.home() / ".mimo_transcribe"
CONFIG_FILE = CONFIG_DIR / "config.json"

PAYG_BASE_URL = "https://api.xiaomimimo.com/v1"
TOKEN_PLAN_CN_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
TOKEN_PLAN_SGP_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/v1"
TOKEN_PLAN_AMS_BASE_URL = "https://token-plan-ams.xiaomimimo.com/v1"


SPEAKER_PROMPT = """
请转写这段短音频，并尽量区分不同演讲人。

输出格式：

【演讲人1】：内容
【演讲人2】：内容
【演讲人1】：内容

要求：
1. 只转写本段音频，不要补全前后文。
2. 不要总结，不要解释。
3. 不要重复已经说过的内容。
4. 如果听不清，请写【听不清】。
5. 如果能从音频中识别出演讲人的真实姓名（例如自我介绍、被其他人称呼等），请使用真实姓名，且英文名字首字母大写，如【张三】、【John】。如果无法确定真实姓名，则使用"演讲人1""演讲人2"等编号。
6. 保留中英文混合内容。
7. 如果出现技术名词，例如 token、workflow、template、Jira、Gemini、ChatGPT，等等，请尽量保留英文原词。
"""


# ── 基础工具函数 ──────────────────────────────────────────────

def looks_like_repetition_loop(text: str) -> bool:
    if not text:
        return True

    suspicious_phrases = [
        "E是哪个",
        "哪个",
        "嗯嗯嗯",
    ]

    for phrase in suspicious_phrases:
        if text.count(phrase) >= 20:
            return True

    if len(text) > 1000:
        unique_chars = len(set(text))
        if unique_chars < 30:
            return True

    return False


def get_machine_key() -> bytes:
    raw = f"{platform.node()}-{os.getenv('USERNAME', os.getenv('USER', 'default'))}"
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def load_saved_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}

    try:
        encrypted = CONFIG_FILE.read_bytes()
        fernet = Fernet(get_machine_key())
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        return {}


def save_config(api_key: str, base_url: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"api_key": api_key, "base_url": base_url}).encode("utf-8")
    fernet = Fernet(get_machine_key())
    encrypted = fernet.encrypt(data)
    CONFIG_FILE.write_bytes(encrypted)


def run_cmd(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def check_ffmpeg() -> None:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
    except Exception:
        print("错误：找不到 ffmpeg。请先安装 ffmpeg。")
        print("Windows: winget install Gyan.FFmpeg")
        print("Mac: brew install ffmpeg")
        print("Linux Ubuntu/Debian: sudo apt install ffmpeg")
        sys.exit(1)


def extract_audio_to_mp3(input_path: Path, output_path: Path, bitrate: str = "64k") -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", bitrate,
        "-ar", "16000",
        "-ac", "1",
        str(output_path)
    ]
    run_cmd(cmd)


def split_audio_to_mp3_parts(
    input_audio: Path,
    output_dir: Path,
    segment_seconds: int,
    bitrate: str = "64k"
) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    pattern = output_dir / "part_%03d.mp3"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_audio),
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", bitrate,
        "-ar", "16000",
        "-ac", "1",
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        str(pattern)
    ]
    run_cmd(cmd)

    return sorted(output_dir.glob("part_*.mp3"))


def file_to_base64_data_url(audio_path: Path, mime_type: str = "audio/mpeg") -> str:
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{audio_base64}"


def estimate_base64_size_mb(file_path: Path) -> float:
    raw_size = file_path.stat().st_size
    base64_size = raw_size * 4 / 3
    return base64_size / 1024 / 1024


def extract_text_from_message(message) -> str:
    content = getattr(message, "content", None)
    reasoning_content = getattr(message, "reasoning_content", None)

    if content:
        return content.strip()

    if reasoning_content:
        return reasoning_content.strip()

    return ""


def is_auth_error(error: Exception) -> bool:
    if isinstance(error, AuthenticationError):
        return True

    if isinstance(error, APIStatusError) and error.status_code in (401, 403):
        return True

    message = str(error).lower()
    keywords = [
        "incorrect api key",
        "invalid api key",
        "unauthorized",
        "authentication",
        "api-key",
        "api key",
        "forbidden"
    ]

    return any(keyword in message for keyword in keywords)


def make_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=base_url
    )


# ── API 调用 ─────────────────────────────────────────────────

def call_mimo_asr(
    audio_data_url: str,
    language: str,
    api_key: str,
    base_url: str
) -> str:
    def request(client: OpenAI):
        return client.chat.completions.create(
            model="mimo-v2.5-asr",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_data_url
                            }
                        }
                    ]
                }
            ],
            extra_body={
                "asr_options": {
                    "language": language
                }
            }
        )

    completion = request(make_client(api_key, base_url))
    return extract_text_from_message(completion.choices[0].message)


def call_mimo_audio_understanding(
    audio_data_url: str,
    model: str,
    prompt: str,
    api_key: str,
    base_url: str,
    max_tokens: int = 8192
) -> str:
    def request(client: OpenAI):
        return client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are MiMo, an AI assistant developed by Xiaomi."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_data_url
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ],
            max_completion_tokens=max_tokens
        )

    completion = request(make_client(api_key, base_url))
    return extract_text_from_message(completion.choices[0].message)


def process_one_audio_part(
    audio_path: Path,
    mode: str,
    language: str,
    prompt: str,
    api_key: str,
    base_url: str
) -> str:
    audio_data_url = file_to_base64_data_url(audio_path, mime_type="audio/mpeg")

    if mode == "asr":
        return call_mimo_asr(
            audio_data_url=audio_data_url,
            language=language,
            api_key=api_key,
            base_url=base_url
        )

    if mode == "v25":
        return call_mimo_audio_understanding(
            audio_data_url=audio_data_url,
            model="mimo-v2.5",
            prompt=prompt,
            api_key=api_key,
            base_url=base_url
        )

    if mode == "omni":
        return call_mimo_audio_understanding(
            audio_data_url=audio_data_url,
            model="mimo-v2-omni",
            prompt=prompt,
            api_key=api_key,
            base_url=base_url
        )

    raise ValueError(f"未知 mode: {mode}")


# ── CLI 非交互模式 ──────────────────────────────────────────

def resolve_base_url(api_key: str, base_url: Optional[str]) -> str:
    if base_url:
        return base_url

    if api_key.startswith("sk-"):
        return PAYG_BASE_URL

    if api_key.startswith("tp-"):
        saved = load_saved_config()
        if saved.get("base_url"):
            return saved["base_url"]
        return TOKEN_PLAN_CN_BASE_URL

    saved = load_saved_config()
    if saved.get("base_url"):
        return saved["base_url"]

    return PAYG_BASE_URL


def resolve_api_key(cli_key: Optional[str]) -> Optional[str]:
    if cli_key:
        return cli_key

    env_key = os.environ.get("MIMO_API_KEY", "").strip()
    if env_key:
        return env_key

    saved = load_saved_config()
    if saved.get("api_key"):
        return saved["api_key"]

    return None


# ── 交互模式 ────────────────────────────────────────────────

def enable_windows_dpi_awareness() -> None:
    if platform.system() != "Windows":
        return

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def choose_one_file() -> Path:
    import tkinter as tk
    from tkinter import filedialog

    enable_windows_dpi_awareness()

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    file_path = filedialog.askopenfilename(
        title="请选择一个视频或音频文件",
        filetypes=[
            ("Media files", "*.mp4 *.mkv *.mov *.avi *.wmv *.flv *.webm *.mp3 *.wav *.m4a *.flac *.ogg"),
            ("Video files", "*.mp4 *.mkv *.mov *.avi *.wmv *.flv *.webm"),
            ("Audio files", "*.mp3 *.wav *.m4a *.flac *.ogg"),
            ("All files", "*.*"),
        ]
    )

    root.destroy()

    if not file_path:
        print("没有选择文件，程序退出。")
        sys.exit(0)

    return Path(file_path).resolve()


def ask_non_empty(prompt: str, secret: bool = False) -> str:
    while True:
        value = getpass(prompt).strip() if secret else input(prompt).strip()
        if value:
            return value
        print("不能为空，请重新输入。")


def choose_base_url_from_token_plan() -> str:
    print("\n检测到 Token Plan API Key。")
    print("请选择 Token Plan 区域：")
    print("1. 中国区 cn")
    print("2. 新加坡区 sgp")
    print("3. 欧洲区 ams")
    print("4. 手动输入 Base URL")

    while True:
        choice = input("请输入 1 / 2 / 3 / 4，默认 1：").strip() or "1"

        if choice == "1":
            return TOKEN_PLAN_CN_BASE_URL
        if choice == "2":
            return TOKEN_PLAN_SGP_BASE_URL
        if choice == "3":
            return TOKEN_PLAN_AMS_BASE_URL
        if choice == "4":
            return ask_non_empty("请输入完整 Base URL，例如 https://token-plan-cn.xiaomimimo.com/v1：")

        print("输入无效，请重新选择。")


def guess_base_url_from_key(api_key: str) -> str:
    if api_key.startswith("sk-"):
        print("检测到按量付费 API Key。")
        return PAYG_BASE_URL

    if api_key.startswith("tp-"):
        return choose_base_url_from_token_plan()

    print("\n无法根据 API Key 前缀判断类型。")
    print("1. 按量 API")
    print("2. Token Plan 中国区")
    print("3. Token Plan 新加坡区")
    print("4. Token Plan 欧洲区")
    print("5. 手动输入 Base URL")

    while True:
        choice = input("请输入 1 / 2 / 3 / 4 / 5，默认 1：").strip() or "1"

        if choice == "1":
            return PAYG_BASE_URL
        if choice == "2":
            return TOKEN_PLAN_CN_BASE_URL
        if choice == "3":
            return TOKEN_PLAN_SGP_BASE_URL
        if choice == "4":
            return TOKEN_PLAN_AMS_BASE_URL
        if choice == "5":
            return ask_non_empty("请输入完整 Base URL：")

        print("输入无效，请重新选择。")


def get_api_key_and_base_url() -> Tuple[str, str]:
    print("\n=== 第 1 步：API Key 设置 ===")

    api_key = os.environ.get("MIMO_API_KEY", "").strip()
    base_url = os.environ.get("MIMO_BASE_URL", "").strip()

    if api_key and base_url:
        print("已检测到环境变量 MIMO_API_KEY 和 MIMO_BASE_URL。")
        save_config(api_key, base_url)
        print(f"当前使用 Base URL: {base_url}")
        return api_key, base_url

    if api_key and not base_url:
        print("已检测到环境变量 MIMO_API_KEY。")
        base_url = guess_base_url_from_key(api_key)
        save_config(api_key, base_url)
        print(f"当前使用 Base URL: {base_url}")
        return api_key, base_url

    saved = load_saved_config()
    if saved.get("api_key") and saved.get("base_url"):
        masked = saved["api_key"][:4] + "****" + saved["api_key"][-4:]
        print(f"已找到已保存的配置 (Key: {masked})。")
        choice = input("是否使用已保存的配置？(Y/n，默认 Y)：").strip().lower()
        if choice in ("", "y", "yes"):
            print(f"当前使用 Base URL: {saved['base_url']}")
            return saved["api_key"], saved["base_url"]

    print("没有检测到环境变量或已保存的配置。")
    api_key = ask_non_empty("请输入 MIMO_API_KEY，支持 sk- 或 tp-：", secret=True)
    base_url = guess_base_url_from_key(api_key)

    save_config(api_key, base_url)
    print(f"当前使用 Base URL: {base_url}")
    return api_key, base_url


def choose_model_mode() -> str:
    print("\n=== 第 2 步：选择模型 ===")
    print("1. asr  - mimo-v2.5-asr，专门语音识别，推荐用于转文字")
    print("2. v25  - mimo-v2.5，音频理解，可要求区分演讲人")
    print("3. omni - mimo-v2-omni，音频理解，可要求区分演讲人")
    print("4. all  - 三个模型都跑一遍")

    while True:
        choice = input("请选择模型，输入 1 / 2 / 3 / 4，默认 1：").strip() or "1"

        if choice == "1":
            return "asr"
        if choice == "2":
            return "v25"
        if choice == "3":
            return "omni"
        if choice == "4":
            return "all"

        print("输入无效，请重新选择。")


def choose_language() -> str:
    print("\n=== 第 3 步：选择音频语言 ===")
    print("1. zh   中文 / 普通话 / 中文方言为主")
    print("2. en   英文为主")
    print("3. auto 自动检测，中英混合或不确定时选这个")

    while True:
        choice = input("请选择语言，输入 1 / 2 / 3，默认 1：").strip() or "1"

        if choice == "1":
            return "zh"
        if choice == "2":
            return "en"
        if choice == "3":
            return "auto"

        print("输入无效，请重新选择。")


# ── 主流程（两种模式共用） ──────────────────────────────────

def run_pipeline(
    input_path: Path,
    mode: str,
    language: str,
    api_key: str,
    base_url: str,
    prompt: str,
    segment_seconds: int,
    bitrate: str,
    output_dir: Optional[Path] = None,
    print_text: bool = False,
) -> Path:
    """核心转写流程，交互/CLI 两种模式共用。返回最终输出文件路径。"""

    check_ffmpeg()

    if output_dir is None:
        output_dir = input_path.parent
    work_dir = output_dir / f"{input_path.stem}_mimo_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    audio_path = output_dir / f"{input_path.stem}.mp3"

    print(f"\n[1/4] 提取音频 → {audio_path}")
    extract_audio_to_mp3(input_path, audio_path, bitrate=bitrate)

    raw_audio_mb = audio_path.stat().st_size / 1024 / 1024
    print(f"       音频大小: {raw_audio_mb:.2f} MB")

    modes = ["asr", "v25", "omni"] if mode == "all" else [mode]
    last_output_path = None

    for current_mode in modes:
        print(f"\n[2/4] 模式: {current_mode} — 切片（每段 {segment_seconds} 秒）")

        limit_mb = 10 if current_mode == "asr" else 50

        parts_dir = work_dir / f"parts_{current_mode}"
        parts = split_audio_to_mp3_parts(
            input_audio=audio_path,
            output_dir=parts_dir,
            segment_seconds=segment_seconds,
            bitrate=bitrate
        )
        print(f"       共 {len(parts)} 段")

        results = []

        for idx, part in enumerate(parts, start=1):
            part_b64_mb = estimate_base64_size_mb(part)
            print(f"  [{idx}/{len(parts)}] {part.name} ({part_b64_mb:.2f} MB b64)")

            if part_b64_mb > limit_mb:
                print(f"  超过 {limit_mb} MB，跳过")
                results.append(f"【Part {idx}】\n[超过大小限制，已跳过]")
                continue

            try:
                text = process_one_audio_part(
                    audio_path=part,
                    mode=current_mode,
                    language=language,
                    prompt=prompt,
                    api_key=api_key,
                    base_url=base_url
                )
            except Exception as e:
                print(f"  调用失败: {e}")
                text = ""

            if looks_like_repetition_loop(text):
                print(f"  疑似重复/乱码，跳过")
                results.append(f"【Part {idx}】\n[疑似重复/乱码，已跳过]")
            else:
                results.append(f"【Part {idx}】\n{text}".strip())

        final_text = "\n\n".join(results).strip()

        suffix = f".{current_mode}.speaker_transcript" if mode == "all" else ".speaker_transcript"
        output_path = output_dir / f"{input_path.stem}{suffix}.txt"
        output_path.write_text(final_text, encoding="utf-8")
        last_output_path = output_path

        print(f"\n[3/4] 转写完成")
        print(f"       结果: {output_path}")

        if print_text:
            print(f"\n{'='*60}")
            print(final_text)
            print(f"{'='*60}")

    print(f"\n[4/4] 全部完成")
    return last_output_path


# ── 入口：自动判断交互 / CLI 模式 ───────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="视频/音频转文字工具 — 支持 CLI 和交互两种模式"
    )

    parser.add_argument(
        "input_file",
        nargs="?",
        default=None,
        help="输入文件路径。不指定则进入交互模式（弹窗选择文件）"
    )

    parser.add_argument(
        "--model", "-m",
        choices=["asr", "v25", "omni", "all"],
        default=None,
        help="模型选择。CLI 模式必填，交互模式下会提示选择"
    )

    parser.add_argument(
        "--language", "-l",
        choices=["zh", "en", "auto"],
        default=None,
        help="音频语言。CLI 模式必填，交互模式下会提示选择"
    )

    parser.add_argument(
        "--api-key", "-k",
        default=None,
        help="MiMo API Key。未指定则读环境变量 MIMO_API_KEY 或已保存配置"
    )

    parser.add_argument(
        "--base-url", "-u",
        default=None,
        help="API Base URL。未指定则根据 Key 类型自动推断"
    )

    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=180,
        help="切片长度，秒，默认 180"
    )

    parser.add_argument(
        "--bitrate",
        default="128k",
        help="提取音频码率，默认 128k"
    )

    parser.add_argument(
        "--prompt",
        default=SPEAKER_PROMPT,
        help="给 v25/omni 模型的提示词"
    )

    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="输出目录，默认与输入文件同目录"
    )

    parser.add_argument(
        "--print-text",
        action="store_true",
        help="转写完成后在终端打印全文"
    )

    args = parser.parse_args()

    # ── CLI 模式：指定了文件路径 ──
    if args.input_file:
        input_path = Path(args.input_file).resolve()
        if not input_path.exists():
            print(f"错误：文件不存在 → {input_path}")
            sys.exit(1)

        api_key = resolve_api_key(args.api_key)
        if not api_key:
            print("错误：未提供 API Key。请通过 --api-key、环境变量 MIMO_API_KEY 或先运行一次保存配置。")
            sys.exit(1)

        base_url = resolve_base_url(api_key, args.base_url)

        mode = args.model
        if mode is None:
            print("错误：CLI 模式需指定 --model (-m)，可选 asr / v25 / omni / all")
            sys.exit(1)

        language = args.language or "zh"

        output_dir = Path(args.output_dir).resolve() if args.output_dir else None

        run_pipeline(
            input_path=input_path,
            mode=mode,
            language=language,
            api_key=api_key,
            base_url=base_url,
            prompt=args.prompt,
            segment_seconds=args.segment_seconds,
            bitrate=args.bitrate,
            output_dir=output_dir,
            print_text=args.print_text,
        )

    # ── 交互模式：未指定文件路径 ──
    else:
        api_key, base_url = get_api_key_and_base_url()
        mode = choose_model_mode()
        language = choose_language()

        print("\n=== 第 4 步：选择文件 ===")
        input_path = choose_one_file()
        print(f"你选择的文件是：{input_path}")

        run_pipeline(
            input_path=input_path,
            mode=mode,
            language=language,
            api_key=api_key,
            base_url=base_url,
            prompt=args.prompt,
            segment_seconds=args.segment_seconds,
            bitrate=args.bitrate,
            print_text=True,
        )


if __name__ == "__main__":
    main()
