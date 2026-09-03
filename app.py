import streamlit as st
import datetime
import json
import time
import random
import os
import calendar
import io
import pandas as pd
from google import genai
from google.genai import types
from pypdf import PdfReader
from supabase import create_client, Client

# Dependencias para generar PDF
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    REPORTLAB_DISPONIBLE = True
except ImportError:
    REPORTLAB_DISPONIBLE = False

# ---------------------------------------------------------
# CONFIGURACIÓN PÁGINA Y CONEXIONES
# ---------------------------------------------------------
st.set_page_config(page_title="Plataforma de Exámenes", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    .stRadio label {
        font-size: 20px !important;
        font-weight: 500 !important;
    }
    .stRadio div[role='radiogroup'] > label {
        font-size: 18px !important;
        margin-bottom: 8px !important;
    }
    .pregunta-titulo {
        font-size: 24px !important;
        font-weight: bold !important;
        color: #1A365D;
    }
    </style>
""", unsafe_allow_html=True)

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
if "usuario_modal_sel" not in st.session_state:
    st.session_state.usuario_modal_sel = None

# Estado del examen y tiempos
if "examen_activo" not in st.session_state:
    st.session_state.examen_activo = False
if "modo_revision" not in st.session_state:
    st.session_state.modo_revision = False
if "modificando_desde_revision" not in st.session_state:
    st.session_state.modificando_desde_revision = False
if "tiempos_restantes_preguntas" not in st.session_state:
    st.session_state.tiempos_restantes_preguntas = {}
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


def seleccionar_preguntas_por_subindice(banco_completo, num_por_subindice=3):
    subindices = {}
    for p in banco_completo:
        sub = p.get("subindice", "General")
        subindices.setdefault(sub, []).append(p)
    
    seleccionadas = []
    for sub, lista_p in subindices.items():
        sample_size = min(len(lista_p), num_por_subindice)
        seleccionadas.extend(random.sample(lista_p, sample_size))
        
    random.shuffle(seleccionadas)
    return seleccionadas


def obtener_dias_restantes_mes():
    ahora = datetime.datetime.now()
    _, ultimo_dia = calendar.monthrange(ahora.year, ahora.month)
    return ultimo_dia - ahora.day + 1


def generar_pdf_resultado(intento):
    """Genera un archivo PDF binario con el resumen del examen y sus fallos."""
    if not REPORTLAB_DISPONIBLE:
        return None
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    titulo_style = ParagraphStyle('Titulo', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor("#1A365D"), spaceAfter=10)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=11, leading=14, textColor=colors.HexColor("#4A5568"), spaceAfter=15)
    bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=10, leading=13, fontName="Helvetica-Bold")
    norm_style = ParagraphStyle('Norm', parent=styles['Normal'], fontSize=10, leading=13)
    err_style = ParagraphStyle('Err', parent=styles['Normal'], fontSize=10, leading=13, textColor=colors.HexColor("#C53030"))

    story.append(Paragraph("Informe de Evaluación de Examen", titulo_style))
    fecha_txt = intento.get("fecha_inicio", "")[:10] if intento.get("fecha_inicio") else "N/A"
    story.append(Paragraph(f"<b>Empleado:</b> {intento.get('nombre_empleado')} | <b>Fecha:</b> {fecha_txt} | <b>Apartado:</b> {intento.get('apartado')}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=15))

    respuestas = intento.get("respuestas_usuario", [])
    total_p = len(respuestas) if respuestas else 1
    correctas = sum(1 for r in respuestas if r.get("es_correcta"))
    porcentaje = intento.get("porcentaje_obtenido", 0)
    estado_txt = "APROBADO" if porcentaje >= UMBRAL_APROBADO_PORCENTAJE else "SUSPENSO"

    data_res = [
        [Paragraph("<b>Aciertos</b>", norm_style), Paragraph(f"{correctas} / {total_p}", norm_style)],
        [Paragraph("<b>Porcentaje</b>", norm_style), Paragraph(f"{porcentaje}%", norm_style)],
        [Paragraph("<b>Nota Final</b>", norm_style), Paragraph(f"{intento.get('nota', 0)} / 10", norm_style)],
        [Paragraph("<b>Estado</b>", norm_style), Paragraph(f"<b>{estado_txt}</b>", bold_style)]
    ]
    t = Table(data_res, colWidths=[150, 350])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))

    erroneas = [r for r in respuestas if not r.get("es_correcta")]
    if erroneas:
        story.append(Paragraph("<b>Desglose de Preguntas Erróneas o Sin Responder:</b>", bold_style))
        story.append(Spacer(1, 8))
        for idx_e, err in enumerate(erroneas, 1):
            story.append(Paragraph(f"<b>{idx_e}. {err.get('pregunta')}</b>", norm_style))
            story.append(Paragraph(f"Respuesta registrada: <i>{err.get('opcion_elegida')}</i>", err_style))
            story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("<b>¡Examen perfecto! Sin errores registrados.</b>", bold_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------
# DIÁLOGO DE AUTENTICACIÓN
# ---------------------------------------------------------
@st.dialog("🔒 Confirmar Contraseña")
def login_modal():
    usuario = st.session_state.usuario_modal_sel
    st.write(f"Accediendo como: **{usuario['nombre']}**")
    
    with st.form("form_login_modal"):
        pwd_input = st.text_input(
            "Introduce tu contraseña:", 
            type="password", 
            key="modal_pwd_input",
            autocomplete="current-password"
        )
        submitted = st.form_submit_button("Ingresar")
        
        if submitted:
            if usuario["password_hash"] == pwd_input:
                st.session_state.user_id = usuario["id"]
                st.session_state.user_nombre = usuario["nombre"]
                st.session_state.es_croma = usuario.get("es_admin_croma", False)
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta.")


# ---------------------------------------------------------
# MÓDULO 1: AUTENTICACIÓN
# ---------------------------------------------------------
st.title("📝 Sistema de Evaluación Mensual")

if not st.session_state.autenticado:
    st.subheader("Selecciona tu perfil para ingresar")
    
    try:
        res_usuarios = supabase.table("empleados").select("*").execute()
        lista_usuarios = res_usuarios.data if res_usuarios.data else []
    except Exception as e:
        lista_usuarios = []
        st.error(f"Error al conectar con la base de datos: {e}")

    if lista_usuarios:
        cols = st.columns(3)
        for idx, u in enumerate(lista_usuarios):
            with cols[idx % 3]:
                st.markdown(f"### 👤 {u['nombre']}")
                st.caption("Administrador" if u.get("es_admin_croma") else "Empleado")
                if st.button("Acceder", key=f"usr_btn_{u['id']}"):
                    st.session_state.usuario_modal_sel = u
                    login_modal()
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
            st.session_state.modo_revision = False
            st.rerun()
        
    st.markdown("---")
    
    # MODO REVISIÓN PREVIA A FINALIZAR
    if st.session_state.modo_revision:
        st.subheader("🔍 Revisión de Examen previa a la entrega final")
        st.info("Puedes pulsar en cualquier pregunta para volver a responderla o corregirla antes de guardar.")

        for i, p_item in enumerate(st.session_state.preguntas_seleccionadas):
            resp_actual = next((r for r in st.session_state.respuestas_detalle if r["idx_pregunta"] == i), None)
            texto_resp = resp_actual["opcion_elegida"] if resp_actual else "En blanco (Sin responder)"
            
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"**Pregunta {i+1}:** {p_item['pregunta']}")
                st.caption(f"Respuesta actual: **{texto_resp}**")
            with c2:
                if st.button("Modificar", key=f"mod_rev_{i}"):
                    st.session_state.indice_pregunta = i
                    st.session_state.modo_revision = False
                    st.session_state.modificando_desde_revision = True
                    st.session_state.tiempo_inicio_pregunta = time.time()
                    st.rerun()
            st.write("---")

        if st.button("✅ Confirmar y Entregar Examen Definitivamente"):
            total_p = len(st.session_state.preguntas_seleccionadas)
            correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
            porcentaje = round((correctas / total_p) * 100, 2)
            nota_final = round((correctas / total_p) * 10, 2)
            
            duracion_total = int(time.time() - st.session_state.tiempo_inicio_examen)
            tiempo_limite_total = total_p * TIEMPO_LIMITE_PREGUNTA
            tiempo_fin_examen = datetime.datetime.now(datetime.timezone.utc)
            
            try:
                id_examen_validado = st.session_state.examen_id if isinstance(st.session_state.examen_id, int) and st.session_state.examen_id > 0 else None

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
                st.success(f"🎉 Examen completado: **{correctas} / {total_p} acertadas ({porcentaje}%)**")
            except Exception as e:
                st.error(f"Error guardando intento: {e}")
                
            st.session_state.examen_activo = False
            st.session_state.modo_revision = False
            if st.button("Volver al Inicio"):
                st.rerun()

    # CUESTIONARIO ACTIVO
    elif st.session_state.examen_activo:
        idx = st.session_state.indice_pregunta
        total_p = len(st.session_state.preguntas_seleccionadas)
        
        if idx < total_p:
            p_actual = st.session_state.preguntas_seleccionadas[idx]
            
            col_info, col_ayuda = st.columns([3, 2])
            with col_info:
                st.subheader(f"Pregunta {idx + 1} de {total_p}")
                st.caption(f"📌 **Subíndice/Apartado:** {p_actual.get('subindice', p_actual.get('apartado', 'General'))}")
            with col_ayuda:
                st.caption(f"💡 Ayudas disponibles: **{st.session_state.comodines_restantes} / 3**")

            tiempo_base = st.session_state.tiempos_restantes_preguntas.get(idx, TIEMPO_LIMITE_PREGUNTA)
            tiempo_transcurrido = int(time.time() - st.session_state.tiempo_inicio_pregunta)
            tiempo_restante = tiempo_base - tiempo_transcurrido
            
            st.progress(max(0.0, tiempo_restante / TIEMPO_LIMITE_PREGUNTA))
            
            if tiempo_restante > 0:
                st.caption(f"⏱️ Tiempo restante: **{tiempo_restante} segundos**")
            else:
                st.warning("⏰ ¡Tiempo agotado en esta pregunta!")
                st.session_state.sobrepaso_tiempo_global = True
                st.session_state.tiempos_restantes_preguntas[idx] = 0
                
                if not st.session_state.modificando_desde_revision:
                    st.session_state.respuestas_detalle = [r for r in st.session_state.respuestas_detalle if r["idx_pregunta"] != idx]
                    st.session_state.respuestas_detalle.append({
                        "idx_pregunta": idx,
                        "pregunta": p_actual["pregunta"],
                        "opcion_elegida": "En blanco (Agotado tiempo)",
                        "es_correcta": False
                    })
                    st.session_state.indice_pregunta += 1
                    st.session_state.tiempo_inicio_pregunta = time.time()
                    st.rerun()

            st.markdown(f"<p class='pregunta-titulo'>{p_actual['pregunta']}</p>", unsafe_allow_html=True)
            
            if p_actual.get("tipo") == "practica_imagen" and p_actual.get("imagen_url"):
                st.image(p_actual["imagen_url"], caption="Imagen del Ejercicio Práctico", use_container_width=True)

            resp_previa = next((r["opcion_elegida"] for r in st.session_state.respuestas_detalle if r["idx_pregunta"] == idx), None)
            idx_previa = None
            if resp_previa and resp_previa in p_actual["opciones_barajadas"]:
                idx_previa = p_actual["opciones_barajadas"].index(resp_previa)

            eleccion = st.radio("Selecciona una opción:", p_actual["opciones_barajadas"], index=idx_previa, key=f"p_{idx}")
            
            if idx in st.session_state.pistas_activadas:
                pista_texto = p_actual.get("pista", "Lee con atención las opciones y descarta las inconsistentes.")
                st.info(f"💡 **Pista:** {pista_texto}")
            else:
                if st.session_state.comodines_restantes > 0:
                    if st.button("💡 Pedir Ayuda (Gasta 1 comodín)", key=f"btn_pista_{idx}"):
                        st.session_state.comodines_restantes -= 1
                        st.session_state.pistas_activadas.add(idx)
                        st.rerun()
                else:
                    st.caption("🚫 Has agotado tus 3 comodines de ayuda.")

            st.write("")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Responder / Siguiente", key=f"btn_sig_{idx}"):
                    st.session_state.tiempos_restantes_preguntas[idx] = max(0, tiempo_restante)
                    st.session_state.modificando_desde_revision = False
                    
                    if eleccion is None or eleccion == "":
                        es_correcta = False
                        opcion_guardada = "En blanco (Sin marcar)"
                    else:
                        es_correcta = (eleccion == p_actual["respuesta_correcta_texto"])
                        opcion_guardada = eleccion
                    
                    st.session_state.respuestas_detalle = [r for r in st.session_state.respuestas_detalle if r["idx_pregunta"] != idx]
                    st.session_state.respuestas_detalle.append({
                        "idx_pregunta": idx,
                        "pregunta": p_actual["pregunta"],
                        "opcion_elegida": opcion_guardada,
                        "es_correcta": es_correcta
                    })
                    
                    st.session_state.indice_pregunta += 1
                    st.session_state.tiempo_inicio_pregunta = time.time()
                    st.rerun()

            with col_b2:
                if st.button("📋 Ir a Revisión", key=f"btn_rev_{idx}"):
                    st.session_state.tiempos_restantes_preguntas[idx] = max(0, tiempo_restante)
                    st.session_state.modificando_desde_revision = False
                    st.session_state.modo_revision = True
                    st.rerun()

            if tiempo_restante > 0:
                time.sleep(1)
                st.rerun()

        else:
            st.session_state.modo_revision = True
            st.rerun()

    # MENÚ PRINCIPAL
    else:
        if st.session_state.es_croma:
            tab_examenes, tab_admin_resultados, tab_admin_export, tab_admin_gestion = st.tabs([
                "📝 Realizar Examen", 
                "📊 Resultados / Edición", 
                "📥 Exportación e Informes",
                "⚙️ Gestión de Documentos"
            ])
        else:
            tab_examenes, tab_mis_resultados = st.tabs([
                "📝 Realizar Examen", 
                "📊 Mis Resultados y Estado"
            ])

        with tab_examenes:
            # Obtener exámenes realizados por el usuario en el año actual
            anio_actual = datetime.datetime.now().year
            inicio_anio = f"{anio_actual}-01-01T00:00:00"
            
            res_user_intentos = supabase.table("intentos_examen").select("*").eq("empleado_id", st.session_state.user_id).gte("fecha_inicio", inicio_anio).execute()
            user_intentos = res_user_intentos.data if res_user_intentos.data else []

            # Mapeo de apartados realizados y su nota
            dict_realizados = {}
            for it in user_intentos:
                apt = it.get("apartado")
                if apt:
                    dict_realizados[apt] = {
                        "nota": it.get("nota", 0),
                        "porcentaje": it.get("porcentaje_obtenido", 0)
                    }

            try:
                res_examenes = supabase.table("examenes").select("id, apartado, preguntas_json").execute()
                examenes_disponibles = res_examenes.data if res_examenes.data else []
            except Exception as e:
                examenes_disponibles = []
                st.error(f"Error al cargar manuales: {e}")

            if examenes_disponibles:
                st.subheader("📋 Seleccionar Modalidad")
                tab_global, tab_manual = st.tabs(["🌐 Examen Global (2 por Subíndice + 5 Prácticas)", "📘 Examen por Manual"])
                
                with tab_global:
                    st.info("El Examen Global incluirá **2 preguntas teóricas por cada subíndice** de todos los manuales y **5 ejercicios prácticos**.")
                    
                    if "GLOBAL COMPLETO" in dict_realizados:
                        info_g = dict_realizados["GLOBAL COMPLETO"]
                        st.success(f"✅ **REALIZADO ({anio_actual})** — Nota obtenida: **{info_g['nota']} / 10** ({info_g['porcentaje']}%)")
                    
                    if st.button("Comenzar Examen Global Combinado"):
                        preguntas_preparadas = []
                        
                        for ex_obj in examenes_disponibles:
                            banco = ex_obj["preguntas_json"]
                            elegidas_sub = seleccionar_preguntas_por_subindice(banco, num_por_subindice=2)
                            
                            for p in elegidas_sub:
                                idx_c = p["respuesta_correcta"]
                                texto_c = p["opciones"][idx_c]
                                opciones_shuffled = p["opciones"].copy()
                                random.shuffle(opciones_shuffled)
                                
                                preguntas_preparadas.append({
                                    "apartado": ex_obj["apartado"],
                                    "subindice": p.get("subindice", "General"),
                                    "pregunta": p["pregunta"],
                                    "opciones_barajadas": opciones_shuffled,
                                    "respuesta_correcta_texto": texto_c,
                                    "pista": p.get("pista", "Revisa los conceptos clave."),
                                    "tipo": "teorica"
                                })
                        
                        practicas_ejemplo = [
                            {
                                "subindice": "Práctica Operativa",
                                "pregunta": f"Ejercicio Práctico {i+1}: Identifica el parámetro o valor correcto reflejado en la imagen.",
                                "opciones_barajadas": ["Parámetro Normal (100)", "Exceso de Límite (150)", "Valor Crítico (200)", "Sin Lectura"],
                                "respuesta_correcta_texto": "Parámetro Normal (100)",
                                "imagen_url": "https://via.placeholder.com/600x300.png?text=Ejercicio+Practico+Imagen",
                                "pista": "Observa las especificaciones del panel técnico.",
                                "tipo": "practica_imagen"
                            } for i in range(5)
                        ]
                        
                        preguntas_preparadas.extend(practicas_ejemplo)
                        random.shuffle(preguntas_preparadas)
                        
                        st.session_state.examen_id = None
                        st.session_state.apartado_actual = "GLOBAL COMPLETO"
                        st.session_state.preguntas_seleccionadas = preguntas_preparadas
                        st.session_state.indice_pregunta = 0
                        st.session_state.respuestas_detalle = []
                        st.session_state.tiempos_restantes_preguntas = {}
                        st.session_state.modificando_desde_revision = False
                        st.session_state.tiempo_inicio_examen = time.time()
                        st.session_state.tiempo_inicio_pregunta = time.time()
                        st.session_state.comodines_restantes = 3
                        st.session_state.pistas_activadas = set()
                        st.session_state.examen_activo = True
                        st.rerun()

                with tab_manual:
                    st.subheader("Selecciona el Manual para la Evaluación")
                    cols_m = st.columns(2)
                    for idx_m, ex_obj in enumerate(examenes_disponibles):
                        nombre_apt = ex_obj['apartado']
                        with cols_m[idx_m % 2]:
                            st.markdown(f"### 📘 {nombre_apt}")
                            
                            # Indicador visual de realizado para no administradores
                            if nombre_apt in dict_realizados:
                                info_m = dict_realizados[nombre_apt]
                                st.success(f"✅ **REALIZADO ({anio_actual})** — Nota: **{info_m['nota']} / 10**")
                            
                            if st.button(f"Iniciar Examen de {nombre_apt}", key=f"btn_manual_{ex_obj['id']}"):
                                banco = ex_obj["preguntas_json"]
                                seleccion_3_sub = seleccionar_preguntas_por_subindice(banco, num_por_subindice=3)
                                
                                preguntas_preparadas = []
                                for p in seleccion_3_sub:
                                    idx_c = p["respuesta_correcta"]
                                    texto_c = p["opciones"][idx_c]
                                    opciones_shuffled = p["opciones"].copy()
                                    random.shuffle(opciones_shuffled)
                                    
                                    preguntas_preparadas.append({
                                        "apartado": nombre_apt,
                                        "subindice": p.get("subindice", "General"),
                                        "pregunta": p["pregunta"],
                                        "opciones_barajadas": opciones_shuffled,
                                        "respuesta_correcta_texto": texto_c,
                                        "pista": p.get("pista", "Revisa la documentación técnica."),
                                        "tipo": "teorica"
                                    })
                                
                                st.session_state.examen_id = ex_obj["id"]
                                st.session_state.apartado_actual = nombre_apt
                                st.session_state.preguntas_seleccionadas = preguntas_preparadas
                                st.session_state.indice_pregunta = 0
                                st.session_state.respuestas_detalle = []
                                st.session_state.tiempos_restantes_preguntas = {}
                                st.session_state.modificando_desde_revision = False
                                st.session_state.tiempo_inicio_examen = time.time()
                                st.session_state.tiempo_inicio_pregunta = time.time()
                                st.session_state.comodines_restantes = 3
                                st.session_state.pistas_activadas = set()
                                st.session_state.examen_activo = True
                                st.rerun()
            else:
                st.warning("No hay manuales cargados en el sistema.")

        # VISTA USUARIO: MIS RESULTADOS Y DESCARGA DE PDF
        if not st.session_state.es_croma:
            with tab_mis_resultados:
                st.subheader("📌 Mis Calificaciones e Historial")
                
                res_mis_intentos = supabase.table("intentos_examen").select("*").eq("empleado_id", st.session_state.user_id).order("fecha_inicio", desc=True).execute()
                mis_intentos = res_mis_intentos.data if res_mis_intentos.data else []
                
                dias_restantes = obtener_dias_restantes_mes()
                st.info(f"📅 **Habilitación de Examen:** Quedan **{dias_restantes} días** para finalizar el ciclo de evaluación.")
                
                if mis_intentos:
                    for i in mis_intentos:
                        fecha_str = i["fecha_inicio"][:10] if i.get("fecha_inicio") else "N/A"
                        porc = i.get("porcentaje_obtenido", 0)
                        respuestas = i.get("respuestas_usuario", [])
                        num_correctas = sum(1 for r in respuestas if r.get("es_correcta"))
                        total_p = len(respuestas) if respuestas else 15
                        
                        estado = "🟢 APROBADO" if porc >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
                        
                        with st.expander(f"Examen #{i['id']} - {i.get('apartado')} | {fecha_str} | Nota: {i.get('nota', 0)}/10 ({porc}%) - {estado}"):
                            st.write(f"**Resultado:** {num_correctas} / {total_p} aciertos ({porc}%)")
                            
                            pdf_bytes = generar_pdf_resultado(i)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Descargar Informe PDF de Resultados",
                                    data=pdf_bytes,
                                    file_name=f"resultado_examen_{i['id']}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_usr_{i['id']}"
                                )
                            
                            erroneas = [r for r in respuestas if not r.get("es_correcta")]
                            if erroneas:
                                st.write("### ❌ Preguntas Erróneas o En Blanco:")
                                for idx_e, err in enumerate(erroneas, 1):
                                    st.write(f"**{idx_e}. {err.get('pregunta')}**")
                                    st.caption(f"Tu respuesta: `{err.get('opcion_elegida')}`")
                            else:
                                st.success("¡Excelente! No cometiste ningún error en este examen.")
                else:
                    st.write("Aún no has realizado ningún examen.")

        # ADMIN CROMA - RESULTADOS CON FILTRO POR AÑO
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Historial General y Edición por Usuario")
                
                # Cargar todos los intentos para extrae los años disponibles
                res_todos = supabase.table("intentos_examen").select("*").order("fecha_inicio", desc=True).execute()
                todos_intentos = res_todos.data if res_todos.data else []
                
                if todos_intentos:
                    # Extraer lista de años únicos
                    anios_disponibles = sorted(
                        list(set(int(it["fecha_inicio"][:4]) for it in todos_intentos if it.get("fecha_inicio"))),
                        reverse=True
                    )
                    
                    anio_sel = st.selectbox("📅 Filtrar exámenes por año:", anios_disponibles)
                    
                    # Filtrar intentos por el año seleccionado
                    intentos_filtrados = [
                        it for it in todos_intentos 
                        if it.get("fecha_inicio") and int(it["fecha_inicio"][:4]) == anio_sel
                    ]
                    
                    st.write(f"Se encontraron **{len(intentos_filtrados)}** exámenes realizados en el año **{anio_sel}**.")
                    
                    if intentos_filtrados:
                        dict_intentos = {f"ID #{it['id']} - {it.get('nombre_empleado')} ({it.get('apartado')}) [{it.get('fecha_inicio', '')[:10]}]": it for it in intentos_filtrados}
                        intento_sel_key = st.selectbox("Selecciona un examen para auditar/editar:", list(dict_intentos.keys()))
                        
                        intento_obj = dict_intentos[intento_sel_key]
                        intento_target_id = intento_obj["id"]
                        respuestas_lista = json.loads(json.dumps(intento_obj.get("respuestas_usuario", [])))
                        
                        if respuestas_lista:
                            dict_preguntas = {f"P{idx+1}: {p['pregunta'][:60]}...": idx for idx, p in enumerate(respuestas_lista)}
                            p_sel_key = st.selectbox("Selecciona la pregunta a corregir:", list(dict_preguntas.keys()), key=f"sel_p_{intento_target_id}")
                            
                            p_idx = dict_preguntas[p_sel_key]
                            p_objetivo = respuestas_lista[p_idx]
                            
                            st.info(f"Respuesta seleccionada: **{p_objetivo.get('opcion_elegida')}** | Estado: **{'Correcta' if p_objetivo.get('es_correcta') else 'Incorrecta'}**")
                            
                            nuevo_estado = st.checkbox("Marcar como Correcta", value=p_objetivo.get("es_correcta", False))
                            motivo_edicion = st.text_area("Motivo de la corrección:")
                            
                            if st.button("Guardar Corrección Auditada"):
                                if not motivo_edicion.strip():
                                    st.error("❌ El motivo es obligatorio.")
                                else:
                                    respuestas_lista[p_idx]["es_correcta"] = nuevo_estado
                                    correctas_nuevas = sum(1 for r in respuestas_lista if r["es_correcta"])
                                    total_preg = len(respuestas_lista)
                                    nuevo_porc = round((correctas_nuevas / total_preg) * 100, 2)
                                    nueva_nota = round((correctas_nuevas / total_preg) * 10, 2)
                                    
                                    supabase.table("intentos_examen").update({
                                        "respuestas_usuario": respuestas_lista,
                                        "nota": nueva_nota,
                                        "porcentaje_obtenido": nuevo_porc
                                    }).eq("id", intento_target_id).execute()
                                    
                                    registro_audit = {
                                        "intento_id": intento_target_id,
                                        "usuario_modificador": st.session_state.user_nombre,
                                        "fecha_modificacion": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                        "campo_modificada": f"Pregunta {p_idx+1}: {p_objetivo['pregunta']}",
                                        "valor_anterior": json.dumps({"es_correcta": p_objetivo.get("es_correcta")}),
                                        "valor_nuevo": json.dumps({"es_correcta": nuevo_estado}),
                                        "motivo": motivo_edicion
                                    }
                                    supabase.table("auditoria_modificaciones").insert(registro_audit).execute()
                                    st.success("✅ Cambio registrado y auditado con éxito.")
                                    st.rerun()

        # EXPORTACIÓN CON FILTRO DE AÑO
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación e Informes")
                
                res_todos = supabase.table("intentos_examen").select("*").order("fecha_inicio", desc=False).execute()
                todos_intentos = res_todos.data if res_todos.data else []

                if todos_intentos:
                    anios_exp = sorted(
                        list(set(int(it["fecha_inicio"][:4]) for it in todos_intentos if it.get("fecha_inicio"))),
                        reverse=True
                    )
                    anio_exp_sel = st.selectbox("📅 Seleccionar año para exportación:", anios_exp, key="exp_anio")
                    
                    intentos_exp_filtrados = [
                        it for it in todos_intentos 
                        if it.get("fecha_inicio") and int(it["fecha_inicio"][:4]) == anio_exp_sel
                    ]

                    if intentos_exp_filtrados:
                        opciones_examenes = [
                            f"Examen #{i['id']} - Empleado: {i.get('nombre_empleado')} | {i.get('apartado')} ({i.get('fecha_inicio', '')[:10]})"
                            for i in intentos_exp_filtrados
                        ]
                        
                        opcion_elegida = st.selectbox("Selecciona el examen a exportar:", opciones_examenes)
                        idx_sel = opciones_examenes.index(opcion_elegida)
                        examen_sel = intentos_exp_filtrados[idx_sel]

                        col_exp_a, col_exp_b = st.columns(2)
                        with col_exp_a:
                            if st.button("📊 Generar Excel de este Examen"):
                                df_export = pd.DataFrame([examen_sel])
                                buffer = io.BytesIO()
                                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                    df_export.to_excel(writer, index=False, sheet_name="Examen")
                                
                                st.download_button(
                                    label="📥 Descargar Excel",
                                    data=buffer.getvalue(),
                                    file_name=f"examen_{examen_sel['id']}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )

                        with col_exp_b:
                            pdf_bytes = generar_pdf_resultado(examen_sel)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Descargar Informe PDF",
                                    data=pdf_bytes,
                                    file_name=f"informe_examen_{examen_sel['id']}.pdf",
                                    mime="application/pdf"
                                )

        # ADMIN CROMA - GESTIÓN Y ELIMINACIÓN PRESERVANDO HISTORIAL
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                col_subir, col_del = st.columns([3, 2])
                
                with col_subir:
                    st.subheader("⚙️ Cargar Manual con Subíndices Técnicos")
                    archivo_pdf = st.file_uploader("Cargar PDF del Manual", type=["pdf"])
                    nombre_apartado = st.text_input("Nombre del Manual / Apartado")
                    
                    if st.button("Procesar y Generar Banco estructurado"):
                        if archivo_pdf and nombre_apartado:
                            try:
                                reader = PdfReader(archivo_pdf)
                                texto = "".join([page.extract_text() or "" for page in reader.pages])
                                
                                if not texto.strip():
                                    st.error("❌ No se pudo extraer texto del PDF. Verifica que no sea una imagen escaneada.")
                                    st.stop()

                                prompt = """Genera un banco de EXACTAMENTE 50 preguntas tipo test basadas en el documento.

Requisitos estrictos para el JSON:
1. "es_principal": Marca como true ÚNICAMENTE en las 5 preguntas más fundamentales de todo el documento. El resto debe ser false.
2. "dificultad": Asigna equitativamente "facil", "media" o "dificil".
3. "pista": Incluye una pista breve (máx 2 frases) sin revelar la opción correcta.

Responde ÚNICAMENTE con un array JSON estructurado así:
[
  {
    "pregunta": "texto de la pregunta",
    "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
    "respuesta_correcta": 0,
    "pista": "Texto de la pista de ayuda",
    "tipo": "teorica"
  }
]

Texto del manual:
""" + texto[:8000]

                                modelos = ['gemini-3.6-flash', 'gemini-3.1-flash', 'gemini-3.5-flash-lite']
                                res = None
                                
                                with st.spinner("Generando banco de preguntas con IA..."):
                                    for model_name in modelos:
                                        try:
                                            res = gemini_client.models.generate_content(
                                                model=model_name,
                                                contents=prompt,
                                                config=types.GenerateContentConfig(
                                                    response_mime_type="application/json"
                                                )
                                            )
                                            if res and res.text:
                                                break
                                        except Exception as model_err:
                                            st.warning(f"Reintentando con modelo alternativo... ({model_err})")
                                            time.sleep(1)

                                if res and res.text:
                                    clean_text = res.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                                    preguntas_json = json.loads(clean_text)
                                    
                                    supabase.table("examenes").insert({
                                        "apartado": nombre_apartado, 
                                        "preguntas_json": preguntas_json
                                    }).execute()
                                    
                                    st.success(f"✅ Se generaron {len(preguntas_json)} preguntas en el banco de '{nombre_apartado}'.")
                                    st.rerun()
                                else:
                                    st.error("❌ No se recibió respuesta válida del servicio de IA. Inténtalo de nuevo.")

                            except Exception as e:
                                st.error(f"❌ Error al generar el examen: {e}")
                        else:
                            st.error("Sube un PDF e introduce un nombre de apartado.")

                with col_del:
                    st.subheader("🗑️ Eliminar Documentos / Apartados")
                    res_ex_del = supabase.table("examenes").select("id, apartado").execute()
                    examenes_del = res_ex_del.data if res_ex_del.data else []
                    
                    if examenes_del:
                        dict_borrado = {f"{ex['apartado']} (ID: {ex['id']})": ex['id'] for ex in examenes_del}
                        doc_a_eliminar = st.selectbox("Selecciona apartado a borrar:", list(dict_borrado.keys()))
                        
                        if st.button("🔴 Eliminar Documento Seleccionado"):
                            id_borrar = dict_borrado[doc_a_eliminar]
                            try:
                                # 1. Mantener el historial: Desvincular los intentos sin borrarlos
                                supabase.table("intentos_examen").update({"examen_id": None}).eq("examen_id", id_borrar).execute()
                                
                                # 2. Eliminar el documento de la tabla examenes
                                supabase.table("examenes").delete().eq("id", id_borrar).execute()
                                
                                st.success(f"✅ Apartado '{doc_a_eliminar}' eliminado. Se conserva el historial de exámenes realizados.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al eliminar apartado: {e}")
                    else:
                        st.info("No hay documentos guardados para eliminar.")
