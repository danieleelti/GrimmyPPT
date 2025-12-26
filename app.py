import streamlit as st
import google.generativeai as genai
from pptx import Presentation
import io
import importlib
import page1
import page2
# import page3, page4, page5, page6 (Li aggiungerai qui)

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Team Building AI Architect", layout="wide")

# --- LOGIN ---
if 'auth' not in st.session_state: st.session_state['auth'] = False

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

# --- INIT SESSION STATE ---
# Predisponiamo le chiavi per 6 pagine
pages_indices = [1, 2, 3, 4, 5, 6]
for i in pages_indices:
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
# SIDEBAR: SETUP, FILES & ANALISI GLOBALE
# ==========================================
with st.sidebar:
    st.divider()
    st.header("🧠 Motori AI")
    
    gem_opts, img_opts = get_models_by_type()
    
    # Selezione Gemini
    g_idx = next((i for i, m in enumerate(gem_opts) if "gemini-3" in m), 0)
    selected_gemini = st.selectbox("Testo (Brain):", gem_opts, index=g_idx)
    
    # Selezione Imagen
    i_idx = next((i for i, m in enumerate(img_opts) if "imagen-4" in m), 
                 next((i for i, m in enumerate(img_opts) if "imagen-3" in m), 0))
    selected_imagen = st.selectbox("Immagini (Art):", img_opts, index=i_idx)
    
    st.divider()
    st.header("📂 Documenti")
    t_file = st.file_uploader("1. Template (10 pag)", type=['pptx'])
    c_file = st.file_uploader("2. Contenuto (Old PPT)", type=['pptx'])
    
    # Reset buffer se cambiano i file
    if t_file and c_file:
        if t_file.name != st.session_state['last_t_name'] or c_file.name != st.session_state['last_c_name']:
            st.session_state['ppt_buffer'] = io.BytesIO(t_file.getvalue())
            st.session_state['last_t_name'] = t_file.name
            st.session_state['last_c_name'] = c_file.name
            # Reset dati pagine
            for i in pages_indices:
                st.session_state[f'p{i}_data'] = None
                st.session_state[f'p{i}_img'] = None
            st.toast("Nuovi file caricati. Premi Analizza!", icon="🔄")

    # --- BOTTONE ANALISI GLOBALE ---
    st.divider()
    analyze_btn = st.button("⚡ ANALIZZA TUTTO (6 PAGINE)", type="primary", use_container_width=True, disabled=not(t_file and c_file))

    if analyze_btn and t_file and c_file:
        # Ricarica moduli per sicurezza
        importlib.reload(page1)
        importlib.reload(page2)
        # importlib.reload(page3)...
        
        with st.status("🚀 Avvio sequenza di analisi...", expanded=True) as status:
            full_text = get_context(c_file)
            
            # --- PAGINA 1 ---
            status.write("🔍 Analisi Page 1: Cover...")
            st.session_state['p1_data'] = page1.analyze_content(full_text, selected_gemini)
            
            # --- PAGINA 2 ---
            status.write("🔍 Analisi Page 2: Scenario...")
            st.session_state['p2_data'] = page2.analyze_content(full_text, selected_gemini)
            
            # --- PAGINA 3, 4, 5, 6 (Futuro) ---
            # status.write("🔍 Analisi Page 3...")
            # st.session_state['p3_data'] = page3.analyze_content(full_text, selected_gemini)
            # ... e così via fino alla 6
            
            status.update(label="✅ Analisi Completa! Controlla le schede.", state="complete", expanded=False)


# ==========================================
# MAIN PAGE: WORKSPACE
# ==========================================
st.title("⚡ AI PPT Architect")

