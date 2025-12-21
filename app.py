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
            pwd = st.text_input("Password Workspace", type="password")
            if st.button("Entra"):
                if pwd == st.secrets["APP_PASSWORD"]:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Accesso Negato")
        st.stop()

# --- SETUP API GOOGLE (Unica Chiave per tutto) ---
api_key = st.secrets.get("GOOGLE_API_KEY")
if not api_key:
    with st.sidebar:
        api_key = st.text_input("Google API Key", type="password")
        if not api_key:
            st.stop()
genai.configure(api_key=api_key)

# --- FUNZIONI CORE ---

def extract_content(file_path):
    """Estrae testo e la prima immagine (cover originale) dal vecchio file."""
    prs = Presentation(file_path)
    full_text = []
    first_image = None 
    
    # Prende la prima immagine valida dalla slide 1 per confronto
    try:
        if len(prs.slides) > 0:
            for shape in prs.slides[0].shapes:
                if shape.shape_type == 13: # Picture
                    first_image = shape.image.blob
                    break
    except:
        pass

    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))
    
    return "\n".join(full_text), first_image

def get_gemini_plan_and_prompts(text):
    """
    Usa Gemini 1.5 Pro per ragionare sulla struttura e scrivere i prompt per Imagen.
    """
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
    
    prompt = f"""
    Sei un Creative Director esperto in Corporate Team Building.
    
    ANALIZZA questo contenuto grezzo:
    "{text[:3500]}"...
    
    OBIETTIVO 1: Ristruttura le slide per i layout: Cover_Main, Intro_Concept, Activity_Detail, Technical_Grid, Logistics_Info.
    
    OBIETTIVO 2: Scrivi 2 PROMPT per generare un'immagine di COPERTINA usando Google Imagen.
    I prompt devono essere in INGLESE, molto dettagliati.
    - Prompt A (Stile "Corporate Action"): Fotorealistico, persone sorridenti, collaborazione, luminoso, alta definizione, stile fotografia stock premium.
    - Prompt B (Stile "Conceptual Art"): Astratto, metaforico, oggetti che rappresentano il tema (es. ingredienti cucina, bussole, nodi), illuminazione cinematografica, 3d render style o macro photography.
    
    OUTPUT JSON:
    {{
        "slides": [ ...array con layout, title, body... ],
        "cover_prompt_a": "...",
        "cover_prompt_b": "..."
    }}
    Restituisci SOLO JSON valido senza markdown.
    """
    try:
        resp = model.generate_content(prompt)
        cleaned = re.sub(r"```json|```", "", resp.text).strip()
        return json.loads(cleaned)
    except Exception as e:
        st.error(f"Errore Gemini Planning: {e}")
        return None

def generate_imagen_image(prompt):
    """
    Genera immagini usando Google Imagen 3 tramite l'SDK genai.
    Nota: Richiede che la chiave API abbia accesso alla beta di Imagen o al modello 'imagen-3.0-generate-001'.
    """
    try:
        # Tenta di usare il modello Imagen 3. Se non disponibile, scala su versioni precedenti
        # Modello standard per generazione immagini in AI Studio
        imagen_model = genai.ImageGenerationModel("imagen-3.0-generate-001") 
        
        response = imagen_model.generate_images(
            prompt=prompt + ", high quality, 4k, photorealistic, no text",
            number_of_images=1,
            aspect_ratio="16:9", # Ottimo per slide PPT
            safety_filter_level="block_only_high",
            person_generation="allow_adult" # Necessario per foto di team building con persone
        )
        
        # Imagen restituisce un oggetto immagine, lo convertiamo in bytes
        if response.images:
            img = response.images[0]
            # Salva in buffer
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
        return None

    except Exception as e:
        st.warning(f"Errore Imagen: {e}. Controlla che la tua API Key supporti Imagen 3.")
        return None

