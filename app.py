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
# CONFIGURACIÓN PÁGINA Y ESTILOS HTML / CSS
# ---------------------------------------------------------
st.set_page_config(page_title="Plataforma de Exámenes", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}

    :root {
        --primary-color: #1A365D;
        --secondary-color: #2B6CB0;
        --background-color: #F7FAFC;
        --card-bg: #FFFFFF;
        --text-color: #2D3748;
        --border-radius: 12px;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    .stRadio label {
        font-size: 18px !important;
        font-weight: 500 !important;
        line-height: 1.4 !important;
        color: var(--text-color) !important;
    }
    
    .stRadio div[role='radiogroup'] {
        gap: 10px;
    }

    .stRadio div[role='radiogroup'] > label {
        background-color: #EDF2F7;
        padding: 12px 18px !important;
        border-radius: 8px !important;
        border: 1px solid #CBD5E0 !important;
        transition: all 0.2s ease-in-out;
        width: 100%;
        margin-bottom: 8px !important;
    }

    .stRadio div[role='radiogroup'] > label:hover {
        background-color: #E2E8F0;
        border-color: #A0AEC0 !important;
    }

    .pregunta-titulo {
        font-size: 24px !important;
        font-weight: 700 !important;
        color: #1A365D;
        margin-bottom: 20px;
        line-height: 1.3;
        padding: 15px;
        background-color: #F7FAFC;
        border-left: 5px solid #2B6CB0;
        border-radius: 4px;
    }

    div[data-baseweb="select"] span {
        white-space: normal !important;
        max-width: none !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }
    
    div[data-baseweb="popover"] li {
        white-space: normal !important;
        word-break: break-word !important;
    }

    .user-card {
        background-color: var(--card-bg);
        border: 1px solid #E2E8F0;
        border-radius: var(--border-radius);
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# CREDENCIALES Y CLIENTES
# ---------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"Error al inicializar el cliente de Gemini: {e}")

# ---------------------------------------------------------
# ESTADO DE LA SESIÓN
# ---------------------------------------------------------
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

# Estado del examen
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
NUM_PREGUNTAS_EXAMEN = 15

PROMPT_DEFECTO = """Genera un banco de EXACTAMENTE 50 preguntas tipo test basadas en el documento.

Requisitos strictly para el JSON:
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
"""

MODELOS_GEMINI_DISPONIBLES = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

# ---------------------------------------------------------
# FUNCIONES AUXILIARES
# ---------------------------------------------------------
def limpiar_timestamp_sql(ts_val):
    if pd.isna(ts_val) or ts_val is None:
        return None
    ts_str = str(ts_val).strip()
    if " " in ts_str and "T" in ts_str:
        ts_str = ts_str.split(" ")[0]
    return ts_str

def seleccionar_15_preguntas(banco_completo):
    sample_size = min(len(banco_completo), NUM_PREGUNTAS_EXAMEN)
    seleccionadas = random.sample(banco_completo, sample_size)
    random.shuffle(seleccionadas)
    return seleccionadas

def obtener_dias_restantes_mes():
    ahora = datetime.datetime.now()
    _, ultimo_dia = calendar.monthrange(ahora.year, ahora.month)
    return ultimo_dia - ahora.day + 1

def generar_pdf_resultado(intento):
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
        [Paragraph("<b>Resultado</b>", norm_style), Paragraph(f"<b>{estado_txt}</b>", bold_style)]
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
st.title("📝 Plataforma de Evaluación y Exámenes")

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
                st.markdown(f"""
                <div class="user-card">
                    <h3>👤 {u['nombre']}</h3>
                    <p style="color: #718096; font-size: 14px;">{"Administrador" if u.get("es_admin_croma") else "Empleado"}</p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Acceder", key=f"usr_btn_{u['id']}", use_container_width=True):
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
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.examen_activo = False
            st.session_state.modo_revision = False
            st.rerun()
        
    st.markdown("---")
    
    # MODO REVISIÓN PREVIA A FINALIZAR
    if st.session_state.modo_revision:
        st.subheader("🔍 Revisión de Examen previa a la entrega final")
        st.info("Revisa tus respuestas e indica si deseas modificar alguna antes de la entrega definitiva.")

        for i, p_item in enumerate(st.session_state.preguntas_seleccionadas):
            resp_actual = next((r for r in st.session_state.respuestas_detalle if r["idx_pregunta"] == i), None)
            texto_resp = resp_actual["opcion_elegida"] if resp_actual else "En blanco (Sin responder)"
            
            t_restante = st.session_state.tiempos_restantes_preguntas.get(i, TIEMPO_LIMITE_PREGUNTA)
            
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"**Pregunta {i+1}:** {p_item['pregunta']}")
                st.caption(f"Respuesta actual: **{texto_resp}** | ⏱️ Tiempo restante: **{t_restante} s**")
            with c2:
                btn_bloqueado = (t_restante <= 0)
                if st.button("Modificar", key=f"mod_rev_{i}", disabled=btn_bloqueado, use_container_width=True):
                    st.session_state.indice_pregunta = i
                    st.session_state.modo_revision = False
                    st.session_state.modificando_desde_revision = True
                    st.session_state.tiempo_inicio_pregunta = time.time()
                    st.rerun()
                if btn_bloqueado:
                    st.caption("🔒 Tiempo agotado")
            st.write("---")

        if st.button("✅ Confirmar y Entregar Examen Definitivamente", use_container_width=True):
            total_p = len(st.session_state.preguntas_seleccionadas)
            correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
            porcentaje = round((correctas / total_p) * 100, 2)
            nota_final = round((correctas / total_p) * 10, 2)
            estado_evaluacion = "🟢 APROBADO" if porcentaje >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
            
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

                try:
                    supabase.table("autorizaciones_examen").delete()\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("apartado", st.session_state.apartado_actual).execute()
                except Exception:
                    pass
                
                if porcentaje >= UMBRAL_APROBADO_PORCENTAJE:
                    st.success(f"🎉 Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%) | **{estado_evaluacion}**")
                else:
                    st.error(f"❌ Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%) | **{estado_evaluacion}**")

            except Exception as e:
                st.error(f"Error guardando intento: {e}")
                
            st.session_state.examen_activo = False
            st.session_state.modo_revision = False
            if st.button("Volver al Inicio", use_container_width=True):
                st.rerun()

    # CUESTIONARIO ACTIVO
    elif st.session_state.examen_activo:
        st.markdown("<div id='pregunta_activa'></div>", unsafe_allow_html=True)
        st.components.v1.html(
            "<script>window.parent.document.getElementById('pregunta_activa').scrollIntoView({behavior: 'smooth'});</script>",
            height=0
        )

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
            
            deshabilitar_opciones = False
            if tiempo_restante > 0:
                st.caption(f"⏱️ Tiempo restante: **{tiempo_restante} segundos**")
            else:
                st.error("⏰ ¡Tiempo agotado en esta pregunta! La selección ha sido bloqueada.")
                deshabilitar_opciones = True
                st.session_state.sobrepaso_tiempo_global = True
                st.session_state.tiempos_restantes_preguntas[idx] = 0

            st.markdown(f"<div class='pregunta-titulo'>{p_actual['pregunta']}</div>", unsafe_allow_html=True)

            resp_previa = next((r["opcion_elegida"] for r in st.session_state.respuestas_detalle if r["idx_pregunta"] == idx), None)
            idx_previa = None
            if resp_previa and resp_previa in p_actual["opciones_barajadas"]:
                idx_previa = p_actual["opciones_barajadas"].index(resp_previa)

            eleccion = st.radio(
                "Selecciona una opción:", 
                p_actual["opciones_barajadas"], 
                index=idx_previa, 
                key=f"p_{idx}",
                disabled=deshabilitar_opciones
            )
            
            if idx in st.session_state.pistas_activadas:
                pista_texto = p_actual.get("pista", "Lee con atención las opciones y descarta las inconsistentes.")
                st.info(f"💡 **Pista:** {pista_texto}")
            else:
                if st.session_state.comodines_restantes > 0 and not deshabilitar_opciones:
                    if st.button("💡 Pedir Ayuda (Gasta 1 comodín)", key=f"btn_pista_{idx}"):
                        st.session_state.comodines_restantes -= 1
                        st.session_state.pistas_activadas.add(idx)
                        st.rerun()
                elif deshabilitar_opciones:
                    st.caption("🚫 Tiempo agotado. No se pueden pedir comodines.")
                else:
                    st.caption("🚫 Has agotado tus 3 comodines de ayuda.")

            st.write("")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                lbl_btn = "Ir a Revisión" if (st.session_state.modificando_desde_revision or deshabilitar_opciones) else "Responder / Siguiente"
                if st.button(lbl_btn, key=f"btn_sig_{idx}", use_container_width=True):
                    st.session_state.tiempos_restantes_preguntas[idx] = max(0, tiempo_restante)
                    
                    if deshabilitar_opciones and not resp_previa:
                        es_correcta = False
                        opcion_guardada = "En blanco (Agotado tiempo)"
                    elif eleccion is None or eleccion == "":
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
                        "respuesta_correcta_texto": p_actual["respuesta_correcta_texto"],
                        "opciones_posibles": p_actual["opciones_barajadas"],
                        "es_correcta": es_correcta
                    })
                    
                    if st.session_state.modificando_desde_revision or deshabilitar_opciones:
                        st.session_state.modificando_desde_revision = False
                        st.session_state.modo_revision = True
                    else:
                        st.session_state.indice_pregunta += 1
                        st.session_state.tiempo_inicio_pregunta = time.time()
                    
                    st.rerun()

            with col_b2:
                if st.button("📋 Ir a Revisión Directa", key=f"btn_rev_{idx}", use_container_width=True):
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
        st.info(f"🎯 **Criterio de Evaluación:** Para obtener un resultado **APROBADO**, debes alcanzar una nota mínima de **{UMBRAL_APROBADO_PORCENTAJE / 10} / 10** ({int(UMBRAL_APROBADO_PORCENTAJE)}% de aciertos).")

        if st.session_state.es_croma:
            tab_examenes, tab_admin_resultados, tab_admin_export, tab_admin_gestion = st.tabs([
                "📝 Realizar Examen", 
                "📊 Resultados / Edición", 
                "📥 Exportación e Informes",
                "⚙️ Gestión y Autorizaciones"
            ])
        else:
            tab_examenes, tab_mis_resultados = st.tabs([
                "📝 Realizar Examen", 
                "📊 Mis Resultados y Estado"
            ])

        with tab_examenes:
            ahora = datetime.datetime.now()
            primer_dia_mes = datetime.datetime(ahora.year, ahora.month, 1, 0, 0, 0).isoformat()
            
            res_user_intentos = supabase.table("intentos_examen").select("*")\
                .eq("empleado_id", st.session_state.user_id)\
                .gte("fecha_inicio", primer_dia_mes).execute()
            user_intentos = res_user_intentos.data if res_user_intentos.data else []

            dict_realizados = {}
            for it in user_intentos:
                apt = it.get("apartado")
                if apt:
                    dict_realizados[apt] = {
                        "nota": it.get("nota", 0),
                        "porcentaje": it.get("porcentaje_obtenido", 0)
                    }

            try:
                res_aut = supabase.table("autorizaciones_examen").select("apartado")\
                    .eq("empleado_id", st.session_state.user_id).execute()
                autorizaciones_set = set(item["apartado"] for item in (res_aut.data or []))
            except Exception:
                autorizaciones_set = set()

            try:
                res_examenes = supabase.table("examenes").select("id, apartado, preguntas_json").execute()
                examenes_disponibles = res_examenes.data if res_examenes.data else []
            except Exception as e:
                examenes_disponibles = []
                st.error(f"Error al cargar manuales: {e}")

            if examenes_disponibles:
                st.subheader("📋 Seleccionar Modalidad")
                tab_global, tab_manual = st.tabs(["🌐 Examen Global (15 preguntas aleatorias)", "📘 Examen por Manual (15 preguntas)"])
                
                with tab_global:
                    st.info("El Examen Global seleccionará **15 preguntas aleatorias** de entre todos los manuales.")
                    
                    ya_hecho_global = "GLOBAL COMPLETO" in dict_realizados
                    permitido_global = autorizaciones_set.__contains__("GLOBAL COMPLETO")
                    bloqueado_global = ya_hecho_global and not permitido_global and not st.session_state.es_croma

                    if ya_hecho_global:
                        info_g = dict_realizados["GLOBAL COMPLETO"]
                        est_txt = "🟢 APROBADO" if info_g["porcentaje"] >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
                        st.warning(f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{info_g['nota']} / 10** ({info_g['porcentaje']}%) | **{est_txt}**")
                        if permitido_global:
                            st.success("🔓 **El administrador te ha habilitado un nuevo intento para este examen.**")
                        elif not st.session_state.es_croma:
                            st.error("🔒 Debes esperar al próximo mes o solicitar una autorización al administrador para volver a realizarlo.")

                    if st.button("Comenzar Examen Global Combinado", disabled=bloqueado_global, use_container_width=True):
                        banco_global = []
                        
                        for ex_obj in examenes_disponibles:
                            banco = ex_obj["preguntas_json"]
                            for p in banco:
                                idx_c = p["respuesta_correcta"]
                                texto_c = p["opciones"][idx_c]
                                opciones_shuffled = p["opciones"].copy()
                                random.shuffle(opciones_shuffled)
                                
                                banco_global.append({
                                    "apartado": ex_obj["apartado"],
                                    "subindice": p.get("subindice", "General"),
                                    "pregunta": p["pregunta"],
                                    "opciones_barajadas": opciones_shuffled,
                                    "respuesta_correcta_texto": texto_c,
                                    "pista": p.get("pista", "Revisa los conceptos clave."),
                                    "tipo": "teorica"
                                })
                        
                        preguntas_preparadas = seleccionar_15_preguntas(banco_global)
                        
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
                            
                            ya_hecho_manual = nombre_apt in dict_realizados
                            permitido_manual = autorizaciones_set.__contains__(nombre_apt)
                            bloqueado_manual = ya_hecho_manual and not permitido_manual and not st.session_state.es_croma

                            if ya_hecho_manual:
                                info_m = dict_realizados[nombre_apt]
                                est_txt = "🟢 APROBADO" if info_m["porcentaje"] >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
                                st.warning(f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{info_m['nota']} / 10** | **{est_txt}**")
                                if permitido_manual:
                                    st.success("🔓 **El administrador te ha habilitado un nuevo intento para este examen.**")
                                elif not st.session_state.es_croma:
                                    st.error("🔒 Requiere autorización del administrador para repetirlo este mes.")
                            
                            if st.button(f"Iniciar Examen de {nombre_apt}", key=f"btn_manual_{ex_obj['id']}", disabled=bloqueado_manual, use_container_width=True):
                                banco = ex_obj["preguntas_json"]
                                banco_manual = []
                                
                                for p in banco:
                                    idx_c = p["respuesta_correcta"]
                                    texto_c = p["opciones"][idx_c]
                                    opciones_shuffled = p["opciones"].copy()
                                    random.shuffle(opciones_shuffled)
                                    
                                    banco_manual.append({
                                        "apartado": nombre_apt,
                                        "subindice": p.get("subindice", "General"),
                                        "pregunta": p["pregunta"],
                                        "opciones_barajadas": opciones_shuffled,
                                        "respuesta_correcta_texto": texto_c,
                                        "pista": p.get("pista", "Revisa la documentación técnica."),
                                        "tipo": "teorica"
                                    })
                                
                                preguntas_preparadas = seleccionar_15_preguntas(banco_manual)
                                
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
                st.info(f"📅 **Habilitación de Examen:** Quedan **{dias_restantes} días** para finalizar el ciclo de evaluación actual.")
                
                if mis_intentos:
                    for i in mis_intentos:
                        fecha_str = i["fecha_inicio"][:10] if i.get("fecha_inicio") else "N/A"
                        porc = i.get("porcentaje_obtenido", 0)
                        respuestas = i.get("respuestas_usuario", [])
                        num_correctas = sum(1 for r in respuestas if r.get("es_correcta"))
                        total_p = len(respuestas) if respuestas else 15
                        
                        estado = "🟢 APROBADO" if porc >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
                        
                        with st.expander(f"Examen #{i['id']} - {i.get('apartado')} | {fecha_str} | Nota: {i.get('nota', 0)}/10 | Estado: {estado}"):
                            st.write(f"**Resultado:** {num_correctas} / {total_p} aciertos ({porc}%) - **{estado}**")
                            
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

        # ADMIN CROMA - RESULTADOS Y EDICIÓN
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Historial General y Edición por Usuario")
                
                res_todos = supabase.table("intentos_examen").select("*").order("fecha_inicio", desc=True).execute()
                todos_intentos = res_todos.data if res_todos.data else []
                
                if todos_intentos:
                    anios_disponibles = sorted(
                        list(set(int(it["fecha_inicio"][:4]) for it in todos_intentos if it.get("fecha_inicio"))),
                        reverse=True
                    )
                    
                    anio_sel = st.selectbox("📅 Filtrar exámenes por año:", anios_disponibles)
                    
                    intentos_filtrados = [
                        it for it in todos_intentos 
                        if it.get("fecha_inicio") and int(it["fecha_inicio"][:4]) == anio_sel
                    ]
                    
                    st.write(f"Se encontraron **{len(intentos_filtrados)}** exámenes realizados en el año **{anio_sel}**.")
                    
                    if intentos_filtrados:
                        dict_intentos = {}
                        for it in intentos_filtrados:
                            est_it = "🟢 APROBADO" if it.get("porcentaje_obtenido", 0) >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
                            dict_intentos[f"ID #{it['id']} - {it.get('nombre_empleado')} ({it.get('apartado')}) | Nota: {it.get('nota', 0)}/10 [{est_it}]"] = it

                        intento_sel_key = st.selectbox("Selecciona un examen para auditar/editar:", list(dict_intentos.keys()))
                        
                        intento_obj = dict_intentos[intento_sel_key]
                        intento_target_id = intento_obj["id"]
                        respuestas_lista = json.loads(json.dumps(intento_obj.get("respuestas_usuario", [])))
                        
                        if respuestas_lista:
                            dict_preguntas = {f"P{idx+1}: {p['pregunta']}": idx for idx, p in enumerate(respuestas_lista)}
                            p_sel_key = st.selectbox("Selecciona la pregunta a corregir:", list(dict_preguntas.keys()), key=f"sel_p_{intento_target_id}")
                            
                            p_idx = dict_preguntas[p_sel_key]
                            p_objetivo = respuestas_lista[p_idx]
                            
                            st.write(f"### ❓ Pregunta seleccionada:\n**{p_objetivo.get('pregunta')}**")
                            st.info(f"Respuesta registrada del empleado: **{p_objetivo.get('opcion_elegida')}** | Estado actual: **{'Correcta' if p_objetivo.get('es_correcta') else 'Incorrecta'}**")
                            
                            opciones_disponibles = p_objetivo.get("opciones_posibles", [])
                            texto_respuesta_correcta = p_objetivo.get("respuesta_correcta_texto", "")
                            
                            res_examenes_db = supabase.table("examenes").select("id, preguntas_json").execute()
                            banco_todos = res_examenes_db.data if res_examenes_db.data else []
                            
                            pregunta_texto_limpio = p_objetivo.get("pregunta", "").strip()
                            
                            for ex_item in banco_todos:
                                preguntas_banco = ex_item.get("preguntas_json", [])
                                for p_b in preguntas_banco:
                                    if p_b.get("pregunta", "").strip() == pregunta_texto_limpio:
                                        opciones_disponibles = p_b.get("opciones", [])
                                        num_correcta = p_b.get("respuesta_correcta")
                                        if isinstance(num_correcta, int) and 0 <= num_correcta < len(opciones_disponibles):
                                            texto_respuesta_correcta = opciones_disponibles[num_correcta]
                                        break

                            if texto_respuesta_correcta:
                                st.success(f"🎯 **Respuesta correcta según el Banco de Preguntas:**\n\n{texto_respuesta_correcta}")

                            with st.form(key=f"form_edit_{intento_target_id}_{p_idx}"):
                                st.markdown("### 📝 Formulario de Modificación de Respuesta")
                                
                                persona_modifica = st.text_input(
                                    "👤 Persona que modifica (Obligatorio):*", 
                                    value=st.session_state.user_nombre
                                )
                                
                                if opciones_disponibles:
                                    idx_defecto_resp = 0
                                    if texto_respuesta_correcta in opciones_disponibles:
                                        idx_defecto_resp = opciones_disponibles.index(texto_respuesta_correcta)
                                        
                                    resp_correcta_input = st.selectbox(
                                        "✅ Seleccionar o Confirmar Respuesta Correcta:*",
                                        options=opciones_disponibles,
                                        index=idx_defecto_resp
                                    )
                                else:
                                    resp_correcta_input = st.text_input(
                                        "✅ Respuesta correcta del examen (Obligatorio):*",
                                        value=texto_respuesta_correcta
                                    )
                                
                                nuevo_estado = st.checkbox("Marcar esta pregunta como Correcta para el empleado", value=p_objetivo.get("es_correcta", False))
                                motivo_edicion = st.text_area("📋 Motivo de la corrección (Obligatorio):*")
                                
                                btn_guardar_edit = st.form_submit_button("Guardar Corrección Auditada")
                                
                                if btn_guardar_edit:
                                    if not persona_modifica.strip():
                                        st.error("❌ El campo 'Persona que modifica' es obligatorio.")
                                    elif not resp_correcta_input or not str(resp_correcta_input).strip():
                                        st.error("❌ Debes indicar una respuesta correcta válida.")
                                    elif not motivo_edicion.strip():
                                        st.error("❌ El motivo de la corrección es obligatorio.")
                                    else:
                                        try:
                                            respuestas_lista[p_idx]["es_correcta"] = nuevo_estado
                                            respuestas_lista[p_idx]["respuesta_correcta_texto"] = resp_correcta_input
                                            respuestas_lista[p_idx]["opciones_posibles"] = opciones_disponibles
                                            
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
                                                "intento_id": int(intento_target_id),
                                                "usuario_modificador": persona_modifica.strip(),
                                                "fecha_modificacion": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                                "valor_anterior": json.dumps({"es_correcta": p_objetivo.get("es_correcta"), "respuesta_correcta": texto_respuesta_correcta}),
                                                "valor_nuevo": json.dumps({"es_correcta": nuevo_estado, "respuesta_correcta": resp_correcta_input}),
                                                "motivo": motivo_edicion.strip()
                                            }
                                            
                                            supabase.table("auditoria_modificaciones").insert(registro_audit).execute()
                                            st.success("✅ Corrección guardada y auditada correctamente.")
                                            time.sleep(1.5)
                                            st.rerun()

                                        except Exception as err:
                                            st.error(f"⚠️ Error al guardar en la base de datos: {err}")

# carga de archivos JSON de examenes
st.subheader("📄 Cargar Banco de Preguntas desde JSON")
nombre_apartado_json = st.text_input("Nombre del Manual / Apartado para este JSON:")
archivo_json = st.file_uploader("Seleccionar archivo JSON con preguntas", type=["json"])

if st.button("🚀 Subir Preguntas a Supabase"):
    if archivo_json and nombre_apartado_json:
        try:
            contenido_json = json.load(archivo_json)
            
            # Guardar directamente en la tabla 'examenes'
            supabase.table("examenes").insert({
                "apartado": nombre_apartado_json,
                "preguntas_json": contenido_json
            }).execute()
            
            st.success(f"✅ ¡Se cargaron {len(contenido_json)} preguntas correctamente!")
            time.sleep(1.5)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo JSON: {e}")
    else:
        st.warning("⚠️ Debes proporcionar un nombre para el apartado y subir un archivo JSON.")

        
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
                        opciones_examenes = []
                        for i in intentos_exp_filtrados:
                            est_exp = "🟢 APROBADO" if i.get("porcentaje_obtenido", 0) >= UMBRAL_APROBADO_PORCENTAJE else "🔴 SUSPENSO"
                            opciones_examenes.append(
                                f"Examen #{i['id']} - {i.get('nombre_empleado')} | {i.get('apartado')} | Nota: {i.get('nota', 0)}/10 [{est_exp}]"
                            )
                        
                        opcion_elegida = st.selectbox("Selecciona el examen a exportar:", opciones_examenes)
                        idx_sel = opciones_examenes.index(opcion_elegida)
                        examen_sel = intentos_exp_filtrados[idx_sel]

                        col_exp_a, col_exp_b = st.columns(2)
                        with col_exp_a:
                            if st.button("📊 Generar Excel de este Examen", use_container_width=True):
                                df_export = pd.DataFrame([examen_sel])
                                buffer = io.BytesIO()
                                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                    df_export.to_excel(writer, index=False, sheet_name="Examen")
                                
                                st.download_button(
                                    label="📥 Descargar Excel",
                                    data=buffer.getvalue(),
                                    file_name=f"examen_{examen_sel['id']}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )

                        with col_exp_b:
                            pdf_bytes = generar_pdf_resultado(examen_sel)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Descargar Informe PDF",
                                    data=pdf_bytes,
                                    file_name=f"informe_examen_{examen_sel['id']}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )

        # ADMIN CROMA - GESTIÓN Y AUTORIZACIONES
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                # SECCIÓN 1: REHABILITAR EXÁMENES A EMPLEADOS
                st.subheader("🔓 Autorizar Repetición de Examen a un Empleado")
                st.caption("Concede permiso especial a un empleado para volver a realizar un examen antes de finalizar el mes.")
                
                try:
                    res_emp = supabase.table("empleados").select("id, nombre").execute()
                    empleados_list = res_emp.data if res_emp.data else []
                    
                    res_ex_todos = supabase.table("examenes").select("apartado").execute()
                    apartados_unicos = sorted(list(set([e["apartado"] for e in (res_ex_todos.data or [])])))
                    apartados_unicos.insert(0, "GLOBAL COMPLETO")
                except Exception as ex_db:
                    empleados_list = []
                    apartados_unicos = []
                    st.error(f"Error cargando listados para autorizaciones: {ex_db}")

                if empleados_list and apartados_unicos:
                    dict_emp = {emp["nombre"]: emp["id"] for emp in empleados_list}
                    
                    col_aut1, col_aut2 = st.columns(2)
                    with col_aut1:
                        emp_aut_sel = st.selectbox("Seleccionar Empleado:", list(dict_emp.keys()), key="aut_emp_sel")
                    with col_aut2:
                        apt_aut_sel = st.selectbox("Seleccionar Examen/Manual:", apartados_unicos, key="aut_apt_sel")
                        
                    if st.button("Habilitar Repetición de Examen", use_container_width=True):
                        emp_id_target = dict_emp[emp_aut_sel]
                        try:
                            data_aut = {
                                "empleado_id": emp_id_target,
                                "apartado": apt_aut_sel,
                                "autorizado_por": st.session_state.user_nombre
                            }
                            supabase.table("autorizaciones_examen").insert(data_aut).execute()
                            st.success(f"✅ Se ha autorizado a **{emp_aut_sel}** para repetir el examen **{apt_aut_sel}**.")
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e_aut:
                            st.info("El usuario ya cuenta con un permiso activo para realizar este examen.")

                # SECCIÓN DE AUTORIZACIONES ACTIVAS
                try:
                    res_aut_activas = supabase.table("autorizaciones_examen").select("id, empleado_id, apartado, fecha_autorizacion, autorizado_por").execute()
                    list_aut_activas = res_aut_activas.data if res_aut_activas.data else []
                except Exception:
                    list_aut_activas = []

                if list_aut_activas:
                    st.markdown("#### 📋 Autorizaciones Activas Pendientes")
                    dict_emp_inverse = {emp["id"]: emp["nombre"] for emp in empleados_list}
                    
                    for aut in list_aut_activas:
                        e_nombre = dict_emp_inverse.get(aut["empleado_id"], f"Empleado ID {aut['empleado_id']}")
                        c_info, c_btn = st.columns([4, 1])
                        with c_info:
                            st.write(f"• **{e_nombre}** → `{aut['apartado']}` *(Autorizado por: {aut.get('autorizado_por', 'Admin')})*")
                        with c_btn:
                            if st.button("Revocar", key=f"rev_aut_{aut['id']}", use_container_width=True):
                                supabase.table("autorizaciones_examen").delete().eq("id", aut["id"]).execute()
                                st.warning("Autorización revocada.")
                                time.sleep(1)
                                st.rerun()

                st.markdown("---")

                # SECCIÓN 2: IMPORTAR INTENTOS DESDE CSV
                st.subheader("📥 Importar Registro de Exámenes (CSV)")
                st.caption("Carga un archivo CSV para insertar masivamente intentos de examen en la base de datos SQL (`intentos_examen`).")
                
                archivo_csv_import = st.file_uploader("Seleccionar archivo CSV", type=["csv"], key="csv_import_uploader")
                
                if archivo_csv_import is not None:
                    if st.button("🚀 Procesar e Importar CSV a la Base de Datos", use_container_width=True):
                        try:
                            try:
                                df_csv = pd.read_csv(archivo_csv_import, sep=';')
                                if len(df_csv.columns) <= 1:
                                    archivo_csv_import.seek(0)
                                    df_csv = pd.read_csv(archivo_csv_import, sep=',')
                            except Exception:
                                archivo_csv_import.seek(0)
                                df_csv = pd.read_csv(archivo_csv_import, sep=',')

                            res_emp_all = supabase.table("empleados").select("id, nombre").execute()
                            map_empleados = {emp["nombre"].strip().lower(): emp["id"] for emp in (res_emp_all.data or [])}

                            registros_insertados = 0
                            errores_import = 0

                            for idx_row, row in df_csv.iterrows():
                                nombre_emp = str(row.get("nombre empleado") or row.get("nombre_empleado") or "").strip()
                                emp_id = map_empleados.get(nombre_emp.lower(), None)
                                
                                resp_raw = row.get("respuestas_usuario", "[]")
                                if isinstance(resp_raw, str):
                                    try:
                                        resp_json = json.loads(resp_raw)
                                    except Exception:
                                        resp_json = []
                                elif isinstance(resp_raw, list):
                                    resp_json = resp_raw
                                else:
                                    resp_json = []

                                t_limite = row.get("tiempo_limite")
                                if pd.isna(t_limite) or t_limite is None:
                                    t_limite = row.get("tiempo_limite_segundos", 0)

                                fecha_inicio_clean = limpiar_timestamp_sql(row.get("fecha_inicio"))
                                fecha_fin_clean = limpiar_timestamp_sql(row.get("fecha_fin"))

                                registro_nuevo = {
                                    "empleado_id": emp_id,
                                    "nombre_empleado": nombre_emp if nombre_emp else "Desconocido",
                                    "apartado": str(row.get("Apartado") or row.get("apartado") or ""),
                                    "fecha_inicio": fecha_inicio_clean,
                                    "fecha_fin": fecha_fin_clean,
                                    "tiempo_total_segundos": int(row.get("tiempo_total_segundos", 0)) if not pd.isna(row.get("tiempo_total_segundos")) else 0,
                                    "tiempo_limite": int(t_limite) if not pd.isna(t_limite) else 0,
                                    "porcentaje_obtenido": float(row.get("porcentaje_obtenido", 0)) if not pd.isna(row.get("porcentaje_obtenido")) else 0.0,
                                    "nota": float(row.get("nota", 0)) if not pd.isna(row.get("nota")) else 0.0,
                                    "respuestas_usuario": resp_json,
                                }

                                try:
                                    supabase.table("intentos_examen").insert(registro_nuevo).execute()
                                    registros_insertados += 1
                                except Exception as err_ins:
                                    st.error(f"Error importando fila {idx_row + 1} ({nombre_emp}): {err_ins}")
                                    errores_import += 1

                            if registros_insertados > 0:
                                st.success(f"✅ Importación completada: Se insertaron **{registros_insertados}** registros correctamente.")
                                if errores_import > 0:
                                    st.warning(f"⚠️ Ocurrieron {errores_import} errores durante la carga.")
                                time.sleep(1.5)
                                st.rerun()

                        except Exception as e_csv:
                            st.error(f"❌ Error al procesar el archivo CSV: {e_csv}")

                st.markdown("---")

                # SECCIÓN 3: CARGA Y BORRADO DE MANUALES CON GESTOR DE PROMPTS Y MODELOS
                col_subir, col_del = st.columns([3, 2])
                
                with col_subir:
                    st.subheader("⚙️ Cargar Manual con Configuración de IA")
                    archivo_pdf = st.file_uploader("Cargar PDF del Manual", type=["pdf"])
                    nombre_apartado = st.text_input("Nombre del Manual / Apartado")

                    configs_prompts_db = []
                    try:
                        res_p = supabase.table("config_prompts").select("*").order("id", desc=True).execute()
                        configs_prompts_db = res_p.data if res_p.data else []
                    except Exception:
                        configs_prompts_db = []

                    opciones_dropdown_prompts = ["+ Nueva configuración personalizada"]
                    for cfg in configs_prompts_db:
                        opciones_dropdown_prompts.append(f"#{cfg['id']} - {cfg['nombre']} ({cfg['modelo']})")

                    prompt_seleccionado_obj = None
                    index_defecto_dropdown = 1 if len(configs_prompts_db) > 0 else 0

                    prompt_desplegable = st.selectbox(
                        "📋 Plantillas de Prompt guardadas en SQL (Por defecto la última usada):",
                        options=opciones_dropdown_prompts,
                        index=index_defecto_dropdown
                    )

                    if prompt_desplegable != "+ Nueva configuración personalizada" and len(configs_prompts_db) > 0:
                        idx_sel = opciones_dropdown_prompts.index(prompt_desplegable) - 1
                        prompt_seleccionado_obj = configs_prompts_db[idx_sel]
                        
                        prompt_val_inicial = prompt_seleccionado_obj["prompt_texto"]
                        
                        modelo_db = prompt_seleccionado_obj["modelo"]
                        if modelo_db in MODELOS_GEMINI_DISPONIBLES:
                            modelo_val_inicial = MODELOS_GEMINI_DISPONIBLES.index(modelo_db)
                        else:
                            modelo_val_inicial = 0
                    else:
                        prompt_val_inicial = PROMPT_DEFECTO
                        modelo_val_inicial = 0

                    st.markdown("### ✏️ Configuración editable")
                    modelo_gemini_sel = st.selectbox(
                        "🤖 Versión del Modelo Gemini:",
                        options=MODELOS_GEMINI_DISPONIBLES,
                        index=modelo_val_inicial
                    )

                    prompt_editable = st.text_area(
                        "💬 Prompt de Generación (Editable):",
                        value=prompt_val_inicial,
                        height=250
                    )

                    c_btn_a, c_btn_b = st.columns(2)
                    with c_btn_a:
                        guardar_nuevo_prompt = st.checkbox("💾 Guardar esta configuración en SQL")
                        nombre_nueva_config = ""
                        if guardar_nuevo_prompt:
                            nombre_nueva_config = st.text_input("Nombre identificativo para la versión:")

                    with c_btn_b:
                        st.write("")
                        st.write("")
                        btn_procesar_manual = st.button("🚀 Procesar y Generar Banco", use_container_width=True)

                    if btn_procesar_manual:
                        if archivo_pdf and nombre_apartado:
                            try:
                                if guardar_nuevo_prompt:
                                    if not nombre_nueva_config.strip():
                                        st.error("❌ Por favor indica un nombre para guardar la versión del prompt.")
                                        st.stop()
                                    else:
                                        supabase.table("config_prompts").insert({
                                            "nombre": nombre_nueva_config.strip(),
                                            "prompt_texto": prompt_editable,
                                            "modelo": modelo_gemini_sel
                                        }).execute()
                                        st.toast("✅ Configuración guardada en SQL")

                                reader = PdfReader(archivo_pdf)
                                texto = "".join([page.extract_text() or "" for page in reader.pages])
                                
                                if not texto.strip():
                                    st.error("❌ No se pudo extraer texto del PDF. Verifica que no sea una imagen escaneada.")
                                    st.stop()

                                prompt_final = prompt_editable + "\n\nTexto del manual:\n" + texto[:12000]

                                res = None
                                with st.spinner(f"Generando banco de preguntas usando {modelo_gemini_sel}..."):
                                    try:
                                        res = gemini_client.models.generate_content(
                                            model=modelo_gemini_sel,
                                            contents=prompt_final,
                                            config=types.GenerateContentConfig(
                                                response_mime_type="application/json"
                                            )
                                        )
                                    except Exception as model_err:
                                        st.error(f"❌ Error al procesar con {modelo_gemini_sel}: {model_err}")
                                        st.stop()

                                if res and res.text:
                                    clean_text = res.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                                    preguntas_json = json.loads(clean_text)
                                    
                                    supabase.table("examenes").insert({
                                        "apartado": nombre_apartado, 
                                        "preguntas_json": preguntas_json
                                    }).execute()
                                    
                                    st.success(f"✅ Se generaron {len(preguntas_json)} preguntas en el banco de '{nombre_apartado}'.")
                                    time.sleep(1.5)
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
                        
                        if st.button("🔴 Eliminar Documento Seleccionado", use_container_width=True):
                            id_borrar = dict_borrado[doc_a_eliminar]
                            try:
                                supabase.table("intentos_examen").update({"examen_id": None}).eq("examen_id", id_borrar).execute()
                                supabase.table("examenes").delete().eq("id", id_borrar).execute()
                                
                                st.success(f"✅ Apartado '{doc_a_eliminar}' eliminado. Se conserva el historial de exámenes realizados.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error al eliminar apartado: {e}")
                    else:
                        st.info("No hay documentos guardados para eliminar.")
