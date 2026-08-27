import streamlit as st
import fal_client
import edge_tts
import asyncio
import tempfile
import os
import re
import subprocess
import wave
from pathlib import Path

import requests
import imageio_ffmpeg


# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="Myanmar AI Story Studio V2.2",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 Myanmar AI Story Studio — Version 2.2")
st.caption(
    "Scene တစ်ခန်းချင်း ဖန်တီး → Preview / Download → Scene အားလုံး Join → "
    "9:16 / 16:9 Export"
)


# =========================================================
# FAL API KEY
# =========================================================
def read_secret(name, default=None):
    try:
        return st.secrets[name]
    except Exception:
        return default


FAL_KEY = read_secret("FAL_KEY")

if not FAL_KEY:
    st.error("FAL_KEY မထည့်ရသေးပါ။ Streamlit Secrets ကို စစ်ပါ။")
    st.stop()

os.environ["FAL_KEY"] = FAL_KEY


# =========================================================
# CONSTANTS
# =========================================================
VOICE_MAP = {
    "Nilar": "my-MM-NilarNeural",
    "Thiha": "my-MM-ThihaNeural",
}

SPEAKER_LABELS = {
    "Nilar": "👩 Nilar — မိန်းကလေး",
    "Thiha": "👨 Thiha — ယောကျ်ားလေး",
}

SPEAKER_ALIASES = {
    "nilar": "Nilar",
    "နီလာ": "Nilar",
    "မိန်းကလေး": "Nilar",
    "ကောင်မလေး": "Nilar",
    "female": "Nilar",
    "thiha": "Thiha",
    "သီဟ": "Thiha",
    "ယောကျ်ားလေး": "Thiha",
    "ကောင်လေး": "Thiha",
    "male": "Thiha",
}

ASPECT_PRESETS = {
    "📱 9:16 — TikTok / Reels / Shorts": (720, 1280),
    "🖥️ 16:9 — YouTube / Facebook": (1280, 720),
}

STORY_TYPES = [
    "Family Drama",
    "Romance",
    "Comedy 😂",
    "Sad / Emotional",
    "Horror",
    "Other",
]

FLASH_MODEL = "fal-ai/flashtalk"
COUPLE_MODEL = "fal-ai/ai-avatar/multi"

# Fallback prices if fal pricing API is temporarily unavailable.
# Current public prices can change, so the app also tries to refresh them.
FLASH_FALLBACK_PER_SEC = 0.02
COUPLE_FALLBACK_480_PER_SEC = 0.20

FAL_BILLING_URL = "https://fal.ai/dashboard/usage-billing/billing"


# =========================================================
# HELPERS
# =========================================================
def normalize_speaker(name: str):
    cleaned = (
        name.replace("👩", "")
        .replace("👨", "")
        .replace("🧑", "")
        .strip()
        .lower()
    )
    return SPEAKER_ALIASES.get(cleaned)


def parse_dialogue(dialogue_text: str):
    items = []
    invalid_lines = []

    for line_no, raw_line in enumerate(dialogue_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = re.split(r"[:：]", line, maxsplit=1)
        if len(parts) != 2:
            invalid_lines.append(line_no)
            continue

        speaker = normalize_speaker(parts[0])
        text = parts[1].strip()

        if not speaker or not text:
            invalid_lines.append(line_no)
            continue

        items.append((speaker, text))

    return items, invalid_lines


async def make_audio(text_value: str, voice_value: str, output_path: str):
    communicate = edge_tts.Communicate(text_value, voice_value)
    await communicate.save(output_path)


def save_uploaded_image(uploaded_file, folder: Path, base_name: str):
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in [".jpg", ".jpeg", ".png", ".webp"]:
        suffix = ".jpg"

    path = folder / f"{base_name}{suffix}"
    path.write_bytes(uploaded_file.getvalue())
    return str(path)


def download_file(url: str, output_path: str):
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def run_ffmpeg(cmd, error_title="FFmpeg error"):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{error_title}\n\n"
            + result.stderr[-1800:]
        )

    return result


