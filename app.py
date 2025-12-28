import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import storage
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from pptx import Presentation
import json
import os
import time
import uuid

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Slide Monster: GOD MODE (Gemini 3)", page_icon="⚡", layout="wide")

# ======================================================
# ⚙️ I TUOI DATI
# ======================================================
GCP_PROJECT_ID = "gen-lang-client-0247086002"
GCS_BUCKET_NAME = "bucket_grimmy"
GCP_LOCATION = "us-central1"
# ======================================================

DEFAULT_TEMPLATE_ID = "1BHac-ciWsMCxjtNrv8RxB68LyDi9cZrV6VMWEeXCw5A" 
DEFAULT_FOLDER_ID = "1wL1oxos7ISS03GzfW0db44XoAk3UocV0"

# --- GESTIONE STATO ---
if "app_state" not in st.session_state: st.session_state.app_state = "UPLOAD"
if "draft_data" not in st.session_state: st.session_state.draft_data = {}
if "final_images" not in st.session_state: st.session_state.final_images = {} 

# --- INIZIALIZZAZIONE ---
try:
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        service_account_info = json.loads(st.secrets["gcp_service_account"]["json_content"])
    else:
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
    # PERMESSI COMPLETI (Scope corretti)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=[
            'https://www.googleapis.com/auth/cloud-platform',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/presentations'
        ]
    )

    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"]) 
    drive_service = build('drive', 'v3', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)
    
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION, credentials=creds)
    storage_client = storage.Client(credentials=creds, project=GCP_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)

except Exception as e:
    st.error(f"⚠️ Errore Inizializzazione: {e}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚡ Slide Monster")
    
    st.subheader("🧠 Cervello")
    # FORZIAMO GEMINI 3 PRO PREVIEW COME DEFAULT ASSOLUTO
    # Se il modello non è nella lista automatica, lo aggiungiamo manualmente.
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except:
        available_models = []

    # Nome tecnico ufficiale di Gemini 3
    target_model = "models/gemini-3-pro-preview" 
    
    # Se non c'è nella lista (perché è preview nascosta), lo aggiungiamo in cima
    if target_model not in available_models:
        available_models.insert(0, target_model)
    else:
        # Se c'è, lo spostiamo in cima per renderlo default
        available_models.remove(target_model)
        available_models.insert(0, target_model)

    # Menu a tendina con Gemini 3 pre-selezionato
    selected_gemini = st.selectbox("Modello Attivo:", available_models, index=0)
    
    st.caption(f"ID: `{selected_gemini}`")

    st.subheader("🎨 Artista")
    st.caption("Motore: **Imagen 3 (High Fidelity)**")
    
    image_styles = [
        "Fotorealistico (High Fidelity)", 
        "Cinematico (Film Look)", 
        "Digital Art (Moderno)", 
        "Illustrazione 3D (Pixar Style)"
    ]
    selected_style = st.selectbox("Stile Visivo:", image_styles, index=0)
    
    st.divider()
    if st.button("🔄 Reset"):
        st.session_state.app_state = "UPLOAD"
        st.session_state.draft_data = {}
        st.session_state.final_images = {}
        st.rerun()

# --- FUNZIONI CORE ---

def extract_text_from_pptx(file_obj):
    prs = Presentation(file_obj)
    full_text = []
    for slide in prs.slides:
        s_txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                s_txt.append(shape.text.strip())
        full_text.append(" | ".join(s_txt))
    return "\n---\n".join(full_text)

