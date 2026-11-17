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

def update_item_category(item_id: str, new_category: str):
    """Ändert nachträglich die Kategorie eines Kleidungsstücks in Supabase."""
    supabase.table("wardrobe_items").update({"category": new_category}).eq("id", item_id).execute()

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

# --- 4. KARUSSELL-ZEILE (MIT SEITLICHER VORSCHAU & LOCK-PIN) ---
def render_carousel_row(category_label: str, items: list, state_key: str, main_width: int, side_width: int):
    """Rendert: [Vorschau links] [‹] [Hauptbild] [›] [Vorschau rechts] + Lock-Pin."""
    if not items:
        st.caption(f"Noch keine {category_label} vorhanden.")
        return None

    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    lock_key = f"lock_{state_key}"
    if lock_key not in st.session_state:
        st.session_state[lock_key] = False

    n = len(items)
    idx = st.session_state[state_key] % n
    current_item = items[idx]
    prev_item = items[(idx - 1) % n]
    next_item = items[(idx + 1) % n]
    is_locked = st.session_state[lock_key]

    col_prev, col_left, col_main, col_right, col_next = st.columns(
        [0.9, 0.8, 3.4, 0.8, 0.9], vertical_alignment="center"
    )

    with col_prev:
        if n > 1 and not is_locked:
            st.image(prev_item["image_url"], width=side_width)
    with col_left:
        if st.button("‹", key=f"prev_{state_key}", use_container_width=True, disabled=(n <= 1 or is_locked)):
            st.session_state[state_key] = (idx - 1) % n
            st.rerun()
        # Dezenter Lock-Pin direkt unter dem linken Pfeil
        lock_icon = "🔒" if is_locked else "🔓"
        if st.button(lock_icon, key=f"btn_{lock_key}", use_container_width=True, help=f"{category_label} beim Shuffle fixieren"):
            st.session_state[lock_key] = not is_locked
            st.rerun()
    with col_main:
        st.image(current_item["image_url"], width=main_width)
    with col_right:
        if st.button("›", key=f"next_{state_key}", use_container_width=True, disabled=(n <= 1 or is_locked)):
            st.session_state[state_key] = (idx + 1) % n
            st.rerun()
    with col_next:
        if n > 1 and not is_locked:
            st.image(next_item["image_url"], width=side_width)

    return current_item

# --- 5. HAUPT-OBERFLÄCHE ---
st.markdown("<h2 style='text-align: center; font-family: serif; letter-spacing: -0.5px; margin-bottom: 0.1rem;'>Dress Me</h2>", unsafe_allow_html=True)

all_items = fetch_wardrobe()

tab_swiper, tab_closet, tab_saved, tab_upload = st.tabs([
    "👗 Dress Me", 
    f"🗄️ Schrank ({len(all_items)})", 
    "⭐ Outfits", 
    "➕ Upload"
])

# === TAB 1: OUTFIT SWIPER ===
with tab_swiper:
    tops = [i for i in all_items if str(i.get("category", "")).strip() == "Oberteil"]
    jackets = [i for i in all_items if str(i.get("category", "")).strip() == "Jacke"]
    pants = [i for i in all_items if str(i.get("category", "")).strip() == "Hose"]
    shoes = [i for i in all_items if str(i.get("category", "")).strip() == "Schuhe"]

    top_1, top_2 = st.columns([1, 1], vertical_alignment="center")
    with top_1:
        include_jacket = st.toggle("🧥 + Jacke", value=False)
    with top_2:
        if st.button("⇅ Shuffle", use_container_width=True):
            # Würfelt nur Kategorien neu aus, die NICHT per 🔒 gesperrt sind
            if tops and not st.session_state.get("lock_idx_top", False):
                st.session_state["idx_top"] = random.randint(0, len(tops) - 1)
            if jackets and not st.session_state.get("lock_idx_jacket", False):
                st.session_state["idx_jacket"] = random.randint(0, len(jackets) - 1)
            if pants and not st.session_state.get("lock_idx_pants", False):
                st.session_state["idx_pants"] = random.randint(0, len(pants) - 1)
            if shoes and not st.session_state.get("lock_idx_shoes", False):
                st.session_state["idx_shoes"] = random.randint(0, len(shoes) - 1)
            st.rerun()

    selected_ids = []
    if include_jacket:
        sel_jacket = render_carousel_row("Jacke", jackets, "idx_jacket", main_width=150, side_width=38)
        if sel_jacket: selected_ids.append(sel_jacket["id"])

    sel_top = render_carousel_row("Oberteil", tops, "idx_top", main_width=165, side_width=42)
    if sel_top: selected_ids.append(sel_top["id"])

    sel_pants = render_carousel_row("Hose", pants, "idx_pants", main_width=170, side_width=40)
    if sel_pants: selected_ids.append(sel_pants["id"])

    sel_shoes = render_carousel_row("Schuhe", shoes, "idx_shoes", main_width=115, side_width=34)
    if sel_shoes: selected_ids.append(sel_shoes["id"])

    # Kollisionsfreie Speichern-Box (linksbündig mit Platz zum roten Streamlit-Badge rechts)
    if len(selected_ids) >= 2:
        st.write("")
        c_save_area, c_badge_spacer = st.columns([3.8, 1.2], vertical_alignment="center")
        with c_save_area:
            with st.popover("💾 Outfit speichern", use_container_width=True):
                outfit_name = st.text_input("Name für den Look:", placeholder="z.B. Clean Uni Look")
                if st.button("✅ Jetzt speichern", type="primary", use_container_width=True):
                    supabase.table("saved_outfits").insert({
                        "outfit_name": outfit_name or "Saved Look",
                        "item_ids": selected_ids
                    }).execute()
                    st.success("Gespeichert im Tab '⭐ Outfits'!")

