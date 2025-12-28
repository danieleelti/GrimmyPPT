import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import storage
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
import json
import os
import time
import uuid
import io

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Slide Monster: GOD MODE", page_icon="⚡", layout="wide")

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
if "original_images" not in st.session_state: st.session_state.original_images = {} 

# --- INIZIALIZZAZIONE ---
try:
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        service_account_info = json.loads(st.secrets["gcp_service_account"]["json_content"])
    else:
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
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
    # FORZATURA GEMINI 3 PRO PREVIEW
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except: available_models = []
    
    target_model = "models/gemini-3-pro-preview" 
    
    if target_model not in available_models:
        available_models.insert(0, target_model)
    else:
        available_models.remove(target_model)
        available_models.insert(0, target_model)

    selected_gemini = st.selectbox("Modello Attivo:", available_models, index=0)
    st.caption("Default: 3 Pro Preview")

    st.subheader("🎨 Artista")
    image_styles = ["Fotorealistico", "Cinematico", "Digital Art", "Illustrazione 3D"]
    selected_style = st.selectbox("Stile:", image_styles, index=0)
    
    st.divider()
    if st.button("🔄 Reset"):
        st.session_state.app_state = "UPLOAD"
        st.session_state.draft_data = {}
        st.session_state.final_images = {}
        st.session_state.original_images = {}
        st.rerun()

# --- FUNZIONI CORE ---

def analyze_pptx_content(file_obj):
    """Estrae testo e immagini originali dal PPTX"""
    prs = Presentation(file_obj)
    full_text = []
    extracted_images = {} 

    for i, slide in enumerate(prs.slides):
        s_txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                s_txt.append(shape.text.strip())
            
            # Estrazione Immagini
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                if i not in extracted_images: 
                    extracted_images[i] = shape.image.blob

        full_text.append(" | ".join(s_txt))
    
    return "\n---\n".join(full_text), extracted_images

def brain_process(text, model_name, style_choice):
    style_instruction = "Photorealistic, highly detailed, 8k resolution"
    if "Digital Art" in style_choice: style_instruction = "Digital art, vibrant colors"
    elif "Illustrazione 3D" in style_choice: style_instruction = "3D render, cute, clay style"
    elif "Cinematico" in style_choice: style_instruction = "Cinematic shot, dramatic lighting"

    prompt = f"""
    Sei un Creative Director. Analizza il testo e struttura una presentazione.
    OUTPUT JSON:
    {{
        "cover": {{ "title": "Titolo", "subtitle": "Slogan", "image_prompt": "Descrizione visiva INGLESE" }},
        "slides": [
            {{ "id": 1, "title": "Titolo", "body": "Testo (max 30 parole)", "image_prompt": "Descrizione visiva INGLESE" }},
            {{ "id": 2, "title": "Titolo", "body": "Testo", "image_prompt": "Descrizione visiva INGLESE" }},
            {{ "id": 3, "title": "Titolo", "body": "Testo", "image_prompt": "Descrizione visiva INGLESE" }},
            {{ "id": 4, "title": "Titolo", "body": "Testo", "image_prompt": "Descrizione visiva INGLESE" }},
            {{ "id": 5, "title": "Titolo", "body": "Testo", "image_prompt": "Descrizione visiva INGLESE" }}
        ]
    }}
    Style: {style_instruction}.
    """
    model = genai.GenerativeModel(model_name)
    try:
        resp = model.generate_content(f"{prompt}\n\nTESTO:\n{text}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        st.error(f"Errore Gemini: {e}")
        return None

def upload_bytes_to_bucket(image_bytes):
    try:
        filename = f"img_{uuid.uuid4()}.png"
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type="image/png")
        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
    except Exception as e:
        st.error(f"Errore Upload Bucket: {e}")
        return None