def brain_process(text, model_name, style_choice):
    
    style_instruction = "Photorealistic, highly detailed, 8k resolution"
    if "Digital Art" in style_choice:
        style_instruction = "Digital art, vibrant colors, modern corporate style"
    elif "Illustrazione 3D" in style_choice:
        style_instruction = "3D render, cute, clay style, bright lighting"
    elif "Cinematico" in style_choice:
        style_instruction = "Cinematic shot, dramatic lighting, movie scene"

    prompt = f"""
    Sei un Creative Director esperto. 
    Analizza il testo fornito e struttura una presentazione efficace.
    
    OUTPUT RICHIESTO (JSON):
    {{
        "cover": {{ "title": "Titolo Accattivante", "subtitle": "Slogan", "image_prompt": "Descrizione visiva dettagliata in INGLESE per la copertina" }},
        "slides": [
            {{ "id": 1, "title": "Titolo Slide 1", "body": "Contenuto sintetico (max 30 parole)", "image_prompt": "Descrizione visiva in INGLESE" }},
            {{ "id": 2, "title": "Titolo Slide 2", "body": "Contenuto sintetico", "image_prompt": "Descrizione visiva in INGLESE" }},
            {{ "id": 3, "title": "Titolo Slide 3", "body": "Contenuto sintetico", "image_prompt": "Descrizione visiva in INGLESE" }},
            {{ "id": 4, "title": "Titolo Slide 4", "body": "Contenuto sintetico", "image_prompt": "Descrizione visiva in INGLESE" }},
            {{ "id": 5, "title": "Titolo Slide 5", "body": "Contenuto sintetico", "image_prompt": "Descrizione visiva in INGLESE" }}
        ]
    }}
    
    NOTA SUI PROMPT IMMAGINI: Usa lo stile: {style_instruction}.
    """
    
    model = genai.GenerativeModel(model_name)
    try:
        # Configurazione per output JSON
        resp = model.generate_content(
            f"{prompt}\n\nTESTO SORGENTE:\n{text}", 
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(resp.text)
    except Exception as e:
        st.error(f"Errore Gemini ({model_name}): {e}")
        return None

def generate_and_upload_imagen(prompt):
    try:
        # Imagen 3 è la scelta solida
        model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
        
        images = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            language="en",
            aspect_ratio="16:9",
            safety_filter_level="block_some",
            person_generation="allow_adult"
        )
        
        if not images: return None, "Nessuna immagine generata."
        
        filename = f"img_{uuid.uuid4()}.png"
        blob = bucket.blob(filename)
        blob.upload_from_string(images[0]._image_bytes, content_type="image/png")
        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
        
        return public_url, None
        
    except Exception as e:
        return None, str(e)

def find_image_element_id_smart(prs_id, label):
    label_clean = label.strip().upper()
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if 'description' in el and el['description'].strip().upper() == label_clean:
                    return el['objectId']
    except Exception as e:
        print(f"Errore ricerca ID: {e}")
    return None

def worker_bot_finalize(template_id, folder_id, filename, ai_data, urls_map):
    try:
        # 1. COPIA FILE (Ora funziona se hai abilitato Drive API)
        copy = drive_service.files().copy(
            fileId=template_id, 
            body={'name': filename, 'parents': [folder_id]}, 
            supportsAllDrives=True
        ).execute()
        new_id = copy.get('id')
        
        # 2. TESTI
        reqs = []
        if 'cover' in ai_data:
            reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover'].get('subtitle', '')}})
        
        if 'slides' in ai_data:
            for i, s in enumerate(ai_data['slides']):
                idx = i + 1
                reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s.get('title', '')}})
                reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s.get('body', '')}})
                
        if reqs:
            slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()

        # 3. IMMAGINI
        for label, url in urls_map.items():
            if url:
                el_id = find_image_element_id_smart(new_id, label)
                if el_id:
                    req = {'replaceImage': {'imageObjectId': el_id, 'imageReplaceMethod': 'CENTER_CROP', 'url': url}}
                    try:
                        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': [req]}).execute()
                        time.sleep(0.5) 
                    except Exception as e:
                        print(f"Errore immagine {label}: {e}")
        
        return new_id
    except Exception as e:
        st.error(f"Errore finale Worker: {e}")
        return None

# ==========================================
# INTERFACCIA UTENTE
# ==========================================

st.title("⚡ Slide Monster: GOD MODE")

col1, col2 = st.columns([1, 2])
with col1:
    st.info("Configurazione Attiva")
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella Output", value=DEFAULT_FOLDER_ID)

# --- FASE 1: UPLOAD & ANALISI ---
if st.session_state.app_state == "UPLOAD":
    with col2:
        st.write("### 1. Carica i file")
        uploaded = st.file_uploader("Trascina qui i PPTX", accept_multiple_files=True, type=['pptx'])
        
        if st.button("🧠 Analizza (Gemini 3 Pro)", type="primary"):
            if uploaded:
                st.session_state.draft_data = {}
                st.session_state.final_images = {}
                
                bar = st.progress(0)
                for i, f in enumerate(uploaded):
                    fname = f.name.replace(".pptx", "") + "_ITA"
                    txt = extract_text_from_pptx(f)
                    
                    data = brain_process(txt, selected_gemini, selected_style)
                    
                    if data:
                        st.session_state.draft_data[fname] = {"ai_data": data, "original_file": f.name}
                        st.session_state.final_images[fname] = {} 
                    
                    bar.progress((i+1)/len(uploaded))
                
                st.session_state.app_state = "EDIT"
                st.rerun()

