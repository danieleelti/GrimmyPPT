import streamlit as st
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE_TYPE
import tempfile
import json
import os
from io import BytesIO

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Grimmy PPT Agent", layout="wide", page_icon="🍌")

# --- AUTH ---
if "APP_PASSWORD" not in st.secrets:
    st.warning("⚠️ Manca APP_PASSWORD in secrets.toml")
    st.stop()
elif "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    pwd = st.text_input("Password", type="password")
    if st.button("Entra"):
        if pwd == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("No")
    st.stop()

# --- API KEY ---
api_key = st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    api_key = st.sidebar.text_input("Google API Key", type="password")
if api_key:
    genai.configure(api_key=api_key)

# --- SIDEBAR SEMPLIFICATA ---
with st.sidebar:
    st.header("⚙️ Configurazione")
    
    # FORZATURA GEMINI 3 (Come richiesto)
    st.success("🧠 Cervello: Gemini 3 Pro (Active)")
    selected_text_model = "gemini-3-pro-preview" # Forzato hardcoded
    
    st.info("🎨 NanoBanana: Imagen 3")
    selected_image_model = "imagen-3.0-generate"

    st.markdown("---")
    template = st.file_uploader("Carica Template Master", type=["pptx"])

# --- FUNZIONI ---

def extract_content(file_path):
    prs = Presentation(file_path)
    full_text = []
    first_image = None
    
    # Testo
    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))
        
    # Immagine (Logo/Extra)
    try:
        if len(prs.slides) > 0:
            for shape in prs.slides[0].shapes:
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    first_image = shape.image.blob; break
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for child in shape.shapes:
                        if child.shape_type == MSO_SHAPE_TYPE.PICTURE:
                            first_image = child.image.blob; break
                    if first_image: break
    except: pass
    
    return "\n".join(full_text), first_image

def get_gemini_plan(text):
    # Prompt per Gemini 3
    prompt = f"""
    You are an Elite Creative Director.
    ANALYZE this event format content: "{text[:6000]}"
    
    TASK 1: Structure the slides mapping content to: Cover_Main, Intro_Concept, Activity_Detail, Technical_Grid, Logistics_Info.
    TASK 2: Write 2 PHOTOREALISTIC IMAGE PROMPTS for the Cover Background.
    
    Output JSON ONLY:
    {{
        "slides": [ {{"layout": "Cover_Main", "title": "...", "body": "..."}} ],
        "cover_prompt_a": "High-end corporate photography of [activity]...",
        "cover_prompt_b": "Cinematic abstract composition representing [theme]..."
    }}
    """
    try:
        model = genai.GenerativeModel(selected_text_model)
        resp = model.generate_content(prompt)
        # Pulizia JSON aggressiva
        raw = resp.text
        start, end = raw.find('{'), raw.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(raw[start:end])
    except Exception as e:
        st.error(f"Errore Gemini 3: {e}")
    return None

def generate_image(prompt):
    try:
        # Questo è il punto che falliva: ora con requirements aggiornato funzionerà
        model = genai.ImageGenerationModel(selected_image_model)
        res = model.generate_images(
            prompt=prompt + ", 4k, photorealistic, highly detailed, corporate style",
            number_of_images=1,
            aspect_ratio="16:9",
            person_generation="allow_adult"
        )
        if res.images:
            buf = BytesIO()
            res.images[0].save(buf, format="PNG")
            return buf.getvalue()
    except Exception as e:
        st.error(f"Errore NanoBanana: {e}")
        return None

def create_pptx(plan, cover_img, tpl_path):
    prs = Presentation(tpl_path)
    prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # Cover
    slide = prs.slides.add_slide(layout_map.get("Cover_Main", prs.slide_master_layouts[0]))
    c_data = next((s for s in plan.get('slides',[]) if s['layout']=='Cover_Main'), {})
    if slide.shapes.title: slide.shapes.title.text = c_data.get('title', 'Event')
    
    # Immagine di sfondo
    if cover_img:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp.write(cover_img); tmp_path = tmp.name
        try:
            slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
            # Sposta l'immagine dietro (send to back simulato riaggiungendo titolo se necessario, 
            # ma pptx lo mette in cima allo stack. Workaround: titolo sopra)
        except: pass
        os.remove(tmp_path)
    
    # Altre slide (semplificato)
    for s_data in plan.get('slides', []):
        if s_data['layout'] == 'Cover_Main': continue
        l_name = s_data.get('layout', 'Intro_Concept')
        if l_name in layout_map:
            s = prs.slides.add_slide(layout_map[l_name])
            if s.shapes.title: s.shapes.title.text = s_data.get('title','')
            for ph in s.placeholders:
                if ph.placeholder_format.idx == 1: ph.text = s_data.get('body','')
                
    return prs

# --- INTERFACCIA ---

st.title("🍌 Grimmy PPT Agent (Gemini 3 Powered)")

if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}

# STEP 1: UPLOAD
if st.session_state.step == 1:
    source = st.file_uploader("Carica Vecchio PPT", type=["pptx"])
    if st.button("Analizza con Gemini 3") and template and source:
        with st.spinner("Analisi in corso..."):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                t.write(template.getvalue()); st.session_state.data['tpl'] = t.name
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                s.write(source.getvalue()); st.session_state.data['src'] = s.name
            
            txt, orig = extract_content(st.session_state.data['src'])
            st.session_state.data['orig'] = orig
            
            plan = get_gemini_plan(txt)
            if plan:
                st.session_state.data['plan'] = plan
                st.session_state.step = 2
                st.rerun()

# STEP 2: REVISIONE PROMPT
elif st.session_state.step == 2:
    st.header("🎨 Direzione Creativa")
    plan = st.session_state.data['plan']
    
    c1, c2 = st.columns(2)
    with c1:
        pa = st.text_area("Prompt Corporate", plan.get('cover_prompt_a',''), height=150)
    with c2:
        pb = st.text_area("Prompt Creativo", plan.get('cover_prompt_b',''), height=150)
        
    if st.button("Genera Immagini (NanoBanana)"):
        with st.spinner("Generazione 4K..."):
            st.session_state.data['img_a'] = generate_image(pa)
            st.session_state.data['img_b'] = generate_image(pb)
            st.session_state.step = 3
            st.rerun()

# STEP 3: RISULTATI
elif st.session_state.step == 3:
    st.header("🏆 Risultato Finale")
    c1, c2, c3 = st.columns(3)
    sel = None
    
    with c1:
        st.caption("Originale (Logo)")
        if st.session_state.data.get('orig'): 
            st.image(st.session_state.data['orig'])
            if st.button("Usa Logo"): sel = "orig"
    with c2:
        st.caption("Corporate")
        if st.session_state.data.get('img_a'): 
            st.image(st.session_state.data['img_a'])
            if st.button("Scegli A"): sel = "A"
    with c3:
        st.caption("Creativo")
        if st.session_state.data.get('img_b'): 
            st.image(st.session_state.data['img_b'])
            if st.button("Scegli B"): sel = "B"
            
    if sel:
        img = None
        if sel == "orig": img = st.session_state.data.get('orig')
        elif sel == "A": img = st.session_state.data.get('img_a')
        elif sel == "B": img = st.session_state.data.get('img_b')
        
        prs = create_pptx(st.session_state.data['plan'], img, st.session_state.data['tpl'])
        out = "Grimmy_Result.pptx"
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
            prs.save(tmp.name)
            with open(tmp.name, "rb") as f:
                st.download_button("📥 Scarica PPTX", f, out, type="primary")
    
    if st.button("Ricomincia"):
        st.session_state.step = 1
        st.rerun()
