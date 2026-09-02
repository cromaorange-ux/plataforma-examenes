import streamlit as st
import datetime
import json
import time
from supabase import create_client, Client
from pypdf import PdfReader
from google import genai
from google.genai import types

# ---------------------------------------------------------
# CONFIGURACIÓN DE APIS Y BASE DE DATOS
# ---------------------------------------------------------
SUPABASE_URL = "https://vezkigrbksmsndasxldu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZlemtpZ3Jia3Ntc25kYXN4bGR1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgyNTgyMjgsImV4cCI6MjEwMzgzNDIyOH0.0jkzfl0zceROHR0Xl00r-5TthJ7Z5neqY7b4h9PAyzw"
GEMINI_API_KEY = "AQ.Ab8RN6J-S9DRtaJ5Bkj7n_L0_uK2D4EhbEKiLaNeO7Ry7o0TJg"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

st.set_page_config(page_title="Plataforma de Exámenes", layout="centered")

# Inicialización de estados en la sesión
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "examen_iniciado" not in st.session_state:
    st.session_state.examen_iniciado = False

# ---------------------------------------------------------
# MÓDULO 1: AUTENTICACIÓN CON DESPLEGABLE DE USUARIOS
# ---------------------------------------------------------
st.title("📝 Sistema de Evaluación Mensual")

if not st.session_state.autenticado:
    st.subheader("Iniciar Sesión")
    
    # 1. Obtener la lista de usuarios desde la base de datos
    try:
        res_usuarios = supabase.table("empleados").select("nombre").execute()
        # Extraer los nombres en una lista ordenada
        lista_usuarios = [emp["nombre"] for emp in res_usuarios.data] if res_usuarios.data else []
    except Exception as e:
        lista_usuarios = []
        st.error(f"Error al conectar con la base de datos: {e}")

    if lista_usuarios:
        # 2. Menú desplegable para seleccionar el usuario
        usuario_seleccionado = st.selectbox("Selecciona tu Usuario", lista_usuarios)
        password_input = st.text_input("Contraseña", type="password")
        
        if st.button("Ingresar"):
            # Consultar los datos completos del usuario elegido
            res = supabase.table("empleados").select("*").eq("nombre", usuario_seleccionado).execute()
            
            if res.data and res.data[0]["password_hash"] == password_input:
                emp = res.data[0]
                st.session_state.user_id = emp["id"]
                st.session_state.user_nombre = emp["nombre"]
                st.session_state.es_croma = emp["es_admin_croma"]
                
                # Validar intentos en el mes actual
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
        st.warning("No se encontraron usuarios en la base de datos. Verifica la conexión con Supabase o la tabla 'empleados'.")

