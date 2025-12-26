import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1
import page2  # Importiamo il nuovo file

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

if 'auth' not in st.session_state: st.session_state['auth'] = False
if not st.session_state['auth']:
    pwd = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        if pwd == st.secrets["app_password"]: st.session_state['auth'] = True; st.rerun()
    st.stop()

try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("ERRORE API KEY"); st.stop()

# --- INIT SESSION STATE PER PAGINA 1 e 2 ---
# Usiamo chiavi diverse per non sovrascrivere i dati
keys = ['p1_data', 'p1_img', 'p2_data', 'p2_img', 'ppt_buffer']
for k in keys:
    if k not in st.session_state: st.session_state[k] = None

# --- SIDEBAR MODELLI ---
st.sidebar.header("🧠 AI Settings")
gemini_model = "models/gemini-3-pro-preview" # Default forzato
imagen_model = "models/imagen-4.0-generate-preview-06-06" # Default forzato

# Selezione manuale se serve
try:
    models = [m.name for m in genai.list_models()]
    if gemini_model not in models: gemini_model = models[0]
except: pass
st.sidebar.caption(f"G: {gemini_model} | I: {imagen_model}")

# --- UTILS ---
def get_context(file):
    prs = Presentation(file)
    return "\n".join([" | ".join([s.text for s in slide.shapes if hasattr(s, 'text')]) for slide in prs.slides])

# --- UI PRINCIPALE ---
st.title("⚡ AI PPT Architect")

c1, c2 = st.columns(2)
t_file = c1.file_uploader("Template", type=['pptx'], key="tf")
c_file = c2.file_uploader("Contenuto", type=['pptx'], key="cf")

if t_file and c_file:
    # Gestione del file PPT in memoria (per poterlo salvare progressivamente)
    if st.session_state['ppt_buffer'] is None:
        # Carichiamo il template in memoria la prima volta
        st.session_state['ppt_buffer'] = io.BytesIO(t_file.getvalue())

    # --- TAB DI LAVORO ---
    tab1, tab2 = st.tabs(["PAGE 1: Cover", "PAGE 2: Scenario"])

    # ==========================
    # LOGICA PAGINA 1 (COVER)
    # ==========================
    with tab1:
        st.header("Cover")
        importlib.reload(page1)
        
        if st.button("1. Analizza Cover", key="btn_p1_an"):
            full_text = get_context(c_file)
            st.session_state['p1_data'] = page1.analyze_content(full_text, gemini_model)
        
        if st.session_state['p1_data']:
            with st.expander("Dati Cover", expanded=True):
                d = st.session_state['p1_data']
                d['format_name'] = st.text_input("Titolo", d.get('format_name'), key="p1_t")
                d['claim'] = st.text_input("Claim", d.get('claim'), key="p1_c")
                d['imagen_prompt'] = st.text_area("Prompt Img", d.get('imagen_prompt'), key="p1_p")
            
            if st.button("2. Genera Immagine Cover", key="btn_p1_img"):
                with st.spinner("Imagen 4 al lavoro..."):
                    img = page1.generate_image_with_imagen(d['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], imagen_model)
                    st.session_state['p1_img'] = img
            
            if st.session_state['p1_img']:
                st.image(st.session_state['p1_img'], width=300)
                
                if st.button("3. Salva Cover nel PPT", key="btn_p1_save"):
                    # Carica il PPT corrente dalla memoria
                    prs = Presentation(st.session_state['ppt_buffer'])
                    # Applica modifiche
                    page1.insert_content_into_ppt(prs.slides[0], st.session_state['p1_data'], st.session_state['p1_img'])
                    # Salva nel buffer
                    out = io.BytesIO()
                    prs.save(out)
                    out.seek(0)
                    st.session_state['ppt_buffer'] = out
                    st.success("Cover salvata in memoria! Passa alla Pagina 2.")

    # ==========================
    # LOGICA PAGINA 2 (SCENARIO)
    # ==========================
    with tab2:
        st.header("Scenario / Intro")
        importlib.reload(page2)
        
        if st.button("1. Analizza Pagina 2", key="btn_p2_an"):
            full_text = get_context(c_file)
            st.session_state['p2_data'] = page2.analyze_content(full_text, gemini_model)
            
        if st.session_state['p2_data']:
            with st.expander("Dati Pagina 2", expanded=True):
                d2 = st.session_state['p2_data']
                d2['format_name'] = st.text_input("Titolo", d2.get('format_name'), key="p2_t")
                d2['subtitle'] = st.text_input("Sottotitolo", d2.get('subtitle'), key="p2_st")
                d2['body'] = st.text_area("Corpo Testo", d2.get('body'), height=150, key="p2_b")
                d2['imagen_prompt'] = st.text_area("Prompt Img", d2.get('imagen_prompt'), key="p2_p")

            if st.button("2. Genera Immagine Pagina 2", key="btn_p2_img"):
                with st.spinner("Imagen 4 al lavoro..."):
                    img2 = page2.generate_image(d2['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], imagen_model)
                    st.session_state['p2_img'] = img2
            
            if st.session_state['p2_img']:
                st.image(st.session_state['p2_img'], width=300)
                
                if st.button("3. Salva Pagina 2 nel PPT", key="btn_p2_save"):
                    prs = Presentation(st.session_state['ppt_buffer'])
                    # Modifica slide 1 (che è la pagina 2, visto che parte da 0)
                    if len(prs.slides) > 1:
                        page2.insert_into_slide(prs.slides[1], st.session_state['p2_data'], st.session_state['p2_img'])
                        
                        out = io.BytesIO()
                        prs.save(out)
                        out.seek(0)
                        st.session_state['ppt_buffer'] = out
                        st.success("Pagina 2 salvata in memoria!")
                    else:
                        st.error("Il template ha meno di 2 pagine!")

    # --- DOWNLOAD GLOBALE ---
    st.divider()
    if st.session_state['ppt_buffer']:
        st.download_button("📥 SCARICA PPT AGGIORNATO (P1 + P2)", st.session_state['ppt_buffer'], "WIP_Presentation.pptx")
