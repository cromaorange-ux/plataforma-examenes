import streamlit as st
import datetime
import json
import time
import random
import os
from google import genai
from google.genai import types
from pypdf import PdfReader
from supabase import create_client, Client

# ---------------------------------------------------------
# CONFIGURACIÓN PÁGINA Y CONEXIONES
# ---------------------------------------------------------
st.set_page_config(page_title="Plataforma de Exámenes", layout="centered")

# CORRECTO: Se queda con la etiqueta literal "SUPABASE_URL"
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

# Configuración de variable de entorno para compatibilidad GCP/Vertex AI
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Inicialización adaptada para credenciales de proyecto GCP
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"Error al inicializar el cliente de Gemini: {e}")

# Variables de Estado de Sesión
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user_nombre" not in st.session_state:
    st.session_state.user_nombre = ""
if "es_croma" not in st.session_state:
    st.session_state.es_croma = False

# Estado del examen
if "examen_activo" not in st.session_state:
    st.session_state.examen_activo = False
if "preguntas_seleccionadas" not in st.session_state:
    st.session_state.preguntas_seleccionadas = []
if "indice_pregunta" not in st.session_state:
    st.session_state.indice_pregunta = 0
if "respuestas_detalle" not in st.session_state:
    st.session_state.respuestas_detalle = []
if "tiempo_inicio_pregunta" not in st.session_state:
    st.session_state.tiempo_inicio_pregunta = None
if "tiempo_inicio_examen" not in st.session_state:
    st.session_state.tiempo_inicio_examen = None
if "examen_id" not in st.session_state:
    st.session_state.examen_id = None
if "apartado_actual" not in st.session_state:
    st.session_state.apartado_actual = ""
if "sobrepaso_tiempo_global" not in st.session_state:
    st.session_state.sobrepaso_tiempo_global = False

# Sistema de Ayudas (3 Comodines)
if "comodines_restantes" not in st.session_state:
    st.session_state.comodines_restantes = 3
if "pistas_obtenidas" not in st.session_state:
    st.session_state.pistas_obtenidas = {}

