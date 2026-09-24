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

# Importar SDK de Anthropic (Claude) - Opcional / Fallback
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
        --text-color: #FFFFFF;
        --border-radius: 12px;
    }

    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        background-color: var(--background-color);
    }

    /* ESTILOS DE RADIO BUTTON PARA OPCIONES EN BLANCO */
    .stRadio label {
        font-size: 16px !important;
        font-weight: 600 !important;
        line-height: 1.4 !important;
        color: #FFFFFF !important;
    }
    
    .stRadio div[role='radiogroup'] {
        gap: 10px;
    }

    .stRadio div[role='radiogroup'] > label {
        background-color: #1A202C !important;
        padding: 14px 18px !important;
        border-radius: 8px !important;
        border: 2px solid #4A5568 !important;
        transition: all 0.2s ease-in-out;
        width: 100%;
        margin-bottom: 8px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }

    .stRadio div[role='radiogroup'] > label p {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }

    .stRadio div[role='radiogroup'] > label:hover {
        background-color: #2D3748 !important;
        border-color: #3182CE !important;
    }

    .pregunta-titulo {
        font-size: 22px !important;
        font-weight: 700 !important;
        color: #FFFFFF;
        margin-bottom: 20px;
        line-height: 1.3;
        padding: 18px;
        background-color: #1A202C;
        border-left: 6px solid #3182CE;
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
# CREDENCIALES Y CLIENTES CONECTIVIDAD
# ---------------------------------------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "")
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
# FUNCIONES AUXILIARES DE CONFIGURACIÓN Y BASE DE DATOS
# ---------------------------------------------------------
def obtener_tiempo_pregunta_config():
    try:
        res = supabase.table("config_tiempos_pregunta").select("tiempo_segundos").order("id", desc=True).limit(1).execute()
        if res.data and res.data[0].get("tiempo_segundos") is not None:
            return int(res.data[0]["tiempo_segundos"])
    except Exception:
        pass
    try:
        res = supabase.table("config_tiempos_preguntas").select("tiempos_segundos").order("id", desc=True).limit(1).execute()
        if res.data and res.data[0].get("tiempos_segundos") is not None:
            return int(res.data[0]["tiempos_segundos"])
    except Exception:
        pass
    return 45

def obtener_num_preguntas_config(tipo):
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        res = supabase.table("config_prompts").select("valor").eq("nombre", clave_nombre).limit(1).execute()
        if res.data and res.data[0].get("valor") is not None:
            return int(res.data[0]["valor"])
    except Exception:
        pass
    return 15 if tipo == "global" else 10

def guardar_tiempo_pregunta_config(nuevo_tiempo):
    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        res = supabase.table("config_tiempos_pregunta").select("id").order("id", desc=True).limit(1).execute()
        if res.data:
            supabase.table("config_tiempos_pregunta").update({
                "tiempo_segundos": int(nuevo_tiempo),
                "updated_at": now_iso
            }).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("config_tiempos_pregunta").insert({
                "tiempo_segundos": int(nuevo_tiempo),
                "created_at": now_iso,
                "updated_at": now_iso
            }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar tiempo por pregunta: {e}")
        return False

def guardar_num_preguntas_config(tipo, cantidad):
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        res = supabase.table("config_prompts").select("nombre").eq("nombre", clave_nombre).execute()
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
        res = supabase.table("modelos_ai").select("nombre_modelo").eq("activo", True).execute()
        if res.data:
            modelos = [r["nombre_modelo"] for r in res.data if r.get("nombre_modelo")]
            if modelos:
                return list(dict.fromkeys(modelos))
    except Exception:
        pass
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
    except Exception:
        pass
    return ["gemini-2.5-pro", "gemini-2.5-flash", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]

def guardar_prompt_config(nombre_prompt, nuevo_valor):
    try:
        res = supabase.table("config_prompts").select("nombre").eq("nombre", nombre_prompt).execute()
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

def registrar_consulta_ia(usuario, modelo, prompt, respuesta):
    try:
        supabase.table("consultas_ia").insert({
            "usuario": usuario,
            "modelo": modelo,
            "prompt": prompt,
            "respuesta": respuesta
        }).execute()
    except Exception:
        pass

def consultar_ia(modelo, prompt, sistema=""):
    modelos_disponibles = obtener_modelos_ia_disponibles()
    cola_modelos = [modelo] + [m for m in modelos_disponibles if m != modelo]
    
    ultimo_error = None
    for mod in cola_modelos:
        try:
            res_txt = ""
            if "claude" in mod.lower():
                if CLAUDE_DISPONIBLE and claude_client:
                    mensaje = claude_client.messages.create(
                        model=mod,
                        max_tokens=4096,
                        system=sistema if sistema else "Eres un asistente experto en análisis de datos y evaluación formativa.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    res_txt = mensaje.content[0].text
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
                    res_txt = res.text
                else:
                    raise Exception(f"Respuesta vacía recibida de Gemini ({mod}).")

            if res_txt:
                registrar_consulta_ia(st.session_state.get("user_nombre", "Sistema"), mod, prompt, res_txt)
                return res_txt
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

    lineas = str(texto_informe).split('\n')
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
            if pwd_input and len(pwd_input) > 0:
                st.session_state.user_id = usuario["id"]
                st.session_state.user_nombre = usuario["nombre"]
                st.session_state.es_croma = usuario.get("es_admin_croma", False)
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("❌ Por favor introduce la contraseña.")

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
# MÓDULO 1: AUTENTICACIÓN DE USUARIO
# ---------------------------------------------------------
st.title("📝 Plataforma Integrada de Evaluación y Exámenes")

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
# MÓDULO 2: PANEL Y EVALUACIÓN PRINCIPAL
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
                "tiempo_limite_segundos": len(st.session_state.preguntas_seleccionadas) * TIEMPO_LIMITE_PREGUNTA,
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
                "tiempo_limite_segundos": tiempo_limite_total,
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

            texto_pregunta = p_actual.get("pregunta", "Pregunta no disponible")
            st.markdown(f"<div class='pregunta-titulo'>{texto_pregunta}</div>", unsafe_allow_html=True)

            resp_previa = next((r["opcion_elegida"] for r in st.session_state.respuestas_detalle if r["idx_pregunta"] == idx), None)
            idx_previa = None
            if resp_previa and resp_previa in p_actual["opciones_barajadas"]:
                idx_previa = p_actual["opciones_barajadas"].index(resp_previa)

            def registrar_respuesta_pregunta(elec_val=None):
                if elec_val is None:
                    elec_val = st.session_state.get(f"p_{idx}")
                
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

            eleccion = st.radio(
                "Selecciona una opción:", 
                p_actual["opciones_barajadas"], 
                index=idx_previa, 
                key=f"p_{idx}",
                disabled=deshabilitar_opciones,
                on_change=registrar_respuesta_pregunta
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
            col_b1, col_b2, col_b3 = st.columns(3)

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

            with col_b3:
                if st.button("🚫 Cancelar Examen (Nota 0)", key=f"btn_canc_{idx}", use_container_width=True):
                    registrar_respuesta_pregunta(eleccion)
                    cancelar_examen_bd()
                    st.session_state.examen_activo = False
                    st.session_state.modo_revision = False
                    st.session_state.examen_finalizado = True
                    st.rerun()

            if tiempo_restante <= 0:
                registrar_respuesta_pregunta(eleccion)

        else:
            st.session_state.modo_revision = True
            st.rerun()

    # MENÚ PRINCIPAL Y PESTAÑAS
    else:
        st.info(f"🎯 **Criterio de Evaluación:** Para obtener un resultado **APROBADO**, debes alcanzar una nota mínima de **{UMBRAL_APROBADO_PORCENTAJE / 10} / 10** ({int(UMBRAL_APROBADO_PORCENTAJE)}% de aciertos). Tiempo configurado por pregunta: **{TIEMPO_LIMITE_PREGUNTA} segundos**.")

        if st.session_state.es_croma:
            tab_examenes, tab_admin_manual, tab_admin_evaluaciones, tab_admin_resultados, tab_admin_export, tab_admin_analisis, tab_admin_informes_ia, tab_admin_gestion = st.tabs([
                "📝 Realizar Examen",
                "📄 Cargar Manual / Prompt", 
                "📋 Evaluaciones Trimestrales",
                "📊 Resultados / Edición", 
                "📥 Exportación e Importación",
                "📈 Analítica e IA",
                "🤖 Informes IA",
                "⚙️ Gestión y Configuración"
            ])
        else:
            tab_examenes, tab_mis_evaluaciones, tab_mis_resultados, tab_mi_analisis = st.tabs([
                "📝 Realizar Examen", 
                "📋 Mis Evaluaciones Trimestrales",
                "📊 Mis Resultados e Historial",
                "📈 Mi Rendimiento e Informes IA"
            ])
            tab_admin_manual = tab_admin_evaluaciones = tab_admin_resultados = tab_admin_export = tab_admin_analisis = tab_admin_informes_ia = tab_admin_gestion = None

        # TAB 1: REALIZAR EXAMEN
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
            except Exception:
                try:
                    res_fallback = supabase.table("intentos_examen").select("*")\
                        .eq("empleado_id", st.session_state.user_id)\
                        .eq("activo", True).execute()
                    fallback_data = res_fallback.data if res_fallback and hasattr(res_fallback, 'data') else []
                    str_mes_actual = f"{ahora.year}-{ahora.month:02d}"
                    user_intentos = [
                        it for it in fallback_data 
                        if it.get("fecha_inicio") and str(it["fecha_inicio"]).startswith(str_mes_actual)
                    ]
                except Exception:
                    user_intentos = []

            dict_realizados = {}
            for it in user_intentos:
                apt = it.get("apartado")
                if apt:
                    dict_realizados[apt] = {
                        "nota": it.get("nota", 0),
                        "porcentaje": it.get("porcentaje_obtenido", 0)
                    }

            try:
                res_examenes = supabase.table("examenes").select("*").eq("activo", True).execute()
                raw_examenes = res_examenes.data if res_examenes.data else []
                examenes_disponibles = [ex for ex in raw_examenes if ex.get("activo") is True or ex.get("activo") is None]
            except Exception as e:
                examenes_disponibles = []
                st.error(f"Error al cargar manuales: {e}")

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
                    bloqueado_global = ya_hecho_global and not st.session_state.es_croma

                    if ya_hecho_global:
                        info_g = dict_realizados["GLOBAL COMPLETO"]
                        est_txt = obtener_estado_evaluacion(info_g['porcentaje'])
                        st.warning(f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{info_g['nota']} / 10** ({info_g['porcentaje']}%) | **{est_txt}**")

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
                        bloqueado_manual = ya_hecho_manual and not st.session_state.es_croma

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
                                
                                registrar_inicio_examen_bd(nombre_apt, ex_obj["id"])
                                st.session_state.examen_activo = True
                                st.rerun()

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
                    prompt_manual_input = st.text_area("💬 Prompt para la IA (Generación de JSON):", value=prompt_defecto_cargador, height=200)
                    guardar_prompt_check = st.checkbox("💾 Actualizar y guardar este prompt como predeterminado")
                    
                    modelos_ia_opciones = obtener_modelos_ia_disponibles()
                    modelos_cargador_sel = st.multiselect("🤖 Modelos de IA a consultar:", options=modelos_ia_opciones, default=[modelos_ia_opciones[0]] if modelos_ia_opciones else [])
                    btn_procesar_manual = st.form_submit_button("🚀 Procesar Documento y Guardar Examen", use_container_width=True)

                if btn_procesar_manual:
                    if not nombre_apartado.strip() or not pdf_file or not modelos_cargador_sel:
                        st.error("❌ Por favor completa todos los campos requeridos.")
                    else:
                        if guardar_prompt_check:
                            guardar_prompt_config("prompt_examen", prompt_manual_input)

                        status_box = st.status("🔄 Procesando manual en el sistema...", expanded=True)
                        try:
                            status_box.write("📖 Extrayendo texto del archivo PDF...")
                            reader = PdfReader(pdf_file)
                            texto_pdf = "".join([page.extract_text() + "\n" for page in reader.pages if page.extract_text()])

                            if not texto_pdf.strip():
                                raise Exception("No se pudo extraer texto del PDF.")

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
                                    status_box.write(f"⚠️ Error parcial con {mod_sel}: {err_model}")

                            if not preguntas_unificadas:
                                raise Exception("No se generaron preguntas válidas.")

                            status_box.write(f"💾 Guardando en Supabase...")
                            supabase.table("examenes").insert({
                                "apartado": nombre_apartado.strip(),
                                "documento_fuente": pdf_file.name,
                                "preguntas_json": preguntas_unificadas,
                                "activo": True
                            }).execute()

                            status_box.update(label="✅ ¡Examen generado y registrado con éxito!", state="complete")
                            st.success(f"🎉 Se han cargado {len(preguntas_unificadas)} preguntas para el manual **{nombre_apartado}**.")
                        except Exception as ex_err:
                            status_box.update(label="❌ Error procesando el manual", state="error")
                            st.error(f"Error: {ex_err}")

        # TAB: EVALUACIONES TRIMESTRALES (ADMIN O VISTA EMPLEADO)
        if st.session_state.es_croma and tab_admin_evaluaciones:
            with tab_admin_evaluaciones:
                st.subheader("📋 Gestión de Evaluaciones Trimestrales")
                try:
                    res_evals = supabase.table("evaluaciones_trimestrales").select("*").eq("activo", True).execute()
                    df_evals = pd.DataFrame(res_evals.data) if res_evals.data else pd.DataFrame()
                    if not df_evals.empty:
                        st.dataframe(df_evals, use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay registros de evaluaciones trimestrales.")
                except Exception as e_ev:
                    st.error(f"Error cargando evaluaciones: {e_ev}")

        elif not st.session_state.es_croma and 'tab_mis_evaluaciones' in locals():
            with tab_mis_evaluaciones:
                st.subheader("📋 Mis Evaluaciones Trimestrales")
                try:
                    res_m_ev = supabase.table("evaluaciones_trimestrales").select("*")\
                        .eq("empleado_id", st.session_state.user_id).eq("activo", True).execute()
                    df_m_ev = pd.DataFrame(res_m_ev.data) if res_m_ev.data else pd.DataFrame()
                    if not df_m_ev.empty:
                        st.dataframe(df_m_ev, use_container_width=True, hide_index=True)
                    else:
                        st.info("No tienes evaluaciones trimestrales registradas.")
                except Exception as e_mev:
                    st.error(f"Error al obtener evaluaciones: {e_mev}")

        # TAB: RESULTADOS / EDICIÓN
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Historial General y Modificación de Intentos")
                try:
                    res_intentos_all = supabase.table("intentos_examen").select("*").eq("activo", True).order("fecha_inicio", desc=True).execute()
                    intentos_all = res_intentos_all.data if res_intentos_all.data else []
                    if intentos_all:
                        df_intentos = pd.DataFrame(intentos_all)
                        st.dataframe(df_intentos[["id", "nombre_empleado", "apartado", "nota", "porcentaje_obtenido", "fecha_inicio"]], use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay intentos registrados.")
                except Exception as e_all:
                    st.error(f"Error cargando intentos: {e_all}")

        elif not st.session_state.es_croma and 'tab_mis_resultados' in locals():
            with tab_mis_resultados:
                st.subheader("📊 Mi Historial de Exámenes")
                try:
                    res_m_int = supabase.table("intentos_examen").select("*")\
                        .eq("empleado_id", st.session_state.user_id).eq("activo", True).order("fecha_inicio", desc=True).execute()
                    m_intentos = res_m_int.data if res_m_int.data else []
                    if m_intentos:
                        df_m_int = pd.DataFrame(m_intentos)
                        st.dataframe(df_m_int[["apartado", "nota", "porcentaje_obtenido", "fecha_inicio", "sobrepasado_tiempo"]], use_container_width=True, hide_index=True)
                    else:
                        st.info("Aún no has realizado ningún examen.")
                except Exception as e_mi:
                    st.error(f"Error cargando tus resultados: {e_mi}")

        # TAB: EXPORTACIÓN E IMPORTACIÓN DATA
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación e Importación de Datos")
                col_exp1, col_exp2 = st.columns(2)
                with col_exp1:
                    st.markdown("#### 📤 Exportar Exámenes")
                    if st.button("Generar Backup JSON de Exámenes", use_container_width=True):
                        res_ex_exp = supabase.table("examenes").select("*").execute()
                        st.download_button("💾 Descargar JSON", data=json.dumps(res_ex_exp.data, indent=2), file_name="backup_examenes.json", mime="application/json")
                with col_exp2:
                    st.markdown("#### 📥 Importar Exámenes")
                    up_json = st.file_uploader("Cargar JSON de exámenes:", type=["json"])
                    if up_json and st.button("Importar a Supabase"):
                        data_imp = json.load(up_json)
                        supabase.table("examenes").insert(data_imp).execute()
                        st.success("Exámenes importados correctamente.")

        # TAB: ANALÍTICA E IA
        if st.session_state.es_croma and tab_admin_analisis:
            with tab_admin_analisis:
                st.subheader("📈 Analítica Global e Informes Generados")
                try:
                    res_an = supabase.table("analisis_ia_empleados").select("*").eq("activo", True).execute()
                    df_an = pd.DataFrame(res_an.data) if res_an.data else pd.DataFrame()
                    if not df_an.empty:
                        st.dataframe(df_an, use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay análisis IA registrados.")
                except Exception as e_an:
                    st.error(f"Error al obtener analítica: {e_an}")

        elif not st.session_state.es_croma and 'tab_mi_analisis' in locals():
            with tab_mi_analisis:
                st.subheader("📈 Mi Rendimiento e Informes IA")
                try:
                    res_m_an = supabase.table("analisis_ia_empleados").select("*")\
                        .eq("empleado_id", st.session_state.user_id).eq("activo", True).execute()
                    df_m_an = pd.DataFrame(res_m_an.data) if res_m_an.data else pd.DataFrame()
                    if not df_m_an.empty:
                        for _, r in df_m_an.iterrows():
                            with st.expander(f"📄 Informe del Año {r.get('anio')} (Modelo: {r.get('modelo_ia')})"):
                                st.write(r.get("analisis_texto"))
                    else:
                        st.info("No dispones de informes de IA generados.")
                except Exception as e_man:
                    st.error(f"Error al cargar tus análisis: {e_man}")

        # TAB: INFORMES IA (ADMIN)
        if st.session_state.es_croma and tab_admin_informes_ia:
            with tab_admin_informes_ia:
                st.subheader("🤖 Generador de Informes Inteligentes")
                st.info("Generación de informes globales y por empleado basados en los resultados acumulados.")

        # TAB: GESTIÓN Y CONFIGURACIÓN (ADMIN)
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Configuración del Sistema")
                c_conf1, c_conf2 = st.columns(2)
                with c_conf1:
                    st.markdown("##### ⏱️ Tiempo por Pregunta (segundos)")
                    n_tiempo = st.number_input("Segundos:", value=TIEMPO_LIMITE_PREGUNTA, min_value=10, max_value=300)
                    if st.button("Guardar Tiempo"):
                        if guardar_tiempo_pregunta_config(n_tiempo):
                            st.success("Tiempo actualizado.")
                            st.rerun()

                with c_conf2:
                    st.markdown("##### 🔢 Número de Preguntas por Examen")
                    n_preg_glob = st.number_input("Preguntas Examen Global:", value=NUM_PREG_GLOBAL, min_value=1)
                    n_preg_man = st.number_input("Preguntas Examen Manual:", value=NUM_PREG_MANUAL, min_value=1)
                    if st.button("Guardar Configuración Preguntas"):
                        guardar_num_preguntas_config("global", n_preg_glob)
                        guardar_num_preguntas_config("manual", n_preg_man)
                        st.success("Configuración de preguntas guardada.")
                        st.rerun()
