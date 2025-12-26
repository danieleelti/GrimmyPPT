import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI - Gemini 3 Preview", layout="wide")

if 'auth' not in st.session_state: st.session_state['auth'] = False
if not st.session_state['auth']:
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]: st.session_state['auth'] = True; st.rerun()
    st.stop()

# --- SETUP API ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("ERRORE: Manca GOOGLE_API_KEY nei secrets."); st.stop()

@st.cache_data(ttl=600)
def get_gemini_models():
    """Recupera la lista modelli disponibile nell'account."""
    try:
        model_list = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if "gemini" in m.name.lower():
                    model_list.append(m.name)
        return model_list
    except Exception as e:
        st.error(f"Errore recupero modelli: {e}")
        return ["models/gemini-1.5-pro"]

# --- SIDEBAR: LOGICA DI SELEZIONE FORZATA ---
st.sidebar.header("🧠 AI Brain Engine")
available_models = get_gemini_models()

# --- MODIFICA CRITICA: TARGET ESATTO DALLO SCREENSHOT ---
TARGET_MODEL = "models/gemini-3-pro-preview"

if TARGET_MODEL in available_models:
    # Se esiste, prendiamo il suo indice per renderlo il default
    default_index = available_models.index(TARGET_MODEL)
    st.sidebar.success(f"✅ Trovato e selezionato: {TARGET_MODEL}")
else:
    # Fallback solo se non esiste (non dovrebbe succedere nel tuo caso)
    default_index = 0
    st.sidebar.warning(f"⚠️ {TARGET_MODEL} non trovato, seleziono il primo disponibile.")

selected_model = st.sidebar.selectbox(
    "Modello Attivo:", 
    available_models, 
    index=default_index
)

# --- CORE LOGIC ---
def get_context(ppt_file):
    prs = Presentation(ppt_file)
    text = []
    for s in prs.slides:
        text.append(" | ".join([shape.text for shape in s.shapes if hasattr(shape, "text")]))
    return "\n".join(text)

st.title("⚡ AI PPT Architect")
st.caption(f"Engine attuale: **{selected_model}**")

col1, col2 = st.columns(2)
with col1:
    t_file = st.file_uploader("Template (10 pag)", type=['pptx'])
with col2:
    c_file = st.file_uploader("Contenuto (Vecchio PPT)", type=['pptx'])

if t_file and c_file:
    if st.button("🚀 ESEGUI PAGE 1 (Cover)"):
        
        # RELOAD per evitare cache del codice
        importlib.reload(page1) 
        
        prs = Presentation(t_file)
        full_text = get_context(c_file)
        
        # Passiamo il modello selezionato (che ora sarà models/gemini-3-pro-preview)
        page1.process(prs.slides[0], full_text, model_name=selected_model)
        
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        st.download_button("📥 Scarica PPT", out, "Page1_Result.pptx")
