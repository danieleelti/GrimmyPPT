import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1
import page2

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# --- LOGIN ---
if 'auth' not in st.session_state: st.session_state['auth'] = False

with st.sidebar:
    st.title("🎛️ Pannello di Controllo")
    if not st.session_state['auth']:
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == st.secrets["app_password"]: 
                st.session_state['auth'] = True
                st.rerun()
        st.stop()

# --- SETUP API ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("ERRORE: Manca GOOGLE_API_KEY nei secrets."); st.stop()

# --- INIT SESSION STATE ---
keys = ['p1_data', 'p1_img', 'p2_data', 'p2_img', 'ppt_buffer', 'last_t_name', 'last_c_name']
for k in keys:
    if k not in st.session_state: st.session_state[k] = None

# --- FUNZIONI UTILI ---
@st.cache_data(ttl=600)
def get_models_by_type():
    """Recupera modelli Gemini e Imagen disponibili."""
    gemini_list, imagen_list = [], []
    try:
        for m in genai.list_models():
            name = m.name
            methods = m.supported_generation_methods
            if 'generateContent' in methods and "gemini" in name.lower(): gemini_list.append(name)
            if 'generateImage' in methods or "imagen" in name.lower(): imagen_list.append(name)
    except: pass
    return gemini_list, imagen_list

def get_context(file):
    prs = Presentation(file)
    return "\n".join([" | ".join([s.text for s in slide.shapes if hasattr(s, 'text')]) for slide in prs.slides])

# ==========================================
# SIDEBAR: SETUP & FILES
# ==========================================
with st.sidebar:
    st.divider()
    st.header("🧠 Motori AI")
    
    gem_opts, img_opts = get_models_by_type()
    
    # Selezione Gemini (Default: Gemini 3)
    g_idx = next((i for i, m in enumerate(gem_opts) if "gemini-3" in m), 0)
    selected_gemini = st.selectbox("Modello Testo:", gem_opts, index=g_idx)
    
    # Selezione Imagen (Default: Imagen 4, poi 3)
    i_idx = next((i for i, m in enumerate(img_opts) if "imagen-4" in m), 
                 next((i for i, m in enumerate(img_opts) if "imagen-3" in m), 0))
    selected_imagen = st.selectbox("Modello Immagini:", img_opts, index=i_idx)
    
    st.divider()
    st.header("📂 File Input")
    t_file = st.file_uploader("1. Template (10 pag)", type=['pptx'])
    c_file = st.file_uploader("2. Contenuto (Old PPT)", type=['pptx'])
    
    # Reset buffer se cambiano i file
    if t_file and c_file:
        if t_file.name != st.session_state['last_t_name'] or c_file.name != st.session_state['last_c_name']:
            st.session_state['ppt_buffer'] = io.BytesIO(t_file.getvalue())
            st.session_state['last_t_name'] = t_file.name
            st.session_state['last_c_name'] = c_file.name
            # Reset dati pagine
            st.session_state['p1_data'] = None; st.session_state['p1_img'] = None
            st.session_state['p2_data'] = None; st.session_state['p2_img'] = None
            st.toast("Buffer PPT inizializzato con nuovi file!", icon="🔄")

# ==========================================
# MAIN PAGE: WORKSPACE
# ==========================================
st.title("⚡ AI PPT Architect")
st.caption(f"Engine Attivo: **{selected_gemini}** + **{selected_imagen}**")

