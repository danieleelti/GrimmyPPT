import streamlit as st
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches, Pt
import tempfile
import json
import re
import os
from io import BytesIO

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Grimmy PPT Agent", layout="wide", page_icon="🤖")

# --- AUTHENTICATION ---
if "APP_PASSWORD" not in st.secrets:
    st.warning("⚠️ Manca APP_PASSWORD in secrets.toml")
else:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🤖 Grimmy Access")
            pwd = st.text_input("Password", type="password")
            if st.button("Sblocca"):
                if pwd == st.secrets["APP_PASSWORD"]:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("No.")
        st.stop()

# --- SETUP API KEY ---
api_key = st.secrets.get("GOOGLE_API_KEY")

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Configurazione")
    if not api_key:
        api_key = st.text_input("Google API Key", type="password")
    if api_key:
        genai.configure(api_key=api_key)

    st.markdown("---")
    
    # MODELLI
    st.subheader("🧠 Cervello")
    default_text = "gemini-3-pro-preview" 
    text_options = [default_text, "gemini-1.5-pro-latest", "gemini-1.5-flash"]
    selected_text_model = st.selectbox("Modello Testo", text_options, index=0)

    st.subheader("🎨 NanoBanana")
    default_img = "imagen-3.0-generate"
    img_options = [default_img, "imagen-3.0-generate-001", "imagen-2.0-generate-001"]
    selected_image_model = st.selectbox("Modello Immagini", img_options, index=0)

    st.markdown("---")
    
    st.subheader("📂 Template")
    template = st.file_uploader("Carica Template (.pptx)", type=["pptx"])
    if template: st.success("Template OK")

# --- FUNZIONI CORE AGGIORNATE ---

def extract_content(file_path):
    """
    Estrae testo e cerca l'immagine di copertina anche nel MASTER
    """
    prs = Presentation(file_path)
    full_text = []
    first_image = None 
    
    # --- LOGICA RAGGI X PER L'IMMAGINE ---
    try:
        if len(prs.slides) > 0:
            slide = prs.slides[0]
            
            # 1. Cerca nella Slide (Livello Superficiale)
            for shape in slide.shapes:
                if shape.shape_type == 13: # 13 = Picture
                    first_image = shape.image.blob
                    break
            
            # 2. Se non trovata, cerca nel Layout (Livello Intermedio)
            if not first_image:
                for shape in slide.slide_layout.shapes:
                    if shape.shape_type == 13:
                        first_image = shape.image.blob
                        break
            
            # 3. Se non trovata, cerca nel Master (Livello Profondo)
            if not first_image:
                for shape in slide.slide_layout.slide_master.shapes:
                    if shape.shape_type == 13:
                        first_image = shape.image.blob
                        break
    except Exception as e:
        print(f"Errore estrazione immagine: {e}")

    # --- ESTRAZIONE TESTO ---
    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))
    
    return "\n".join(full_text), first_image

def get_gemini_plan_and_prompts(text, model_name):
    st.session_state.debug_info['text_len'] = len(text)
    
    if len(text) < 50:
        st.session_state.errors.append("⚠️ Il file PPT sembra vuoto o non contiene testo selezionabile.")
        return None

    try:
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        Sei Grimmy. Analizza questo testo ({len(text)} chars): "{text[:3000]}"...
        
        Output JSON valido con struttura:
        {{
            "slides": [ {{"layout": "Cover_Main", "title": "...", "body": "..."}} ],
            "cover_prompt_a": "Corporate team building photo...",
            "cover_prompt_b": "Creative abstract 3d render..."
        }}
        """
        resp = model.generate_content(prompt)
        cleaned = re.sub(r"```json|```", "", resp.text).strip()
        return json.loads(cleaned)
    except Exception as e:
        st.session_state.errors.append(f"❌ Errore Cervello ({model_name}): {str(e)}")
        return None

def generate_imagen_image(prompt, model_name):
    try:
        if not prompt: return None
        imagen_model = genai.ImageGenerationModel(model_name)
        response = imagen_model.generate_images(
            prompt=prompt, number_of_images=1, aspect_ratio="16:9",
            person_generation="allow_adult"
        )
        if response.images:
            img_byte_arr = BytesIO()
            response.images[0].save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
    except Exception as e:
        st.session_state.errors.append(f"❌ Errore NanoBanana ({model_name}): {str(e)}")
        return None

def create_final_pptx(plan, cover_image_bytes, template_path):
    prs = Presentation(template_path)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # Cover
    cover_layout = layout_map.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_layout)
    
    if plan and 'slides' in plan:
        cover_data = next((s for s in plan['slides'] if s['layout'] == 'Cover_Main'), None)
        if cover_data and slide.shapes.title: 
            slide.shapes.title.text = cover_data.get('title', 'Team Building')
    
    if cover_image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp.write(cover_image_bytes)
            tmp_path = tmp.name
        try:
            inserted = False
            for shape in slide.placeholders:
                if shape.placeholder_format.type == 18: 
                    shape.insert_picture(tmp_path)
                    inserted = True; break
            if not inserted: slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
        except: pass
        os.remove(tmp_path)
        
    return prs

# --- UI MAIN ---
st.title("🕵️ Grimmy Detective (X-Ray Vision)")

if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}
if "errors" not in st.session_state: st.session_state.errors = []
if "debug_info" not in st.session_state: st.session_state.debug_info = {}

if st.session_state.step == 1:
    source = st.file_uploader("Carica Vecchio PPT", type=["pptx"])
    
    if st.button("Analizza Ora") and template and source:
        st.session_state.errors = [] 
        
        with st.spinner("Grimmy sta usando i Raggi X..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                t.write(template.getvalue()); st.session_state.data['tpl_path'] = t.name
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                s.write(source.getvalue()); st.session_state.data['src_path'] = s.name
            
            txt, orig = extract_content(st.session_state.data['src_path'])
            st.session_state.data['orig_img'] = orig
            
            plan = get_gemini_plan_and_prompts(txt, selected_text_model)
            st.session_state.data['plan'] = plan
            
            if plan:
                st.session_state.data['img_a'] = generate_imagen_image(plan.get('cover_prompt_a'), selected_image_model)
                st.session_state.data['img_b'] = generate_imagen_image(plan.get('cover_prompt_b'), selected_image_model)
            
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    if st.session_state.errors:
        st.error("Errori rilevati:")
        for err in st.session_state.errors:
            st.write(err)
        st.divider()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("Originale (Trovata con Raggi X?)")
        if st.session_state.data.get('orig_img'): st.image(st.session_state.data['orig_img'])
        else: st.info("Ancora niente. L'immagine è un Vettore o un Gruppo?")

    with col2:
        st.write("Corporate")
        if st.session_state.data.get('img_a'): st.image(st.session_state.data['img_a'])
        else: st.warning("Errore")

    with col3:
        st.write("Creativo")
        if st.session_state.data.get('img_b'): st.image(st.session_state.data['img_b'])
        else: st.warning("Errore")

    if st.button("Ricomincia"):
        st.session_state.step = 1
        st.rerun()
