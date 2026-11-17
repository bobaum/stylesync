from __future__ import annotations
import io
import uuid
import random
import urllib.request
import streamlit as st
from PIL import Image, ImageOps
from supabase import create_client, Client

# Optionaler HEIC/HEIF-Support
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# --- 1. KONFIGURATION & MOBILE-FIRST STYLING ---
st.set_page_config(page_title="StyleSync", page_icon="👕", layout="centered")

BUCKET_NAME = "wardrobe-images"
MAX_IMAGE_SIZE = (900, 900)
CATEGORIES = ["Oberteil", "Hose", "Schuhe", "Jacke", "Accessoire"]

st.markdown("""
<style>
    .block-container {
        max-width: 460px !important;
        padding-top: 1rem !important;
        padding-bottom: 4rem !important;
    }
    /* Zwingt Spalten auf dem iPhone nebeneinander zu bleiben (kein vertikales Stapeln) */
    div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        gap: 0.35rem !important;
    }
    div[data-testid="stColumn"] {
        min-width: 0px !important;
        flex: 1 1 auto !important;
    }
    /* Bilder zentrieren & Abstände kompakt halten */
    div[data-testid="stImage"] {
        display: flex;
        justify-content: center;
        align-items: center;
        margin-bottom: -0.5rem;
    }
    div[data-testid="stImage"] img {
        object-fit: contain;
        filter: drop-shadow(0px 5px 10px rgba(0,0,0,0.18));
    }
    /* Versteckt das Vollbild-Icon auf den Bildern */
    button[title="View fullscreen"], [data-testid="StyledFullScreenButton"] {
        display: none !important;
    }
    /* Kompakte runde Buttons für Mobile */
    div.stButton > button {
        border-radius: 999px;
        padding: 0.25rem 0.5rem !important;
        min-height: 38px !important;
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
    """Lädt das leichtgewichtige u2netp-Modell einmalig in den RAM (verhindert Cloud-Crash)."""
    from rembg import new_session
    return new_session("u2netp")

# --- 3. DATENBANK- & BILD-FUNKTIONEN (MIT AUTO-CROP) ---
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

def process_and_remove_bg(uploaded_file) -> tuple:
    """Dreht, skaliert, entfernt den Hintergrund RAM-schonend und schneidet Ränder ab."""
    from rembg import remove
    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image)
    image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
    
    session = get_rembg_session()
    cutout_image = remove(image, session=session)
    cutout_image = trim_transparent_borders(cutout_image)
    
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

def recrop_existing_items(items: list):
    """Schneidet bereits hochgeladene Bilder nachträglich scharf zu."""
    for item in items:
        try:
            url = item["image_url"]
            with urllib.request.urlopen(url) as response:
                img = Image.open(io.BytesIO(response.read()))
            cropped = trim_transparent_borders(img)
            buf = io.BytesIO()
            cropped.save(buf, format="PNG", optimize=True)
            
            new_name = f"{uuid.uuid4()}.png"
            supabase.storage.from_(BUCKET_NAME).upload(
                path=new_name,
                file=buf.getvalue(),
                file_options={"content-type": "image/png"}
            )
            new_url = supabase.storage.from_(BUCKET_NAME).get_public_url(new_name)
            supabase.table("wardrobe_items").update({"image_url": new_url}).eq("id", item["id"]).execute()
        except Exception as e:
            st.error(f"Fehler beim Zuschneiden: {e}")

# --- 4. KARUSSELL-ZEILE (3 SPALTEN FÜR IPHONE) ---
def render_carousel_row(category_label: str, items: list, state_key: str, main_width: int):
    """Rendert ◀ | Kleidungsstück | ▶ garantiert nebeneinander (auch auf dem iPhone)."""
    if not items:
        st.caption(f"Noch keine {category_label} vorhanden.")
        return None

    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    n = len(items)
    idx = st.session_state[state_key] % n
    current_item = items[idx]

    col_left, col_main, col_right = st.columns([1, 4, 1], vertical_alignment="center")

    with col_left:
        if st.button("◀", key=f"prev_{state_key}", use_container_width=True, disabled=(n <= 1)):
            st.session_state[state_key] = (idx - 1) % n
            st.rerun()
    with col_main:
        st.image(current_item["image_url"], width=main_width)
    with col_right:
        if st.button("▶", key=f"next_{state_key}", use_container_width=True, disabled=(n <= 1)):
            st.session_state[state_key] = (idx + 1) % n
            st.rerun()

    return current_item

# --- 5. HAUPT-OBERFLÄCHE ---
st.markdown("<h2 style='text-align: center; margin-bottom: 0.2rem;'>Dress Me</h2>", unsafe_allow_html=True)

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

    top_bar_1, top_bar_2 = st.columns([1.2, 1], vertical_alignment="center")
    with top_bar_1:
        include_jacket = st.toggle("🧥 + Jacke", value=False)
    with top_bar_2:
        if st.button("⇅ Shuffle", use_container_width=True):
            if tops: st.session_state["idx_top"] = random.randint(0, len(tops) - 1)
            if jackets: st.session_state["idx_jacket"] = random.randint(0, len(jackets) - 1)
            if pants: st.session_state["idx_pants"] = random.randint(0, len(pants) - 1)
            if shoes: st.session_state["idx_shoes"] = random.randint(0, len(shoes) - 1)
            st.rerun()

    selected_ids = []
    # Optimierte Breiten für einen kompletten Look auf einem Smartphone-Screen
    if include_jacket:
        sel_jacket = render_carousel_row("Jacke", jackets, "idx_jacket", main_width=155)
        if sel_jacket: selected_ids.append(sel_jacket["id"])

    sel_top = render_carousel_row("Oberteil", tops, "idx_top", main_width=165)
    if sel_top: selected_ids.append(sel_top["id"])

    sel_pants = render_carousel_row("Hose", pants, "idx_pants", main_width=175)
    if sel_pants: selected_ids.append(sel_pants["id"])

    sel_shoes = render_carousel_row("Schuhe", shoes, "idx_shoes", main_width=125)
    if sel_shoes: selected_ids.append(sel_shoes["id"])

    if len(selected_ids) >= 2:
        st.write("")
        c_name, c_save = st.columns([2, 1.2], vertical_alignment="bottom")
        with c_name:
            outfit_name = st.text_input("Outfit-Name", placeholder="z.B. Clean Uni Look", label_visibility="collapsed")
        with c_save:
            if st.button("💾 Save", type="primary", use_container_width=True):
                supabase.table("saved_outfits").insert({
                    "outfit_name": outfit_name or "Saved Look",
                    "item_ids": selected_ids
                }).execute()
                st.success("✅ Gespeichert!")

# === TAB 2: KLEIDERSCHRANK-GALERIE ===
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
                    st.caption(f"**{item.get('category', 'Unbekannt')}**")
                    if st.button("🗑️ Löschen", key=f"del_{item['id']}", use_container_width=True):
                        delete_item(item["id"], item["image_url"])
                        st.rerun()

        st.divider()
        if st.button("✂️ Alle bestehenden Bilder nachträglich scharf zuschneiden", use_container_width=True):
            with st.spinner("Schneide transparente Ränder ab..."):
                recrop_existing_items(all_items)
            st.success("✅ Alle Bilder zugeschnitten!")
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
                    progress_bar.progress(idx / len(uploaded_files), text=f"✂️ Freistellen & Auto-Crop: {file.name}...")
                    cutout_img, png_bytes = process_and_remove_bg(file)
                    save_item_to_cloud(png_bytes, selected_category)
                    success_count += 1
                except Exception as e:
                    st.error(f"❌ Fehler bei {file.name}: {e}")
            progress_bar.progress(1.0, text="✅ Durchlauf beendet!")
            if success_count > 0:
                st.success(f"🎉 {success_count} Teil(e) perfekt zugeschnitten & gespeichert!")
                st.rerun()
