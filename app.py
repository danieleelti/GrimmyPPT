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
st.set_page_config(page_title="Slide Monster: FORMAT MODE", page_icon="🏗️", layout="wide")

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
    st.header("🏗️ Slide Monster")
    
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
    Estrae testo (slide + note) e immagini (Torneo Globale).
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

        # 2. NOTE DEL RELATORE
        notes_text = ""
        if slide.has_notes_slide:
            try:
                if slide.notes_slide.notes_text_frame:
                    notes_content = slide.notes_slide.notes_text_frame.text.strip()
                    if notes_content:
                        notes_text = f"\n[[ ISTRUZIONI DALLE NOTE: {notes_content} ]]"
            except: pass
        
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

    # PROMPT SPECIFICO PER LA NUOVA STRUTTURA
    prompt = f"""
    Sei un Creative Director esperto in Team Building.
    Analizza il testo fornito (Slide + Note) ed estrai i contenuti per riempire il nuovo layout a 4 Pagine Dinamiche.
    
    ⚠️ REGOLE LINGUA:
    1. Testi in **ITALIANO**.
    2. Prompt Immagini in **INGLESE**.
    3. Segui le NOTE se presenti.
    
    STRUTTURA RICHIESTA (JSON):
    {{
        "page_1_cover": {{ 
            "title": "Titolo del Format", 
            "image_prompt": "Visual description in English for Cover" 
        }},
        "page_2_desc": {{ 
            "title": "Titolo introduttivo (es. Il Concept)", 
            "body": "Descrizione estesa parte 1 (circa 60 parole)", 
            "image_prompt": "Visual description in English" 
        }},
        "page_3_desc": {{ 
            "title": "Titolo approfondimento (es. La Missione)", 
            "body": "Descrizione estesa parte 2 (circa 60 parole)", 
            "image_prompt": "Visual description in English" 
        }},
        "page_4_details": {{
            "svolgimento": "Descrivi come si svolge l'attività (fasi, dinamiche). Sii schematico.",
            "logistica": "Dettagli logistici (spazi, tempi, partecipanti, indoor/outdoor).",
            "tecnica": "Esigenze tecniche (audio, video, prese elettriche, materiali)."
        }}
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
    """Traduce i valori del JSON in Inglese"""
    prompt = """
    You are a professional translator. Translate the values in the following JSON from Italian to English.
    Do NOT translate the keys. Do NOT translate 'image_prompt'.
    Keep proper names (Format Names) intact.
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
    except: return []

def translate_list_strings(text_list):
    if not text_list: return {}
    prompt = "Translate these Italian strings to English for a corporate presentation. Return JSON {original: translation}."
    model = genai.GenerativeModel("models/gemini-1.5-pro")
    try:
        resp = model.generate_content(f"{prompt}\n\nLIST:\n{json.dumps(text_list)}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except: return {}

def apply_static_translations(presentation_id, translation_map):
    if not translation_map: return
    reqs = []
    for it, en in translation_map.items():
        if it and en and it != en:
            reqs.append({'replaceAllText': {'containsText': {'text': it, 'matchCase': True}, 'replaceText': en}})
    if reqs:
        chunk_size = 50
        for i in range(0, len(reqs), chunk_size):
            try: slides_service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': reqs[i:i+chunk_size]}).execute()
            except: pass

def upload_bytes_to_bucket(image_bytes):
    try:
        filename = f"img_{uuid.uuid4()}.png"
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type="image/png")
        return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"
    except: return None

def generate_imagen_safe(prompt):
    for i in range(3):
        try:
            model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")
            images = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio="16:9", person_generation="allow_adult")
            if images: return images[0]._image_bytes
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e): time.sleep(10 * (i+1))
            else: return None
    return None

