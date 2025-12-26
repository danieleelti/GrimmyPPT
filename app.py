import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import sys
import os

# --- CORREZIONE PERCORSO (Il trucco per far vedere la cartella logic) ---
# Questo dice a Python: "Guarda anche nella cartella dove si trova questo file app.py"
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Ora l'import funzionerà sicuramente
try:
    from logic import page1_cover, page2_generic
except ImportError as e:
    st.error(f"Errore critico di importazione: {e}")
    st.stop()

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# --- LOGIN ---
if 'auth' not in st.session_state: st.session_state['auth'] = False
def check_login():
    if st.session_state['auth']: return True
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]: 
            st.session_state['auth'] = True
            st.rerun()
    return False

if not check_login(): st.stop()

# --- SETUP GOOGLE ---
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
except KeyError:
    st.error("ERRORE: Manca GOOGLE_API_KEY nei secrets.")
    st.stop()

# --- UTILITY CONTESTO ---
def extract_full_context(ppt_file):
    prs = Presentation(ppt_file)
    full_text = []
    for i, slide in enumerate(prs.slides):
        texts = [shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text.strip()]
        full_text.append(f"[[Slide Originale {i+1}]]: {' | '.join(texts)}")
    return "\n\n".join(full_text)

# --- INTERFACCIA ---
st.title("🚀 Team Building AI Architect")
st.success("✅ Moduli Logic Agganciati Correttamente")

col1, col2 = st.columns(2)
with col1:
    template_file = st.file_uploader("📂 Carica Template Rigido (10 pag)", type=['pptx'])
with col2:
    source_file = st.file_uploader("📄 Carica Vecchio PPT (Source)", type=['pptx'])

if template_file and source_file:
    if st.button("✨ Avvia Elaborazione Modulare"):
        
        prs = Presentation(template_file)
        status = st.status("Inizio elaborazione...", expanded=True)
        
        # 1. Lettura Contesto
        status.write("📖 Lettura PPT Sorgente...")
        full_context = extract_full_context(source_file)
        
        # 2. Elaborazione Pagina 1 (Cover)
        status.write("🎨 Elaborazione Slide 1: Cover...")
        try:
            # Chiama la logica specifica per la cover
            page1_cover.process_slide(prs.slides[0], full_context)
        except Exception as e:
            st.error(f"Errore nella Cover: {e}")

        # 3. Elaborazione Pagina 2 (Introduzione/Dettagli)
        # Qui usiamo page2_generic. Se in futuro vorrai una logica diversa per la pag 2
        # creerai un file 'page2_intro.py' e cambierai qui la chiamata.
        status.write("📝 Elaborazione Slide 2: Introduzione...")
        try:
            if len(prs.slides) > 1:
                page2_generic.process_slide(prs.slides[1], full_context, slide_type="Introduzione al Format")
        except Exception as e:
            st.error(f"Errore nella Pagina 2: {e}")

        # 4. Elaborazione Pagina 3 (Es. Obiettivi) - Usiamo il generico come placeholder
        status.write("🎯 Elaborazione Slide 3: Obiettivi...")
        try:
            if len(prs.slides) > 2:
                page2_generic.process_slide(prs.slides[2], full_context, slide_type="Obiettivi Formativi")
        except Exception as e:
            st.error(f"Errore nella Pagina 3: {e}")

        # ... (Il flusso continua per le altre pagine)

        status.update(label="✅ Elaborazione Completata!", state="complete", expanded=False)
        
        # Salvataggio
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        
        st.download_button("📥 Scarica PPT Finale", out, "AI_Remake_Modular.pptx")
