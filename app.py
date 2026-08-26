import streamlit as st
import fal_client
import edge_tts
import asyncio
import tempfile
import os
import re
import subprocess
from pathlib import Path

import requests
import imageio_ffmpeg


st.set_page_config(
    page_title="Myanmar Two-Person Talking Video",
    page_icon="🎬",
    layout="centered",
)

st.title("🎬 Myanmar Two-Person Talking Video")
st.write(
    "ပုံ ၂ ပုံ + စကားပြောစာ → "
    "မိန်းကလေး / ယောကျ်ားလေး တစ်လှည့်စီပြောတဲ့ Video"
)

# -----------------------------
# FAL API Key
# -----------------------------
try:
    os.environ["FAL_KEY"] = st.secrets["FAL_KEY"]
except Exception:
    st.error("FAL_KEY မထည့်ရသေးပါ")
    st.stop()


# -----------------------------
# Myanmar Voices
# -----------------------------
VOICE_MAP = {
    "Nilar": "my-MM-NilarNeural",   # Female
    "Thiha": "my-MM-ThihaNeural",   # Male
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

    for line_no, raw_line in enumerate(
        dialogue_text.splitlines(),
        start=1,
    ):

        line = raw_line.strip()

        if not line:
            continue

        parts = re.split(
            r"[:：]",
            line,
            maxsplit=1,
        )

        if len(parts) != 2:
            invalid_lines.append(line_no)
            continue

        speaker = normalize_speaker(parts[0])
        text = parts[1].strip()

        if not speaker or not text:
            invalid_lines.append(line_no)
            continue

        items.append(
            (
                speaker,
                text,
            )
        )

    return items, invalid_lines


# -----------------------------
# Myanmar TTS
# -----------------------------
async def make_audio(
    text_value: str,
    voice_value: str,
    output_path: str,
):

    communicate = edge_tts.Communicate(
        text_value,
        voice_value,
    )

    await communicate.save(
        output_path
    )


# -----------------------------
# Save uploaded image
# -----------------------------
def save_uploaded_image(
    uploaded_file,
    folder: Path,
    base_name: str,
):

    suffix = Path(
        uploaded_file.name
    ).suffix.lower()

    if suffix not in [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ]:
        suffix = ".jpg"

    path = folder / f"{base_name}{suffix}"

    path.write_bytes(
        uploaded_file.getvalue()
    )

    return str(path)


# -----------------------------
# Download generated video
# -----------------------------
def download_file(
    url: str,
    output_path: str,
):

    with requests.get(
        url,
        stream=True,
        timeout=300,
    ) as response:

        response.raise_for_status()

        with open(
            output_path,
            "wb",
        ) as f:

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):

                if chunk:
                    f.write(chunk)