def find_image_element_id_smart(prs_id, label):
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        label_clean = label.strip().upper()
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
                t_map = translate_list_strings(static_texts)
                apply_static_translations(new_id, t_map)
        
        reqs = []
        # Page 1: Cover
        if 'page_1_cover' in final_data:
            reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': final_data['page_1_cover'].get('title', '')}})
        # Page 2: Desc 1
        if 'page_2_desc' in final_data:
            reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE_1}}'}, 'replaceText': final_data['page_2_desc'].get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': '{{BODY_1}}'}, 'replaceText': final_data['page_2_desc'].get('body', '')}})
        # Page 3: Desc 2
        if 'page_3_desc' in final_data:
            reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE_2}}'}, 'replaceText': final_data['page_3_desc'].get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': '{{BODY_2}}'}, 'replaceText': final_data['page_3_desc'].get('body', '')}})
        # Page 4: Details
        if 'page_4_details' in final_data:
            reqs.append({'replaceAllText': {'containsText': {'text': '{{SVOLGIMENTO}}'}, 'replaceText': final_data['page_4_details'].get('svolgimento', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': '{{LOGISTICA}}'}, 'replaceText': final_data['page_4_details'].get('logistica', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': '{{TECNICA}}'}, 'replaceText': final_data['page_4_details'].get('tecnica', '')}})

        if reqs:
            slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()

        for label, url in urls_map.items():
            if url:
                el_id = find_image_element_id_smart(new_id, label)
                if el_id:
                    req = {'replaceImage': {'imageObjectId': el_id, 'imageReplaceMethod': 'CENTER_CROP', 'url': url}}
                    try: slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': [req]}).execute()
                    except: pass
        return new_id
    except Exception as e:
        print(e)
        return None

# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("🏗️ Slide Monster: FORMAT MODE")

# --- FASE 1: UPLOAD ---
if st.session_state.app_state == "UPLOAD":
    st.markdown("### 1. Carica le presentazioni")
    with st.container(border=True):
        uploaded = st.file_uploader("PPTX", accept_multiple_files=True, type=['pptx'])
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
            st.caption("Analisi ottimizzata per il nuovo layout a 4 Pagine Dinamiche (Cover, Desc 1, Desc 2, Dettagli).")

