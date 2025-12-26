import streamlit as st
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE_TYPE
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
                else: st.error("No.")
        st.stop()

# --- SETUP API KEY ---
api_key = st.secrets.get("GOOGLE_API_KEY")

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Configurazione")
    if not api_key:
        api_key = st.text_input("Google API Key", type="password")
    if api_key: genai.configure(api_key=api_key)

    st.markdown("---")
    st.subheader("🧠 Cervello")
    # Tenta di forzare il modello richiesto
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

# --- FUNZIONI CORE (BULLETPROOF) ---

def try_get_image_from_shape(shape):
    try:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            return shape.image.blob
        if hasattr(shape, 'fill') and shape.fill.type == 6: # Picture fill
             pass # Background fills are extremely hard to extract in python-pptx
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for child in shape.shapes:
                blob = try_get_image_from_shape(child)
                if blob: return blob
        if shape.is_placeholder and shape.placeholder_format.type == 18:
            if hasattr(shape, "image"): return shape.image.blob
    except: pass
    return None

def extract_content(file_path):
    prs = Presentation(file_path)
    full_text = []
    first_image = None 
    
    # Text Extraction
    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))

    # Image Forensic Scan
    if len(prs.slides) > 0:
        slide = prs.slides[0]
        targets = [slide.shapes, slide.slide_layout.shapes, slide.slide_layout.slide_master.shapes]
        for collection in targets:
            if first_image: break
            for shape in collection:
                blob = try_get_image_from_shape(shape)
                if blob: 
                    first_image = blob
                    break
                    
    return "\n".join(full_text), first_image

def get_gemini_plan_and_prompts(text, model_name):
    # 1. Controllo testo vuoto
    if len(text) < 10:
        st.session_state.errors.append("⚠️ Il file PPT non contiene testo leggibile.")
        return None

    try:
        # 2. Configurazione Safety (DISABILITA FILTRI)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        model = genai.GenerativeModel(model_name, safety_settings=safety_settings)
        
        prompt = f"""
        Sei Grimmy. Analizza questo testo corporate ({len(text)} chars): 
        "{text[:4000]}"
        
        Output JSON valido:
        {{
            "slides": [ {{"layout": "Cover_Main", "title": "TITOLO", "body": "..."}} ],
            "cover_prompt_a": "Photo of corporate team building, cooking class, high quality...",
            "cover_prompt_b": "Abstract illustration of teamwork, cooking ingredients, 3d render..."
        }}
        """
        
        resp = model.generate_content(prompt)
        
        # 3. Estrazione JSON Robusta
        raw_text = resp.text
        # Cerca la prima { e l'ultima }
        start = raw_text.find('{')
        end = raw_text.rfind('}') + 1
        
        if start != -1 and end != -1:
            json_str = raw_text[start:end]
            return json.loads(json_str)
        else:
            st.session_state.errors.append(f"❌ Gemini ha risposto ma senza JSON: {raw_text[:100]}...")
            return None

    except Exception as e:
        st.session_state.errors.append(f"❌ Errore Gemini ({model_name}): {str(e)}")
        return None

def generate_imagen_image(prompt, model_name):
    try:
        if not prompt: return None
        model = genai.ImageGenerationModel(model_name)
        res = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio="16:9")
        if res.images:
            buf = BytesIO()
            res.images[0].save(buf, format='PNG')
            return buf.getvalue()
    except Exception as e:
        st.session_state.errors.append(f"❌ Errore NanoBanana: {e}")
        return None

def create_final_pptx(plan, cover_image_bytes, template_path):
    prs = Presentation(template_path)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # COVER
    cover_layout = layout_map.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_layout)
    
    if plan:
        c_data = next((s for s in plan.get('slides', []) if s['layout'] == 'Cover_Main'), None)
        if c_data and slide.shapes.title: slide.shapes.title.text = c_data.get('title', 'Team Building')

    if cover_image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp.write(cover_image_bytes); tmp_path = tmp.name
        try:
            inserted = False
            for shape in slide.placeholders:
                if shape.placeholder_format.type == 18: 
                    shape.insert_picture(tmp_path); inserted = True; break
            if not inserted: slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
        except: pass
        os.remove(tmp_path)

    # ALTRE SLIDE
    if plan:
        for s_data in plan.get('slides', []):
            if s_data['layout'] == 'Cover_Main': continue
            l_name = s_data.get('layout', 'Intro_Concept')
            if l_name not in layout_map: l_name = "Intro_Concept" # Fallback
            if l_name in layout_map:
                s = prs.slides.add_slide(layout_map[l_name])
                if s.shapes.title: s.shapes.title.text = s_data.get('title', '')
                for ph in s.placeholders:
                    if ph.placeholder_format.idx == 1: ph.text = s_data.get('body', '')

    return prs

# --- UI MAIN ---
st.title("🛡️ Grimmy PPT Agent (Bulletproof)")

if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}
if "errors" not in st.session_state: st.session_state.errors = []

if st.session_state.step == 1:
    source = st.file_uploader("Carica Vecchio PPT", type=["pptx"])
    if st.button("Analizza") and template and source:
        st.session_state.errors = []
        with st.spinner("Grimmy sta lavorando..."):
            # Files
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                t.write(template.getvalue()); st.session_state.data['tpl_path'] = t.name
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                s.write(source.getvalue()); st.session_state.data['src_path'] = s.name
            
            # 1. Extract
            txt, orig = extract_content(st.session_state.data['src_path'])
            st.session_state.data['orig_img'] = orig # Sarà probabilmente il logo
            
            # 2. Plan (Gemini)
            plan = get_gemini_plan_and_prompts(txt, selected_text_model)
            st.session_state.data['plan'] = plan
            
            # 3. Images (NanoBanana) - SOLO SE IL PIANO ESISTE
            if plan:
                st.session_state.data['img_a'] = generate_imagen_image(plan.get('cover_prompt_a'), selected_image_model)
                st.session_state.data['img_b'] = generate_imagen_image(plan.get('cover_prompt_b'), selected_image_model)
            else:
                st.error("Gemini non ha restituito un piano valido. Controlla gli errori sopra.")
            
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    if st.session_state.errors:
        st.error("Errori Tecnici Rilevati:")
        for e in st.session_state.errors: st.write(e)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### Originale")
        if st.session_state.data.get('orig_img'): 
            st.image(st.session_state.data['orig_img'], caption="Logo/Img Trovata")
        else: st.info("Sfondo non estraibile (Usa AI)")

    with col2:
        st.markdown("### Corporate")
        if st.session_state.data.get('img_a'): 
            st.image(st.session_state.data['img_a'])
            if st.button("Scegli Corporate"): selection = "A"
        else: st.warning("Non generata")

    with col3:
        st.markdown("### Creativo")
        if st.session_state.data.get('img_b'): 
            st.image(st.session_state.data['img_b'])
            if st.button("Scegli Creativo"): selection = "B"
        else: st.warning("Non generata")

    # Logica Selezione (semplificata per UI)
    if 'selection' in locals():
        final_img = None
        if selection == "A": final_img = st.session_state.data.get('img_a')
        elif selection == "B": final_img = st.session_state.data.get('img_b')
        
        new_prs = create_final_pptx(st.session_state.data['plan'], final_img, st.session_state.data['tpl_path'])
        out_name = "Grimmy_Presentation.pptx"
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
            new_prs.save(tmp.name)
            with open(tmp.name, "rb") as f:
                st.download_button("📥 SCARICA PPTX", f, out_name, type="primary")

    if st.button("Ricomincia"): st.session_state.step = 1; st.rerun()
