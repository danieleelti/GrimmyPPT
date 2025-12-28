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
# ⚙️ RECUPERO DATI DA SECRETS
# ======================================================
if "slides_config" in st.secrets:
    DEF_TEMPLATE_ID = st.secrets["slides_config"]["template_id"]
    DEF_FOLDER_ID = st.secrets["slides_config"]["folder_id"]
else:
    DEF_TEMPLATE_ID = ""
    DEF_FOLDER_ID = ""

GCP_PROJECT_ID = "gen-lang-client-0247086002"
GCS_BUCKET_NAME = "bucket_grimmy"
GCP_LOCATION = "us-central1"

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

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.header("⚡ Slide Monster")
    
    with st.expander("⚙️ Configurazione Drive", expanded=True):
        tmpl = st.text_input("ID Template PPT", value=DEF_TEMPLATE_ID)
        fold = st.text_input("ID Cartella Output", value=DEF_FOLDER_ID)
        make_english = st.checkbox("🇬🇧 Genera anche versione Inglese", value=True)

    st.divider()

    st.subheader("🧠 Cervello")
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except: available_models = []
    
    target_model = "models/gemini-3-pro-preview" 
    if target_model not in available_models:
        available_models.insert(0, target_model)
    else:
        available_models.remove(target_model)
        available_models.insert(0, target_model)

    selected_gemini = st.selectbox("Modello:", available_models, index=0)

    st.subheader("🎨 Artista")
    image_styles = ["Fotorealistico", "Cinematico", "Digital Art", "Illustrazione 3D"]
    selected_style = st.selectbox("Stile:", image_styles, index=0)
    
    st.divider()
    if st.button("🔄 Reset Totale", type="secondary", use_container_width=True):
        st.session_state.app_state = "UPLOAD"
        st.session_state.draft_data = {}
        st.session_state.final_images = {}
        st.session_state.original_images = {}
        st.rerun()

# --- FUNZIONI CORE ---

def get_all_images_from_shapes(shapes):
    """Raccoglie tutte le immagini e le loro dimensioni"""
    images_found = [] 
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            area = shape.width * shape.height
            images_found.append((area, shape.image.blob))
        elif shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for s in shape.shapes:
                if s.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    area = s.width * s.height
                    images_found.append((area, s.image.blob))
    return images_found

def analyze_pptx_content(file_obj):
    """
    Estrae testo VISIBILE e NOTE DEL RELATORE.
    Estrae immagini con logica Torneo Globale.
    """
    prs = Presentation(file_obj)
    full_text = []
    extracted_images = {} 

    for i, slide in enumerate(prs.slides):
        # 1. TESTO VISIBILE
        s_txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                s_txt.append(shape.text.strip())
        
        visible_text = " | ".join(s_txt)

        # 2. NOTE DEL RELATORE (Nuova Funzione!)
        notes_text = ""
        if slide.has_notes_slide:
            try:
                notes_slide = slide.notes_slide
                if notes_slide.notes_text_frame:
                    notes_content = notes_slide.notes_text_frame.text.strip()
                    if notes_content:
                        notes_text = f"\n[[ ISTRUZIONI DALLE NOTE: {notes_content} ]]"
            except:
                pass # Se fallisce l'estrazione note, ignora
        
        # Uniamo tutto nel pacchetto per Gemini
        full_text.append(f"SLIDE {i+1} CONTENUTO: {visible_text} {notes_text}")

        # 3. IMMAGINI (Torneo Globale)
        candidates = []
        candidates.extend(get_all_images_from_shapes(slide.shapes))
        if slide.slide_layout:
            candidates.extend(get_all_images_from_shapes(slide.slide_layout.shapes))
        if slide.slide_layout and slide.slide_layout.slide_master:
            candidates.extend(get_all_images_from_shapes(slide.slide_layout.slide_master.shapes))
        
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            extracted_images[i] = candidates[0][1]
    
    return "\n---\n".join(full_text), extracted_images

