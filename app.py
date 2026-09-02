import streamlit as st
import datetime
import json
import time
from google import genai
from google.genai import types
from pypdf import PdfReader
from supabase import create_client, Client

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y CONEXIONES
# ---------------------------------------------------------
st.set_page_config(page_title="Plataforma de Exámenes", layout="centered")

SUPABASE_URL = st.secrets["https://vezkigrbksmsndasxldu.supabase.co"]
SUPABASE_KEY = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZlemtpZ3Jia3Ntc25kYXN4bGR1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODgyNTgyMjgsImV4cCI6MjEwMzgzNDIyOH0.0jkzfl0zceROHR0Xl00r-5TthJ7Z5neqY7b4h9PAyzw"]
GEMINI_API_KEY = st.secrets["AQ.Ab8RN6L66WvdO0jOeDW15-EElhDz6lo8WtJX-rfnpwRwPtn8pA"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Variables de estado globales
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_nombre" not in st.session_state:
    st.session_state.user_nombre = ""
if "es_croma" not in st.session_state:
    st.session_state.es_croma = False

# Estado de la prueba/examen activo
if "examen_activo" not in st.session_state:
    st.session_state.examen_activo = False
if "preguntas" not in st.session_state:
    st.session_state.preguntas = []
if "indice_pregunta" not in st.session_state:
    st.session_state.indice_pregunta = 0
if "respuestas_usuario" not in st.session_state:
    st.session_state.respuestas_usuario = []
if "tiempo_inicio_pregunta" not in st.session_state:
    st.session_state.tiempo_inicio_pregunta = None
if "examen_id" not in st.session_state:
    st.session_state.examen_id = None

TIEMPO_LIMITE_SEGUNDOS = 45

# ---------------------------------------------------------
# MÓDULO 1: AUTENTICACIÓN
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
                
                # Verificar intentos del mes
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
        st.warning("No se encontraron usuarios en la base de datos.")

# ---------------------------------------------------------
# MÓDULO 2: PANEL DE EXAMEN Y ADMIN
# ---------------------------------------------------------
else:
    st.write(f"Bienvenido/a, **{st.session_state.user_nombre}**")
    
    if st.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.session_state.examen_activo = False
        st.rerun()
        
    st.markdown("---")
    
    # -----------------------------------------------------
    # INTERFAZ DEL EXAMEN EN CURSO (CON TEMPORIZADOR)
    # -----------------------------------------------------
    if st.session_state.examen_activo:
        idx = st.session_state.indice_pregunta
        total_preguntas = len(st.session_state.preguntas)
        
        if idx < total_preguntas:
            pregunta_actual = st.session_state.preguntas[idx]
            
            # Cálculo del temporizador
            tiempo_transcurrido = int(time.time() - st.session_state.tiempo_inicio_pregunta)
            tiempo_restante = TIEMPO_LIMITE_SEGUNDOS - tiempo_transcurrido
            
            st.progress(max(0.0, tiempo_restante / TIEMPO_LIMITE_SEGUNDOS))
            
            if tiempo_restante > 0:
                st.caption(f"⏱️ Tiempo restante para esta pregunta: **{tiempo_restante} segundos**")
            else:
                st.warning("⏰ ¡Se agotó el tiempo para esta pregunta!")
                st.session_state.respuestas_usuario.append(None)
                st.session_state.indice_pregunta += 1
                st.session_state.tiempo_inicio_pregunta = time.time()
                st.rerun()

            st.subheader(f"Pregunta {idx + 1} de {total_preguntas}")
            st.write(f"**{pregunta_actual['pregunta']}**")
            
            eleccion = st.radio(
                "Selecciona una respuesta:", 
                pregunta_actual["opciones"], 
                key=f"p_{idx}"
            )
            
            if st.button("Siguiente Pregunta"):
                # Registrar el índice de la respuesta elegida
                idx_respuesta = pregunta_actual["opciones"].index(eleccion)
                st.session_state.respuestas_usuario.append(idx_respuesta)
                st.session_state.indice_pregunta += 1
                st.session_state.tiempo_inicio_pregunta = time.time()
                st.rerun()
                
            # Autorrefresco para mantener el temporizador visualizando el conteo en tiempo real
            time.sleep(1)
            st.rerun()
            
        else:
            # PROCESAR Y GUARDAR RESULTADOS AL FINALIZAR
            st.success("🎉 ¡Has completado todas las preguntas del examen!")
            
            aciertos = 0
            for i, p in enumerate(st.session_state.preguntas):
                resp = st.session_state.respuestas_usuario[i]
                if resp is not None and resp == p["respuesta_correcta"]:
                    aciertos += 1
                    
            nota_final = round((aciertos / total_preguntas) * 10, 2)
            st.metric(label="Nota Final", value=f"{nota_final} / 10")
            
            # Guardar en Supabase
            try:
                supabase.table("intentos_examen").insert({
                    "empleado_id": st.session_state.user_id,
                    "examen_id": st.session_state.examen_id,
                    "nota": nota_final,
                    "respuestas": st.session_state.respuestas_usuario
                }).execute()
                st.success("Resultado guardado en el historial de evaluaciones.")
            except Exception as e:
                st.error(f"Error al guardar la calificación: {e}")
                
            if st.button("Volver al Inicio"):
                st.session_state.examen_activo = False
                st.rerun()

# -----------------------------------------------------
    # PANTALLA PRINCIPAL DE SELECCIÓN DE EXAMEN
    # -----------------------------------------------------
    else:
        try:
            # Seleccionamos el id, el nombre de la materia y el array JSON de preguntas
            res_examenes = supabase.table("examenes").select("id, apartado, preguntas_json").execute()
            examenes_disponibles = res_examenes.data if res_examenes.data else []
        except Exception as e:
            examenes_disponibles = []
            st.error(f"Error al cargar exámenes: {e}")

        if examenes_disponibles:
            # Creamos un diccionario para buscar fácilmente por el nombre del apartado
            dict_examenes = {ex["apartado"]: ex for ex in examenes_disponibles}
            examen_seleccionado = st.selectbox("Seleccionar Examen", list(dict_examenes.keys()))
            
            if st.button("Comenzar Examen"):
                ex_obj = dict_examenes[examen_seleccionado]
                
                # Cargar el examen en la sesión y activar el reloj/preguntas
                st.session_state.examen_id = ex_obj["id"]
                st.session_state.preguntas = ex_obj["preguntas_json"]
                st.session_state.indice_pregunta = 0
                st.session_state.respuestas_usuario = []
                st.session_state.tiempo_inicio_pregunta = time.time()
                st.session_state.examen_activo = True
                
                st.rerun()  # Recarga inmediata para mostrar la Pregunta 1
        else:
            st.warning("No hay exámenes disponibles cargados en el sistema.")
            
        # -------------------------------------------------
        # PANEL ADMIN (GENERACIÓN CON GEMINI)
        # -------------------------------------------------
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
                        
                        prompt = """Genera un examen de 5 preguntas tipo test del texto. Responde ÚNICAMENTE con un array JSON.
Estructura: [{"pregunta": "texto", "opciones": ["A", "B", "C"], "respuesta_correcta": 0, "tipo": "test"}]

Texto a evaluar:
""" + texto[:4000]
                        
                        res = gemini_client.models.generate_content(
                            model='gemini-2.0-flash',
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
                        msg_error = str(e)
                        if "401" in msg_error or "UNAUTHENTICATED" in msg_error:
                            st.error("❌ **Error 401: Clave de API no autorizada**. Revisa que GEMINI_API_KEY en Secrets sea correcta y no tenga espacios sobrantes.")
                        else:
                            st.error(f"❌ Error al procesar con IA: {e}")
                else:
                    st.error("Por favor, sube un archivo PDF e indica el nombre del apartado.")
