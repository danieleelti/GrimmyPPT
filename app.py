import streamlit as st
import google.generativeai as genai
import pandas as pd

st.set_page_config(page_title="🔍 Google API Debugger", layout="wide")

st.title("🔍 Google Model Debugger")
st.markdown("Questo tool interroga la tua API Key per scoprire quali modelli sono *realmente* disponibili.")

# --- INPUT API KEY ---
api_key = st.text_input("Inserisci la tua Google API Key", type="password")

if st.button("Avvia Scansione Modelli") and api_key:
    genai.configure(api_key=api_key)
    
    st.divider()
    
    # --- 1. LISTA UFFICIALE (Text & Multimodal) ---
    st.subheader("1. Lista Modelli Restituita dall'API (Gemini/Text)")
    st.info("Questi sono i modelli che Google dichiara esplicitamente disponibili per te.")
    
    try:
        models = list(genai.list_models())
        
        data = []
        for m in models:
            data.append({
                "Nome Modello (ID)": m.name,
                "Display Name": m.display_name,
                "Metodi Supportati": m.supported_generation_methods
            })
        
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
        
    except Exception as e:
        st.error(f"Errore nel recupero lista modelli: {e}")

    st.divider()

    # --- 2. PROBE TEST PER IMAGEN (Immagini) ---
    st.subheader("2. Test 'Forza Bruta' per Imagen")
    st.warning("""
    Nota: I modelli di immagine (Imagen) spesso NON appaiono nella lista sopra perché sono in 'Preview' o gestiti diversamente.
    Qui sotto provo a chiamarli uno per uno per vedere se rispondono.
    """)

    # Lista dei nomi tecnici noti per Imagen su AI Studio
    imagen_candidates = [
        "imagen-3.0-generate-001",
        "imagen-2.0-generate-001", 
        "turing-preview", # A volte usato internamente per test
        "image-generation-001"
    ]

    for model_name in imagen_candidates:
        col1, col2 = st.columns([1, 4])
        with col1:
            st.write(f"Testing: `{model_name}`...")
        
        with col2:
            try:
                # Tentativo di generazione fittizia (basso carico)
                model = genai.ImageGenerationModel(model_name)
                response = model.generate_images(
                    prompt="A tiny blue dot",
                    number_of_images=1,
                    aspect_ratio="1:1"
                )
                st.success(f"✅ SUCCESSO! Il modello '{model_name}' è attivo e funzionante.")
            except Exception as e:
                err_msg = str(e)
                if "404" in err_msg or "not found" in err_msg.lower():
                    st.error(f"❌ Non trovato (404)")
                elif "403" in err_msg or "permission" in err_msg.lower():
                    st.warning(f"⛔ Trovato ma accesso negato (403 - Permessi o Billing)")
                else:
                    st.error(f"❌ Errore generico: {err_msg}")
