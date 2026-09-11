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
        --background-color: #000000;
        --card-bg: #FFFFFF;
        --text-color: #2D3748;
        --border-radius: 12px;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        background-color: var(--background-color);
    }

    .stRadio label {
        font-size: 16px !important;
        font-weight: 600 !important;
        line-height: 1.4 !important;
        color: #2D3748 !important;
    }
    
    .stRadio div[role='radiogroup'] {
        gap: 10px;
    }

    .stRadio div[role='radiogroup'] > label {
        background-color: #FFFFFF !important;
        padding: 14px 18px !important;
        border-radius: 8px !important;
        border: 2px solid #E2E8F0 !important;
        transition: all 0.2s ease-in-out;
        width: 100%;
        margin-bottom: 8px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    .stRadio div[role='radiogroup'] > label p {
        color: #2D3748 !important;
        font-weight: 600 !important;
    }

    .stRadio div[role='radiogroup'] > label:hover {
        background-color: #EDF2F7 !important;
        border-color: #2B6CB0 !important;
    }

    .pregunta-titulo {
        font-size: 22px !important;
        font-weight: 700 !important;
        color: #1A365D;
        margin-bottom: 20px;
        line-height: 1.3;
        padding: 18px;
        background-color: #FFFFFF;
        border-left: 6px solid #2B6CB0;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
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
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
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

    .stButton > button {
        background-color: #2B6CB0 !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: background-color 0.2s ease !important;
    }

    .stButton > button:hover {
        background-color: #1A365D !important;
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
except Exception:
    gemini_client = None

claude_client = None
if CLAUDE_DISPONIBLE and CLAUDE_API_KEY:
    try:
        claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    except Exception:
        claude_client = None

# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE CONFIGURACIÓN Y SQL
# ---------------------------------------------------------
def obtener_tiempo_pregunta_config():
    try:
        res = supabase.table("config_prompts").select("prompt_texto").eq("nombre", "tiempo_pregunta").limit(1).execute()
        if res.data and res.data[0].get("prompt_texto"):
            return int(res.data[0]["prompt_texto"])
    except Exception:
        pass
    return 45

def guardar_tiempo_pregunta_config(nuevo_tiempo):
    try:
        supabase.table("config_prompts").upsert({
            "nombre": "tiempo_pregunta",
            "prompt_texto": str(nuevo_tiempo)
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar tiempo por pregunta: {e}")
        return False

def guardar_num_preguntas_config(tipo, cantidad):
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        supabase.table("config_prompts").upsert({
            "nombre": clave_nombre,
            "prompt_texto": str(cantidad)
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar número de preguntas ({tipo}): {e}")
        return False
        
def guardar_num_preguntas_config(tipo, cantidad):
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        res = supabase.table("config_prompts").select("id").eq("nombre", clave_nombre).execute()
        if res.data:
            supabase.table("config_prompts").update({"prompt_texto": str(cantidad)}).eq("nombre", clave_nombre).execute()
        else:
            supabase.table("config_prompts").insert({"nombre": clave_nombre, "prompt_texto": str(cantidad)}).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar número de preguntas ({tipo}): {e}")
        return False

def obtener_modelos_ia_disponibles():
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
if "tiempo_inicio_revision" not in st.session_state:
    st.session_state.tiempo_inicio_revision = None
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
if "examen_finalizado" not in st.session_state:
    st.session_state.examen_finalizado = False

TIEMPO_LIMITE_PREGUNTA = obtener_tiempo_pregunta_config()
UMBRAL_APROBADO_PORCENTAJE = 70.0

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
    "dificultad": "facil",
    "tipo": "teorica"
  }
]
"""

PROMPT_DEFECTO_EXAMEN = f"""Genera un conjunto de preguntas tipo test exclusivas para un examen basándote en el documento.
Asegúrate de incluir al menos dos preguntas por cada tema detectado en el documento.
Para cada pregunta, asigna por defecto el nivel de dificultad "dificil" y establece el campo "tipo" como "examen".
Cada pregunta debe incluir la propiedad "tiempo_segundos": {TIEMPO_LIMITE_PREGUNTA}.

Responde ÚNICAMENTE con un array JSON estructurado exactamente de la siguiente forma (sin envoltorios markdown extraños fuera del json):
[
  {{
    "pregunta": "Texto detailed de la pregunta",
    "opciones": ["Opción A", "Opción B", "Opción C", "Opción D"],
    "respuesta_correcta": 0,
    "pista": "Breve pista aclaratoria",
    "subindice": "Nombre Exacto del Tema",
    "dificultad": "dificil",
    "tipo": "examen",
    "tiempo_segundos": {TIEMPO_LIMITE_PREGUNTA}
  }}
]
"""

TEXTO_EXAMEN_GLOBAL_INFO = f"""En el examen global, deben aparecer al menos dos preguntas por tema siendo de nivel difícil por defecto y examen, cada pregunta por defecto son {TIEMPO_LIMITE_PREGUNTA} segundos. Da igual el número de preguntas a realizar."""

MAPEO_CAMPOS = {
    'q': 'pregunta',
    'question': 'pregunta',
    'ok': 'respuesta_correcta',
    'correcta': 'respuesta_correcta',
    'respuesta_correcta': 'respuesta_correcta',
    'correct': 'respuesta_correcta',
    'no': 'incorrectas',
    'incorrectas': 'incorrectas',
    'respuestas_incorrectas': 'incorrectas',
    'h': 'pista',
    'pista': 'pista',
    'hint': 'pista',
    'cat': 'categoria',
    'categoria': 'categoria',
    'category': 'categoria',
    'subindex': 'subindice',
    'subindice': 'subindice',
    'dificultad': 'dificultad',
    'difficulty': 'dificultad'
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

def consultar_ia(modelo, prompt, sistema=""):
    modelos_disponibles = obtener_modelos_ia_disponibles()
    cola_modelos = [modelo] + [m for m in modelos_disponibles if m != modelo]
    
    ultimo_error = None
    for mod in cola_modelos:
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
                    raise Exception("SDK de Anthropic/Claude no disponible o ANTHROPIC_API_KEY no configurada.")
            else:
                if not gemini_client:
                    raise Exception("El cliente de Gemini no está configurado.")
                
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
                raise Exception(f"Respuesta vacía recibida de Gemini ({mod}).")
        except Exception as err:
            ultimo_error = err
            continue

    raise Exception(f"Error procesando la consulta tras intentar con todos los modelos de la lista. Último error: {ultimo_error}")

def limpiar_timestamp_sql(ts_val):
    if pd.isna(ts_val) or ts_val is None:
        return None
    ts_str = str(ts_val).strip()
    if "T" in ts_str:
        ts_str = ts_str.replace("T", " ")
    if "." in ts_str:
        ts_str = ts_str.split(".")[0]
    return ts_str[:19]

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
    dificultad_val = item_normalizado.get("dificultad", "media")
    
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
        "dificultad": str(dificultad_val),
        "tipo": item_normalizado.get("tipo", "teorica")
    }
    
def seleccionar_preguntas_equilibradas(banco_completo, num_preguntas=15):
    if not banco_completo:
        return []

    temas_dict = {}
    for p in banco_completo:
        sub = str(p.get("subindice", "General")).strip()
        if sub not in temas_dict:
            temas_dict[sub] = []
        temas_dict[sub].append(p)

    num_temas = len(temas_dict)
    
    if num_temas * 2 > num_preguntas:
        cupo_por_tema = max(1, num_preguntas // num_temas)
    else:
        cupo_por_tema = 2

    seleccionadas = []
    
    for sub, pregs in temas_dict.items():
        sample_n = min(len(pregs), cupo_por_tema)
        seleccionadas.extend(random.sample(pregs, sample_n))

    if len(seleccionadas) < num_preguntas and len(banco_completo) > len(seleccionadas):
        restantes = [p for p in banco_completo if p not in seleccionadas]
        faltantes = min(num_preguntas - len(seleccionadas), len(restantes))
        seleccionadas.extend(random.sample(restantes, faltantes))

    if len(seleccionadas) > num_preguntas:
        seleccionadas = random.sample(seleccionadas, num_preguntas)

    seleccionadas.sort(key=lambda x: str(x.get("subindice", "General")).lower())
    return seleccionadas

def obtener_dias_restantes_mes():
    ahora = datetime.datetime.now()
    _, ultimo_dia = calendar.monthrange(ahora.year, me := ahora.month)
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

def generar_pdf_evaluacion_ia(empleado_nombre, texto_informe, anio):
    if not REPORTLAB_DISPONIBLE:
        return None
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    titulo_style = ParagraphStyle('Titulo', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor("#1A365D"), spaceAfter=10)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=11, leading=14, textColor=colors.HexColor("#4A5568"), spaceAfter=15)
    norm_style = ParagraphStyle('Norm', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor("#2D3748"))

    story.append(Paragraph("📄 Informe Profesional de Evaluación IA", titulo_style))
    story.append(Paragraph(f"<b>Trabajador:</b> {empleado_nombre} | <b>Año de Evaluación:</b> {anio}", sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#CBD5E0"), spaceAfter=15))

    lineas = texto_informe.split('\n')
    for linea in lineas:
        if linea.strip():
            story.append(Paragraph(linea.strip(), norm_style))
            story.append(Spacer(1, 6))

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
            st.session_state.examen_finalizado = False
            st.rerun()
        
    st.markdown("---")

    def guardar_intento_en_bd():
        if st.session_state.examen_finalizado:
            return
        total_p = len(st.session_state.preguntas_seleccionadas)
        correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
        porcentaje = round((correctas / total_p) * 100, 2)
        nota_final = round((correctas / total_p) * 10, 2)
        
        duracion_total = int(time.time() - (st.session_state.tiempo_inicio_examen or time.time()))
        tiempo_limite_total = total_p * TIEMPO_LIMITE_PREGUNTA
        tiempo_fin_examen = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        tiempo_ini_examen = datetime.datetime.fromtimestamp(st.session_state.tiempo_inicio_examen, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if st.session_state.tiempo_inicio_examen else tiempo_fin_examen
        
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
                "fecha_inicio": tiempo_ini_examen,
                "fecha_fin": tiempo_fin_examen,
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
            
            st.session_state.examen_finalizado = True

        except Exception as e:
            st.error(f"Error guardando intento: {e}")
    
    # MODO REVISIÓN PREVIA A FINALIZAR
    if st.session_state.modo_revision:
        if st.session_state.tiempo_inicio_revision is None:
            st.session_state.tiempo_inicio_revision = time.time()
            
        tiempo_revision_transcurrido = int(time.time() - st.session_state.tiempo_inicio_revision)
        tiempo_revision_restante = 300 - tiempo_revision_transcurrido
        
        st.subheader("🔍 Revisión de Examen previa a la entrega final")
        
        if not st.session_state.examen_finalizado:
            st.info("Revisa tus respuestas e indica si deseas modificar alguna antes de la entrega definitiva.")

            if tiempo_revision_restante > 0:
                st.warning(f"⏱️ Tiempo restante de revisión: **{tiempo_revision_restante // 60:02d}:{tiempo_revision_restante % 60:02d} minutos**. Si se agota, el examen se finalizará automáticamente.")
            else:
                st.error("⏰ ¡Tiempo de revisión agotado (5 minutos)! Finalizando el examen automáticamente...")

            for i, p_item in enumerate(st.session_state.preguntas_seleccionadas):
                resp_actual = next((r for r in st.session_state.respuestas_detalle if r["idx_pregunta"] == i), None)
                texto_resp = resp_actual["opcion_elegida"] if resp_actual else "En blanco (Sin responder)"
                
                t_restante = st.session_state.tiempos_restantes_preguntas.get(i, TIEMPO_LIMITE_PREGUNTA)
                
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"**Pregunta {i+1}:** {p_item['pregunta']}")
                    st.caption(f"Categoría/Tema: **{p_item.get('subindice', 'General')}** | Respuesta actual: **{texto_resp}** | ⏱️ Tiempo restante: **{t_restante} s** | Dificultad: **{p_item.get('dificultad', 'dificil')}**")
                with c2:
                    btn_bloqueado = (t_restante <= 0 or tiempo_revision_restante <= 0)
                    if st.button("Modificar", key=f"mod_rev_{i}", disabled=btn_bloqueado, use_container_width=True):
                        st.session_state.indice_pregunta = i
                        st.session_state.modo_revision = False
                        st.session_state.modificando_desde_revision = True
                        st.session_state.tiempo_inicio_pregunta = time.time()
                        st.rerun()
                    if btn_bloqueado:
                        st.caption("🔒 Tiempo agotado")
                st.write("---")

            if tiempo_revision_restante <= 0:
                guardar_intento_en_bd()
                st.rerun()
            else:
                if st.button("✅ Confirmar y Entregar Examen Definitivamente", use_container_width=True):
                    guardar_intento_en_bd()
                    st.rerun()
        else:
            total_p = len(st.session_state.preguntas_seleccionadas)
            correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
            porcentaje = round((correctas / total_p) * 100, 2)
            nota_final = round((correctas / total_p) * 10, 2)
            estado_evaluacion = obtener_estado_evaluacion(porcentaje, st.session_state.sobrepaso_tiempo_global)

            if "APROBADO" in estado_evaluacion:
                st.success(f"🎉 Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%) | **{estado_evaluacion}**")
            else:
                st.error(f"❌ Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%) | **{estado_evaluacion}**")

            if st.button("Volver al Inicio", use_container_width=True):
                st.session_state.examen_activo = False
                st.session_state.modo_revision = False
                st.session_state.examen_finalizado = False
                st.session_state.tiempo_inicio_revision = None
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
                st.caption(f"📌 **Subíndice/Categoría:** {p_actual.get('subindice', p_actual.get('apartado', 'General'))} | Dificultad: **{p_actual.get('dificultad', 'dificil')}**")
            with col_ayuda:
                st.caption(f"💡 Ayudas disponibles: **{st.session_state.comodines_restantes} / 3**")

            tiempo_base = st.session_state.tiempos_restantes_preguntas.get(idx, TIEMPO_LIMITE_PREGUNTA)
            
            if st.session_state.tiempo_inicio_pregunta is None:
                st.session_state.tiempo_inicio_pregunta = time.time()
                
            tiempo_transcurrido = int(time.time() - st.session_state.tiempo_inicio_pregunta)
            tiempo_restante = tiempo_base - tiempo_transcurrido
            
            st.progress(max(0.0, tiempo_restante / TIEMPO_LIMITE_PREGUNTA))
            
            deshabilitar_opciones = False
            if tiempo_restante > 0:
                st.caption(f"⏱️ Tiempo restante: **{tiempo_restante} segundos**")
            else:
                st.warning("⏰ ¡Tiempo agotado en esta pregunta! Se registrará la casilla marcada.")
                deshabilitar_opciones = True
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
                    "dificultad": p_actual.get("dificultad", "dificil"),
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
                        st.session_state.tiempo_inicio_pregunta = None
                    
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

        else:
            st.session_state.modo_revision = True
            st.rerun()

    # MENÚ PRINCIPAL
    else:
        st.info(f"🎯 **Criterio de Evaluación:** Para obtener un resultado **APROBADO**, debes alcanzar una nota mínima de **{UMBRAL_APROBADO_PORCENTAJE / 10} / 10** ({int(UMBRAL_APROBADO_PORCENTAJE)}% de aciertos). Tiempo configurado por pregunta: **{TIEMPO_LIMITE_PREGUNTA} segundos**.")

        if st.session_state.es_croma:
            tab_examenes, tab_admin_manual, tab_admin_resultados, tab_admin_export, tab_admin_analisis, tab_admin_claude, tab_admin_gestion = st.tabs([
                "📝 Realizar Examen",
                "📄 Cargar Manual / Prompt", 
                "📊 Resultados / Edición", 
                "📥 Exportación e Informes",
                "📈 Analítica e IA",
                "🤖 Consultas Gemini / IA",
                "⚙️ Gestión y Configuración"
            ])
        else:
            tab_examenes, tab_mis_resultados, tab_mi_analisis = st.tabs([
                "📝 Realizar Examen", 
                "📊 Mis Resultados e Historial",
                "📈 Mi Rendimiento e Informes IA"
            ])

        # TAB: REALIZAR EXAMEN
        with tab_examenes:
            ahora = datetime.datetime.now(datetime.timezone.utc)
            primer_dia_mes = datetime.datetime(ahora.year, ahora.month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            user_intentos = []
            try:
                res_user_intentos = supabase.table("intentos_examen").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("activo", True)\
                    .gte("fecha_inicio", primer_dia_mes).execute()
                user_intentos = res_user_intentos.data if res_user_intentos.data else []
            except Exception as e:
                try:
                    res_fallback = supabase.table("intentos_examen").select("*")\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("activo", True).execute()
                    fallback_data = res_fallback.data if res_fallback and hasattr(res_fallback, 'data') else []
                except Exception:
                    fallback_data = []

                if fallback_data:
                    str_mes_actual = f"{ahora.year}-{ahora.month:02d}"
                    user_intentos = [
                        it for it in fallback_data 
                        if it.get("fecha_inicio") and str(it["fecha_inicio"]).startswith(str_mes_actual)
                    ]

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
                res_examenes = supabase.table("examenes").select("*").eq("activo", True).execute()
                raw_examenes = res_examenes.data if res_examenes.data else []

                examenes_disponibles = [
                    ex for ex in raw_examenes 
                    if ex.get("activo") is True or ex.get("activo") is None
                ]
            except Exception as e:
                examenes_disponibles = []
                st.error(f"Error al cargar manuales de la base de datos: {e}")

            if examenes_disponibles:
                st.subheader("📋 Seleccionar Modalidad")

                tab_global, tab_manual = st.tabs(["🌐 Examen Global", "📘 Examen por Manual"])
                
                with tab_global:
                    num_p_global = obtener_num_preguntas_config("global")
                    st.info(f"El Examen Global seleccionará **{num_p_global} preguntas aleatorias** de entre todos los manuales.")
                    
                    texto_global_bd = TEXTO_EXAMEN_GLOBAL_INFO
                    try:
                        res_info_g = supabase.table("config_prompts").select("prompt_texto").eq("nombre", "info_examen_global").limit(1).execute()
                        if res_info_g.data and res_info_g.data[0].get("prompt_texto"):
                            texto_global_bd = res_info_g.data[0]["prompt_texto"]
                    except Exception:
                        pass

                    st.markdown(f"**Condiciones del Examen Global:**\n> {texto_global_bd}")
                    
                    ya_hecho_global = "GLOBAL COMPLETO" in dict_realizados
                    permitido_global = autorizaciones_set.__contains__("GLOBAL COMPLETO")
                    bloqueado_global = ya_hecho_global and not permitido_global and not st.session_state.es_croma

                    if ya_hecho_global:
                        info_g = dict_realizados["GLOBAL COMPLETO"]
                        est_txt = obtener_estado_evaluacion(info_g['porcentaje'])
                        st.warning(f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{info_g['nota']} / 10** ({info_g['porcentaje']}%) | **{est_txt}**")
                        if permitido_global:
                            st.success("🔓 **El administrador te ha habilitado un nuevo intento para este examen.**")
                        elif not st.session_state.es_croma:
                            st.error("🔒 Debes esperar al próximo mes o solicitar una autorización al administrador para volver a realizarlo.")

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
                                                "dificultad": p.get("dificultad", "dificil"),
                                                "tipo": "teorica"
                                            })
                        
                        preguntas_preparadas = seleccionar_preguntas_equilibradas(banco_global, num_p_global)
                        
                        st.session_state.examen_id = None
                        st.session_state.apartado_actual = "GLOBAL COMPLETO"
                        st.session_state.preguntas_seleccionadas = preguntas_preparadas
                        st.session_state.indice_pregunta = 0
                        st.session_state.respuestas_detalle = []
                        st.session_state.tiempos_restantes_preguntas = {}
                        st.session_state.modificando_desde_revision = False
                        st.session_state.tiempo_inicio_examen = time.time()
                        st.session_state.tiempo_inicio_pregunta = None
                        st.session_state.tiempo_inicio_revision = None
                        st.session_state.comodines_restantes = 3
                        st.session_state.pistas_activadas = set()
                        st.session_state.sobrepaso_tiempo_global = False
                        st.session_state.examen_finalizado = False
                        st.session_state.examen_activo = True
                        st.rerun()

                with tab_manual:
                    st.subheader("Selecciona el Manual para la Evaluación")
                    num_p_manual = obtener_num_preguntas_config("manual")
                    
                    manual_nombres = [ex['apartado'] for ex in examenes_disponibles]
                    manual_sel_nom = st.selectbox("Selecciona un manual:", manual_nombres, key="sel_manual_eval")
                    ex_obj = next((ex for ex in examenes_disponibles if ex['apartado'] == manual_sel_nom), None)
                    
                    if ex_obj:
                        nombre_apt = ex_obj['apartado']
                        num_p_totales = len(ex_obj.get("preguntas_json", [])) if isinstance(ex_obj.get("preguntas_json"), list) else 0
                        st.info(f"📊 **Información del Manual:** Se han generado un total de **{num_p_totales} preguntas** para este manual. En el examen se presentarán **{num_p_manual} preguntas**.")

                        ya_hecho_manual = nombre_apt in dict_realizados
                        permitido_manual = autorizaciones_set.__contains__(nombre_apt)
                        bloqueado_manual = ya_hecho_manual and not permitido_manual and not st.session_state.es_croma

                        if ya_hecho_manual:
                            info_m = dict_realizados[nombre_apt]
                            est_txt = obtener_estado_evaluacion(info_m['porcentaje'])
                            st.warning(f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{info_m['nota']} / 10** | **{est_txt}**")
                            if permitido_manual:
                                st.success("🔓 **El administrador te ha habilitado un nuevo intento para este examen.**")
                            elif not st.session_state.es_croma:
                                st.error("🔒 Requiere autorización del administrador para repetirlo este mes.")
                        
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
                                                "dificultad": p.get("dificultad", "dificil"),
                                                "tipo": "teorica"
                                            })
                            
                            preguntas_preparadas = seleccionar_preguntas_equilibradas(banco_manual, num_p_manual)
                            
                            st.session_state.examen_id = ex_obj["id"]
                            st.session_state.apartado_actual = nombre_apt
                            st.session_state.preguntas_seleccionadas = preguntas_preparadas
                            st.session_state.indice_pregunta = 0
                            st.session_state.respuestas_detalle = []
                            st.session_state.tiempos_restantes_preguntas = {}
                            st.session_state.modificando_desde_revision = False
                            st.session_state.tiempo_inicio_examen = time.time()
                            st.session_state.tiempo_inicio_pregunta = None
                            st.session_state.tiempo_inicio_revision = None
                            st.session_state.comodines_restantes = 3
                            st.session_state.pistas_activadas = set()
                            st.session_state.sobrepaso_tiempo_global = False
                            st.session_state.examen_finalizado = False
                            st.session_state.examen_activo = True
                            st.rerun()

                        res_intentos_m = supabase.table("intentos_examen").select("*")\
                            .eq("empleado_id", st.session_state.user_id)\
                            .eq("apartado", nombre_apt)\
                            .eq("activo", True)\
                            .order("fecha_inicio", desc=True).execute()
                        intentos_m = res_intentos_m.data if res_intentos_m.data else []

                        if intentos_m:
                            st.markdown("---")
                            st.markdown(f"#### 📊 Estadísticas por Tema/Subíndice para {nombre_apt}")
                            
                            banco_actual_m = ex_obj.get("preguntas_json", [])
                            temas_totales_banco = set()
                            if isinstance(banco_actual_m, list):
                                for p_b in banco_actual_m:
                                    if isinstance(p_b, dict):
                                        temas_totales_banco.add(str(p_b.get("subindice", "General")).strip())

                            ultimo_intento = intentos_m[0]
                            resp_ult = ultimo_intento.get("respuestas_usuario", [])
                            if resp_ult:
                                st.markdown("##### 📈 Rendimiento del Último Examen Realizado (Gráfica Lineal)")
                                df_ult = pd.DataFrame(resp_ult)
                                if "subindice" not in df_ult.columns:
                                    df_ult["subindice"] = df_ult.get("categoria", "General")
                                df_ult["subindice"] = df_ult["subindice"].fillna("General")

                                ult_resumen = df_ult.groupby("subindice").agg(
                                    Aciertos=('es_correcta', lambda x: sum(x == True)),
                                    Total=('es_correcta', 'count')
                                ).reset_index()
                                ult_resumen["% Aciertos"] = (ult_resumen["Aciertos"] / ult_resumen["Total"] * 100).round(2)

                                for t_b in temas_totales_banco:
                                    if t_b not in ult_resumen["subindice"].values:
                                        ult_resumen = pd.concat([ult_resumen, pd.DataFrame([{
                                            "subindice": t_b, "Aciertos": 0, "Total": 0, "% Aciertos": 0.0
                                        }])], ignore_index=True)

                                st.line_chart(ult_resumen.set_index("subindice")["% Aciertos"], use_container_width=True)

                            todas_resp_m = []
                            for it_m in intentos_m:
                                resp_usr = it_m.get("respuestas_usuario", [])
                                if isinstance(resp_usr, list):
                                    todas_resp_m.extend(resp_usr)

                            if todas_resp_m:
                                st.markdown("##### 📊 Histórico Acumulado por Tema/Subíndice")
                                df_resp_m = pd.DataFrame(todas_resp_m)
                                if "subindice" not in df_resp_m.columns:
                                    df_resp_m["subindice"] = df_resp_m.get("categoria", "General")
                                df_resp_m["subindice"] = df_resp_m["subindice"].fillna("General")

                                resumen_cat_m = df_resp_m.groupby("subindice").agg(
                                    Aciertos=('es_correcta', lambda x: sum(x == True)),
                                    Fallos_o_Blanco=('es_correcta', lambda x: sum(x == False)),
                                    Total=('es_correcta', 'count')
                                ).reset_index()

                                for t_b in temas_totales_banco:
                                    if t_b not in resumen_cat_m["subindice"].values:
                                        resumen_cat_m = pd.concat([resumen_cat_m, pd.DataFrame([{
                                            "subindice": t_b, "Aciertos": 0, "Fallos_o_Blanco": 0, "Total": 0
                                        }])], ignore_index=True)

                                resumen_cat_m["% Aciertos"] = (resumen_cat_m["Aciertos"] / resumen_cat_m["Total"].replace(0, 1) * 100).round(2)
                                resumen_cat_m.loc[resumen_cat_m["Total"] == 0, "% Aciertos"] = 0.0

                                st.bar_chart(
                                    resumen_cat_m.set_index("subindice")[["Aciertos", "Fallos_o_Blanco"]], 
                                    use_container_width=True
                                )
                                st.dataframe(resumen_cat_m, use_container_width=True, hide_index=True)
            else:
                st.warning("No hay manuales activos cargados en el sistema.")

        # TAB: CARGAR MANUAL Y PROMPT (ADMIN)
        if st.session_state.es_croma and tab_admin_manual:
            with tab_admin_manual:
                st.subheader("📄 Cargar Nuevo Manual en PDF y Generar Examen con IA")
                
                cfg_prompt_ex = None
                try:
                    res_cfg_ex = supabase.table("config_prompts").select("*").eq("nombre", "prompt_examen").limit(1).execute()
                    if res_cfg_ex.data:
                        cfg_prompt_ex = res_cfg_ex.data[0]
                except Exception:
                    cfg_prompt_ex = None

                prompt_defecto_cargador = cfg_prompt_ex.get("prompt_texto") if cfg_prompt_ex else PROMPT_DEFECTO_EXAMEN

                with st.form("form_cargar_manual", clear_on_submit=False):
                    nombre_apartado = st.text_input("📘 Nombre del Manual/Apartado (Ej. Manual Seguridad 2026):*")
                    pdf_file = st.file_uploader("📂 Selecciona el documento PDF:*", type=["pdf"])
                    
                    prompt_manual_input = st.text_area(
                        "💬 Prompt para la IA (Generación de JSON):",
                        value=prompt_defecto_cargador,
                        height=200
                    )
                    
                    modelos_ia_opciones = obtener_modelos_ia_disponibles()
                    modelo_cargador_sel = st.selectbox("🤖 Modelo de IA a utilizar:", options=modelos_ia_opciones, index=0)
                    
                    btn_procesar_manual = st.form_submit_button("🚀 Procesar Documento y Guardar Examen", use_container_width=True)

                if btn_procesar_manual:
                    if not nombre_apartado.strip():
                        st.error("❌ Por favor indica el nombre del manual/apartado.")
                    elif not pdf_file:
                        st.error("❌ Por favor sube un archivo PDF válido.")
                    else:
                        status_box = st.status("🔄 Procesando manual en el sistema...", expanded=True)
                        try:
                            status_box.write("📖 Extrayendo texto del archivo PDF...")
                            reader = PdfReader(pdf_file)
                            texto_pdf = ""
                            for page in reader.pages:
                                page_text = page.extract_text()
                                if page_text:
                                    texto_pdf += page_text + "\n"

                            if not texto_pdf.strip():
                                raise Exception("No se pudo extraer texto del PDF subido.")

                            status_box.write(f"🧠 Consultando al modelo {modelo_cargador_sel}...")
                            prompt_final = f"{prompt_manual_input}\n\n[CONTENIDO DEL DOCUMENTO PDF]:\n{texto_pdf[:40000]}"
                            
                            res_ia_raw = consultar_ia(modelo_cargador_sel, prompt_final, sistema="Eres un generador de exámenes técnicos estructurados exclusivamente en formato JSON.")
                            
                            status_box.write("⚙️ Normalizando preguntas y comprobando formato JSON...")
                            
                            txt_json = res_ia_raw.strip()
                            if "```json" in txt_json:
                                txt_json = txt_json.split("```json")[1].split("```")[0].strip()
                            elif "```" in txt_json:
                                txt_json = txt_json.split("```")[1].split("```")[0].strip()

                            parsed_json = json.loads(txt_json)
                            preguntas_validas = []

                            if isinstance(parsed_json, list):
                                for item in parsed_json:
                                    p_norm = normalizar_pregunta_json(item)
                                    if p_norm:
                                        preguntas_validas.append(p_norm)

                            if not preguntas_validas:
                                raise Exception("No se generaron preguntas válidas a partir del documento.")

                            status_box.write("💾 Registrando examen en Supabase...")
                            
                            registro_nuevo_examen = {
                                "apartado": nombre_apartado.strip(),
                                "preguntas_json": preguntas_validas,
                                "activo": True
                            }
                            
                            supabase.table("examenes").insert(registro_nuevo_examen).execute()
                            
                            status_box.update(label="✅ ¡Manual procesado y guardado con éxito!", state="complete", expanded=False)
                            st.success(f"🎉 Se han generado exitosamente **{len(preguntas_validas)} preguntas** para el manual **{nombre_apartado.strip()}**.")
                            time.sleep(2)
                            st.rerun()

                        except Exception as err_m:
                            status_box.update(label="❌ Error al procesar el manual", state="error", expanded=True)
                            st.error(f"Se produjo un fallo al procesar el documento: {err_m}")

        # VISTA USUARIO: MIS RESULTADOS
        if not st.session_state.es_croma:
            with tab_mis_resultados:
                st.subheader("📌 Mis Calificaciones e Historial Completo")
                
                res_mis_intentos = supabase.table("intentos_examen").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("activo", True)\
                    .order("fecha_inicio", desc=True).execute()
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
                        
                        expirado = i.get("sobrepasado_tiempo", False)
                        estado = obtener_estado_evaluacion(porc, expirado)
                        
                        with st.expander(f"Examen #{i['id']} - {i.get('apartado')} | {fecha_str} | Nota: {i.get('nota', 0)}/10 | Estado: {estado}"):
                            st.write(f"**Resultado:** {num_correctas} / {total_p} aciertos ({porc}%) - **{estado}**")
                            
                            if respuestas:
                                df_resp = pd.DataFrame(respuestas)
    
                                if "subindice" not in df_resp.columns:
                                    df_resp["subindice"] = df_resp.get("categoria", "General")
                                df_resp["subindice"] = df_resp["subindice"].fillna("General")

                                resumen_cat = df_resp.groupby("subindice").agg(
                                    Aciertos=('es_correcta', lambda x: sum(x == True)),
                                    Fallos_o_Blanco=('es_correcta', lambda x: sum(x == False)),
                                    Total=('es_correcta', 'count')
                                ).reset_index()

                                st.markdown("#### 📊 Desglose de Aciertos por Categoría / Tema")
                                st.bar_chart(
                                    resumen_cat.set_index("subindice")[["Aciertos", "Fallos_o_Blanco"]], 
                                    use_container_width=True
                                )

                                st.dataframe(
                                    resumen_cat.rename(columns={"subindice": "Categoría / Tema"}), 
                                    use_container_width=True, 
                                    hide_index=True
                                )
                            
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
                                st.write("### ❌ Preguntas Erróneas o Sin Responder:")
                                for idx_e, err in enumerate(erroneas, 1):
                                    st.markdown(f"**{idx_e}. {err.get('pregunta')}**")
                                    st.markdown(f"- **Tu respuesta:** `{err.get('opcion_elegida')}`")
                                    st.markdown(f"- **Respuesta correcta:** `{err.get('respuesta_correcta_texto', 'No disponible')}`")
                                    st.write("---")
                            else:
                                st.success("🎉 ¡Excelente! No cometiste ningún error en este examen.")
                else:
                    st.write("Aún no has realizado ningún examen.")

            with tab_mi_analisis:
                st.subheader("📈 Mi Rendimiento Personal")
                
                res_mis_graf = supabase.table("intentos_examen").select("id, nota, porcentaje_obtenido, fecha_inicio, apartado")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("activo", True)\
                    .order("fecha_inicio", desc=False).execute()
                mis_datos_graf = res_mis_graf.data if res_mis_graf.data else []
                
                if mis_datos_graf:
                    df_mi_graf = pd.DataFrame(mis_datos_graf)
                    df_mi_graf["fecha"] = df_mi_graf["fecha_inicio"].str[:10]
                    
                    st.markdown("#### 📊 Evolución Histórica de Calificaciones")
                    st.line_chart(df_mi_graf, x="fecha", y="nota")
                    
                    st.markdown("#### 📄 Informe Profesional de Evaluación IA")
                    anio_actual_int = datetime.datetime.now().year
                    res_mi_an = supabase.table("analisis_ia_empleados").select("*")\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("anio", anio_actual_int)\
                        .order("fecha_generacion", desc=True)\
                        .limit(1).execute()
                    
                    if res_mi_an.data:
                        txt_eval = res_mi_an.data[0]["analisis_texto"]
                        st.info(txt_eval)
                        pdf_eval_usr = generar_pdf_evaluacion_ia(st.session_state.user_nombre, txt_eval, anio_actual_int)
                        if pdf_eval_usr:
                            st.download_button(
                                label="📄 Exportar Informe IA en PDF",
                                data=pdf_eval_usr,
                                file_name=f"Informe_Evaluacion_IA_{st.session_state.user_nombre.replace(' ', '_')}_{anio_actual_int}.pdf",
                                mime="application/pdf",
                                key="pdf_eval_usr_btn"
                            )
                    else:
                        st.caption("Aún no hay un informe cualitativo generado para ti en el ciclo actual.")
                else:
                    st.info("No dispones de suficientes evaluaciones registradas para generar gráficos.")

        # ADMIN CROMA - RESULTADOS Y EDICIÓN
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Historial General y Edición por Usuario")
                
                res_todos = supabase.table("intentos_examen").select("*")\
                    .eq("activo", True)\
                    .order("id", desc=True).execute()
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
                        intentos_filtrados_ordenados = sorted(intentos_filtrados, key=lambda x: x['id'], reverse=True)
                        map_id_to_intento = {it['id']: it for it in intentos_filtrados_ordenados}
                        
                        def format_func(it_id):
                            it = map_id_to_intento[it_id]
                            est_it = obtener_estado_evaluacion(it.get("porcentaje_obtenido", 0), it.get("sobrepasado_tiempo"))
                            return f"ID #{it['id']} - {it.get('nombre_empleado')} ({it.get('apartado')}) | Nota: {it.get('nota', 0)}/10 [{est_it}]"

                        opciones_ids = list(map_id_to_intento.keys())
                        
                        if st.session_state.intento_auditado_id_sel not in opciones_ids:
                            st.session_state.intento_auditado_id_sel = opciones_ids[0]

                        idx_defecto_intento = opciones_ids.index(st.session_state.intento_auditado_id_sel)

                        intento_target_id = st.selectbox(
                            "Selecciona un examen para auditar/editar:", 
                            options=opciones_ids,
                            index=idx_defecto_intento,
                            format_func=format_func,
                            key="select_intento_audit_id"
                        )
                        
                        st.session_state.intento_auditado_id_sel = intento_target_id

                        intento_obj = map_id_to_intento[intento_target_id]
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
                                if isinstance(preguntas_banco, list):
                                    preguntas_validas = [p for p in preguntas_banco if isinstance(p, dict)]
                                    for p_b in preguntas_validas:
                                        p_texto = p_b.get("pregunta")
                                        if isinstance(p_texto, str) and p_texto.strip() == pregunta_texto_limpio:
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
                                                "fecha_modificacion": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                                "valor_anterior": json.dumps({"es_correcta": p_objetivo.get("es_correcta"), "respuesta_correcta": texto_respuesta_correcta}),
                                                "valor_nuevo": json.dumps({"es_correcta": nuevo_estado, "respuesta_correcta": resp_correcta_input}),
                                                "motivo": motivo_edicion.strip()
                                            }
                                            
                                            supabase.table("auditoria_modificaciones").insert(registro_audit).execute()
                                            st.success("✅ Corrección guardada y auditada correctamente.")
                                            time.sleep(1)
                                            st.rerun()

                                        except Exception as err:
                                            st.error(f"⚠️ Error al guardar en la base de datos: {err}")

        # ADMIN CROMA - EXPORTACIÓN E INFORMES
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación e Informes")
                
                res_todos = supabase.table("intentos_examen").select("*")\
                    .eq("activo", True)\
                    .order("fecha_inicio", desc=False).execute()
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
                            est_exp = obtener_estado_evaluacion(i.get("porcentaje_obtenido", 0), i.get("sobrepasado_tiempo"))
                            opciones_examenes.append(
                                f"Examen #{i['id']} - {i.get('nombre_empleado')} | {i.get('apartado')} | Nota: {i.get('nota', 0)}/10 [{est_exp}]"
                            )
                        
                        opcion_elegida = st.selectbox("Selecciona el examen a exportar:", opciones_examenes)
                        idx_sel = opciones_examenes.index(opcion_elegida)
                        examen_sel = intentos_exp_filtrados[idx_sel]

                        col_exp_a, col_exp_b = st.columns(2)
                        with col_exp_a:
                            df_export = pd.DataFrame([examen_sel])
                            buffer_excel = io.BytesIO()
                            with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                                df_export.to_excel(writer, index=False, sheet_name="Examen")
                            
                            st.download_button(
                                label="📥 Descargar Excel de este Examen",
                                data=buffer_excel.getvalue(),
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

                st.markdown("---")
                st.subheader("📥 Importar Registro de Exámenes (CSV)")
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

                                minutos_val = row.get("minutes")
                                if not pd.isna(minutos_val) and minutos_val is not None:
                                    t_limite = int(minutos_val) * 60
                                else:
                                    t_limite = int(row.get("tiempo_limite") or row.get("tiempo_limite_segundos") or 0)

                                fecha_inicio_clean = limpiar_timestamp_sql(row.get("fecha_inicio"))
                                fecha_fin_clean = limpiar_timestamp_sql(row.get("fecha_fin"))

                                sobrepasado = False
                                duracion_seg = 0
                                if fecha_inicio_clean and fecha_fin_clean:
                                    try:
                                        dt_ini = pd.to_datetime(fecha_inicio_clean)
                                        dt_fin = pd.to_datetime(fecha_fin_clean)
                                        duracion_seg = int((dt_fin - dt_ini).total_seconds())
                                        if t_limite > 0 and duracion_seg > t_limite:
                                            sobrepasado = True
                                    except Exception:
                                        pass

                                if len(row) >= 8 and not pd.isna(row.iloc[7]):
                                    porcentaje_val = float(row.iloc[7])
                                else:
                                    porcentaje_val = float(row.get("porcentaje_obtenido", 0)) if not pd.isna(row.get("porcentaje_obtenido")) else 0.0

                                nota_val = float(row.get("nota", 0)) if not pd.isna(row.get("nota")) else 0.0

                                if sobrepasado:
                                    nota_val = 0.0
                                    porcentaje_val = 0.0

                                registro_nuevo = {
                                    "empleado_id": emp_id,
                                    "nombre_empleado": nombre_emp if nombre_emp else "Desconocido",
                                    "apartado": str(row.get("Apartado") or row.get("apartado") or ""),
                                    "fecha_inicio": fecha_inicio_clean,
                                    "fecha_fin": fecha_fin_clean,
                                    "tiempo_total_segundos": duracion_seg if duracion_seg > 0 else int(row.get("tiempo_total_segundos", 0)),
                                    "tiempo_limite": t_limite,
                                    "porcentaje_obtenido": porcentaje_val,
                                    "nota": nota_val,
                                    "respuestas_usuario": resp_json,
                                    "sobrepasado_tiempo": sobrepasado,
                                    "activo": True
                                }

                                try:
                                    supabase.table("intentos_examen").insert(registro_nuevo).execute()
                                    registros_insertados += 1
                                except Exception as err_ins:
                                    st.error(f"Error importando fila {idx_row + 1} ({nombre_emp}): {err_ins}")
                                    errores_import += 1

                            if registros_insertados > 0:
                                st.success(f"✅ Importación completada: Se insertaron **{registros_insertados}** registros correctamente.")
                                time.sleep(1.5)
                                st.rerun()

                        except Exception as e_csv:
                            st.error(f"❌ Error al procesar el archivo CSV: {e_csv}")

        # ADMIN CROMA - ANALÍTICA E IA
        if st.session_state.es_croma and tab_admin_analisis:
            with tab_admin_analisis:
                st.subheader("📈 Analítica Global e Inteligencia Artificial")
                
                try:
                    res_m_counts = supabase.table("examenes").select("id, apartado, preguntas_json, activo").execute()
                    if res_m_counts.data:
                        st.markdown("### 📊 Conteo de Preguntas Generadas por Examen/Manual")
                        data_counts = []
                        for ex_m in res_m_counts.data:
                            preg_list = ex_m.get("preguntas_json", [])
                            data_counts.append({
                                "ID": ex_m.get("id"),
                                "Manual / Examen": ex_m.get("apartado"),
                                "Preguntas Generadas": len(preg_list) if isinstance(preg_list, list) else 0,
                                "Estado": "Activo" if ex_m.get("activo") else "Deshabilitado"
                            })
                        st.dataframe(pd.DataFrame(data_counts), use_container_width=True, hide_index=True)
                except Exception as e_cnt:
                    st.warning(f"No se pudo obtener el desglose de preguntas por examen: {e_cnt}")

                st.markdown("---")

                cfg_eval = None
                try:
                    res_cfg_eval = supabase.table("config_prompts").select("*").eq("nombre", "evaluacion_empleado").limit(1).execute()
                    if res_cfg_eval.data:
                        cfg_eval = res_cfg_eval.data[0]
                except Exception:
                    cfg_eval = None

                prompt_defecto_eval = cfg_eval.get("prompt_texto") if cfg_eval else "Analiza a este trabajador y da tu opinión como profesional de su evolución en los exámenes realizados, este año, y años anteriores."

                res_all_intentos = supabase.table("intentos_examen").select("*")\
                    .eq("activo", True)\
                    .order("fecha_inicio", desc=False).execute()
                data_intentos_val = res_all_intentos.data if res_all_intentos.data else []

                if data_intentos_val:
                    df_all = pd.DataFrame(data_intentos_val)
                    df_all["fecha_inicio_dt"] = pd.to_datetime(df_all["fecha_inicio"], errors='coerce')
                    df_all["anio_int"] = df_all["fecha_inicio_dt"].dt.year
                    
                    anios_m_disponibles = sorted(list(df_all["anio_int"].dropna().astype(int).unique()), reverse=True)
                    anio_metrica_sel = st.selectbox("📅 Selecciona el año de consulta para métricas:", anios_m_disponibles)
                    
                    st.markdown("### 📊 Gráficas y Métricas por Empleado (Histórico Completo SQL)")
                    
                    res_emp_activos_todos = supabase.table("empleados").select("id, nombre").eq("activo", True).execute()
                    emp_list_select = res_emp_activos_todos.data if res_emp_activos_todos.data else []
                    
                    nombres_activos_solamente = sorted(list(set([e["nombre"] for e in emp_list_select])))
                    nombres_trabajadores = ["Todos los trabajadores activos"] + nombres_activos_solamente
                    
                    col_f_emp, col_f_ex = st.columns(2)
                    with col_f_emp:
                        emp_seleccionado_nombre = st.selectbox("👤 Selecciona un trabajador:", nombres_trabajadores)
                    with col_f_ex:
                        examenes_unicos_hist = ["Todos"] + sorted(list(df_all["apartado"].dropna().unique()))
                        examen_seleccionado_filtro = st.selectbox("📘 Selecciona un examen/manual:", examenes_unicos_hist)

                    if emp_seleccionado_nombre == "Todos los trabajadores activos":
                        df_emp_tot = df_all[df_all["nombre_empleado"].isin(nombres_activos_solamente)]
                    else:
                        df_emp_tot = df_all[df_all["nombre_empleado"].str.strip().str.lower() == emp_seleccionado_nombre.strip().lower()]

                    if examen_seleccionado_filtro != "Todos":
                        df_emp_tot = df_emp_tot[df_emp_tot["apartado"] == examen_seleccionado_filtro]

                    df_emp_anio = df_emp_tot[df_emp_tot["anio_int"] == anio_metrica_sel]

                    if not df_emp_anio.empty:
                        total_ex = len(df_emp_anio)
                        nota_media = round(df_emp_anio["nota"].mean(), 2)
                        porcentaje_medio = round(nota_media * 10, 2)
                        nota_max = round(df_emp_anio["nota"].max(), 2)
                        nota_min = round(df_emp_anio["nota"].min(), 2)
                        porc_max = round(df_emp_anio["porcentaje_obtenido"].max(), 2)
                        porc_min = round(df_emp_anio["porcentaje_obtenido"].min(), 2)

                        df_resumen_metricas = pd.DataFrame([{
                            "Año": anio_metrica_sel,
                            "Total Exámenes": total_ex,
                            "Nota Media": nota_media,
                            "Porcentaje Medio (%)": porcentaje_medio,
                            "Nota Máxima": nota_max,
                            "Nota Mínima": nota_min,
                            "Porcentaje Máximo (%)": porc_max,
                            "Porcentaje Mínimo (%)": porc_min
                        }])

                        st.dataframe(df_resumen_metricas, use_container_width=True, hide_index=True)
                        st.line_chart(df_emp_tot, x="fecha_inicio", y="nota")
                    else:
                        st.info(f"No se registran exámenes para la selección aplicada en el año **{anio_metrica_sel}**.")

                    st.markdown("---")
                    st.markdown("### 📄 Informe Profesional de Evaluación IA")
                    
                    with st.form("form_informe_eval_ia"):
                        prompt_eval_input = st.text_area(
                            "💬 Prompt de Evaluación Profesional:",
                            value=prompt_defecto_eval,
                            height=100
                        )
                        
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            modelos_actuales = obtener_modelos_ia_disponibles()
                            modelo_ia_eval = st.selectbox(
                                "🤖 Seleccionar versión de IA a utilizar:",
                                options=modelos_actuales,
                                index=0
                            )
                        with col_m2:
                            st.write("")
                            st.write("")
                            btn_generar_eval = st.form_submit_button("🚀 Generar Informe de Evaluación", use_container_width=True)

                    if btn_generar_eval:
                        with st.spinner("Procesando histórico de exámenes y generando evaluación IA..."):
                            try:
                                resumen_historico = f"HISTORIAL COMPLETO DE EXÁMENES DE {emp_seleccionado_nombre.upper()}:\n"
                                for _, row in df_emp_tot.iterrows():
                                    resumen_historico += f"- Fecha: {str(row['fecha_inicio'])[:10]} | Examen: {row['apartado']} | Nota: {row['nota']}/10 | Aciertos: {row['porcentaje_obtenido']}%\n"
                                
                                prompt_completo_eval = f"{prompt_eval_input}\n\n[DATOS DEL TRABAJADOR]:\n{resumen_historico}"
                                
                                res_analisis_final = consultar_ia(modelo_ia_eval, prompt_completo_eval)
                                st.session_state.eval_resultado_cache = res_analisis_final

                                emp_id_final = None
                                emp_busq = [e["id"] for e in emp_list_select if e["nombre"].strip().lower() == emp_seleccionado_nombre.strip().lower()]
                                if emp_busq:
                                    emp_id_final = emp_busq[0]

                                if emp_id_final:
                                    supabase.table("analisis_ia_empleados").insert({
                                        "empleado_id": emp_id_final,
                                        "anio": anio_metrica_sel,
                                        "analisis_texto": res_analisis_final
                                    }).execute()

                            except Exception as e_ia:
                                st.session_state.eval_resultado_cache = f"Error al generar informe: {e_ia}"

                    st.markdown("#### 📝 Resultado de la Evaluación IA:")
                    if st.session_state.eval_resultado_cache:
                        st.info(st.session_state.eval_resultado_cache)
                        
                        pdf_bytes_eval = generar_pdf_evaluacion_ia(
                            emp_seleccionado_nombre, 
                            st.session_state.eval_resultado_cache, 
                            anio_metrica_sel
                        )
                        if pdf_bytes_eval:
                            st.download_button(
                                label="📄 Exportar Informe Profesional IA en PDF",
                                data=pdf_bytes_eval,
                                file_name=f"Informe_Evaluacion_IA_{emp_seleccionado_nombre.replace(' ', '_')}_{anio_metrica_sel}.pdf",
                                mime="application/pdf",
                                key="btn_download_eval_pdf"
                            )
                    else:
                        st.caption("🔒 El apartado de evaluación se encuentra desactivado hasta que pulses en 'Generar Informe de Evaluación'.")

        # ADMIN CROMA - CONSULTAS LIBRES
        if st.session_state.es_croma and tab_admin_claude:
            with tab_admin_claude:
                st.subheader("🤖 Consola de Consultas y Análisis Libre con Gemini / Claude")
                st.caption("Escribe un prompt para realizar consultas, análisis avanzados o interactuar con los modelos guardando los resultados en la base de datos.")

                tab_sub_nueva, tab_sub_historial = st.tabs(["💬 Nueva Consulta", "🗄️ Historial y Gestión de Consultas (BD)"])

                with tab_sub_nueva:
                    col_cl1, col_cl2 = st.columns([3, 1])
                    with col_cl1:
                        modelos_actuales = obtener_modelos_ia_disponibles()
                        modelo_ia_eval = st.selectbox(
                            "🤖 Seleccionar versión de IA a utilizar:",
                            options=modelos_actuales,
                            index=0,
                            key="sel_mod_libre"
                        )

                    with col_cl2:
                        incluir_datos_sql = st.checkbox("Inyectar contexto actual de la BD (Exámenes/Empleados)", value=True)

                    prompt_consulta_libre = st.text_area(
                        "💬 Prompt de Consulta o Análisis personalizado:",
                        height=180,
                        placeholder="Ejemplo: Realiza un resumen comparativo del rendimiento del personal en el último trimestre y da 3 recomendaciones tácticas.",
                        key="prompt_consulta_libre_text"
                    )

                    if st.button("🚀 Ejecutar Consulta y Guardar en BD", use_container_width=True):
                        if not prompt_consulta_libre.strip():
                            st.warning("⚠️ Introduce un prompt antes de ejecutar la consulta.")
                        else:
                            contexto_adicional = ""
                            if incluir_datos_sql:
                                try:
                                    res_e = supabase.table("empleados").select("nombre, activo").execute()
                                    res_i = supabase.table("intentos_examen").select("nombre_empleado, apartado, nota, porcentaje_obtenido, fecha_inicio").order("id", desc=True).limit(50).execute()
                                    contexto_adicional = f"\n\n[CONTEXTO BASE DE DATOS]:\nEmpleados: {json.dumps(res_e.data or [])}\nÚltimos 50 intentos: {json.dumps(res_i.data or [])}"
                                except Exception as ex_ctx:
                                    contexto_adicional = f"\n\n[Error extrayendo contexto SQL: {ex_ctx}]"

                            with st.spinner("Procesando consulta con el modelo seleccionado..."):
                                try:
                                    respuesta_ia = consultar_ia(
                                        modelo=modelo_ia_eval,
                                        prompt=prompt_consulta_libre + contexto_adicional,
                                        sistema="Eres un analista de datos Senior y consultor experto para la plataforma."
                                    )
                                    
                                    registro_consulta = {
                                        "usuario": st.session_state.user_nombre,
                                        "modelo": modelo_ia_eval,
                                        "prompt": prompt_consulta_libre,
                                        "respuesta": respuesta_ia,
                                        "fecha": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                                    }
                                    supabase.table("consultas_ia").insert(registro_consulta).execute()

                                    st.markdown("### 📋 Respuesta / Resultado del Análisis")
                                    st.markdown(respuesta_ia)
                                    st.success("✅ Consulta registrada en la base de datos correctamente.")
                                except Exception as err_c:
                                    st.error(f"❌ Error al procesar la consulta: {err_c}")

                with tab_sub_historial:
                    st.subheader("🛠️ Registros de Consultas de Gemini / Claude")
                    try:
                        res_consultas = supabase.table("consultas_ia").select("*").order("fecha", desc=True).execute()
                        consultas_lista = res_consultas.data if res_consultas.data else []
                    except Exception as err_hist:
                        consultas_lista = []
                        st.error(f"Error al obtener el historial de consultas de la BD: {err_hist}")

                    if consultas_lista:
                        modelos_presentes = list(set([c.get("modelo", "Desconocido") for c in consultas_lista]))
                        
                        col_f1, _ = st.columns(2)
                        with col_f1:
                            filtro_modelo = st.selectbox("Filtrar por modelo de IA:", ["Todos"] + modelos_presentes, key="filt_mod_consultas")
                        
                        consultas_filtradas = consultas_lista
                        if filtro_modelo != "Todos":
                            consultas_filtradas = [c for c in consultas_lista if c.get("modelo") == filtro_modelo]

                        st.write(f"Mostrando **{len(consultas_filtradas)}** consultas registradas:")

                        for cons in consultas_filtradas:
                            cid = cons["id"]
                            c_fecha = cons.get("fecha", "")[:19].replace("T", " ")
                            c_usr = cons.get("usuario", "Anonimo")
                            c_mod = cons.get("modelo", "General")
                            c_prompt = cons.get("prompt", "")
                            c_resp = cons.get("respuesta", "")

                            with st.expander(f"📌 #{cid} | {c_mod} | {c_usr} | {c_fecha}"):
                                with st.form(key=f"form_cons_edit_{cid}"):
                                    st.markdown(f"**Usuario:** {c_usr} | **Modelo:** {c_mod}")
                                    p_edit = st.text_area("Prompt enviado:", value=c_prompt, height=100, key=f"p_e_{cid}")
                                    r_edit = st.text_area("Respuesta del modelo:", value=c_resp, height=200, key=f"r_e_{cid}")

                                    col_eb1, col_eb2 = st.columns(2)
                                    with col_eb1:
                                        btn_mod_cons = st.form_submit_button("✏️ Guardar Modificación", use_container_width=True)
                                    with col_eb2:
                                        btn_del_cons = st.form_submit_button("🗑️ Eliminar Registro", use_container_width=True)

                                    if btn_mod_cons:
                                        try:
                                            supabase.table("consultas_ia").update({
                                                "prompt": p_edit,
                                                "respuesta": r_edit
                                            }).eq("id", cid).execute()
                                            st.success("✅ Consulta actualizada correctamente.")
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as err_upd:
                                            st.error(f"❌ Error actualizando la consulta: {err_upd}")

                                    if btn_del_cons:
                                        try:
                                            supabase.table("consultas_ia").delete().eq("id", cid).execute()
                                            st.success("🗑️ Registro eliminado de la base de datos.")
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as err_del:
                                            st.error(f"❌ Error eliminando la consulta: {err_del}")
                    else:
                        st.info("No hay consultas de IA registradas en la base de datos.")

        # ADMIN CROMA - GESTIÓN Y CONFIGURACIÓN
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Configuración Global de Parámetros de Examen (Base de Datos)")
                st.caption("Solo los administradores registrados pueden modificar estos valores. Se sincronizan directamente en la base de datos Supabase.")
                
                tiempo_actual_db = obtener_tiempo_pregunta_config()
                num_p_global_actual = obtener_num_preguntas_config("global")
                num_p_manual_actual = obtener_num_preguntas_config("manual")

                with st.form("form_config_examenes"):
                    st.markdown("##### ⏱️ Configuración del Tiempo por Pregunta")
                    nuevo_tiempo_inp = st.number_input(
                        "Tiempo asignado por pregunta (segundos):",
                        min_value=5,
                        max_value=300,
                        value=tiempo_actual_db,
                        step=5,
                        help="Tiempo por defecto para responder cada pregunta."
                    )
                    
                    st.markdown("---")
                    st.markdown("##### 🔢 Cantidad de Preguntas por Modalidad")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        nuevo_num_global = st.number_input(
                            "Número de preguntas para Examen Global:",
                            min_value=1,
                            max_value=100,
                            value=num_p_global_actual,
                            step=1
                        )
                    with col_p2:
                        nuevo_num_manual = st.number_input(
                            "Número de preguntas para Examen por Manual:",
                            min_value=1,
                            max_value=100,
                            value=num_p_manual_actual,
                            step=1
                        )

                    btn_save_config = st.form_submit_button("💾 Guardar Configuración de Exámenes")
                    
                    if btn_save_config:
                        ok_tiempo = guardar_tiempo_pregunta_config(nuevo_tiempo_inp)
                        ok_global = guardar_num_preguntas_config("global", nuevo_num_global)
                        ok_manual = guardar_num_preguntas_config("manual", nuevo_num_manual)
                        
                        if ok_tiempo and ok_global and ok_manual:
                            st.success("✅ Configuración de exámenes actualizada correctamente en la base de datos.")
                            time.sleep(1)
                            st.rerun()

                st.markdown("---")
                st.subheader("⚙️ Gestión de Empleados (Crear / Editar)")
                
                tab_emp_crear, tab_emp_editar = st.tabs(["➕ Crear Empleado", "✏️ Editar Empleado Existente"])
                
                with tab_emp_crear:
                    with st.form("form_crear_empleado"):
                        st.markdown("##### 👤 Nuevo Empleado")
                        nuevo_nombre = st.text_input("Nombre de Empleado (campo: nombre):*")
                        nuevo_pass = st.text_input("Clave de Acceso (campo: password_hash):*", type="password")
                        es_admin_croma_val = st.checkbox("Nivel Administrador (campo: es_admin_croma)", value=False)
                        activo_val = st.checkbox("Activo (campo: activo)", value=True)
                        
                        btn_crear_emp = st.form_submit_button("💾 Guardar Nuevo Empleado")
                        
                        if btn_crear_emp:
                            if not nuevo_nombre.strip() or not nuevo_pass.strip():
                                st.error("❌ El nombre y la clave de acceso son obligatorios.")
                            else:
                                try:
                                    supabase.table("empleados").insert({
                                        "nombre": nuevo_nombre.strip(),
                                        "password_hash": nuevo_pass.strip(),
                                        "es_admin_croma": es_admin_croma_val,
                                        "activo": activo_val
                                    }).execute()
                                    st.success(f"✅ Empleado '{nuevo_nombre.strip()}' creado correctamente.")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as err_e_c:
                                    st.error(f"❌ Error al crear el empleado: {err_e_c}")

                with tab_emp_editar:
                    try:
                        res_emp_todos_e = supabase.table("empleados").select("*").order("nombre").execute()
                        todos_emp_edit = res_emp_todos_e.data if res_emp_todos_e.data else []
                    except Exception:
                        todos_emp_edit = []

                    if todos_emp_edit:
                        map_emp_edit = {f"{e['nombre']} (ID: {e['id']})": e for e in todos_emp_edit}
                        emp_sel_nom_edit = st.selectbox("Selecciona un empleado para editar:", list(map_emp_edit.keys()))
                        emp_obj_edit = map_emp_edit[emp_sel_nom_edit]

                        with st.form(key=f"form_edit_emp_{emp_obj_edit['id']}"):
                            st.markdown(f"##### ✏️ Modificar datos de {emp_obj_edit['nombre']}")
                            edit_nombre = st.text_input("Nombre de Empleado:", value=emp_obj_edit.get("nombre", ""))
                            edit_pass = st.text_input("Clave de Acceso:", value=emp_obj_edit.get("password_hash", ""), type="password")
                            edit_es_admin = st.checkbox("Nivel Administrador", value=emp_obj_edit.get("es_admin_croma", False))
                            edit_activo = st.checkbox("Activo", value=emp_obj_edit.get("activo", True))

                            btn_update_emp = st.form_submit_button("💾 Actualizar Datos del Empleado")

                            if btn_update_emp:
                                if not edit_nombre.strip() or not edit_pass.strip():
                                    st.error("❌ El nombre y la clave de acceso son obligatorios.")
                                else:
                                    try:
                                        supabase.table("empleados").update({
                                            "nombre": edit_nombre.strip(),
                                            "password_hash": edit_pass.strip(),
                                            "es_admin_croma": edit_es_admin,
                                            "activo": edit_activo
                                        }).eq("id", emp_obj_edit["id"]).execute()
                                        st.success("✅ Datos del empleado actualizados correctamente.")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as err_e_u:
                                        st.error(f"❌ Error actualizando empleado: {err_e_u}")
                    else:
                        st.info("No se encontraron empleados en la base de datos.")

                st.markdown("---")
                st.subheader("⚙️ Configuración de IA y Modelos (SQL config_prompts)")
                st.caption("Administra la plantilla por defecto y los modelos predeterminados de Gemini y Claude.")

                config_prompt_actual = None
                try:
                    res_cfg_db = supabase.table("config_prompts").select("*").eq("nombre", "evaluacion_empleado").limit(1).execute()
                    if res_cfg_db.data:
                        config_prompt_actual = res_cfg_db.data[0]
                except Exception:
                    config_prompt_actual = None

                cfg_prompt_examen = None
                try:
                    res_cfg_ex = supabase.table("config_prompts").select("*").eq("nombre", "prompt_examen").limit(1).execute()
                    if res_cfg_ex.data:
                        cfg_prompt_examen = res_cfg_ex.data[0]
                except Exception:
                    cfg_prompt_examen = None

                p_def_val = config_prompt_actual.get("prompt_texto") if config_prompt_actual else "Analiza a este trabajador y da tu opinión como profesional de su evolución en los exámenes realizados, este año, y años anteriores."
                p_def_ex_val = cfg_prompt_examen.get("prompt_texto") if cfg_prompt_examen else PROMPT_DEFECTO_EXAMEN

                listado_modelos = obtener_modelos_ia_disponibles()

                with st.expander("🛠️ Editar Lista Global de Modelos de IA"):
                    st.write("Agrega o edita las versiones de los modelos registradas en la base de datos (separadas por comas):")
                    nuevos_modelos_str = st.text_area("Modelos disponibles:", value=", ".join(listado_modelos))
                    if st.button("💾 Actualizar Lista de Modelos IA"):
                        lista_nuevos = [m.strip() for m in nuevos_modelos_str.split(",") if m.strip()]
                        g_str = ",".join([m for m in lista_nuevos if "gemini" in m.lower()])
                        c_str = ",".join([m for m in lista_nuevos if "claude" in m.lower()])
                        try:
                            res_c1 = supabase.table("config_prompts").select("id").eq("nombre", "evaluacion_empleado").execute()
                            if res_c1.data:
                                supabase.table("config_prompts").update({
                                    "modelo_gemini": g_str if g_str else "gemini-2.5-pro",
                                    "modelo_claude": c_str if c_str else "claude-3-5-sonnet-20241022"
                                }).eq("nombre", "evaluacion_empleado").execute()
                            else:
                                supabase.table("config_prompts").insert({
                                    "nombre": "evaluacion_empleado",
                                    "prompt_texto": p_def_val,
                                    "modelo_gemini": g_str if g_str else "gemini-2.5-pro",
                                    "modelo_claude": c_str if c_str else "claude-3-5-sonnet-20241022"
                                }).execute()

                            st.success("✅ Lista de modelos actualizada correctamente.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_mod:
                            st.error(f"Error actualizando lista de modelos: {e_mod}")

                with st.form("form_config_ia_prompts"):
                    prompt_eval_config = st.text_area("Prompt por defecto para Evaluación de Empleados:", value=p_def_val, height=100)
                    prompt_exam_config = st.text_area("Prompt por defecto para Generación de Exámenes:", value=p_def_ex_val, height=150)
                    
                    btn_save_cfg_prompts = st.form_submit_button("💾 Guardar Configuración de Prompts")
                    if btn_save_cfg_prompts:
                        try:
                            res_ev = supabase.table("config_prompts").select("id").eq("nombre", "evaluacion_empleado").execute()
                            if res_ev.data:
                                supabase.table("config_prompts").update({"prompt_texto": prompt_eval_config}).eq("nombre", "evaluacion_empleado").execute()
                            else:
                                supabase.table("config_prompts").insert({"nombre": "evaluacion_empleado", "prompt_texto": prompt_eval_config}).execute()

                            res_ex = supabase.table("config_prompts").select("id").eq("nombre", "prompt_examen").execute()
                            if res_ex.data:
                                supabase.table("config_prompts").update({"prompt_texto": prompt_exam_config}).eq("nombre", "prompt_examen").execute()
                            else:
                                supabase.table("config_prompts").insert({"nombre": "prompt_examen", "prompt_texto": prompt_exam_config}).execute()

                            st.success("✅ Prompts por defecto actualizados.")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e_pr:
                            st.error(f"Error al guardar prompts: {e_pr}")