# -----------------------------
# Combine all video clips
# -----------------------------
def concat_videos(
    video_paths,
    output_path,
    work_dir: Path,
):

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    list_path = (
        work_dir /
        "concat_list.txt"
    )

    with open(
        list_path,
        "w",
        encoding="utf-8",
    ) as f:

        for video_path in video_paths:

            safe_path = str(
                Path(
                    video_path
                ).resolve()
            ).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{safe_path}'\n"
            )

    # Fast method
    copy_cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        output_path,
    ]

    copy_result = subprocess.run(
        copy_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if copy_result.returncode == 0:
        return

    # Fallback method
    encode_cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        output_path,
    ]

    encode_result = subprocess.run(
        encode_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if encode_result.returncode != 0:

        raise RuntimeError(
            "Video တွေ ပေါင်းရာမှာ error ဖြစ်ပါတယ်။\n"
            + encode_result.stderr[-1500:]
        )


# ==================================================
# UI
# ==================================================

st.subheader(
    "1️⃣ လူနှစ်ယောက်ရဲ့ ပုံကိုရွေးပါ"
)

col1, col2 = st.columns(2)


# Female image
with col1:

    nilar_image = st.file_uploader(
        "👩 Nilar — မိန်းကလေးပုံ",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
        key="nilar_image",
    )

    if nilar_image is not None:

        st.image(
            nilar_image,
            caption="👩 Nilar",
            use_container_width=True,
        )


# Male image
with col2:

    thiha_image = st.file_uploader(
        "👨 Thiha — ယောကျ်ားလေးပုံ",
        type=[
            "jpg",
            "jpeg",
            "png",
            "webp",
        ],
        key="thiha_image",
    )

    if thiha_image is not None:

        st.image(
            thiha_image,
            caption="👨 Thiha",
            use_container_width=True,
        )


# ==================================================
# Dialogue
# ==================================================

st.subheader(
    "2️⃣ တစ်လှည့်စီပြောမယ့်စာရေးပါ"
)

dialogue = st.text_area(

    "စာကြောင်းတိုင်းကို "
    "Nilar: သို့ Thiha: နဲ့စပါ",

    value=(

        "Nilar: မင်္ဂလာပါ။ ဘယ်သွားမလို့လဲ။\n"

        "Thiha: ဈေးသွားမလို့ပါ။ "
        "ဘာဝယ်ပေးရမလဲ။\n"

        "Nilar: ဟင်းသီးဟင်းရွက်လေး "
        "ဝယ်ခဲ့ပေးနော်။\n"

        "Thiha: ဟုတ်ကဲ့။ "
        "ဝယ်ခဲ့ပေးမယ်။"
    ),

    height=220,
)


st.caption(
    "✅ Nilar = မိန်းကလေးအသံ | "
    "Thiha = ယောကျ်ားလေးအသံ\n"
    "မြန်မာလို "
    "'မိန်းကလေး:' / 'ကောင်လေး:' "
    "လို့လည်းရေးလို့ရပါတယ်။"
)


parsed_dialogue, invalid_lines = (
    parse_dialogue(dialogue)
)


if invalid_lines:

    st.warning(
        "ဒီစာကြောင်းတွေမှာ "
        "format မမှန်ပါ: "
        + ", ".join(
            map(
                str,
                invalid_lines,
            )
        )
    )


if parsed_dialogue:

    st.info(
        f"စကားပြောအလှည့် "
        f"{len(parsed_dialogue)} ခု "
        "တွေ့ပါတယ်။"
    )


# ==================================================
# Generate button
# ==================================================

generate = st.button(
    "🎬 နှစ်ယောက် တစ်လှည့်စီပြောတဲ့ Video ထုတ်မယ်",
    use_container_width=True,
)


if generate:

    if invalid_lines:

        st.error(
            "Format မမှန်တဲ့ "
            "စာကြောင်းတွေကို "
            "အရင်ပြင်ပါ။"
        )

        st.stop()


    if not parsed_dialogue:

        st.warning(
            "စကားပြောစာ "
            "အရင်ထည့်ပါ။"
        )

        st.stop()


    # Stop accidental large credit usage
    if len(parsed_dialogue) > 10:

        st.warning(
            "ပထမဆုံးစမ်းဖို့ "
            "စကားပြောအလှည့် "
            "10 ခုအောက်ပဲ ထည့်ပါ။"
        )

        st.stop()


    used_speakers = {
        speaker
        for speaker, _
        in parsed_dialogue
    }


    if (
        "Nilar" in used_speakers
        and nilar_image is None
    ):

        st.warning(
            "Nilar ပြောမယ့်စာရှိလို့ "
            "မိန်းကလေးပုံကို "
            "အရင်တင်ပါ။"
        )

        st.stop()


    if (
        "Thiha" in used_speakers
        and thiha_image is None
    ):

        st.warning(
            "Thiha ပြောမယ့်စာရှိလို့ "
            "ယောကျ်ားလေးပုံကို "
            "အရင်တင်ပါ။"
        )

        st.stop()


    progress = st.progress(0)
    status = st.empty()


    try:

        with tempfile.TemporaryDirectory() as tmp:

            work_dir = Path(tmp)

            image_paths = {}
            image_urls = {}


            # -------------------------
            # Save images
            # -------------------------
            if nilar_image is not None:

                image_paths["Nilar"] = (
                    save_uploaded_image(
                        nilar_image,
                        work_dir,
                        "nilar",
                    )
                )


            if thiha_image is not None:

                image_paths["Thiha"] = (
                    save_uploaded_image(
                        thiha_image,
                        work_dir,
                        "thiha",
                    )
                )


            # -------------------------
            # Upload images to FAL
            # -------------------------
            status.write(
                "📤 ပုံတွေ Upload "
                "လုပ်နေပါတယ်..."
            )


            for speaker in used_speakers:

                image_urls[speaker] = (
                    fal_client.upload_file(
                        image_paths[speaker]
                    )
                )


            clip_paths = []

            total = len(
                parsed_dialogue
            )


            # ==================================================
            # Generate every dialogue turn
            # ==================================================
            for index, (
                speaker,
                text,
            ) in enumerate(
                parsed_dialogue,
                start=1,
            ):


                if speaker == "Nilar":

                    speaker_label = (
                        "👩 Nilar"
                    )

                else:

                    speaker_label = (
                        "👨 Thiha"
                    )


                status.write(

                    f"🎙️ {index}/{total} — "
                    f"{speaker_label} "
                    "အသံနဲ့ Video "
                    "လုပ်နေပါတယ်..."
                )


                # -------------------------
                # Make Myanmar audio
                # -------------------------
                audio_path = str(
                    work_dir /
                    f"audio_{index:02d}.mp3"
                )


                asyncio.run(
                    make_audio(
                        text,
                        VOICE_MAP[
                            speaker
                        ],
                        audio_path,
                    )
                )


                # -------------------------
                # Upload audio
                # -------------------------
                audio_url = (
                    fal_client.upload_file(
                        audio_path
                    )
                )


                # -------------------------
                # Generate talking video
                # -------------------------
                result = (
                    fal_client.subscribe(

                        "fal-ai/flashtalk",

                        arguments={
                            "image_url":
                                image_urls[
                                    speaker
                                ],

                            "audio_url":
                                audio_url,
                        },
                    )
                )


                video_url = (
                    result[
                        "video"
                    ][
                        "url"
                    ]
                )


                # -------------------------
                # Download video clip
                # -------------------------
                clip_path = str(
                    work_dir /
                    f"clip_{index:02d}.mp4"
                )


                download_file(
                    video_url,
                    clip_path,
                )


                clip_paths.append(
                    clip_path
                )


                progress.progress(
                    int(
                        index /
                        total *
                        90
                    )
                )


            # ==================================================
            # Join all clips
            # ==================================================
            status.write(
                "🎞️ Video အပိုင်းတွေ "
                "တစ်ပုဒ်တည်းဖြစ်အောင် "
                "ပေါင်းနေပါတယ်..."
            )


            final_path = str(
                work_dir /
                "myanmar_two_person_video.mp4"
            )


            concat_videos(
                clip_paths,
                final_path,
                work_dir,
            )


            final_bytes = (
                Path(
                    final_path
                ).read_bytes()
            )


            progress.progress(100)

            status.empty()


            st.success(
                "🎉 Video ပြီးပါပြီ!"
            )


            st.video(
                final_bytes
            )


            st.download_button(

                "📥 Video Download",

                data=final_bytes,

                file_name=(
                    "myanmar_two_person_"
                    "talking_video.mp4"
                ),

                mime="video/mp4",

                use_container_width=True,
            )


    except Exception as e:

        st.error(
            "Video ထုတ်ရာမှာ "
            "Error ဖြစ်နေပါတယ်"
        )

        st.code(
            str(e)
        )
