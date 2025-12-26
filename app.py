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

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configurazione")
    
    # SELEZIONE FORZATA GEMINI 3
    st.markdown("### 🧠 Cervello")
    # Qui definisco solo modelli di nuova generazione
    text_models = ["gemini-3-pro-preview", "gemini-2.0-flash-exp", "gemini-1.5-pro"]
    selected_text_model = st.selectbox("Modello Testo", text_models, index=0)
    
    st.markdown("### 🎨 NanoBanana")
    # Modelli Imagen
    img_models = ["imagen-3.0-generate", "imagen-3.0-generate-001"]
    selected_image_model = st.selectbox("Modello Immagini", img_models, index=0)

    st.markdown("---")
    template = st.file_uploader("Carica Template Master", type=["pptx"])

# --- FUNZIONI ---

def extract_content(file_path):
    prs = Presentation(file_path)
    full_text = []
    first_image = None
    
    # Estrazione Testo
    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))
        
    # Estrazione Immagine (Tentativo su Slide e Gruppi)
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

def get_gemini_plan(text, model_name):
    # Safety Settings: Nessun blocco
    safety = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    prompt = f"""
    You are an Elite Creative Director for Corporate Events.
    ANALYZE this event content: "{text[:6000]}"
    
    TASK 1: Structure the content for these layouts: Cover_Main, Intro_Concept, Activity_Detail, Technical_Grid, Logistics_Info.
    TASK 2: Write 2 HIGH-END IMAGE PROMPTS for the Cover Background (NanoBanana).
    
    GUIDELINES FOR PROMPTS:
    - Contextualized to the specific activity (e.g. if cooking -> kitchen, ingredients).
    - Style: 4K, Photorealistic, Professional, Depth of Field, Cinematic Lighting.
    - No text in the image.
    
    Output JSON ONLY:
    {{
        "slides": [ {{"layout": "Cover_Main", "title": "...", "body": "..."}} ],
        "cover_prompt_a": "Prompt describing a professional corporate scene...",
        "cover_prompt_b": "Prompt describing a creative/abstract metaphorical scene..."
    }}
    """
    try:
        model = genai.GenerativeModel(model_name, safety_settings=safety)
        resp = model.generate_content(prompt)
        
        # Pulizia JSON
        raw = resp.text
        start, end = raw.find('{'), raw.rfind('}') + 1
        if start != -1 and end != -1:
            return json.loads(raw[start:end])
        else:
            st.error(f"Errore formato JSON da Gemini: {raw[:100]}...")
            return None
    except Exception as e:
        st.error(f"Errore Chiamata Gemini ({model_name}): {e}")
        return None

def generate_image(prompt, model_name):
    try:
        # Controllo libreria
        if not hasattr(genai, "ImageGenerationModel"):
            st.error("⚠️ ERRORE LIBRERIA: `google-generativeai` è vecchia. Devi aggiornare requirements.txt e riavviare l'app!")
            return None

        model = genai.ImageGenerationModel(model_name)
        res = model.generate_images(
            prompt=prompt + ", 4k, photorealistic, highly detailed, corporate event style, no text",
            number_of_images=1,
            aspect_ratio="16:9",
            person_generation="allow_adult"
        )
        if res.images:
            buf = BytesIO()
            res.images[0].save(buf, format="PNG")
            return buf.getvalue()
    except Exception as e:
        st.error(f"Errore NanoBanana ({model_name}): {e}")
        return None

def create_pptx(plan, cover_img, tpl_path):
    prs = Presentation(tpl_path)
    prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # Cover
    slide = prs.slides.add_slide(layout_map.get("Cover_Main", prs.slide_master_layouts[0]))
    c_data = next((s for s in plan.get('slides',[]) if s['layout']=='Cover_Main'), {})
    if slide.shapes.title: slide.shapes.title.text = c_data.get('title', 'Event')
    
    # Immagine Sfondo
    if cover_img:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            tmp.write(cover_img); tmp_path = tmp.name
        try:
            # Inserisce immagine a tutto schermo
            pic = slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
            # Sposta l'immagine dietro (Hack: taglia e incolla gli altri elementi sopra? 
            # PPTX mette l'ultimo aggiunto sopra. 
            # Qui ci affidiamo al layout: se il placeholder è "sopra" nel master, il testo sarà sopra)
        except: pass
        os.remove(tmp_path)
    
    # Altre slide
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

st.title("🍌 Grimmy: Human-in-the-Loop")

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
            
            plan = get_gemini_plan(txt, selected_text_model)
            if plan:
                st.session_state.data['plan'] = plan
                st.session_state.step = 2
                st.rerun()

# STEP 2: REVISIONE PROMPT
elif st.session_state.step == 2:
    st.header("🎨 Direzione Creativa (Prompt Review)")
    st.info(f"Gemini 3 ha scritto questi prompt. Modificali se vuoi.")
    
    plan = st.session_state.data['plan']
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Prompt A (Corporate)")
        pa = st.text_area("Descrizione", plan.get('cover_prompt_a',''), height=150, key="pa")
    with c2:
        st.subheader("Prompt B (Creativo)")
        pb = st.text_area("Descrizione", plan.get('cover_prompt_b',''), height=150, key="pb")
        
    if st.button("🎨 Genera Immagini (NanoBanana)"):
        with st.spinner("Generazione 4K in corso..."):
            st.session_state.data['img_a'] = generate_image(pa, selected_image_model)
            st.session_state.data['img_b'] = generate_image(pb, selected_image_model)
            st.session_state.step = 3
            st.rerun()

# STEP 3: RISULTATI
elif st.session_state.step == 3:
    st.header("🏆 Risultato Finale")
    c1, c2, c3 = st.columns(3)
    sel = None
    
    with c1:
        st.caption("Originale")
        if st.session_state.data.get('orig'): 
            st.image(st.session_state.data['orig'])
            if st.button("Usa Logo/Originale"): sel = "orig"
        else: st.write("Nessuna immagine")
            
    with c2:
        st.caption("NanoBanana A")
        if st.session_state.data.get('img_a'): 
            st.image(st.session_state.data['img_a'])
            if st.button("Scegli A"): sel = "A"
        else: st.error("Errore Gen A")
            
    with c3:
        st.caption("NanoBanana B")
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
