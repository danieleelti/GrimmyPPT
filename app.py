import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI - Interactive", layout="wide")

# Inizializzazione Session State per gestire il flusso
if 'analysis_data' not in st.session_state: st.session_state['analysis_data'] = None
if 'generated_image' not in st.session_state: st.session_state['generated_image'] = None
if 'ppt_ready' not in st.session_state: st.session_state['ppt_ready'] = None
if 'auth' not in st.session_state: st.session_state['auth'] = False

# --- LOGIN ---
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

# --- FUNZIONI UTILI ---
@st.cache_data(ttl=600)
def get_models_by_type():
    """Divide i modelli in Testo (Gemini) e Immagini (Imagen)."""
    gemini_list = []
    imagen_list = []
    try:
        for m in genai.list_models():
            name = m.name
            methods = m.supported_generation_methods
            if 'generateContent' in methods and "gemini" in name.lower(): gemini_list.append(name)
            if 'generateImage' in methods or "imagen" in name.lower(): imagen_list.append(name)
    except Exception as e: st.error(f"Errore API: {e}"); return [], []
    return gemini_list, imagen_list

def get_context(ppt_file):
    prs = Presentation(ppt_file)
    text = []
    for s in prs.slides:
        text.append(" | ".join([shape.text for shape in s.shapes if hasattr(shape, "text")]))
    return "\n".join(text)

# --- SIDEBAR: SELEZIONE MODELLI ---
st.sidebar.header("🎛️ AI Engine Room")
gemini_opts, imagen_opts = get_models_by_type()

gem_idx = next((i for i, m in enumerate(gemini_opts) if "gemini-3" in m), 0)
selected_gemini = st.sidebar.selectbox("Modello Gemini:", gemini_opts, index=gem_idx)

img_idx = next((i for i, m in enumerate(imagen_opts) if "imagen-4" in m), 
               next((i for i, m in enumerate(imagen_opts) if "imagen-3" in m), 0))
selected_imagen = st.sidebar.selectbox("Modello Imagen:", imagen_opts, index=img_idx)

st.sidebar.divider()
if "imagen-4" in selected_imagen: st.sidebar.success("🚀 Imagen 4 Attivo!")
elif "imagen-3" in selected_imagen: st.sidebar.success("✅ Imagen 3 Attivo")

# --- INTERFACCIA PRINCIPALE ---
st.title("⚡ AI PPT Architect - Flusso Interattivo")
st.caption(f"Engine: **{selected_gemini}** + **{selected_imagen}**")

col1, col2 = st.columns(2)
with col1: t_file = st.file_uploader("Template (10 pag)", type=['pptx'], key="t_file")
with col2: c_file = st.file_uploader("Contenuto (Vecchio PPT)", type=['pptx'], key="c_file")

# Reset stato se cambiano i file
if t_file and c_file:
    if st.session_state.get('last_t_file') != t_file.name or st.session_state.get('last_c_file') != c_file.name:
        st.session_state['analysis_data'] = None
        st.session_state['generated_image'] = None
        st.session_state['ppt_ready'] = None
        st.session_state['last_t_file'] = t_file.name
        st.session_state['last_c_file'] = c_file.name

if t_file and c_file:
    st.divider()
    importlib.reload(page1) # Reload logica

    # --- STEP 1: ANALISI TESTO ---
    if st.button("1️⃣ Analizza Testo e Prepara Prompt"):
        with st.spinner("Gemini sta analizzando il contenuto..."):
            full_text = get_context(c_file)
            # Chiama la nuova funzione di analisi
            data = page1.analyze_content(full_text, selected_gemini)
            if data:
                st.session_state['analysis_data'] = data
                st.session_state['generated_image'] = None # Reset immagine se si ri-analizza
                st.session_state['ppt_ready'] = None
                st.success("Analisi completata! Puoi modificare i prompt qui sotto.")
            else:
                st.error("Errore durante l'analisi del testo.")

    # --- VISUALIZZAZIONE E MODIFICA PROMPT ---
    if st.session_state['analysis_data']:
        st.subheader("📝 Revisione Prompt")
        with st.expander("Modifica Testi e Prompt Immagine", expanded=True):
            # Campi di testo modificabili dall'utente
            new_format_name = st.text_input("Nome Format (Titolo)", st.session_state['analysis_data'].get("format_name", ""))
            new_claim = st.text_input("Claim (Sottotitolo)", st.session_state['analysis_data'].get("claim", ""))
            new_imagen_prompt = st.text_area("Prompt per Imagen (Inglese)", st.session_state['analysis_data'].get("imagen_prompt", ""), height=150)
            
            # Aggiorna lo stato con i valori eventualmente modificati
            st.session_state['analysis_data']['format_name'] = new_format_name
            st.session_state['analysis_data']['claim'] = new_claim
            st.session_state['analysis_data']['imagen_prompt'] = new_imagen_prompt

        # --- STEP 2: GENERAZIONE E ANTEPRIMA IMMAGINE ---
        if st.button("2️⃣ Genera Anteprima Immagine"):
            with st.spinner(f"Imagen sta creando l'immagine con il tuo prompt..."):
                api_key = st.secrets["GOOGLE_API_KEY"]
                prompt = st.session_state['analysis_data']['imagen_prompt']
                # Chiama la funzione di generazione immagine
                img_bytes = page1.generate_image_with_imagen(prompt, api_key, selected_imagen)
                if img_bytes:
                    st.session_state['generated_image'] = img_bytes
                    st.session_state['ppt_ready'] = None # Reset PPT se si rigenera l'immagine
                else:
                    st.error("Generazione immagine fallita.")

    # --- VISUALIZZAZIONE ANTEPRIMA ---
    if st.session_state['generated_image']:
        st.subheader("🖼️ Anteprima Immagine")
        st.image(st.session_state['generated_image'], caption="Immagine generata da Imagen", use_column_width=True)
        st.info("Se l'immagine non ti piace, modifica il prompt sopra e clicca di nuovo su 'Genera Anteprima'.")

        # --- STEP 3: CONFERMA E CREAZIONE PPT ---
        if st.button("3️⃣ Conferma e Crea PPT (Immagine nello Schema)"):
            with st.spinner("Inserimento contenuti nel PowerPoint..."):
                # Ricarica il template originale per evitare modifiche su modifiche
                t_file.seek(0)
                prs = Presentation(t_file)
                slide = prs.slides[0] # Cover
                
                # Chiama la nuova funzione di inserimento nel PPT
                success = page1.insert_content_into_ppt(
                    slide, 
                    st.session_state['analysis_data'], 
                    st.session_state['generated_image']
                )
                
                if success:
                    out = io.BytesIO()
                    prs.save(out)
                    out.seek(0)
                    st.session_state['ppt_ready'] = out
                    st.success("PPT creato con successo! L'immagine è stata inserita nello Schema Diapositiva.")
                else:
                    st.error("Errore durante la creazione del PPT.")

    # --- DOWNLOAD FINALE ---
    if st.session_state['ppt_ready']:
        st.divider()
        st.download_button("📥 Scarica PPT Completo", st.session_state['ppt_ready'], "Cover_Final.pptx")
