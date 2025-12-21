import streamlit as st
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches
import tempfile
import json
import re
import os
from io import BytesIO
from PIL import Image

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="NanoBanana PPT Agent", layout="wide", page_icon="🍌")

# --- AUTHENTICATION ---
if "APP_PASSWORD" not in st.secrets:
    st.warning("⚠️ Manca APP_PASSWORD in secrets.toml")
else:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🍌 Accesso NanoBanana")
            pwd = st.text_input("Password Workspace", type="password")
            if st.button("Entra"):
                if pwd == st.secrets["APP_PASSWORD"]:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Accesso Negato")
        st.stop()

# --- SETUP API KEY ---
api_key = st.secrets.get("GOOGLE_API_KEY")

# --- SIDEBAR: CENTRO DI CONTROLLO MODELLI (STEP 0) ---
with st.sidebar:
    st.header("⚙️ Configurazione Motore")
    
    # 1. API KEY
    if not api_key:
        api_key = st.text_input("Google API Key", type="password")
        if not api_key:
            st.warning("Inserisci API Key per iniziare")
            st.stop()
    
    genai.configure(api_key=api_key)

    # 2. SCELTA MODELLO TESTO (Auto-Discovery)
    st.subheader("1. Cervello (Testo)")
    try:
        # Chiede a Google la lista dei modelli disponibili per questa chiave
        all_models = list(genai.list_models())
        # Filtriamo solo quelli che generano contenuto ("generateContent") e sono "gemini"
        text_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name]
        # Ordiniamo per avere i pro/flash più recenti in cima
        text_models.sort(reverse=True)
        
        selected_text_model = st.selectbox(
            "Versione Gemini", 
            text_models, 
            index=0 if text_models else None
        )
    except Exception as e:
        st.error(f"Errore connessione API: {e}")
        selected_text_model = "models/gemini-1.5-pro-latest" # Fallback

    # 3. SCELTA MODELLO IMMAGINI (NanoBanana)
    st.subheader("2. Artista (Immagini)")
    imagen_options = [
        "imagen-3.0-generate-001",
        "imagen-2.0-generate-001",
        "turing-preview",
        "image-generation-001"
    ]
    selected_image_model = st.selectbox("Versione Imagen", imagen_options)

    # 4. PULSANTE TEST CONNESSIONE
    if st.button("🔌 Testa Modelli Selezionati"):
        with st.status("Verifica connessione in corso...") as status:
            # Test Testo
            try:
                st.write(f"Ping {selected_text_model}...")
                model = genai.GenerativeModel(selected_text_model)
                res = model.generate_content("Hello")
                st.write("✅ Gemini OK")
            except Exception as e:
                st.error(f"❌ Gemini Error: {e}")
            
            # Test Immagine
            try:
                st.write(f"Ping {selected_image_model}...")
                img_model = genai.ImageGenerationModel(selected_image_model)
                res = img_model.generate_images(prompt="Dot", number_of_images=1)
                st.write("✅ Imagen OK")
            except Exception as e:
                st.error(f"❌ Imagen Error: {e}")
            
            status.update(label="Test Completato", state="complete")
    
    st.divider()
    st.info(f"Usando:\n🧠 {selected_text_model}\n🎨 {selected_image_model}")

# --- FUNZIONI CORE (Aggiornate per accettare i modelli scelti) ---

def extract_content(file_path):
    prs = Presentation(file_path)
    full_text = []
    first_image = None 
    try:
        if len(prs.slides) > 0:
            for shape in prs.slides[0].shapes:
                if shape.shape_type == 13: 
                    first_image = shape.image.blob
                    break
    except: pass

    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))
    
    return "\n".join(full_text), first_image

def get_gemini_plan_and_prompts(text, model_name):
    """Usa il modello di testo selezionato dall'utente"""
    model = genai.GenerativeModel(model_name)
    
    prompt = f"""
    Sei un Creative Director esperto in Corporate Team Building.
    ANALIZZA questo contenuto grezzo: "{text[:3500]}"...
    
    OBIETTIVO 1: Ristruttura le slide per i layout: Cover_Main, Intro_Concept, Activity_Detail, Technical_Grid, Logistics_Info.
    
    OBIETTIVO 2: Scrivi 2 PROMPT per generare un'immagine di COPERTINA usando Google Imagen.
    I prompt devono essere in INGLESE, dettagliati.
    - Prompt A (Corporate): Fotorealistico, persone, luminoso.
    - Prompt B (Creative): Astratto, metaforico, oggetti 3D render.
    
    OUTPUT JSON:
    {{
        "slides": [ ...array con layout, title, body... ],
        "cover_prompt_a": "...",
        "cover_prompt_b": "..."
    }}
    Restituisci SOLO JSON valido.
    """
    try:
        resp = model.generate_content(prompt)
        cleaned = re.sub(r"```json|```", "", resp.text).strip()
        return json.loads(cleaned)
    except Exception as e:
        st.error(f"Errore Gemini Planning: {e}")
        return None

