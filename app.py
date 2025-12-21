import streamlit as st
import google.generativeai as genai
from pptx import Presentation
from pptx.util import Inches, Pt
import tempfile
import json
import re
import os
from io import BytesIO
from PIL import Image

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Grimmy PPT Agent", layout="wide", page_icon="🤖")

# --- AUTHENTICATION ---
if "APP_PASSWORD" not in st.secrets:
    st.warning("⚠️ Manca APP_PASSWORD in secrets.toml")
else:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🤖 Ciao, sono Grimmy.")
            st.markdown("Inserisci la password per entrare nel mio laboratorio.")
            pwd = st.text_input("Password Workspace", type="password")
            if st.button("Sblocca Grimmy"):
                if pwd == st.secrets["APP_PASSWORD"]:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("Accesso Negato. Riprova.")
        st.stop()

# --- SETUP API KEY ---
api_key = st.secrets.get("GOOGLE_API_KEY")

# --- FUNZIONE GENERATORE TEMPLATE TECNICO (16:9) ---
def create_technical_template():
    """Crea un PPT vuoto in 16:9 con i layout rinominati correttamente per Grimmy."""
    prs = Presentation()
    
    # --- FORZA WIDESCREEN 16:9 ---
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    # -----------------------------

    master = prs.slide_master
    layouts = master.slide_layouts
    
    # Helper per note
    def add_hint(layout, text):
        try:
            txBox = layout.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(12), Inches(1))
            tf = txBox.text_frame
            tf.text = text
            tf.paragraphs[0].font.color.rgb = None 
            tf.paragraphs[0].font.size = Pt(12)
            tf.paragraphs[0].font.bold = True
        except: pass

    # 0. COVER
    if len(layouts) > 0:
        layouts[0].name = "Cover_Main"
        add_hint(layouts[0], "LAYOUT: Cover_Main (Titolo + Sottotitolo + Immagine NanoBanana)")

    # 1. INTRO (Il Concept Emotivo)
    if len(layouts) > 1:
        layouts[1].name = "Intro_Concept"
        add_hint(layouts[1], "LAYOUT: Intro_Concept (Titolo + Frase a effetto breve/informale)")

    # 2. LOGISTICS 
    if len(layouts) > 2:
        layouts[2].name = "Logistics_Info"
        add_hint(layouts[2], "LAYOUT: Logistics_Info (Cosa incluso/escluso)")

    # 3. ACTIVITY 
    if len(layouts) > 3:
        layouts[3].name = "Activity_Detail"
        add_hint(layouts[3], "LAYOUT: Activity_Detail (Descrizione operativa + Foto)")

    # 4. TECHNICAL 
    if len(layouts) > 4:
        layouts[4].name = "Technical_Grid"
        add_hint(layouts[4], "LAYOUT: Technical_Grid (Scheda tecnica, durate, pax)")

    # --- SLIDE FISSE ---
    if len(layouts) > 5:
        layouts[5].name = "Standard_Training"
        add_hint(layouts[5], "FISSO: Standard_Training (Grafica Formazione)")
    
    if len(layouts) > 6:
        layouts[6].name = "Standard_Extras"
        add_hint(layouts[6], "FISSO: Standard_Extras (Foto/Video/Gadget)")

    if len(layouts) > 7:
        layouts[7].name = "Standard_Payment"
        add_hint(layouts[7], "FISSO: Standard_Payment (IBAN/Banca)")

    if len(layouts) > 8:
        layouts[8].name = "Closing_Contact"
        add_hint(layouts[8], "FISSO: Closing_Contact (Contatti finali)")

    output = BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# --- SIDEBAR: CENTRO DI CONTROLLO ---