def concat_videos(video_paths, output_path, work_dir: Path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    list_path = work_dir / "concat_list.txt"

    with open(list_path, "w", encoding="utf-8") as f:
        for video_path in video_paths:
            safe_path = str(Path(video_path).resolve()).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    cmd = [
        ffmpeg,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    run_ffmpeg(cmd, "Video အပိုင်းတွေ ပေါင်းရာမှာ Error ဖြစ်ပါတယ်။")


def fit_video(input_path: str, output_path: str, width: int, height: int):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    run_ffmpeg(cmd, "Video Size ပြောင်းရာမှာ Error ဖြစ်ပါတယ်။")


def media_duration(path: str):
    """Read duration from ffmpeg output without requiring ffprobe."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg, "-i", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        result.stderr,
    )
    if not match:
        return 0.0

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def convert_to_wav(input_path: str, output_path: str):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg,
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "44100",
        "-c:a", "pcm_s16le",
        output_path,
    ]
    run_ffmpeg(cmd, "Audio WAV ပြောင်းရာမှာ Error ဖြစ်ပါတယ်။")


def wav_duration(path: str):
    with wave.open(path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        if not rate:
            return 0.0
        return frames / float(rate)


def make_silence_wav(output_path: str, duration: float):
    rate = 44100
    channels = 1
    sample_width = 2
    frames = max(1, int(duration * rate))

    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)


def concat_wavs(paths, output_path: str):
    if not paths:
        raise ValueError("Audio segments မရှိပါ။")

    with wave.open(paths[0], "rb") as first:
        params = first.getparams()
        frames = [first.readframes(first.getnframes())]

    for path in paths[1:]:
        with wave.open(path, "rb") as wf:
            if (
                wf.getnchannels() != params.nchannels
                or wf.getsampwidth() != params.sampwidth
                or wf.getframerate() != params.framerate
            ):
                raise RuntimeError("Audio format မတူပါ။")
            frames.append(wf.readframes(wf.getnframes()))

    with wave.open(output_path, "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(b"".join(frames))


def auth_headers(key):
    return {"Authorization": f"Key {key}"}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_model_price(endpoint_id: str, api_key: str, fallback: float):
    try:
        response = requests.get(
            "https://api.fal.ai/v1/models/pricing",
            params={"endpoint_id": endpoint_id},
            headers=auth_headers(api_key),
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()

        for item in data.get("prices", []):
            if item.get("endpoint_id") == endpoint_id:
                return float(item.get("unit_price", fallback))

    except Exception:
        pass

    return fallback


@st.cache_data(ttl=60, show_spinner=False)
def fetch_credit_balance(admin_key: str):
    if not admin_key:
        return None, None, "FAL_ADMIN_KEY မထည့်ရသေးပါ။"

    try:
        response = requests.get(
            "https://api.fal.ai/v1/account/billing",
            params={"expand": "credits"},
            headers=auth_headers(admin_key),
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        credits = data.get("credits") or {}
        balance = credits.get("current_balance")
        currency = credits.get("currency", "USD")

        if balance is None:
            return None, currency, "Credit balance မရပါ။"

        return float(balance), currency, None

    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        if status == 403:
            return None, None, "Exact balance ကြည့်ဖို့ ADMIN scope key လိုပါတယ်။"
        return None, None, f"Balance API error ({status or 'unknown'})"

    except Exception:
        return None, None, "Balance ကို ယာယီဖတ်မရပါ။"


FLASH_PRICE_PER_SEC = fetch_model_price(
    FLASH_MODEL,
    FAL_KEY,
    FLASH_FALLBACK_PER_SEC,
)

COUPLE_PRICE_480_PER_SEC = fetch_model_price(
    COUPLE_MODEL,
    FAL_KEY,
    COUPLE_FALLBACK_480_PER_SEC,
)


# =========================================================
# STANDARD TALKING VIDEO
# =========================================================
def generate_one_talking_clip(
    image_url: str,
    text: str,
    speaker: str,
    work_dir: Path,
    index: int,
):
    audio_path = str(work_dir / f"audio_{index:02d}.mp3")

    asyncio.run(
        make_audio(
            text,
            VOICE_MAP[speaker],
            audio_path,
        )
    )

    audio_url = fal_client.upload_file(audio_path)

    result = fal_client.subscribe(
        FLASH_MODEL,
        arguments={
            "image_url": image_url,
            "audio_url": audio_url,
        },
    )

    video_url = result["video"]["url"]
    clip_path = str(work_dir / f"clip_{index:02d}.mp4")
    download_file(video_url, clip_path)

    duration = float(result.get("duration") or 0)
    if duration <= 0:
        duration = media_duration(clip_path)

    return clip_path, duration


def build_scene_video(
    dialogue_items,
    speaker_images,
    width,
    height,
    status=None,
    progress=None,
):
    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)

        used_speakers = {speaker for speaker, _ in dialogue_items}
        image_urls = {}

        if status:
            status.write("📤 ပုံ Upload လုပ်နေပါတယ်...")

        for speaker in used_speakers:
            image_path = save_uploaded_image(
                speaker_images[speaker],
                work_dir,
                f"{speaker.lower()}_image",
            )
            image_urls[speaker] = fal_client.upload_file(image_path)

        clip_paths = []
        total_duration = 0.0
        total = len(dialogue_items)

        for index, (speaker, text) in enumerate(dialogue_items, start=1):
            if status:
                status.write(
                    f"🎙️ {index}/{total} — "
                    f"{SPEAKER_LABELS[speaker]} Video လုပ်နေပါတယ်..."
                )

            clip_path, duration = generate_one_talking_clip(
                image_url=image_urls[speaker],
                text=text,
                speaker=speaker,
                work_dir=work_dir,
                index=index,
            )
            clip_paths.append(clip_path)
            total_duration += duration

            if progress:
                progress.progress(int(index / total * 80))

        if len(clip_paths) == 1:
            joined_path = clip_paths[0]
        else:
            if status:
                status.write("🎞️ စကားပြောအပိုင်းတွေ ပေါင်းနေပါတယ်...")

            joined_path = str(work_dir / "scene_joined.mp4")
            concat_videos(
                clip_paths,
                joined_path,
                work_dir,
            )

        if progress:
            progress.progress(90)

        if status:
            status.write("📐 Video size ပြင်နေပါတယ်...")

        final_path = str(work_dir / "scene_final.mp4")
        fit_video(
            joined_path,
            final_path,
            width,
            height,
        )

        if progress:
            progress.progress(100)

        estimated_cost = total_duration * FLASH_PRICE_PER_SEC
        return Path(final_path).read_bytes(), total_duration, estimated_cost


# =========================================================
# COUPLE PHOTO MODE
# =========================================================
def build_parallel_couple_tracks(
    dialogue_items,
    first_person: str,
    second_person: str,
    work_dir: Path,
    pause_seconds: float = 0.22,
    status=None,
):
    first_segments = []
    second_segments = []

    for index, (speaker, text) in enumerate(dialogue_items, start=1):
        if status:
            status.write(
                f"🎙️ Couple audio {index}/{len(dialogue_items)} — "
                f"{SPEAKER_LABELS[speaker]}"
            )

        mp3_path = str(work_dir / f"couple_line_{index:02d}.mp3")
        wav_path = str(work_dir / f"couple_line_{index:02d}.wav")

        asyncio.run(
            make_audio(
                text,
                VOICE_MAP[speaker],
                mp3_path,
            )
        )
        convert_to_wav(mp3_path, wav_path)

        line_duration = wav_duration(wav_path)
        silent_line = str(work_dir / f"silent_line_{index:02d}.wav")
        make_silence_wav(silent_line, line_duration)

        if speaker == first_person:
            first_segments.append(wav_path)
            second_segments.append(silent_line)
        else:
            first_segments.append(silent_line)
            second_segments.append(wav_path)

        if index < len(dialogue_items) and pause_seconds > 0:
            gap = str(work_dir / f"gap_{index:02d}.wav")
            make_silence_wav(gap, pause_seconds)
            first_segments.append(gap)
            second_segments.append(gap)

    first_track = str(work_dir / "person1_track.wav")
    second_track = str(work_dir / "person2_track.wav")

    concat_wavs(first_segments, first_track)
    concat_wavs(second_segments, second_track)

    return first_track, second_track


def build_couple_scene_video(
    dialogue_items,
    couple_image,
    first_person,
    second_person,
    model_resolution,
    width,
    height,
    status=None,
    progress=None,
):
    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)

        if status:
            status.write("📤 နှစ်ယောက်တွဲပုံ Upload လုပ်နေပါတယ်...")

        image_path = save_uploaded_image(
            couple_image,
            work_dir,
            "couple_image",
        )
        image_url = fal_client.upload_file(image_path)

        if progress:
            progress.progress(15)

        first_track, second_track = build_parallel_couple_tracks(
            dialogue_items=dialogue_items,
            first_person=first_person,
            second_person=second_person,
            work_dir=work_dir,
            status=status,
        )

        if progress:
            progress.progress(35)

        first_audio_url = fal_client.upload_file(first_track)
        second_audio_url = fal_client.upload_file(second_track)

        if status:
            status.write(
                "💑 MultiTalk နဲ့ နှစ်ယောက်အပြန်အလှန် Video ထုတ်နေပါတယ်..."
            )

        prompt = (
            "A natural two-person conversation. "
            f"Person 1 is {first_person} on the left side of the image. "
            f"Person 2 is {second_person} on the right side of the image. "
            "They take turns speaking naturally. "
            "Only the person whose audio is active should move their lips. "
            "Keep both people recognizable and preserve their faces, clothing, "
            "background and body proportions. Natural subtle gestures, stable camera."
        )

        result = fal_client.subscribe(
            COUPLE_MODEL,
            arguments={
                "image_url": image_url,
                "first_audio_url": first_audio_url,
                "second_audio_url": second_audio_url,
                "prompt": prompt,
                "resolution": model_resolution,
                "acceleration": "regular",
            },
        )

        if progress:
            progress.progress(80)

        video_url = result["video"]["url"]
        raw_path = str(work_dir / "couple_raw.mp4")
        download_file(video_url, raw_path)

        source_duration = media_duration(raw_path)

        if status:
            status.write("📐 Couple Video size ပြင်နေပါတယ်...")

        final_path = str(work_dir / "couple_final.mp4")
        fit_video(
            raw_path,
            final_path,
            width,
            height,
        )

        if progress:
            progress.progress(100)

        multiplier = 2.0 if model_resolution == "720p" else 1.0
        estimated_cost = (
            source_duration
            * COUPLE_PRICE_480_PER_SEC
            * multiplier
        )

        return Path(final_path).read_bytes(), source_duration, estimated_cost


# =========================================================
# JOIN
# =========================================================
def join_scene_bytes(scene_videos, width, height):
    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        normalized_paths = []

        for index, video_bytes in enumerate(scene_videos, start=1):
            raw_path = str(work_dir / f"scene_raw_{index:02d}.mp4")
            fixed_path = str(work_dir / f"scene_fixed_{index:02d}.mp4")

            Path(raw_path).write_bytes(video_bytes)

            fit_video(
                raw_path,
                fixed_path,
                width,
                height,
            )
            normalized_paths.append(fixed_path)

        output_path = str(work_dir / "final_story.mp4")

        if len(normalized_paths) == 1:
            Path(output_path).write_bytes(
                Path(normalized_paths[0]).read_bytes()
            )
        else:
            concat_videos(
                normalized_paths,
                output_path,
                work_dir,
            )

        return Path(output_path).read_bytes()


# =========================================================
# VALIDATION
# =========================================================
def validate_dialogue(dialogue_items, invalid_lines, images):
    if invalid_lines:
        return (
            False,
            "Format မမှန်တဲ့ စာကြောင်း: "
            + ", ".join(map(str, invalid_lines)),
        )

    if not dialogue_items:
        return False, "စကားပြောစာ အရင်ထည့်ပါ။"

    if len(dialogue_items) > 10:
        return (
            False,
            "Credit မကုန်အောင် Scene တစ်ခုမှာ "
            "စကားပြောအလှည့် 10 ခုအောက်ထားပါ။",
        )

    used_speakers = {speaker for speaker, _ in dialogue_items}

    for speaker in used_speakers:
        if images.get(speaker) is None:
            return False, f"{SPEAKER_LABELS[speaker]} ပုံကို အရင်တင်ပါ။"

    return True, ""


def validate_couple(dialogue_items, invalid_lines, couple_image):
    if invalid_lines:
        return (
            False,
            "Format မမှန်တဲ့ စာကြောင်း: "
            + ", ".join(map(str, invalid_lines)),
        )

    if couple_image is None:
        return False, "Thiha + Nilar နှစ်ယောက်တွဲပုံကို အရင်တင်ပါ။"

    if not dialogue_items:
        return False, "စကားပြောစာ အရင်ထည့်ပါ။"

    if len(dialogue_items) > 8:
        return (
            False,
            "Couple Mode က credit ပိုကုန်လို့ "
            "ပထမစမ်းရာမှာ စကားပြောအလှည့် 8 ခုအောက်ထားပါ။",
        )

    used = {speaker for speaker, _ in dialogue_items}
    if "Thiha" not in used or "Nilar" not in used:
        return (
            False,
            "Couple Mode စမ်းရာမှာ Thiha နဲ့ Nilar "
            "နှစ်ယောက်လုံး အနည်းဆုံး တစ်ကြောင်းစီပြောပါ။",
        )

    return True, ""


# =========================================================
# SESSION STATE
# =========================================================
if "scene_count" not in st.session_state:
    st.session_state.scene_count = 1

if "final_story_video" not in st.session_state:
    st.session_state.final_story_video = None

if "session_estimated_cost" not in st.session_state:
    st.session_state.session_estimated_cost = 0.0


# =========================================================
# CREDIT DASHBOARD
# =========================================================
with st.container(border=True):
    st.subheader("💳 fal Credit Dashboard")

    admin_key = read_secret("FAL_ADMIN_KEY")
    balance, currency, balance_error = fetch_credit_balance(admin_key)

    c1, c2, c3 = st.columns(3)

    with c1:
        if balance is not None:
            st.metric(
                "Credit Balance",
                f"${balance:,.2f}",
            )
        else:
            st.metric("Credit Balance", "—")

    with c2:
        st.metric(
            "This Session Used (estimated)",
            f"${st.session_state.session_estimated_cost:,.3f}",
        )

    with c3:
        if balance is not None:
            st.metric(
                "Current Balance",
                f"${balance:,.2f} {currency or 'USD'}",
            )
        else:
            st.metric("Balance Status", "Not connected")

    if balance_error:
        st.caption(
            "ℹ️ " + balance_error
            + "  Video Generate ကတော့ FAL_KEY နဲ့ ဆက်အလုပ်လုပ်နိုင်ပါတယ်။"
        )

    b1, b2 = st.columns(2)

    with b1:
        st.link_button(
            "➕ Add / Buy fal Credits",
            FAL_BILLING_URL,
            use_container_width=True,
        )

    with b2:
        if st.button(
            "🔄 Refresh Balance",
            use_container_width=True,
        ):
            fetch_credit_balance.clear()
            st.rerun()

    st.caption(
        f"FlashTalk ≈ ${FLASH_PRICE_PER_SEC:.3f}/video sec • "
        f"Couple MultiTalk 480p ≈ ${COUPLE_PRICE_480_PER_SEC:.3f}/video sec • "
        "720p Couple ≈ 2×"
    )


# =========================================================
# PROJECT SETTINGS
# =========================================================
with st.container(border=True):
    st.subheader("🎞️ Project Settings")

    col1, col2, col3 = st.columns(3)

    with col1:
        project_name = st.text_input(
            "Project Name",
            value="My Myanmar Story",
        )

    with col2:
        story_type = st.selectbox(
            "Story Type",
            STORY_TYPES,
        )

    with col3:
        aspect_label = st.selectbox(
            "Output Size",
            list(ASPECT_PRESETS.keys()),
        )

    output_width, output_height = ASPECT_PRESETS[aspect_label]

    if "Comedy" in story_type:
        st.info(
            "😂 Comedy Mode ရွေးထားပါတယ်။ "
            "Punchline pause / reaction zoom / funny SFX / BGM ကို နောက်အဆင့်မှာ ထည့်မယ်။"
        )

    st.caption(
        "Next: 🎬 Story Motion + 🎵 Auto BGM + 🔊 Auto SFX "
        "(phone ring, door close, footsteps, comedy reactions...)"
    )


# =========================================================
# TABS
# =========================================================
tab_story, tab_quick = st.tabs(
    ["🎬 Story Studio", "💬 Quick Talk"]
)


# =========================================================
# STORY STUDIO
# =========================================================
with tab_story:
    st.subheader("🎬 Scene Builder")

    top_col1, top_col2, top_col3 = st.columns(3)

    with top_col1:
        if st.button("➕ Add Scene", use_container_width=True):
            st.session_state.scene_count += 1
            st.rerun()

    with top_col2:
        if st.button(
            "➖ Remove Last Scene",
            use_container_width=True,
            disabled=st.session_state.scene_count <= 1,
        ):
            last = st.session_state.scene_count

            for suffix in [
                "video",
                "mode",
                "single_speaker",
                "single_image",
                "single_text",
                "nilar_image",
                "thiha_image",
                "dialogue",
                "existing_video",
                "couple_image",
                "couple_dialogue",
                "couple_order",
                "couple_resolution",
                "last_cost",
                "last_duration",
            ]:
                st.session_state.pop(
                    f"scene_{last}_{suffix}",
                    None,
                )

            st.session_state.scene_count -= 1
            st.rerun()

    with top_col3:
        st.metric("Scenes", st.session_state.scene_count)

    for scene_no in range(1, st.session_state.scene_count + 1):
        with st.expander(
            f"🎞️ Scene {scene_no}",
            expanded=(scene_no == 1),
        ):
            scene_mode = st.radio(
                "Scene Mode",
                [
                    "🧍 တစ်ယောက်တည်းပြော",
                    "👩‍❤️‍👨 နှစ်ယောက်ပုံခွဲ အပြန်အလှန်",
                    "💑 နှစ်ယောက်တွဲပုံတစ်ပုံ အပြန်အလှန်",
                ],
                key=f"scene_{scene_no}_mode",
            )

            dialogue_items = []
            invalid_lines = []
            speaker_images = {}
            couple_image = None
            couple_first_person = "Thiha"
            couple_second_person = "Nilar"
            couple_resolution = "480p"

            # -------------------------------------------------
            # Recover / reuse already-downloaded MP4
            # -------------------------------------------------
            with st.expander("📤 Download ထားပြီးသား Scene Video ပြန်သုံးမယ်"):
                existing_video = st.file_uploader(
                    f"Scene {scene_no} MP4 ကိုရွေးပါ",
                    type=["mp4"],
                    key=f"scene_{scene_no}_existing_video",
                    help=(
                        "အရင် Generate လုပ်ပြီး Download သိမ်းထားတဲ့ "
                        "Scene MP4 ကို ဒီမှာပြန်တင်နိုင်ပါတယ်။"
                    ),
                )

                if existing_video is not None:
                    st.video(existing_video)

                    if st.button(
                        f"✅ ဒီ MP4 ကို Scene {scene_no} အဖြစ်သုံးမယ်",
                        use_container_width=True,
                        key=f"use_existing_scene_{scene_no}",
                    ):
                        st.session_state[
                            f"scene_{scene_no}_video"
                        ] = existing_video.getvalue()

                        st.session_state[
                            f"scene_{scene_no}_last_cost"
                        ] = 0.0

                        st.session_state.final_story_video = None

                        st.success(
                            f"✅ Scene {scene_no} ကို ပြန်ထည့်ပြီးပါပြီ — "
                            "fal credit မကုန်ပါ။"
                        )
                        st.rerun()

            # -------------------------------------------------
            # SINGLE
            # -------------------------------------------------
            if scene_mode.startswith("🧍"):
                speaker = st.selectbox(
                    "ဘယ်သူပြောမလဲ",
                    ["Thiha", "Nilar"],
                    format_func=lambda x: SPEAKER_LABELS[x],
                    key=f"scene_{scene_no}_single_speaker",
                )

                image_file = st.file_uploader(
                    f"Scene {scene_no} — {SPEAKER_LABELS[speaker]} ပုံ",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"scene_{scene_no}_single_image",
                )

                if image_file is not None:
                    st.image(
                        image_file,
                        caption=SPEAKER_LABELS[speaker],
                        width=320,
                    )

                text_value = st.text_area(
                    "ပြောမယ့်စာ",
                    placeholder=(
                        "မင်္ဂလာပါ။ ဒီနေ့ အားလုံးကို "
                        "စကားလေးပြောချင်ပါတယ်။"
                    ),
                    height=130,
                    key=f"scene_{scene_no}_single_text",
                )

                if text_value.strip():
                    dialogue_items = [(speaker, text_value.strip())]

                speaker_images[speaker] = image_file

            # -------------------------------------------------
            # TWO SEPARATE PHOTOS
            # -------------------------------------------------
            elif scene_mode.startswith("👩‍❤️‍👨"):
                col_a, col_b = st.columns(2)

                with col_a:
                    nilar_image = st.file_uploader(
                        "👩 Nilar — မိန်းကလေးပုံ",
                        type=["jpg", "jpeg", "png", "webp"],
                        key=f"scene_{scene_no}_nilar_image",
                    )

                    if nilar_image is not None:
                        st.image(
                            nilar_image,
                            caption="👩 Nilar",
                            use_container_width=True,
                        )

                with col_b:
                    thiha_image = st.file_uploader(
                        "👨 Thiha — ယောကျ်ားလေးပုံ",
                        type=["jpg", "jpeg", "png", "webp"],
                        key=f"scene_{scene_no}_thiha_image",
                    )

                    if thiha_image is not None:
                        st.image(
                            thiha_image,
                            caption="👨 Thiha",
                            use_container_width=True,
                        )

                dialogue_text = st.text_area(
                    "တစ်လှည့်စီပြောမယ့်စာ",
                    value=(
                        "Thiha: မင်္ဂလာပါ နီလာ။\n"
                        "Nilar: မင်္ဂလာပါ သီဟ။"
                    ),
                    height=170,
                    key=f"scene_{scene_no}_dialogue",
                )

                st.caption(
                    "စာကြောင်းတိုင်း `Thiha:` သို့ `Nilar:` နဲ့စပါ။"
                )

                dialogue_items, invalid_lines = parse_dialogue(
                    dialogue_text
                )

                speaker_images = {
                    "Nilar": nilar_image,
                    "Thiha": thiha_image,
                }

            # -------------------------------------------------
            # COUPLE PHOTO MODE
            # -------------------------------------------------
            else:
                st.info(
                    "💑 ဒီ Mode က နှစ်ယောက်ပါတဲ့ ပုံ ၁ ပုံတည်းနဲ့ "
                    "Thiha / Nilar အလှည့်ကျပြောဖို့ MultiTalk ကိုသုံးပါတယ်။"
                )

                st.warning(
                    "⚠️ Couple MultiTalk က FlashTalk ထက် credit ပိုကုန်ပါတယ်။ "
                    "ပထမဆုံး 480p + စကားတိုတိုနဲ့ စမ်းပါ။"
                )

                couple_image = st.file_uploader(
                    "💑 Thiha + Nilar နှစ်ယောက်တွဲပုံ",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"scene_{scene_no}_couple_image",
                )

                if couple_image is not None:
                    st.image(
                        couple_image,
                        caption="💑 Couple Photo",
                        width=380,
                    )

                couple_order = st.radio(
                    "ပုံထဲမှာ ဘယ်သူက ဘယ်ဘက်မှာလဲ",
                    [
                        "👨 Thiha ဘယ်ဘက် • 👩 Nilar ညာဘက်",
                        "👩 Nilar ဘယ်ဘက် • 👨 Thiha ညာဘက်",
                    ],
                    key=f"scene_{scene_no}_couple_order",
                )

                if couple_order.startswith("👨"):
                    couple_first_person = "Thiha"
                    couple_second_person = "Nilar"
                else:
                    couple_first_person = "Nilar"
                    couple_second_person = "Thiha"

                couple_dialogue = st.text_area(
                    "💬 Couple အလှည့်ကျ စကားပြောစာ",
                    value=(
                        "Thiha: နီလာရေ၊ ဒီနေ့ အတူတူရှိရတာ ပျော်တယ်နော်။\n"
                        "Nilar: ဟုတ်တာပေါ့ ကိုသီဟ၊ နေ့တိုင်း ဒီလိုဆိုကောင်းမှာပဲ။"
                    ),
                    height=180,
                    key=f"scene_{scene_no}_couple_dialogue",
                )

                dialogue_items, invalid_lines = parse_dialogue(
                    couple_dialogue
                )

                resolution_label = st.radio(
                    "Couple Model Quality",
                    [
                        "480p — စမ်းသပ်ဖို့ / Credit သက်သာ",
                        "720p — Quality ပိုကောင်း / Credit ~2×",
                    ],
                    horizontal=True,
                    key=f"scene_{scene_no}_couple_resolution",
                )

                couple_resolution = (
                    "720p"
                    if resolution_label.startswith("720p")
                    else "480p"
                )

                rate = COUPLE_PRICE_480_PER_SEC * (
                    2 if couple_resolution == "720p" else 1
                )

                st.caption(
                    f"💰 လက်ရှိခန့်မှန်း rate: ${rate:.3f} / generated video second"
                )

            if invalid_lines:
                st.warning(
                    "Format မမှန်တဲ့ စာကြောင်း: "
                    + ", ".join(map(str, invalid_lines))
                )

            if dialogue_items:
                st.caption(
                    f"စကားပြောအလှည့် {len(dialogue_items)} ခု"
                )

            generate_col, clear_col = st.columns([2, 1])

            with generate_col:
                generate_scene = st.button(
                    f"🎬 Scene {scene_no} Generate",
                    use_container_width=True,
                    key=f"generate_scene_{scene_no}",
                )

            with clear_col:
                clear_scene = st.button(
                    "🗑️ Result Clear",
                    use_container_width=True,
                    key=f"clear_scene_{scene_no}",
                )

            if clear_scene:
                st.session_state.pop(
                    f"scene_{scene_no}_video",
                    None,
                )
                st.session_state.pop(
                    f"scene_{scene_no}_last_cost",
                    None,
                )
                st.session_state.pop(
                    f"scene_{scene_no}_last_duration",
                    None,
                )
                st.rerun()

            if generate_scene:
                is_couple_mode = scene_mode.startswith("💑")

                if is_couple_mode:
                    ok, message = validate_couple(
                        dialogue_items,
                        invalid_lines,
                        couple_image,
                    )
                else:
                    ok, message = validate_dialogue(
                        dialogue_items,
                        invalid_lines,
                        speaker_images,
                    )

                if not ok:
                    st.warning(message)

                else:
                    progress = st.progress(0)
                    status = st.empty()

                    try:
                        if is_couple_mode:
                            scene_bytes, duration, scene_cost = (
                                build_couple_scene_video(
                                    dialogue_items=dialogue_items,
                                    couple_image=couple_image,
                                    first_person=couple_first_person,
                                    second_person=couple_second_person,
                                    model_resolution=couple_resolution,
                                    width=output_width,
                                    height=output_height,
                                    status=status,
                                    progress=progress,
                                )
                            )
                        else:
                            scene_bytes, duration, scene_cost = (
                                build_scene_video(
                                    dialogue_items=dialogue_items,
                                    speaker_images=speaker_images,
                                    width=output_width,
                                    height=output_height,
                                    status=status,
                                    progress=progress,
                                )
                            )

                        st.session_state[
                            f"scene_{scene_no}_video"
                        ] = scene_bytes

                        st.session_state[
                            f"scene_{scene_no}_last_cost"
                        ] = scene_cost

                        st.session_state[
                            f"scene_{scene_no}_last_duration"
                        ] = duration

                        st.session_state.session_estimated_cost += scene_cost
                        st.session_state.final_story_video = None

                        fetch_credit_balance.clear()

                        status.empty()
                        st.success(
                            f"✅ Scene {scene_no} ပြီးပါပြီ! "
                            f"Estimated fal cost: ${scene_cost:.3f}"
                        )

                    except Exception as e:
                        status.empty()
                        st.error(
                            f"Scene {scene_no} ထုတ်ရာမှာ Error ဖြစ်ပါတယ်"
                        )
                        st.code(str(e))

            saved_scene = st.session_state.get(
                f"scene_{scene_no}_video"
            )

            if saved_scene:
                st.video(saved_scene)

                last_cost = st.session_state.get(
                    f"scene_{scene_no}_last_cost"
                )
                last_duration = st.session_state.get(
                    f"scene_{scene_no}_last_duration"
                )

                if last_cost is not None:
                    text = f"💰 Last action estimated cost: ${last_cost:.3f}"
                    if last_duration:
                        text += f" • {last_duration:.2f} sec"
                    st.caption(text)

                st.download_button(
                    f"📥 Scene {scene_no} Download",
                    data=saved_scene,
                    file_name=f"scene_{scene_no:02d}.mp4",
                    mime="video/mp4",
                    use_container_width=True,
                    key=f"download_scene_{scene_no}",
                )

    st.divider()

    generated_scene_videos = []
    generated_scene_numbers = []

    for scene_no in range(1, st.session_state.scene_count + 1):
        scene_bytes = st.session_state.get(
            f"scene_{scene_no}_video"
        )

        if scene_bytes:
            generated_scene_videos.append(scene_bytes)
            generated_scene_numbers.append(scene_no)

    st.subheader("🎞️ Final Story")

    st.write(
        f"Generated Scenes: {len(generated_scene_videos)} / "
        f"{st.session_state.scene_count}"
    )

    if len(generated_scene_videos) < st.session_state.scene_count:
        st.caption(
            "💡 Session ပြန်စသွားလို့ Scene ပျောက်ရင် Scene အတွင်းက "
            "‘Download ထားပြီးသား Scene Video ပြန်သုံးမယ်’ မှာ MP4 ပြန်တင်ပါ။ "
            "Generate ထပ်လုပ်စရာမလိုလို့ fal credit မကုန်ပါ။"
        )

    if generated_scene_numbers:
        st.caption(
            "Ready: "
            + ", ".join(
                f"Scene {n}"
                for n in generated_scene_numbers
            )
        )

    if st.button(
        "🎞️ Join All Generated Scenes",
        type="primary",
        use_container_width=True,
    ):
        if not generated_scene_videos:
            st.warning("အရင်ဆုံး Scene တစ်ခုအနည်းဆုံး Generate လုပ်ပါ။")
        else:
            with st.spinner(
                "Scene အားလုံးကို တစ်ပုဒ်တည်း ပေါင်းနေပါတယ်..."
            ):
                try:
                    final_bytes = join_scene_bytes(
                        generated_scene_videos,
                        output_width,
                        output_height,
                    )
                    st.session_state.final_story_video = final_bytes
                    st.success(
                        "🎉 Final Story Video ပြီးပါပြီ! "
                        "Join လုပ်တာ fal generation credit မကုန်ပါ။"
                    )

                except Exception as e:
                    st.error("Final Video Join လုပ်ရာမှာ Error ဖြစ်ပါတယ်")
                    st.code(str(e))

    if st.session_state.final_story_video:
        st.video(st.session_state.final_story_video)

        safe_project_name = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            project_name.strip(),
        ).strip("_") or "myanmar_story"

        st.download_button(
            "📥 Final Story Download",
            data=st.session_state.final_story_video,
            file_name=f"{safe_project_name}.mp4",
            mime="video/mp4",
            use_container_width=True,
        )


# =========================================================
# QUICK TALK
# =========================================================
with tab_quick:
    st.subheader("💬 Quick Talk")
    st.caption(
        "တစ်ယောက် / နှစ်ယောက်ပုံခွဲ စကားပြော Video ကို မြန်မြန်ထုတ်ဖို့"
    )

    quick_mode = st.radio(
        "Quick Mode",
        [
            "🧍 တစ်ယောက်တည်း",
            "👩‍❤️‍👨 နှစ်ယောက်ပုံခွဲ",
        ],
        horizontal=True,
        key="quick_mode",
    )

    quick_items = []
    quick_invalid = []
    quick_images = {}

    if quick_mode.startswith("🧍"):
        quick_speaker = st.selectbox(
            "အသံ",
            ["Thiha", "Nilar"],
            format_func=lambda x: SPEAKER_LABELS[x],
            key="quick_speaker",
        )

        quick_image = st.file_uploader(
            "ပုံတင်ပါ",
            type=["jpg", "jpeg", "png", "webp"],
            key="quick_single_image",
        )

        quick_text = st.text_area(
            "ပြောမယ့်စာ",
            key="quick_single_text",
            height=130,
        )

        if quick_text.strip():
            quick_items = [
                (quick_speaker, quick_text.strip())
            ]

        quick_images[quick_speaker] = quick_image

    else:
        q1, q2 = st.columns(2)

        with q1:
            quick_nilar = st.file_uploader(
                "👩 Nilar ပုံ",
                type=["jpg", "jpeg", "png", "webp"],
                key="quick_nilar_image",
            )

        with q2:
            quick_thiha = st.file_uploader(
                "👨 Thiha ပုံ",
                type=["jpg", "jpeg", "png", "webp"],
                key="quick_thiha_image",
            )

        quick_dialogue = st.text_area(
            "တစ်လှည့်စီပြောမယ့်စာ",
            value=(
                "Nilar: မင်္ဂလာပါ။ ဘယ်သွားမလို့လဲ။\n"
                "Thiha: ဈေးသွားမလို့ပါ။"
            ),
            height=180,
            key="quick_dialogue",
        )

        quick_items, quick_invalid = parse_dialogue(
            quick_dialogue
        )

        quick_images = {
            "Nilar": quick_nilar,
            "Thiha": quick_thiha,
        }

    if st.button(
        "🎬 Quick Video Generate",
        type="primary",
        use_container_width=True,
    ):
        ok, message = validate_dialogue(
            quick_items,
            quick_invalid,
            quick_images,
        )

        if not ok:
            st.warning(message)

        else:
            progress = st.progress(0)
            status = st.empty()

            try:
                quick_bytes, duration, quick_cost = build_scene_video(
                    dialogue_items=quick_items,
                    speaker_images=quick_images,
                    width=output_width,
                    height=output_height,
                    status=status,
                    progress=progress,
                )

                st.session_state.quick_video = quick_bytes
                st.session_state.quick_last_cost = quick_cost
                st.session_state.quick_last_duration = duration
                st.session_state.session_estimated_cost += quick_cost

                fetch_credit_balance.clear()

                status.empty()
                st.success(
                    f"✅ Quick Video ပြီးပါပြီ! "
                    f"Estimated fal cost: ${quick_cost:.3f}"
                )

            except Exception as e:
                status.empty()
                st.error("Quick Video ထုတ်ရာမှာ Error ဖြစ်ပါတယ်")
                st.code(str(e))

    if st.session_state.get("quick_video"):
        st.video(st.session_state.quick_video)

        if st.session_state.get("quick_last_cost") is not None:
            st.caption(
                f"💰 Estimated cost: "
                f"${st.session_state.quick_last_cost:.3f}"
            )

        st.download_button(
            "📥 Quick Video Download",
            data=st.session_state.quick_video,
            file_name="quick_talking_video.mp4",
            mime="video/mp4",
            use_container_width=True,
        )


# =========================================================
# FOOTER
# =========================================================
st.divider()
st.caption(
    "Myanmar AI Story Studio V2.2 • "
    "New: 💑 Couple Photo Mode + 💳 Credit Dashboard • "
    "Next: Story Motion + Auto BGM + Auto SFX + Comedy Timing"
)
