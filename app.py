from __future__ import annotations
import io
import uuid
import random
import urllib.request
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
from supabase import create_client, Client

# Optionaler HEIC/HEIF-Support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# --- 1. KONFIGURATION & STUDIO-LOOK STYLING ---
st.set_page_config(page_title="StyleSync", page_icon="👕", layout="centered")

BUCKET_NAME = "wardrobe-images"
MAX_IMAGE_SIZE = (900, 900)
CATEGORIES = ["Oberteil", "Hose", "Schuhe", "Jacke", "Accessoire"]

st.markdown("""
<style>
    .block-container {
        max-width: 430px !important;
        padding-top: 0.8rem !important;
        padding-bottom: 6rem !important;
    }
    /* Spalten auf dem iPhone zwingend nebeneinander halten */
    div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        gap: 0.15rem !important;
    }
    div[data-testid="stColumn"] {
        min-width: 0px !important;
        flex: 1 1 auto !important;
    }
    /* Bilder flach & clean ohne Schlagschatten, minimaler vertikaler Abstand */
    div[data-testid="stImage"] {
        display: flex;
        justify-content: center;
        align-items: center;
        margin-top: -0.35rem;
        margin-bottom: -0.35rem;
    }
    div[data-testid="stImage"] img {
        object-fit: contain;
        filter: none !important;
    }
    /* Versteckt das Vollbild-Icon auf den Bildern */
    button[title="View fullscreen"], [data-testid="StyledFullScreenButton"] {
        display: none !important;
    }
    /* Dezente, fast unsichtbare Navigations-Buttons im Swiper */
    div.stButton > button {
        border-radius: 999px;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        background-color: transparent !important;
        padding: 0.15rem 0.4rem !important;
        min-height: 34px !important;
        font-size: 0.85rem !important;
    }
    /* Primäre Buttons (Save / Upload) weiterhin kräftig hervorheben */
    div.stButton > button[kind="primary"] {
        background-color: #111111 !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 600 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. SUPABASE CLIENT & REMBG SESSION (GECACHED) ---
@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Fehler beim Laden der Supabase-Secrets: {e}")
        st.stop()

supabase = init_supabase()

@st.cache_resource
def get_rembg_session():
    """Lädt das leichtgewichtige u2netp-Modell einmalig in den RAM."""
    from rembg import new_session
    return new_session("u2netp")

# --- 3. DATENBANK- & BILD-FUNKTIONEN (AUTO-CROP & STUDIO-BOOST) ---
def fetch_wardrobe() -> list:
    res = supabase.table("wardrobe_items").select("*").order("created_at", desc=True).execute()
    return res.data or []

def fetch_saved_outfits() -> list:
    res = supabase.table("saved_outfits").select("*").order("created_at", desc=True).execute()
    return res.data or []

def delete_item(item_id: str, image_url: str):
    file_name = image_url.split("/")[-1].split("?")[0]
    try:
        supabase.storage.from_(BUCKET_NAME).remove([file_name])
    except Exception:
        pass
    supabase.table("wardrobe_items").delete().eq("id", item_id).execute()

def trim_transparent_borders(img: Image.Image) -> Image.Image:
    """Schneidet alle leeren/transparenten Ränder exakt am Kleidungsstück ab."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.split()[-1]
    mask = alpha.point(lambda p: 255 if p > 15 else 0)
    bbox = mask.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

def apply_studio_enhancement(img: Image.Image) -> Image.Image:
    """Verleiht Handyfotos automatisch leichtes Studio-Licht (+Helligkeit, +Kontrast, +Schärfe)."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    rgb_img = Image.merge("RGB", (r, g, b))
    rgb_img = ImageEnhance.Brightness(rgb_img).enhance(1.06)
    rgb_img = ImageEnhance.Contrast(rgb_img).enhance(1.08)
    rgb_img = ImageEnhance.Sharpness(rgb_img).enhance(1.15)
    r2, g2, b2 = rgb_img.split()
    return Image.merge("RGBA", (r2, g2, b2, a))

def process_and_remove_bg(uploaded_file) -> tuple:
    """Dreht, skaliert, stellt frei, schneidet Ränder ab und optimiert Belichtung."""
    from rembg import remove
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)
    image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
    
    session = get_rembg_session()
    cutout_image = remove(image, session=session)
    cutout_image = trim_transparent_borders(cutout_image)
    cutout_image = apply_studio_enhancement(cutout_image)
    
    img_byte_arr = io.BytesIO()
    cutout_image.save(img_byte_arr, format="PNG", optimize=True)
    return cutout_image, img_byte_arr.getvalue()

def save_item_to_cloud(png_bytes: bytes, category: str):
    file_name = f"{uuid.uuid4()}.png"
    supabase.storage.from_(BUCKET_NAME).upload(
        path=file_name,
        file=png_bytes,
        file_options={"content-type": "image/png"}
    )
    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(file_name)
    supabase.table("wardrobe_items").insert({
        "image_url": public_url,
        "category": category,
        "color": None
    }).execute()

def rotate_existing_item(item: dict):
    """Dreht ein bereits hochgeladenes Kleidungsstück um 90 Grad im Uhrzeigersinn."""
    url = item["image_url"]
    with urllib.request.urlopen(url) as response:
        img = Image.open(io.BytesIO(response.read()))
    rotated = img.rotate(-90, expand=True)
    rotated = trim_transparent_borders(rotated)
    buf = io.BytesIO()
    rotated.save(buf, format="PNG", optimize=True)

    new_name = f"{uuid.uuid4()}.png"
    supabase.storage.from_(BUCKET_NAME).upload(
        path=new_name,
        file=buf.getvalue(),
        file_options={"content-type": "image/png"}
    )
    new_url = supabase.storage.from_(BUCKET_NAME).get_public_url(new_name)
    supabase.table("wardrobe_items").update({"image_url": new_url}).eq("id", item["id"]).execute()

def recrop_existing_items(items: list):
    """Schneidet bestehende Bilder nach und wendet den Studio-Boost an."""
    for item in items:
        try:
            url = item["image_url"]
            with urllib.request.urlopen(url) as response:
                img = Image.open(io.BytesIO(response.read()))
            cropped = trim_transparent_borders(img)
            enhanced = apply_studio_enhancement(cropped)
            buf = io.BytesIO()
            enhanced.save(buf, format="PNG", optimize=True)
            
            new_name = f"{uuid.uuid4()}.png"
            supabase.storage.from_(BUCKET_NAME).upload(
                path=new_name,
                file=buf.getvalue(),
                file_options={"content-type": "image/png"}
            )
            new_url = supabase.storage.from_(BUCKET_NAME).get_public_url(new_name)
            supabase.table("wardrobe_items").update({"image_url": new_url}).eq("id", item["id"]).execute()
        except Exception as e:
            st.error(f"Fehler beim Optimieren: {e}")

# --- 4. KARUSSELL-ZEILE (MIT SEITLICHER VORSCHAU WIE IM VORBILD) ---
def render_carousel_row(category_label: str, items: list, state_key: str, main_width: int, side_width: int):
    """Rendert: [Vorschau links] [◀] [Hauptbild] [▶] [Vorschau rechts] in einer Zeile."""
    if not items:
        st.caption(f"Noch keine {category_label} vorhanden.")
        return None

    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    n = len(items)
    idx = st.session_state[state_key] % n
    current_item = items[idx]
    prev_item = items[(idx - 1) % n]
    next_item = items[(idx + 1) % n]

    col_prev, col_left, col_main, col_right, col_next = st.columns(
        [0.9, 0.7, 3.6, 0.7, 0.9], vertical_alignment="center"
    )

    with col_prev:
        if n > 1:
            st.image(prev_item["image_url"], width=side_width)
    with col_left:
        if st.button("‹", key=f"prev_{state_key}", use_container_width=True, disabled=(n <= 1)):
            st.session_state[state_key] = (idx - 1) % n
            st.rerun()
    with col_main:
        st.image(current_item["image_url"], width=main_width)
    with col_right:
        if st.button("›", key=f"next_{state_key}", use_container_width=True, disabled=(n <= 1)):
            st.session_state[state_key] = (idx + 1) % n
            st.rerun()
    with col_next:
        if n > 1:
            st.image(next_item["image_url"], width=side_width)

    return current_item

# --- 5. HAUPT-OBERFLÄCHE ---
st.markdown("<h2 style='text-align: center; font-family: serif; letter-spacing: -0.5px; margin-bottom: 0.1rem;'>Dress Me</h2>", unsafe_allow_html=True)

all_items = fetch_wardrobe()

tab_swiper, tab_closet, tab_saved, tab_upload = st.tabs([
    "👗 Dress Me", 
    f"🗄️ Schrank ({len(all_items)})