# --- FASE 2: SALA DI REGIA ---
elif st.session_state.app_state == "EDIT":
    st.divider()
    st.write("### 2. Sala di Regia")
    st.caption(f"Cervello: {selected_gemini} | Artista: Imagen 3")

    for fname, content in st.session_state.draft_data.items():
        data = content['ai_data']
        
        with st.expander(f"📂 Progetto: **{fname}**", expanded=True):
            
            # === COPERTINA ===
            st.markdown("#### Copertina")
            c1, c2 = st.columns([2, 1])
            with c1:
                st.write(f"**Titolo:** {data['cover'].get('title')}")
                p_cov = st.text_area("Prompt Cover", value=data['cover'].get('image_prompt', ''), height=100, key=f"p_c_{fname}")
                st.session_state.draft_data[fname]['ai_data']['cover']['image_prompt'] = p_cov
                
                if st.button("✨ Genera Cover", key=f"b_c_{fname}"):
                    with st.spinner("Generazione..."):
                        url, err = generate_and_upload_imagen(p_cov)
                        if url: 
                            st.session_state.final_images[fname]['cover'] = url
                            st.rerun()
                        else: st.error(f"Errore: {err}")
            
            with c2:
                url = st.session_state.final_images[fname].get('cover')
                if url: 
                    st.image(url, use_container_width=True)
                    st.success("OK")
                else:
                    st.warning("Da generare")

            # === SLIDE INTERNE ===
            if 'slides' in data:
                st.markdown("---")
                st.markdown("#### Slide Interne")
                for idx, slide in enumerate(data['slides']):
                    st.caption(f"Slide {idx+1}")
                    sc1, sc2 = st.columns([2, 1])
                    
                    with sc1:
                        st.write(f"**{slide.get('title')}**")
                        p_sl = st.text_area("Prompt", value=slide.get('image_prompt', ''), height=80, key=f"p_s_{idx}_{fname}")
                        st.session_state.draft_data[fname]['ai_data']['slides'][idx]['image_prompt'] = p_sl
                        
                        if st.button(f"✨ Genera Slide {idx+1}", key=f"b_s_{idx}_{fname}"):
                            with st.spinner("Generazione..."):
                                url, err = generate_and_upload_imagen(p_sl)
                                if url:
                                    st.session_state.final_images[fname][f"slide_{idx+1}"] = url
                                    st.rerun()
                                else: st.error(err)
                    
                    with sc2:
                        url = st.session_state.final_images[fname].get(f"slide_{idx+1}")
                        if url: st.image(url, use_container_width=True)

    # --- FOOTER ---
    st.divider()
    col_back, col_save = st.columns([1, 4])
    with col_back:
        if st.button("⬅️ Indietro"):
            st.session_state.app_state = "UPLOAD"
            st.rerun()
    
    with col_save:
        if st.button("💾 SALVA TUTTO SU DRIVE", type="primary", use_container_width=True):
            progress_bar = st.progress(0)
            msg_box = st.empty()
            
            i = 0
            for fname, content in st.session_state.draft_data.items():
                msg_box.write(f"Scrittura file **{fname}**...")
                
                url_map = {}
                saved_imgs = st.session_state.final_images.get(fname, {})
                if 'cover' in saved_imgs: url_map['IMG_COVER'] = saved_imgs['cover']
                for k, v in saved_imgs.items():
                    if k.startswith("slide_"): 
                        num = k.split("_")[1]
                        url_map[f"IMG_{num}"] = v
                
                res_id = worker_bot_finalize(tmpl, fold, fname, content['ai_data'], url_map)
                
                if res_id: st.toast(f"✅ Creato: {fname}")
                else: st.error(f"❌ Fallito: {fname}")
                i+=1
                progress_bar.progress(i/len(st.session_state.draft_data))
                
            st.success("Tutte le presentazioni sono state create!")
            st.balloons()