def generate_imagen_safe(prompt):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
            images = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio="16:9", person_generation="allow_adult")
            if images: return images[0]._image_bytes
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                wait = 10 * (attempt + 1)
                st.warning(f"🚦 Quota raggiunta. Attendo {wait}s... ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                st.error(f"Errore Imagen: {e}")
                return None
    return None

def find_image_element_id_smart(prs_id, label):
    label_clean = label.strip().upper()
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if 'description' in el and el['description'].strip().upper() == label_clean:
                    return el['objectId']
    except: pass
    return None

def worker_bot_finalize(template_id, folder_id, filename, ai_data, urls_map):
    try:
        copy = drive_service.files().copy(
            fileId=template_id, body={'name': filename, 'parents': [folder_id]}, supportsAllDrives=True
        ).execute()
        new_id = copy.get('id')
        
        reqs = []
        if 'cover' in ai_data:
            reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover'].get('subtitle', '')}})
        
        if 'slides' in ai_data:
            for i, s in enumerate(ai_data['slides']):
                idx = i + 1
                reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s.get('title', '')}})
                reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s.get('body', '')}})
                
        if reqs: slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()

        for label, url in urls_map.items():
            if url:
                el_id = find_image_element_id_smart(new_id, label)
                if el_id:
                    req = {'replaceImage': {'imageObjectId': el_id, 'imageReplaceMethod': 'CENTER_CROP', 'url': url}}
                    try:
                        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': [req]}).execute()
                        time.sleep(0.5) 
                    except: pass
        return new_id
    except Exception as e: return None

# ==========================================
# INTERFACCIA
# ==========================================
st.title("⚡ Slide Monster: GOD MODE")
col1, col2 = st.columns([1, 2])
with col1:
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella", value=DEFAULT_FOLDER_ID)

# --- FASE 1: UPLOAD ---
if st.session_state.app_state == "UPLOAD":
    with col2:
        uploaded = st.file_uploader("PPTX", accept_multiple_files=True, type=['pptx'])
        if st.button("🧠 Analizza", type="primary"):
            if uploaded:
                st.session_state.draft_data = {}
                st.session_state.final_images = {}
                st.session_state.original_images = {}
                
                bar = st.progress(0)
                for i, f in enumerate(uploaded):
                    fname = f.name.replace(".pptx", "") + "_ITA"
                    txt, imgs_dict = analyze_pptx_content(f)
                    
                    data = brain_process(txt, selected_gemini, selected_style)
                    if data:
                        st.session_state.draft_data[fname] = {"ai_data": data}
                        st.session_state.final_images[fname] = {}
                        st.session_state.original_images[fname] = imgs_dict
                    
                    bar.progress((i+1)/len(uploaded))
                st.session_state.app_state = "EDIT"
                st.rerun()

