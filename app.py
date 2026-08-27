
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


# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="Myanmar AI Story Studio V2",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 Myanmar AI Story Studio — Version 2")
st.caption(
    "Scene တစ်ခန်းချင်း ဖန်တီး → Preview / Download → Scene အားလုံး Join → 9:16 / 16:9 Export"
)

# =========================================================
# FAL API KEY
# =========================================================
try:
    os.environ["FAL_KEY"] = st.secrets["FAL_KEY"]
except Exception:
    st.error("FAL_KEY မထည့်ရသေးပါ။ Streamlit Secrets ကို စစ်ပါ။")
    st.stop()


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
        "fal-ai/flashtalk",
        arguments={
            "image_url": image_url,
            "audio_url": audio_url,
        },
    )

    video_url = result["video"]["url"]
    clip_path = str(work_dir / f"clip_{index:02d}.mp4")
    download_file(video_url, clip_path)

    return clip_path


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
        total = len(dialogue_items)

        for index, (speaker, text) in enumerate(dialogue_items, start=1):
            if status:
                status.write(
                    f"🎙️ {index}/{total} — "
                    f"{SPEAKER_LABELS[speaker]} Video လုပ်နေပါတယ်..."
                )

            clip_path = generate_one_talking_clip(
                image_url=image_urls[speaker],
                text=text,
                speaker=speaker,
                work_dir=work_dir,
                index=index,
            )
            clip_paths.append(clip_path)

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

        return Path(final_path).read_bytes()


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
        return False, "Credit မကုန်အောင် Scene တစ်ခုမှာ စကားပြောအလှည့် 10 ခုအောက်ထားပါ။"

    used_speakers = {speaker for speaker, _ in dialogue_items}

    for speaker in used_speakers:
        if images.get(speaker) is None:
            return False, f"{SPEAKER_LABELS[speaker]} ပုံကို အရင်တင်ပါ။"

    return True, ""


# =========================================================
# SESSION STATE
# =========================================================
if "scene_count" not in st.session_state:
    st.session_state.scene_count = 1

if "final_story_video" not in st.session_state:
    st.session_state.final_story_video = None


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
            "Punchline pause / reaction zoom / funny SFX / BGM ကို Phase 2 မှာ ထည့်မယ်။"
        )

    st.caption(
        "Phase 2: 🎬 Story Motion + 🎵 Auto BGM + 🔊 Auto SFX "
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
                    "👩‍❤️‍👨 နှစ်ယောက်အပြန်အလှန်",
                ],
                horizontal=True,
                key=f"scene_{scene_no}_mode",
            )

            dialogue_items = []
            invalid_lines = []
            speaker_images = {}

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
                    placeholder="မင်္ဂလာပါ။ ဒီနေ့ အားလုံးကို စကားလေးပြောချင်ပါတယ်။",
                    height=130,
                    key=f"scene_{scene_no}_single_text",
                )

                if text_value.strip():
                    dialogue_items = [(speaker, text_value.strip())]

                speaker_images[speaker] = image_file

            else:
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
                st.rerun()

            if generate_scene:
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
                        scene_bytes = build_scene_video(
                            dialogue_items=dialogue_items,
                            speaker_images=speaker_images,
                            width=output_width,
                            height=output_height,
                            status=status,
                            progress=progress,
                        )

                        st.session_state[
                            f"scene_{scene_no}_video"
                        ] = scene_bytes

                        status.empty()
                        st.success(
                            f"✅ Scene {scene_no} ပြီးပါပြီ!"
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
                    st.success("🎉 Final Story Video ပြီးပါပြီ!")

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
        "Version 1 လို တစ်ယောက် / နှစ်ယောက် စကားပြော Video ကို မြန်မြန်ထုတ်ဖို့"
    )

    quick_mode = st.radio(
        "Quick Mode",
        [
            "🧍 တစ်ယောက်တည်း",
            "👩‍❤️‍👨 နှစ်ယောက်",
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
                quick_bytes = build_scene_video(
                    dialogue_items=quick_items,
                    speaker_images=quick_images,
                    width=output_width,
                    height=output_height,
                    status=status,
                    progress=progress,
                )

                st.session_state.quick_video = quick_bytes
                status.empty()
                st.success("✅ Quick Video ပြီးပါပြီ!")

            except Exception as e:
                status.empty()
                st.error("Quick Video ထုတ်ရာမှာ Error ဖြစ်ပါတယ်")
                st.code(str(e))

    if st.session_state.get("quick_video"):
        st.video(st.session_state.quick_video)

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
    "Myanmar AI Story Studio V2 • "
    "Next: Story Motion + Auto BGM + Auto SFX + Comedy Timing"
)