# ---------------------------------------------------------
# MODULO 2: PANEL DE CONTROL Y Carga DE EXÁMENES
# ---------------------------------------------------------
else:
    st.sidebar.write(f"👤 **Usuario:** {st.session_state.user_nombre}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.clear()
        st.rerun()

    if not st.session_state.examen_iniciado:
        st.subheader("Seleccionar Examen")
        
        # Cargar lista de exámenes creados en Supabase
        examenes_res = supabase.table("examenes").select("id, apartado").execute()
        opciones_examenes = {e["apartado"]: e["id"] for e in examenes_res.data} if examenes_res.data else {}
        
        if opciones_examenes:
            examen_sel = st.selectbox("Elige el examen a realizar:", list(opciones_examenes.keys()))
            
            if st.button("Comenzar Examen"):
                # Cargar preguntas del examen seleccionado
                ex_data = supabase.table("examenes").select("*").eq("id", opciones_examenes[examen_sel]).execute().data[0]
                
                st.session_state.preguntas = ex_data["preguntas_json"]
                st.session_state.apartado = ex_data["apartado"]
                st.session_state.num_preguntas = len(st.session_state.preguntas)
                st.session_state.tiempo_limite = st.session_state.num_preguntas * 45 # 45 segundos por pregunta
                st.session_state.hora_inicio = datetime.datetime.now()
                st.session_state.examen_iniciado = True
                st.rerun()
        else:
            st.info("No hay exámenes disponibles cargados en el sistema.")

# Opción extra para admins: Generar nuevo examen desde PDF
        if st.session_state.es_croma:
            st.markdown("---")
            st.subheader("⚙️ Panel Admin: Generar Nuevo Examen")
            archivo_pdf = st.file_uploader("Cargar PDF con manual operativo", type=["pdf"])
            nombre_apartado = st.text_input("Nombre de la materia/apartado")
            
            if st.button("Procesar con IA e Insertar en BBDD"):
                if archivo_pdf and nombre_apartado:
                    reader = PdfReader(archivo_pdf)
                    texto = "".join([page.extract_text() or "" for page in reader.pages])
                    
                    prompt = """Genera un examen de 5 preguntas tipo test del texto. Responde ÚNICAMENTE con un array JSON.
Estructura: [{"pregunta": "texto", "opciones": ["A", "B", "C"], "respuesta_correcta": 0, "tipo": "test"}]

Texto a evaluar:
""" + texto[:4000]
                    
                    # Cambiar 'gemini-3.6-flash' por 'gemini-2.5-flash' o 'gemini-1.5-flash'
                    res = gemini_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    
                    preguntas_json = json.loads(res.text)
                    supabase.table("examenes").insert({"apartado": nombre_apartado, "preguntas_json": preguntas_json}).execute()
                    st.success("Examen generado e introducido en la base de datos.")
                    st.rerun()
                else:
                    st.error("Por favor, sube un archivo PDF y escribe un nombre para el apartado.")

    
# ---------------------------------------------------------
# MODULO 3: EJECUCIÓN Y EVALUACIÓN DEL EXAMEN
# ---------------------------------------------------------
    else:
        st.subheader(f"Examen: {st.session_state.apartado}")
        
        # Cálculo de tiempo transcurrido
        tiempo_transcurrido = int((datetime.datetime.now() - st.session_state.hora_inicio).total_seconds())
        tiempo_restante = max(0, st.session_state.tiempo_limite - tiempo_transcurrido)
        
        st.warning(f"⏱️ Tiempo restante: {tiempo_restante // 60}m {tiempo_restante % 60}s | Límite: {st.session_state.tiempo_limite}s")
        
        respuestas_usuario = {}
        with st.form("form_examen"):
            for i, p in enumerate(st.session_state.preguntas):
                st.markdown(f"**{i+1}. {p['pregunta']}**")
                respuestas_usuario[i] = st.radio(f"Selecciona una opción para la pregunta {i+1}:", p["opciones"], key=f"p_{i}", index=None)
            
            enviar = st.form_submit_button("Enviar Examen")
            
        if enviar:
            hora_fin = datetime.datetime.now()
            tiempo_total = int((hora_fin - st.session_state.hora_inicio).total_seconds())
            sobrepasado = tiempo_total > st.session_state.tiempo_limite
            
            # Corregir examen
            aciertos = 0
            for i, p in enumerate(st.session_state.preguntas):
                opcion_elegida = respuestas_usuario.get(i)
                if opcion_elegida and p["opciones"].index(opcion_elegida) == p["respuesta_correcta"]:
                    aciertos += 1
                    
            porcentaje = (aciertos / st.session_state.num_preguntas) * 100
            
            # Guardar intento en Supabase
            supabase.table("intentos_examen").insert({
                "empleado_id": st.session_state.user_id,
                "apartado": st.session_state.apartado,
                "fecha_inicio": st.session_state.hora_inicio.isoformat(),
                "fecha_fin": hora_fin.isoformat(),
                "tiempo_total_segundos": tiempo_total,
                "tiempo_limite_segundos": st.session_state.tiempo_limite,
                "sobrepasado_tiempo": sobrepasado,
                "porcentaje_obtenido": porcentaje,
                "respuestas_usuario": respuestas_usuario
            }).execute()
            
            st.session_state.examen_iniciado = False
            st.success(f"Examen finalizado. Nota: {porcentaje:.1f}%")
            if sobrepasado:
                st.error("⚠️ Has sobrepasado el tiempo límite establecido.")
