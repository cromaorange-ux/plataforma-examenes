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

# Importar SDK de Anthropic (Claude) - Opcional / Fallback futuro
try:
    import anthropic
    CLAUDE_DISPONIBLE = True
except ImportError:
    CLAUDE_DISPONIBLE = False

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
        font-weight: 600 !important;
        line-height: 1.4 !important;
        color: #1A202C !important;
    }
    
    .stRadio div[role='radiogroup'] {
        gap: 10px;
    }

    .stRadio div[role='radiogroup'] > label {
        background-color: #FFFFFF !important;
        padding: 12px 18px !important;
        border-radius: 8px !important;
        border: 2px solid #CBD5E0 !important;
        transition: all 0.2s ease-in-out;
        width: 100%;
        margin-bottom: 8px !important;
    }

    .stRadio div[role='radiogroup'] > label p {
        color: #1A202C !important;
        font-weight: 600 !important;
    }

    .stRadio div[role='radiogroup'] > label:hover {
        background-color: #EDF2F7 !important;
        border-color: #2B6CB0 !important;
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
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0;
        border-radius: var(--border-radius);
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 15px;
    }

    .user-card h3 {
        color: #1A365D !important;
        font-weight: 700 !important;
        font-size: 20px !important;
        margin-bottom: 5px !important;
    }

    .user-card p {
        color: #4A5568 !important;
        font-size: 14px !important;
        margin: 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# CREDENCIALES Y CLIENTES
# ---------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
CLAUDE_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")

os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
except Exception as e:
    gemini_client = None

claude_client = None
if CLAUDE_DISPONIBLE and CLAUDE_API_KEY:
    try:
        claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    except Exception as e:
        claude_client = None

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
if "intento_auditado_id_sel" not in st.session_state:
    st.session_state.intento_auditado_id_sel = None
if "eval_resultado_cache" not in st.session_state:
    st.session_state.eval_resultado_cache = None

TIEMPO_LIMITE_PREGUNTA = 45
UMBRAL_APROBADO_PORCENTAJE = 70.0
NUM_PREGUNTAS_EXAMEN = 15

PROMPT_DEFECTO = """Genera un banco de EXACTAMENTE 50 preguntas tipo test basadas en el documento. El documento esta separado por temas, cada tema el texto descriptivo, se encuentra en un tamaño más grande que el anterior. Siendo la pagina 2 donde comienza.

Requisitos strictly para el JSON:
1. "es_principal": Marca como true ÚNICAMENTE en las 5 preguntas más fundamentales de todo el documento. El resto debe ser false.
2. "dificultad": Asigna equitativamente "facil", "media" o "dificil".
3. "pista": Incluye una pista breve (máx 2 frases) sin revelar la opción correcta.

Responde ÚNICAMENTE con un array JSON estructurado así (sin marcas de markdown fuera del json):
[
  {
    "pregunta": "texto de la pregunta",
    "opciones": ["Opción A", "Opción B", "Opción C"],
    "respuesta_correcta": 0,
    "pista": "Texto de la pista de ayuda",
    "subindice": "Nombre del Tema/Sección",
    "tipo": "teorica"
  }
]
"""

def obtener_modelos_ia_disponibles():
    """Obtiene dinámicamente la lista de modelos de IA registrados en la base de datos SQL."""
    try:
        res = supabase.table("config_prompts").select("modelo_gemini, modelo_claude").execute()
        if res.data:
            modelos_sql = []
            for fila in res.data:
                if fila.get("modelo_gemini"):
                    modelos_sql.extend([m.strip() for m in fila["modelo_gemini"].split(",") if m.strip()])
                if fila.get("modelo_claude"):
                    modelos_sql.extend([m.strip() for m in fila["modelo_claude"].split(",") if m.strip()])
            
            modelos_unicos = list(dict.fromkeys(modelos_sql))
            if modelos_unicos:
                return modelos_unicos
    except Exception as err:
        st.warning(f"No se pudieron cargar los modelos desde la base de datos: {err}")
    
    return ["gemini-2.5-pro", "gemini-2.5-flash", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]

MAPEO_CAMPOS = {
    'q': 'pregunta', 'question': 'pregunta', 'ok': 'respuesta_correcta',
    'correcta': 'respuesta_correcta', 'respuesta_correcta': 'respuesta_correcta',
    'correct': 'respuesta_correcta', 'no': 'incorrectas', 'incorrectas': 'incorrectas',
    'respuestas_incorrectas': 'incorrectas', 'h': 'pista', 'pista': 'pista',
    'hint': 'pista', 'cat': 'categoria', 'categoria': 'categoria',
    'category': 'categoria', 'subindex': 'subindice', 'subindice': 'subindice'
}

# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE IA Y PROCESAMIENTO
# ---------------------------------------------------------
def obtener_estado_evaluacion(porcentaje, sobrepasado_tiempo=False):
    porc_val = float(porcentaje) if porcentaje is not None else 0.0
    if sobrepasado_tiempo:
        return "🔴 SUSPENSO (TIEMPO EXCEDIDO)"
    if porc_val >= UMBRAL_APROBADO_PORCENTAJE:
        return "🟢 APROBADO"
    return "🔴 SUSPENSO"

def consultar_ia(modelo_inicial, prompt, sistema=""):
    """
    Intenta ejecutar el prompt en el modelo principal y, si falla,
    recorre la lista completa de modelos_AI sucesivamente.
    """
    modelos_disponibles = obtener_modelos_ia_disponibles()
    if modelo_inicial in modelos_disponibles:
        modelos_disponibles.remove(modelo_inicial)
    modelos_a_probar = [modelo_inicial] + modelos_disponibles

    errores = []
    for mod in modelos_a_probar:
        try:
            if "claude" in mod.lower():
                if CLAUDE_DISPONIBLE and claude_client:
                    mensaje = claude_client.messages.create(
                        model=mod,
                        max_tokens=4096,
                        system=sistema if sistema else "Eres un asistente experto en análisis de datos y evaluación formativa.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return mensaje.content[0].text
                else:
                    raise Exception("SDK/API Key de Claude no disponible.")
            else:
                if not gemini_client:
                    raise Exception("Cliente Gemini no disponible.")
                p_final = f"{sistema}\n\n{prompt}" if sistema else prompt
                config_gen = types.GenerateContentConfig()
                if "JSON" in prompt.upper() or "json" in prompt:
                    config_gen.response_mime_type = "application/json"
                res = gemini_client.models.generate_content(
                    model=mod,
                    contents=p_final,
                    config=config_gen
                )
                if res and res.text:
                    return res.text
                raise Exception("Respuesta vacía recibida.")
        except Exception as e:
            errores.append(f"Modelo {mod}: {e}")

    raise Exception(f"Fallaron todos los modelos disponibles en el listado: {'; '.join(errores)}")

def limpiar_timestamp_sql(ts_val):
    if pd.isna(ts_val) or ts_val is None:
        return None
    try:
        dt = pd.to_datetime(ts_val)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        ts_str = str(ts_val).strip().split('.')[0]
        return ts_str.replace("T", " ")

def normalizar_pregunta_json(item):
    if not isinstance(item, dict):
        return None
    
    item_normalizado = {}
    for k, v in item.items():
        k_lower = str(k).strip().lower()
        clave_estandar = MAPEO_CAMPOS.get(k_lower, k)
        item_normalizado[clave_estandar] = v

    pregunta_texto = item_normalizado.get("pregunta", item_normalizado.get("q", ""))
    pista_texto = item_normalizado.get("pista", "Revisa la documentación.")
    categoria_texto = item_normalizado.get("subindice", item_normalizado.get("categoria", "General"))
    
    opciones = []
    idx_correcta = 0

    if "opciones" in item_normalizado and isinstance(item_normalizado["opciones"], list):
        opciones = [str(o) for o in item_normalizado["opciones"]]
        raw_correcta = item_normalizado.get("respuesta_correcta", 0)
        
        if isinstance(raw_correcta, int) and 0 <= raw_correcta < len(opciones):
            idx_correcta = raw_correcta
        elif isinstance(raw_correcta, str) and raw_correcta in opciones:
            idx_correcta = opciones.index(raw_correcta)
        else:
            idx_correcta = 0

    elif "respuesta_correcta" in item_normalizado and "incorrectas" in item_normalizado:
        val_correcta = str(item_normalizado["respuesta_correcta"])
        val_incorrectas = item_normalizado["incorrectas"]
        if isinstance(val_incorrectas, list):
            val_incorrectas = [str(i) for i in val_incorrectas]
        else:
            val_incorrectas = [str(val_incorrectas)]
        
        opciones = [val_correcta] + val_incorrectas
        random.shuffle(opciones)
        idx_correcta = opciones.index(val_correcta)

    if not pregunta_texto or not opciones:
        return None

    return {
        "pregunta": str(pregunta_texto),
        "opciones": opciones,
        "respuesta_correcta": idx_correcta,
        "pista": str(pista_texto),
        "subindice": str(categoria_texto),
        "tipo": item_normalizado.get("tipo", "teorica")
    }
    
def seleccionar_15_preguntas(banco_completo):
    sample_size = min(len(banco_completo), NUM_PREGUNTAS_EXAMEN)
    seleccionadas = random.sample(banco_completo, sample_size)
    seleccionadas.sort(key=lambda x: str(x.get("subindice", "General")).lower())
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
    fecha_txt = str(intento.get("fecha_inicio", ""))[:10] if intento.get("fecha_inicio") else "N/A"
    story.append(Paragraph(f"<b>Empleado:</b> {intento.get('nombre_empleado')} | <b>Fecha:</b> {fecha_txt} | <b>Apartado:</b> {intento.get('apartado')}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=15))

    respuestas = intento.get("respuestas_usuario", [])
    total_p = len(respuestas) if respuestas else 1
    correctas = sum(1 for r in respuestas if r.get("es_correcta"))
    porcentaje = intento.get("porcentaje_obtenido", 0)
    estado_txt = obtener_estado_evaluacion(porcentaje, intento.get("sobrepasado_tiempo", False))

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
        pwd_input = st.text_input("Introduce tu contraseña:", type="password", key="modal_pwd_input", autocomplete="current-password")
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
        res_usuarios = supabase.table("empleados").select("*").eq("activo", True).execute()
        lista_usuarios = res_usuarios.data if res_usuarios.data else []
    except Exception as e:
        lista_usuarios = []
        st.error(f"Error al conectar con la base de datos de empleados: {e}")

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
        st.warning("No se encontraron perfiles de empleados activos en la base de datos.")

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
            
            estado_evaluacion = obtener_estado_evaluacion(porcentaje, st.session_state.sobrepaso_tiempo_global)
            
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
                    "fecha_inicio": datetime.datetime.fromtimestamp(st.session_state.tiempo_inicio_examen, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    "fecha_fin": tiempo_fin_examen.strftime("%Y-%m-%d %H:%M:%S"),
                    "tiempo_total_segundos": duracion_total,
                    "tiempo_limite": tiempo_limite_total,
                    "sobrepasado_tiempo": st.session_state.sobrepaso_tiempo_global,
                    "activo": True
                }
                
                supabase.table("intentos_examen").insert(registro_intento).execute()

                try:
                    supabase.table("autorizaciones_examen").delete()\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("apartado", st.session_state.apartado_actual).execute()
                except Exception:
                    pass
                
                if "APROBADO" in estado_evaluacion:
                    st.success(f"🎉 Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%) | **{estado_evaluacion}**")
                else:
                    st.error(f"❌ Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%) | **{estado_evaluacion}**")

            except Exception as e:
                st.error(f"Error guardando intento: {e}")
                
            st.session_state.examen_activo = False
            st.session_state.modo_revision = False
            if st.button("Volver al Inicio", use_container_width=True):
                st.rerun()

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
            tiempo_restante = max(0, tiempo_base - tiempo_transcurrido)
            
            st.progress(max(0.0, tiempo_restante / TIEMPO_LIMITE_PREGUNTA))
            
            deshabilitar_opciones = False
            if tiempo_restante > 0:
                st.caption(f"⏱️ Tiempo restante: **{tiempo_restante} segundos**")
            else:
                st.warning("⏰ ¡Tiempo agotado en esta pregunta! Se registrará la opción elegida hasta el momento.")
                deshabilitar_opciones = True
                st.session_state.tiempos_restantes_preguntas[idx] = 0

            st.markdown(f"<div class='pregunta-titulo'>{p_actual['pregunta']}</div>", unsafe_allow_html=True)

            resp_previa = next((r["opcion_elegida"] for r in st.session_state.respuestas_detalle if r["idx_pregunta"] == idx), None)
            idx_previa = None
            if resp_previa and resp_previa in p_actual["opciones_barajadas"]:
                idx_previa = p_actual["opciones_barajadas"].index(resp_previa)

            eleccion = st.radio("Selecciona una opción:", p_actual["opciones_barajadas"], index=idx_previa, key=f"p_{idx}", disabled=deshabilitar_opciones)
            
            if idx in st.session_state.pistas_activadas:
                pista_texto = p_actual.get("pista", "Lee con atención las opciones y descarta las inconsistentes.")
                st.info(f"💡 **Pista:** {pista_texto}")
            else:
                if st.session_state.comodines_restantes > 0 and not deshabilitar_opciones:
                    if st.button("💡 Pedir Ayuda (Gasta 1 comodín)", key=f"btn_pista_{idx}"):
                        st.session_state.comodines_restantes -= 1
                        st.session_state.pistas_activadas.add(idx)
                        st.rerun()

            st.write("")
            col_b1, col_b2 = st.columns(2)
            
            def registrar_respuesta_pregunta(elec_val):
                if elec_val is not None and elec_val != "":
                    es_corr = (elec_val == p_actual["respuesta_correcta_texto"])
                    op_guardada = elec_val
                else:
                    es_corr = False
                    op_guardada = "En blanco (Sin responder)"

                st.session_state.respuestas_detalle = [r for r in st.session_state.respuestas_detalle if r["idx_pregunta"] != idx]
                st.session_state.respuestas_detalle.append({
                    "idx_pregunta": idx,
                    "pregunta": p_actual["pregunta"],
                    "subindice": p_actual.get("subindice", "General"),
                    "opcion_elegida": op_guardada,
                    "respuesta_correcta_texto": p_actual["respuesta_correcta_texto"],
                    "opciones_posibles": p_actual["opciones_barajadas"],
                    "es_correcta": es_corr
                })

            with col_b1:
                lbl_btn = "Ir a Revisión" if st.session_state.modificando_desde_revision else "Responder / Siguiente"
                if st.button(lbl_btn, key=f"btn_sig_{idx}", use_container_width=True):
                    st.session_state.tiempos_restantes_preguntas[idx] = max(0, tiempo_restante)
                    registrar_respuesta_pregunta(eleccion)
                    
                    if st.session_state.modificando_desde_revision:
                        st.session_state.modificando_desde_revision = False
                        st.session_state.modo_revision = True
                    else:
                        st.session_state.indice_pregunta += 1
                        st.session_state.tiempo_inicio_pregunta = time.time()
                    st.rerun()

            with col_b2:
                if st.button("📋 Ir a Revisión Directa", key=f"btn_rev_{idx}", use_container_width=True):
                    st.session_state.tiempos_restantes_preguntas[idx] = max(0, tiempo_restante)
                    registrar_respuesta_pregunta(eleccion)
                    st.session_state.modificando_desde_revision = False
                    st.session_state.modo_revision = True
                    st.rerun()

            if tiempo_restante <= 0:
                registrar_respuesta_pregunta(eleccion)

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
            tab_examenes, tab_admin_resultados, tab_admin_export, tab_admin_analisis, tab_admin_claude, tab_admin_gestion = st.tabs([
                "📝 Realizar Examen", "📊 Resultados / Edición", "📥 Exportación e Informes",
                "📈 Analítica e IA", "🤖 Consultas Gemini / IA", "⚙️ Gestión y Configuración"
            ])
        else:
            tab_examenes, tab_mis_resultados, tab_mi_analisis = st.tabs([
                "📝 Realizar Examen", "📊 Mis Resultados e Historial", "📈 Mi Rendimiento e Informes IA"
            ])

        with tab_examenes:
            ahora = datetime.datetime.now(datetime.timezone.utc)
            primer_dia_mes = datetime.datetime(2026, ahora.month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            user_intentos = []
            try:
                res_user_intentos = supabase.table("intentos_examen").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .gte("fecha_inicio", primer_dia_mes).execute()
                user_intentos = res_user_intentos.data if res_user_intentos.data else []
            except Exception:
                user_intentos = []

            dict_realizados = {it.get("apartado"): {"nota": it.get("nota", 0), "porcentaje": it.get("porcentaje_obtenido", 0)} for it in user_intentos if it.get("apartado")}

            try:
                res_aut = supabase.table("autorizaciones_examen").select("apartado").eq("empleado_id", st.session_state.user_id).execute()
                autorizaciones_set = set(item["apartado"] for item in (res_aut.data or []))
            except Exception:
                autorizaciones_set = set()

            try:
                res_examenes = supabase.table("examenes").select("*").eq("activo", True).execute()
                examenes_disponibles = res_examenes.data if res_examenes.data else []
            except Exception as e:
                examenes_disponibles = []
                st.error(f"Error al cargar manuales activos: {e}")

            if examenes_disponibles:
                st.subheader("📋 Seleccionar Modalidad")
                tab_global, tab_manual = st.tabs(["🌐 Examen Global (15 preguntas aleatorias)", "📘 Examen por Manual (15 preguntas)"])
                
                with tab_global:
                    st.info("El Examen Global seleccionará **15 preguntas aleatorias** de entre todos los manuales activos.")
                    ya_hecho_global = "GLOBAL COMPLETO" in dict_realizados
                    permitido_global = "GLOBAL COMPLETO" in autorizaciones_set
                    bloqueado_global = ya_hecho_global and not permitido_global and not st.session_state.es_croma

                    if ya_hecho_global:
                        info_g = dict_realizados["GLOBAL COMPLETO"]
                        st.warning(f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{info_g['nota']} / 10** ({info_g['porcentaje']}%)")

                    if st.button("Comenzar Examen Global Combinado", disabled=bloqueado_global, use_container_width=True):
                        banco_global = []
                        for ex_obj in examenes_disponibles:
                            banco = ex_obj.get("preguntas_json", [])
                            if isinstance(banco, list):
                                for p in banco:
                                    if isinstance(p, dict):
                                        idx_c = p.get("respuesta_correcta", 0)
                                        opciones = p.get("opciones", [])
                                        if isinstance(idx_c, int) and 0 <= idx_c < len(opciones):
                                            texto_c = opciones[idx_c]
                                            opciones_shuffled = opciones.copy()
                                            random.shuffle(opciones_shuffled)
                                            banco_global.append({
                                                "apartado": ex_obj.get("apartado", ""),
                                                "subindice": p.get("subindice", "General"),
                                                "pregunta": p.get("pregunta", ""),
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
                        st.session_state.sobrepaso_tiempo_global = False
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
                            permitido_manual = nombre_apt in autorizaciones_set
                            bloqueado_manual = ya_hecho_manual and not permitido_manual and not st.session_state.es_croma

                            if ya_hecho_manual:
                                info_m = dict_realizados[nombre_apt]
                                st.warning(f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{info_m['nota']} / 10**")
                            
                            if st.button(f"Iniciar Examen de {nombre_apt}", key=f"btn_manual_{ex_obj['id']}", disabled=bloqueado_manual, use_container_width=True):
                                banco = ex_obj.get("preguntas_json", [])
                                banco_manual = []
                                if isinstance(banco, list):
                                    for p in banco:
                                        if isinstance(p, dict):
                                            idx_c = p.get("respuesta_correcta", 0)
                                            opciones = p.get("opciones", [])
                                            if isinstance(idx_c, int) and 0 <= idx_c < len(opciones):
                                                texto_c = opciones[idx_c]
                                                opciones_shuffled = opciones.copy()
                                                random.shuffle(opciones_shuffled)
                                                banco_manual.append({
                                                    "apartado": nombre_apt,
                                                    "subindice": p.get("subindice", "General"),
                                                    "pregunta": p.get("pregunta", ""),
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
                                st.session_state.sobrepaso_tiempo_global = False
                                st.session_state.examen_activo = True
                                st.rerun()
            else:
                st.warning("No hay manuales activos cargados en el sistema.")

        # VISTA USUARIO: MIS RESULTADOS
        if not st.session_state.es_croma:
            with tab_mis_resultados:
                st.subheader("📌 Mis Calificaciones e Historial Completo")
                res_mis_intentos = supabase.table("intentos_examen").select("*")\
                    .eq("empleado_id", st.session_state.user_id).eq("activo", True).order("fecha_inicio", desc=True).execute()
                mis_intentos = res_mis_intentos.data if res_mis_intentos.data else []
                
                if mis_intentos:
                    for i in mis_intentos:
                        fecha_str = str(i["fecha_inicio"])[:10] if i.get("fecha_inicio") else "N/A"
                        porc = i.get("porcentaje_obtenido", 0)
                        respuestas = i.get("respuestas_usuario", [])
                        estado = obtener_estado_evaluacion(porc, i.get("sobrepasado_tiempo", False))
                        
                        with st.expander(f"Examen #{i['id']} - {i.get('apartado')} | {fecha_str} | Nota: {i.get('nota', 0)}/10 | Estado: {estado}"):
                            if respuestas:
                                df_resp = pd.DataFrame(respuestas)
                                if "subindice" not in df_resp.columns:
                                    df_resp["subindice"] = df_resp.get("categoria", "General")
                                df_resp["subindice"] = df_resp["subindice"].fillna("General")

                                resumen_cat = df_resp.groupby("subindice").agg(
                                    Aciertos=('es_correcta', lambda x: sum(x == True)),
                                    Fallos=('es_correcta', lambda x: sum(x == False)),
                                    Total=('es_correcta', 'count')
                                ).reset_index()

                                st.markdown("#### 📊 Estadísticas por Tema (Aciertos / Errores)")
                                st.bar_chart(resumen_cat.set_index("subindice")[["Aciertos", "Fallos"]], use_container_width=True)
                                st.dataframe(resumen_cat, use_container_width=True, hide_index=True)

        # ADMIN CROMA - RESULTADOS Y EDICIÓN
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Historial General y Edición por Usuario")
                res_todos = supabase.table("intentos_examen").select("*").eq("activo", True).order("id", desc=True).execute()
                todos_intentos = res_todos.data if res_todos.data else []
                
                if todos_intentos:
                    anios_disponibles = sorted(list(set(int(str(it["fecha_inicio"])[:4]) for it in todos_intentos if it.get("fecha_inicio"))), reverse=True)
                    anio_sel = st.selectbox("📅 Filtrar exámenes por año:", anios_disponibles)
                    intentos_filtrados = [it for it in todos_intentos if it.get("fecha_inicio") and int(str(it["fecha_inicio"])[:4]) == anio_sel]

                    if intentos_filtrados:
                        map_id = {it['id']: it for it in intentos_filtrados}
                        opciones_ids = list(map_id.keys())
                        intento_target_id = st.selectbox("Selecciona examen a auditar:", opciones_ids)
                        intento_obj = map_id[intento_target_id]

                        respuestas_lista = json.loads(json.dumps(intento_obj.get("respuestas_usuario", [])))
                        if respuestas_lista:
                            p_sel_key = st.selectbox("Pregunta a corregir:", [f"P{idx+1}: {p['pregunta']}" for idx, p in enumerate(respuestas_lista)])
                            p_idx = [f"P{idx+1}: {p['pregunta']}" for idx, p in enumerate(respuestas_lista)].index(p_sel_key)
                            p_objetivo = respuestas_lista[p_idx]

                            with st.form(key=f"form_edit_{intento_target_id}_{p_idx}"):
                                persona_modifica = st.text_input("👤 Persona que modifica:*", value=st.session_state.user_nombre)
                                nuevo_estado = st.checkbox("Marcar como Correcta", value=p_objetivo.get("es_correcta", False))
                                motivo_edicion = st.text_area("📋 Motivo de la corrección:*")
                                
                                if st.form_submit_button("Guardar Corrección Auditada"):
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
                                    st.success("✅ Examen corregido.")
                                    st.rerun()

        # ADMIN CROMA - EXPORTACIÓN E INFORMES (SOLO EXÁMENES ACTIVOS)
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación e Informes (Exámenes Activos)")
                res_activos = supabase.table("intentos_examen").select("*").eq("activo", True).order("fecha_inicio", desc=True).execute()
                intentos_activos = res_activos.data if res_activos.data else []

                if intentos_activos:
                    opciones = [f"#{i['id']} - {i.get('nombre_empleado')} ({i.get('apartado')}) | Nota: {i.get('nota')}/10" for i in intentos_activos]
                    sel_exp = st.selectbox("Seleccionar examen para exportar:", opciones)
                    idx_exp = opciones.index(sel_exp)
                    target_exp = intentos_activos[idx_exp]

                    col_exp_a, col_exp_b = st.columns(2)
                    with col_exp_a:
                        df_exp = pd.DataFrame([target_exp])
                        buf = io.BytesIO()
                        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
                            df_exp.to_excel(writer, index=False)
                        st.download_button("📥 Descargar Excel", data=buf.getvalue(), file_name=f"examen_{target_exp['id']}.xlsx", use_container_width=True)
                    with col_exp_b:
                        pdf_bytes = generar_pdf_resultado(target_exp)
                        if pdf_bytes:
                            st.download_button("📄 Descargar PDF", data=pdf_bytes, file_name=f"examen_{target_exp['id']}.pdf", use_container_width=True)

        # ADMIN CROMA - ANALÍTICA E IA
        if st.session_state.es_croma and tab_admin_analisis:
            with tab_admin_analisis:
                st.subheader("📈 Analítica Global e Inteligencia Artificial")
                res_all_intentos = supabase.table("intentos_examen").select("*").eq("activo", True).order("fecha_inicio", desc=False).execute()
                data_intentos_val = res_all_intentos.data if res_all_intentos.data else []

                if data_intentos_val:
                    df_all = pd.DataFrame(data_intentos_val)
                    df_all["anio_int"] = pd.to_datetime(df_all["fecha_inicio"], errors='coerce').dt.year
                    
                    st.markdown("### 📊 Gráficas y Métricas por Empleado (Histórico Completo SQL)")
                    col_m1, col_m2, col_m3 = st.columns(3)
                    
                    with col_m1:
                        nombres_trabajadores = sorted(list(set(df_all["nombre_empleado"].dropna().unique())))
                        emp_sel = st.selectbox("👤 Selecciona Trabajador:", nombres_trabajadores)
                    with col_m2:
                        examenes_unq = ["Todos"] + sorted(list(set(df_all["apartado"].dropna().unique())))
                        ex_sel = st.selectbox("📘 Selecciona Examen/Manual:", examenes_unq)
                    with col_m3:
                        anios_unq = sorted(list(df_all["anio_int"].dropna().astype(int).unique()), reverse=True)
                        anio_sel_metric = st.selectbox("📅 Selecciona Año:", anios_unq)

                    df_filt = df_all[(df_all["nombre_empleado"] == emp_sel) & (df_all["anio_int"] == anio_sel_metric)]
                    if ex_sel != "Todos":
                        df_filt = df_filt[df_filt["apartado"] == ex_sel]

                    if not df_filt.empty:
                        st.dataframe(df_filt[["id", "nombre_empleado", "apartado", "nota", "porcentaje_obtenido", "fecha_inicio"]], use_container_width=True)
                        st.line_chart(df_filt, x="fecha_inicio", y="nota")
                    else:
                        st.info("No se hallaron registros con los filtros seleccionados.")

        # ADMIN CROMA - CONSULTAS LIBRES
        if st.session_state.es_croma and tab_admin_claude:
            with tab_admin_claude:
                st.subheader("🤖 Consola de Consultas e IA Libre")
                prompt_free = st.text_area("Prompt de consulta:", key="p_free_text")
                if st.button("🚀 Ejecutar Consulta"):
                    res_ia = consultar_ia(obtener_modelos_ia_disponibles()[0], prompt_free)
                    st.write(res_ia)

        # ADMIN CROMA - GESTIÓN Y CONFIGURACIÓN
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Configuración de IA y Modelos (SQL config_prompts)")
                listado_modelos = obtener_modelos_ia_disponibles()

                with st.expander("🛠️ Editar Lista Global de Modelos de IA"):
                    nuevos_modelos_str = st.text_area("Modelos disponibles (separados por coma):", value=", ".join(listado_modelos))
                    if st.button("💾 Actualizar Lista de Modelos IA"):
                        lista_nuevos = [m.strip() for m in nuevos_modelos_str.split(",") if m.strip()]
                        g_str = ",".join([m for m in lista_nuevos if "gemini" in m.lower()])
                        c_str = ",".join([m for m in lista_nuevos if "claude" in m.lower()])
                        try:
                            supabase.table("config_prompts").upsert({
                                "nombre": "evaluacion_empleado",
                                "modelo_gemini": g_str if g_str else "gemini-2.5-pro",
                                "modelo_claude": c_str if c_str else "claude-3-5-sonnet-20241022"
                            }, on_conflict="nombre").execute()
                            st.success("✅ Lista de modelos actualizada.")
                            st.rerun()
                        except Exception as e_mod:
                            st.error(f"Error actualizando lista de modelos: {e_mod}")

                st.markdown("---")
                
                # Cargar manual con guardado memorizado
                st.subheader("⚙️ Cargar Manual con Configuración de IA")
                prompt_editable = st.text_area("💬 Prompt de Generación (Editable):", value=PROMPT_DEFECTO, height=180)
                
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    if st.button("💾 Memorizar Prompt en BD (`config_prompts`)", use_container_width=True):
                        try:
                            supabase.table("config_prompts").upsert({
                                "nombre": "evaluacion_empleado",
                                "prompt_texto": prompt_editable.strip()
                            }, on_conflict="nombre").execute()
                            st.success("✅ Prompt guardado y memorizado en la base de datos.")
                        except Exception as e_prm:
                            st.error(f"Error guardando prompt: {e_prm}")

                st.markdown("---")
                st.subheader("🚫 Control Operativo y Deshabilitación (2026)")
                
                tab_activos, tab_deshabilitados = st.tabs(["🟢 Entidades Activas (2026)", "🔴 Entidades Deshabilitadas"])
                
                with tab_activos:
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        st.markdown("#### 👤 Trabajadores Activos")
                        res_emp_a = supabase.table("empleados").select("id, nombre, activo").eq("activo", True).execute()
                        for emp in (res_emp_a.data or []):
                            if not st.checkbox(f"{emp['nombre']}", value=True, key=f"emp_a_{emp['id']}"):
                                supabase.table("empleados").update({"activo": False}).eq("id", emp["id"]).execute()
                                st.rerun()
                    with col_d2:
                        st.markdown("#### 📘 Exámenes Activos")
                        res_ex_a = supabase.table("examenes").select("id, apartado, activo").eq("activo", True).execute()
                        for ex_i in (res_ex_a.data or []):
                            if not st.checkbox(f"{ex_i['apartado']}", value=True, key=f"ex_a_{ex_i['id']}"):
                                supabase.table("examenes").update({"activo": False}).eq("id", ex_i["id"]).execute()
                                st.rerun()

                with tab_deshabilitados:
                    col_dh1, col_dh2 = st.columns(2)
                    with col_dh1:
                        st.markdown("#### 👤 Trabajadores Deshabilitados")
                        res_emp_d = supabase.table("empleados").select("id, nombre, activo").eq("activo", False).execute()
                        for emp in (res_emp_d.data or []):
                            if st.checkbox(f"Reactivar {emp['nombre']}", value=False, key=f"emp_d_{emp['id']}"):
                                supabase.table("empleados").update({"activo": True}).eq("id", emp["id"]).execute()
                                st.rerun()
                    with col_dh2:
                        st.markdown("#### 📘 Exámenes Deshabilitados")
                        res_ex_d = supabase.table("examenes").select("id, apartado, activo").eq("activo", False).execute()
                        for ex_i in (res_ex_d.data or []):
                            if st.checkbox(f"Reactivar {ex_i['apartado']}", value=False, key=f"ex_d_{ex_i['id']}"):
                                supabase.table("examenes").update({"activo": True}).eq("id", ex_i["id"]).execute()
                                st.rerun()

                st.markdown("---")
                st.subheader("📥 Importar Registro de Exámenes (CSV)")
                archivo_csv_import = st.file_uploader("Seleccionar archivo CSV", type=["csv"], key="csv_import_uploader")
                
                if archivo_csv_import is not None and st.button("🚀 Procesar e Importar CSV", use_container_width=True):
                    try:
                        df_csv = pd.read_csv(archivo_csv_import, sep=None, engine='python')
                        res_emp_all = supabase.table("empleados").select("id, nombre").execute()
                        map_empleados = {emp["nombre"].strip().lower(): emp["id"] for emp in (res_emp_all.data or [])}

                        registros_insertados = 0
                        for idx_row, row in df_csv.iterrows():
                            nombre_emp = str(row.get("nombre empleado") or row.get("nombre_empleado") or "").strip()
                            emp_id = map_empleados.get(nombre_emp.lower(), None)
                            
                            # Mapeo exacto posición 7 (índice 6)
                            porcentaje_val = 0.0
                            if len(row) >= 7:
                                val_p7 = row.iloc[6]
                                porcentaje_val = float(val_p7) if not pd.isna(val_p7) else 0.0

                            fecha_inicio_clean = limpiar_timestamp_sql(row.get("fecha_inicio"))
                            fecha_fin_clean = limpiar_timestamp_sql(row.get("fecha_fin"))

                            registro_nuevo = {
                                "empleado_id": emp_id,
                                "nombre_empleado": nombre_emp if nombre_emp else "Desconocido",
                                "apartado": str(row.get("Apartado") or row.get("apartado") or ""),
                                "fecha_inicio": fecha_inicio_clean,
                                "fecha_fin": fecha_fin_clean,
                                "porcentaje_obtenido": porcentaje_val,
                                "nota": float(row.get("nota", 0)) if not pd.isna(row.get("nota")) else round(porcentaje_val / 10, 2),
                                "activo": True
                            }
                            supabase.table("intentos_examen").insert(registro_nuevo).execute()
                            registros_insertados += 1

                        st.success(f"✅ Importación completada: {registros_insertados} registros.")
                        st.rerun()
                    except Exception as e_csv:
                        st.error(f"❌ Error al procesar el archivo CSV: {e_csv}")
