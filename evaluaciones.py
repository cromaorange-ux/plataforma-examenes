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
        --primary-color: #8094B0;
        --secondary-color: #327DCD;
        --background-color: #fff7ef;
        --card-bg: #FFFFFF;
        --text-color: #B2C0D7;
        --border-radius: 12px;
    }

    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background-color: #fff7ef !important;
        color: ##B2C0D7 !important; 
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        background-color: #fff7ef;
        color: ##B2C0D7 !important;
    }
    .stMarkdown, .stText, p, label, h1, h2, h3, h4, h5, h6,
    [data-testid="stCaptionContainer"], [data-testid="stMarkdownContainer"] {
        color: #2B1800;
    }
    [data-testid="stExpander"], [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff;
        border-color: #e7d9ca;
    }
    input, textarea, [data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #B2C0D7 !important;
    }

    /* ESTILOS DE RADIO BUTTON PARA OPCIONES EN BLANCO */
    .stRadio label {
        font-size: 16px !important;
        font-weight: 600 !important;
        line-height: 1.4 !important;
        color: #B2C0D7 !important;
    }
    
    .stRadio div[role='radiogroup'] {
        gap: 10px;
    }

    .stRadio div[role='radiogroup'] > label {
        background-color: #ffffff !important;
        padding: 14px 18px !important;
        border-radius: 8px !important;
        border: 2px solid #4A5568 !important;
        transition: all 0.2s ease-in-out;
        width: 100%;
        margin-bottom: 8px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }

    .stRadio div[role='radiogroup'] > label p {
        color: #B2C0D7 !important;
        font-weight: 600 !important;
    }

    .stRadio div[role='radiogroup'] > label:hover {
        background-color: #fff0e2 !important;
        border-color: #3182CE !important;
    }

    .pregunta-titulo {
        font-size: 22px !important;
        font-weight: 700 !important;
        color: #141b26;
        margin-bottom: 20px;
        line-height: 1.3;
        padding: 18px;
        background-color: #ffffff;
        border-left: 6px solid #e87916;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.2);
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
        background-color: #B2C0D7 !important;
        border: 1px solid #768EB7;
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

    .manual-card {
        background-color: #B2C0D7 !important;
        border: 1px solid #E2E8F0;
        border-top: 5px solid #2B6CB0;
        border-radius: var(--border-radius);
        padding: 20px;
        text-align: left;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        margin-bottom: 15px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }

    .manual-card h4 {
        color: #1A365D !important;
        font-weight: 700 !important;
        font-size: 18px !important;
        margin-bottom: 8px !important;
    }

    .manual-card p {
        color: #4A5568 !important;
        font-size: 13px !important;
        margin-bottom: 12px !important;
    }

    .stButton > button {
        background-color: #e87916 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
        border: none !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: background-color 0.2s ease !important;
    }

    .stButton > button:hover {
        background-color: #c65f0b !important;
    }

    /* Diálogos, ventanas emergentes y opciones: paleta clara */
    [data-testid="stDialog"], [role="dialog"], [data-baseweb="modal"] > div,
    [data-testid="stPopover"], [data-baseweb="popover"] {
        background-color: #ffffff !important;
        color: #B2C0D7 !important;
        border-color: #ead9c8 !important;
    }
    [role="dialog"] *, [data-baseweb="popover"] *, [data-testid="stDialog"] * {
        color: #000000 !important;
    }
    .stRadio div[role='radiogroup'] > label {
        background-color: #fffaf5 !important;
        border: 1px solid #e8d7c5 !important;
        color: #B2C0D7 !important;
        box-shadow: 0 1px 2px rgba(80, 45, 15, 0.06) !important;
    }
    .stRadio div[role='radiogroup'] > label:hover {
        background-color: #fff0df !important;
        border-color: #efbd8c !important;
    }
    [role="dialog"] .stButton > button, [data-testid="stDialog"] .stButton > button {
        background-color: #ffe8d2 !important;
        color: #FFFFFF !important;
        border: 1px solid #f0c9a4 !important;
    }
    [role="dialog"] .stButton > button:hover, [data-testid="stDialog"] .stButton > button:hover {
        background-color: #ffdab8 !important;
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
        res = supabase.table("config_tiempos_preguntas").select("tiempos_segundos").order("id", desc=True).limit(1).execute()
        if res.data and res.data[0].get("tiempos_segundos") is not None:
            return int(res.data[0]["tiempos_segundos"])
    except Exception:
        pass
    return 45

def obtener_num_preguntas_config(tipo):
    """Lee el número de preguntas desde las columnas de configuración vigentes."""
    columna = "num_preguntas_global" if tipo == "global" else "num_preguntas_manual"
    try:
        res = supabase.table("config_prompts").select(columna).order("id", desc=True).limit(1).execute()
        if res.data and res.data[0].get(columna) is not None:
            return int(res.data[0][columna])
    except Exception:
        pass
    # Compatibilidad con instalaciones antiguas que guardaban el parámetro en nombre/valor.
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        res = supabase.table("config_prompts").select("valor").eq("nombre", clave_nombre).order("id", desc=True).limit(1).execute()
        if res.data and res.data[0].get("valor") is not None:
            return int(res.data[0]["valor"])
    except Exception:
        pass
    return 15 if tipo == "global" else 10

def guardar_tiempo_pregunta_config(nuevo_tiempo):
    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        res = supabase.table("config_tiempos_preguntas").select("id").order("id", desc=True).limit(1).execute()
        if res.data:
            supabase.table("config_tiempos_preguntas").update({
                "tiempos_segundos": int(nuevo_tiempo),
                "updated_at": now_iso
            }).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("config_tiempos_preguntas").insert({
                "tiempos_segundos": int(nuevo_tiempo),
                "updated_at": now_iso
            }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar tiempo por pregunta: {e}")
        return False

def guardar_num_preguntas_config(tipo, cantidad):
    columna = "num_preguntas_global" if tipo == "global" else "num_preguntas_manual"
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        # Esquema vigente: número de preguntas almacenado en columnas de config_prompts.
        res = supabase.table("config_prompts").select("id").order("id", desc=True).limit(1).execute()
        if res.data:
            supabase.table("config_prompts").update({columna: int(cantidad)}).eq("id", res.data[0]["id"]).execute()
            return True
    except Exception:
        # Compatibilidad con instalaciones antiguas que aún usan nombre/valor.
        pass
    try:
        res = supabase.table("config_prompts").select("id").eq("nombre", clave_nombre).order("id", desc=True).limit(1).execute()
        if res.data:
            supabase.table("config_prompts").update({"valor": str(cantidad)}).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("config_prompts").insert({"nombre": clave_nombre, "valor": str(cantidad)}).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar número de preguntas ({tipo}) en config_prompts.{columna}: {e}")
        return False

def obtener_modelos_ia_disponibles():
    try:
        res = supabase.table("config_prompts").select("modelo_gemini, modelo_claude, modelo_openai").execute()
        if res.data:
            modelos_sql = []
            for fila in res.data:
                for col in ["modelo_gemini", "modelo_claude", "modelo_openai"]:
                    if fila.get(col):
                        modelos_sql.extend([m.strip() for m in fila[col].split(",") if m.strip()])
            
            modelos_unicos = list(dict.fromkeys(modelos_sql))
            if modelos_unicos:
                return modelos_unicos
    except Exception as err:
        st.warning(f"No se pudieron cargar los modelos desde la base de datos: {err}")
    
    return ["gemini-2.5-pro", "gemini-2.5-flash", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]

def guardar_prompt_config(nombre_prompt, nuevo_valor):
    try:
        res = supabase.table("config_prompts").select("id").eq("nombre", nombre_prompt).execute()
        if res.data:
            supabase.table("config_prompts").update({"valor": nuevo_valor}).eq("nombre", nombre_prompt).execute()
        else:
            supabase.table("config_prompts").insert({"nombre": nombre_prompt, "valor": nuevo_valor}).execute()
        return True
    except Exception as e:
        st.error(f"Error al actualizar el prompt '{nombre_prompt}': {e}")
        return False

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
if "intento_id_actual" not in st.session_state:
    st.session_state.intento_id_actual = None
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
if "mostrar_analisis_ia_exp" not in st.session_state:
    st.session_state.mostrar_analisis_ia_exp = False

TIEMPO_LIMITE_PREGUNTA = obtener_tiempo_pregunta_config()
UMBRAL_APROBADO_PORCENTAJE = 70.0
NUM_PREG_GLOBAL = obtener_num_preguntas_config("global")
NUM_PREG_MANUAL = obtener_num_preguntas_config("manual")

PROMPT_DEFECTO = """Genera un banco de EXACTAMENTE 50 preguntas tipo test por cada temática/sección basadas en el documento. 

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

PROMPT_DEFECTO_EXAMEN = f"""Genera un banco de EXACTAMENTE 50 preguntas tipo test por cada temática detectada en el documento.
Para cada pregunta, asigna por defecto el nivel de dificultad "dificil" y establece el campo "tipo" como "examen".
Cada pregunta debe incluir la propiedad "tiempo_segundos": {TIEMPO_LIMITE_PREGUNTA}.

Responde ÚNICAMENTE con un array JSON estructurado exactamente de la siguiente forma (sin envoltorios markdown extraños fuera del json):
[
  {{
    "pregunta": "Texto detallado de la pregunta",
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

TEXTO_EXAMEN_GLOBAL_INFO = f"""En el examen global, se incluirán exactamente {NUM_PREG_GLOBAL} preguntas distribuidas equitativamente entre las distintas temáticas. Se aplicará un tiempo máximo por pregunta de {TIEMPO_LIMITE_PREGUNTA} segundos."""

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
    cupo_por_tema = max(1, num_preguntas // num_temas) if num_temas > 0 else 1

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


# =========================================================
# MÓDULO INTEGRADO: EVALUACIONES TRIMESTRALES
# Adaptado de streamlit_app (5).py para funcionar dentro de app.py.
# =========================================================
try:
    import openpyxl
except ImportError:
    openpyxl = None
import base64

QT_APARTADOS_DEFECTO = [
    "Tareas realizar por turnos y todos los turnos",
    "Tiempos respuesta Tbox",
    "Tiempos respuesta Siemens",
    "Iniciativa / Proactividad ante el trabajo",
    "Conocimientos",
    "Evaluacion",
]
QT_SUBAPARTADOS_DEFECTO = {
    "Tareas realizar por turnos y todos los turnos": [
        "Turno mañana", "Turno Fin de semana Mañana", "Turno Tarde",
        "Turno Noche", "Turno Fin de semana Noche", "Todos los turnos"
    ],
    "Tiempos respuesta Tbox": [
        "% menos de 1 %", "tiempo mas de 20 minutos",
        "Numero alarmas mas de 15 minutos (inferior a 10)"
    ],
    "Tiempos respuesta Siemens": [
        "% menos de 1 %", "tiempo mas de 20 minutos",
        "Numero alarmas mas de 15 minutos (inferior a 10)"
    ],
    "Iniciativa / Proactividad ante el trabajo": [
        "Sugerencia de ideas / Mejoras / Realización de tabajos sin indicar nada"
    ],
    "Conocimientos": ["Conocimientos aplicados en puesto trabajo"],
    "Evaluacion": ["Teorica (ANUAL)", "Practica (ANUAL)", "Herramienta (ANUAL)", "Dejar operativo portatil desde 0"],
}
QT_MAX_PUNTUACION_APARTADO = {
    "Tareas realizar por turnos y todos los turnos": 3.0,
    "Tiempos respuesta Tbox": 3.0,
    "Tiempos respuesta Siemens": 3.0,
    "Iniciativa / Proactividad ante el trabajo": 3.0,
    "Conocimientos": 1.0,
    "Evaluacion": 1.0,
}

def qt_norm(v):
    return str(v).strip().lower().replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u").replace("ñ","n")

def qt_sub_clave(apartado, subapartado):
    return f"{apartado}::{subapartado}"

def qt_sub_oculto(ocultos, apartado, subapartado):
    return subapartado in set(ocultos or []) or qt_sub_clave(apartado, subapartado) in set(ocultos or [])

def qt_obtener_visibilidad(empleado_id, anio):
    defecto={"qs_habilitados": {f"Q{i}": True for i in range(1,5)}, "apartados_habilitados": {x: True for x in QT_APARTADOS_DEFECTO}, "subapartados_deshabilitados": []}
    try:
        r=supabase.table("visibilidad_empleados").select("*").eq("empleado_id",empleado_id).eq("anio",int(anio)).limit(1).execute()
        return r.data[0] if r.data else defecto
    except Exception:
        return defecto

def qt_guardar_visibilidad(empleado_id, anio, qs, apartados, sub):
    supabase.table("visibilidad_empleados").upsert({"empleado_id":empleado_id,"anio":int(anio),"qs_habilitados":qs,"apartados_habilitados":apartados,"subapartados_deshabilitados":sub}, on_conflict="empleado_id,anio").execute()

def qt_obtener_pesos():
    """Obtiene los pesos base desde la estructura SQL existente."""
    pesos = {}
    try:
        r = supabase.table("config_apartados_pesos").select("apartado,peso_porcentaje,habilitado").execute()
        for x in (r.data or []):
            if x.get("apartado"):
                pesos[str(x["apartado"])] = float(x.get("peso_porcentaje") or 0)
        if pesos:
            return pesos
    except Exception:
        pass
    try:
        r = supabase.table("config_pesos_apartados").select("seccion,peso_porcentaje,habilitado").execute()
        for x in (r.data or []):
            if x.get("seccion"):
                pesos[str(x["seccion"])] = float(x.get("peso_porcentaje") or 0)
    except Exception:
        pass
    return pesos

def qt_pesos_recalculados(pesos_base, apartados_habilitados, subapartados_por_apartado=None, subapartados_deshabilitados=None):
    """
    Recalcula los pesos para que SIEMPRE sumen 100% para la configuración
    visible de cada empleado.

    - Si se deshabilita un apartado, su peso se redistribuye proporcionalmente
      entre los apartados activos.
    - Si se deshabilita un subapartado, el peso total del apartado no desaparece;
      se reparte proporcionalmente entre sus subapartados activos.
    - Nunca modifica los pesos base de SQL: son pesos globales y la visibilidad
      es específica de empleado/año.
    """
    subapartados_por_apartado = subapartados_por_apartado or {}
    subapartados_deshabilitados = set(subapartados_deshabilitados or [])

    if not pesos_base:
        return {}, {}, 0.0

    # Apartados activos. Si un apartado no aparece en la configuración de
    # visibilidad, se considera activo por compatibilidad con datos antiguos.
    activos = [
        ap for ap, peso in pesos_base.items()
        if float(peso or 0) > 0 and apartados_habilitados.get(ap, True)
    ]

    suma_activos = sum(float(pesos_base.get(ap, 0) or 0) for ap in activos)
    pesos_apartados = {}
    if suma_activos > 0:
        factor = 100.0 / suma_activos
        for ap in pesos_base:
            if ap in activos:
                pesos_apartados[ap] = float(pesos_base[ap] or 0) * factor
            else:
                pesos_apartados[ap] = 0.0

    # Peso de cada subapartado dentro de su apartado.
    pesos_subapartados = {}
    for ap, peso_ap in pesos_apartados.items():
        subs = list(subapartados_por_apartado.get(ap, []) or [])
        if not subs:
            continue
        subs_activos = [s for s in subs if not qt_sub_oculto(subapartados_deshabilitados, ap, s) and apartados_habilitados.get(ap, True)]
        if subs_activos:
            peso_sub = peso_ap / len(subs_activos)
            pesos_subapartados[ap] = {s: (peso_sub if s in subs_activos else 0.0) for s in subs}
        else:
            pesos_subapartados[ap] = {s: 0.0 for s in subs}

    return pesos_apartados, pesos_subapartados, sum(pesos_apartados.values())

def qt_estructura(emp_id, anio):
    estructura={}
    try:
        ev=supabase.table("evaluaciones_trimestrales").select("id").eq("empleado_id",emp_id).eq("anio",int(anio)).execute().data or []
        ids=[x["id"] for x in ev]
        if ids:
            det=supabase.table("evaluacion_detalles").select("apartado,subapartado").in_("evaluacion_id",ids).execute().data or []
            for d in det:
                a=d.get("apartado") or d.get("seccion") or "Evaluacion"
                estructura.setdefault(a,set())
                if d.get("subapartado"): estructura[a].add(d["subapartado"])
    except Exception: pass
    if not estructura: estructura={k:set(v) for k,v in QT_SUBAPARTADOS_DEFECTO.items()}
    return {k:sorted(v) for k,v in estructura.items()}

def qt_max_puntuacion(apartado, subapartado=None):
    """Máxima puntuación real según el apartado/subapartado de la plantilla."""
    return float(QT_MAX_PUNTUACION_APARTADO.get(apartado, 5.0))


def qt_cargar_excel(uploaded_file, anio_defecto, creado_por):
    """Importa la plantilla real de evaluaciones trimestrales.

    Formato soportado:
      - Hojas Q1, Q2, Q3 y Q4.
      - Empleado en A8 y año en A10.
      - Cabecera de evaluación en la fila 12.
      - Apartados en columna A y criterios en las filas siguientes.
      - Puntuación en columna C y observaciones en columna D.
      - Observaciones generales en la fila 44.
      - La hoja Resumen se ignora.

    Se abre el libro dos veces: data_only=True permite obtener el valor
    calculado de fórmulas como ='Q2'!A8, en lugar del texto de la fórmula.
    """
    if openpyxl is None:
        raise RuntimeError("Falta openpyxl en requirements.txt")

    raw = uploaded_file.getvalue()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as e:
        raise RuntimeError(f"No se pudo abrir el Excel: {e}")

    hojas_validas = [ws for ws in wb.worksheets if str(ws.title).strip().upper() in {"Q1", "Q2", "Q3", "Q4"}]
    if not hojas_validas:
        raise ValueError("El Excel debe contener al menos una hoja Q1, Q2, Q3 o Q4.")

    # Apartados que existen en la plantilla entregada. También se acepta
    # cualquier apartado nuevo si aparece en columna A de una fila de criterio.
    apartados_conocidos = {
        "Tareas realizar por turnos y todos los turnos",
        "Tiempos respuesta Tbox",
        "Tiempos respuesta Siemens",
        "Iniciativa / Proactividad ante el trabajo",
        "Conocimientos",
        "Evaluacion",
    }

    def celda_texto(ws, fila, columna):
        valor = ws.cell(fila, columna).value
        if valor is None:
            return ""
        return str(valor).strip()

    def numero_puntuacion(valor):
        if valor is None or isinstance(valor, bool):
            return None
        try:
            if isinstance(valor, str):
                texto = valor.strip().replace(",", ".")
                if not texto:
                    return None
                # Fórmulas de Excel ya no llegan aquí como fórmula porque
                # el libro se abrió con data_only=True.
                return float(texto)
            return float(valor)
        except Exception:
            return None

    # Empleados existentes en SQL.
    empleados = supabase.table("empleados").select("id,nombre,activo").execute().data or []
    by_id = {str(x["id"]): x for x in empleados}
    by_name = {qt_norm(x.get("nombre")): x for x in empleados if x.get("nombre")}

    grupos = {}
    hojas_importadas = []

    for ws in hojas_validas:
        trimestre = str(ws.title).strip().upper()

        # En esta plantilla las fórmulas de Q1/Q3/Q4 apuntan a Q2. Al usar
        # data_only=True openpyxl nos entrega directamente "Carlos Perez" y 2025.
        nombre_excel = celda_texto(ws, 8, 1)
        anio_excel = ws.cell(10, 1).value
        evaluador = celda_texto(ws, 10, 2)
        fecha_evaluacion = ws.cell(8, 2).value

        nombre_normalizado = qt_norm(nombre_excel)
        emp = by_name.get(nombre_normalizado) if nombre_normalizado else None

        if emp is None:
            raise ValueError(
                f"Empleado no encontrado en SQL para la hoja {trimestre}: '{nombre_excel}'. "
                "Comprueba que el nombre de la hoja coincide con empleados.nombre."
            )

        try:
            anio = int(float(anio_excel)) if anio_excel is not None else int(anio_defecto)
        except Exception:
            anio = int(anio_defecto)

        detalles = []
        apartado_actual = None

        # La plantilla empieza la evaluación en la fila 14.
        for fila in range(14, ws.max_row + 1):
            nombre_a = celda_texto(ws, fila, 1)
            valor_c = ws.cell(fila, 3).value
            observacion = ws.cell(fila, 4).value

            # Filas de cálculo: C21, C26, C31, C34, C37, C43, C45, etc.
            # No son criterios individuales y nunca se insertan como detalle.
            if not nombre_a:
                continue

            # Observaciones generales de la plantilla.
            if nombre_a.lower() == "observaciones generales:":
                continue

            # Si la fila es uno de los apartados, cambia el contexto.
            if nombre_a in apartados_conocidos:
                apartado_actual = nombre_a
                continue

            # También detectamos un apartado nuevo cuando C contiene el texto
            # "Peso total (...)". Esto evita depender únicamente de la lista.
            c_texto = str(valor_c).strip() if valor_c is not None else ""
            if "peso total" in c_texto.lower():
                apartado_actual = nombre_a
                continue

            # Si no hay apartado, no es una fila de criterio utilizable.
            if not apartado_actual:
                continue

            # Una fila de criterio tiene un nombre en A y opcionalmente
            # puntuación en C y/o observación en D.
            puntuacion = numero_puntuacion(valor_c)
            obs = "" if observacion is None else str(observacion).strip()

            # Si no hay puntuación ni observación, sigue siendo un criterio
            # válido de la plantilla (por ejemplo Q1/Q2 no evaluados).
            detalles.append({
                "apartado": apartado_actual,
                "subapartado": nombre_a,
                "puntuacion": puntuacion,
                "puntuacion_maxima": qt_max_puntuacion(apartado_actual, nombre_a),
                "observaciones": obs,
            })

        # Observaciones generales: la plantilla las coloca normalmente en A44.
        observaciones_generales = ""
        for fila in range(43, ws.max_row + 1):
            a = celda_texto(ws, fila, 1)
            if a.lower() == "observaciones generales:":
                # Puede estar en la fila siguiente (A44) o en D44 según versión.
                siguiente_a = ws.cell(fila + 1, 1).value if fila + 1 <= ws.max_row else None
                siguiente_d = ws.cell(fila + 1, 4).value if fila + 1 <= ws.max_row else None
                observaciones_generales = str(siguiente_a or siguiente_d or "").strip()
                break

        grupos[(emp["id"], anio, trimestre)] = {
            "empleado": emp,
            "detalles": detalles,
            "observaciones_generales": observaciones_generales,
            "evaluador": evaluador,
            "fecha_evaluacion": str(fecha_evaluacion) if fecha_evaluacion is not None else "",
        }
        hojas_importadas.append(trimestre)

    if not grupos:
        raise ValueError(
            "No se encontraron evaluaciones en las hojas Q1-Q4. "
            "La plantilla debe tener el empleado en A8 y los criterios desde la fila 14."
        )

    total = 0
    archivo = {
        "nombre": uploaded_file.name,
        "mime": getattr(uploaded_file, "type", None),
        "tamano_bytes": len(raw),
        "contenido_base64": base64.b64encode(raw).decode("ascii"),
    }

    for (emp_id, anio, trimestre), info in grupos.items():
        emp = info["empleado"]
        datos = {
            "origen": "Excel",
            "plantilla": "Evaluaciones trimestrales Q1-Q4",
            "archivo_subido": archivo,
            "filas_importadas": len(info["detalles"]),
            "hoja": trimestre,
            "importado_por": creado_por,
            "evaluador": info["evaluador"],
            "fecha_evaluacion": info["fecha_evaluacion"],
            "observaciones_generales": info["observaciones_generales"],
        }

        existing = (
            supabase.table("evaluaciones_trimestrales")
            .select("id")
            .eq("empleado_id", emp_id)
            .eq("anio", anio)
            .eq("trimestre", trimestre)
            .limit(1)
            .execute().data or []
        )

        if existing:
            evaluacion_id = existing[0]["id"]
            # No usamos actualizado_en porque no sabemos si esa columna existe
            # en la estructura SQL original.
            supabase.table("evaluaciones_trimestrales").update({
                "nombre_empleado": emp["nombre"],
                "datos_completos_json": datos,
            }).eq("id", evaluacion_id).execute()

            supabase.table("evaluacion_detalles").delete().eq(
                "evaluacion_id", evaluacion_id
            ).execute()
        else:
            r = supabase.table("evaluaciones_trimestrales").insert({
                "empleado_id": emp_id,
                "nombre_empleado": emp["nombre"],
                "anio": anio,
                "trimestre": trimestre,
                "habilitado": True,
                "apartado": True,
                "activo": True,
                "datos_completos_json": datos,
            }).execute()

            if not r.data:
                raise RuntimeError(
                    f"Supabase no devolvió la evaluación creada para {emp['nombre']} {trimestre}."
                )
            evaluacion_id = r.data[0]["id"]

        detalles_sql = []
        for d in info["detalles"]:
            detalles_sql.append({
                "empleado_id": emp_id,
                "nombre_empleado": emp["nombre"],
                "anio": anio,
                "trimestre": trimestre,
                "evaluacion_id": evaluacion_id,
                "apartado": d["apartado"],
                "subapartado": d["subapartado"],
                # None significa "no evaluado" y evita convertir una celda
                # vacía del Excel en un 0 artificial.
                "puntuacion": d["puntuacion"],
                "puntuacion_maxima": d["puntuacion_maxima"],
                "observaciones": d["observaciones"],
                "habilitado": True,
            })

        if detalles_sql:
            supabase.table("evaluacion_detalles").insert(detalles_sql).execute()

        total += 1

    return total

def qt_obtener_modelos_ia():
    """Lee TODOS los modelos configurados en config_prompts.

    La configuración de la aplicación guarda los modelos en las columnas
    modelo_gemini, modelo_claude y modelo_openai. Puede haber varias filas y
    cada columna puede contener uno o varios modelos separados por comas.
    No se añaden modelos de respaldo que no estén en SQL.
    """
    columnas = [
        ("modelo_gemini", "gemini"),
        ("modelo_claude", "claude"),
        ("modelo_openai", "openai"),
    ]
    salida, vistos = [], set()
    try:
        res = (supabase.table("config_prompts")
               .select("modelo_gemini, modelo_claude, modelo_openai")
               .execute())
        filas = res.data or []
        for fila in filas:
            for columna, proveedor in columnas:
                valor = fila.get(columna)
                if valor is None:
                    continue
                # Aceptamos texto separado por comas, saltos de línea o punto y coma.
                texto = str(valor).replace("\n", ",").replace(";", ",")
                for modelo in texto.split(","):
                    modelo = modelo.strip()
                    if not modelo:
                        continue
                    clave = f"{proveedor}:{modelo}".lower()
                    if clave in vistos:
                        continue
                    vistos.add(clave)
                    salida.append({
                        "proveedor": proveedor,
                        "nombre_modelo": modelo,
                    })
    except Exception as e:
        st.error(f"No se pudieron cargar los modelos IA desde config_prompts: {e}")
    return salida


def generar_y_guardar_informe_ia_multimodelo(empleado_id, nombre_emp, anio, lista_modelos_info):
    """Genera y guarda el informe trimestral usando la IA ya integrada en app.py."""
    try:
        cfg = supabase.table("config_prompts_eval").select("*").limit(1).execute().data or []
        prompt_base = cfg[0].get("prompt_texto") if cfg else None
        if not prompt_base:
            prompt_base = "Realiza un informe evaluativo profesional basado en estos datos."
    except Exception:
        prompt_base = "Realiza un informe evaluativo profesional basado en estos datos."

    vis = qt_obtener_visibilidad(empleado_id, anio)
    qs_hab = vis.get("qs_habilitados", {})
    apts_hab = vis.get("apartados_habilitados", {})
    sub_ocultos = vis.get("subapartados_deshabilitados", [])

    try:
        q_evals = (supabase.table("evaluaciones_trimestrales").select("*")
                   .eq("empleado_id", empleado_id).eq("anio", anio).eq("activo", True)
                   .execute().data or [])
    except Exception as e:
        return False, f"Error leyendo evaluaciones trimestrales: {e}"

    resumen_datos = []
    for q in q_evals:
        q_nom = q.get("trimestre")
        if not qs_hab.get(q_nom, True):
            continue
        try:
            detalles = supabase.table("evaluacion_detalles").select("*").eq("evaluacion_id", q["id"]).execute().data or []
        except Exception as e:
            return False, f"Error leyendo detalles del trimestre {q_nom}: {e}"
        for r in detalles:
            apartado, subapartado = r.get("apartado"), r.get("subapartado")
            if not apts_hab.get(apartado, True) or qt_sub_oculto(sub_ocultos, apartado, subapartado):
                continue
            resumen_datos.append({
                "trimestre": q_nom, "apartado": apartado, "subapartado": subapartado,
                "puntuacion": r.get("puntuacion"), "observaciones": r.get("observaciones", "")
            })

    if not resumen_datos:
        return False, f"No existen datos de evaluaciones habilitadas para {nombre_emp} en {anio}."

    prompt_completo = f"""{prompt_base}

Empleado: {nombre_emp}
Año: {anio}

Datos de evaluaciones del año:
{json.dumps(resumen_datos, ensure_ascii=False, indent=2)}

Genera un informe detallado, constructivo y estructurado en Markdown.
"""

    textos, errores = [], []
    for mod_info in lista_modelos_info:
        nombre_modelo = mod_info.get("nombre_modelo")
        proveedor = mod_info.get("proveedor", "gemini")
        if not nombre_modelo:
            continue
        try:
            # Firma real de consultar_ia() en app.py: consultar_ia(modelo, prompt, sistema="")
            texto = consultar_ia(nombre_modelo, prompt_completo)
            if texto:
                textos.append(f"### 🤖 Informe generado con {nombre_modelo} ({proveedor.upper()})\n\n{texto}" if len(lista_modelos_info) > 1 else texto)
            else:
                errores.append(f"[{nombre_modelo}]: la IA no devolvió contenido")
        except Exception as e:
            errores.append(f"[{nombre_modelo}]: {e}")

    if not textos:
        return False, f"Fallaron todas las consultas de IA: {'; '.join(errores)}"

    informe_final = "\n\n---\n\n".join(textos)
    try:
        # Guardamos cada informe en la tabla real del esquema. Esto permite
        # recuperarlo después de un rerun de Streamlit y controlar su visibilidad.
        cfg_id = None
        try:
            cfg_rows = supabase.table("config_prompts_eval").select("id").limit(1).execute().data or []
            cfg_id = cfg_rows[0].get("id") if cfg_rows else None
        except Exception:
            pass

        # Un registro por ejecución/modelo; los anteriores no desaparecen.
        for mod_info, texto_modelo in zip(lista_modelos_info, textos):
            nombre_modelo = mod_info.get("nombre_modelo")
            if not nombre_modelo:
                continue
            # Si hay varios modelos, quitar el encabezado añadido para guardar el texto limpio.
            texto_guardar = texto_modelo
            prefijo = f"### 🤖 Informe generado con {nombre_modelo} ({mod_info.get('proveedor','gemini').upper()})\n\n"
            if texto_guardar.startswith(prefijo):
                texto_guardar = texto_guardar[len(prefijo):]
            payload = {
                "empleado_id": empleado_id,
                "nombre_empleado": nombre_emp,
                "anio": int(anio),
                "prompt_id": cfg_id,
                "modelo_ia": nombre_modelo,
                "resultado_texto": texto_guardar,
                "grafica_data_json": None,
                "activo": True,
                "creado_por": st.session_state.get("user_nombre") or st.session_state.get("usuario_actual") or "Administrador",
                "visible_empleado": False,
            }
            supabase.table("resultados_evaluacion_ia").insert(payload).execute()
    except Exception as e:
        return False, f"Error al guardar el informe en la BD: {e}"
    return True, informe_final


def qt_render_resumen(emp_id, nombre, anio):
    vis = qt_obtener_visibilidad(emp_id, anio)
    qs = vis.get("qs_habilitados", {})
    apts = vis.get("apartados_habilitados", {})
    ocultos = set(vis.get("subapartados_deshabilitados", []))
    pesos_base = qt_obtener_pesos()
    estructura = qt_estructura(emp_id, anio)
    pesos, pesos_sub, total_w = qt_pesos_recalculados(pesos_base, apts, estructura, ocultos)

    evs = (supabase.table("evaluaciones_trimestrales").select("*")
           .eq("empleado_id", emp_id).eq("anio", int(anio))
           .order("trimestre").execute().data or [])
    if not evs:
        st.info("No hay evaluaciones trimestrales para este empleado/año.")
        return

    st.subheader(f"📊 {nombre} · {anio}")
    st.success(f"Pesos efectivos de apartados activos: **{total_w:.2f}%**")

    # Acumulación anual basada en los mismos datos que se muestran por trimestre.
    q_resultados = []
    anual_puntos = 0.0
    anual_max = 0.0

    for q in evs:
        q_nom = q.get("trimestre")
        if not qs.get(q_nom, True):
            continue
        det = (supabase.table("evaluacion_detalles").select("*")
               .eq("evaluacion_id", q["id"]).execute().data or [])
        df = pd.DataFrame(det)
        if df.empty:
            continue
        df = df[df.apply(lambda r: apts.get(r.get("apartado"), True) and not qt_sub_oculto(ocultos, r.get("apartado"), r.get("subapartado")), axis=1)]
        if df.empty:
            continue

        q_puntos = 0.0
        q_max = 0.0
        for _, r in df.iterrows():
            if r.get("puntuacion") is None or pd.isna(r.get("puntuacion")):
                continue
            mx = qt_max_puntuacion(r.get("apartado"), r.get("subapartado"))
            q_puntos += float(r.get("puntuacion") or 0)
            q_max += mx
        q_nota = (q_puntos / q_max * 10.0) if q_max else None
        q_resultados.append((q_nom, q_puntos, q_max, q_nota, df))
        anual_puntos += q_puntos
        anual_max += q_max

    st.markdown("### 🏆 Puntuación total")
    col1, col2, col3 = st.columns(3)
    anual_nota = (anual_puntos / anual_max * 10.0) if anual_max else 0.0
    notas_q = [n for _,_,_,n,_ in q_resultados if n is not None]
    media_q = (sum(notas_q) / len(notas_q)) if notas_q else 0.0
    with col1:
        st.metric("Total anual", f"{anual_puntos:.2f} / {anual_max:.2f}")
    with col2:
        st.metric("Nota anual normalizada", f"{anual_nota:.2f} / 10")
    try:
        cfg = supabase.table("config_prompts_eval").select("objetivo_media").limit(1).execute().data or []
        objetivo = float(cfg[0].get("objetivo_media")) if cfg and cfg[0].get("objetivo_media") is not None else 8.0
    except Exception:
        objetivo = 8.0
    with col3:
        if media_q >= objetivo:
            st.success(f"Media de Q: **{media_q:.2f}/10** · Objetivo {objetivo:.2f} · **CUMPLE**")
        else:
            st.warning(f"Media de Q: **{media_q:.2f}/10** · Objetivo {objetivo:.2f} · **NO CUMPLE**")

    if q_resultados:
        st.markdown("### 📅 Puntuación por trimestre")
        st.dataframe(pd.DataFrame([
            {"Trimestre": q, "Puntuación": f"{p:.2f} / {m:.2f}", "Nota /10": f"{n:.2f}" if n is not None else "Sin datos", "Objetivo": "Cumple" if n is not None and n >= objetivo else "No cumple"}
            for q,p,m,n,_ in q_resultados
        ]), use_container_width=True, hide_index=True)

    if pesos_base:
        tabla_pesos = []
        for ap, base in pesos_base.items():
            tabla_pesos.append({"Apartado": ap, "Peso base %": round(float(base or 0),2), "Activo": "Sí" if apts.get(ap,True) else "No", "Peso efectivo %": round(float(pesos.get(ap,0)),2)})
        with st.expander("⚖️ Pesos base y pesos efectivos", expanded=False):
            st.dataframe(pd.DataFrame(tabla_pesos), use_container_width=True, hide_index=True)

    for q_nom, q_puntos, q_max, q_nota, df in q_resultados:
        st.markdown(f"## {q_nom} · **{q_puntos:.2f} / {q_max:.2f}** · **{q_nota:.2f}/10**")
        for ap in [x for x in QT_APARTADOS_DEFECTO if x in set(df["apartado"].tolist())] + [x for x in df["apartado"].unique() if x not in QT_APARTADOS_DEFECTO]:
            g = df[df["apartado"] == ap]
            if g.empty:
                continue
            p = 0.0; maxp = 0.0
            for _, r in g.iterrows():
                if r.get("puntuacion") is None or pd.isna(r.get("puntuacion")):
                    continue
                p += float(r.get("puntuacion") or 0)
                maxp += qt_max_puntuacion(ap, r.get("subapartado"))
            nota = (p / maxp * 10.0) if maxp else 0.0
            w = pesos.get(ap,0)
            with st.expander(f"📌 {ap} · {p:.2f}/{maxp:.2f} · {nota:.2f}/10 · Peso {w:.2f}%", expanded=True):
                for _, r in g.iterrows():
                    sub = r.get("subapartado")
                    mx = qt_max_puntuacion(ap, sub)
                    score = r.get("puntuacion")
                    score_txt = "Sin evaluar" if score is None or pd.isna(score) else f"{float(score):g} / {mx:g}"
                    wsp = pesos_sub.get(ap,{}).get(sub,0.0)
                    st.write(f"**{sub}** · {score_txt} · Peso efectivo {wsp:.2f}%")
                    if r.get("observaciones"):
                        st.caption(str(r.get("observaciones")))
        q_row = next((x for x in evs if x.get("trimestre") == q_nom), None)
        if q_row and q_row.get("observaciones_generales"):
            st.info(q_row["observaciones_generales"])

def qt_pdf(nombre,informe,anio):
    return generar_pdf_evaluacion_ia(nombre,informe,anio)


def qt_render_informes_ia(emp_id, nombre, anio, admin=False):
    """Muestra informes IA persistidos para un empleado/año y permite ver/descargar.
    El admin además puede activar/desactivar la visibilidad para el empleado.
    """
    try:
        rows = (supabase.table("resultados_evaluacion_ia").select("*")
                .eq("empleado_id", emp_id).eq("anio", int(anio)).eq("activo", True)
                .order("created_at", desc=True).execute().data or [])
    except Exception as e:
        st.error(f"No se pudieron cargar los informes IA: {e}")
        return

    st.markdown(f"### 📄 Informes IA guardados · {anio}")
    if not rows:
        st.info(f"No hay informes IA guardados para {nombre} en {anio}.")
        return

    for r in rows:
        rid = r.get("id")
        modelo = r.get("modelo_ia") or "Modelo IA"
        fecha = r.get("created_at") or ""
        visible = bool(r.get("visible_empleado"))
        texto = r.get("resultado_texto") or ""
        etiqueta = "🟢 Visible al empleado" if visible else "🔒 Solo administrador"
        with st.expander(f"🤖 {modelo} · {etiqueta} · {str(fecha)[:16]}", expanded=False):
            if admin:
                nuevo_visible = st.checkbox(
                    "Permitir que el empleado vea este informe",
                    value=visible,
                    key=f"qt_inf_vis_{rid}",
                )
                if st.button("💾 Guardar visibilidad", key=f"qt_inf_vis_save_{rid}"):
                    try:
                        supabase.table("resultados_evaluacion_ia").update({"visible_empleado": nuevo_visible}).eq("id", rid).execute()
                        st.success("Visibilidad guardada.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"No se pudo guardar la visibilidad: {e}")

            st.markdown(texto)
            pdf = qt_pdf(nombre, texto, anio)
            if pdf:
                st.download_button(
                    "📥 Descargar este informe en PDF",
                    data=pdf,
                    file_name=f"Informe_IA_{nombre}_{anio}_{modelo}.pdf".replace("/", "-"),
                    mime="application/pdf",
                    key=f"qt_inf_pdf_{rid}",
                    use_container_width=True,
                )


def render_admin_evaluaciones_trimestrales():
    st.title("📋 Evaluaciones Trimestrales")
    t1,t2,t4,t5,t6=st.tabs(["📥 Cargar Excel","👁️ Visibilidad","⚙️ Configuración","🤖 Generar e Insertar Informes IA","👥 Datos empleado"])
    with t1:
        st.subheader("📥 Cargar evaluaciones trimestrales")
        anio=st.number_input("Año por defecto",min_value=2020,max_value=2100,value=datetime.datetime.now().year,key="qt_upload_year")
        f=st.file_uploader("Selecciona Excel (.xlsx)",type=["xlsx"],key="qt_excel")
        if f:
            st.success(f"Archivo leído: {f.name}")
            st.info("El Excel se procesa directamente al pulsar el botón. Las hojas válidas son Q1, Q2, Q3 y Q4; la hoja Resumen se ignora.")
            st.markdown("### 💾 Guardar Excel en SQL")
            st.caption("Si una evaluación Q ya existe, se actualiza con los datos del Excel. Las celdas vacías no generan puntuaciones artificiales.")
            if st.button("💾 Guardar pestañas Q1-Q4 en SQL",key="qt_save_excel",type="primary",use_container_width=True):
                try:
                    with st.spinner("Guardando las evaluaciones en SQL…"):
                        total_guardadas = qt_cargar_excel(f,anio,st.session_state.user_nombre)
                    st.success(f"✅ Se han guardado correctamente {total_guardadas} pestaña(s) de evaluación en SQL.")
                except Exception as e:
                    st.error(f"❌ No se pudo guardar el Excel en SQL: {e}")
                    st.exception(e)
    with t2:
        st.subheader("👁️ Visibilidad por empleado y año")
        emps = supabase.table("empleados").select("id,nombre,activo").order("nombre").execute().data or []
        emp = st.selectbox("Empleado", emps, key="qt_vis_emp", format_func=lambda x:f"{x['nombre']} · {'Activo' if x.get('activo') else 'Deshabilitado'}")
        anio = st.number_input("Año", value=datetime.datetime.now().year, step=1, key="qt_vis_year")
        if emp:
            v = qt_obtener_visibilidad(emp["id"], anio)
            qs = {}
            st.markdown("#### Trimestres visibles")
            cols = st.columns(4)
            for i, q in enumerate(["Q1","Q2","Q3","Q4"]):
                qs[q] = cols[i].checkbox(q, value=v.get("qs_habilitados",{}).get(q,True), key=f"qtq_{q}_{emp['id']}")
            estructura = qt_estructura(emp["id"], anio)
            af = {}; sub = []
            st.markdown("#### Apartados y subapartados")
            for ap, subs in estructura.items():
                with st.expander(ap, expanded=True):
                    af[ap] = st.checkbox(f"Habilitar apartado · {ap}", value=v.get("apartados_habilitados",{}).get(ap,True), key=f"qta_{emp['id']}_{anio}_{ap}")
                    cols_sub = st.columns(2) if len(subs) > 1 else [st.container()]
                    for idx, su in enumerate(subs):
                        clave = qt_sub_clave(ap, su)
                        antiguo = su in v.get("subapartados_deshabilitados",[])
                        guardado = clave in v.get("subapartados_deshabilitados",[]) or antiguo
                        ok = cols_sub[idx % len(cols_sub)].checkbox(su, value=not guardado, key=f"qts_{emp['id']}_{anio}_{clave}", disabled=not af[ap])
                        if not ok:
                            sub.append(clave)
                    st.caption(f"Puntuación máxima por subapartado: {qt_max_puntuacion(ap):g} puntos · El apartado será la suma de sus subapartados activos.")
            if st.button("💾 Guardar visibilidad del empleado", key="qt_save_vis", type="primary"):
                qt_guardar_visibilidad(emp["id"], anio, qs, af, sub)
                st.success(f"Configuración guardada para {emp['nombre']} · {anio}.")

        st.markdown("---")
        st.markdown("#### 📤 Exportar configuración de visibilidad")
        st.caption("Exporta la configuración efectiva de visibilidad de todos los empleados para el año seleccionado.")
        if st.button("📊 Preparar Excel de visibilidad de todos los empleados", key="qt_export_vis"):
            if openpyxl is None:
                st.error("Falta openpyxl para generar el Excel.")
            else:
                wb_exp = openpyxl.Workbook(); ws_exp = wb_exp.active; ws_exp.title = "Visibilidad"
                ws_exp.append(["Empleado","ID","Año","Activo","Q1","Q2","Q3","Q4","Apartado","Activo apartado","Subapartado","Activo subapartado"])
                for e in emps:
                    vv = qt_obtener_visibilidad(e["id"], anio)
                    estructura_e = qt_estructura(e["id"], anio)
                    for ap, subs in estructura_e.items():
                        for su in subs:
                            oculto = qt_sub_oculto(vv.get("subapartados_deshabilitados",[]), ap, su)
                            ws_exp.append([e.get("nombre"), e.get("id"), anio, bool(e.get("activo")),
                                           bool(vv.get("qs_habilitados",{}).get("Q1",True)), bool(vv.get("qs_habilitados",{}).get("Q2",True)),
                                           bool(vv.get("qs_habilitados",{}).get("Q3",True)), bool(vv.get("qs_habilitados",{}).get("Q4",True)),
                                           ap, bool(vv.get("apartados_habilitados",{}).get(ap,True)), su, not oculto])
                bio=io.BytesIO(); wb_exp.save(bio); bio.seek(0)
                st.download_button("⬇️ Descargar Excel de visibilidad", bio.getvalue(), f"Visibilidad_Evaluaciones_{anio}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="qt_download_vis")

    with t4:
        st.subheader("⚙️ Configuración de evaluaciones trimestrales")
        try:
            cfg_rows = supabase.table("config_prompts_eval").select("*").limit(1).execute().data or []
            cfg = cfg_rows[0] if cfg_rows else {}
        except Exception:
            cfg_rows=[]; cfg={}
        prompt_col = "prompt_text" if "prompt_text" in cfg else "prompt_texto"
        prompt_actual = cfg.get(prompt_col) or "Realiza un informe evaluativo profesional basado en estos datos."
        objetivo_actual = float(cfg.get("objetivo_media") or 8.0)
        nuevo_prompt = st.text_area("📝 Prompt base para informes IA", value=prompt_actual, height=180, key="qt_prompt_eval")
        nuevo_objetivo = st.number_input("🎯 Objetivo de media anual (sobre 10)", min_value=0.0, max_value=10.0, value=objetivo_actual, step=0.1, key="qt_obj_eval")
        if st.button("💾 Guardar configuración de prompt y objetivo", type="primary", key="qt_save_cfg"):
            datos_cfg={prompt_col:nuevo_prompt,"objetivo_media":nuevo_objetivo}
            try:
                if cfg.get("id") is not None: datos_cfg["id"]=cfg["id"]
                supabase.table("config_prompts_eval").upsert(datos_cfg).execute()
                st.success("Configuración guardada correctamente.")
            except Exception as e:
                st.error(f"No se pudo guardar la configuración: {e}")
        st.markdown("---")
        st.markdown("#### ⚖️ Pesos de apartados")
        st.caption("Los pesos SQL son la base. La visibilidad individual redistribuye automáticamente los pesos activos hasta el 100%.")
        rows=supabase.table("config_apartados_pesos").select("*").order("apartado").execute().data or []
        if not rows:
            rows=[{"apartado":k,"peso_porcentaje":v,"habilitado":True} for k,v in qt_obtener_pesos().items()]
        total_base=sum(float(x.get("peso_porcentaje") or 0) for x in rows if x.get("habilitado",True))
        st.metric("Suma de pesos base",f"{total_base:.2f}%")
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.markdown("#### 📐 Máximas puntuaciones")
        st.dataframe(pd.DataFrame([{"Apartado":k,"Máximo por subapartado":v} for k,v in QT_MAX_PUNTUACION_APARTADO.items()]), use_container_width=True, hide_index=True)
        st.info("El valor del apartado es la suma de las puntuaciones de sus subapartados activos. La nota se normaliza a 10 usando la suma de sus máximos reales.")
    with t5:
        st.subheader("🤖 Generar e Insertar Informes IA (Multi-modelo y Multi-empleado)")
        modelos=qt_obtener_modelos_ia(); opciones=[f"{m['nombre_modelo']} ({m['proveedor'].upper()})" for m in modelos]
        selmods=st.multiselect("Modelos IA",opciones,default=opciones[:1],key="qt_models"); anio=st.number_input("Año",value=datetime.datetime.now().year,step=1,key="qt_ai_year")
        activos=supabase.table("empleados").select("id,nombre").eq("activo",True).order("nombre").execute().data or []; mp={e["nombre"]:e["id"] for e in activos}
        st.markdown("#### Selección de Empleados")
        st.success(f"Usuarios activos disponibles: **{len(activos)}**")
        todos=st.checkbox("Seleccionar TODOS los usuarios activos",key="qt_all_active"); sels=list(mp) if todos else st.multiselect("Empleado(s)",list(mp),key="qt_ai_emps")
        hacer_visibles = st.checkbox("👁️ Hacer visibles automáticamente al empleado los informes generados", value=False, key="qt_ai_visible_new")
        infos=[modelos[opciones.index(x)] for x in selmods]
        if st.button("🚀 Generar e Insertar Informes Seleccionados",type="primary",key="qt_ai_go"):
            if not sels or not infos: st.warning("Selecciona empleados activos y al menos un modelo.")
            else:
                resultados=[]
                for nom in sels:
                    ok,msg=generar_y_guardar_informe_ia_multimodelo(mp[nom],nom,anio,infos); resultados.append((nom,ok,msg))
                for nom,ok,msg in resultados:
                    if ok:
                        if hacer_visibles:
                            try:
                                supabase.table("resultados_evaluacion_ia").update({"visible_empleado": True}).eq("empleado_id", mp[nom]).eq("anio", int(anio)).eq("activo", True).execute()
                            except Exception as e_vis:
                                st.warning(f"El informe se guardó, pero no se pudo activar su visibilidad: {e_vis}")
                        st.success(f"Informe generado y guardado para {nom} · año {anio}")
                    else:
                        st.error(f"{nom}: {msg}")

        st.markdown("---")
        st.markdown("### 👁️ Ver informes ya guardados")
        if activos:
            emp_ver = st.selectbox("Empleado", activos, format_func=lambda x:x["nombre"], key="qt_ai_view_emp")
            anios_inf = sorted({int(x.get("anio")) for x in (supabase.table("resultados_evaluacion_ia").select("anio").eq("empleado_id", emp_ver["id"]).eq("activo", True).execute().data or []) if x.get("anio")}, reverse=True)
            if not anios_inf:
                anios_inf = [anio]
            anio_inf = st.selectbox("📅 Año del informe", anios_inf, key="qt_ai_view_year")
            qt_render_informes_ia(emp_ver["id"], emp_ver["nombre"], anio_inf, admin=True)
    with t6:
        emps=supabase.table("empleados").select("id,nombre,activo").order("nombre").execute().data or []
        emp=st.selectbox("Empleado",emps,key="qt_data_emp",format_func=lambda x:x["nombre"]); anio=st.number_input("Año",value=datetime.datetime.now().year,step=1,key="qt_data_year")
        if emp: qt_render_resumen(emp["id"],emp["nombre"],anio)

def render_empleado_evaluaciones_trimestrales(emp_id,nombre):
    st.title("📋 Evaluaciones Trimestrales")
    if not emp_id: st.warning("No hay empleado autenticado."); return
    ev=supabase.table("evaluaciones_trimestrales").select("anio").eq("empleado_id",emp_id).eq("activo",True).execute().data or []
    anios=sorted({int(x["anio"]) for x in ev if x.get("anio")},reverse=True) or [datetime.datetime.now().year]
    anio=st.selectbox("📅 Año de la evaluación/informe",anios,key="qt_emp_year")
    qt_render_resumen(emp_id,nombre,anio)
    st.markdown("---")
    qt_render_informes_ia(emp_id,nombre,anio,admin=False)


# ---------------------------------------------------------
# DIÁLOGO DE AUTENTICACIÓN Y CONTRASEÑA POR DEFECTO
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
            # La selección/autenticación de usuario pertenece al flujo Python
            # principal; el prototipo HTML no debe crear un segundo acceso.
            st.session_state.user_id = usuario["id"]
            st.session_state.user_nombre = usuario["nombre"]
            st.session_state.es_croma = usuario.get("es_admin_croma", False)
            st.session_state.autenticado = True
            st.rerun()

# ---------------------------------------------------------
# FRAGMENTOS DE TEMPORIZACIÓN DINÁMICA
# ---------------------------------------------------------
@st.fragment(run_every=1)
def renderizar_temporizador_realtime(idx):
    tiempo_base = st.session_state.tiempos_restantes_preguntas.get(idx, TIEMPO_LIMITE_PREGUNTA)
    if st.session_state.tiempo_inicio_pregunta is None:
        st.session_state.tiempo_inicio_pregunta = time.time()
        
    tiempo_transcurrido = int(time.time() - st.session_state.tiempo_inicio_pregunta)
    tiempo_restante = max(0, tiempo_base - tiempo_transcurrido)
    
    # Temporizador General del Examen
    if st.session_state.tiempo_inicio_examen:
        total_p = len(st.session_state.preguntas_seleccionadas)
        tiempo_total_limite = total_p * TIEMPO_LIMITE_PREGUNTA
        tiempo_transcurrido_examen = int(time.time() - st.session_state.tiempo_inicio_examen)
        tiempo_restante_examen = max(0, tiempo_total_limite - tiempo_transcurrido_examen)
        st.info(f"⏳ **Tiempo total restante del examen:** {tiempo_restante_examen // 60:02d}:{tiempo_restante_examen % 60:02d} minutos")

    st.progress(tiempo_restante / TIEMPO_LIMITE_PREGUNTA)
    if tiempo_restante > 0:
        st.caption(f"⏱️ Tiempo restante en esta pregunta: **{tiempo_restante} segundos**")
    else:
        st.warning("⏰ ¡Tiempo agotado en esta pregunta! La selección ha quedado bloqueada.")

@st.fragment(run_every=1)
def renderizar_temporizador_examen():
    total_p = len(st.session_state.preguntas_seleccionadas)
    limite = int(st.session_state.get("tiempo_limite_examen_actual", total_p * TIEMPO_LIMITE_PREGUNTA))
    inicio = st.session_state.tiempo_inicio_examen or time.time()
    restante = max(0, limite - int(time.time() - inicio))
    c1, c2 = st.columns([3, 1])
    with c1:
        st.progress(restante / max(1, limite), text="Tiempo total del examen")
    with c2:
        st.metric("Tiempo restante", f"{restante // 60:02d}:{restante % 60:02d}")
    if restante <= 0 and not st.session_state.get("tiempo_examen_agotado", False):
        st.session_state.tiempo_examen_agotado = True
        st.rerun()


@st.fragment(run_every=1)
def renderizar_temporizador_revision():
    if st.session_state.tiempo_inicio_revision is None:
        st.session_state.tiempo_inicio_revision = time.time()
        
    tiempo_revision_transcurrido = int(time.time() - st.session_state.tiempo_inicio_revision)
    tiempo_revision_restante = max(0, 300 - tiempo_revision_transcurrido)
    
    if tiempo_revision_restante > 0:
        st.warning(f"⏱️ Tiempo restante de revisión: **{tiempo_revision_restante // 60:02d}:{tiempo_revision_restante % 60:02d} minutos**. Si se agota, el examen se finalizará automáticamente.")
    else:
        st.error("⏰ ¡Tiempo de revisión agotado (5 minutos)! Finalizando el examen automáticamente...")

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

    def registrar_inicio_examen_bd(apartado_nombre, examen_id_val=None):
        """Registra el inicio formal del examen en Supabase al hacer clic en comenzar."""
        try:
            tiempo_ini_examen = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            id_examen_validado = examen_id_val if isinstance(examen_id_val, int) and examen_id_val > 0 else None
            
            registro_inicio = {
                "empleado_id": st.session_state.user_id,
                "nombre_empleado": st.session_state.user_nombre,
                "examen_id": id_examen_validado,
                "apartado": apartado_nombre,
                "nota": 0.0,
                "porcentaje_obtenido": 0.0,
                "respuestas_usuario": [],
                "fecha_inicio": tiempo_ini_examen,
                "fecha_fin": None,
                "tiempo_total_segundos": 0,
                "tiempo_limite": len(st.session_state.preguntas_seleccionadas) * TIEMPO_LIMITE_PREGUNTA,
                "sobrepasado_tiempo": False,
                "activo": True
            }
            res = supabase.table("intentos_examen").insert(registro_inicio).execute()
            if res.data and len(res.data) > 0:
                st.session_state.intento_id_actual = res.data[0]["id"]
        except Exception as e:
            st.error(f"Error al registrar inicio de examen en BD: {e}")

    def cancelar_examen_bd():
        """Sanciona el examen como realizado con nota 0 si se cancela/abandona."""
        if st.session_state.intento_id_actual:
            tiempo_fin_examen = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            duracion_total = int(time.time() - (st.session_state.tiempo_inicio_examen or time.time()))
            try:
                supabase.table("intentos_examen").update({
                    "nota": 0.0,
                    "porcentaje_obtenido": 0.0,
                    "fecha_fin": tiempo_fin_examen,
                    "tiempo_total_segundos": duracion_total,
                    "respuestas_usuario": st.session_state.respuestas_detalle
                }).eq("id", st.session_state.intento_id_actual).execute()
            except Exception as e:
                st.error(f"Error al registrar cancelación de examen: {e}")

    def guardar_intento_en_bd():
        if st.session_state.examen_finalizado:
            return True
        total_p = len(st.session_state.preguntas_seleccionadas)
        correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
        porcentaje = round((correctas / total_p) * 100, 2) if total_p > 0 else 0.0
        nota_final = round((correctas / total_p) * 10, 2) if total_p > 0 else 0.0
        
        duracion_total = int(time.time() - (st.session_state.tiempo_inicio_examen or time.time()))
        tiempo_limite_total = total_p * TIEMPO_LIMITE_PREGUNTA
        tiempo_fin_examen = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            id_examen_validado = st.session_state.examen_id if isinstance(st.session_state.examen_id, int) and st.session_state.examen_id > 0 else None

            datos_actualizacion = {
                "nota": nota_final,
                "porcentaje_obtenido": porcentaje,
                "respuestas_usuario": st.session_state.respuestas_detalle,
                "fecha_fin": tiempo_fin_examen,
                "tiempo_total_segundos": duracion_total,
                "sobrepasado_tiempo": st.session_state.sobrepaso_tiempo_global
            }

            if st.session_state.intento_id_actual:
                supabase.table("intentos_examen").update(datos_actualizacion).eq("id", st.session_state.intento_id_actual).execute()
            else:
                tiempo_ini_examen = datetime.datetime.fromtimestamp(st.session_state.tiempo_inicio_examen, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if st.session_state.tiempo_inicio_examen else tiempo_fin_examen
                datos_actualizacion.update({
                    "empleado_id": st.session_state.user_id,
                    "nombre_empleado": st.session_state.user_nombre,
                    "examen_id": id_examen_validado,
                    "apartado": st.session_state.apartado_actual,
                    "fecha_inicio": tiempo_ini_examen,
                    "tiempo_limite": tiempo_limite_total,
                    "activo": True
                })
                supabase.table("intentos_examen").insert(datos_actualizacion).execute()

            try:
                supabase.table("autorizaciones_examen").delete()\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("apartado", st.session_state.apartado_actual).execute()
            except Exception:
                pass
            
            st.session_state.examen_finalizado = True
            return True

        except Exception as e:
            st.error(f"Error guardando intento: {e}")
            return False
    
    # MODO REVISIÓN PREVIA A FINALIZAR
    if st.session_state.modo_revision:
        if st.session_state.tiempo_inicio_revision is None:
            st.session_state.tiempo_inicio_revision = time.time()
            
        tiempo_revision_transcurrido = int(time.time() - st.session_state.tiempo_inicio_revision)
        tiempo_revision_restante = max(0, 300 - tiempo_revision_transcurrido)
        
        st.subheader("🔍 Revisión de Examen previa a la entrega final")
        
        if not st.session_state.examen_finalizado:
            st.info("Revisa tus respuestas e indica si deseas modificar alguna antes de la entrega definitiva.")

            # Temporizador dinámico en tiempo real para los 5 minutos de revisión
            renderizar_temporizador_revision()

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
                c_fin1, c_fin2 = st.columns(2)
                with c_fin1:
                    if st.button("✅ Confirmar y Entregar Examen Definitivamente", use_container_width=True):
                        if guardar_intento_en_bd():
                            st.rerun()
                with c_fin2:
                    if st.button("🚫 Cancelar / Abandonar Examen (Nota 0)", use_container_width=True):
                        cancelar_examen_bd()
                        st.session_state.examen_activo = False
                        st.session_state.modo_revision = False
                        st.session_state.examen_finalizado = True
                        st.rerun()
        else:
            total_p = len(st.session_state.preguntas_seleccionadas)
            correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
            porcentaje = round((correctas / total_p) * 100, 2) if total_p > 0 else 0.0
            nota_final = round((correctas / total_p) * 10, 2) if total_p > 0 else 0.0
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

    # CUESTIONARIO ACTIVO: TODAS LAS PREGUNTAS EN UNA SOLA PANTALLA
    elif st.session_state.examen_activo:
        total_p = len(st.session_state.preguntas_seleccionadas)
        tiempo_limite_total = int(st.session_state.get("tiempo_limite_examen_actual", total_p * TIEMPO_LIMITE_PREGUNTA))
        transcurrido_total = int(time.time() - (st.session_state.tiempo_inicio_examen or time.time()))
        restante_total = max(0, tiempo_limite_total - transcurrido_total)
        st.markdown("<div id='pregunta_activa'></div>", unsafe_allow_html=True)
        st.subheader(f"📝 Examen completo · {total_p} preguntas")
        st.caption("Todas las preguntas están disponibles en esta pantalla. Responde en el orden que prefieras y revisa tus selecciones antes de entregar.")
        renderizar_temporizador_examen()
        if restante_total <= 0:
            st.warning("⏰ Se agotó el tiempo. Las respuestas seleccionadas se entregarán automáticamente al confirmar.")

        respuestas_previas = {r.get("idx_pregunta"): r.get("opcion_elegida") for r in st.session_state.respuestas_detalle}
        for idx, p_actual in enumerate(st.session_state.preguntas_seleccionadas):
            with st.container(border=True):
                st.markdown(f"#### Pregunta {idx + 1} de {total_p}")
                st.caption(f"📌 Categoría: {p_actual.get('subindice', p_actual.get('apartado', 'General'))} · Dificultad: {p_actual.get('dificultad', 'dificil')}")
                st.markdown(f"<div class='pregunta-titulo'>{p_actual.get('pregunta', 'Pregunta no disponible')}</div>", unsafe_allow_html=True)
                opciones = p_actual.get("opciones_barajadas", [])
                previa = respuestas_previas.get(idx)
                idx_previa = opciones.index(previa) if previa in opciones else None
                st.radio(
                    "Selecciona una respuesta:",
                    opciones,
                    index=idx_previa,
                    key=f"p_{idx}",
                    disabled=restante_total <= 0,
                    label_visibility="visible"
                )
                if idx in st.session_state.pistas_activadas:
                    st.info(f"💡 Pista: {p_actual.get('pista', 'Revisa los conceptos clave.')}")
                elif st.session_state.comodines_restantes > 0 and restante_total > 0:
                    if st.button("💡 Mostrar pista (consume 1 ayuda)", key=f"btn_pista_{idx}"):
                        st.session_state.comodines_restantes -= 1
                        st.session_state.pistas_activadas.add(idx)
                        st.rerun()

        st.caption(f"Ayudas disponibles: {st.session_state.comodines_restantes} / 3")
        col_finish1, col_finish2 = st.columns(2)
        with col_finish1:
            if st.button("📋 Revisar y entregar examen", key="btn_revisar_entregar_todo", use_container_width=True):
                respuestas_detalle = []
                for idx, p_item in enumerate(st.session_state.preguntas_seleccionadas):
                    eleccion = st.session_state.get(f"p_{idx}")
                    if not eleccion:
                        eleccion = "En blanco (Sin responder)"
                    respuestas_detalle.append({
                        "idx_pregunta": idx,
                        "pregunta": p_item.get("pregunta", ""),
                        "subindice": p_item.get("subindice", "General"),
                        "dificultad": p_item.get("dificultad", "dificil"),
                        "opcion_elegida": eleccion,
                        "respuesta_correcta_texto": p_item.get("respuesta_correcta_texto", ""),
                        "opciones_posibles": p_item.get("opciones_barajadas", []),
                        "es_correcta": eleccion == p_item.get("respuesta_correcta_texto", "")
                    })
                st.session_state.respuestas_detalle = respuestas_detalle
                st.session_state.modo_revision = True
                st.session_state.tiempo_inicio_revision = None
                st.rerun()
        with col_finish2:
            if st.button("🚫 Cancelar examen (nota 0)", key="btn_cancelar_examen_todo", use_container_width=True):
                respuestas_detalle = []
                for idx, p_item in enumerate(st.session_state.preguntas_seleccionadas):
                    eleccion = st.session_state.get(f"p_{idx}") or "En blanco (Sin responder)"
                    respuestas_detalle.append({
                        "idx_pregunta": idx, "pregunta": p_item.get("pregunta", ""),
                        "subindice": p_item.get("subindice", "General"),
                        "dificultad": p_item.get("dificultad", "dificil"),
                        "opcion_elegida": eleccion,
                        "respuesta_correcta_texto": p_item.get("respuesta_correcta_texto", ""),
                        "opciones_posibles": p_item.get("opciones_barajadas", []),
                        "es_correcta": False
                    })
                st.session_state.respuestas_detalle = respuestas_detalle
                cancelar_examen_bd()
                st.session_state.examen_activo = False
                st.session_state.modo_revision = False
                st.session_state.examen_finalizado = True
                st.rerun()

    # MENÚ PRINCIPAL
    else:
        st.info(f"🎯 **Criterio de Evaluación:** Para obtener un resultado **APROBADO**, debes alcanzar una nota mínima de **{UMBRAL_APROBADO_PORCENTAJE / 10} / 10** ({int(UMBRAL_APROBADO_PORCENTAJE)}% de aciertos). Tiempo configurado por pregunta: **{TIEMPO_LIMITE_PREGUNTA} segundos**.")

        if st.session_state.es_croma:
            tab_examenes, tab_admin_manual, tab_admin_resultados, tab_admin_export, tab_admin_analisis, tab_admin_informes_ia, tab_admin_gestion, tab_admin_trimestrales = st.tabs([
                "📝 Realizar Examen",
                "📄 Cargar Manual / Prompt", 
                "📊 Resultados / Edición", 
                "📥 Exportación Exámenes e Importación Datos",
                "📈 Analítica e IA",
                "🤖 Informes IA",
                "⚙️ Gestión y Configuración",
                "📋 Evaluaciones Trimestrales"
            ])
        else:
            tab_examenes, tab_mis_resultados, tab_mi_analisis, tab_mis_trimestrales = st.tabs([
                "📝 Realizar Examen", 
                "📊 Mis Resultados e Historial",
                "📈 Mi Rendimiento e Informes IA",
                "📋 Evaluaciones Trimestrales"
            ])

        # TAB: EVALUACIONES TRIMESTRALES
        if st.session_state.es_croma:
            with tab_admin_trimestrales:
                render_admin_evaluaciones_trimestrales()
        else:
            with tab_mis_trimestrales:
                render_empleado_evaluaciones_trimestrales(st.session_state.user_id, st.session_state.user_nombre)

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
                    num_p_global = NUM_PREG_GLOBAL
                    st.info(f"El Examen Global seleccionará exactamente **{num_p_global} preguntas aleatorias** distribuidas equitativamente entre los manuales.")
                    
                    texto_global_bd = TEXTO_EXAMEN_GLOBAL_INFO
                    try:
                        res_info_g = supabase.table("config_prompts").select("valor").eq("nombre", "info_examen_global").limit(1).execute()
                        if res_info_g.data and res_info_g.data[0].get("valor"):
                            texto_global_bd = res_info_g.data[0]["valor"]
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
                        st.session_state.tiempo_limite_examen_actual = len(preguntas_preparadas) * TIEMPO_LIMITE_PREGUNTA
                        st.session_state.tiempo_examen_agotado = False
                        st.session_state.tiempo_inicio_pregunta = None
                        st.session_state.tiempo_inicio_revision = None
                        st.session_state.comodines_restantes = 3
                        st.session_state.pistas_activadas = set()
                        st.session_state.sobrepaso_tiempo_global = False
                        st.session_state.examen_finalizado = False
                        
                        # Registrar inicio en la base de datos
                        registrar_inicio_examen_bd("GLOBAL COMPLETO", None)
                        
                        st.session_state.examen_activo = True
                        st.rerun()

                with tab_manual:
                    st.subheader("📘 Manuales y Exámenes Disponibles")
                    num_p_manual = NUM_PREG_MANUAL
                    
                    cols = st.columns(3)
                    for idx_ex, ex_obj in enumerate(examenes_disponibles):
                        nombre_apt = ex_obj['apartado']
                        num_p_totales = len(ex_obj.get("preguntas_json", [])) if isinstance(ex_obj.get("preguntas_json"), list) else 0

                        ya_hecho_manual = nombre_apt in dict_realizados
                        permitido_manual = autorizaciones_set.__contains__(nombre_apt)
                        bloqueado_manual = ya_hecho_manual and not permitido_manual and not st.session_state.es_croma

                        with cols[idx_ex % 3]:
                            st.markdown(f"""
                            <div class="manual-card">
                                <div>
                                    <h4>📘 {nombre_apt}</h4>
                                    <p><b>Banco de preguntas:</b> {num_p_totales} totales<br>
                                    <b>Preguntas en examen:</b> {num_p_manual}</p>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                            if ya_hecho_manual:
                                info_m = dict_realizados[nombre_apt]
                                est_txt = obtener_estado_evaluacion(info_m['porcentaje'])
                                st.caption(f"⚠️ **Realizado este mes:** {info_m['nota']}/10 ({est_txt})")

                            if st.button(f"Iniciar Examen", key=f"btn_card_manual_{ex_obj['id']}", disabled=bloqueado_manual, use_container_width=True):
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
                                st.session_state.tiempo_limite_examen_actual = len(preguntas_preparadas) * TIEMPO_LIMITE_PREGUNTA
                                st.session_state.tiempo_examen_agotado = False
                                st.session_state.tiempo_inicio_pregunta = None
                                st.session_state.tiempo_inicio_revision = None
                                st.session_state.comodines_restantes = 3
                                st.session_state.pistas_activadas = set()
                                st.session_state.sobrepaso_tiempo_global = False
                                st.session_state.examen_finalizado = False
                                
                                # Registrar inicio en la base de datos
                                registrar_inicio_examen_bd(nombre_apt, ex_obj["id"])

                                st.session_state.examen_activo = True
                                st.rerun()

                    # Estadísticas de soporte técnico
                    manual_nombres = [ex['apartado'] for ex in examenes_disponibles]
                    st.markdown("---")
                    st.subheader("📊 Histórico del Trabajador por Manual")
                    manual_sel_nom = st.selectbox("Selecciona un manual para ver tu histórico:", manual_nombres, key="sel_manual_eval_stats")
                    ex_obj_stats = next((ex for ex in examenes_disponibles if ex['apartado'] == manual_sel_nom), None)
                    
                    if ex_obj_stats:
                        nombre_apt_stat = ex_obj_stats['apartado']
                        res_intentos_m = supabase.table("intentos_examen").select("*")\
                            .eq("empleado_id", st.session_state.user_id)\
                            .eq("apartado", nombre_apt_stat)\
                            .eq("activo", True)\
                            .order("fecha_inicio", desc=True).execute()
                        intentos_m = res_intentos_m.data if res_intentos_m.data else []

                        if intentos_m:
                            banco_actual_m = ex_obj_stats.get("preguntas_json", [])
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

                prompt_defecto_cargador = cfg_prompt_ex.get("valor") if cfg_prompt_ex and cfg_prompt_ex.get("valor") else PROMPT_DEFECTO_EXAMEN

                with st.form("form_cargar_manual", clear_on_submit=False):
                    nombre_apartado = st.text_input("📘 Nombre del Manual/Apartado (Ej. Manual Seguridad 2026):*")
                    pdf_file = st.file_uploader("📂 Selecciona el documento PDF:*", type=["pdf"])
                    
                    prompt_manual_input = st.text_area(
                        "💬 Prompt para la IA (Generación de JSON):",
                        value=prompt_defecto_cargador,
                        height=200
                    )
                    
                    guardar_prompt_check = st.checkbox("💾 Actualizar y guardar este prompt en la base de datos como predeterminado")
                    
                    modelos_ia_opciones = obtener_modelos_ia_disponibles()
                    modelos_cargador_sel = st.multiselect(
                        "🤖 Selección múltiple de modelos de IA a consultar (Se unificarán los JSON):", 
                        options=modelos_ia_opciones, 
                        default=[modelos_ia_opciones[0]] if modelos_ia_opciones else []
                    )
                    
                    btn_procesar_manual = st.form_submit_button("🚀 Procesar Documento y Guardar Examen", use_container_width=True)

                if btn_procesar_manual:
                    if not nombre_apartado.strip():
                        st.error("❌ Por favor indica el nombre del manual/apartado.")
                    elif not pdf_file:
                        st.error("❌ Por favor sube un archivo PDF válido.")
                    elif not modelos_cargador_sel:
                        st.error("❌ Por favor selecciona al menos un modelo de IA.")
                    else:
                        if guardar_prompt_check:
                            guardar_prompt_config("prompt_examen", prompt_manual_input)

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

                            preguntas_unificadas = []

                            for mod_sel in modelos_cargador_sel:
                                status_box.write(f"🧠 Consultando al modelo {mod_sel}...")
                                prompt_final = f"{prompt_manual_input}\n\n[CONTENIDO DEL DOCUMENTO PDF]:\n{texto_pdf[:40000]}"
                                
                                try:
                                    res_ia_raw = consultar_ia(mod_sel, prompt_final, sistema="Eres un generador de exámenes técnicos estructurados exclusivamente en formato JSON.")
                                    txt_json = res_ia_raw.strip()
                                    if "```json" in txt_json:
                                        txt_json = txt_json.split("```json")[1].split("```")[0].strip()
                                    elif "```" in txt_json:
                                        txt_json = txt_json.split("```")[1].split("```")[0].strip()

                                    parsed_json = json.loads(txt_json)
                                    if isinstance(parsed_json, list):
                                        for item in parsed_json:
                                            p_norm = normalizar_pregunta_json(item)
                                            if p_norm and p_norm not in preguntas_unificadas:
                                                preguntas_unificadas.append(p_norm)
                                except Exception as err_model:
                                    status_box.write(f"⚠️ Error parcial al consultar con {mod_sel}: {err_model}")

                            if not preguntas_unificadas:
                                raise Exception("No se generaron preguntas válidas a partir del documento.")

                            status_box.write(f"💾 Registrando examen con {len(preguntas_unificadas)} preguntas unificadas en Supabase...")
                            
                            registro_nuevo_examen = {
                                "apartado": nombre_apartado.strip(),
                                "preguntas_json": preguntas_unificadas,
                                "activo": True
                            }
                            
                            supabase.table("examenes").insert(registro_nuevo_examen).execute()
                            
                            status_box.update(label="✅ ¡Manual procesado y unificado con éxito!", state="complete", expanded=False)
                            st.success(f"🎉 Se han generado exitosamente **{len(preguntas_unificadas)} preguntas unificadas** en un solo JSON para el manual **{nombre_apartado.strip()}**.")
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
                st.subheader("📈 Mi Rendimiento Personal e Informe IA")

                # Verificar si el usuario actual tiene habilitado el análisis por IA
                res_usr_cfg = supabase.table("empleados").select("analisis_ia_habilitado").eq("id", st.session_state.user_id).execute()
                ia_permitida = res_usr_cfg.data[0].get("analisis_ia_habilitado", True) if res_usr_cfg.data else True

                if not ia_permitida:
                    st.warning("🔒 La generación y visualización de Análisis por IA ha sido deshabilitada para tu usuario por el administrador.")
                else:
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
                        
                    st.markdown("---")
                    st.markdown("#### 📄 Informe Profesional de Evaluación IA (Año Vigente)")
                    
                    anio_vigente = datetime.datetime.now().year
                    
                    res_mi_an = supabase.table("analisis_ia_empleados").select("*")\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("anio", anio_vigente)\
                        .eq("activo", True)\
                        .order("fecha_generacion", desc=True)\
                        .limit(1).execute()
                    
                    if res_mi_an.data:
                        info_eval_db = res_mi_an.data[0]
                        txt_eval = info_eval_db["analisis_texto"]
                        mod_usado = info_eval_db.get("modelo_ia", "IA")
                        fecha_gen = info_eval_db.get("fecha_generacion", "")[:10]
                        
                        st.caption(f"🤖 Evaluado con: **{mod_usado}** | Fecha de informe: **{fecha_gen}** | Año: **{anio_vigente}**")
                        st.info(txt_eval)
                    else:
                        st.warning(f"Aún no hay ningún informe de evaluación guardado y activo para ti en el año {anio_vigente}.")

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
                st.subheader("📥 Exportación Exámenes e Importación Datos")
                
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
                
                # INFORME DE EVALUACIÓN IA (SQL) - ADMINISTRADOR
                st.subheader("📄 Consulta de Informe de Análisis IA por Empleado (SQL)")
                
                try:
                    res_emp_act_exp = supabase.table("empleados").select("id, nombre").eq("activo", True).order("nombre", desc=False).execute()
                    list_emp_exp = res_emp_act_exp.data if res_emp_act_exp.data else []
                except Exception:
                    list_emp_exp = []

                if list_emp_exp:
                    dict_emp_exp = {e["nombre"]: e["id"] for e in list_emp_exp}
                    col_ia_a, col_ia_b = st.columns(2)
                    
                    with col_ia_a:
                        emp_exp_sel_nom = st.selectbox("👥 Seleccionar Empleado:", list(dict_emp_exp.keys()), key="exp_ia_emp_nom")
                    with col_ia_b:
                        anio_defecto = datetime.datetime.now().year
                        anio_exp_ia = st.number_input("📅 Seleccionar Año:", min_value=2020, max_value=2030, value=anio_defecto, key="exp_ia_anio_num")

                    emp_exp_id_val = dict_emp_exp[emp_exp_sel_nom]

                    res_an_sql = supabase.table("analisis_ia_empleados").select("*")\
                        .eq("empleado_id", emp_exp_id_val)\
                        .eq("anio", int(anio_exp_ia))\
                        .order("fecha_generacion", desc=True)\
                        .execute()

                    if res_an_sql.data:
                        informes_disponibles = res_an_sql.data
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("👁️ Mostrar Análisis IA", use_container_width=True, key="btn_toggle_ia_show"):
                                st.session_state.mostrar_analisis_ia_exp = not st.session_state.mostrar_analisis_ia_exp

                        informe_principal = informes_disponibles[0]
                        txt_analisis = informe_principal.get("analisis_texto", "")

                        with col_btn2:
                            pdf_bytes_ia = generar_pdf_evaluacion_ia(emp_exp_sel_nom, txt_analisis, anio_exp_ia)
                            if pdf_bytes_ia:
                                st.download_button(
                                    label="📄 Descargar PDF del Análisis IA",
                                    data=pdf_bytes_ia,
                                    file_name=f"Analisis_IA_{emp_exp_sel_nom.replace(' ', '_')}_{anio_exp_ia}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True,
                                    key="btn_download_pdf_ia_admin"
                                )

                        if st.session_state.mostrar_analisis_ia_exp:
                            st.info(f"**Análisis de Evaluación IA de {emp_exp_sel_nom} ({anio_exp_ia}):**\n\n{txt_analisis}")
                    else:
                        st.warning(f"⚠️ No se encontró ningún informe de Análisis IA generado en SQL para **{emp_exp_sel_nom}** en el año **{anio_exp_ia}**.")
                else:
                    st.warning("No se pudieron cargar los empleados para consultar los informes de IA.")

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

                st.subheader("📄 Cargar Banco de Preguntas desde JSON (Soporta múltiples archivos)")
                nombre_apartado_json = st.text_input("Nombre del Manual / Apartado para este JSON:")
                archivos_json = st.file_uploader("Seleccionar uno o varios archivos JSON con preguntas", type=["json"], accept_multiple_files=True)

                if st.button("🚀 Subir y Unificar Preguntas a Supabase"):
                    if archivos_json and nombre_apartado_json:
                        try:
                            contenido_validado_unificado = []
                            
                            for f_json in archivos_json:
                                raw_json = json.load(f_json)
                                
                                if isinstance(raw_json, dict):
                                    array_preguntas = raw_json.get("bank", raw_json.get("preguntas", []))
                                elif isinstance(raw_json, list):
                                    array_preguntas = raw_json
                                else:
                                    array_preguntas = []

                                if isinstance(array_preguntas, list):
                                    for p in array_preguntas:
                                        preg_normalizada = normalizar_pregunta_json(p)
                                        if preg_normalizada:
                                            contenido_validado_unificado.append(preg_normalizada)

                            if contenido_validado_unificado:
                                supabase.table("examenes").insert({
                                    "apartado": nombre_apartado_json,
                                    "preguntas_json": contenido_validado_unificado,
                                    "activo": True
                                }).execute()
                                
                                st.success(f"✅ ¡Se unificaron y cargaron {len(contenido_validado_unificado)} preguntas en un solo registro SQL correctamente!")
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.error("❌ Los archivos JSON subidos no contienen preguntas válidas.")
                        except Exception as e:
                            st.error(f"❌ Error al procesar y unificar los JSON: {e}")

                st.markdown("---")

        # ADMIN CROMA - ANALÍTICA E IA
        if st.session_state.es_croma and tab_admin_analisis:
            with tab_admin_analisis:
                st.subheader("📈 Analítica Global e Inteligencia Artificial")
                
                try:
                    res_m_counts = supabase.table("examenes").select("id, apartado, preguntas_json, activo").eq("activo", True).execute()
                    if res_m_counts.data:
                        st.markdown("### 📊 Conteo de Preguntas Generadas por Examen/Manual (Solo Activos)")
                        data_counts = []
                        for ex_m in res_m_counts.data:
                            preg_list = ex_m.get("preguntas_json", [])
                            data_counts.append({
                                "ID": ex_m.get("id"),
                                "Manual / Examen": ex_m.get("apartado"),
                                "Preguntas Generadas": len(preg_list) if isinstance(preg_list, list) else 0,
                                "Estado": "Activo"
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

                prompt_defecto_eval = cfg_eval.get("valor") if cfg_eval and cfg_eval.get("valor") else "Analiza los exámenes del empleado y genera una evaluación profesional estructurada."

                st.markdown("### 🤖 Evaluación Múltiple e Informe de Trabajadores")
                
                # Carga de empleados activos
                res_emp_activos_todos = supabase.table("empleados").select("id, nombre").eq("activo", True).execute()
                emp_list_select = res_emp_activos_todos.data if res_emp_activos_todos.data else []
                map_empleados_dict = {e["nombre"]: e["id"] for e in emp_list_select}
                nombres_activos = sorted(list(map_empleados_dict.keys()))

                col_filtro1, col_filtro2 = st.columns(2)
                with col_filtro1:
                    empleados_sel = st.multiselect("👥 Selecciona uno o varios empleados a analizar:", options=nombres_activos, default=nombres_activos[:1] if nombres_activos else [])
                with col_filtro2:
                    anio_actual_def = datetime.datetime.now().year
                    anio_analisis_sel = st.number_input("📅 Año del informe:", min_value=2020, max_value=2030, value=anio_actual_def)

                res_all_examenes = supabase.table("examenes").select("apartado").eq("activo", True).execute()
                examenes_unicos = sorted(list(set([ex["apartado"] for ex in (res_all_examenes.data or [])])))
                examenes_sel = st.multiselect("📘 Selecciona exámenes para restringir el estudio (Opcional):", options=examenes_unicos, default=examenes_unicos)

                modelos_ia_opciones = obtener_modelos_ia_disponibles()
                modelos_estudio_sel = st.multiselect("🤖 Selecciona el modelo de IA a consultar:", options=modelos_ia_opciones, default=[modelos_ia_opciones[0]] if modelos_ia_opciones else [])

                prompt_estudio_input = st.text_area("💬 Prompt de evaluación (Modificable y editable):", value=prompt_defecto_eval, height=120)
                guardar_prompt_eval_check = st.checkbox("💾 Guardar cambios de este prompt en la base de datos (SQL)", key="chk_save_prompt_eval")

                if st.button("🚀 Generar Informe Cualitativo", use_container_width=True):
                    if not empleados_sel:
                        st.error("❌ Por favor selecciona al menos un empleado.")
                    elif not modelos_estudio_sel:
                        st.error("❌ Por favor selecciona al menos un modelo de IA.")
                    else:
                        if guardar_prompt_eval_check:
                            guardar_prompt_config("evaluacion_empleado", prompt_estudio_input)

                        with st.spinner("🔍 Extrayendo exámenes desde SQL y procesando con la IA..."):
                            try:
                                # Filtrar intentos del año seleccionado
                                query = supabase.table("intentos_examen").select("*").eq("activo", True).in_("nombre_empleado", empleados_sel)
                                if examenes_sel:
                                    query = query.in_("apartado", examenes_sel)
                                res_intentos_sql = query.execute()
                                datos_intentos = [it for it in (res_intentos_sql.data or []) if it.get("fecha_inicio") and int(it["fecha_inicio"][:4]) == anio_analisis_sel]

                                if not datos_intentos:
                                    st.warning(f"No se encontraron registros de exámenes en SQL para los empleados y año {anio_analisis_sel} elegidos.")
                                else:
                                    resumen_contexto = json.dumps(datos_intentos, indent=2, ensure_ascii=False)
                                    prompt_completo = f"{prompt_estudio_input}\n\n[DATOS HISTÓRICOS DE EXÁMENES DEL AÑO {anio_analisis_sel}]:\n{resumen_contexto[:35000]}"

                                    st.session_state.eval_resultado_cache = []

                                    for mod in modelos_estudio_sel:
                                        resp_ia = consultar_ia(mod, prompt_completo, sistema="Eres un evaluador profesional en rendimiento y capacitación técnica.")
                                        st.session_state.eval_resultado_cache.append({
                                            "modelo": mod,
                                            "texto": resp_ia,
                                            "prompt": prompt_estudio_input,
                                            "anio": anio_analisis_sel,
                                            "empleados": empleados_sel
                                        })

                            except Exception as e_est:
                                st.error(f"Error generando el estudio con la IA: {e_est}")

                # Renderizar resultados generados si existen en el estado de la sesión
                if st.session_state.get("eval_resultado_cache"):
                    st.markdown("---")
                    st.markdown("### 📋 Resultados Generados por la IA")

                    for item_eval in st.session_state.eval_resultado_cache:
                        mod = item_eval["modelo"]
                        resp_ia = item_eval["texto"]
                        anio_inf = item_eval["anio"]
                        list_emp = item_eval["empleados"]

                        st.markdown(f"#### 🧠 Modelo: `{mod}` | Año: **{anio_inf}**")
                        st.info(resp_ia)

                        c_btn1, c_btn2 = st.columns(2)
                        
                        # Botón 1: Descargar Informe PDF
                        with c_btn1:
                            pdf_exp = generar_pdf_evaluacion_ia(", ".join(list_emp), resp_ia, anio_inf)
                            if pdf_exp:
                                st.download_button(
                                    label=f"📄 Descargar Informe PDF ({mod})",
                                    data=pdf_exp,
                                    file_name=f"Informe_IA_{mod}_{datetime.datetime.now().strftime('%Y%m%d')}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_btn_{mod}",
                                    use_container_width=True
                                )

                        # Botón 2: Guardar en Base de Datos SQL
                        with c_btn2:
                            if st.button(f"💾 Guardar Consulta en SQL para Empleado(s)", key=f"btn_sql_save_{mod}", use_container_width=True):
                                try:
                                    registros_guardados = 0
                                    for emp_nom in list_emp:
                                        emp_id_val = map_empleados_dict.get(emp_nom)
                                        if emp_id_val:
                                            # Insertar en la tabla correspondiente
                                            supabase.table("analisis_ia_empleados").insert({
                                                "empleado_id": emp_id_val,
                                                "nombre_empleado": emp_nom,
                                                "anio": int(anio_inf),
                                                "modelo_ia": mod,
                                                "prompt_utilizado": item_eval["prompt"],
                                                "analisis_texto": resp_ia,
                                                "creado_por": st.session_state.user_nombre
                                            }).execute()
                                            registros_guardados += 1

                                    st.success(f"✅ Informe guardado en SQL exitosamente para {registros_guardados} empleado(s). El usuario ya puede visualizarlo.")
                                except Exception as err_save_sql:
                                    st.error(f"❌ Error al guardar en SQL: {err_save_sql}")

        # ADMIN CROMA - PESTAÑA: GESTIÓN DE INFORMES IA
        if st.session_state.es_croma and tab_admin_informes_ia:
            with tab_admin_informes_ia:
                st.subheader("🤖 Gestión e Informes Generados por IA")
                st.caption(
                    "Consulta, activa o deshabilita la visibilidad de los informes"
                    " almacenados en la base de datos (analisis_ia_empleados)."
                )

                # Obtener la lista de años disponibles en los informes
                res_anios = supabase.table("analisis_ia_empleados").select("anio").execute()
                anios_set = sorted(list(set(item.get("anio") for item in (res_anios.data or []) if item.get("anio"))), reverse=True)
                
                col_f_est, col_f_anio = st.columns([2, 1])

                with col_f_est:
                    filtro_estado_ia = st.radio(
                        "Filtrar informes por estado:",
                        ["Activos", "Deshabilitados", "Todos"],
                        index=0,  # Por defecto Activos
                        horizontal=True,
                        key="f_ia_informes_est",
                    )
                
                with col_f_anio:
                    opciones_anios = ["Todos"] + [str(a) for a in anios_set]
                    filtro_anio_ia = st.selectbox(
                        "Filtrar por año:",
                        options=opciones_anios,
                        index=0,
                        key="f_ia_informes_anio"
                    )

                try:
                    q_ia = supabase.table("analisis_ia_empleados").select("*").order("fecha_generacion", desc=True)

                    if filtro_estado_ia == "Activos":
                        q_ia = q_ia.eq("activo", True)
                    elif filtro_estado_ia == "Deshabilitados":
                        q_ia = q_ia.eq("activo", False)

                    if filtro_anio_ia != "Todos":
                        q_ia = q_ia.eq("anio", int(filtro_anio_ia))

                    res_ia_mng = q_ia.execute()
                    ia_informes_data = res_ia_mng.data if res_ia_mng.data else []

                    if ia_informes_data:
                        for inf in ia_informes_data:
                            inf_id = inf["id"]
                            nombre_emp = inf.get("nombre_empleado", "Desconocido")
                            anio_inf = inf.get("anio", "N/A")
                            mod_ia = inf.get("modelo_ia", "IA")
                            est_activo = inf.get("activo", True)
                            fecha_gen = str(inf.get("fecha_generacion", ""))[:10]

                            label_expander = (
                                f"📄 Informe #{inf_id} | {nombre_emp} | Año: {anio_inf} | Modelo: {mod_ia} "
                                f"({'🟢 Visibilidad Activa' if est_activo else '🔴 Deshabilitado'})"
                            )

                            with st.expander(label_expander):
                                col_txt, col_ctrl = st.columns([3, 1])

                                with col_txt:
                                    st.markdown(
                                        f"**Creado por:** {inf.get('creado_por', 'Sistema')} el `{fecha_gen}`"
                                    )
                                    st.info(inf.get("analisis_texto", "Sin texto disponible."))

                                with col_ctrl:
                                    st.markdown("### ⚙️ Control")
                                    nuevo_est_ia = st.checkbox(
                                        "Mostrar al empleado (Activo)",
                                        value=est_activo,
                                        key=f"chk_ia_inf_{inf_id}",
                                    )

                                    if nuevo_est_ia != est_activo:
                                        try:
                                            supabase.table("analisis_ia_empleados").update(
                                                {"activo": nuevo_est_ia}
                                            ).eq("id", inf_id).execute()

                                            st.success("Estado actualizado correctamente.")
                                            time.sleep(0.5)
                                            st.rerun()
                                        except Exception as err_upd:
                                            st.error(f"Error al actualizar la base de datos: {err_upd}")

                                    pdf_bytes = generar_pdf_evaluacion_ia(
                                        nombre_emp, inf.get("analisis_texto", ""), anio_inf
                                    )
                                    if pdf_bytes:
                                        st.download_button(
                                            label="📄 Descargar PDF",
                                            data=pdf_bytes,
                                            file_name=f"Informe_IA_{nombre_emp}_{anio_inf}.pdf",
                                            mime="application/pdf",
                                            key=f"btn_dl_ia_{inf_id}",
                                            use_container_width=True,
                                        )
                    else:
                        st.info("No se encontraron informes de IA con los filtros seleccionados.")

                except Exception as err_mng_ia:
                    st.error(f"Error al consultar la tabla 'analisis_ia_empleados': {err_mng_ia}")

        # ADMIN CROMA - GESTIÓN Y CONFIGURACIÓN
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Gestión de Usuarios, Manuales, Exámenes y Estado Activo")
                
                tab_g_emp, tab_g_man, tab_g_cfg = st.tabs([
                    "👥 Lista de Empleados Registrados",
                    "📘 Gestión de Manuales y Exámenes Cargados",
                    "⏱️ Configuración de Tiempos y Prompts"
                ])

                # TAB 1: GESTIÓN DE EMPLEADOS
                with tab_g_emp:
                    st.markdown("### 👥 Empleados Registrados")

                    filtro_estado_emp = st.radio(
                        "Filtrar empleados por estado:",
                        ["Activos", "Deshabilitados", "Todos"],
                        index=0,  # Por defecto Activos
                        horizontal=True,
                        key="f_emp_est"
                    )

                    try:
                        q_emp = supabase.table("empleados").select("*").order("nombre", desc=False)
                        if filtro_estado_emp == "Activos":
                            q_emp = q_emp.eq("activo", True)
                        elif filtro_estado_emp == "Deshabilitados":
                            q_emp = q_emp.eq("activo", False)

                        res_emp_mgmt = q_emp.execute()
                        empleados_data = res_emp_mgmt.data if res_emp_mgmt.data else []

                        if empleados_data:
                            for emp in empleados_data:
                                emp_id = emp["id"]
                                emp_nom = emp.get("nombre", "Sin Nombre")
                                emp_act = emp.get("activo", True)
                                emp_admin = emp.get("es_admin_croma", False)
                                emp_ia_hab = emp.get("analisis_ia_habilitado", True)

                                with st.expander(f"👤 {emp_nom} ({'Administrador' if emp_admin else 'Empleado'}) - {'🟢 Activo' if emp_act else '🔴 Deshabilitado'}"):
                                    col_e1, col_e2 = st.columns(2)
                                    correo_actual = emp.get("correo_electronico") or emp.get("email") or ""
                                    with col_e1:
                                        nuevo_nom = st.text_input("Nombre completo:", value=emp_nom, key=f"emp_nom_in_{emp_id}")
                                        nuevo_correo = st.text_input("Correo electrónico:", value=correo_actual, key=f"emp_email_in_{emp_id}", placeholder="nombre@empresa.com")
                                        chk_act = st.checkbox("Cuenta Activa en Plataforma", value=emp_act, key=f"emp_act_chk_{emp_id}")
                                    with col_e2:
                                        chk_adm = st.checkbox("Es Administrador CROMA", value=emp_admin, key=f"emp_adm_chk_{emp_id}")
                                        chk_ia_hab = st.checkbox("Permitir Análisis IA a este usuario", value=emp_ia_hab, key=f"emp_ia_chk_{emp_id}")

                                    if st.button("💾 Guardar Cambios de Empleado", key=f"btn_save_emp_{emp_id}"):
                                        try:
                                            supabase.table("empleados").update({
                                                "nombre": nuevo_nom.strip(),
                                                "correo_electronico": nuevo_correo.strip() or None,
                                                "activo": chk_act,
                                                "es_admin_croma": chk_adm,
                                                "analisis_ia_habilitado": chk_ia_hab
                                            }).eq("id", emp_id).execute()
                                            st.success("✅ Cambios actualizados correctamente.")
                                            time.sleep(0.5)
                                            st.rerun()
                                        except Exception as err_u_e:
                                            st.error(f"Error actualizando usuario: {err_u_e}")
                        else:
                            st.info("No se encontraron empleados registrados con el filtro seleccionado.")

                    except Exception as err_emp_m:
                        st.error(f"Error consultando empleados: {err_emp_m}")

                # TAB 2: GESTIÓN DE MANUALES
                with tab_g_man:
                    st.markdown("### 📘 Manuales y Bancos de Preguntas")

                    filtro_estado_man = st.radio(
                        "Filtrar manuales por estado:",
                        ["Activos", "Deshabilitados", "Todos"],
                        index=0,  # Por defecto Activos
                        horizontal=True,
                        key="f_man_est"
                    )

                    try:
                        q_man = supabase.table("examenes").select("*").order("id", desc=True)
                        if filtro_estado_man == "Activos":
                            q_man = q_man.eq("activo", True)
                        elif filtro_estado_man == "Deshabilitados":
                            q_man = q_man.eq("activo", False)

                        res_ex_mgmt = q_man.execute()
                        examenes_mng_data = res_ex_mgmt.data if res_ex_mgmt.data else []

                        if examenes_mng_data:
                            for ex_m in examenes_mng_data:
                                ex_id = ex_m["id"]
                                apt_nom = ex_m.get("apartado", "Sin Nombre")
                                act_status = ex_m.get("activo", True)
                                pregs_json_val = ex_m.get("preguntas_json", [])
                                num_p_tot = len(pregs_json_val) if isinstance(pregs_json_val, list) else 0

                                label_man = f"📘 Examen/Manual #{ex_id}: {apt_nom} ({num_p_tot} preguntas) - {'🟢 Activo' if act_status else '🔴 Deshabilitado'}"

                                with st.expander(label_man):
                                    nuevo_apt = st.text_input("Nombre del Manual / Apartado:", value=apt_nom, key=f"ex_apt_in_{ex_id}")
                                    chk_man_act = st.checkbox("Manual Activo en Plataforma", value=act_status, key=f"ex_act_chk_{ex_id}")

                                    col_m1, col_m2 = st.columns(2)
                                    with col_m1:
                                        if st.button("💾 Guardar Cambios de Manual", key=f"btn_save_ex_{ex_id}"):
                                            try:
                                                supabase.table("examenes").update({
                                                    "apartado": nuevo_apt.strip(),
                                                    "activo": chk_man_act
                                                }).eq("id", ex_id).execute()
                                                st.success("✅ Manual actualizado correctamente.")
                                                time.sleep(0.5)
                                                st.rerun()
                                            except Exception as err_u_m:
                                                st.error(f"Error actualizando manual: {err_u_m}")
                                    with col_m2:
                                        if st.button("🗑️ Eliminar Examen Permanentemente", key=f"btn_del_ex_{ex_id}"):
                                            try:
                                                supabase.table("examenes").delete().eq("id", ex_id).execute()
                                                st.warning("⚠️ Examen eliminado de la base de datos.")
                                                time.sleep(0.5)
                                                st.rerun()
                                            except Exception as err_d_m:
                                                st.error(f"Error eliminando manual: {err_d_m}")
                        else:
                            st.info("No se encontraron manuales con el filtro seleccionado.")

                    except Exception as err_man_m:
                        st.error(f"Error consultando manuales: {err_man_m}")

# ADMIN CROMA - PESTAÑA: GESTIÓN Y CONFIGURACIÓN
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Gestión y Configuración del Sistema")
                
                subtab_tiempos_prompts, subtab_autorizaciones, subtab_empleados = st.tabs([
                    "⏱️ Tiempos y Prompts / Modelos IA", 
                    "🔑 Autorizaciones de Examen",
                    "👥 Gestión de Empleados"
                ])

                # TAB 3: CONFIGURACIÓN DE TIEMPOS Y PROMPTS (Y MODELOS IA)
                with subtab_tiempos_prompts:
                    st.markdown("### ⏱️ Configuración de Tiempos y Preguntas")
                    
                    with st.form("form_config_tiempos_preguntas"):
                        col_t1, col_t2, col_t3 = st.columns(3)
                        with col_t1:
                            nuevo_tiempo_seg = st.number_input(
                                "⏱️ Tiempo por pregunta (segundos):", 
                                min_value=10, max_value=300, 
                                value=TIEMPO_LIMITE_PREGUNTA
                            )
                        with col_t2:
                            nuevo_num_global = st.number_input(
                                "🌐 N.º Preguntas Examen Global:", 
                                min_value=1, max_value=100, 
                                value=NUM_PREG_GLOBAL
                            )
                        with col_t3:
                            nuevo_num_manual = st.number_input(
                                "📘 N.º Preguntas Examen Manual:", 
                                min_value=1, max_value=100, 
                                value=NUM_PREG_MANUAL
                            )
                        
                        btn_guardar_tiempos = st.form_submit_button("💾 Guardar Tiempos y Parámetros")
                        
                        if btn_guardar_tiempos:
                            ok_t = guardar_tiempo_pregunta_config(nuevo_tiempo_seg)
                            ok_g = guardar_num_preguntas_config("global", nuevo_num_global)
                            ok_m = guardar_num_preguntas_config("manual", nuevo_num_manual)
                            if ok_t and ok_g and ok_m:
                                st.success("✅ Configuración de tiempos y número de preguntas actualizada correctamente.")
                                time.sleep(1)
                                st.rerun()

                    st.markdown("---")
                    st.markdown("### 🤖 Configuración de Modelos de IA")
                    st.caption("Modifica los modelos disponibles por proveedor. Puedes introducir varios modelos separados por comas.")

                    # Cargar los valores actuales de los modelos desde la tabla config_prompts
                    modelos_gemini_val = "gemini-2.5-pro, gemini-2.5-flash"
                    modelos_claude_val = "claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022"
                    modelos_openai_val = "gpt-4o, gpt-4o-mini"
                    config_prompts_id = None

                    try:
                        res_cfg_modelos = supabase.table("config_prompts").select("id, modelo_gemini, modelo_claude, modelo_openai").execute()
                        if res_cfg_modelos.data:
                            # Tomamos el primer registro existente con configuración de modelos
                            fila_cfg = res_cfg_modelos.data[0]
                            config_prompts_id = fila_cfg.get("id")
                            if fila_cfg.get("modelo_gemini"):
                                modelos_gemini_val = fila_cfg["modelo_gemini"]
                            if fila_cfg.get("modelo_claude"):
                                modelos_claude_val = fila_cfg["modelo_claude"]
                            if fila_cfg.get("modelo_openai"):
                                modelos_openai_val = fila_cfg["modelo_openai"]
                    except Exception as e_cfg:
                        st.warning(f"No se pudieron cargar los modelos actuales: {e_cfg}")

                    with st.form("form_config_modelos_ia"):
                        input_gemini = st.text_input("💎 Modelos Gemini (modelo_gemini):", value=modelos_gemini_val)
                        input_claude = st.text_input("🧠 Modelos Claude / Anthropic (modelo_claude):", value=modelos_claude_val)
                        input_openai = st.text_input("⚡ Modelos OpenAI (modelo_openai):", value=modelos_openai_val)

                        btn_guardar_modelos = st.form_submit_button("💾 Guardar Configuración de Modelos IA", use_container_width=True)

                        if btn_guardar_modelos:
                            try:
                                datos_actualizacion = {
                                    "modelo_gemini": input_gemini.strip(),
                                    "modelo_claude": input_claude.strip(),
                                    "modelo_openai": input_openai.strip()
                                }
                                
                                if config_prompts_id:
                                    # Actualizar registro existente
                                    supabase.table("config_prompts").update(datos_actualizacion).eq("id", config_prompts_id).execute()
                                else:
                                    # Insertar uno nuevo si la tabla está vacía
                                    supabase.table("config_prompts").insert(datos_actualizacion).execute()

                                st.success("✅ Modelos de IA actualizados correctamente en la base de datos.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as err_m_save:
                                st.error(f"❌ Error al guardar los modelos de IA: {err_m_save}")

                    st.markdown("---")
                    st.markdown("### 💬 Prompts Predeterminados del Sistema")
                    
                    # Cargar Prompts Actuales
                    prompt_actual_examen = PROMPT_DEFECTO_EXAMEN
                    prompt_actual_eval = "Analiza los exámenes del empleado y genera una evaluación profesional estructurada."
                    
                    try:
                        res_p1 = supabase.table("config_prompts").select("valor").eq("nombre", "prompt_examen").limit(1).execute()
                        if res_p1.data and res_p1.data[0].get("valor"):
                            prompt_actual_examen = res_p1.data[0]["valor"]
                            
                        res_p2 = supabase.table("config_prompts").select("valor").eq("nombre", "evaluacion_empleado").limit(1).execute()
                        if res_p2.data and res_p2.data[0].get("valor"):
                            prompt_actual_eval = res_p2.data[0]["valor"]
                    except Exception:
                        pass

                    with st.form("form_prompts_sistema"):
                        p_examen_val = st.text_area("📄 Prompt por defecto para Generación de Exámenes:", value=prompt_actual_examen, height=180)
                        p_eval_val = st.text_area("📈 Prompt por defecto para Evaluación de Empleados con IA:", value=prompt_actual_eval, height=140)
                        
                        btn_guardar_prompts = st.form_submit_button("💾 Guardar Prompts Predeterminados")
                        
                        if btn_guardar_prompts:
                            ok_p1 = guardar_prompt_config("prompt_examen", p_examen_val)
                            ok_p2 = guardar_prompt_config("evaluacion_empleado", p_eval_val)
                            if ok_p1 and ok_p2:
                                st.success("✅ Prompts del sistema actualizados correctamente.")
                                time.sleep(1)
                                st.rerun()