with st.sidebar:
    st.title("⚙️ Configurazione")
    
    if not api_key:
        api_key = st.text_input("Google API Key", type="password")
        if not api_key:
            st.warning("Dammi una chiave API per funzionare.")
            st.stop()
    
    genai.configure(api_key=api_key)

    st.markdown("---")
    
    # SCELTA MODELLI
    st.subheader("🧠 I Modelli AI")
    
    # Testo (Gemini)
    try:
        all_models = list(genai.list_models())
        text_models = [m.name for m in all_models if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name]
        text_models.sort(reverse=True) 
        
        default_gemini = "gemini-3-pro-preview"
        target_found = False
        for i, m in enumerate(text_models):
            if default_gemini in m:
                default_gemini = m
                text_models.pop(i)
                text_models.insert(0, default_gemini)
                target_found = True
                break
        if not target_found: text_models.insert(0, default_gemini)

        selected_text_model = st.selectbox("Cervello (Logica)", text_models, index=0)
    except Exception as e:
        selected_text_model = "gemini-3-pro-preview"

    # Immagini (NanoBanana)
    imagen_options = [
        "imagen-3.0-generate",
        "imagen-3.0-generate-001",
        "imagen-2.0-generate-001",
        "turing-preview",
        "image-generation-001"
    ]
    selected_image_model = st.selectbox("NanoBanana (Arte)", imagen_options)

    st.markdown("---")

    # GESTIONE TEMPLATE
    st.subheader("📂 Il Template Master")
    
    with st.expander("🛠️ Crea Nuovo Scheletro (16:9)"):
        st.caption("Genera un file .pptx vuoto e Widescreen. Scaricalo, modificalo in PowerPoint e ricaricalo qui sotto.")
        if st.button("Genera Scheletro Tecnico"):
            tpl_bytes = create_technical_template()
            st.download_button(
                label="📥 Scarica Template_Grimmy_Base.pptx",
                data=tpl_bytes,
                file_name="Template_Grimmy_Base.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key="dl_skeleton"
            )

    template = st.file_uploader("Carica il Template Master (.pptx)", type=["pptx"])
    if template:
        st.success("✅ Template caricato!")
    else:
        st.info("⚠️ Carica il template per abilitare Grimmy.")

    st.markdown("---")

    if st.button("❤️ Check Salute"):
        with st.status("Diagnostica...") as status:
            try:
                model = genai.GenerativeModel(selected_text_model)
                res = model.generate_content("Ping")
                st.write("✅ Cervello OK")
            except: st.error("❌ Errore Cervello")
            
            try:
                img_model = genai.ImageGenerationModel(selected_image_model)
                res = img_model.generate_images(prompt="Dot", number_of_images=1)
                st.write("✅ NanoBanana OK")
            except: st.error("❌ Errore NanoBanana")
            status.update(label="Test Finito", state="complete")

# --- FUNZIONI CORE ---

def extract_content(file_path):
    prs = Presentation(file_path)
    full_text = []
    first_image = None 
    try:
        if len(prs.slides) > 0:
            for shape in prs.slides[0].shapes:
                if shape.shape_type == 13: 
                    first_image = shape.image.blob
                    break
    except: pass

    for slide in prs.slides:
        txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                txt.append(shape.text.strip())
        if txt: full_text.append(" | ".join(txt))
    
    return "\n".join(full_text), first_image

