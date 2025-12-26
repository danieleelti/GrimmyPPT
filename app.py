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
st.set_page_config(page_title="Grimmy PPT Agent", layout="wide", page_icon="🍌")

# --- AUTHENTICATION ---
if "APP_PASSWORD" not in st.secrets:
    st.warning("⚠️ Manca APP_PASSWORD in secrets.toml")
else:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🍌 Grimmy Access")
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
    st.subheader("🧠 Cervello (Testi & Prompt)")
    # Forziamo Gemini 1.5 Pro (più stabile col JSON) o Gemini 3 se disponibile
    text_models = ["gemini-1.5-pro-latest", "gemini-3-pro-preview", "gemini-1.5-flash"]
    selected_text_model = st.selectbox("Modello Testo", text_models, index=0)

    st.subheader("🎨 NanoBanana (Immagini)")
    # Nota: Assicurati di aver aggiornato la libreria google-generativeai!
    img_models = ["imagen-3.0-generate", "imagen-3.0-generate-001", "imagen-2.0-generate-001"]
    selected_image_model = st.selectbox("Modello Immagini", img_models, index=0)

    st.markdown("---")
    st.subheader("📂 Template")
    template = st.file_uploader("Carica Template (.pptx)", type=["pptx"])
    if template: st.success("Template OK")

# --- FUNZIONI CORE ---

def extract_content(file_path):
    """Estrae testo e cerca blob immagine (logo)"""
    prs = Presentation(file_path)
    full_text = []
    first_image = None 
    
    # Text
    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))

    # Image (Forensic Light)
    try:
        if len(prs.slides) > 0:
            slide = prs.slides[0]
            for shape in slide.shapes:
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    first_image = shape.image.blob; break
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP: # Try inside group
                    for child in shape.shapes:
                        if child.shape_type == MSO_SHAPE_TYPE.PICTURE:
                             first_image = child.image.blob; break
                    if first_image: break
    except: pass
                    
    return "\n".join(full_text), first_image

def get_gemini_plan_and_prompts(text, model_name):
    # SAFETY: Disabilitiamo i filtri per evitare blocchi su parole corporate
    safety = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]
    
    try:
        model = genai.GenerativeModel(model_name, safety_settings=safety)
        
        prompt = f"""
        You are a Senior Art Director for High-End Corporate Events.
        
        TASK 1: ANALYZE the content provided below.
        TASK 2: STRUCTURE the presentation content for the slides.
        TASK 3: WRITE 2 HIGH-FIDELITY IMAGE PROMPTS for the Cover slide background.
        
        CONTENT TO ANALYZE:
        "{text[:5000]}"
        
        GUIDELINES FOR IMAGE PROMPTS (NanoBanana):
        - They must be in ENGLISH.
        - They must be extremely detailed, describing lighting (e.g., "cinematic lighting", "golden hour"), camera angle (e.g., "wide angle", "macro"), style (e.g., "photorealistic 8k", "editorial photography").
        - PROMPT A (Corporate): Professional, dynamic, showing real people interacting, bright, clean.
        - PROMPT B (Creative/Abstract): Metaphorical, texture-focused, artistic, deep colors, 3D render style.
        
        OUTPUT JSON FORMAT ONLY:
        {{
            "slides": [ 
                {{"layout": "Cover_Main", "title": "Main Title", "subtitle": "Subtitle"}},
                {{"layout": "Intro_Concept", "title": "The Concept", "body": "Short punchy slogan..."}},
                {{"layout": "Activity_Detail", "title": "Activity", "body": "Bullet points..."}}
            ],
            "cover_prompt_a": "...",
            "cover_prompt_b": "..."
        }}
        """
        
        response = model.generate_content(prompt)
        
        # JSON CLEANING (Robustezza estrema)
        txt_resp = response.text
        start = txt_resp.find('{')
        end = txt_resp.rfind('}') + 1
        if start != -1 and end != -1:
            json_str = txt_resp[start:end]
            return json.loads(json_str)
        else:
            st.error(f"Gemini non ha prodotto JSON valido:\n{txt_resp[:200]}...")
            return None
            
    except Exception as e:
        st.error(f"Errore Gemini ({model_name}): {e}")
        return None

def generate_imagen_image(prompt, model_name):
    try:
        # Check libreria
        if not hasattr(genai, "ImageGenerationModel"):
            st.error("ERRORE CRITICO: La tua libreria `google-generativeai` è vecchia. Aggiorna requirements.txt!")
            return None

        model = genai.ImageGenerationModel(model_name)
        response = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9",
            person_generation="allow_adult" 
        )
        if response.images:
            buf = BytesIO()
            response.images[0].save(buf, format='PNG')
            return buf.getvalue()
    except Exception as e:
        st.error(f"Errore NanoBanana: {e}")
        return None