def brain_process(text, model_name, style_choice):
    style_instruction = "Photorealistic, highly detailed, 8k resolution"
    if "Digital Art" in style_choice: style_instruction = "Digital art, vibrant colors"
    elif "Illustrazione 3D" in style_choice: style_instruction = "3D render, cute, clay style"
    elif "Cinematico" in style_choice: style_instruction = "Cinematic shot, dramatic lighting"

    # PROMPT AGGIORNATO PER LE NOTE
    prompt = f"""
    Sei un Creative Director esperto.
    Analizza il testo fornito. Troverai sia il testo visibile che le "ISTRUZIONI DALLE NOTE".
    
    ⚠️ REGOLE CRUCIALI:
    1. **Usa le NOTE come fonte primaria di verità**: Se nelle note c'è scritto cosa dire o come strutturare la slide, segui quelle istruzioni alla lettera per generare il campo 'body'.
    2. Lingua Testi: **ITALIANO**.
    3. Lingua Prompt Immagini: **INGLESE**.
    
    OUTPUT RICHIESTO (JSON):
    {{
        "cover": {{ "title": "Titolo ITA", "subtitle": "Slogan ITA", "image_prompt": "Prompt ENG" }},
        "slides": [
            {{ "id": 1, "title": "Titolo ITA", "body": "Testo ITA basato sulle NOTE se presenti (max 30 parole)", "image_prompt": "Prompt ENG" }},
            {{ "id": 2, "title": "Titolo ITA", "body": "Testo ITA basato sulle NOTE", "image_prompt": "Prompt ENG" }},
            {{ "id": 3, "title": "Titolo ITA", "body": "Testo ITA basato sulle NOTE", "image_prompt": "Prompt ENG" }},
            {{ "id": 4, "title": "Titolo ITA", "body": "Testo ITA basato sulle NOTE", "image_prompt": "Prompt ENG" }},
            {{ "id": 5, "title": "Titolo ITA", "body": "Testo ITA basato sulle NOTE", "image_prompt": "Prompt ENG" }}
        ]
    }}
    Style: {style_instruction}.
    """
    model = genai.GenerativeModel(model_name)
    try:
        resp = model.generate_content(f"{prompt}\n\nTESTO SORGENTE:\n{text}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        st.error(f"Errore Gemini: {e}")
        return None

def translate_struct_to_english(ai_data):
    """Traduce la struttura dati in Inglese (chiavi e prompt esclusi)"""
    prompt = """
    You are a professional translator. Translate the values in the following JSON from Italian to English.
    Do NOT translate the keys. Do NOT translate 'image_prompt'.
    Return ONLY the valid JSON.
    """
    model = genai.GenerativeModel("models/gemini-1.5-pro") 
    try:
        resp = model.generate_content(f"{prompt}\n\nJSON:\n{json.dumps(ai_data)}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        print(f"Errore Traduzione Struct: {e}")
        return ai_data

def get_template_static_text(presentation_id):
    """Estrae testo statico dalla presentazione"""
    try:
        prs = slides_service.presentations().get(presentationId=presentation_id).execute()
        texts_to_translate = set()
        
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if 'shape' in el and 'text' in el['shape']:
                    for tr in el['shape']['text']['textElements']:
                        if 'textRun' in tr and 'content' in tr['textRun']:
                            content = tr['textRun']['content'].strip()
                            if content and "{{" not in content and "}}" not in content and len(content) > 2:
                                texts_to_translate.add(content)
        return list(texts_to_translate)
    except Exception as e:
        print(f"Errore estrazione testo statico: {e}")
        return []

def translate_list_strings(text_list):
    """Traduce una lista di stringhe"""
    if not text_list: return {}
    
    prompt = """
    You are a professional translator. Translate the following list of Italian strings into English.
    Output a JSON object where keys are the original Italian strings and values are the English translations.
    """
    model = genai.GenerativeModel("models/gemini-1.5-pro")
    try:
        resp = model.generate_content(f"{prompt}\n\nLIST:\n{json.dumps(text_list)}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        print(f"Errore Traduzione Lista: {e}")
        return {}

def apply_static_translations(presentation_id, translation_map):
    if not translation_map: return
    reqs = []
    for it_text, en_text in translation_map.items():
        if it_text and en_text and it_text != en_text:
            reqs.append({
                'replaceAllText': {
                    'containsText': {'text': it_text, 'matchCase': True},
                    'replaceText': en_text
                }
            })
    if reqs:
        chunk_size = 50
        for i in range(0, len(reqs), chunk_size):
            chunk = reqs[i:i + chunk_size]
            try:
                slides_service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': chunk}).execute()
                time.sleep(0.5)
            except Exception as e:
                print(f"Errore batch traduzione: {e}")

# ------------------------------------

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

def worker_bot_finalize(template_id, folder_id, filename, ai_data, urls_map, translate_mode=False):
    try:
        copy = drive_service.files().copy(
            fileId=template_id, body={'name': filename, 'parents': [folder_id]}, supportsAllDrives=True
        ).execute()
        new_id = copy.get('id')
        
        final_data = ai_data
        if translate_mode:
            st.toast(f"🇬🇧 Traduzione dinamica: {filename}")
            final_data = translate_struct_to_english(ai_data)
            
            st.toast(f"🇬🇧 Traduzione statica: {filename}")
            static_texts = get_template_static_text(new_id)
            if static_texts:
                translation_map = translate_list_strings(static_texts)
                apply_static_translations(new_id, translation_map)
        
        reqs = []
        if 'cover' in final_data:
            reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': final_data['cover'].get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': final_data['cover'].get('subtitle', '')}})
        
        if 'slides' in final_data:
            for i, s in enumerate(final_data['slides']):
                idx = i + 1
                reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s.get('title', '')}})
                reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s.get('body', '')}})
                
        if reqs:
            slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()

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
    except Exception as e: 
        print(f"Error Worker: {e}")
        return None

# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("⚡ Slide Monster: GOD MODE")

# --- FASE 1: UPLOAD ---
if st.session_state.app_state == "UPLOAD":
    st.markdown("### 1. Carica le presentazioni")
    
    with st.container(border=True):
        uploaded = st.file_uploader("Trascina qui i tuoi file PPTX", accept_multiple_files=True, type=['pptx'])
        
        col_act1, col_act2 = st.columns([1, 4])
        with col_act1:
            if st.button("🧠 ANALIZZA", type="primary", use_container_width=True):
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
        with col_act2:
            st.caption("Analisi: Legge Slide, Master (Immagini) e **NOTE DEL RELATORE** per il testo.")

# --- FASE 2: EDITING ---
elif st.session_state.app_state == "EDIT":
    
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.info("✏️ **Sala di Regia**: Controlla i testi (ITA). Se nelle Note del PPT originale c'erano istruzioni, sono state usate.")
    with col_h2:
        if st.button("💾 SALVA TUTTO SU DRIVE", type="primary", use_container_width=True):
            bar = st.progress(0)
            total_ops = len(st.session_state.draft_data)
            
            for i, (fname, content) in enumerate(st.session_state.draft_data.items()):
                url_map = {}
                saved = st.session_state.final_images.get(fname, {})
                if 'cover' in saved: url_map['IMG_COVER'] = saved['cover']
                for k, v in saved.items():
                    if k.startswith("slide_"): url_map[f"IMG_{k.split('_')[1]}"] = v
                
                # 1. ITA
                st.toast(f"🇮🇹 Creazione ITA: {fname}")
                res_ita = worker_bot_finalize(tmpl, fold, fname, content['ai_data'], url_map, translate_mode=False)
                
                # 2. ENG (Se attivo)
                if make_english:
                    fname_eng = fname.replace("_ITA", "_ENG")
                    st.toast(f"🇬🇧 Creazione ENG: {fname_eng}")
                    res_eng = worker_bot_finalize(tmpl, fold, fname_eng, content['ai_data'], url_map, translate_mode=True)

                if res_ita: st.success(f"✅ Salvato: {fname}")
                else: st.error(f"❌ Errore: {fname}")
                
                bar.progress((i+1)/total_ops)
            
            st.balloons()
            time.sleep(2)

    for fname, content in st.session_state.draft_data.items():
        data = content['ai_data']
        orig_imgs = st.session_state.original_images.get(fname, {})
        
        st.markdown(f"## 📂 {fname}")
        
        tab_labels = ["🏠 Copertina"] + [f"📄 Slide {i+1}" for i in range(len(data.get('slides', [])))]
        tabs = st.tabs(tab_labels)
        
        # TAB 0: COPERTINA
        with tabs[0]:
            st.markdown("### 📝 Contenuti Testuali")
            new_t = st.text_input("Titolo Copertina", value=data['cover'].get('title', ''), key=f"t_c_{fname}")
            new_s = st.text_input("Sottotitolo", value=data['cover'].get('subtitle', ''), key=f"s_c_{fname}")
            st.session_state.draft_data[fname]['ai_data']['cover']['title'] = new_t
            st.session_state.draft_data[fname]['ai_data']['cover']['subtitle'] = new_s

            st.markdown("---")
            col_ai, col_orig = st.columns([1, 1], gap="large")
            with col_ai:
                st.markdown("#### 🤖 Laboratorio AI")
                p_cov = st.text_area("Prompt Imagen", value=data['cover'].get('image_prompt', ''), height=100, key=f"p_c_{fname}")
                if st.button("✨ Genera Immagine (AI)", key=f"b_gen_c_{fname}", use_container_width=True):
                    with st.spinner("Generazione..."):
                        img_bytes = generate_imagen_safe(p_cov)
                        if img_bytes:
                            url = upload_bytes_to_bucket(img_bytes)
                            st.session_state.final_images[fname]['cover'] = url
                            st.rerun()
                curr_url = st.session_state.final_images[fname].get('cover')
                if curr_url:
                    st.image(curr_url, caption="Immagine Attiva", use_container_width=True)
                    st.success("✅ Questa immagine verrà usata")

            with col_orig:
                st.markdown("#### 🖼️ Originale PPT")
                orig_bytes = orig_imgs.get(0)
                if orig_bytes:
                    st.image(orig_bytes, caption="Estratta dal PPT (la più grande)", use_container_width=True)
                    if st.button("Usa questa Originale", key=f"b_orig_c_{fname}", use_container_width=True):
                        url = upload_bytes_to_bucket(orig_bytes)
                        st.session_state.final_images[fname]['cover'] = url
                        st.rerun()
                else: st.warning("Nessuna immagine trovata.")

        # TAB SLIDES
        if 'slides' in data:
            for idx, slide in enumerate(data['slides']):
                with tabs[idx+1]:
                    st.markdown("### 📝 Contenuti Testuali")
                    new_st = st.text_input(f"Titolo Slide {idx+1}", value=slide.get('title', ''), key=f"t_s_{idx}_{fname}")
                    new_sb = st.text_area(f"Corpo del testo", value=slide.get('body', ''), height=150, key=f"b_s_{idx}_{fname}")
                    st.session_state.draft_data[fname]['ai_data']['slides'][idx]['title'] = new_st
                    st.session_state.draft_data[fname]['ai_data']['slides'][idx]['body'] = new_sb

                    st.markdown("---")
                    col_ai, col_orig = st.columns([1, 1], gap="large")
                    with col_ai:
                        st.markdown("#### 🤖 Laboratorio AI")
                        p_sl = st.text_area("Prompt Imagen", value=slide.get('image_prompt', ''), height=100, key=f"p_p_{idx}_{fname}")
                        if st.button(f"✨ Genera Immagine (AI)", key=f"btn_ai_{idx}_{fname}", use_container_width=True):
                            with st.spinner("Generazione..."):
                                img_bytes = generate_imagen_safe(p_sl)
                                if img_bytes:
                                    url = upload_bytes_to_bucket(img_bytes)
                                    st.session_state.final_images[fname][f"slide_{idx+1}"] = url
                                    st.rerun()
                        curr_url_sl = st.session_state.final_images[fname].get(f"slide_{idx+1}")
                        if curr_url_sl:
                            st.image(curr_url_sl, caption="Immagine Attiva", use_container_width=True)
                            st.success("✅ Questa immagine verrà usata")

                    with col_orig:
                        st.markdown("#### 🖼️ Originale PPT")
                        orig_bytes_sl = orig_imgs.get(idx + 1)
                        if orig_bytes_sl:
                            st.image(orig_bytes_sl, caption="Estratta dal PPT", use_container_width=True)
                            if st.button(f"Usa questa Originale", key=f"btn_org_{idx}_{fname}", use_container_width=True):
                                url = upload_bytes_to_bucket(orig_bytes_sl)
                                st.session_state.final_images[fname][f"slide_{idx+1}"] = url
                                st.rerun()
                        else: st.warning("Nessuna immagine trovata.")
        st.markdown("---")
