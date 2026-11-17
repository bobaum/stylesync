# Project Context: StyleSync (Digitaler B2C-Kleiderschrank)

## 1. Projektziel & Anforderungen (MVP)

### 1.1 Vision & Business Value
StyleSync ist eine Mobile-First Web-Anwendung zur Digitalisierung des eigenen Kleiderschranks. Der Fokus liegt auf einer schnellen Batch-Erfassung mit automatischer Hintergrundentfernung (Freistellung) und einem visuellen Outfit-Swiper ("Dress Me"), um Kleidungsstücke interaktiv zu kombinieren und Lieblings-Looks zu speichern.

### 1.2 Umgesetzte Features (Definition of Done erreicht)
- **Batch-Upload & Auto-Crop Pipeline:** Mehrfach-Upload von Smartphone-Fotos (inkl. nativem Apple `.heic`/`.heif`-Support), EXIF-Rotationskorrektur, Skalierung (max. 900px), KI-Hintergrundentfernung via `rembg` und automatisches Zuschneiden transparenter Ränder (`getbbox`).
- **Cloud-Persistence:** Speicherung der freigestellten PNGs im öffentlichen Supabase Storage Bucket (`wardrobe-images`) und der Metadaten in PostgreSQL.
- **Dress Me (Outfit-Swiper):** Frei schwebende Darstellung von Jacke (optional), Oberteil, Hose und Schuhen untereinander mit Seiten-Vorschau, `◀`/`▶`-Navigation und Zufalls-Generator (`Shuffle`).
- **Kleiderschrank-Galerie & Outfits-Vault:** Filterbare Übersicht aller Einzelteile sowie Speichern und Verwalten ganzer Outfits (inkl. Löschfunktion aus DB und Storage).

---

## 2. Aktueller Tech-Stack & FinOps-Status

- **Frontend & App-Logik:** Python 3.9, Streamlit (Single-Page Multi-Tab Architektur mit Custom CSS für Mobile-Proportionen).
- **Bildverarbeitung:** `Pillow`, `pillow-heif` (HEIC-Support), `rembg` + `onnxruntime` (lokale U2Net-Freistellung ohne API-Kosten).
- **Backend & Storage:** Supabase (PostgreSQL + Storage Bucket) im Free Tier.
- **FinOps-Bilanz:** **0,00 € / Monat** (100 % Free Tier & lokale Bildverarbeitung).

---

## 3. Wichtige Architektur-Entscheidungen (ADR)

1. **Pivot von Gemini-Zero-Data-Entry zu Batch-Kategorie-Auswahl:** Wegen temporärer `503 UNAVAILABLE`-Lastspitzen der Gemini API und um den Upload von 10+ Teilen einer Kategorie (z. B. alle Hosen auf einmal) massiv zu beschleunigen, wird die Kategorie vor dem Batch-Upload per Radio-Button gewählt. Das System hat dadurch 0 % externe API-Ausfallrate.
2. **Natives `st.image` statt Custom HTML `<img>`:** Verhindert Browser-Blocking (Safari Tracking/Mixed-Content-Schutz) beim Laden externer Supabase-URLs auf `localhost` und erhält volle Transparenz ohne störende Hintergrund-Container.
3. **Auto-Cropping (`trim_transparent_borders`):** Schneidet nach dem `rembg`-Durchlauf alle transparenten Ränder ab, sodass Kleidungsstücke unabhängig vom Foto-Abstand immer gleich groß im Swiper dargestellt werden.
4. **Python 3.9 Kompatibilität:** Einsatz von `from __future__ import annotations` und `cryptography<45.0.0` (`--only-binary=:all:`), um Rust/OpenSSL-Kompilierungsfehler auf macOS (x86_64) zu vermeiden.

---

## 4. Datenbank-Schema (Supabase PostgreSQL)

- **Tabelle `wardrobe_items`:** `id` (UUID, PK), `image_url` (Text), `category` (Text), `color` (Text, nullable), `created_at` (Timestamptz).
- **Tabelle `saved_outfits`:** `id` (UUID, PK), `outfit_name` (Text), `item_ids` (UUID[]), `created_at` (Timestamptz).
- **Storage Bucket:** `wardrobe-images` (Public, RLS Policy für Uploads freigeschaltet).

---

## 5. Offene Aufgaben & Nächste Schritte
- [x] Arbeitspaket 1: Projekt-Setup & Supabase-Infrastruktur
- [x] Arbeitspaket 2: Upload-Pipeline, `rembg`-Freistellung & Auto-Crop
- [x] Arbeitspaket 3: Kleiderschrank-Galerie & Filter
- [x] Arbeitspaket 4: "Dress Me" Outfit-Swiper & Favoriten-Speicherung
- [ ] Optionales Deployment (GitHub + Streamlit Community Cloud) für echte Nutzung auf dem iPhone oder kleinere UI-/Feature-Erweiterungen.