if t_file and c_file and st.session_state['ppt_buffer']:
    
    tab1, tab2 = st.tabs(["PAGE 1: Cover", "PAGE 2: Scenario"])

    # --- TAB 1: COVER ---
    with tab1:
        st.subheader("🎨 Pagina 1: Cover")
        importlib.reload(page1)
        
        col_a, col_b = st.columns([1, 1])
        with col_a:
            if st.button("1. Analizza Cover", key="p1_an", use_container_width=True):
                with st.spinner("Analisi in corso..."):
                    full_text = get_context(c_file)
                    st.session_state['p1_data'] = page1.analyze_content(full_text, selected_gemini)

            if st.session_state['p1_data']:
                d = st.session_state['p1_data']
                d['format_name'] = st.text_input("Titolo Format", d.get('format_name'), key="p1_t")
                d['claim'] = st.text_input("Claim", d.get('claim'), key="p1_c")
                d['imagen_prompt'] = st.text_area("Prompt Immagine", d.get('imagen_prompt'), height=100, key="p1_p")
                
                if st.button("2. Genera Immagine", key="p1_ig", use_container_width=True):
                     with st.spinner("Generazione..."):
                        img = page1.generate_image_with_imagen(d['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
                        st.session_state['p1_img'] = img

        with col_b:
            if st.session_state['p1_img']:
                st.image(st.session_state['p1_img'], caption="Anteprima Cover", use_column_width=True)
                
                if st.button("3. SALVA in PPT", type="primary", key="p1_sv", use_container_width=True):
                    prs = Presentation(st.session_state['ppt_buffer'])
                    page1.insert_content_into_ppt(prs.slides[0], st.session_state['p1_data'], st.session_state['p1_img'])
                    out = io.BytesIO()
                    prs.save(out)
                    out.seek(0)
                    st.session_state['ppt_buffer'] = out
                    st.success("✅ Cover salvata nel file temporaneo!")

    # --- TAB 2: SCENARIO ---
    with tab2:
        st.subheader("📝 Pagina 2: Scenario / Intro")
        importlib.reload(page2)
        
        col_c, col_d = st.columns([1, 1])
        with col_c:
            if st.button("1. Analizza Pagina 2", key="p2_an", use_container_width=True):
                with st.spinner("Analisi in corso..."):
                    full_text = get_context(c_file)
                    st.session_state['p2_data'] = page2.analyze_content(full_text, selected_gemini)
            
            if st.session_state['p2_data']:
                d2 = st.session_state['p2_data']
                d2['format_name'] = st.text_input("Titolo Slide", d2.get('format_name'), key="p2_t")
                d2['subtitle'] = st.text_input("Sottotitolo", d2.get('subtitle'), key="p2_st")
                d2['body'] = st.text_area("Corpo del Testo", d2.get('body'), height=150, key="p2_b")
                d2['imagen_prompt'] = st.text_area("Prompt Immagine", d2.get('imagen_prompt'), height=100, key="p2_p")
                
                if st.button("2. Genera Immagine", key="p2_ig", use_container_width=True):
                    with st.spinner("Generazione..."):
                        img2 = page2.generate_image(d2['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
                        st.session_state['p2_img'] = img2

        with col_d:
            if st.session_state['p2_img']:
                st.image(st.session_state['p2_img'], caption="Anteprima Pagina 2", use_column_width=True)
                
                if st.button("3. SALVA in PPT", type="primary", key="p2_sv", use_container_width=True):
                    prs = Presentation(st.session_state['ppt_buffer'])
                    if len(prs.slides) > 1:
                        page2.insert_into_slide(prs.slides[1], st.session_state['p2_data'], st.session_state['p2_img'])
                        out = io.BytesIO()
                        prs.save(out)
                        out.seek(0)
                        st.session_state['ppt_buffer'] = out
                        st.success("✅ Pagina 2 salvata nel file temporaneo!")
                    else:
                        st.error("Errore: Il template non ha una pagina 2.")

    # --- DOWNLOAD BAR ---
    st.divider()
    st.markdown("### 📥 Esportazione Finale")
    col_dwn, _ = st.columns([1, 3])
    with col_dwn:
        st.download_button(
            label="SCARICA PRESENTAZIONE AGGIORNATA",
            data=st.session_state['ppt_buffer'],
            file_name="New_Format_TeamBuilding.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary",
            use_container_width=True
        )

else:
    st.info("👈 Carica il Template e il Vecchio PPT dalla barra laterale per iniziare.")
