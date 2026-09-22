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
st.set_page_config(page_title="Plataforma de Exámenes y Evaluaciones", layout="wide")

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

    .seccion-naranja {
        background-color: #E65100 !important;
        color: #FFFFFF !important;
        padding: 12px 16px;
        border-radius: 8px;
        font-weight: 700;
        font-size: 16px;
        margin-top: 15px;
        margin-bottom: 10px;
    }

    .subapartado-neutro {
        background-color: #F7FAFC;
        border: 1px solid #E2E8F0;
        padding: 10px 14px;
        border-radius: 6px;
        margin-bottom: 6px;
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

    .manual-card {
        background-color: #FFFFFF !important;
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
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
CLAUDE_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")

os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if (SUPABASE_URL and SUPABASE_KEY) else None

try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
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
        if supabase:
            res = supabase.table("config_tiempos_preguntas").select("tiempos_segundos").order("id", desc=True).limit(1).execute()
            if res.data and res.data[0].get("tiempos_segundos") is not None:
                return int(res.data[0]["tiempos_segundos"])
    except Exception:
        pass
    return 45

def obtener_num_preguntas_config(tipo):
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        if supabase:
            res = supabase.table("config_prompts").select("valor").eq("nombre", clave_nombre).limit(1).execute()
            if res.data and res.data[0].get("valor") is not None:
                return int(res.data[0]["valor"])
    except Exception:
        pass
    return 15 if tipo == "global" else 10

def guardar_tiempo_pregunta_config(nuevo_tiempo):
    try:
        if not supabase: return False
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
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        if not supabase: return False
        res = supabase.table("config_prompts").select("id").eq("nombre", clave_nombre).execute()
        if res.data:
            supabase.table("config_prompts").update({"valor": str(cantidad)}).eq("nombre", clave_nombre).execute()
        else:
            supabase.table("config_prompts").insert({"nombre": clave_nombre, "valor": str(cantidad)}).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar número de preguntas ({tipo}): {e}")
        return False

def obtener_modelos_ia_disponibles():
    try:
        if supabase:
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
    except Exception:
        pass
    return ["gemini-2.5-pro", "gemini-2.5-flash", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]

def guardar_prompt_config(nombre_prompt, nuevo_valor):
    try:
        if not supabase: return False
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

# Estado para actualización condicional de Evaluaciones Trimestrales Excel
if "modal_actualizar_q" not in st.session_state:
    st.session_state.modal_actualizar_q = None

TIEMPO_LIMITE_PREGUNTA = obtener_tiempo_pregunta_config()
NUM_PREG_GLOBAL = obtener_num_preguntas_config("global")
NUM_PREG_MANUAL = obtener_num_preguntas_config("manual")
UMBRAL_APROBADO_PORCENTAJE = 70.0

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

    raise Exception(f"Error procesando la consulta tras intentar con todos los modelos. Último error: {ultimo_error}")

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

# ---------------------------------------------------------
# FUNCIONES AUXILIARES: EVALUACIONES TRIMESTRALES EXCEL
# ---------------------------------------------------------
SECCIONES_TRIMESTRALES_DEFINICION = [
    "Tareas realizar por turnos y todos los turnos",
    "Tiempos respuesta Tbox",
    "Tiempos respuesta Siemens",
    "Iniciativa / Proactividad ante el trabajo",
    "Conocimientos"
]

def procesar_excel_evaluacion_trimestral(file_bytes):
    xls = pd.ExcelFile(file_bytes)
    pestaanas_q = [sheet for sheet in xls.sheet_names if sheet.strip().upper() in ["Q1", "Q2", "Q3", "Q4"]]
    
    if not pestaanas_q:
        raise Exception("El documento no contiene ninguna pestaña nombrada Q1, Q2, Q3 o Q4.")

    resultados = []

    for sheet_name in pestaanas_q:
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        
        nombre_emp = ""
        try:
            val_a8 = df.iloc[7, 0]
            if pd.notna(val_a8):
                nombre_emp = str(val_a8).strip()
        except Exception:
            pass

        anio_val = None
        try:
            val_a10 = df.iloc[9, 0]
            if pd.notna(val_a10):
                import re
                nums = re.findall(r'\b20\d{2}\b', str(val_a10))
                if nums:
                    anio_val = int(nums[0])
                else:
                    anio_val = int(float(val_a10))
        except Exception:
            anio_val = datetime.datetime.now().year

        puntuacion_total = None
        observaciones_texto = ""
        apartados_detallados = []
        seccion_actual = "General"

        for r_idx, row in df.iterrows():
            col_a = str(row[0]).strip() if len(row) > 0 and pd.notna(row[0]) else ""
            col_c = row[2] if len(row) > 2 else None
            col_d = str(row[3]).strip() if len(row) > 3 and pd.notna(row[3]) else ""

            for sec in SECCIONES_TRIMESTRALES_DEFINICION:
                if sec.lower() in col_a.lower():
                    seccion_actual = sec
                    break

            if "puntuacion total" in col_a.lower() or "porciento de puntuacion" in col_a.lower():
                if "puntuacion total" in col_a.lower() and pd.notna(col_c):
                    try:
                        puntuacion_total = float(col_c)
                    except Exception:
                        pass
                continue

            if "observaciones generales:" in col_a.lower() or "observaciones" in col_a.lower():
                obs_candidates = [col_d]
                if r_idx + 1 < len(df):
                    row_next = df.iloc[r_idx + 1]
                    for c in range(len(row_next)):
                        if pd.notna(row_next[c]):
                            obs_candidates.append(str(row_next[c]).strip())
                obs_candidates = [o for o in obs_candidates if o]
                if obs_candidates:
                    observaciones_texto += " ".join(obs_candidates) + " "
                continue

            if pd.notna(col_c):
                try:
                    num_val = float(col_c)
                    tipo_nombre = col_a if col_a else f"Subapartado Fila {r_idx+1}"
                    apartados_detallados.append({
                        "seccion": seccion_actual,
                        "tipo": tipo_nombre,
                        "valor_c": num_val,
                        "comentario_d": col_d,
                        "habilitado": True,
                        "peso": 1.0
                    })
                except ValueError:
                    pass

        resultados.append({
            "trimestre": sheet_name.strip().upper(),
            "empleado_nombre": nombre_emp,
            "anio": anio_val,
            "puntuacion_total": puntuacion_total,
            "observaciones": observaciones_texto.strip(),
            "apartados": apartados_detallados
        })

    return resultados

def calcular_media_trimestral_empleado(evaluaciones_list):
    """
    Saca la media de puntuaciones considerando únicamente trimestres y apartados habilitados.
    Si no hay datos, retorna (None, 0).
    """
    puntuaciones_q = []
    
    for ev in evaluaciones_list:
        if not ev.get("activo", True):
            continue
        
        datos = ev.get("datos_completos_json", {})
        apartados = datos.get("apartados", [])
        
        ap_hab = [a for a in apartados if a.get("habilitado", True)]
        
        if ap_hab:
            suma_pesada = sum(float(a.get("valor_c", 0)) * float(a.get("peso", 1.0)) for a in ap_hab)
            suma_pesos = sum(float(a.get("peso", 1.0)) for a in ap_hab)
            media_q = (suma_pesada / suma_pesos) if suma_pesos > 0 else 0.0
            puntuaciones_q.append(media_q)
        elif ev.get("puntuacion_total") is not None:
            puntuaciones_q.append(float(ev["puntuacion_total"]))

    if not puntuaciones_q:
        return None, 0
    return round(sum(puntuaciones_q) / len(puntuaciones_q), 2), len(puntuaciones_q)

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
            if usuario.get("password_hash") == pwd_input:
                st.session_state.user_id = usuario["id"]
                st.session_state.user_nombre = usuario["nombre"]
                st.session_state.es_croma = usuario.get("es_admin_croma", False)
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta.")

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
        if supabase:
            res_usuarios = supabase.table("empleados").select("*").eq("activo", True).execute()
            lista_usuarios = res_usuarios.data if res_usuarios.data else []
        else:
            lista_usuarios = []
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
            return True
        total_p = len(st.session_state.preguntas_seleccionadas)
        correctas = sum(1 for r in st.session_state.respuestas_detalle if r["es_correcta"])
        porcentaje = round((correctas / total_p) * 100, 2) if total_p > 0 else 0.0
        nota_final = round((correctas / total_p) * 10, 2) if total_p > 0 else 0.0
        
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
            
            if supabase:
                supabase.table("intentos_examen").insert(registro_intento).execute()

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
                if st.button("✅ Confirmar y Entregar Examen Definitivamente", use_container_width=True):
                    if guardar_intento_en_bd():
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
            tiempo_restante = max(0, tiempo_base - tiempo_transcurrido)
            
            renderizar_temporizador_realtime(idx)

            deshabilitar_opciones = (tiempo_restante <= 0)
            if deshabilitar_opciones:
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
            tab_examenes, tab_evaluaciones_trim, tab_admin_manual, tab_admin_resultados, tab_admin_export, tab_admin_analisis, tab_admin_informes_ia, tab_admin_gestion = st.tabs([
                "📝 Realizar Examen",
                "📊 Evaluaciones Trimestrales",
                "📄 Cargar Manual / Prompt", 
                "📊 Resultados / Edición", 
                "📥 Exportación Exámenes e Importación Datos",
                "📈 Analítica e IA",
                "🤖 Informes IA",
                "⚙️ Gestión y Configuración"
            ])
        else:
            tab_examenes, tab_eval_trim_emp, tab_mis_resultados, tab_mi_analisis = st.tabs([
                "📝 Realizar Examen", 
                "📊 Informes Evaluaciones Trimestrales",
                "📊 Mis Resultados e Historial",
                "📈 Mi Rendimiento e Informes IA"
            ])

        # TAB: REALIZAR EXAMEN
        with tab_examenes:
            ahora = datetime.datetime.now(datetime.timezone.utc)
            primer_dia_mes = datetime.datetime(ahora.year, ahora.month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            user_intentos = []
            try:
                if supabase:
                    res_user_intentos = supabase.table("intentos_examen").select("*")\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("activo", True)\
                        .gte("fecha_inicio", primer_dia_mes).execute()
                    user_intentos = res_user_intentos.data if res_user_intentos.data else []
            except Exception:
                try:
                    if supabase:
                        res_fallback = supabase.table("intentos_examen").select("*")\
                            .eq("empleado_id", st.session_state.user_id)\
                            .eq("activo", True).execute()
                        fallback_data = res_fallback.data if res_fallback and hasattr(res_fallback, 'data') else []
                    else:
                        fallback_data = []
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
                if supabase:
                    res_aut = supabase.table("autorizaciones_examen").select("apartado")\
                        .eq("empleado_id", st.session_state.user_id).execute()
                    autorizaciones_set = set(item["apartado"] for item in (res_aut.data or []))
                else:
                    autorizaciones_set = set()
            except Exception:
                autorizaciones_set = set()

            try:
                if supabase:
                    res_examenes = supabase.table("examenes").select("*").eq("activo", True).execute()
                    raw_examenes = res_examenes.data if res_examenes.data else []

                    examenes_disponibles = [
                        ex for ex in raw_examenes 
                        if ex.get("activo") is True or ex.get("activo") is None
                    ]
                else:
                    examenes_disponibles = []
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
                        if supabase:
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
                        st.session_state.tiempo_inicio_pregunta = None
                        st.session_state.tiempo_inicio_revision = None
                        st.session_state.comodines_restantes = 3
                        st.session_state.pistas_activadas = set()
                        st.session_state.sobrepaso_tiempo_global = False
                        st.session_state.examen_finalizado = False
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
                                st.session_state.tiempo_inicio_pregunta = None
                                st.session_state.tiempo_inicio_revision = None
                                st.session_state.comodines_restantes = 3
                                st.session_state.pistas_activadas = set()
                                st.session_state.sobrepaso_tiempo_global = False
                                st.session_state.examen_finalizado = False
                                st.session_state.examen_activo = True
                                st.rerun()

                    # Estadísticas por manual
                    manual_nombres = [ex['apartado'] for ex in examenes_disponibles]
                    st.markdown("---")
                    st.subheader("📊 Histórico del Trabajador por Manual")
                    manual_sel_nom = st.selectbox("Selecciona un manual para ver tu histórico:", manual_nombres, key="sel_manual_eval_stats")
                    ex_obj_stats = next((ex for ex in examenes_disponibles if ex['apartado'] == manual_sel_nom), None)
                    
                    if ex_obj_stats and supabase:
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

        # ---------------------------------------------------------
        # PESTAÑA: EVALUACIONES TRIMESTRALES (ADMINISTRADOR CROMA)
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_evaluaciones_trim:
            with tab_evaluaciones_trim:
                st.subheader("📊 Evaluaciones Trimestrales - Carga y Análisis Excel (Q1 - Q4)")
                
                subtab_upload_q, subtab_edit_q, subtab_reporte_ia = st.tabs([
                    "📤 Cargar Archivo XLSX", 
                    "⚙️ Edición y Ponderación de Apartados", 
                    "🤖 Informes de Evaluaciones e IA"
                ])

                # SUBTAB 1: CARGA DE ARCHIVOS EXCEL (Q1 - Q4)
                with subtab_upload_q:
                    st.markdown("#### Subir Evaluación Excel (Pestañas Q1, Q2, Q3, Q4)")
                    excel_q_file = st.file_uploader("📂 Selecciona el documento Excel (.xlsx):", type=["xlsx"], key="excel_q_uploader")

                    if excel_q_file:
                        if st.button("🚀 Procesar e Importar Evaluaciones Trimestrales", use_container_width=True):
                            try:
                                evaluaciones_extraidas = procesar_excel_evaluacion_trimestral(excel_q_file)
                                
                                res_emp_sql = supabase.table("empleados").select("id, nombre").execute() if supabase else None
                                map_emp_sql = {e["nombre"].strip().lower(): e for e in (res_emp_sql.data if res_emp_sql else [])}

                                for eval_q in evaluaciones_extraidas:
                                    emp_nom = eval_q["empleado_nombre"]
                                    anio_eval = eval_q["anio"]
                                    trim_str = eval_q["trimestre"]

                                    emp_match = map_emp_sql.get(emp_nom.lower())
                                    if not emp_match:
                                        st.error(f"❌ El empleado **'{emp_nom}'** indicado en {trim_str} no existe en la base de datos de Empleados.")
                                        continue

                                    emp_id = emp_match["id"]

                                    res_exist = supabase.table("evaluaciones_trimestrales").select("*")\
                                        .eq("empleado_id", emp_id)\
                                        .eq("anio", anio_eval)\
                                        .eq("trimestre", trim_str).execute() if supabase else None

                                    if res_exist and res_exist.data:
                                        reg_viejo = res_exist.data[0]
                                        p_total_v = reg_viejo.get("puntuacion_total")
                                        p_total_n = eval_q["puntuacion_total"]

                                        if str(p_total_v) != str(p_total_n):
                                            st.warning(f"⚠️ **Detección de Cambio en {trim_str} ({anio_eval}) para {emp_nom}**:")
                                            st.write(f"Valor en BD: **{p_total_v}** ➡️ Nuevo Valor: **{p_total_n}**")
                                            
                                            st.session_state.modal_actualizar_q = {
                                                "reg_id": reg_viejo["id"],
                                                "emp_id": emp_id,
                                                "emp_nom": emp_nom,
                                                "anio": anio_eval,
                                                "trimestre": trim_str,
                                                "p_viejo": p_total_v,
                                                "p_nuevo": p_total_n,
                                                "eval_nueva": eval_q
                                            }
                                        else:
                                            st.info(f"ℹ️ La evaluación para **{emp_nom}** ({trim_str} - {anio_eval}) ya está registrada sin cambios.")
                                    else:
                                        reg_nuevo_q = {
                                            "empleado_id": emp_id,
                                            "nombre_empleado": emp_nom,
                                            "anio": anio_eval,
                                            "trimestre": trim_str,
                                            "puntuacion_total": eval_q["puntuacion_total"],
                                            "observaciones": eval_q["observaciones"],
                                            "activo": True,
                                            "datos_completos_json": {"apartados": eval_q["apartados"]}
                                        }
                                        if supabase:
                                            supabase.table("evaluaciones_trimestrales").insert(reg_nuevo_q).execute()
                                        st.success(f"✅ Se ha grabado exitosamente **{trim_str} ({anio_eval})** para **{emp_nom}**.")

                            except Exception as err_xlsx:
                                st.error(f"❌ Error al procesar el documento Excel: {err_xlsx}")

                    if st.session_state.get("modal_actualizar_q"):
                        st.markdown("---")
                        mod_data = st.session_state.modal_actualizar_q
                        st.subheader(f"🔄 Confirmar Modificación para {mod_data['emp_nom']} ({mod_data['trimestre']} {mod_data['anio']})")

                        with st.form("form_confirmar_cambio_q"):
                            st.write(f"**Puntuación Anterior:** {mod_data['p_viejo']} | **Puntuación Nueva:** {mod_data['p_nuevo']}")
                            persona_mod_q = st.text_input("👤 Nombre de quien realiza la modificación:*", value=st.session_state.user_nombre)
                            motivo_mod_q = st.text_area("📋 Motivo del cambio:*")

                            col_act_1, col_act_2 = st.columns(2)
                            with col_act_1:
                                btn_aceptar_q = st.form_submit_button("✅ Aceptar y Actualizar en SQL")
                            with col_act_2:
                                btn_cancelar_q = st.form_submit_button("❌ Cancelar")

                            if btn_aceptar_q:
                                if not persona_mod_q.strip() or not motivo_mod_q.strip():
                                    st.error("❌ Por favor indica tu nombre y el motivo del cambio.")
                                else:
                                    try:
                                        ev_n = mod_data["eval_nueva"]
                                        if supabase:
                                            supabase.table("evaluaciones_trimestrales").update({
                                                "puntuacion_total": ev_n["puntuacion_total"],
                                                "observaciones": ev_n["observaciones"],
                                                "datos_completos_json": {"apartados": ev_n["apartados"]},
                                                "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                                            }).eq("id", mod_data["reg_id"]).execute()

                                            supabase.table("auditoria_evaluaciones").insert({
                                                "evaluacion_id": mod_data["reg_id"],
                                                "empleado_id": mod_data["emp_id"],
                                                "anio": mod_data["anio"],
                                                "trimestre": mod_data["trimestre"],
                                                "campo_modificado": "puntuacion_total",
                                                "valor_anterior": str(mod_data["p_viejo"]),
                                                "valor_nuevo": str(mod_data["p_nuevo"]),
                                                "usuario_modificador": persona_mod_q.strip(),
                                                "motivo": motivo_mod_q.strip()
                                            }).execute()

                                        st.success("✅ Cambio guardado y auditado con éxito.")
                                        st.session_state.modal_actualizar_q = None
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as err_aud_q:
                                        st.error(f"❌ Error al actualizar datos en SQL: {err_aud_q}")

                            if btn_cancelar_q:
                                st.session_state.modal_actualizar_q = None
                                st.rerun()

                # SUBTAB 2: EDICIÓN, VISIBILIDAD Y PESOS DE APARTADOS
                with subtab_edit_q:
                    st.markdown("#### Configuración, Visibilidad y Ponderación de Apartados")
                    
                    filtro_q_edit = st.radio("Filtro Estado Trimestres:", ["Solo Habilitados", "Solo Deshabilitados", "Todos"], index=0, horizontal=True, key="filtro_q_edit_radio")
                    
                    res_emp_q = supabase.table("empleados").select("id, nombre").eq("activo", True).order("nombre").execute() if supabase else None
                    dict_emp_q = {e["nombre"]: e["id"] for e in (res_emp_q.data if res_emp_q else [])}

                    if dict_emp_q:
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            emp_sel_q_nom = st.selectbox("👥 Seleccionar Empleado:", list(dict_emp_q.keys()), key="sel_emp_q_edit")
                        with col_m2:
                            anio_q_sel = st.number_input("📅 Seleccionar Año:", min_value=2020, max_value=2030, value=datetime.datetime.now().year, key="sel_anio_q_edit")

                        emp_sel_q_id = dict_emp_q[emp_sel_q_nom]

                        query_ev = supabase.table("evaluaciones_trimestrales").select("*").eq("empleado_id", emp_sel_q_id).eq("anio", int(anio_q_sel)) if supabase else None
                        if query_ev:
                            if filtro_q_edit == "Solo Habilitados":
                                query_ev = query_ev.eq("activo", True)
                            elif filtro_q_edit == "Solo Deshabilitados":
                                query_ev = query_ev.eq("activo", False)
                            res_ev_all = query_ev.execute()
                            evals_emp = res_ev_all.data if res_ev_all.data else []
                        else:
                            evals_emp = []

                        if evals_emp:
                            st.write(f"##### Resumen de Qs Registrados en {anio_q_sel}:")
                            
                            for ev in evals_emp:
                                trim_nom = ev["trimestre"]
                                est_act = bool(ev.get("activo", True))
                                p_tot = ev.get("puntuacion_total", "N/A")
                                datos_j = ev.get("datos_completos_json", {})
                                list_ap = datos_j.get("apartados", [])

                                with st.expander(f"{trim_nom} - Puntuación Total: {p_tot} | Estado: {'🟢 Habilitado' if est_act else '🔴 Deshabilitado'}"):
                                    
                                    chk_habil_q = st.checkbox(f"Habilitar {trim_nom} para el cálculo de la media anual", value=est_act, key=f"chk_q_hab_{ev['id']}")
                                    if chk_habil_q != est_act:
                                        try:
                                            if supabase:
                                                supabase.table("evaluaciones_trimestrales").update({"activo": bool(chk_habil_q)}).eq("id", ev["id"]).execute()
                                            st.success(f"Estado de {trim_nom} actualizado correctamente.")
                                            time.sleep(0.5)
                                            st.rerun()
                                        except Exception as err_up_q:
                                            st.error(f"❌ Error al actualizar estado del trimestre: {err_up_q}")

                                    st.write("###### Configuración y Visualización de Apartados:")
                                    
                                    # Ponderación porcentual por apartados principales (Color Naranja)
                                    st.markdown("###### Ponderación de Porcentajes por Sección:")
                                    cols_pct = st.columns(len(SECCIONES_TRIMESTRALES_DEFINICION))
                                    porcentajes_dict = {}
                                    pct_defecto = 100.0 / len(SECCIONES_TRIMESTRALES_DEFINICION)
                                    
                                    for idx_sec, sec_name in enumerate(SECCIONES_TRIMESTRALES_DEFINICION):
                                        with cols_pct[idx_sec]:
                                            pct_val = st.number_input(
                                                f"% {sec_name[:15]}...",
                                                min_value=0.0,
                                                max_value=100.0,
                                                value=pct_defecto,
                                                step=5.0,
                                                key=f"pct_{ev['id']}_{idx_sec}"
                                            )
                                            porcentajes_dict[sec_name] = pct_val
                                            
                                    suma_porcentajes = sum(porcentajes_dict.values())
                                    if round(suma_porcentajes, 1) == 100.0:
                                        st.success(f"📊 Suma Total de Porcentajes: **{suma_porcentajes:.1f}%** (Correcto)")
                                    else:
                                        st.warning(f"⚠️ Suma Total de Porcentajes: **{suma_porcentajes:.1f}%** (Atención: la suma ideal es 100%)")

                                    # Mostrar subapartados agrupados con formato
                                    for sec_name in SECCIONES_TRIMESTRALES_DEFINICION:
                                        st.markdown(f"<div class='seccion-naranja'>📙 Apartado: {sec_name} (Peso: {porcentajes_dict.get(sec_name, 0)}%)</div>", unsafe_allow_html=True)
                                        sub_items = [a for a in list_ap if a.get("seccion", "").lower() == sec_name.lower()]
                                        
                                        if sub_items:
                                            for idx_sub, sub_item in enumerate(sub_items):
                                                val_c = sub_item.get("valor_c", "N/A")
                                                com_d = sub_item.get("comentario_d", "")
                                                nom_tipo = sub_item.get("tipo", f"Subapartado {idx_sub+1}")
                                                
                                                st.markdown(f"""
                                                <div class='subapartado-neutro'>
                                                    <b>Subapartado:</b> {nom_tipo} | <b>Puntuación Columna C:</b> <span style='color: #2B6CB0; font-weight: bold;'>{val_c}</span><br>
                                                    <small style='color: #718096;'>Observación Columna D: {com_d if com_d else 'Sin observación'}</small>
                                                </div>
                                                """, unsafe_allow_html=True)
                                        else:
                                            st.caption("No se detectaron subapartados específicos registrados para esta sección.")

                        # Mostrar Resumen Anual y Media
                        media_calc, num_qs = calcular_media_trimestral_empleado(evals_emp)
                        st.markdown("---")
                        if media_calc is not None:
                            st.metric(f"📈 Resumen Anual Media {anio_q_sel} ({emp_sel_q_nom})", f"{media_calc} / 10", f"Basado en {num_qs} Q(s) habilitado(s)")
                        else:
                            st.info(f"ℹ️ **Resumen Anual {anio_q_sel} ({emp_sel_q_nom}):** Sin datos evaluados o sin trimestres habilitados.")

                # SUBTAB 3: PROMPTS DE EVALUACIÓN E INFORMES IA (ADMIN)
                with subtab_reporte_ia:
                    st.markdown("#### Generación de Informes de Evaluación Experto con IA")
                    
                    res_p_sql = supabase.table("config_prompts_eval").select("*").eq("activo", True).execute() if supabase else None
                    prompts_list = res_p_sql.data if res_p_sql else []

                    prompt_default_text = "Como experto en evaluaciones de empleados de empresa, quiero que me hagas una evaluacion del empleado seleccionado, tanto los datos de este año como los anteriores. Con gráficas, e indicar la media del objetivo corporativo."

                    if not prompts_list and supabase:
                        supabase.table("config_prompts_eval").insert({
                            "nombre": "Evaluación Experto Trimestral",
                            "prompt_texto": prompt_default_text,
                            "modelo_ia": "gemini-2.5-flash",
                            "objetivo_media": 8.0,
                            "activo": True
                        }).execute()
                        res_p_sql = supabase.table("config_prompts_eval").select("*").eq("activo", True).execute()
                        prompts_list = res_p_sql.data or []

                    dict_prompts = {p["nombre"]: p for p in prompts_list} if prompts_list else {"Por Defecto": {"id": 1, "prompt_texto": prompt_default_text, "objetivo_media": 8.0}}
                    p_sel_nom = st.selectbox("💬 Seleccionar Prompt Guardado en SQL:", list(dict_prompts.keys()), key="sel_prompt_eval_q")
                    p_obj_sel = dict_prompts[p_sel_nom]

                    with st.form("form_edit_prompt_q"):
                        texto_prompt_edit = st.text_area("Editar Prompt seleccionado:", value=p_obj_sel.get("prompt_texto", prompt_default_text), height=100)
                        obj_media_input = st.number_input("Media del Objetivo en estas características:", min_value=0.0, max_value=10.0, value=float(p_obj_sel.get("objetivo_media", 8.0)), step=0.1)
                        
                        modelos_opciones = obtener_modelos_ia_disponibles()
                        mod_ia_sel = st.selectbox("IA a consultar:", modelos_opciones, key="mod_eval_q_sel")

                        if st.form_submit_button("💾 Guardar Cambios del Prompt en SQL"):
                            if supabase and p_obj_sel.get("id"):
                                supabase.table("config_prompts_eval").update({
                                    "prompt_texto": texto_prompt_edit,
                                    "objetivo_media": obj_media_input,
                                    "modelo_ia": mod_ia_sel
                                }).eq("id", p_obj_sel["id"]).execute()
                                st.success("Prompt actualizado en SQL.")
                                st.rerun()

                    st.markdown("---")
                    st.write("##### Generar Nuevo Informe Experto para Empleados (Selección Múltiple):")
                    
                    res_emp_act = supabase.table("empleados").select("id, nombre").eq("activo", True).order("nombre").execute() if supabase else None
                    map_emp_act = {e["nombre"]: e["id"] for e in (res_emp_act.data if res_emp_act else [])}

                    if map_emp_act:
                        col_g1, col_g2 = st.columns(2)
                        with col_g1:
                            list_emp_inf_nombres = st.multiselect("👥 Seleccionar Empleado(s):*", list(map_emp_act.keys()), key="inf_q_emp_multiselect")
                        with col_g2:
                            anio_inf_q = st.number_input("Año:", min_value=2020, max_value=2030, value=datetime.datetime.now().year, key="inf_q_anio")

                        modelos_multiselect_ia = st.multiselect("🤖 Seleccionar Modelo(s) de IA a Consultar:*", options=modelos_opciones, default=[modelos_opciones[0]])

                        if st.button("🚀 Generar Evaluación Experto con IA", use_container_width=True):
                            if not list_emp_inf_nombres:
                                st.error("❌ Selecciona al menos un empleado.")
                            elif not modelos_multiselect_ia:
                                st.error("❌ Selecciona al menos un modelo de IA.")
                            else:
                                with st.spinner("Procesando histórico de datos y ejecutando prompt de IA..."):
                                    for emp_inf_nom in list_emp_inf_nombres:
                                        emp_inf_id = map_emp_act[emp_inf_nom]
                                        try:
                                            res_h = supabase.table("evaluaciones_trimestrales").select("*")\
                                                .eq("empleado_id", emp_inf_id).order("anio", desc=True).execute() if supabase else None
                                            datos_historicos = res_h.data if res_h else []

                                            prompt_completo = f"{texto_prompt_edit}\n\n[HISTÓRICO COMPLETO DE EVALUACIONES TRIMESTRALES DE {emp_inf_nom}]:\n{json.dumps(datos_historicos, ensure_ascii=False, indent=2)}"

                                            for mod_ia_target in modelos_multiselect_ia:
                                                resultado_ia = consultar_ia(mod_ia_target, prompt_completo, sistema="Eres un experto en Recursos Humanos y Evaluación de Desempeño Corporativo.")

                                                if supabase:
                                                    supabase.table("resultados_evaluacion_ia").insert({
                                                        "empleado_id": emp_inf_id,
                                                        "nombre_empleado": emp_inf_nom,
                                                        "anio": int(anio_inf_q),
                                                        "prompt_id": p_obj_sel.get("id"),
                                                        "modelo_ia": mod_ia_target,
                                                        "resultado_texto": resultado_ia,
                                                        "activo": True,
                                                        "creado_por": st.session_state.user_nombre
                                                    }).execute()

                                                st.success(f"✅ Evaluación generada ({mod_ia_target}) para **{emp_inf_nom}**.")
                                                st.info(resultado_ia)

                                        except Exception as err_gen_eval:
                                            st.error(f"❌ Error al generar la evaluación para {emp_inf_nom}: {err_gen_eval}")

                    st.markdown("---")
                    st.write("##### Control de Visibilidad de Informes para Empleados:")
                    
                    filtro_visib = st.radio("Mostrar informes:", ["Solo Habilitados", "Solo Deshabilitados", "Todos"], index=0, horizontal=True, key="filtro_vis_inf")
                    
                    if supabase:
                        query_inf = supabase.table("resultados_evaluacion_ia").select("*").order("created_at", desc=True)
                        if filtro_visib == "Solo Habilitados":
                            query_inf = query_inf.eq("activo", True)
                        elif filtro_visib == "Solo Deshabilitados":
                            query_inf = query_inf.eq("activo", False)

                        res_inf_list = query_inf.execute()
                        informes_q_data = res_inf_list.data or []
                    else:
                        informes_q_data = []

                    if informes_q_data:
                        for inf_q in informes_q_data:
                            vis_actual = bool(inf_q.get("activo", True))
                            with st.expander(f"Informe #{inf_q['id']} - {inf_q['nombre_empleado']} ({inf_q['anio']}) | Modelo: {inf_q.get('modelo_ia')} | Visibilidad: {'🟢 Habilitado' if vis_actual else '🔴 Deshabilitado'}"):
                                st.write(inf_q.get("resultado_texto"))
                                chk_vis = st.checkbox("Habilitar para el Empleado", value=vis_actual, key=f"vis_inf_{inf_q['id']}")
                                if chk_vis != vis_actual:
                                    try:
                                        if supabase:
                                            supabase.table("resultados_evaluacion_ia").update({"activo": bool(chk_vis)}).eq("id", inf_q["id"]).execute()
                                        st.success("Visibilidad actualizada.")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except Exception as err_vis:
                                        st.error(f"Error al actualizar visibilidad: {err_vis}")

        # ---------------------------------------------------------
        # PESTAÑA: INFORMES EVALUACIONES TRIMESTRALES (EMPLEADO)
        # ---------------------------------------------------------
        if not st.session_state.es_croma and tab_eval_trim_emp:
            with tab_eval_trim_emp:
                st.subheader("📊 Mis Informes de Evaluaciones Trimestrales")
                
                obj_media_val = 8.0
                try:
                    if supabase:
                        res_obj = supabase.table("config_prompts_eval").select("objetivo_media").eq("activo", True).limit(1).execute()
                        if res_obj.data and res_obj.data[0].get("objetivo_media") is not None:
                            obj_media_val = float(res_obj.data[0]["objetivo_media"])
                except Exception:
                    pass

                st.info(f"🎯 **Media del Objetivo Corporativo:** **{obj_media_val} / 10**")

                anio_actual_emp = datetime.datetime.now().year
                anio_sel_emp = st.number_input("📅 Seleccionar Año de Consulta:", min_value=2020, max_value=2030, value=anio_actual_emp, key="emp_q_anio_sel")

                res_emp_qs = supabase.table("evaluaciones_trimestrales").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("anio", int(anio_sel_emp))\
                    .eq("activo", True).execute() if supabase else None
                mis_evals_q = res_emp_qs.data if res_emp_qs else []

                if mis_evals_q:
                    media_emp, num_q_hab = calcular_media_trimestral_empleado(mis_evals_q)
                    if media_emp is not None:
                        st.metric(f"📈 Mi Media Obtenida ({anio_sel_emp})", f"{media_emp} / 10", f"Basado en {num_q_hab} Q(s) habilitado(s)")
                    else:
                        st.info("Sin datos evaluados en este período.")

                    st.markdown("##### 📋 Desglose de Puntuaciones por Q Registrado:")
                    cols_q = st.columns(4)
                    for idx_q_nom, q_code in enumerate(["Q1", "Q2", "Q3", "Q4"]):
                        q_match = next((item for item in mis_evals_q if item["trimestre"] == q_code), None)
                        with cols_q[idx_q_nom]:
                            if q_match:
                                st.success(f"**{q_code}:** {q_match.get('puntuacion_total', 'N/A')} / 10")
                                if q_match.get("observaciones"):
                                    st.caption(f"💬 *{q_match['observaciones']}*")
                            else:
                                st.warning(f"**{q_code}:** Sin datos")
                else:
                    st.warning(f"No tienes evaluaciones trimestrales registradas o habilitadas para el año {anio_sel_emp}.")

                st.markdown("---")
                st.markdown("##### 📄 Mi Informe de Evaluación Experto:")
                
                res_mi_inf = supabase.table("resultados_evaluacion_ia").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("anio", int(anio_sel_emp))\
                    .eq("activo", True)\
                    .order("created_at", desc=True).execute() if supabase else None
                mis_informes = res_mi_inf.data if res_mi_inf else []

                if mis_informes:
                    inf_principal = mis_informes[0]
                    st.write(f"**Fecha del Informe:** `{inf_principal.get('created_at', '')[:10]}` | **Modelo:** `{inf_principal.get('modelo_ia')}`")
                    st.info(inf_principal.get("resultado_texto"))
                else:
                    st.info(f"No hay ningún informe de evaluación guardado y visible para ti en el año {anio_sel_emp}.")

        # TAB: CARGAR MANUAL Y PROMPT (ADMIN)
        if st.session_state.es_croma and tab_admin_manual:
            with tab_admin_manual:
                st.subheader("📄 Cargar Nuevo Manual en PDF y Generar Examen con IA")
                
                cfg_prompt_ex = None
                try:
                    if supabase:
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
                            
                            if supabase:
                                supabase.table("examenes").insert(registro_nuevo_examen).execute()
                            
                            status_box.update(label="✅ ¡Manual procesado y unificado con éxito!", state="complete", expanded=False)
                            st.success(f"🎉 Se han generado exitosamente **{len(preguntas_unificadas)} preguntas unificadas** en un solo JSON para el manual **{nombre_apartado.strip()}**.")
                            time.sleep(2)
                            st.rerun()

                        except Exception as err_m:
                            status_box.update(label="❌ Error al procesar el manual", state="error", expanded=True)
                            st.error(f"Se produjo un fallo al procesar el documento: {err_m}")

        # TAB: RESULTADOS Y EDICIÓN (ADMIN)
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Resultados de Exámenes y Edición de Respuestas")
                
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    filtro_est_res = st.radio("Mostrar Intentos:", ["Solo Habilitados", "Solo Deshabilitados", "Todos"], index=0, horizontal=True, key="filtro_est_res_radio")
                
                query_res = supabase.table("intentos_examen").select("*").order("fecha_inicio", desc=True) if supabase else None
                if query_res:
                    if filtro_est_res == "Solo Habilitados":
                        query_res = query_res.eq("activo", True)
                    elif filtro_est_res == "Solo Deshabilitados":
                        query_res = query_res.eq("activo", False)
                    res_all_intentos = query_res.execute()
                    todos_intentos = res_all_intentos.data if res_all_intentos.data else []
                else:
                    todos_intentos = []

                if todos_intentos:
                    for it in todos_intentos:
                        est_habil = bool(it.get("activo", True))
                        with st.expander(f"Examen #{it['id']} - {it['nombre_empleado']} | {it['apartado']} | Nota: {it.get('nota')}/10 | Estado: {'🟢 Activo' if est_habil else '🔴 Inactivo'}"):
                            c_a1, c_a2 = st.columns(2)
                            with c_a1:
                                chk_int_act = st.checkbox("Habilitado / Activo", value=est_habil, key=f"chk_int_{it['id']}")
                                if chk_int_act != est_habil:
                                    try:
                                        if supabase:
                                            supabase.table("intentos_examen").update({"activo": bool(chk_int_act)}).eq("id", it["id"]).execute()
                                        st.success("Estado del intento actualizado.")
                                        st.rerun()
                                    except Exception as err_i_up:
                                        st.error(f"Error: {err_i_up}")

                            resp_list = it.get("respuestas_usuario", [])
                            if resp_list:
                                st.write("##### Respuestas Registradas:")
                                for p_idx, r in enumerate(resp_list):
                                    st.write(f"**P{p_idx+1}:** {r.get('pregunta')}")
                                    st.write(f"- Elegida: `{r.get('opcion_elegida')}` | Correcta: `{r.get('respuesta_correcta_texto')}` | Es Correcta: {r.get('es_correcta')}")
                            
                            pdf_b = generar_pdf_resultado(it)
                            if pdf_b:
                                st.download_button("📄 Descargar PDF", pdf_b, file_name=f"resultado_{it['id']}.pdf", mime="application/pdf", key=f"pdf_adm_{it['id']}")

        # TAB: EXPORTACIÓN E IMPORTACIÓN (ADMIN)
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación e Importación de Datos")
                
                st.markdown("#### Exportar Intentos de Examen (CSV / Excel)")
                if st.button("📥 Generar y Descargar CSV de Intentos", use_container_width=True):
                    res_exp = supabase.table("intentos_examen").select("*").execute() if supabase else None
                    if res_exp and res_exp.data:
                        df_exp = pd.DataFrame(res_exp.data)
                        csv_bytes = df_exp.to_csv(index=False).encode('utf-8')
                        st.download_button("💾 Descargar Archivo CSV", csv_bytes, "intentos_examen.csv", "text/csv")
                    else:
                        st.info("No hay datos para exportar.")

        # TAB: ANALÍTICA IA (ADMIN)
        if st.session_state.es_croma and tab_admin_analisis:
            with tab_admin_analisis:
                st.subheader("📈 Analítica Global e Inteligencia Artificial")
                
                res_all_m = supabase.table("intentos_examen").select("*").eq("activo", True).execute() if supabase else None
                if res_all_m and res_all_m.data:
                    df_all_m = pd.DataFrame(res_all_m.data)
                    st.metric("Total de Exámenes Realizados", len(df_all_m))
                    st.metric("Nota Media Global", round(df_all_m["nota"].mean(), 2) if "nota" in df_all_m.columns else 0.0)
                    st.bar_chart(df_all_m["nota"])

        # TAB: INFORMES IA (ADMIN)
        if st.session_state.es_croma and tab_admin_informes_ia:
            with tab_admin_informes_ia:
                st.subheader("🤖 Módulo de Informes IA Generados")
                st.info("Consulte y administre los informes consolidados generados por los distintos modelos de IA.")

        # TAB: GESTIÓN Y CONFIGURACIÓN (ADMIN)
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Gestión del Sistema y Parámetros Globales")
                
                tab_g_usr, tab_g_man, tab_g_global = st.tabs([
                    "👥 Gestión de Usuarios", 
                    "📘 Gestión de Manuales", 
                    "⚙️ Parámetros Globales del Sistema"
                ])

                with tab_g_usr:
                    st.markdown("#### Lista y Estado Activo de Empleados")
                    filtro_usr_est = st.radio("Mostrar Empleados:", ["Solo Habilitados", "Solo Deshabilitados", "Todos"], index=0, horizontal=True, key="filtro_usr_radio")
                    
                    if supabase:
                        query_usr = supabase.table("empleados").select("*").order("nombre")
                        if filtro_usr_est == "Solo Habilitados":
                            query_usr = query_usr.eq("activo", True)
                        elif filtro_usr_est == "Solo Deshabilitados":
                            query_usr = query_usr.eq("activo", False)
                        res_emp_gest = query_usr.execute()
                        emp_list = res_emp_gest.data if res_emp_gest else []
                    else:
                        emp_list = []

                    if emp_list:
                        for emp in emp_list:
                            est_u = bool(emp.get("activo", True))
                            c_u1, c_u2 = st.columns([3, 1])
                            with c_u1:
                                st.write(f"**{emp['nombre']}** ({'Admin' if emp.get('es_admin_croma') else 'Empleado'})")
                            with c_u2:
                                chk_u_act = st.checkbox("Habilitado", value=est_u, key=f"chk_u_{emp['id']}")
                                if chk_u_act != est_u:
                                    try:
                                        if supabase:
                                            supabase.table("empleados").update({"activo": bool(chk_u_act)}).eq("id", emp["id"]).execute()
                                        st.success("Estado actualizado.")
                                        st.rerun()
                                    except Exception as err_u:
                                        st.error(f"Error: {err_u}")

                with tab_g_man:
                    st.markdown("#### Lista y Estado Activo de Manuales / Exámenes")
                    filtro_man_est = st.radio("Mostrar Manuales:", ["Solo Habilitados", "Solo Deshabilitados", "Todos"], index=0, horizontal=True, key="filtro_man_radio")
                    
                    if supabase:
                        query_man = supabase.table("examenes").select("*").order("apartado")
                        if filtro_man_est == "Solo Habilitados":
                            query_man = query_man.eq("activo", True)
                        elif filtro_man_est == "Solo Deshabilitados":
                            query_man = query_man.eq("activo", False)
                        res_man_gest = query_man.execute()
                        man_list = res_man_gest.data if res_man_gest else []
                    else:
                        man_list = []

                    if man_list:
                        for man in man_list:
                            est_m = bool(man.get("activo", True))
                            c_m1, c_m2 = st.columns([3, 1])
                            with c_m1:
                                st.write(f"📘 **{man['apartado']}** ({len(man.get('preguntas_json', []))} preguntas)")
                            with c_m2:
                                chk_m_act = st.checkbox("Habilitado", value=est_m, key=f"chk_m_{man['id']}")
                                if chk_m_act != est_m:
                                    try:
                                        if supabase:
                                            supabase.table("examenes").update({"activo": bool(chk_m_act)}).eq("id", man["id"]).execute()
                                        st.success("Estado actualizado.")
                                        st.rerun()
                                    except Exception as err_m:
                                        st.error(f"Error: {err_m}")

                with tab_g_global:
                    st.markdown("#### Parámetros Globales del Sistema y Prompts Editables")
                    
                    with st.form("form_param_globales"):
                        st.subheader("⏱️ Tiempos y Cantidad de Preguntas por Tipo de Examen")
                        tiempo_seg_in = st.number_input("Tiempo límite por pregunta (segundos):", min_value=10, max_value=300, value=TIEMPO_LIMITE_PREGUNTA, step=5)
                        num_preg_global_in = st.number_input("Número de preguntas en Examen Global:", min_value=5, max_value=50, value=NUM_PREG_GLOBAL, step=1)
                        num_preg_manual_in = st.number_input("Número de preguntas en Examen por Manual:", min_value=5, max_value=50, value=NUM_PREG_MANUAL, step=1)

                        st.subheader("💬 Prompts Generales del Sistema")
                        prompt_def_in = st.text_area("Prompt por defecto para Generación General de Preguntas:", value=PROMPT_DEFECTO, height=150)
                        prompt_ex_in = st.text_area("Prompt por defecto para Generación de Exámenes:", value=PROMPT_DEFECTO_EXAMEN, height=150)

                        if st.form_submit_button("💾 Guardar Parámetros Globales"):
                            guardar_tiempo_pregunta_config(tiempo_seg_in)
                            guardar_num_preguntas_config("global", num_preg_global_in)
                            guardar_num_preguntas_config("manual", num_preg_manual_in)
                            guardar_prompt_config("prompt_defecto", prompt_def_in)
                            guardar_prompt_config("prompt_examen", prompt_ex_in)
                            st.success("✅ Parámetros globales guardados correctamente.")
                            st.rerun()

        # VISTA USUARIO: MIS RESULTADOS Y RENDIMIENTO
        if not st.session_state.es_croma:
            with tab_mis_resultados:
                st.subheader("📌 Mis Calificaciones e Historial Completo")
                
                res_mis_intentos = supabase.table("intentos_examen").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("activo", True)\
                    .order("fecha_inicio", desc=True).execute() if supabase else None
                mis_intentos = res_mis_intentos.data if res_mis_intentos else []
                
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
                            
                            pdf_bytes = generar_pdf_resultado(i)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Descargar Informe PDF de Resultados",
                                    data=pdf_bytes,
                                    file_name=f"resultado_examen_{i['id']}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_usr_{i['id']}"
                                )
                else:
                    st.write("Aún no has realizado ningún examen.")

            with tab_mi_analisis:
                st.subheader("📈 Mi Rendimiento Personal e Informe IA")

                res_usr_cfg = supabase.table("empleados").select("analisis_ia_habilitado").eq("id", st.session_state.user_id).execute() if supabase else None
                ia_permitida = res_usr_cfg.data[0].get("analisis_ia_habilitado", True) if (res_usr_cfg and res_usr_cfg.data) else True

                if not ia_permitida:
                    st.warning("🔒 La generación y visualización de Análisis por IA ha sido deshabilitada para tu usuario por el administrador.")
                else:
                    res_mis_graf = supabase.table("intentos_examen").select("id, nota, porcentaje_obtenido, fecha_inicio, apartado")\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("activo", True)\
                        .order("fecha_inicio", desc=False).execute() if supabase else None
                    mis_datos_graf = res_mis_graf.data if res_mis_graf else []
                    
                    if mis_datos_graf:
                        df_mi_graf = pd.DataFrame(mis_datos_graf)
                        df_mi_graf["fecha"] = df_mi_graf["fecha_inicio"].str[:10]
                        
                        st.markdown("#### 📊 Evolución Histórica de Calificaciones")
                        st.line_chart(df_mi_graf, x="fecha", y="nota")