# --- FASE 2: EDITING CON TAB ---
elif st.session_state.app_state == "EDIT":
    st.divider()
    st.info("✏️ Sala di Regia: Naviga tra le pagine con i Tab qui sotto.")

    for fname, content in st.session_state.draft_data.items():
        data = content['ai_data']
        orig_imgs = st.session_state.original_images.get(fname, {})
        
        # Titolo del file
        st.markdown(f"### 📂 File: {fname}")
        
        # --- CREAZIONE TAB ---
        # Creiamo un Tab per la Cover + uno per ogni Slide
        tab_labels = ["🏠 Copertina"] + [f"📄 Slide {i+1}" for i in range(len(data.get('slides', [])))]
        tabs = st.tabs(tab_labels)
        
        # --- TAB 0: COPERTINA ---
        with tabs[0]:
            c1, c2, c3 = st.columns([1, 1, 1])
            
            with c1: # TESTI
                st.markdown("#### 📝 Testi")
                new_t = st.text_input("Titolo Cover", value=data['cover'].get('title', ''), key=f"t_c_{fname}")
                new_s = st.text_input("Sottotitolo Cover", value=data['cover'].get('subtitle', ''), key=f"s_c_{fname}")
                st.session_state.draft_data[fname]['ai_data']['cover']['title'] = new_t
                st.session_state.draft_data[fname]['ai_data']['cover']['subtitle'] = new_s

            with c2: # IMAGEN AI
                st.markdown("#### 🤖 Genera AI")
                p_cov = st.text_area("Prompt AI", value=data['cover'].get('image_prompt', ''), height=80, key=f"p_c_{fname}")
                if st.button("✨ Genera Cover (Imagen)", key=f"b_gen_c_{fname}"):
                    with st.spinner("Generazione..."):
                        img_bytes = generate_imagen_safe(p_cov)
                        if img_bytes:
                            url = upload_bytes_to_bucket(img_bytes)
                            st.session_state.final_images[fname]['cover'] = url
                            st.rerun()

            with c3: # ORIGINALE & PREVIEW
                st.markdown("#### 🖼️ Immagine")
                # Cerchiamo immagine indice 0 (Cover)
                orig_bytes = orig_imgs.get(0) 
                if orig_bytes:
                    st.image(orig_bytes, caption="Originale nel PPT", width=200)
                    if st.button("Usa Originale", key=f"b_orig_c_{fname}"):
                        url = upload_bytes_to_bucket(orig_bytes)
                        st.session_state.final_images[fname]['cover'] = url
                        st.success("Selezionata!")
                        time.sleep(1)
                        st.rerun()
                
                # Check se abbiamo un'immagine finale selezionata
                curr_url = st.session_state.final_images[fname].get('cover')
                if curr_url: 
                    st.success("✅ Immagine pronta per la Cover")
                else:
                    st.warning("⚠️ Manca immagine")

        # --- TAB SLIDES ---
        if 'slides' in data:
            for idx, slide in enumerate(data['slides']):
                # L'indice del tab è idx + 1 perché il tab 0 è la cover
                with tabs[idx+1]:
                    sc1, sc2, sc3 = st.columns([1, 1, 1])
                    
                    with sc1: # TESTI
                        st.markdown("#### 📝 Testi")
                        new_st = st.text_input(f"Titolo Slide {idx+1}", value=slide.get('title', ''), key=f"t_s_{idx}_{fname}")
                        new_sb = st.text_area(f"Body Slide {idx+1}", value=slide.get('body', ''), height=120, key=f"b_s_{idx}_{fname}")
                        st.session_state.draft_data[fname]['ai_data']['slides'][idx]['title'] = new_st
                        st.session_state.draft_data[fname]['ai_data']['slides'][idx]['body'] = new_sb

                    with sc2: # IMAGEN AI
                        st.markdown("#### 🤖 Genera AI")
                        p_sl = st.text_area("Prompt AI", value=slide.get('image_prompt', ''), height=80, key=f"p_p_{idx}_{fname}")
                        if st.button(f"✨ Genera Slide {idx+1}", key=f"btn_ai_{idx}_{fname}"):
                            with st.spinner("Generazione..."):
                                img_bytes = generate_imagen_safe(p_sl)
                                if img_bytes:
                                    url = upload_bytes_to_bucket(img_bytes)
                                    st.session_state.final_images[fname][f"slide_{idx+1}"] = url
                                    st.rerun()

                    with sc3: # ORIGINALE
                        st.markdown("#### 🖼️ Immagine")
                        # Slide 1 (idx 0 nel JSON) corrisponde solitamente all'indice 1 nel PPT originale (0=Cover, 1=Slide1...)
                        orig_bytes_sl = orig_imgs.get(idx + 1) 
                        if orig_bytes_sl:
                            st.image(orig_bytes_sl, caption="Originale nel PPT", width=200)
                            if st.button(f"Usa Originale", key=f"btn_org_{idx}_{fname}"):
                                url = upload_bytes_to_bucket(orig_bytes_sl)
                                st.session_state.final_images[fname][f"slide_{idx+1}"] = url
                                st.success("Selezionata!")
                                time.sleep(0.5)
                                st.rerun()
                                
                        curr_url_sl = st.session_state.final_images[fname].get(f"slide_{idx+1}")
                        if curr_url_sl: st.success(f"✅ Immagine pronta per Slide {idx+1}")
                        else: st.warning("⚠️ Manca immagine")
        
        st.divider()

    # FOOTER
    col_back, col_save = st.columns([1, 4])
    with col_back:
        if st.button("⬅️ Indietro"):
            st.session_state.app_state = "UPLOAD"
            st.rerun()
    with col_save:
        if st.button("💾 SALVA TUTTO SU DRIVE", type="primary", use_container_width=True):
            bar = st.progress(0)
            for i, (fname, content) in enumerate(st.session_state.draft_data.items()):
                url_map = {}
                saved = st.session_state.final_images.get(fname, {})
                if 'cover' in saved: url_map['IMG_COVER'] = saved['cover']
                for k, v in saved.items():
                    if k.startswith("slide_"): url_map[f"IMG_{k.split('_')[1]}"] = v
                
                res = worker_bot_finalize(tmpl, fold, fname, content['ai_data'], url_map)
                if res: st.toast(f"✅ Salvato: {fname}")
                else: st.error(f"❌ Errore: {fname}")
                bar.progress((i+1)/len(st.session_state.draft_data))
            st.balloons()
