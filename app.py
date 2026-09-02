import streamlit as st
import datetime
import json
from google import genai
from google.genai import types
from pypdf import PdfReader
from supabase import create_client, Client

# ---------------------------------------------------------
# CONFIGURACIÓN DE CONEXIONES Y CLIENTES
# ---------------------------------------------------------
st.set_page_config(page_title="Plataforma de Exámenes", layout="centered")

# Lectura de credenciales desde Streamlit Secrets
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# Inicializar clientes
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Variables de estado de sesión
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_nombre" not in st.session_state:
    st.session_state.user_nombre = ""
if "es_croma" not in st.session_state:
    st.session_state.es_croma = False

# ---------------------------------------------------------
# MÓDULO 1: AUTENTICACIÓN CON DESPLEGABLE
# ---------------------------------------------------------
st.title("📝 Sistema de Evaluación Mensual")

if not st.session_state.autenticado:
    st.subheader("Iniciar Sesión")
    
    try:
        res_usuarios = supabase.table("empleados").select("nombre").execute()
        lista_usuarios = [emp["nombre"] for emp in res_usuarios.data] if res_usuarios.data else []
    except Exception as e:
        lista_usuarios = []
        st.error(f"Error al conectar con la base de datos: {e}")

    if lista_usuarios:
        usuario_seleccionado = st.selectbox("Selecciona tu Usuario", lista_usuarios)
        password_input = st.text_input("Contraseña", type="password")
        
        if st.button("Ingresar"):
            res = supabase.table("empleados").select("*").eq("nombre", usuario_seleccionado).execute()
            
            if res.data and res.data[0]["password_hash"] == password_input:
                emp = res.data[0]
                st.session_state.user_id = emp["id"]
                st.session_state.user_nombre = emp["nombre"]
                st.session_state.es_croma = emp["es_admin_croma"]
                
                # Comprobar si ya hizo un examen este mes
                inicio_mes = datetime.datetime.now().replace(day=1, hour=0, minute=0, second=0).isoformat()
                intentos = supabase.table("intentos_examen").select("*").eq("empleado_id", emp["id"]).gte("fecha_inicio", inicio_mes).execute()
                
                if len(intentos.data) > 0 and not st.session_state.es_croma:
                    st.error("❌ Ya has realizado tu examen correspondiente a este mes.")
                else:
                    st.session_state.autenticado = True
                    st.rerun()
            else:
                st.error("❌ Contraseña incorrecta.")
    else:
        st.warning("No se encontraron usuarios en la base de datos. Verifica RLS o la tabla 'empleados'.")

# ---------------------------------------------------------
# MÓDULO 2: SELECCIÓN DE EXAMEN Y PANEL ADMIN (IA)
# ---------------------------------------------------------
else:
    st.write(f"Bienvenido/a, **{st.session_state.user_nombre}**")
    
    if st.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()
        
    st.markdown("---")
    
    # 1. Cargar lista de exámenes disponibles
    try:
        res_examenes = supabase.table("examenes").select("id, apartado").execute()
        examenes_disponibles = res_examenes.data if res_examenes.data else []
    except Exception as e:
        examenes_disponibles = []
        st.error(f"Error al cargar exámenes: {e}")

    if examenes_disponibles:
        opciones_examenes = {ex["apartado"]: ex["id"] for ex in examenes_disponibles}
        examen_elegido = st.selectbox("Seleccionar Examen", list(opciones_examenes.keys()))
        
        if st.button("Comenzar Examen"):
            st.info(f"Iniciando examen: {examen_elegido}")
            # Aquí continúa la lógica del temporizador e interfaz de preguntas
    else:
        st.warning("No hay exámenes disponibles cargados en el sistema.")

    # 2. Panel exclusivo para administradores (CROMA)
    if st.session_state.es_croma:
        st.markdown("---")
        st.subheader("⚙️ Panel Admin: Generar Nuevo Examen")
        archivo_pdf = st.file_uploader("Cargar PDF con manual operativo", type=["pdf"])
        nombre_apartado = st.text_input("Nombre de la materia/apartado")
        
        if st.button("Procesar con IA e Insertar en BBDD"):
            if archivo_pdf and nombre_apartado:
                try:
                    reader = PdfReader(archivo_pdf)
                    texto = "".join([page.extract_text() or "" for page in reader.pages])
                    
                    # Prompt concatenado para evitar errores de llaves JSON con f-strings
                    prompt = """Genera un examen de 5 preguntas tipo test del texto. Responde ÚNICAMENTE con un array JSON.
Estructura: [{"pregunta": "texto", "opciones": ["A", "B", "C"], "respuesta_correcta": 0, "tipo": "test"}]

Texto a evaluar:
""" + texto[:4000]
                    
                    res = gemini_client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    
                    preguntas_json = json.loads(res.text)
                    supabase.table("examenes").insert({
                        "apartado": nombre_apartado, 
                        "preguntas_json": preguntas_json
                    }).execute()
                    
                    st.success("✅ Examen generado e introducido en la base de datos correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al procesar el examen: {e}")
            else:
                st.error("Por favor, sube un archivo PDF e indica el nombre del apartado.")
