import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import os
import json
import importlib

# ==========================================
# 🛠️ AUTO-CREAZIONE FILE (NELLA STESSA CARTELLA)
# ==========================================
# Questo blocco crea fisicamente i file .py necessari se non esistono.

def create_helper_files():
    
    # --- FILE 1: page1_cover.py ---
    if not os.path.exists("page1_cover.py"):
        code_cover = '''
import google.generativeai as genai
import json

def process_slide(slide, full_context):
    """
    GESTIONE COVER (Slide 0)
    Obiettivo: Inserire Nome Format (intoccabile) e Claim (creativo).
    """
    # Se "gemini-3.0-pro" non è ancora attivo, usa "gemini-1.5-pro"
    model = genai.GenerativeModel("gemini-1.5-pro") 
    
    prompt = f"""
    Sei un esperto di Marketing e Team Building.
    Analizza il testo sorgente per compilare la COPERTINA della presentazione.
    
    OUTPUT RICHIESTO (JSON):
    1. "format_name": Trova il nome del format nel testo. DEVE ESSERE ESATTO. Non cambiarlo.
    2. "claim": Crea uno slogan commerciale, breve (max 6 parole), energico.
    3. "imagen_prompt": Descrizione per Imagen 3 di una copertina epica, fotorealistica.

    TESTO SORGENTE:
    {full_context}
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        
        # 1. Titolo (Format Name)
        if slide.shapes.title:
            slide.shapes.title.text = data.get("format_name", "NOME FORMAT")
            
        # 2. Sottotitolo (Claim)
        # Cerca il primo box di testo che non sia il titolo
        for shape in slide.placeholders:
            if shape.has_text_frame and shape != slide.shapes.title:
                shape.text = data.get("claim", "")
                break
                
        # 3. Prompt Immagine (Nelle note)
        if not slide.has_notes_slide:
            slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        slide.notes_slide.notes_text_frame.text = f"IMAGEN PROMPT:\\n{data.get('imagen_prompt')}"
        
        return True
    except Exception as e:
        print(f"Errore Cover: {e}")
        return False
'''
        with open("page1_cover.py", "w") as f:
            f.write(code_cover)

    # --- FILE 2: page2_generic.py ---
    if not os.path.exists("page2_generic.py"):
        code_generic = '''
import google.generativeai as genai
import json

def process_slide(slide, full_context, section_name):
    """
    GESTIONE PAGINE INTERNE
    Obiettivo: Titolo (Format), Box Piccolo (Categoria), Box Grande (Corpo).
    """
    model = genai.GenerativeModel("gemini-1.5-pro")
    
    prompt = f"""
    Sei un esperto di Team Building.
    Stiamo scrivendo la pagina dedicata a: {section_name.upper()}.
    
    OUTPUT RICHIESTO (JSON):
    1. "title": Il nome del Format (usalo sempre come titolo).
    2. "category": Scrivi esattamente "{section_name}".
    3. "body": Estrai dal testo le info su "{section_name}" e riscrivile in modo professionale.
    4. "imagen_prompt": Prompt per immagine di supporto (stile corporate/action).

    TESTO SORGENTE:
    {full_context}
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        
        # 1. Titolo
        if slide.shapes.title:
            slide.shapes.title.text = data.get("title", "")
            
        # 2. Gestione Box Testo (Categoria vs Corpo)
        # Troviamo i placeholder di testo (escluso titolo)
        text_shapes = [s for s in slide.placeholders if s.has_text_frame and s != slide.shapes.title]
        
        # Li ordiniamo dall'alto verso il basso (Top position)
        text_shapes.sort(key=lambda s: s.top)
        
        if len(text_shapes) >= 2:
            text_shapes[0].text = data.get("category", section_name) # Box in alto (piccolo)
            text_shapes[1].text = data.get("body", "")              # Box sotto (grande)
        elif len(text_shapes) == 1:
            text_shapes[0].text = f"{section_name}\\n\\n{data.get('body', '')}"

        # 3. Prompt Immagine (Nelle note)
        if not slide.has_notes_slide:
            slide.notes_slide = slide.part.presentation.slides._library.add_notes_slide(slide.part, slide.part.slide_layout)
        slide.notes_slide.notes_text_frame.text = f"IMAGEN PROMPT:\\n{data.get('imagen_prompt')}"
        
        return True
    except Exception as e:
        print(f"Errore {section_name}: {e}")
        return False
'''
        with open("page2_generic.py", "w") as f:
            f.write(code_generic)

# Eseguiamo la creazione dei file PRIMA di importare
create_helper_files()

# --- IMPORT DINAMICO (Ora i file esistono nella root) ---
import page1_cover
import page2_generic

# ==========================================
# 🚀 APP PRINCIPALE
# ==========================================

# Configurazione Base
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# Login
if 'auth' not in st.session_state: st.session_state['auth'] = False
if not st.session_state['auth']:
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]: 
            st.session_state['auth'] = True
            st.rerun()
    st.stop()

# Setup API Google
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
except KeyError:
    st.error("ERRORE: Manca GOOGLE_API_KEY nei secrets.")
    st.stop()

# Funzione estrazione testo
def extract_full_context(ppt_file):
    prs = Presentation(ppt_file)
    full_text = []
    for i, slide in enumerate(prs.slides):
        texts = [shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text.strip()]
        full_text.append(f"[[Slide Originale {i+1}]]: {' | '.join(texts)}")
    return "\n\n".join(full_text)

# --- INTERFACCIA ---
st.title("🚀 Team Building AI Architect")
st.success("✅ Sistema Flat (No cartelle) operativo.")

col1, col2 = st.columns(2)
with col1:
    template_file = st.file_uploader("📂 Carica Template Rigido (10 pag)", type=['pptx'])
with col2:
    source_file = st.file_uploader("📄 Carica Vecchio PPT (Source)", type=['pptx'])

if template_file and source_file:
    if st.button("✨ AVVIA ELABORAZIONE SEQUENZIALE"):
        
        prs = Presentation(template_file)
        status = st.status("Inizio elaborazione...", expanded=True)
        
        # 1. Lettura
        status.write("📖 Lettura PPT originale...")
        full_context = extract_full_context(source_file)
        
        # 2. Elaborazione Modulare (Pagina per Pagina)
        
        # --- PAGINA 1: COVER ---
        status.write("🎨 Elaborazione Cover...")
        page1_cover.process_slide(prs.slides[0], full_context)

        # --- PAGINA 2: INTRODUZIONE ---
        if len(prs.slides) > 1:
            status.write("📝 Elaborazione Pagina 2: Intro...")
            page2_generic.process_slide(prs.slides[1], full_context, section_name="Introduzione al Format")

        # --- PAGINA 3: DETTAGLI TECNICI ---
        if len(prs.slides) > 2:
            status.write("⚙️ Elaborazione Pagina 3: Dettagli Tecnici...")
            page2_generic.process_slide(prs.slides[2], full_context, section_name="Dettagli Tecnici")

        # --- PAGINA 4: SVOLGIMENTO ---
        if len(prs.slides) > 3:
            status.write("▶️ Elaborazione Pagina 4: Svolgimento...")
            page2_generic.process_slide(prs.slides[3], full_context, section_name="Svolgimento Attività")
            
        # ... Aggiungi qui le altre pagine (5, 6, 7...) usando page2_generic
        
        status.update(label="✅ Finito! PPT pronto.", state="complete", expanded=False)
        
        # Download
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        st.download_button("📥 Scarica PPT Completato", out, "AI_Remake_Flat.pptx")