if t_file and c_file and st.session_state['ppt_buffer']:
    
    # Definiamo le TAB (ne prevedo già 6 visivamente)
    tabs = st.tabs(["P1: Cover", "P2: Scenario", "P3: Timeline", "P4: Tech", "P5: Extra", "P6: Chiusura"])

    # --- TAB 1: COVER ---
    with tabs[0]:
        st.subheader("🎨 P1: Cover")
        
        if st.session_state['p1_data']:
            col_a, col_b = st.columns([1, 1])
            with col_a:
                d = st.session_state['p1_data']
                d['format_name'] = st.text_input("Titolo Format", d.get('format_name'), key="p1_t")
                d['claim'] = st.text_input("Claim", d.get('claim'), key="p1_c")
                d['imagen_prompt'] = st.text_area("Prompt Immagine", d.get('imagen_prompt'), height=120, key="p1_p")
                
                if st.button("🎨 Genera Immagine Cover", key="p1_ig", use_container_width=True):
                     with st.spinner("Generazione..."):
                        img = page1.generate_image_with_imagen(d['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
                        st.session_state['p1_img'] = img

            with col_b:
                if st.session_state['p1_img']:
                    st.image(st.session_state['p1_img'], caption="Anteprima", use_column_width=True)
                    if st.button("💾 SALVA P1 NEL PPT", type="primary", key="p1_sv", use_container_width=True):
                        prs = Presentation(st.session_state['ppt_buffer'])
                        page1.insert_content_into_ppt(prs.slides[0], st.session_state['p1_data'], st.session_state['p1_img'])
                        out = io.BytesIO(); prs.save(out); out.seek(0)
                        st.session_state['ppt_buffer'] = out
                        st.success("✅ Salvato!")
                else:
                    st.info("Genera l'immagine per vedere l'anteprima.")
        else:
            st.info("👈 Premi 'ANALIZZA TUTTO' nella sidebar per iniziare.")

    # --- TAB 2: SCENARIO ---
    with tabs[1]:
        st.subheader("📝 P2: Scenario / Intro")
        
        if st.session_state['p2_data']:
            col_c, col_d = st.columns([1, 1])
            with col_c:
                d2 = st.session_state['p2_data']
                d2['format_name'] = st.text_input("Titolo Slide", d2.get('format_name'), key="p2_t")
                d2['subtitle'] = st.text_input("Sottotitolo", d2.get('subtitle'), key="p2_st")
                d2['body'] = st.text_area("Corpo Testo", d2.get('body'), height=150, key="p2_b")
                d2['imagen_prompt'] = st.text_area("Prompt Immagine", d2.get('imagen_prompt'), height=120, key="p2_p")
                
                if st.button("🎨 Genera Immagine P2", key="p2_ig", use_container_width=True):
                    with st.spinner("Generazione..."):
                        img2 = page2.generate_image(d2['imagen_prompt'], st.secrets["GOOGLE_API_KEY"], selected_imagen)
                        st.session_state['p2_img'] = img2

            with col_d:
                if st.session_state['p2_img']:
                    st.image(st.session_state['p2_img'], caption="Anteprima", use_column_width=True)
                    if st.button("💾 SALVA P2 NEL PPT", type="primary", key="p2_sv", use_container_width=True):
                        prs = Presentation(st.session_state['ppt_buffer'])
                        if len(prs.slides) > 1:
                            page2.insert_into_slide(prs.slides[1], st.session_state['p2_data'], st.session_state['p2_img'])
                            out = io.BytesIO(); prs.save(out); out.seek(0)
                            st.session_state['ppt_buffer'] = out
                            st.success("✅ Salvato!")
                        else:
                            st.error("Template troppo corto (manca pag 2).")
                else:
                    st.info("Genera l'immagine per vedere l'anteprima.")
        else:
            st.info("In attesa di analisi...")

    # --- TAB 3, 4, 5, 6 (Placeholder) ---
    with tabs[2]: st.info("🚧 In arrivo: Timeline")
    with tabs[3]: st.info("🚧 In arrivo: Dettagli Tecnici")
    with tabs[4]: st.info("🚧 In arrivo: Extra")
    with tabs[5]: st.info("🚧 In arrivo: Chiusura")

    # --- DOWNLOAD BAR ---
    st.divider()
    st.markdown("### 📥 Output Finale")
    st.download_button(
        label="SCARICA PRESENTAZIONE COMPLETA",
        data=st.session_state['ppt_buffer'],
        file_name="AI_TeamBuilding_Presentation.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        type="primary",
        use_container_width=True
    )

else:
    st.markdown("""
    ### 👋 Benvenuto nell'AI Architect
    1. Carica il **Template** e il **Vecchio PPT** nella barra a sinistra.
    2. Scegli i modelli AI (Consigliato: **Gemini 3** + **Imagen 4**).
    3. Premi **"ANALIZZA TUTTO"**.
    """)
