# StyleSync – Digitaler B2C-Kleiderschrank & Outfit-Swiper

Hi, ich bin Bo und studiere Wirtschaftsinformatik an der Hochschule Osnabrück.

Ich habe StyleSync gebaut, weil ich morgens auf dem iPhone schnell sehen wollte, was ich überhaupt im Schrank habe und wie ich meine Sachen gut kombinieren kann. Andere Apps waren mir dafür viel zu umständlich, weil man jedes Teil einzeln abfotografieren, ausschneiden und ewig viele Felder ausfüllen muss.

Für mich war es außerdem spannend, nach meinem Job Scout auch mal eine kleine Anwendung direkt fürs Smartphone zu bauen. Mir ging es vor allem darum, dass die App im Alltag wirklich Spaß macht, ohne laufende Serverkosten auskommt und meine Fotos automatisch sauber freistellt.

## Was die App besonders macht

* **Batch-Upload & Zero-Effort-Freistellung:** Man kann mehrere Smartphone-Fotos (inklusive nativem Apple `.heic`/`.heif`-Format) gleichzeitig hochladen. Die Pipeline korrigiert automatisch die EXIF-Smartphone-Rotation und entfernt den Hintergrund lokal über ein leichtgewichtiges `U2Netp`-Modell (`rembg`).
* **Automatisches Cropping & Studio-Boost:** Damit jedes Kleidungsstück unabhängig vom Foto-Abstand im Swiper exakt gleich groß wirkt, schneidet ein Algorithmus (`getbbox`) alle transparenten Ränder pixelgenau ab und optimiert Helligkeit, Kontrast und Schärfe automatisch auf Studio-Niveau.
* **RAM- & Cloud-Optimierung:** Um das 1-GB-RAM-Limit der Streamlit Community Cloud auch bei großen Foto-Batches niemals zu reißen, wird die ONNX-Session über `@st.cache_resource` gecacht und jedes Bild vor der Verarbeitung ressourcenschonend skaliert.
* **Mobile-First CSS-Architektur:** Durch gezieltes Flexbox-Overriding bricht das Layout auf schmalen Smartphone-Displays nicht vertikal um, sondern verhält sich als echte Progressive Web App (PWA) auf dem iPhone-Homescreen wie eine native iOS-App.

## Mein Tech Stack

**Frontend & Mobile UI:** Python, Streamlit (Single-Page Multi-Tab Architektur mit Mobile-First Custom CSS)  
**Datenbank & Cloud Storage:** Supabase (PostgreSQL Datenbank & Public Object Storage Bucket)  
**Computer Vision & Bildverarbeitung:** `rembg` (`u2netp` via `onnxruntime`), `Pillow` (`ImageOps`, `ImageEnhance`), `pillow-heif` (Apple HEIC/HEIF-Decoder)

## Die Module

1. **Dress Me (Outfit-Swiper)**  
   Das Herzstück der App im Lookbook-Canvas-Stil. Hier lassen sich Jacke (optional zuschaltbar), Oberteil, Hose und Schuhe frei schwebend untereinander durchswipen. Mit dem **Lock-Pin (`🔒`)** können einzelne Lieblingsteile fixiert werden, während der **Shuffle-Generator (`⇅`)** den Rest des Outfits passend dazu neu auswürfelt.

2. **Mein Kleiderschrank (Cloud-Galerie)**  
   Eine nach Kategorien filterbare Übersicht aller digitalisierten Kleidungsstücke. Jedes Teil lässt sich hier bei Bedarf nachträglich mit einem Klick **um 90° drehen (`🔄`)**, in eine **andere Kategorie verschieben** oder rückstandslos aus Datenbank und Cloud-Storage löschen.

3. **Gespeicherte Outfits (Lookbook-Vault)**  
   Gefundene Lieblings-Kombinationen können direkt aus dem Swiper heraus unter eigenem Namen (z. B. *„Clean Uni Look“*) in Supabase gespeichert und jederzeit im Lookbook abgerufen werden.

4. **Batch-Uploader & Bild-Pipeline**  
   Kategorie wählen, beliebig viele Handyfotos aus der iPhone-Mediathek auswählen und in einem Durchlauf automatisch freistellen, zuschneiden, belichten und in der Cloud sichern lassen.