def create_final_pptx(plan, cover_image_bytes, template_path):
    prs = Presentation(template_path)
    prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # 1. Cover
    cover_l = layout_map.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_l)
    
    # Dati Cover
    c_data = next((s for s in plan.get('slides', []) if s['layout'] == 'Cover_Main'), {})
    if slide.shapes.title: slide.shapes.title.text = c_data.get('title', 'Team Building')
    
    # Immagine Sfondo
    if cover_image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp.write(cover_image_bytes); tmp_path = tmp.name
        try:
            inserted = False
            for ph in slide.placeholders:
                if ph.placeholder_format.type == 18: 
                    ph.insert_picture(tmp_path); inserted = True; break
            if not inserted: slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
        except: pass
        os.remove(tmp_path)
    
    # 2. Altre Slide
    for s_data in plan.get('slides', []):
        if s_data['layout'] == 'Cover_Main': continue
        l_name = s_data.get('layout', 'Intro_Concept')
        if l_name not in layout_map: l_name = "Intro_Concept" # fallback
        if l_name in layout_map:
            s = prs.slides.add_slide(layout_map[l_name])
            if s.shapes.title: s.shapes.title.text = s_data.get('title', '')
            for ph in s.placeholders:
                if ph.placeholder_format.idx == 1: ph.text = s_data.get('body', '')

    return prs

# --- GESTIONE STATI ---
if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}

# --- INTERFACCIA ---

st.title("🍌 Grimmy: Human-in-the-Loop")

# STEP 1: UPLOAD & ANALISI (Solo Testo)
if st.session_state.step == 1:
    st.markdown("### 1️⃣ Carica e Analizza")
    source = st.file_uploader("Carica Vecchio PPT", type=["pptx"])
    
    if st.button("Analizza Contenuto") and template and source:
        with st.spinner("Grimmy sta leggendo e preparando i prompt..."):
            # Salvataggio
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                t.write(template.getvalue()); st.session_state.data['tpl_path'] = t.name
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                s.write(source.getvalue()); st.session_state.data['src_path'] = s.name
            
            # Estrazione
            txt, orig = extract_content(st.session_state.data['src_path'])
            st.session_state.data['orig_img'] = orig
            
            # Gemini: Genera Piano e Prompt (ma NON immagini ancora)
            plan = get_gemini_plan_and_prompts(txt, selected_text_model)
            
            if plan:
                st.session_state.data['plan'] = plan
                # Passiamo allo step di revisione
                st.session_state.step = 2
                st.rerun()

# STEP 2: REVISIONE PROMPT (Il momento del Direttore Creativo)
elif st.session_state.step == 2:
    st.markdown("### 2️⃣ Direzione Creativa")
    st.info("Ecco i prompt che Gemini ha scritto. Modificali come preferisci prima di generare.")
    
    plan = st.session_state.data['plan']
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Opzione A: Corporate")
        prompt_a = st.text_area("Prompt A", value=plan.get('cover_prompt_a', ''), height=200)
    
    with col2:
        st.subheader("Opzione B: Creativa")
        prompt_b = st.text_area("Prompt B", value=plan.get('cover_prompt_b', ''), height=200)
        
    st.markdown("---")
    
    if st.button("🎨 Conferma e Genera NanoBanana"):
        # Salviamo i prompt modificati
        st.session_state.data['prompt_a_final'] = prompt_a
        st.session_state.data['prompt_b_final'] = prompt_b
        
        with st.spinner("NanoBanana sta dipingendo in 4K... (Richiede ~10-20 sec)"):
            img_a = generate_imagen_image(prompt_a, selected_image_model)
            img_b = generate_imagen_image(prompt_b, selected_image_model)
            
            st.session_state.data['img_a'] = img_a
            st.session_state.data['img_b'] = img_b
            
            st.session_state.step = 3
            st.rerun()

# STEP 3: SCELTA E DOWNLOAD
elif st.session_state.step == 3:
    st.markdown("### 3️⃣ Scegli e Scarica")
    
    c1, c2, c3 = st.columns(3)
    selection = None
    
    with c1:
        st.caption("Originale (Logo/Extra)")
        if st.session_state.data.get('orig_img'):
            st.image(st.session_state.data['orig_img'])
            if st.button("Usa Originale"): selection = "orig"
        else: st.info("Nessuna immagine trovata")
        
    with c2:
        st.caption("NanoBanana A")
        if st.session_state.data.get('img_a'):
            st.image(st.session_state.data['img_a'])
            if st.button("Scegli A"): selection = "A"
        else: st.warning("Errore Generazione A")

    with c3:
        st.caption("NanoBanana B")
        if st.session_state.data.get('img_b'):
            st.image(st.session_state.data['img_b'])
            if st.button("Scegli B"): selection = "B"
        else: st.warning("Errore Generazione B")

    if selection:
        final_img = None
        if selection == "orig": final_img = st.session_state.data.get('orig_img')
        elif selection == "A": final_img = st.session_state.data.get('img_a')
        elif selection == "B": final_img = st.session_state.data.get('img_b')
        
        with st.spinner("Creazione PPT..."):
            new_prs = create_final_pptx(st.session_state.data['plan'], final_img, st.session_state.data['tpl_path'])
            out = "Grimmy_Final.pptx"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp:
                new_prs.save(tmp.name)
                with open(tmp.name, "rb") as f:
                    st.success("Fatto!")
                    st.download_button("📥 Scarica PPTX", f, out, type="primary")

    if st.button("Ricomincia da capo"):
        st.session_state.step = 1
        st.rerun()