TIEMPO_LIMITE_PREGUNTA = 45  # Segundos por pregunta

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
                
                # Comprobar si ya realizó el examen este mes
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
# MÓDULO 2: PANEL Y EVALUACIÓN
# ---------------------------------------------------------
else:
    st.write(f"Bienvenido/a, **{st.session_state.user_nombre}**")
    
    if st.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.session_state.examen_activo = False
        st.rerun()
        
    st.markdown("---")
    
    # -----------------------------------------------------
    # CUESTIONARIO ACTIVO
    # -----------------------------------------------------
    if st.session_state.examen_activo:
        idx = st.session_state.indice_pregunta
        total_p = len(st.session_state.preguntas_seleccionadas)
        
        if idx < total_p:
            p_actual = st.session_state.preguntas_seleccionadas[idx]
            
            # Encabezado con comodines de ayuda
            col_info, col_ayuda = st.columns([3, 2])
            with col_info:
                st.subheader(f"Pregunta {idx + 1} de {total_p}")
            with col_ayuda:
                st.caption(f"💡 Ayudas disponibles: **{st.session_state.comodines_restantes} / 3**")

            # Temporizador por pregunta
            tiempo_transcurrido = int(time.time() - st.session_state.tiempo_inicio_pregunta)
            tiempo_restante = TIEMPO_LIMITE_PREGUNTA - tiempo_transcurrido
            
            st.progress(max(0.0, tiempo_restante / TIEMPO_LIMITE_PREGUNTA))
            
            if tiempo_restante > 0:
                st.caption(f"⏱️ Tiempo restante: **{tiempo_restante} segundos**")
            else:
                st.warning("⏰ ¡Tiempo agotado en esta pregunta!")
                st.session_state.sobrepaso_tiempo_global = True
                
                st.session_state.respuestas_detalle.append({
                    "pregunta": p_actual["pregunta"],
                    "opcion_elegida": "Sin respuesta (Agotado tiempo)",
                    "es_correcta": False
                })
                st.session_state.indice_pregunta += 1
                st.session_state.tiempo_inicio_pregunta = time.time()
                st.rerun()

            st.write(f"**{p_actual['pregunta']}**")
            
            eleccion = st.radio("Selecciona una opción:", p_actual["opciones_barajadas"], key=f"p_{idx}")
            
            # PISTA DE AYUDA DE IA
            if idx in st.session_state.pistas_obtenidas:
                st.info(f"💡 **Pista:** {st.session_state.pistas_obtenidas[idx]}")
            else:
                if st.session_state.comodines_restantes > 0:
                    if st.button("💡 Pedir Ayuda de IA (Gasta 1 comodín)"):
                        st.session_state.comodines_restantes -= 1
                        
                        prompt_pista = f"""El usuario está respondiendo a esta pregunta de examen:
Pregunta: {p_actual['pregunta']}
Opciones: {p_actual['opciones_barajadas']}

Proporciona una pista concisa (máximo 2 frases) que le ayude a razonar la respuesta correcta SIN revelar directamente cuál de las opciones es.
"""
                        try:
                            res_pista = gemini_client.models.generate_content(
                                model='gemini-3.6-flash',
                                contents=prompt_pista
                            )
                            st.session_state.pistas_obtenidas[idx] = res_pista.text
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al solicitar la ayuda: {e}")
                else:
                    st.caption("🚫 Has agotado tus 3 comodines de ayuda en este examen.")

            st.write("")
            if st.button("Responder / Siguiente"):
                es_correcta = (eleccion == p_actual["respuesta_correcta_texto"])
                
                st.session_state.respuestas_detalle.append({
                    "pregunta": p_actual["pregunta"],
                    "opcion_elegida": eleccion,
                    "es_correcta": es_correcta
                })
                
                st.session_state.indice_pregunta += 1
                st.session_state.tiempo_inicio_pregunta = time.time()
                st.rerun()
                
            time.sleep(1)
            st.rerun()
            
        else:
            # COMPLETADO: PROCESAR Y GUARDAR
            st.success("🎉 Examen finalizado.")
            
            correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
            porcentaje = round((correctas / total_p) * 100, 2)
            nota_final = round((correctas / total_p) * 10, 2)
            
            tiempo_fin_examen = datetime.datetime.now(datetime.timezone.utc)
            duracion_total = int(time.time() - st.session_state.tiempo_inicio_examen)
            tiempo_limite_total = total_p * TIEMPO_LIMITE_PREGUNTA
            
            st.metric(label="Calificación", value=f"{nota_final} / 10 ({porcentaje}%)")
            st.write(f"⏱️ Tiempo total empleado: **{duracion_total} segundos**")
            st.write(f"💡 Comodines de ayuda utilizados: **{3 - st.session_state.comodines_restantes} / 3**")
            
            # Guardar auditoría en Supabase
            try:
                registro_intento = {
                    "empleado_id": st.session_state.user_id,
                    "nombre_empleado": st.session_state.user_nombre,
                    "examen_id": st.session_state.examen_id,
                    "apartado": st.session_state.apartado_actual,
                    "nota": nota_final,
                    "porcentaje_obtenido": porcentaje,
                    "respuestas_usuario": st.session_state.respuestas_detalle,
                    "fecha_inicio": datetime.datetime.fromtimestamp(st.session_state.tiempo_inicio_examen, datetime.timezone.utc).isoformat(),
                    "fecha_fin": tiempo_fin_examen.isoformat(),
                    "tiempo_total_segundos": duracion_total,
                    "tiempo_limite": tiempo_limite_total,
                    "sobrepasado_tiempo": st.session_state.sobrepaso_tiempo_global
                }
                
                supabase.table("intentos_examen").insert(registro_intento).execute()
                st.success("✅ Intento guardado con éxito en la base de datos.")
            except Exception as e:
                st.error(f"Error guardando intento: {e}")
                
            if st.button("Finalizar y Volver"):
                st.session_state.examen_activo = False
                st.rerun()

    # -----------------------------------------------------
    # SELECCIÓN Y CARGA DE EXÁMENES
    # -----------------------------------------------------
    else:
        try:
            res_examenes = supabase.table("examenes").select("id, apartado, preguntas_json").execute()
            examenes_disponibles = res_examenes.data if res_examenes.data else []
        except Exception as e:
            examenes_disponibles = []
            st.error(f"Error al cargar exámenes: {e}")

        if examenes_disponibles:
            dict_examenes = {ex["apartado"]: ex for ex in examenes_disponibles}
            examen_seleccionado = st.selectbox("Seleccionar Examen", list(dict_examenes.keys()))
            
            if st.button("Comenzar Examen"):
                ex_obj = dict_examenes[examen_seleccionado]
                banco_completo = ex_obj["preguntas_json"]
                
                # Seleccionar 3 preguntas al azar
                num_a_seleccionar = min(3, len(banco_completo))
                preguntas_elegidas = random.sample(banco_completo, num_a_seleccionar)
                
                # Mezclar opciones de respuesta
                preguntas_preparadas = []
                for p in preguntas_elegidas:
                    idx_correcta = p["respuesta_correcta"]
                    texto_correcto = p["opciones"][idx_correcta]
                    
                    opciones_shuffled = p["opciones"].copy()
                    random.shuffle(opciones_shuffled)
                    
                    preguntas_preparadas.append({
                        "pregunta": p["pregunta"],
                        "opciones_barajadas": opciones_shuffled,
                        "respuesta_correcta_texto": texto_correcto
                    })
                
                # Configurar Estado inicial
                st.session_state.examen_id = ex_obj["id"]
                st.session_state.apartado_actual = ex_obj["apartado"]
                st.session_state.preguntas_seleccionadas = preguntas_preparadas
                st.session_state.indice_pregunta = 0
                st.session_state.respuestas_detalle = []
                st.session_state.sobrepaso_tiempo_global = False
                st.session_state.tiempo_inicio_examen = time.time()
                st.session_state.tiempo_inicio_pregunta = time.time()
                st.session_state.comodines_restantes = 3
                st.session_state.pistas_obtenidas = {}
                st.session_state.examen_activo = True
                
                st.rerun()
        else:
            st.warning("No hay exámenes disponibles en el sistema.")

        # -------------------------------------------------
        # PANEL ADMIN: GENERAR BBDD DE 15 PREGUNTAS CON IA
        # -------------------------------------------------
        if st.session_state.es_croma:
            st.markdown("---")
            st.subheader("⚙️ Panel Admin: Generar Banco de 15 Preguntas")
            archivo_pdf = st.file_uploader("Cargar PDF con manual operativo", type=["pdf"])
            nombre_apartado = st.text_input("Nombre de la materia/apartado")
            
            if st.button("Procesar e Insertar 15 Preguntas con IA"):
                if archivo_pdf and nombre_apartado:
                    try:
                        reader = PdfReader(archivo_pdf)
                        texto = "".join([page.extract_text() or "" for page in reader.pages])
                        
                        prompt = """Genera un examen con EXACTAMENTE 15 preguntas tipo test basadas en el texto.
Responde ÚNICAMENTE con un array JSON estructurado así:
[
  {
    "pregunta": "texto de la pregunta",
    "opciones": ["Opcion A", "Opcion B", "Opcion C", "Opcion D"],
    "respuesta_correcta": 0,
    "tipo": "test"
  }
]

Texto de estudio:
""" + texto[:6000]

                        # Lista de modelos a intentar en orden de preferencia si hay saturación (503)
                        modelos = ['gemini-3.6-flash', 'gemini-3.1-flash', 'gemini-3.5-flash-lite']
                        res = None
                        
                        with st.spinner("Generando 15 preguntas con IA... Esto puede tomar unos segundos."):
                            for model_name in modelos:
                                intencion = 0
                                exito = False
                                while intencion < 3 and not exito:
                                    try:
                                        res = gemini_client.models.generate_content(
                                            model=model_name,
                                            contents=prompt,
                                            config=types.GenerateContentConfig(response_mime_type="application/json")
                                        )
                                        exito = True
                                    except Exception as err:
                                        if "503" in str(err) or "UNAVAILABLE" in str(err):
                                            intencion += 1
                                            time.sleep(2)  # Espera 2 segundos antes de reintentar
                                        else:
                                            raise err  # Si es otro tipo de error, lo lanza de inmediato
                                if exito:
                                    break

                        if res and res.text:
                            preguntas_json = json.loads(res.text)
                            
                            supabase.table("examenes").insert({
                                "apartado": nombre_apartado, 
                                "preguntas_json": preguntas_json
                            }).execute()
                            
                            st.success(f"✅ Se han generado {len(preguntas_json)} preguntas y se guardaron en el apartado '{nombre_apartado}'.")
                            st.rerun()
                        else:
                            st.error("❌ El servicio de IA está muy saturado en este momento. Por favor, reinténtalo en 1 minuto.")

                    except Exception as e:
                        st.error(f"❌ Error al generar el examen: {e}")
                else:
                    st.error("Sube un PDF e introduce un nombre de apartado.")
