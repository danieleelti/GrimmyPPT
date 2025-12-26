import streamlit as st
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE_TYPE
import tempfile
import json
import os
import time
from io import BytesIO

# --- 1. CONFIGURAZIONE COSTANTI ---
# FORZATURA TOTALE SU GEMINI 3 COME RICHIESTO
MODEL_TEXT_NAME = "gemini-3-pro-preview" 
MODEL_IMAGE_NAME = "imagen-3.0-generate"

st.set_page_config(page_title="Grimmy G3", layout="wide", page_icon="🍌")

# --- 2. AUTENTICAZIONE ---
if "APP_PASSWORD" not in st.secrets:
    st.error("⚠️ Manca la password nei secrets!")
    st.stop()

if "auth" not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    pwd = st.text_input("Inserisci Password", type="password")
    if st.button("Accedi"):
        if pwd == st.secrets["APP_PASSWORD"]:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Password errata")
    st.stop()

# --- 3. SETUP API ---
api_key = st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    st.error("⚠️ Manca GOOGLE_API_KEY nei secrets!")
    st.stop()

try:
    genai.configure(api_key=api_key)
except Exception as e:
    st.error(f"Errore configurazione API: {e}")
    st.stop()

# --- 4. FUNZIONI DI LAVORO ---

def extract_text_and_logo(ppt_file):
    """Legge il testo e cerca un'immagine logo nella prima slide."""
    prs = Presentation(ppt_file)
    text_content = []
    logo_blob = None

    # Estrazione Testo
    for slide in prs.slides:
        slide_text = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_text.append(shape.text.strip())
        if slide_text:
            text_content.append(" | ".join(slide_text))
            
    # Estrazione Logo (Forensic Light)
    try:
        if len(prs.slides) > 0:
            # Cerca nella slide 1
            for shape in prs.slides[0].shapes:
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    logo_blob = shape.image.blob; break
                # Cerca nei gruppi
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for s in shape.shapes:
                        if s.shape_type == MSO_SHAPE_TYPE.PICTURE:
                            logo_blob = s.image.blob; break
                    if logo_blob: break
    except: pass 

    return "\n".join(text_content), logo_blob

