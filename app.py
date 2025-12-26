import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib

# --- IMPORTIAMO LA LOGICA DELLE PAGINE ---
# Nota: Devi creare una cartella chiamata "logic" e mettere i file lì dentro
from logic import page1_cover, page2_generic

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# Recupero Secrets
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
except KeyError:
    st.error("ERRORE: Manca GOOGLE_API_KEY nei secrets.")
    st.stop()

# Login veloce (semplificato per brevità)
if 'auth' not in st.session_state: st.session_state['auth'] = False
if not st.session_state['auth']:
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]: st.session_state['auth'] = True; st.rerun()
    st.stop()

# --- FUNZIONI DI SUPPORTO ---
def extract_full_context(ppt_file):
    """Estrae TUTTO il testo dal vecchio PPT per dare contesto a Gemini."""
    prs = Presentation(ppt_file)
    full_text = []
    for i, slide in enumerate(prs.slides):
        texts = [shape.text for shape in slide.shapes if hasattr(shape, "text") and shape.text.strip()]
        full_text.append(f"[[Slide Originale {i+1}]]: {' | '.join(texts)}")
    return "\n\n".join(full_text)

# --- INTERFACCIA ---
st.title("🚀 Team Building AI Architect - Modular System")
st.markdown("Sistema a moduli: ogni pagina ha il suo cervello dedicato.")

col1, col2 = st.columns(2)
with col1:
    template_file = st.file_uploader("📂 Carica Template Rigido (10 pag)", type=['pptx'])
with col2:
    source_file = st.file_uploader("📄 Carica Vecchio PPT (Source)", type=['pptx'])

# --- ESECUZIONE ---
if template_file and source_file:
    if st.button("✨ ESEGUI TUTTO (Pagine 1-10)"):
        
        # 1. Preparazione
        status = st.status("Inizializzazione...", expanded=True)
        prs = Presentation(template_file)
        
        status.write("📖 Lettura contesto dal vecchio PPT...")
        full_context = extract_full_context(source_file)
        
        # 2. Elaborazione Modulare
        # Qui chiamiamo i file specifici per ogni pagina
        
        # --- PAGINA 1: COVER ---
        status.write("🎨 Elaborazione Pagina 1: Cover...")
        try:
            # Passiamo la slide[0], il contesto e l'API key (o il modello configurato)
            page1_cover.process_slide(prs.slides[0], full_context)
        except Exception as e:
            st.error(f"Errore su Pagina 1: {e}")

        # --- PAGINA 2: INTRODUZIONE / DETTAGLI ---
        status.write("📝 Elaborazione Pagina 2: Intro/Dettagli...")
        try:
            # Usiamo un file dedicato. Se la pag 3 è diversa, creerai page3.py
            page2_generic.process_slide(prs.slides[1], full_context, slide_type="Introduzione")
        except Exception as e:
            st.error(f"Errore su Pagina 2: {e}")
            
        # --- PAGINA 3... 10 ---
        # Per ora usiamo il generico per la pagina 3 come esempio, 
        # ma tu creerai page3_timeline.py, page4_tech.py etc.
        status.write("📝 Elaborazione Pagina 3: Esempio Generico...")
        try:
            page2_generic.process_slide(prs.slides[2], full_context, slide_type="Dettagli Tecnici")
        except IndexError:
            st.warning("Il template ha meno di 3 pagine, salto.")

        status.update(label="✅ Elaborazione Completata!", state="complete", expanded=False)
        
        # 3. Download
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        
        st.success("Tutte le pagine sono state processate secondo i moduli specifici.")
        st.download_button("📥 Scarica PPT Completato", out, "AI_Remake_Full.pptx")
