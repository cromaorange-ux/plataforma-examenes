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
    "Conocimientos",
    "Evaluacion"
]

CONFIG_APARTADOS = {
    "Tareas realizar por turnos y todos los turnos": {
        "max_punt": 3.0,
        "subapartados": [
            "Turno mañana",
            "Turno Fin de semana Mañana",
            "Turno Tarde",
            "Turno Noche",
            "Turno Fin de semana Noche",
            "Todos los turnos"
        ]
    },
    "Tiempos respuesta Tbox": {
        "max_punt": 3.0,
        "subapartados": [
            "% menos de 1 %",
            "tiempo mas de 20 minutos",
            "Numero alarmas mas de 15 minutos (inferior a 10)"
        ]
    },
    "Tiempos respuesta Siemens": {
        "max_punt": 3.0,
        "subapartados": [
            "% menos de 1 %",
            "tiempo mas de 20 minutos",
            "Numero alarmas mas de 15 minutos (inferior a 10)"
        ]
    },
    "Iniciativa / Proactividad ante el trabajo": {
        "max_punt": 3.0,
        "subapartados": [
            "Sugerencia de ideas / Mejoras / Realización de tabajos sin indicar nada"
        ]
    },
    "Conocimientos": {
        "max_punt": 1.0,
        "subapartados": [
            "Conocimientos aplicados en puesto trabajo"
        ]
    },
    "Evaluacion": {
        "max_punt": 1.0,
        "subapartados": [
            "Teorica (ANUAL)",
            "Practica (ANUAL)",
            "Herramienta (ANUAL)",
            "Dejar operativo portatil desde 0"
        ]
    }
}

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
                    max_p = CONFIG_APARTADOS.get(seccion_actual, {}).get("max_punt", 3.0)
                    apartados_detallados.append({
                        "seccion": seccion_actual,
                        "tipo": tipo_nombre,
                        "valor_c": num_val,
                        "max_puntuacion": max_p,
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
                "📥 Exportar / Informes",
                "📈 Análisis Comparativo",
                "🤖 Informes de Evaluaciones e IA",
                "⚙️ Gestión y Configuración"
            ])
        else:
            tab_examenes = st.container()
            tab_evaluaciones_trim = None
            tab_admin_manual = None
            tab_admin_resultados = None
            tab_admin_export = None
            tab_admin_analisis = None
            tab_admin_informes_ia = None
            tab_admin_gestion = None

        # ---------------------------------------------------------
        # PESTAÑA: REALIZAR EXAMEN
        # ---------------------------------------------------------
        with tab_examenes:
            st.subheader("📋 Selecciona un Examen Disponible")

            res_aut = supabase.table("autorizaciones_examen").select("apartado")\
                .eq("empleado_id", st.session_state.user_id).execute() if supabase else None
            apartados_autorizados = [r["apartado"] for r in res_aut.data] if res_aut and res_aut.data else []

            res_manuales = supabase.table("examenes").select("*").eq("activo", True).execute() if supabase else None
            manuales_db = res_manuales.data if res_manuales and res_manuales.data else []

            col_g, col_m = st.columns(2)

            with col_g:
                st.markdown("""
                <div class="manual-card">
                    <div>
                        <h4>🌐 EXAMEN GLOBAL COMPLETO</h4>
                        <p>Examen general con preguntas aleatorias e integrales de todos los apartados.</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                res_intentos_glob = supabase.table("intentos_examen").select("id")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("apartado", "GLOBAL COMPLETO")\
                    .eq("activo", True).execute() if supabase else None
                ya_realizo_global = bool(res_intentos_glob and res_intentos_glob.data)
                
                deshabilitar_global = ya_realizo_global and ("GLOBAL COMPLETO" not in apartados_autorizados)

                if st.button("🚀 Comenzar Examen Global", disabled=deshabilitar_global, use_container_width=True, key="btn_start_global"):
                    todas_preguntas = []
                    for m in manuales_db:
                        pregs_m = m.get("preguntas_json", [])
                        if isinstance(pregs_m, list):
                            for p in pregs_m:
                                norm = normalizar_pregunta_json(p)
                                if norm:
                                    norm["apartado_origen"] = m["apartado"]
                                    todas_preguntas.append(norm)

                    preguntas_sel = seleccionar_preguntas_equilibradas(todas_preguntas, NUM_PREG_GLOBAL)

                    for p in preguntas_sel:
                        ops = list(p["opciones"])
                        c_text = ops[p["respuesta_correcta"]] if p["respuesta_correcta"] < len(ops) else ops[0]
                        random.shuffle(ops)
                        p["opciones_barajadas"] = ops
                        p["respuesta_correcta_texto"] = c_text

                    st.session_state.preguntas_seleccionadas = preguntas_sel
                    st.session_state.indice_pregunta = 0
                    st.session_state.respuestas_detalle = []
                    st.session_state.tiempos_restantes_preguntas = {i: TIEMPO_LIMITE_PREGUNTA for i in range(len(preguntas_sel))}
                    st.session_state.tiempo_inicio_examen = time.time()
                    st.session_state.tiempo_inicio_pregunta = time.time()
                    st.session_state.examen_id = 0
                    st.session_state.apartado_actual = "GLOBAL COMPLETO"
                    st.session_state.comodines_restantes = 3
                    st.session_state.pistas_activadas = set()
                    st.session_state.examen_activo = True
                    st.session_state.modo_revision = False
                    st.session_state.examen_finalizado = False
                    st.rerun()

                if deshabilitar_global:
                    st.caption("🔒 Ya has realizado el examen global. Contacta con el administrador si necesitas habilitar un nuevo intento.")

            with col_m:
                st.markdown("#### 📘 Exámenes Específicos por Manual")
                if manuales_db:
                    for man in manuales_db:
                        apt_nombre = man["apartado"]
                        
                        res_int_m = supabase.table("intentos_examen").select("id")\
                            .eq("empleado_id", st.session_state.user_id)\
                            .eq("apartado", apt_nombre)\
                            .eq("activo", True).execute() if supabase else None
                        ya_realizo_manual = bool(res_int_m and res_int_m.data)
                        
                        deshabilitar_m = ya_realizo_manual and (apt_nombre not in apartados_autorizados)

                        pregs_raw = man.get("preguntas_json", [])
                        cant_p = len(pregs_raw) if isinstance(pregs_raw, list) else 0

                        st.write(f"**{apt_nombre}** ({cant_p} preguntas en banco)")
                        if st.button(f"Iniciar {apt_nombre}", disabled=deshabilitar_m, key=f"btn_man_{man['id']}", use_container_width=True):
                            pregs_norm = []
                            for p in pregs_raw:
                                norm = normalizar_pregunta_json(p)
                                if norm:
                                    norm["apartado_origen"] = apt_nombre
                                    pregs_norm.append(norm)

                            preguntas_sel = seleccionar_preguntas_equilibradas(pregs_norm, NUM_PREG_MANUAL)

                            for p in preguntas_sel:
                                ops = list(p["opciones"])
                                c_text = ops[p["respuesta_correcta"]] if p["respuesta_correcta"] < len(ops) else ops[0]
                                random.shuffle(ops)
                                p["opciones_barajadas"] = ops
                                p["respuesta_correcta_texto"] = c_text

                            st.session_state.preguntas_seleccionadas = preguntas_sel
                            st.session_state.indice_pregunta = 0
                            st.session_state.respuestas_detalle = []
                            st.session_state.tiempos_restantes_preguntas = {i: TIEMPO_LIMITE_PREGUNTA for i in range(len(preguntas_sel))}
                            st.session_state.tiempo_inicio_examen = time.time()
                            st.session_state.tiempo_inicio_pregunta = time.time()
                            st.session_state.examen_id = man["id"]
                            st.session_state.apartado_actual = apt_nombre
                            st.session_state.comodines_restantes = 3
                            st.session_state.pistas_activadas = set()
                            st.session_state.examen_activo = True
                            st.session_state.modo_revision = False
                            st.session_state.examen_finalizado = False
                            st.rerun()

                        if deshabilitar_m:
                            st.caption(f"🔒 Examen '{apt_nombre}' completado previamente.")
                        st.write("---")
                else:
                    st.info("No hay exámenes por manual cargados en el sistema.")

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

                # SUBTAB 1: CARGA Y ACTUALIZACIÓN DE EVALUACIONES TRIMESTRALES
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
                                                "eval_nueva": eval_q,
                                                "subapartados_viejos": reg_viejo.get("datos_completos_json", {}).get("apartados", [])
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

                    # MODAL DE CONFIRMACIÓN DE CAMBIOS
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
                                                "datos_completos_json": {"apartados": ev_n["apartados"]}
                                            }).eq("id", mod_data["reg_id"]).execute()

                                            st.success("✅ Evaluación actualizada correctamente.")
                                            st.session_state.modal_actualizar_q = None
                                            time.sleep(0.5)
                                            st.rerun()
                                    except Exception as err_up_q:
                                        st.error(f"Error al actualizar la evaluación: {err_up_q}")

                            if btn_cancelar_q:
                                st.session_state.modal_actualizar_q = None
                                st.rerun()

        # ---------------------------------------------------------
        # TAB: GESTIÓN Y CONFIGURACIÓN (ADMIN)
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Gestión del Sistema y Parámetros Globales")
                
                tab_g_usr, tab_g_man, tab_g_global = st.tabs([
                    "👥 Gestión de Usuarios", 
                    "📘 Gestión de Manuales", 
                    "⚙️ Parámetros Globales del Sistema"
                ])

                # 1. GESTIÓN DE USUARIOS
                with tab_g_usr:
                    st.markdown("#### Lista y Estado Activo de Empleados")
                    filtro_usr_est = st.radio(
                        "Mostrar Empleados:", 
                        ["Solo Habilitados", "Solo Deshabilitados", "Todos"],
                        horizontal=True,
                        key="filtro_usr_est_radio"
                    )
                    
                    if supabase:
                        query_usr = supabase.table("empleados").select("*").order("nombre")
                        if filtro_usr_est == "Solo Habilitados":
                            query_usr = query_usr.eq("activo", True)
                        elif filtro_usr_est == "Solo Deshabilitados":
                            query_usr = query_usr.eq("activo", False)
                        
                        res_usr_list = query_usr.execute()
                        lista_emp_admin = res_usr_list.data if res_usr_list.data else []
                    else:
                        lista_emp_admin = []

                    if lista_emp_admin:
                        for emp_adm in lista_emp_admin:
                            est_usr_act = bool(emp_adm.get("activo", True))
                            es_admin_role = bool(emp_adm.get("es_admin_croma", False))
                            
                            c_u1, c_u2, c_u3 = st.columns([3, 2, 2])
                            with c_u1:
                                st.write(f"**{emp_adm['nombre']}** ({'Administrador CROMA' if es_admin_role else 'Empleado'})")
                            with c_u2:
                                chk_usr = st.checkbox("Activo / Habilitado", value=est_usr_act, key=f"chk_usr_{emp_adm['id']}")
                                if chk_usr != est_usr_act:
                                    try:
                                        if supabase:
                                            supabase.table("empleados").update({"activo": bool(chk_usr)}).eq("id", emp_adm["id"]).execute()
                                        st.success(f"Estado de {emp_adm['nombre']} actualizado.")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except Exception as err_u_act:
                                        st.error(f"Error actualizando usuario: {err_u_act}")
                            with c_u3:
                                # Habilitar nuevo intento manualmente
                                if st.button("🔓 Habilitar Examen", key=f"btn_hab_usr_{emp_adm['id']}", use_container_width=True):
                                    st.session_state[f"show_hab_modal_{emp_adm['id']}"] = True

                            if st.session_state.get(f"show_hab_modal_{emp_adm['id']}", False):
                                with st.form(key=f"form_hab_aut_{emp_adm['id']}"):
                                    st.caption(f"Autorizar nuevo intento de examen para **{emp_adm['nombre']}**")
                                    
                                    # Cargar apartados/manuales
                                    opciones_apt = ["GLOBAL COMPLETO"]
                                    if supabase:
                                        res_ex_aut = supabase.table("examenes").select("apartado").eq("activo", True).execute()
                                        if res_ex_aut.data:
                                            opciones_apt.extend([e["apartado"] for e in res_ex_aut.data])
                                    
                                    apt_aut_sel = st.selectbox("Selecciona el examen a autorizar:", opciones_apt, key=f"sel_apt_aut_{emp_adm['id']}")
                                    
                                    col_h1, col_h2 = st.columns(2)
                                    with col_h1:
                                        btn_confirm_aut = st.form_submit_button("✅ Conceder Permiso")
                                    with col_h2:
                                        btn_cancel_aut = st.form_submit_button("❌ Cancelar")

                                    if btn_confirm_aut:
                                        try:
                                            if supabase:
                                                supabase.table("autorizaciones_examen").insert({
                                                    "empleado_id": emp_adm["id"],
                                                    "apartado": apt_aut_sel,
                                                    "autorizado_por": st.session_state.user_nombre
                                                }).execute()
                                            st.success(f"✅ Autorización guardada para {apt_aut_sel}.")
                                            st.session_state[f"show_hab_modal_{emp_adm['id']}"] = False
                                            time.sleep(0.5)
                                            st.rerun()
                                        except Exception as err_aut_add:
                                            st.error(f"Error al guardar autorización: {err_aut_add}")

                                    if btn_cancel_aut:
                                        st.session_state[f"show_hab_modal_{emp_adm['id']}"] = False
                                        st.rerun()
                            st.markdown("---")
                    else:
                        st.info("No hay usuarios registrados con el filtro seleccionado.")

                # 2. GESTIÓN DE MANUALES
                with tab_g_man:
                    st.markdown("#### Exámenes y Banco de Preguntas Almacenados")
                    if supabase:
                        res_man_adm = supabase.table("examenes").select("*").order("id", desc=True).execute()
                        lista_manuales_adm = res_man_adm.data if res_man_adm.data else []
                    else:
                        lista_manuales_adm = []

                    if lista_manuales_adm:
                        for ex_m in lista_manuales_adm:
                            st_act_m = bool(ex_m.get("activo", True))
                            num_p_json = len(ex_m.get("preguntas_json", [])) if isinstance(ex_m.get("preguntas_json"), list) else 0

                            with st.expander(f"📘 {ex_m['apartado']} ({num_p_json} preguntas) - Estado: {'🟢 Activo' if st_act_m else '🔴 Inactivo'}"):
                                chk_ex_act = st.checkbox("Examen Activo", value=st_act_m, key=f"chk_ex_m_{ex_m['id']}")
                                if chk_ex_act != st_act_m:
                                    try:
                                        if supabase:
                                            supabase.table("examenes").update({"activo": bool(chk_ex_act)}).eq("id", ex_m["id"]).execute()
                                        st.success("Estado del examen actualizado.")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except Exception as err_m_up:
                                        st.error(f"Error al actualizar examen: {err_m_up}")
                    else:
                        st.info("No hay manuales cargados en la base de datos.")

                # 3. PARÁMETROS GLOBALES DEL SISTEMA
                with tab_g_global:
                    st.markdown("#### Ajuste de Configuración Global")
                    
                    with st.form("form_config_global_tiempos"):
                        st.write("##### Tiempos y Cantidad de Preguntas")
                        tiempo_p_input = st.number_input(
                            "⏱️ Tiempo máximo por pregunta (en segundos):", 
                            min_value=10, 
                            max_value=300, 
                            value=int(TIEMPO_LIMITE_PREGUNTA), 
                            step=5
                        )
                        num_p_glob_input = st.number_input(
                            "🌐 Preguntas en Examen Global:", 
                            min_value=5, 
                            max_value=100, 
                            value=int(NUM_PREG_GLOBAL), 
                            step=1
                        )
                        num_p_man_input = st.number_input(
                            "📘 Preguntas en Examen por Manual:", 
                            min_value=5, 
                            max_value=100, 
                            value=int(NUM_PREG_MANUAL), 
                            step=1
                        )

                        if st.form_submit_button("💾 Guardar Configuración Global"):
                            e1 = guardar_tiempo_pregunta_config(tiempo_p_input)
                            e2 = guardar_num_preguntas_config("global", num_p_glob_input)
                            e3 = guardar_num_preguntas_config("manual", num_p_man_input)
                            
                            if e1 and e2 and e3:
                                st.success("✅ Configuración global actualizada correctamente en SQL.")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error("❌ Ocurrió un error al guardar algunos parámetros.")