def get_gemini_plan_and_prompts(text, model_name):
    model = genai.GenerativeModel(model_name)
    
    # PROMPT AGGIORNATO PER STILE INFORMALE NELLA INTRO
    prompt = f"""
    Sei Grimmy, un Senior Art Director specializzato in presentazioni Corporate.
    ANALIZZA questo contenuto grezzo: "{text[:3500]}"...
    
    OBIETTIVO 1: Ristruttura le slide mappandole su questi layout del Master: 
    
    - Cover_Main (Titolo, Sottotitolo)
    
    - Intro_Concept (Titolo: "Il Concept". Body: Scrivi UNA SOLA frase a effetto, breve (max 20 parole). 
      Deve essere uno slogan informale, simpatico e creativo che colleghi l'attività all'immagine visiva del team building. 
      Esempio: "Mettetevi comodi, oggi si cucina!" oppure "Pronti a sporcarvi le mani? No perditempo!")
    
    - Activity_Detail (Dettagli operativi, usa elenchi puntati chiari)
    - Technical_Grid (Scheda tecnica: durata, pax, location)
    - Logistics_Info (Logistica: cosa è incluso/escluso)
    
    OBIETTIVO 2: Scrivi 2 PROMPT per generare un'immagine di COPERTINA usando 'NanoBanana' (Google Imagen).
    I prompt devono essere in INGLESE, estremamente dettagliati.
    - Prompt A (Stile Corporate): Fotorealistico, persone reali in azione, luminoso, collaborazione, alta definizione.
    - Prompt B (Stile Creativo/NanoBanana): Astratto, metaforico, oggetti 3D render, composizione artistica, illuminazione da studio.
    
    OUTPUT JSON:
    {{
        "slides": [ ...array con campi: layout, title, body... ],
        "cover_prompt_a": "...",
        "cover_prompt_b": "..."
    }}
    Restituisci SOLO JSON valido.
    """
    try:
        resp = model.generate_content(prompt)
        cleaned = re.sub(r"```json|```", "", resp.text).strip()
        return json.loads(cleaned)
    except Exception as e:
        st.error(f"Grimmy ha avuto un pensiero confuso: {e}")
        return None

def generate_imagen_image(prompt, model_name):
    try:
        imagen_model = genai.ImageGenerationModel(model_name)
        response = imagen_model.generate_images(
            prompt=prompt + ", high quality, 4k, photorealistic, no text overlays",
            number_of_images=1,
            aspect_ratio="16:9",
            safety_filter_level="block_only_high",
            person_generation="allow_adult"
        )
        if response.images:
            img = response.images[0]
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='PNG')
            return img_byte_arr.getvalue()
        return None
    except Exception as e:
        st.warning(f"NanoBanana ha fallito ({model_name}): {e}")
        return None

def create_final_pptx(plan, cover_image_bytes, template_path):
    prs = Presentation(template_path)
    layout_map = {l.name: l for l in prs.slide_master_layouts}
    
    # 1. Slide Cover
    cover_layout = layout_map.get("Cover_Main", prs.slide_master_layouts[0])
    slide = prs.slides.add_slide(cover_layout)
    
    cover_data = next((s for s in plan['slides'] if s['layout'] == 'Cover_Main'), None)
    if cover_data and slide.shapes.title: 
        slide.shapes.title.text = cover_data.get('title', 'Team Building')
    
    if cover_image_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_img:
            tmp_img.write(cover_image_bytes)
            tmp_path = tmp_img.name
        try:
            inserted = False
            for shape in slide.placeholders:
                if shape.placeholder_format.type == 18: 
                    shape.insert_picture(tmp_path)
                    inserted = True
                    break
            if not inserted:
                slide.shapes.add_picture(tmp_path, 0, 0, width=prs.slide_width)
        except: pass
        os.remove(tmp_path)

    # 2. Altre Slide
    for slide_data in plan['slides']:
        if slide_data['layout'] == 'Cover_Main': continue 
        l_name = slide_data.get("layout", "Intro_Concept")
        if l_name in layout_map:
            s = prs.slides.add_slide(layout_map[l_name])
            if s.shapes.title: s.shapes.title.text = slide_data.get("title", "")
            for shape in s.placeholders:
                if shape.placeholder_format.idx == 1:
                    shape.text = slide_data.get("body", "")

    # 3. Slide Fisse
    fixed = ["Standard_Training", "Standard_Extras", "Standard_Payment", "Closing_Contact"]
    for f in fixed:
        if f in layout_map: prs.slides.add_slide(layout_map[f])

    return prs

# --- INTERFACCIA PRINCIPALE ---

st.title("🤖 Grimmy PPT Agent")
st.markdown("### Area di Lavoro")

