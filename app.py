import streamlit as st
import google.generativeai as genai
import json

st.set_page_config(page_title="Scanner Modelli AI", layout="wide")

st.title("🕵️‍♂️ Scanner Modelli Gemini")
st.info("Vediamo esattamente cosa vede la tua Chiave API.")

# 1. Configurazione API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    st.success("✅ API Key agganciata.")
except Exception as e:
    st.error(f"❌ Problema API Key: {e}")
    st.stop()

# 2. Scansione
if st.button("🔍 SCANSIONA ORA"):
    try:
        models = list(genai.list_models())
        found = []
        
        st.write("---")
        st.subheader("📋 Modelli Trovati:")
        
        for m in models:
            # Mostra solo i modelli che generano testo
            if 'generateContent' in m.supported_generation_methods:
                st.code(m.name) # Questo è il nome VERO da usare
                found.append(m.name)
        
        if not found:
            st.error("Nessun modello trovato! La API Key potrebbe non avere i permessi 'Generative Language'.")
        else:
            st.success(f"Trovati {len(found)} modelli.")
            st.warning("⚠️ COPIA UNO DI QUESTI NOMI ESATTI (esclusi quelli 'vision' o 'embedding').")

    except Exception as e:
        st.error(f"Errore di connessione: {e}")
