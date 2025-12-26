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

# --- FUNZIONI CORE AVANZATE (FORENSIC MODE) ---

def try_get_image_from_shape(shape):
    """Tenta di estrarre un blob immagine da una shape, in qualsiasi modo sia nascosta."""
    try:
        # CASO 1: È un'immagine classica
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            return shape.image.blob
        
        # CASO 2: È una forma con RIEMPIMENTO immagine (comune nei template)
        if hasattr(shape, 'fill'):
            # 6 = MSO_FILL.PICTURE (non importiamo l'enum per brevità, usiamo il valore int)
            if shape.fill.type == 6: 
                # A volte fallisce se l'immagine è corrotta
                try: return shape.fill.fore_color.type # check dummy
                except: pass
                # Non c'è un metodo diretto facile in python-pptx per estrarre il blob dal fill 
                # senza hacking profondi, ma spesso è identificato come Picture
                pass 

        # CASO 3: È un GRUPPO di forme
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for child in shape.shapes:
                blob = try_get_image_from_shape(child)
                if blob: return blob
                
        # CASO 4: Placeholder Immagine (Type 18)
        if shape.is_placeholder and shape.placeholder_format.type == 18:
            if hasattr(shape, "image"):
                return shape.image.blob

    except Exception:
        pass
    return None

def extract_content(file_path):
    """
    Scansiona Slide, Layout, Master e Sfondi per trovare l'immagine.
    """
    prs = Presentation(file_path)
    full_text = []
    first_image = None 
    
    # --- ESTRAZIONE TESTO ---
    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))

    # --- CACCIA ALL'IMMAGINE (Deep Scan) ---
    if len(prs.slides) > 0:
        slide = prs.slides[0]
        layout = slide.slide_layout
        master = layout.slide_master
        
        # ORDINE DI RICERCA:
        # 1. Forme nella Slide
        # 2. Forme nel Layout
        # 3. Forme nel Master
        # 4. Sfondi (Non supportati direttamente in lettura blob da python-pptx, ma proviamo)

        scan_targets = [slide.shapes, layout.shapes, master.shapes]
        
        for shapes in scan_targets:
            if first_image: break
            for shape in shapes:
                blob = try_get_image_from_shape(shape)
                if blob:
                    first_image = blob
                    break
        
        # Se ancora nulla, è probabile che sia un BACKGROUND FILL.
        # Python-pptx ha limiti nell'estrarre il BLOB di un background fill.
        # Se siamo qui e first_image è None, l'immagine è blindata nel background style.
        # Non possiamo estrarla facilmente senza corrompere il file.
        
    return "\n".join(full_text), first_image

def get_gemini_plan_and_prompts(text, model_name):
    if len(text) < 20:
        st.session_state.errors.append("⚠️ Testo insufficiente nel PPT.")
        return None

    try:
        model = genai.GenerativeModel(model_name)
        prompt = f"""
        Sei Grimmy. Analizza: "{text[:3000]}"...
        Output JSON:
        {{
            "slides": [ {{"layout": "Cover_Main", "title": "...", "body": "..."}} ],
            "cover_prompt_a": "Corporate photo...",
            "cover_prompt_b": "Creative 3d render..."
        }}
        """
        resp = model.generate_content(prompt)
        cleaned = re.sub(r"```json|```", "", resp.text).strip()
        return json.loads(cleaned)
    except Exception as e:
        st.session_state.errors.append(f"❌ Errore Gemini: {e}")
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
        st.session_state.errors.append(f"❌ Errore Imagen: {e}")
        return None

def create_final_pptx(plan, cover_image_bytes, template_path):
    prs = Presentation(template_path)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # COVER
    cover_layout = layout_map.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_layout)
    
    if plan and 'slides' in plan:
        c_data = next((s for s in plan['slides'] if s['layout'] == 'Cover_Main'), None)
        if c_data and slide.shapes.title: slide.shapes.title.text = c_data.get('title', '')
    
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

    # ALTRE SLIDE (Semplificato)
    if plan:
        for s_data in plan.get('slides', []):
            if s_data['layout'] == 'Cover_Main': continue
            l_name = s_data.get('layout', 'Intro_Concept')
            if l_name not in layout_map: l_name = list(layout_map.keys())[1]
            
            s = prs.slides.add_slide(layout_map[l_name])
            if s.shapes.title: s.shapes.title.text = s_data.get('title', '')
            for ph in s.placeholders:
                if ph.placeholder_format.idx == 1: ph.text = s_data.get('body', '')

    return prs

# --- MAIN UI ---
st.title("🕵️ Grimmy PPT Agent (Forensic Mode)")

if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}
if "errors" not in st.session_state: st.session_state.errors = []

if st.session_state.step == 1:
    source = st.file_uploader("Carica Vecchio PPT", type=["pptx"])
    if st.button("Analizza") and template and source:
        st.session_state.errors = []
        with st.spinner("Analisi profonda..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                t.write(template.getvalue()); st.session_state.data['tpl_path'] = t.name
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                s.write(source.getvalue()); st.session_state.data['src_path'] = s.name
            
            # ESTRAZIONE
            txt, orig = extract_content(st.session_state.data['src_path'])
            st.session_state.data['orig_img'] = orig
            
            if not orig:
                st.warning("⚠️ Ancora nessuna immagine. Probabilmente è un 'Background Fill' bloccato. Procedo comunque con la generazione AI.")
            
            # AI
            plan = get_gemini_plan_and_prompts(txt, selected_text_model)
            st.session_state.data['plan'] = plan
            
            if plan:
                st.session_state.data['img_a'] = generate_imagen_image(plan.get('cover_prompt_a'), selected_image_model)
                st.session_state.data['img_b'] = generate_imagen_image(plan.get('cover_prompt_b'), selected_image_model)
            
            st.session_state.step = 2
            st.rerun()

elif st.session_state.step == 2:
    if st.session_state.errors:
        st.error("Errori:"); 
        for e in st.session_state.errors: st.write(e)
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.write("Originale")
        if st.session_state.data.get('orig_img'): st.image(st.session_state.data['orig_img'])
        else: st.info("Non trovata (Usa AI)")
    with c2:
        st.write("Corporate")
        if st.session_state.data.get('img_a'): st.image(st.session_state.data['img_a'])
    with c3:
        st.write("Creativo")
        if st.session_state.data.get('img_b'): st.image(st.session_state.data['img_b'])

    if st.button("Reset"): st.session_state.step = 1; st.rerun()