if "step" not in st.session_state: st.session_state.step = 1
if "data" not in st.session_state: st.session_state.data = {}

# STEP 1: UPLOAD SOURCE
if st.session_state.step == 1:
    
    st.info("Trascina qui sotto il file PowerPoint vecchio da convertire. Assicurati di aver caricato il Template nella barra laterale a sinistra.")
    
    source = st.file_uploader("Drop Zone: Vecchio PPT (.pptx)", type=["pptx"])
    
    st.write("")
    st.write("")
    
    if st.button("🚀 Chiedi a Grimmy di lavorare", type="primary"):
        if not template:
            st.error("🛑 Aspetta! Non hai caricato il TEMPLATE nella barra laterale sinistra.")
        elif not source:
            st.error("🛑 Non hai caricato nessun file da convertire qui sopra.")
        else:
            with st.spinner("Grimmy sta leggendo il file e NanoBanana sta scaldando i pennelli..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as t:
                    t.write(template.getvalue())
                    st.session_state.data['tpl_path'] = t.name
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as s:
                    s.write(source.getvalue())
                    st.session_state.data['src_path'] = s.name

                txt, orig_img = extract_content(st.session_state.data['src_path'])
                st.session_state.data['orig_img'] = orig_img
                
                plan = get_gemini_plan_and_prompts(txt, selected_text_model)
                st.session_state.data['plan'] = plan
                
                if plan:
                    st.info(f"NanoBanana sta dipingendo con il modello: {selected_image_model}...")
                    img_a = generate_imagen_image(plan['cover_prompt_a'], selected_image_model)
                    img_b = generate_imagen_image(plan['cover_prompt_b'], selected_image_model)
                    
                    st.session_state.data['img_a'] = img_a
                    st.session_state.data['img_b'] = img_b
                
                st.session_state.step = 2
                st.rerun()

# STEP 2: SELEZIONE E DOWNLOAD
elif st.session_state.step == 2:
    st.subheader("🎨 Scegli la Cover creata da NanoBanana")
    st.markdown("Grimmy ha preparato il contenuto. Ora tocca a te scegliere il volto della presentazione.")
    
    col1, col2, col3 = st.columns(3)
    selection = None
    
    with col1:
        st.markdown("**Originale**")
        if st.session_state.data.get('orig_img'):
            st.image(st.session_state.data['orig_img'], use_container_width=True)
            if st.button("Usa Originale"): selection = "orig"
        else: st.info("Nessuna immagine originale")

    with col2:
        st.markdown("**Stile Corporate**")
        if st.session_state.data.get('img_a'):
            st.image(st.session_state.data['img_a'], use_container_width=True)
            if st.button("Scegli Corporate"): selection = "A"
        else: st.warning("Errore generazione")

    with col3:
        st.markdown("**Stile Creativo**")
        if st.session_state.data.get('img_b'):
            st.image(st.session_state.data['img_b'], use_container_width=True)
            if st.button("Scegli Creativo"): selection = "B"

    if selection:
        final_img = None
        if selection == "orig": final_img = st.session_state.data.get('orig_img')
        elif selection == "A": final_img = st.session_state.data.get('img_a')
        elif selection == "B": final_img = st.session_state.data.get('img_b')
        
        with st.spinner("Grimmy sta assemblando il PPT finale..."):
            new_prs = create_final_pptx(
                st.session_state.data['plan'], 
                final_img, 
                st.session_state.data['tpl_path']
            )
            
            output_name = "PRESENTAZIONE_GRIMMY.pptx"
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pptx') as tmp_out:
                new_prs.save(tmp_out.name)
                with open(tmp_out.name, "rb") as f:
                    st.success("✅ Lavoro completato!")
                    st.download_button("📥 SCARICA PPTX", f, output_name, type="primary")
        
        st.write("")
        if st.button("🔄 Ricomincia con un altro file"):
            st.session_state.step = 1
            st.rerun()
