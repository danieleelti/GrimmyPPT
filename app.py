import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1
import page2
# In futuro importerai qui page3, page4, etc.

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# --- LOGIN ---
if 'auth' not in st.session_state: st.session_state['auth'] = False

# Sidebar Login
with st.sidebar:
    st.title("🎛️ Control Panel")
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

# --- INIT SESSION STATE (Per 6 pagine) ---
# Inizializziamo le variabili per tutte e 6 le pagine
for i in range(1, 7): # Da 1 a 6
    if f'p{i}_data' not in st.session_state: st.session_state[f'p{i}_data'] = None
    if f'p{i}_img' not in st.session_state: st.session_state[f'p{i}_img'] = None

if 'ppt_buffer' not in st.session_state: st.session_state['ppt_buffer'] = None
if 'last_t_name' not in st.session_state: st.session_state['last_t_name'] = None
if 'last_c_name' not in st.session_state: st.session_state['last_c_name'] = None

# --- FUNZIONI UTILI ---
@st.cache_data(ttl=600)
def get_models_by_type():
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
# SIDEBAR: MOTORI E FILE
# ==========================================
with st.sidebar:
    st.divider()
    st.subheader("1. Motori AI")
    gem_opts, img_opts = get_models_by_type()
    
    # Gemini
    g_idx = next((i for i, m in enumerate(gem_opts) if "gemini-3" in m), 0)
    selected_gemini = st.selectbox("Testo:", gem_opts, index=g_idx)
    
    # Imagen
    i_idx = next((i for i, m in enumerate(img_opts) if "imagen-4" in m), 
                 next((i for i, m in enumerate(img_opts) if "imagen-3" in m), 0))
    selected_imagen = st.selectbox("Immagini:", img_opts, index=i_idx)
    
    st.divider()
    st.subheader("2. Caricamento File")
    t_file = st.file_uploader("Template (10 pag)", type=['pptx'])
    c_file = st.file_uploader("Contenuto (Vecchio PPT)", type=['pptx'])
    
    # Reset Buffer se cambiano i file
    if t_file and c_file:
        if t_file.name != st.session_state['last_t_name'] or c_file.name != st.session_state['last_c_name']:
            st.session_state['ppt_buffer'] = io.BytesIO(t_file.getvalue())
            st.session_state['last_t_name'] = t_file.name
            st.session_state['last_c_name'] = c_file.name
            st.toast("File aggiornati. Premi Analizza!", icon="ready")

    # --- BOTTONE ANALIZZA TUTTO ---
    st.divider()
    analyze_btn = st.button("⚡ ANALIZZA TUTTO (6 PAGINE)", type="primary", use_container_width=True)

    if analyze_btn:
        if t_file and c_file:
            # Reload moduli per sicurezza
            importlib.reload(page1)
            importlib.reload(page2)
            
            # Status visibile nella sidebar o main (qui usiamo status container)
            with st.status("🚀 Analisi completa in corso...", expanded=True) as status:
                full_text = get_context(c_file)
                
                # --- PAGINA 1 ---
                status.write("Cover: Analisi...")
                st.session_state['p1_data'] = page1.analyze_content(full_text, selected_gemini)
                
                # --- PAGINA 2 ---
                status.write("Scenario: Analisi...")
                st.session_state['p2_data'] = page2.analyze_content(full_text, selected_gemini)
                
                # --- PAGINA 3-6 (Placeholder) ---
                status.write("Pagine 3-6: In attesa di modulo...")
                # Qui aggiungerai le chiamate a page3.analyze_content quando creeremo i file
                
                status.update(label="✅ Analisi completata!", state="complete", expanded=False)
        else:
            st.error("⚠️ Carica prima entrambi i file PPT!")

# ==========================================
# MAIN PAGE: WORKSPACE (6 TABS)
# ==========================================
st.title("⚡ AI PPT Architect")

if t_file and c_file and st.session_state['ppt_buffer']:
    
    # Creiamo 6 Tab per le 6 pagine richieste
    tabs = st.tabs(["1. Cover", "2. Scenario", "3. Timeline", "4. Tech", "5. Extra", "6. Chiusura"])

    # --- TAB 1: COVER ---
    with tabs[0]:
        st.subheader("🎨 P1: Cover")
        if st.session_state['p1_data']:
            c1, c2 = st.columns([1, 1])
            with c1:
                d = st.session_state['p1_data']
                d['format_name'] = st.text_input("Titolo", d.get('format_name'), key="p1_t")
                d['claim'] = st.text_input("Claim", d.get('claim'), key="p1_c")
                d['imagen_prompt'] = st.text_area("Prompt Img", d.get('imagen_prompt'), height=100, key="p1_p")
                
                if st.button("Genera Img P1", key="p1_ig"):
                    with st.spinner("Generazione..."):
                        st.session_state['p1_img'] = page1.generate_image_with_imagen(d['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
            with c2:
                if st.session_state['p1_img']:
                    st.image(st.session_state['p1_img'], caption="Anteprima P1", use_column_width=True)
                    if st.button("💾 SALVA P1 NEL PPT", type="primary", key="p1_sv"):
                        prs = Presentation(st.session_state['ppt_buffer'])
                        page1.insert_content_into_ppt(prs.slides[0], st.session_state['p1_data'], st.session_state['p1_img'])
                        out = io.BytesIO(); prs.save(out); out.seek(0); st.session_state['ppt_buffer'] = out
                        st.success("Salvato!")
        else: st.info("Premi 'ANALIZZA TUTTO' per iniziare.")

    # --- TAB 2: SCENARIO ---
    with tabs[1]:
        st.subheader("📝 P2: Scenario")
        if st.session_state['p2_data']:
            c3, c4 = st.columns([1, 1])
            with c3:
                d2 = st.session_state['p2_data']
                d2['format_name'] = st.text_input("Titolo", d2.get('format_name'), key="p2_t")
                d2['subtitle'] = st.text_input("Sottotitolo", d2.get('subtitle'), key="p2_st")
                d2['body'] = st.text_area("Corpo", d2.get('body'), height=150, key="p2_b")
                d2['imagen_prompt'] = st.text_area("Prompt Img", d2.get('imagen_prompt'), height=100, key="p2_p")
                
                if st.button("Genera Img P2", key="p2_ig"):
                    with st.spinner("Generazione..."):
                        st.session_state['p2_img'] = page2.generate_image(d2['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
            with c4:
                if st.session_state['p2_img']:
                    st.image(st.session_state['p2_img'], caption="Anteprima P2", use_column_width=True)
                    if st.button("💾 SALVA P2 NEL PPT", type="primary", key="p2_sv"):
                        prs = Presentation(st.session_state['ppt_buffer'])
                        if len(prs.slides) > 1:
                            page2.insert_into_slide(prs.slides[1], st.session_state['p2_data'], st.session_state['p2_img'])
                            out = io.BytesIO(); prs.save(out); out.seek(0); st.session_state['ppt_buffer'] = out
                            st.success("Salvato!")
        else: st.info("In attesa di analisi...")

    # --- TAB 3-6 (Placeholder) ---
    for i in range(2, 6):
        with tabs[i]:
            st.info(f"🚧 Modulo per Pagina {i+1} in costruzione. Appena avremo il file page{i+1}.py lo attiveremo qui.")

    # --- DOWNLOAD ---
    st.divider()
    st.markdown("### 📥 Scarica Risultato")
    st.download_button("SCARICA PPT COMPLETO", st.session_state['ppt_buffer'], "TeamBuilding_AI.pptx", type="primary", use_container_width=True)

else:
    st.info("👈 Carica i file e premi ANALIZZA TUTTO per iniziare.")