# --- FASE 2: EDITING ---
elif st.session_state.app_state == "EDIT":
    
    col_h1, col_h2 = st.columns([3, 1])
    with col_h1:
        st.info("✏️ **Sala di Regia**: Struttura a 4 Tab fissi. Compila i campi e salva.")
    with col_h2:
        if st.button("💾 SALVA SU DRIVE", type="primary", use_container_width=True):
            bar = st.progress(0)
            total_ops = len(st.session_state.draft_data)
            for i, (fname, content) in enumerate(st.session_state.draft_data.items()):
                url_map = {}
                saved = st.session_state.final_images.get(fname, {})
                
                # MAPPING IMMAGINI (Tag Template)
                if 'cover' in saved: url_map['IMG_1'] = saved['cover'] # IMG_1 ora è la Cover (Pag 1)
                if 'desc_1' in saved: url_map['IMG_2'] = saved['desc_1'] # IMG_2 è Pag 2
                if 'desc_2' in saved: url_map['IMG_3'] = saved['desc_2'] # IMG_3 è Pag 3
                
                # ITA
                st.toast(f"🇮🇹 Saving ITA: {fname}")
                res_ita = worker_bot_finalize(tmpl, fold, fname, content['ai_data'], url_map, translate_mode=False)
                # ENG
                if make_english:
                    fname_eng = fname.replace("_ITA", "_ENG")
                    st.toast(f"🇬🇧 Saving ENG: {fname_eng}")
                    res_eng = worker_bot_finalize(tmpl, fold, fname_eng, content['ai_data'], url_map, translate_mode=True)

                if res_ita: st.success(f"✅ {fname}")
                else: st.error(f"❌ {fname}")
                bar.progress((i+1)/total_ops)
            st.balloons()
            time.sleep(2)

    for fname, content in st.session_state.draft_data.items():
        data = content['ai_data']
        orig_imgs = st.session_state.original_images.get(fname, {})
        
        st.markdown(f"## 📂 {fname}")
        
        # 4 TAB FISSI
        tabs = st.tabs(["🏠 1. Cover", "📄 2. Descrizione 1", "📄 3. Descrizione 2", "🛠️ 4. Scheda Tecnica"])
        
        # --- TAB 1: COVER ---
        with tabs[0]:
            c1, c2, c3 = st.columns([1.5, 1, 1])
            with c1:
                st.markdown("#### Testo Cover")
                new_t = st.text_input("Titolo Format", value=data['page_1_cover'].get('title', ''), key=f"t1_{fname}")
                st.session_state.draft_data[fname]['ai_data']['page_1_cover']['title'] = new_t
            with c2:
                st.markdown("#### AI Image")
                p = st.text_area("Prompt", value=data['page_1_cover'].get('image_prompt', ''), height=70, key=f"p1_{fname}")
                if st.button("Genera", key=f"b1_{fname}"):
                    bytes_img = generate_imagen_safe(p)
                    if bytes_img: st.session_state.final_images[fname]['cover'] = upload_bytes_to_bucket(bytes_img); st.rerun()
                if st.session_state.final_images[fname].get('cover'): st.success("Pronta")
            with c3:
                st.markdown("#### Originale")
                if orig_imgs.get(0):
                    st.image(orig_imgs[0], width=150)
                    if st.button("Usa Originale", key=f"bo1_{fname}"):
                        st.session_state.final_images[fname]['cover'] = upload_bytes_to_bucket(orig_imgs[0]); st.rerun()

        # --- TAB 2: DESC 1 ---
        with tabs[1]:
            c1, c2, c3 = st.columns([1.5, 1, 1])
            with c1:
                st.markdown("#### Testo Pagina 2")
                new_t = st.text_input("Titolo 1", value=data['page_2_desc'].get('title', ''), key=f"t2_{fname}")
                new_b = st.text_area("Body 1", value=data['page_2_desc'].get('body', ''), height=100, key=f"b2_{fname}")
                st.session_state.draft_data[fname]['ai_data']['page_2_desc']['title'] = new_t
                st.session_state.draft_data[fname]['ai_data']['page_2_desc']['body'] = new_b
            with c2:
                st.markdown("#### AI Image")
                p = st.text_area("Prompt", value=data['page_2_desc'].get('image_prompt', ''), height=70, key=f"p2_{fname}")
                if st.button("Genera", key=f"b2_gen_{fname}"):
                    bytes_img = generate_imagen_safe(p)
                    if bytes_img: st.session_state.final_images[fname]['desc_1'] = upload_bytes_to_bucket(bytes_img); st.rerun()
                if st.session_state.final_images[fname].get('desc_1'): st.success("Pronta")
            with c3:
                st.markdown("#### Originale")
                # Indice 1 (Slide 2)
                if orig_imgs.get(1):
                    st.image(orig_imgs[1], width=150)
                    if st.button("Usa Originale", key=f"bo2_{fname}"):
                        st.session_state.final_images[fname]['desc_1'] = upload_bytes_to_bucket(orig_imgs[1]); st.rerun()

        # --- TAB 3: DESC 2 ---
        with tabs[2]:
            c1, c2, c3 = st.columns([1.5, 1, 1])
            with c1:
                st.markdown("#### Testo Pagina 3")
                new_t = st.text_input("Titolo 2", value=data['page_3_desc'].get('title', ''), key=f"t3_{fname}")
                new_b = st.text_area("Body 2", value=data['page_3_desc'].get('body', ''), height=100, key=f"b3_{fname}")
                st.session_state.draft_data[fname]['ai_data']['page_3_desc']['title'] = new_t
                st.session_state.draft_data[fname]['ai_data']['page_3_desc']['body'] = new_b
            with c2:
                st.markdown("#### AI Image")
                p = st.text_area("Prompt", value=data['page_3_desc'].get('image_prompt', ''), height=70, key=f"p3_{fname}")
                if st.button("Genera", key=f"b3_gen_{fname}"):
                    bytes_img = generate_imagen_safe(p)
                    if bytes_img: st.session_state.final_images[fname]['desc_2'] = upload_bytes_to_bucket(bytes_img); st.rerun()
                if st.session_state.final_images[fname].get('desc_2'): st.success("Pronta")
            with c3:
                st.markdown("#### Originale")
                # Indice 2 (Slide 3)
                if orig_imgs.get(2):
                    st.image(orig_imgs[2], width=150)
                    if st.button("Usa Originale", key=f"bo3_{fname}"):
                        st.session_state.final_images[fname]['desc_2'] = upload_bytes_to_bucket(orig_imgs[2]); st.rerun()

        # --- TAB 4: DETAILS ---
        with tabs[3]:
            st.markdown("#### 🛠️ Dettagli Tecnici (Slide 4 - 3 Colonne)")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Svolgimento**")
                v1 = st.text_area("Testo", value=data['page_4_details'].get('svolgimento', ''), height=200, key=f"d1_{fname}")
                st.session_state.draft_data[fname]['ai_data']['page_4_details']['svolgimento'] = v1
            with c2:
                st.markdown("**Logistica**")
                v2 = st.text_area("Testo", value=data['page_4_details'].get('logistica', ''), height=200, key=f"d2_{fname}")
                st.session_state.draft_data[fname]['ai_data']['page_4_details']['logistica'] = v2
            with c3:
                st.markdown("**Tecnica**")
                v3 = st.text_area("Testo", value=data['page_4_details'].get('tecnica', ''), height=200, key=f"d3_{fname}")
                st.session_state.draft_data[fname]['ai_data']['page_4_details']['tecnica'] = v3

        st.markdown("---")
