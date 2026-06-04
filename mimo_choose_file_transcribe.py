import os
import sys
import json
import base64
import hashlib
import argparse
import subprocess
import platform
from pathlib import Path
from typing import List, Tuple
from getpass import getpass

from cryptography.fernet import Fernet

import tkinter as tk
from tkinter import filedialog

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


def looks_like_repetition_loop(text: str) -> bool:
    """检测 ASR 输出是否出现重复死循环/乱码。"""
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
    """基于本机 hostname + username 派生加密密钥，绑定当前机器。"""
    raw = f"{platform.node()}-{os.getenv('USERNAME', os.getenv('USER', 'default'))}"
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def load_saved_config() -> dict:
    """读取并解密已保存的配置。失败返回空 dict。"""
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
    """加密并保存 API Key 和 Base URL。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"api_key": api_key, "base_url": base_url}).encode("utf-8")
    fernet = Fernet(get_machine_key())
    encrypted = fernet.encrypt(data)
    CONFIG_FILE.write_bytes(encrypted)


def enable_windows_dpi_awareness() -> None:
    """
    改善 Windows 高 DPI / 高缩放下 tkinter 文件选择框模糊或比例怪的问题。
    macOS / Linux 会自动跳过。
    """
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

    # 优先使用环境变量
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

    # 尝试加载已保存的配置
    saved = load_saved_config()
    if saved.get("api_key") and saved.get("base_url"):
        masked = saved["api_key"][:4] + "****" + saved["api_key"][-4:]
        print(f"已找到已保存的配置 (Key: {masked})。")
        choice = input("是否使用已保存的配置？(Y/n，默认 Y)：").strip().lower()
        if choice in ("", "y", "yes"):
            print(f"当前使用 Base URL: {saved['base_url']}")
            return saved["api_key"], saved["base_url"]

    # 手动输入
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


def make_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=base_url
    )


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


def call_with_api_key_retry(call_func, api_key: str, base_url: str, max_retries: int = 3):
    for attempt in range(1, max_retries + 1):
        client = make_client(api_key, base_url)

        try:
            return call_func(client)

        except Exception as e:
            if is_auth_error(e):
                print("\nAPI Key 无效、过期、没有权限，或者 Base URL 与 Key 类型不匹配。")

                if attempt >= max_retries:
                    print("已达到最大重试次数，程序退出。")
                    raise

                api_key = ask_non_empty("请重新输入 MIMO_API_KEY：", secret=True)
                base_url = guess_base_url_from_key(api_key)
                save_config(api_key, base_url)
                print(f"当前使用 Base URL: {base_url}")
                continue

            raise


def run_cmd(cmd: List[str]) -> None:
    print("运行命令:", " ".join(cmd))
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

    completion = call_with_api_key_retry(request, api_key, base_url)
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

    completion = call_with_api_key_retry(request, api_key, base_url)
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


def main():
    parser = argparse.ArgumentParser(
        description="选择一个视频/音频文件，然后调用 MiMo 模型转写"
    )

    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=180,
        help="切片长度，默认 180 秒（3 分钟）"
    )

    parser.add_argument(
        "--bitrate",
        default="128k",
        help="提取音频的 mp3 码率，默认 128k"
    )

    parser.add_argument(
        "--prompt",
        default=SPEAKER_PROMPT,
        help="给 mimo-v2.5 / mimo-v2-omni 的提示词"
    )

    args = parser.parse_args()

    api_key, base_url = get_api_key_and_base_url()
    mode = choose_model_mode()
    language = choose_language()

    print("\n=== 第 4 步：选择文件 ===")
    input_path = choose_one_file()
    print(f"你选择的文件是：{input_path}")

    check_ffmpeg()

    work_dir = input_path.parent / f"{input_path.stem}_mimo_work"
    work_dir.mkdir(exist_ok=True)

    # MP3 直接保存在原文件旁边
    audio_path = input_path.parent / f"{input_path.stem}.mp3"

    print("\n=== 第 5 步：提取/转换音频为 mp3 ===")
    extract_audio_to_mp3(input_path, audio_path, bitrate=args.bitrate)

    raw_audio_mb = audio_path.stat().st_size / 1024 / 1024
    b64_audio_mb = estimate_base64_size_mb(audio_path)

    print(f"\nMP3 已保存到: {audio_path}")
    print(f"音频大小: {raw_audio_mb:.2f} MB")
    print(f"Base64 预计大小: {b64_audio_mb:.2f} MB")

    modes = ["asr", "v25", "omni"] if mode == "all" else [mode]

    for current_mode in modes:
        print("\n==============================")
        print(f"开始处理模式: {current_mode}")
        print("==============================")

        limit_mb = 10 if current_mode == "asr" else 50

        # 永远切片，避免长音频导致截断/重复/幻觉
        print(f"开始切片（每段 {args.segment_seconds} 秒）...")
        parts_dir = work_dir / f"parts_{current_mode}"
        parts = split_audio_to_mp3_parts(
            input_audio=audio_path,
            output_dir=parts_dir,
            segment_seconds=args.segment_seconds,
            bitrate=args.bitrate
        )
        print(f"共切分为 {len(parts)} 段。")

        results = []

        for idx, part in enumerate(parts, start=1):
            part_b64_mb = estimate_base64_size_mb(part)
            print(f"\n处理第 {idx}/{len(parts)} 段: {part.name}")
            print(f"Base64 预计大小: {part_b64_mb:.2f} MB")

            if part_b64_mb > limit_mb:
                print(f"警告：这一段仍然超过 {limit_mb} MB，建议把 --segment-seconds 调小。")
                print("跳过这一段。")
                continue

            try:
                text = process_one_audio_part(
                    audio_path=part,
                    mode=current_mode,
                    language=language,
                    prompt=args.prompt,
                    api_key=api_key,
                    base_url=base_url
                )
            except Exception as e:
                print(f"调用 MiMo 失败: {e}")
                text = ""

            if looks_like_repetition_loop(text):
                print(f"警告：第 {idx} 段出现重复/乱码，建议降低 --segment-seconds 或提高 --bitrate 后重试该段。")
                results.append(f"【Part {idx}】\n[疑似重复/乱码，已跳过]")
            else:
                results.append(f"【Part {idx}】\n{text}".strip())

        final_text = "\n\n".join(results).strip()

        output_path = input_path.parent / f"{input_path.stem}.{current_mode}.speaker_transcript.txt"
        output_path.write_text(final_text, encoding="utf-8")

        print(f"\n=== {current_mode} 模式完成 ===")
        print(f"结果已保存到: {output_path}")

        print("\n===== 预览 =====")
        print(final_text[:1000])

        if len(final_text) > 1000:
            print("\n...内容较长，已截断预览，请看 txt 文件。")


if __name__ == "__main__":
    main()