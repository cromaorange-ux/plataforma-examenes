import streamlit as st
import datetime
import json
import time
import random
import os
import calendar
from google import genai
from google.genai import types
from pypdf import PdfReader
from supabase import create_client, Client

# ---------------------------------------------------------
# CONFIGURACIÓN PÁGINA Y CONEXIONES
# ---------------------------------------------------------
st.set_page_config(page_title="Plataforma de Exámenes", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"Error al inicializar el cliente de Gemini: {e}")

# Estado de Sesión
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

if "comodines_restantes" not in st.session_state:
    st.session_state.comodines_restantes = 3
if "pistas_activadas" not in st.session_state:
    st.session_state.pistas_activadas = set()

TIEMPO_LIMITE_PREGUNTA = 45
UMBRAL_APROBADO_PORCENTAJE = 70.0


def seleccionar_15_preguntas(banco_completo):
    disponibles = banco_completo.copy()
    random.shuffle(disponibles)
    
    seleccionadas = []
    ids_seleccionados = set()

    principales = [p for p in disponibles if p.get("es_principal", False)]
    for p in principales[:3]:
        seleccionadas.append(p)
        ids_seleccionados.add(p["pregunta"])

    disponibles = [p for p in disponibles if p["pregunta"] not in ids_seleccionados]

    faciles = [p for p in disponibles if p.get("dificultad") == "facil"]
    medias = [p for p in disponibles if p.get("dificultad") == "media"]
    dificiles = [p for p in disponibles if p.get("dificultad") == "dificil"]

    if faciles:
        p_facil = faciles[0]
        seleccionadas.append(p_facil)
        ids_seleccionados.add(p_facil["pregunta"])
    if medias:
        p_media = [p for p in medias if p["pregunta"] not in ids_seleccionados][0]
        seleccionadas.append(p_media)
        ids_seleccionados.add(p_media["pregunta"])
    if dificiles:
        p_dificil = [p for p in dificiles if p["pregunta"] not in ids_seleccionados][0]
        seleccionadas.append(p_dificil)
        ids_seleccionados.add(p_dificil["pregunta"])

    disponibles = [p for p in disponibles if p["pregunta"] not in ids_seleccionados]

    faltantes = 15 - len(seleccionadas)
    if faltantes > 0 and len(disponibles) >= faltantes:
        resto = random.sample(disponibles, faltantes)
        seleccionadas.extend(resto)
    elif faltantes > 0:
        seleccionadas.extend(disponibles)

    random.shuffle(seleccionadas)
    return seleccionadas


