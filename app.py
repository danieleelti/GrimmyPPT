import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io

# --- IMPORTA I CERVELLI DELLE SINGOLE PAGINE ---
# Nota: Questi file devono esistere nella stessa cartella di app.py
import page1
import page2
import page3
# import page4 ... (aggiungerai gli altri man mano)

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI - Precision Mode", layout="wide")

if 'auth' not in st.session_state: st.session_state['auth'] = False
if not st.session_state['auth']:
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]: st.session_state['auth'] = True; st.rerun()
    st.stop()

# Setup API
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("Manca API Key"); st.stop()

def get_context(ppt_file):
    prs = Presentation(ppt_file)
    text = []
    for s in prs.slides:
        text.append(" | ".join([shape.text for shape in s.shapes if hasattr(shape, "text")]))
    return "\n".join(text)

# --- UI ---
st.title("🎛️ Controllo Pagina per Pagina")
t_file = st.file_uploader("Template (10 pag)", type=['pptx'])
c_file = st.file_uploader("Contenuto", type=['pptx'])

if t_file and c_file:
    if st.button("🚀 ESEGUI SEQUENZA DI CONTROLLO"):
        prs = Presentation(t_file)
        full_text = get_context(c_file)
        
        status = st.status("Elaborazione in corso...", expanded=True)
        
        # --- ESECUZIONE MODULARE ---
        
        # PAGINA 1
        status.write("PAGE 1: Cover...")
        page1.process(prs.slides[0], full_text)
        
        # PAGINA 2
        if len(prs.slides) > 1:
            status.write("PAGE 2: Introduzione...")
            page2.process(prs.slides[1], full_text)
            
        # PAGINA 3
        if len(prs.slides) > 2:
            status.write("PAGE 3: Dettagli Tecnici...")
            page3.process(prs.slides[2], full_text)

        # Qui aggiungerai: page4.process(prs.slides[3], full_text)...
        
        status.update(label="Finito!", state="complete")
        
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        st.download_button("Scarica PPT", out, "Precision_Remake.pptx")
