import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI - Next Gen", layout="wide")

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

# --- RECUPERO MODELLI DISPONIBILI ---
@st.cache_data(ttl=600)
def get_models_by_type():
    """Divide i modelli in Testo (Gemini) e Immagini (Imagen)."""
    gemini_list = []
    imagen_list = []
    
    try:
        for m in genai.list_models():
            name = m.name
            methods = m.supported_generation_methods
            
            # GEMINI
            if 'generateContent' in methods and "gemini" in name.lower():
                gemini_list.append(name)
            
            # IMAGEN (Cerca 'generateImage' o 'image' nel nome)
            if 'generateImage' in methods or "imagen" in name.lower():
                imagen_list.append(name)
                
    except Exception as e:
        st.error(f"Errore API Google: {e}")
        return [], []

    return gemini_list, imagen_list

# --- SIDEBAR: INTELLIGENCE SELECTION ---
st.sidebar.header("🎛️ AI Engine Room")

gemini_opts, imagen_opts = get_models_by_type()

# 1. SELEZIONE GEMINI (Cerca Gemini 3)
st.sidebar.subheader("🧠 Cervello (Testo)")
# Logica di default: Cerca "gemini-3", se non c'è prende il primo
gem_idx = 0
for i, m in enumerate(gemini_opts):
    if "gemini-3" in m:
        gem_idx = i
        break
selected_gemini = st.sidebar.selectbox("Modello Gemini:", gemini_opts, index=gem_idx)

# 2. SELEZIONE IMAGEN (Priorità: Imagen 4 > Imagen 3)
st.sidebar.subheader("🎨 Creativo (Immagini)")
img_idx = 0
found_priority = False

# Cerca prima Imagen 4
for i, m in enumerate(imagen_opts):
    if "imagen-4" in m:
        img_idx = i
        found_priority = True
        break

# Se non trova il 4, cerca Imagen 3
if not found_priority:
    for i, m in enumerate(imagen_opts):
        if "imagen-3" in m:
            img_idx = i
            break

selected_imagen = st.sidebar.selectbox("Modello Imagen:", imagen_opts, index=img_idx)

# Feedback visivo
st.sidebar.divider()
if "imagen-4" in selected_imagen:
    st.sidebar.success("🚀 WOW! Imagen 4 Attivo!")
elif "imagen-3" in selected_imagen:
    st.sidebar.success("✅ Imagen 3 Attivo")

# --- CORE LOGIC ---
def get_context(ppt_file):
    prs = Presentation(ppt_file)
    text = []
    for s in prs.slides:
        text.append(" | ".join([shape.text for shape in s.shapes if hasattr(shape, "text")]))
    return "\n".join(text)

st.title("⚡ AI PPT Architect")
st.caption(f"Engine: **{selected_gemini}** + **{selected_imagen}**")

col1, col2 = st.columns(2)
with col1:
    t_file = st.file_uploader("Template (10 pag)", type=['pptx'])
with col2:
    c_file = st.file_uploader("Contenuto (Vecchio PPT)", type=['pptx'])

if t_file and c_file:
    if st.button("🚀 ESEGUI PAGE 1 (Cover)"):
        
        importlib.reload(page1) 
        
        prs = Presentation(t_file)
        full_text = get_context(c_file)
        
        # Passiamo i modelli selezionati
        page1.process(
            slide=prs.slides[0], 
            context=full_text, 
            gemini_model=selected_gemini, 
            imagen_model=selected_imagen
        )
        
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        st.download_button("📥 Scarica PPT", out, "Page1_Imagen4.pptx")