def obtener_dias_restantes_mes():
    ahora = datetime.datetime.now()
    _, ultimo_dia = calendar.monthrange(ahora.year, ahora.month)
    dias_restantes = ultimo_dia - ahora.day + 1
    return dias_restantes


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
    col_usr, col_logout = st.columns([4, 1])
    with col_usr:
        st.write(f"Bienvenido/a, **{st.session_state.user_nombre}** ({'Administrador CROMA' if st.session_state.es_croma else 'Empleado'})")
    with col_logout:
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
            
            col_info, col_ayuda = st.columns([3, 2])
            with col_info:
                st.subheader(f"Pregunta {idx + 1} de {total_p}")
                st.caption(f"📌 **Materia/Apartado:** {p_actual.get('apartado', 'General')}")
            with col_ayuda:
                st.caption(f"💡 Ayudas disponibles: **{st.session_state.comodines_restantes} / 3**")

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
            
            if idx in st.session_state.pistas_activadas:
                pista_texto = p_actual.get("pista", "Lee con atención las opciones y descarta las inconsistentes.")
                st.info(f"💡 **Pista:** {pista_texto}")
            else:
                if st.session_state.comodines_restantes > 0:
                    if st.button("💡 Pedir Ayuda (Gasta 1 comodín)"):
                        st.session_state.comodines_restantes -= 1
                        st.session_state.pistas_activadas.add(idx)
                        st.rerun()
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
            st.success("🎉 Examen finalizado.")
            
            correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
            porcentaje = round((correctas / total_p) * 100, 2)
            nota_final = round((correctas / total_p) * 10, 2)
            
            es_aprobado = porcentaje >= UMBRAL_APROBADO_PORCENTAJE
            estado_resultado = "🟢 APROBADO" if es_aprobado else "🔴 SUSPENSO"
            
            tiempo_fin_examen = datetime.datetime.now(datetime.timezone.utc)
            duracion_total = int(time.time() - st.session_state.tiempo_inicio_examen)
            tiempo_limite_total = total_p * TIEMPO_LIMITE_PREGUNTA
            
            st.metric(label="Calificación Final", value=f"{nota_final} / 10 ({porcentaje}%)", delta=estado_resultado)
            
            if es_aprobado:
                st.success(f"¡Felicidades! Has superado el examen alcanzando el mínimo requerido del {UMBRAL_APROBADO_PORCENTAJE}%.")
            else:
                st.error(f"No has alcanzado la nota mínima de aprobación ({UMBRAL_APROBADO_PORCENTAJE}%).")
                
            st.write(f"⏱️ Tiempo total empleado: **{duracion_total} segundos**")
            
            try:
                id_examen_validado = st.session_state.examen_id if isinstance(st.session_state.examen_id, int) else 0

                registro_intento = {
                    "empleado_id": st.session_state.user_id,
                    "nombre_empleado": st.session_state.user_nombre,
                    "examen_id": id_examen_validado,
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
    # MENÚ PRINCIPAL
    # -----------------------------------------------------
    else:
        # Pestañas diferenciadas según el rol
        if st.session_state.es_croma:
            tab_examenes, tab_admin_resultados, tab_admin_gestion = st.tabs([
                "📝 Realizar Examen", 
                "📊 Resultados Globales / Edición CROMA", 
                "⚙️ Gestión de Documentos"
            ])
        else:
            tab_examenes, tab_mis_resultados = st.tabs([
                "📝 Realizar Examen", 
                "📊 Mis Resultados y Estado"
            ])
            tab_admin_resultados = None
            tab_admin_gestion = None

        # --- SECCIÓN: REALIZAR EXAMEN ---
        with tab_examenes:
            inicio_mes = datetime.datetime.now().replace(day=1, hour=0, minute=0, second=0).isoformat()
            intentos_mes = supabase.table("intentos_examen").select("*").eq("empleado_id", st.session_state.user_id).gte("fecha_inicio", inicio_mes).execute()
            ya_hizo_examen = len(intentos_mes.data) > 0

            if ya_hizo_examen and not st.session_state.es_croma:
                st.warning("⚠️ Ya has realizado tu evaluación de este mes. Revisa la pestaña 'Mis Resultados y Estado'.")
            else:
                try:
                    res_examenes = supabase.table("examenes").select("id, apartado, preguntas_json").execute()
                    examenes_disponibles = res_examenes.data if res_examenes.data else []
                except Exception as e:
                    examenes_disponibles = []
                    st.error(f"Error al cargar exámenes: {e}")

                if examenes_disponibles:
                    st.subheader("📋 Seleccionar Modalidad")
                    tab_global, tab_individual = st.tabs(["🌐 Examen Global (3 preguntas x apartado)", "📌 Examen por Apartado (15 de 50)"])
                    
                    with tab_global:
                        st.info(f"Se seleccionarán **3 preguntas de cada uno de los {len(examenes_disponibles)} apartados**.")
                        if st.button("Comenzar Examen Global Combinado"):
                            preguntas_preparadas = []
                            nombres_apartados = []
                            
                            for ex_obj in examenes_disponibles:
                                apartado_nombre = ex_obj["apartado"]
                                nombres_apartados.append(apartado_nombre)
                                banco_completo = ex_obj["preguntas_json"]
                                
                                num_a_seleccionar = min(3, len(banco_completo))
                                preguntas_elegidas = random.sample(banco_completo, num_a_seleccionar)
                                
                                for p in preguntas_elegidas:
                                    idx_correcta = p["respuesta_correcta"]
                                    texto_correcto = p["opciones"][idx_correcta]
                                    opciones_shuffled = p["opciones"].copy()
                                    random.shuffle(opciones_shuffled)
                                    
                                    preguntas_preparadas.append({
                                        "apartado": apartado_nombre,
                                        "pregunta": p["pregunta"],
                                        "opciones_barajadas": opciones_shuffled,
                                        "respuesta_correcta_texto": texto_correcto,
                                        "pista": p.get("pista", "Revisa los conceptos clave.")
                                    })
                            
                            random.shuffle(preguntas_preparadas)
                            st.session_state.examen_id = 0
                            st.session_state.apartado_actual = "GLOBAL: " + ", ".join(nombres_apartados)
                            st.session_state.preguntas_seleccionadas = preguntas_preparadas
                            st.session_state.indice_pregunta = 0
                            st.session_state.respuestas_detalle = []
                            st.session_state.sobrepaso_tiempo_global = False
                            st.session_state.tiempo_inicio_examen = time.time()
                            st.session_state.tiempo_inicio_pregunta = time.time()
                            st.session_state.comodines_restantes = 3
                            st.session_state.pistas_activadas = set()
                            st.session_state.examen_activo = True
                            st.rerun()

                    with tab_individual:
                        opciones_apartados = {ex["apartado"]: ex for ex in examenes_disponibles}
                        apartado_sel = st.selectbox("Selecciona un apartado:", list(opciones_apartados.keys()))
                        
                        if st.button("Comenzar Examen del Apartado"):
                            ex_obj = opciones_apartados[apartado_sel]
                            banco_50 = ex_obj["preguntas_json"]
                            seleccion_15 = seleccionar_15_preguntas(banco_50)
                            preguntas_preparadas = []
                            
                            for p in seleccion_15:
                                idx_correcta = p["respuesta_correcta"]
                                texto_correcto = p["opciones"][idx_correcta]
                                opciones_shuffled = p["opciones"].copy()
                                random.shuffle(opciones_shuffled)
                                
                                preguntas_preparadas.append({
                                    "apartado": apartado_sel,
                                    "pregunta": p["pregunta"],
                                    "opciones_barajadas": opciones_shuffled,
                                    "respuesta_correcta_texto": texto_correcto,
                                    "pista": p.get("pista", "Revisa los conceptos clave.")
                                })
                            
                            st.session_state.examen_id = ex_obj["id"] if isinstance(ex_obj["id"], int) else 0
                            st.session_state.apartado_actual = apartado_sel
                            st.session_state.preguntas_seleccionadas = preguntas_preparadas
                            st.session_state.indice_pregunta = 0
                            st.session_state.respuestas_detalle = []
                            st.session_state.sobrepaso_tiempo_global = False
                            st.session_state.tiempo_inicio_examen = time.time()
                            st.session_state.tiempo_inicio_pregunta = time.time()
                            st.session_state.comodines_restantes = 3
                            st.session_state.pistas_activadas = set()
                            st.session_state.examen_activo = True
                            st.rerun()
                else:
                    st.warning("No hay exámenes disponibles en el sistema.")

        # --- SECCIÓN: VISTA USUARIO NORMAL ---
        if not st.session_state.es_croma:
            with tab_mis_resultados:
                st.subheader("📌 Mis Calificaciones e Historial")
                
                res_mis_intentos = supabase.table("intentos_examen").select("*").eq("empleado_id", st.session_state.user_id).order("fecha_inicio", desc=True).execute()
                mis_intentos = res_mis_intentos.data if res_mis_intentos.data else []
                
                dias_restantes = obtener_dias_restantes_mes()
                
                st.info(f"📅 **Habilitación de Examen:** Te quedan **{dias_restantes} días** para realizar la evaluación correspondiente al próximo ciclo mensual.")
                
                if mis_intentos:
                    tabla_datos = []
                    for i in mis_intentos:
                        fecha_str = i["fecha_inicio"][:10] if i.get("fecha_inicio") else "N/A"
                        porc = i.get("porcentaje_obtenido", 0)
                        estado = "🟢 APROBADO" if porc >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
                        
                        tabla_datos.append({
                            "Fecha": fecha_str,
                            "Materia / Apartado": i.get("apartado", "General"),
                            "Nota (0-10)": i.get("nota", 0),
                            "Porcentaje": f"{porc}%",
                            "Resultado": estado
                        })
                    
                    st.table(tabla_datos)
                else:
                    st.write("Aún no has realizado ningún examen.")

        # --- SECCIÓN: ADMIN CROMA (RESULTADOS Y EDICIÓN DE PREGUNTAS) ---
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Historial General y Edición por Usuario")
                
                res_todos = supabase.table("intentos_examen").select("*").order("fecha_inicio", desc=True).execute()
                todos_intentos = res_todos.data if res_todos.data else []
                
                if todos_intentos:
                    tabla_admin = []
                    for it in todos_intentos:
                        tabla_admin.append({
                            "ID Intento": it["id"],
                            "Empleado": it.get("nombre_empleado", "N/A"),
                            "Apartado": it.get("apartado", "General"),
                            "Nota": it.get("nota", 0),
                            "Porcentaje": f"{it.get('porcentaje_obtenido', 0)}%",
                            "Estado": "🟢 APROBADO" if it.get('porcentaje_obtenido', 0) >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO",
                            "Fecha": it.get("fecha_inicio", "")[:10]
                        })
                    
                    st.write("### Exámenes Realizados por Todos los Empleados")
                    st.table(tabla_admin)
                    
                    st.markdown("---")
                    st.subheader("✏️ Modificar Pregunta Respondida por un Empleado")
                    
                    dict_intentos = {f"Intento #{it['id']} - {it.get('nombre_empleado')} ({it.get('apartado')})": it for it in todos_intentos}
                    intento_sel_key = st.selectbox("Selecciona el intento a editar:", list(dict_intentos.keys()))
                    intento_obj = dict_intentos[intento_sel_key]
                    
                    respuestas_lista = intento_obj.get("respuestas_usuario", [])
                    
                    if respuestas_lista:
                        dict_preguntas = {f"P{idx+1}: {p['pregunta'][:50]}...": idx for idx, p in enumerate(respuestas_lista)}
                        p_sel_key = st.selectbox("Selecciona la pregunta a modificar:", list(dict_preguntas.keys()))
                        p_idx = dict_preguntas[p_sel_key]
                        p_objetivo = respuestas_lista[p_idx]
                        
                        st.write(f"**Pregunta completa:** {p_objetivo['pregunta']}")
                        st.write(f"**Respuesta actual elegida:** {p_objetivo.get('opcion_elegida')}")
                        st.write(f"**Estado actual:** {'Correcta' if p_objetivo.get('es_correcta') else 'Incorrecta'}")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            nuevo_estado_correcta = st.checkbox("¿Marcar como correcta?", value=p_objetivo.get("es_correcta", False))
                            nueva_opcion_texto = st.text_input("Nueva opción elegida (opcional):", value=p_objetivo.get("opcion_elegida", ""))
                        
                        with col2:
                            editor_nombre = st.text_input("Nombre de la persona que edita:", value=st.session_state.user_nombre)
                            motivo_edicion = st.text_area("Motivo de la edición (obligatorio):")
                        
                        if st.button("Guardar Cambios Auditados"):
                            if not motivo_edicion.strip():
                                st.error("❌ El motivo de la edición es obligatorio.")
                            else:
                                fecha_hora_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                                
                                # Actualizar la pregunta
                                respuestas_lista[p_idx]["es_correcta"] = nuevo_estado_correcta
                                respuestas_lista[p_idx]["opcion_elegida"] = nueva_opcion_texto
                                respuestas_lista[p_idx]["audit_edicion"] = {
                                    "editado_por": editor_nombre,
                                    "fecha_hora": fecha_hora_utc,
                                    "motivo": motivo_edicion
                                }
                                
                                # Recalcular nota y porcentaje
                                total_preg = len(respuestas_lista)
                                nuevas_correctas = sum(1 for r in respuestas_lista if r["es_correcta"])
                                nuevo_porcentaje = round((nuevas_correctas / total_preg) * 100, 2)
                                nueva_nota = round((nuevas_correctas / total_preg) * 10, 2)
                                
                                try:
                                    supabase.table("intentos_examen").update({
                                        "respuestas_usuario": respuestas_lista,
                                        "nota": nueva_nota,
                                        "porcentaje_obtenido": nuevo_porcentaje
                                    }).eq("id", intento_obj["id"]).execute()
                                    
                                    st.success(f"✅ Respuesta modificada correctamente. Nueva nota recalculada: **{nueva_nota} / 10** ({nuevo_porcentaje}%). Auditoría guardada a las {fecha_hora_utc}.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al actualizar intento: {e}")
                    else:
                        st.info("El intento seleccionado no contiene detalle de respuestas.")
                else:
                    st.info("No hay registro de exámenes realizados.")

        # --- SECCIÓN: ADMIN CROMA (GESTIÓN DE DOCUMENTOS) ---
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Panel de Administración - Documentos")
                
                col_gen, col_del = st.columns(2)
                
                with col_gen:
                    st.write("### 📥 Cargar PDF y Generar Banco (50 Preguntas)")
                    archivo_pdf = st.file_uploader("Cargar PDF con manual operativo", type=["pdf"])
                    nombre_apartado = st.text_input("Nombre de la materia/apartado")
                    
                    if st.button("Procesar e Insertar 50 Preguntas con IA"):
                        if archivo_pdf and nombre_apartado:
                            try:
                                reader = PdfReader(archivo_pdf)
                                texto = "".join([page.extract_text() or "" for page in reader.pages])
                                
                                prompt = """Genera un banco de EXACTAMENTE 50 preguntas tipo test basadas en el documento.

Requisitos estrictos para el JSON:
1. "es_principal": Marca como true ÚNICAMENTE en las 5 preguntas más fundamentales de todo el documento. El resto debe ser false.
2. "dificultad": Asigna equitativamente "facil", "media" o "dificil".
3. "pista": Incluye una pista breve (máx 2 frases) sin revelar la opción correcta.

Responde ÚNICAMENTE con un array JSON estructurado así:
[
  {
    "pregunta": "texto de la pregunta",
    "opciones": ["Opcion A", "Opcion B", "Opcion C"],
    "respuesta_correcta": 0,
    "pista": "pista explicativa sin decir la respuesta",
    "es_principal": true,
    "dificultad": "media",
    "tipo": "test"
  }
]

Texto del documento:
""" + texto[:8000]

                                modelos = ['gemini-3.6-flash', 'gemini-3.1-flash', 'gemini-3.5-flash-lite']
                                res = None
                                
                                with st.spinner("Generando banco de 50 preguntas con metadatos de dificultad y pistas..."):
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
                                                    time.sleep(2)
                                                else:
                                                    raise err
                                        if exito:
                                            break

                                if res and res.text:
                                    preguntas_json = json.loads(res.text)
                                    
                                    supabase.table("examenes").insert({
                                        "apartado": nombre_apartado, 
                                        "preguntas_json": preguntas_json
                                    }).execute()
                                    
                                    st.success(f"✅ Se generaron {len(preguntas_json)} preguntas en el banco de '{nombre_apartado}'.")
                                    st.rerun()
                                else:
                                    st.error("❌ El servicio de IA está saturado. Inténtalo en un minuto.")

                            except Exception as e:
                                st.error(f"❌ Error al generar el examen: {e}")
                        else:
                            st.error("Sube un PDF e introduce un nombre de apartado.")

                with col_del:
                    st.write("### 🗑️ Eliminar Documentos / Apartados")
                    res_ex_del = supabase.table("examenes").select("id, apartado").execute()
                    examenes_del = res_ex_del.data if res_ex_del.data else []
                    
                    if examenes_del:
                        dict_borrado = {f"{ex['apartado']} (ID: {ex['id']})": ex['id'] for ex in examenes_del}
                        doc_a_eliminar = st.selectbox("Selecciona apartado a borrar:", list(dict_borrado.keys()))
                        
                        if st.button("🔴 Eliminar Documento Seleccionado"):
                            id_borrar = dict_borrado[doc_a_eliminar]
                            try:
                                supabase.table("intentos_examen").delete().eq("examen_id", id_borrar).execute()
                                supabase.table("examenes").delete().eq("id", id_borrar).execute()
                                
                                st.success(f"✅ Apartado '{doc_a_eliminar}' e historial borrados con éxito.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al eliminar apartado: {e}")
                    else:
                        st.info("No hay documentos guardados para eliminar.")