def generate_imagen_image(prompt, model_name):
    """Usa il modello immagini selezionato dall'utente"""
    try:
        imagen_model = genai.ImageGenerationModel(model_name)
        
        response = imagen_model.generate_images(
            prompt=prompt + ", high quality, 4k, photorealistic, no text",
            number_of_images=1,
            aspect_ratio="16:9",
            safety_filter_level="block_only_high",
            person_generation="allow_adult"
        )
        if response.images:
            img = response.images[0]
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
        return None
    except Exception as e:
        st.warning(f"Errore Imagen ({model_name}): {e}")
        return None

def create_final_pptx(plan, cover_image_bytes, template_path):
    prs = Presentation(template_path)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # 1. Slide Cover
    cover_layout = layout_map.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_layout)
    
    cover_data = next((s for s in plan['slides'] if s['layout'] == 'Cover_Main'), None)
    if cover_data and slide.shapes.title: 
        slide.shapes.title.text = cover_data.get('title', 'Team Building')
    
    if cover_image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
            tmp_img.write(cover_image_bytes)
            tmp_path = tmp_img.name
        try:
            inserted = False
            for shape in slide.placeholders:
                if shape.placeholder_format.type == 18: 
                    shape.insert_picture(tmp_path)
                    inserted = True
                    break
            if not inserted:
                slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
        except: pass
        os.remove(tmp_path)

    # 2. Altre Slide
    for slide_data in plan['slides']:
        if slide_data['layout'] == 'Cover_Main': continue 
        l_name = slide_data.get("layout", "Intro_Concept")
        if l_name in layout_map:
            s = prs.slides.add_slide(layout_map[l_name])
            if s.shapes.title: s.shapes.title.text = slide_data.get("title", "")
            for shape in s.placeholders:
                if shape.placeholder_format.idx == 1:
                    shape.text = slide_data.get("body", "")

    # 3. Slide Fisse
    fixed = ["Standard_Training", "Standard_Extras", "Standard_Payment", "Closing_Contact"]
    for f in fixed:
        if f in layout_map: prs.slides.add_slide(layout_map[f])

    return prs

# --- INTERFACCIA PRINCIPALE ---

st.title("🍌 NanoBanana PPT Agent")
st.caption("Configura i modelli nella barra laterale sinistra.")

if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}

# STEP 1: UPLOAD
if st.session_state.step == 1:
    col1, col2 = st.columns(2)
    with col1: template = st.file_uploader("1. Template Master (.pptx)", type=["pptx"])
    with col2: source = st.file_uploader("2. Vecchio PPT (.pptx)", type=["pptx"])
    
    if st.button("Avvia Analisi e Generazione") and template and source:
        with st.spinner("L'Agente sta lavorando..."):
            # Salvataggio
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                t.write(template.getvalue())
                st.session_state.data['tpl_path'] = t.name
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                s.write(source.getvalue())
                st.session_state.data['src_path'] = s.name

            # Esecuzione
            txt, orig_img = extract_content(st.session_state.data['src_path'])
            st.session_state.data['orig_img'] = orig_img
            
            # CHIAMATA CON IL MODELLO TESTO SELEZIONATO
            plan = get_gemini_plan_and_prompts(txt, selected_text_model)
            st.session_state.data['plan'] = plan
            
            if plan:
                # CHIAMATA CON IL MODELLO IMMAGINI SELEZIONATO
                st.info(f"Generazione cover con {selected_image_model}...")
                img_a = generate_imagen_image(plan['cover_prompt_a'], selected_image_model)
                img_b = generate_imagen_image(plan['cover_prompt_b'], selected_image_model)
                
                st.session_state.data['img_a'] = img_a
                st.session_state.data['img_b'] = img_b
            
            st.session_state.step = 2
            st.rerun()

# STEP 2: SELEZIONE E DOWNLOAD
elif st.session_state.step == 2:
    st.subheader("Scegli la Cover")
    
    col1, col2, col3 = st.columns(3)
    selection = None
    
    with col1:
        st.markdown("**Originale**")
        if st.session_state.data.get('orig_img'):
            st.image(st.session_state.data['orig_img'], use_container_width=True)
            if st.button("Usa Originale"): selection = "orig"
        else: st.info("Nessuna immagine")

    with col2:
        st.markdown("**NanoBanana: Corporate**")
        if st.session_state.data.get('img_a'):
            st.image(st.session_state.data['img_a'], use_container_width=True)
            if st.button("Scegli A"): selection = "A"
        else: st.warning("Errore generazione")

    with col3:
        st.markdown("**NanoBanana: Creative**")
        if st.session_state.data.get('img_b'):
            st.image(st.session_state.data['img_b'], use_container_width=True)
            if st.button("Scegli B"): selection = "B"

    if selection:
        final_img = None
        if selection == "orig": final_img = st.session_state.data.get('orig_img')
        elif selection == "A": final_img = st.session_state.data.get('img_a')
        elif selection == "B": final_img = st.session_state.data.get('img_b')
        
        with st.spinner("Creazione file finale..."):
            new_prs = create_final_pptx(
                st.session_state.data['plan'], 
                final_img, 
                st.session_state.data['tpl_path']
            )
            
            output_name = "PRESENTAZIONE_NANOBANANA.pptx"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_out:
                new_prs.save(tmp_out.name)
                with open(tmp_out.name, "rb") as f:
                    st.download_button("📥 SCARICA PPTX", f, output_name)
        
        if st.button("Ricomincia"):
            st.session_state.step = 1
            st.rerun()