# === TAB 2: KLEIDERSCHRANK-GALERIE (INKL. KATEGORIE-WECHSEL & 90°-DREHEN) ===
with tab_closet:
    if not all_items:
        st.info("Dein Kleiderschrank ist noch leer. Wechsle zum Tab '➕ Upload'!")
    else:
        filter_cat = st.radio("Filter:", ["Alle"] + CATEGORIES, horizontal=True)
        if filter_cat == "Alle":
            filtered = all_items
        else:
            filtered = [i for i in all_items if str(i.get("category", "")).strip() == filter_cat]

        st.caption(f"Zeige {len(filtered)} von {len(all_items)} Kleidungsstück(en)")

        cols = st.columns(2)
        for idx, item in enumerate(filtered):
            with cols[idx % 2]:
                with st.container(border=True):
                    st.image(item["image_url"], use_container_width=True)
                    
                    # Direktes Ändern der Kategorie per Dropdown
                    current_cat = str(item.get("category", "Oberteil")).strip()
                    cat_index = CATEGORIES.index(current_cat) if current_cat in CATEGORIES else 0
                    new_cat = st.selectbox(
                        "Kategorie",
                        options=CATEGORIES,
                        index=cat_index,
                        key=f"cat_{item['id']}",
                        label_visibility="collapsed"
                    )
                    if new_cat != current_cat:
                        update_item_category(item["id"], new_cat)
                        st.rerun()

                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("🔄 90°", key=f"rot_{item['id']}", use_container_width=True):
                            with st.spinner("Drehe..."):
                                rotate_existing_item(item)
                            st.rerun()
                    with b2:
                        if st.button("🗑️", key=f"del_{item['id']}", use_container_width=True):
                            delete_item(item["id"], item["image_url"])
                            st.rerun()

        st.divider()
        if st.button("✨ Bestehende Bilder schärfen & zuschneiden (Studio-Boost)", use_container_width=True):
            with st.spinner("Optimiere bestehende Bilder..."):
                recrop_existing_items(all_items)
            st.success("✅ Alle Bilder optimiert!")
            st.rerun()

# === TAB 3: GESPEICHERTE OUTFITS ===
with tab_saved:
    outfits = fetch_saved_outfits()
    items_by_id = {i["id"]: i for i in all_items}

    if not outfits:
        st.info("Noch keine Outfits gespeichert.")
    else:
        for outfit in outfits:
            with st.container(border=True):
                head_1, head_2 = st.columns([4, 1])
                head_1.subheader(f"⭐ {outfit.get('outfit_name') or 'Look'}")
                if head_2.button("🗑️", key=f"del_out_{outfit['id']}"):
                    supabase.table("saved_outfits").delete().eq("id", outfit["id"]).execute()
                    st.rerun()

                o_items = [items_by_id[iid] for iid in outfit.get("item_ids", []) if iid in items_by_id]
                if o_items:
                    o_cols = st.columns(len(o_items))
                    for c_idx, o_item in enumerate(o_items):
                        with o_cols[c_idx]:
                            st.image(o_item["image_url"], use_container_width=True)

# === TAB 4: BATCH-UPLOAD ===
with tab_upload:
    selected_category = st.radio("1. Kategorie wählen:", options=CATEGORIES, horizontal=True)
    uploaded_files = st.file_uploader(
        f"2. Fotos für '{selected_category}' auswählen",
        type=["jpg", "jpeg", "png", "webp", "heic", "heif"],
        accept_multiple_files=True
    )

    if uploaded_files:
        if st.button(f"✨ Alle {len(uploaded_files)} Bilder freistellen & speichern", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="Starte Batch-Verarbeitung...")
            success_count = 0
            for idx, file in enumerate(uploaded_files):
                try:
                    progress_bar.progress(idx / len(uploaded_files), text=f"✂️ Freistellen & Studio-Boost: {file.name}...")
                    cutout_img, png_bytes = process_and_remove_bg(file)
                    save_item_to_cloud(png_bytes, selected_category)
                    success_count += 1
                except Exception as e:
                    st.error(f"❌ Fehler bei {file.name}: {e}")
            progress_bar.progress(1.0, text="✅ Durchlauf beendet!")
            if success_count > 0:
                st.success(f"🎉 {success_count} Teil(e) perfekt zugeschnitten & gespeichert!")
                st.rerun()
