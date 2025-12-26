import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI - Full Control", layout="wide")

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

# --- FUNZIONI RECUPERO MODELLI ---
@st.cache_data(ttl=600)
def get_models_by_type():
    """Recupera e divide i modelli disponibili in Testo (Gemini) e Immagini (Imagen)."""
    gemini_list = []
    imagen_list = []
    
    try:
        for m in genai.list_models():
            # 1. Lista Gemini (Text Generation)
            if 'generateContent' in m.supported_generation_methods:
                if "gemini" in m.name.lower():
                    gemini_list.append(m.name)
            
            # 2. Lista Imagen (Image Generation)
            # Cerchiamo modelli che hanno 'image' nel nome o supportano 'generateImage'
            if "imagen" in m.name.lower() or 'generateImage' in m.supported_generation_methods:
                imagen_list.append(m.name)
                
    except Exception as e:
        st.error(f"Errore recupero modelli API: {e}")
        # Fallback manuale se l'API fallisce
        return ["models/gemini-1.5-pro"], ["models/imagen-3.0-generate-001"]

    # Se la lista Imagen è vuota (capita con alcune chiavi), forziamo quella nota
    if not imagen_list:
        imagen_list = ["models/imagen-3.0-generate-001", "models/imagen-2.0"]
        
    return gemini_list, imagen_list

# --- SIDEBAR: SELEZIONE MODELLI ---
st.sidebar.header("🎛️ AI Engine Room")

gemini_opts, imagen_opts = get_models_by_type()

# 1. SELEZIONE GEMINI (Default: Gemini 3)
st.sidebar.subheader("🧠 Cervello (Testo)")
gemini_target = "models/gemini-3-pro-preview"
gem_idx = gemini_opts.index(gemini_target) if gemini_target in gemini_opts else 0
selected_gemini = st.sidebar.selectbox("Modello Gemini:", gemini_opts, index=gem_idx)

# 2. SELEZIONE IMAGEN (Default: Imagen 3)
st.sidebar.subheader("🎨 Creativo (Immagini)")
# Cerchiamo di selezionare Imagen 3 di default
img_idx = 0
for i, m in enumerate(imagen_opts):
    if "imagen-3" in m.lower():
        img_idx = i
        break

selected_imagen = st.sidebar.selectbox("Modello Imagen:", imagen_opts, index=img_idx)

# --- CORE LOGIC ---
def get_context(ppt_file):
    prs = Presentation(ppt_file)
    text = []
    for s in prs.slides:
        text.append(" | ".join([shape.text for shape in s.shapes if hasattr(shape, "text")]))
    return "\n".join(text)

st.title("⚡ AI PPT Architect")
st.info(f"Configurazione Attiva: **{selected_gemini}** + **{selected_imagen}**")

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
        
        # Passiamo ENTRAMBI i modelli selezionati
        page1.process(
            slide=prs.slides[0], 
            context=full_text, 
            gemini_model=selected_gemini, 
            imagen_model=selected_imagen
        )
        
        out = io.BytesIO()
        prs.save(out)
        out.seek(0)
        st.download_button("📥 Scarica PPT", out, "Page1_AutoImage.pptx")
