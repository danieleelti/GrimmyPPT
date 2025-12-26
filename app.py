import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1

# --- CONFIGURAZIONE E LOGIN ---
st.set_page_config(page_title="Team Building AI - Gemini 3 Native", layout="wide")

if 'auth' not in st.session_state: st.session_state['auth'] = False
if not st.session_state['auth']:
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]: st.session_state['auth'] = True; st.rerun()
    st.stop()

# --- SETUP API E RECUPERO MODELLI DISPONIBILI ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("ERRORE: Manca GOOGLE_API_KEY nei secrets."); st.stop()

@st.cache_data(ttl=600) # Cache per non chiamare Google a ogni click
def get_gemini_models():
    """Chiede a Google quali modelli sono abilitati per questa API Key."""
    try:
        model_list = []
        for m in genai.list_models():
            # Filtra solo i modelli che generano testo (Gemini)
            if 'generateContent' in m.supported_generation_methods:
                if "gemini" in m.name.lower():
                    model_list.append(m.name)
        model_list.sort(reverse=True) # Mette i numeri più alti in cima (es. 1.5 prima di 1.0)
        return model_list
    except Exception as e:
        st.error(f"Errore nel recupero modelli: {e}")
        return ["models/gemini-1.5-pro"] # Fallback di emergenza

# --- SIDEBAR: SELEZIONE MODELLO ---
st.sidebar.title("🧠 AI Brain Engine")
available_models = get_gemini_models()

# Logica intelligente: Cerca "gemini-3" o "preview" per metterlo di default
default_idx = 0
for i, m in enumerate(available_models):
    if "gemini-3" in m or "preview" in m: # Priorità alla versione 3 o Preview
        default_idx = i
        break

selected_model = st.sidebar.selectbox(
    "Versione Gemini in uso:", 
    available_models, 
    index=default_idx
)

st.sidebar.success(f"Target: `{selected_model}`")

# --- CORE LOGIC ---
def get_context(ppt_file):
    prs = Presentation(ppt_file)
    text = []
    for s in prs.slides:
        text.append(" | ".join([shape.text for shape in s.shapes if hasattr(shape, "text")]))
    return "\n".join(text)

st.title("⚡ AI PPT Architect")

col1, col2 = st.columns(2)
with col1:
    t_file = st.file_uploader("Template (10 pag)", type=['pptx'])
with col2:
    c_file = st.file_uploader("Contenuto (Vecchio PPT)", type=['pptx'])

if t_file and c_file:
    if st.button("🚀 ESEGUI PAGE 1 (Cover)"):
        
        # RICARICA MODULO per evitare cache vecchia
        importlib.reload(page1) 
        
        prs = Presentation(t_file)
        full_text = get_context(c_file)
        
        # Passiamo il modello selezionato dalla tendina alla funzione di processo
        page1.process(prs.slides[0], full_text, model_name=selected_model)
        
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        st.download_button("📥 Scarica PPT", out, "Page1_Gemini3.pptx")