def create_final_pptx(plan, cover_image_bytes, template_path):
    """Assembla il PPT finale con l'immagine scelta."""
    prs = Presentation(template_path)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # 1. Slide Cover
    cover_layout = layout_map.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_layout)
    
    # Dati Cover
    cover_data = next((s for s in plan['slides'] if s['layout'] == 'Cover_Main'), None)
    if cover_data:
        if slide.shapes.title: slide.shapes.title.text = cover_data.get('title', 'Team Building')
    
    # Inserimento Immagine Cover
    if cover_image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
            tmp_img.write(cover_image_bytes)
            tmp_path = tmp_img.name
        
        try:
            inserted = False
            # Cerca placeholder immagine
            for shape in slide.placeholders:
                if shape.placeholder_format.type == 18: # Picture
                    shape.insert_picture(tmp_path)
                    inserted = True
                    break
            if not inserted:
                # Fallback: Sfondo
                slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
        except:
            pass
        os.remove(tmp_path)

    # 2. Altre Slide Dinamiche
    for slide_data in plan['slides']:
        if slide_data['layout'] == 'Cover_Main': continue 
        
        l_name = slide_data.get("layout", "Intro_Concept")
        if l_name in layout_map:
            s = prs.slides.add_slide(layout_map[l_name])
            
            # Titolo
            if s.shapes.title: s.shapes.title.text = slide_data.get("title", "")
            
            # Body Text (Cerca placeholder idx 1)
            for shape in s.placeholders:
                if shape.placeholder_format.idx == 1:
                    shape.text = slide_data.get("body", "")

    # 3. Slide Fisse (Standard)
    fixed = ["Standard_Training", "Standard_Extras", "Standard_Payment", "Closing_Contact"]
    for f in fixed:
        if f in layout_map: prs.slides.add_slide(layout_map[f])

    return prs

# --- INTERFACCIA UTENTE ---

st.title("🍌 NanoBanana PPT Agent (Google Powered)")
st.caption("Powered by Gemini 1.5 Pro & Imagen 3")

# Stati sessione
if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}

# STEP 1: UPLOAD
if st.session_state.step == 1:
    col1, col2 = st.columns(2)
    with col1: template = st.file_uploader("Template (.pptx)", type=["pptx"])
    with col2: source = st.file_uploader("Vecchio PPT (.pptx)", type=["pptx"])
    
    if st.button("Analizza e Genera Cover") and template and source:
        with st.spinner("Gemini sta leggendo e Imagen sta disegnando..."):
            # Salva temporanei
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                t.write(template.getvalue())
                st.session_state.data['tpl_path'] = t.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                s.write(source.getvalue())
                st.session_state.data['src_path'] = s.name

            # Logica
            txt, orig_img = extract_content(st.session_state.data['src_path'])
            st.session_state.data['orig_img'] = orig_img
            
            plan = get_gemini_plan_and_prompts(txt)
            st.session_state.data['plan'] = plan
            
            if plan:
                # Generazione Parallela (concettualmente)
                st.info("Generazione Cover A (Corporate)...")
                img_a = generate_imagen_image(plan['cover_prompt_a'])
                
                st.info("Generazione Cover B (Conceptual)...")
                img_b = generate_imagen_image(plan['cover_prompt_b'])
                
                st.session_state.data['img_a'] = img_a
                st.session_state.data['img_b'] = img_b
            
            st.session_state.step = 2
            st.rerun()

# STEP 2: SCELTA E DOWNLOAD
elif st.session_state.step == 2:
    st.subheader("Scegli la Cover")
    
    col1, col2, col3 = st.columns(3)
    selection = None
    
    # Originale
    with col1:
        st.markdown("**Originale**")
        if st.session_state.data.get('orig_img'):
            st.image(st.session_state.data['orig_img'], use_container_width=True)
            if st.button("Usa Originale"): selection = "orig"
        else:
            st.info("Nessuna immagine trovata")

    # Imagen A
    with col2:
        st.markdown("**NanoBanana: Corporate**")
        if st.session_state.data.get('img_a'):
            st.image(st.session_state.data['img_a'], use_container_width=True)
            with st.expander("Vedi Prompt"):
                st.write(st.session_state.data['plan']['cover_prompt_a'])
            if st.button("Scegli Opzione A"): selection = "A"
        else:
            st.warning("Generazione fallita")

    # Imagen B
    with col3:
        st.markdown("**NanoBanana: Creative**")
        if st.session_state.data.get('img_b'):
            st.image(st.session_state.data['img_b'], use_container_width=True)
            with st.expander("Vedi Prompt"):
                st.write(st.session_state.data['plan']['cover_prompt_b'])
            if st.button("Scegli Opzione B"): selection = "B"

    # Creazione Finale
    if selection:
        final_img = None
        if selection == "orig": final_img = st.session_state.data.get('orig_img')
        elif selection == "A": final_img = st.session_state.data.get('img_a')
        elif selection == "B": final_img = st.session_state.data.get('img_b')
        
        with st.spinner("Impaginazione finale..."):
            new_prs = create_final_pptx(
                st.session_state.data['plan'], 
                final_img, 
                st.session_state.data['tpl_path']
            )
            
            output_name = "PRESENTAZIONE_AI_GOOGLE.pptx"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_out:
                new_prs.save(tmp_out.name)
                with open(tmp_out.name, "rb") as f:
                    st.download_button(
                        "📥 SCARICA PPTX COMPLETO", 
                        f, 
                        output_name,
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    )
        
        if st.button("Ricomincia da capo"):
            st.session_state.step = 1
            st.rerun()