def get_ai_plan(text_input):
    """Chiede a Gemini 3 la struttura e i prompt."""
    model = genai.GenerativeModel(MODEL_TEXT_NAME)
    
    prompt = f"""
    Sei un Creative Director esperto in eventi.
    ANALIZZA questo contenuto grezzo di un format di team building:
    "{text_input[:7000]}"
    
    OBIETTIVO: Creare la struttura per una presentazione commerciale e ideare la copertina.
    
    OUTPUT RICHIESTO (Solo JSON valido):
    {{
        "slides": [
            {{"layout": "Cover_Main", "title": "Titolo Accattivante", "body": "Sottotitolo"}},
            {{"layout": "Intro_Concept", "title": "Il Concept", "body": "Una frase emozionale breve."}},
            {{"layout": "Activity_Detail", "title": "Come Funziona", "body": "Elenco puntato passaggi chiave."}},
            {{"layout": "Technical_Grid", "title": "Scheda Tecnica", "body": "Durata, pax, location."}}
        ],
        "prompt_corporate": "Descrizione dettagliata in INGLESE per una foto realistica, stile corporate, alta risoluzione...",
        "prompt_creative": "Descrizione dettagliata in INGLESE per un'immagine astratta/artistica 3D, metaforica..."
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        # Pulizia JSON brutale
        txt = response.text
        start = txt.find('{')
        end = txt.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(txt[start:end])
        else:
            st.error(f"Gemini 3 ha risposto ma il JSON non è valido. Risposta parziale: {txt[:100]}...")
            return None
    except Exception as e:
        st.error(f"Errore Gemini 3 ({MODEL_TEXT_NAME}): {e}")
        return None

def generate_image(prompt):
    """Chiama Imagen 3."""
    try:
        if not hasattr(genai, "ImageGenerationModel"):
            st.error("ERRORE: Libreria google-generativeai vecchia. Aggiorna requirements.txt!")
            return None
            
        model = genai.ImageGenerationModel(MODEL_IMAGE_NAME)
        result = model.generate_images(
            prompt=prompt + ", 4k, hyper-realistic, corporate event photography, no text",
            number_of_images=1,
            aspect_ratio="16:9",
            person_generation="allow_adult"
        )
        if result.images:
            buf = BytesIO()
            result.images[0].save(buf, format="PNG")
            return buf.getvalue()
    except Exception as e:
        st.error(f"Errore NanoBanana ({MODEL_IMAGE_NAME}): {e}")
        return None

def build_pptx(plan, cover_img_bytes, template_file):
    """Assembla il PPT finale."""
    prs = Presentation(template_file)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    layouts = {l.name: l for l in prs.slide_master_layouts}
    
    # 1. Slide Cover
    cover_layout = layouts.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_layout)
    
    cover_data = next((s for s in plan['slides'] if s['layout']=='Cover_Main'), {})
    if slide.shapes.title: 
        slide.shapes.title.text = cover_data.get('title', 'Titolo')
    
    # Immagine Cover (Sfondo)
    if cover_img_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp.write(cover_img_bytes)
            tmp_path = tmp.name
        try:
            slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
        except: pass
        os.remove(tmp_path)
        
    # 2. Altre Slide
    for s_data in plan['slides']:
        if s_data['layout'] == 'Cover_Main': continue
        
        l_name = s_data.get('layout', 'Intro_Concept')
        if l_name not in layouts: l_name = list(layouts.keys())[0] # Fallback
        
        slide = prs.slides.add_slide(layouts[l_name])
        
        if slide.shapes.title: 
            slide.shapes.title.text = s_data.get('title', '')
            
        for ph in slide.placeholders:
            if ph.placeholder_format.idx == 1: 
                ph.text = s_data.get('body', '')
                
    return prs

# --- 5. INTERFACCIA UTENTE ---

st.title(f"🍌 Grimmy (Powered by {MODEL_TEXT_NAME})")

if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}

# STEP 1
if st.session_state.step == 1:
    st.header("1. Carica File")
    col1, col2 = st.columns(2)
    with col1: tpl = st.file_uploader("Template (.pptx)", type=["pptx"], key="tpl")
    with col2: src = st.file_uploader("Vecchio PPT (.pptx)", type=["pptx"], key="src")
        
    if st.button("Analizza con Gemini 3", type="primary"):
        if tpl and src:
            with st.spinner("Analisi in corso..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                    t.write(tpl.getvalue()); st.session_state.data['tpl_path'] = t.name
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                    s.write(src.getvalue()); st.session_state.data['src_path'] = s.name
                
                txt, logo = extract_text_and_logo(st.session_state.data['src_path'])
                st.session_state.data['logo'] = logo
                
                plan = get_ai_plan(txt)
                if plan:
                    st.session_state.data['plan'] = plan
                    st.session_state.step = 2
                    st.rerun()

# STEP 2
elif st.session_state.step == 2:
    st.header("2. Direzione Creativa")
    plan = st.session_state.data['plan']
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Corporate Prompt")
        p_corp = st.text_area("P1", plan.get("prompt_corporate", ""), height=150)
    with c2:
        st.subheader("Creative Prompt")
        p_creat = st.text_area("P2", plan.get("prompt_creative", ""), height=150)
        
    if st.button("🎨 Genera Immagini", type="primary"):
        with st.spinner("NanoBanana sta lavorando..."):
            st.session_state.data['img_corp'] = generate_image(p_corp)
            st.session_state.data['img_creat'] = generate_image(p_creat)
            st.session_state.step = 3
            st.rerun()

# STEP 3
elif st.session_state.step == 3:
    st.header("3. Risultato Finale")
    c1, c2, c3 = st.columns(3)
    choice = None
    
    with c1:
        st.markdown("**Logo**")
        if st.session_state.data.get('logo'):
            st.image(st.session_state.data['logo'])
            if st.button("Usa Logo"): choice = "logo"
    with c2:
        st.markdown("**Corporate**")
        if st.session_state.data.get('img_corp'):
            st.image(st.session_state.data['img_corp'])
            if st.button("Scegli Corporate"): choice = "corp"
    with c3:
        st.markdown("**Creativo**")
        if st.session_state.data.get('img_creat'):
            st.image(st.session_state.data['img_creat'])
            if st.button("Scegli Creativo"): choice = "creat"
            
    if choice:
        img = None
        if choice == "logo": img = st.session_state.data['logo']
        elif choice == "corp": img = st.session_state.data['img_corp']
        elif choice == "creat": img = st.session_state.data['img_creat']
        
        prs = build_pptx(st.session_state.data['plan'], img, st.session_state.data['tpl_path'])
        out_name = "Grimmy_G3_Presentation.pptx"
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
            prs.save(tmp.name)
            with open(tmp.name, "rb") as f:
                st.download_button("📥 SCARICA", f, out_name, type="primary")
                
    if st.button("Ricomincia"): st.session_state.step = 1; st.rerun()
