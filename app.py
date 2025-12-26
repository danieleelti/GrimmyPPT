import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1
import page2
# import page3...

st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# --- LOGIN ---
if 'auth' not in st.session_state: st.session_state['auth'] = False
with st.sidebar:
    st.title("🎛️ Control Panel")
    if not st.session_state['auth']:
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == st.secrets["app_password"]: st.session_state['auth'] = True; st.rerun()
        st.stop()

# --- SETUP ---
try: genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except: st.error("No API Key"); st.stop()

# --- SESSION STATE ---
for i in range(1, 7):
    if f'p{i}_data' not in st.session_state: st.session_state[f'p{i}_data'] = None
    if f'p{i}_img' not in st.session_state: st.session_state[f'p{i}_img'] = None
if 'ppt_buffer' not in st.session_state: st.session_state['ppt_buffer'] = None
if 'last_t_name' not in st.session_state: st.session_state['last_t_name'] = None
if 'last_c_name' not in st.session_state: st.session_state['last_c_name'] = None

# --- UTILS ---
@st.cache_data(ttl=600)
def get_models_by_type():
    g, i = [], []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and "gemini" in m.name: g.append(m.name)
            if 'generateImage' in m.supported_generation_methods or "imagen" in m.name: i.append(m.name)
    except: pass
    return g, i

def get_context(f):
    prs = Presentation(f)
    return "\n".join([" | ".join([s.text for s in slide.shapes if hasattr(s, 'text')]) for slide in prs.slides])

# --- SIDEBAR ---
with st.sidebar:
    st.divider()
    gem_opts, img_opts = get_models_by_type()
    
    # Selezione Gemini (Cerca Gemini 3)
    g_idx = next((i for i, m in enumerate(gem_opts) if "gemini-3" in m), 0)
    selected_gemini = st.selectbox("Brain:", gem_opts, index=g_idx)
    
    # Selezione Imagen (Cerca Imagen 4)
    i_idx = next((i for i, m in enumerate(img_opts) if "imagen-4" in m), 0)
    selected_imagen = st.selectbox("Art:", img_opts, index=i_idx)
    
    st.divider()
    t_file = st.file_uploader("Template", type=['pptx'])
    c_file = st.file_uploader("Contenuto", type=['pptx'])
    
    if t_file and c_file:
        if t_file.name != st.session_state['last_t_name'] or c_file.name != st.session_state['last_c_name']:
            st.session_state['ppt_buffer'] = io.BytesIO(t_file.getvalue())
            st.session_state['last_t_name'] = t_file.name
            st.session_state['last_c_name'] = c_file.name
            
            # --- FIX: Icona DEVE essere un'emoji, non una parola ---
            st.toast("File pronti! Premi Analizza.", icon="✅")
    
    st.divider()
    if st.button("⚡ ANALIZZA TUTTO (6 PAGINE)", type="primary"):
        if t_file and c_file:
            importlib.reload(page1); importlib.reload(page2)
            with st.status("Analisi in corso...", expanded=True) as status:
                txt = get_context(c_file)
                
                status.write("Cover (Pagina 1)...")
                st.session_state['p1_data'] = page1.analyze_content(txt, selected_gemini)
                
                status.write("Scenario (Pagina 2)...")
                st.session_state['p2_data'] = page2.analyze_content(txt, selected_gemini)
                
                status.update(label="Analisi Completata!", state="complete")

# --- MAIN ---
st.title("⚡ AI PPT Architect")

if t_file and c_file and st.session_state['ppt_buffer']:
    tabs = st.tabs(["1. Cover", "2. Scenario", "3. Timeline", "4. Tech", "5. Extra", "6. Chiusura"])

    # --- TAB 1: COVER ---
    with tabs[0]:
        if st.session_state['p1_data']:
            c1, c2 = st.columns(2)
            with c1:
                d = st.session_state['p1_data']
                d['format_name'] = st.text_input("Titolo", d.get('format_name'), key="p1_t")
                d['claim'] = st.text_input("Claim", d.get('claim'), key="p1_c")
                d['imagen_prompt'] = st.text_area("Prompt Immagine", d.get('imagen_prompt'), height=100, key="p1_p")
                
                if st.button("Genera Img P1", key="p1_ig"):
                    with st.spinner("Generazione..."):
                        st.session_state['p1_img'] = page1.generate_image_with_imagen(d['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
            with c2:
                if st.session_state['p1_img']:
                    st.image(st.session_state['p1_img'], use_column_width=True)
                    if st.button("💾 SALVA P1", key="p1_sv"):
                        prs = Presentation(st.session_state['ppt_buffer'])
                        # Slide 0 = Pagina 1
                        page1.insert_content_into_ppt(prs.slides[0], st.session_state['p1_data'], st.session_state['p1_img'])
                        out = io.BytesIO(); prs.save(out); out.seek(0); st.session_state['ppt_buffer'] = out
                        st.success("Cover Salvata!")
        else:
            st.info("Premi 'ANALIZZA TUTTO' nella sidebar.")

    # --- TAB 2: SCENARIO ---
    with tabs[1]:
        if st.session_state['p2_data']:
            c3, c4 = st.columns(2)
            with c3:
                d2 = st.session_state['p2_data']
                d2['format_name'] = st.text_input("Titolo P2", d2.get('format_name'), key="p2_t")
                # Campo specifico per il testo Emozionale/Corsivo
                d2['emotional_text'] = st.text_area("Testo Emozionale (Corsivo)", d2.get('emotional_text'), height=150, key="p2_e")
                d2['imagen_prompt'] = st.text_area("Prompt Sfondo Full", d2.get('imagen_prompt'), height=100, key="p2_p")
                
                if st.button("Genera Sfondo P2", key="p2_ig"):
                    with st.spinner("Generazione..."):
                        st.session_state['p2_img'] = page2.generate_image(d2['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
            with c4:
                if st.session_state['p2_img']:
                    st.image(st.session_state['p2_img'], use_column_width=True)
                    if st.button("💾 SALVA P2", key="p2_sv"):
                        prs = Presentation(st.session_state['ppt_buffer'])
                        # Slide 1 = Pagina 2
                        if len(prs.slides) > 1:
                            page2.insert_into_slide(prs.slides[1], st.session_state['p2_data'], st.session_state['p2_img'])
                            out = io.BytesIO(); prs.save(out); out.seek(0); st.session_state['ppt_buffer'] = out
                            st.success("Pagina 2 Salvata!")
                        else: st.error("Errore: Il template ha meno di 2 pagine.")
        else: st.info("In attesa di analisi...")

    st.divider()
    st.download_button("📥 SCARICA PPT COMPLETO", st.session_state['ppt_buffer'], "AI_TeamBuilding.pptx", type="primary", use_container_width=True)
else:
    st.info("Carica i file nella sidebar per iniziare.")
