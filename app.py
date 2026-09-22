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

# APARTADOS OFICIALES Y SUS PESOS POR DEFECTO
APARTADOS_CONFIG = {
    "Tareas realizar por turnos y todos los turnos": 20.0,
    "Tiempos respuesta Tbox": 20.0,
    "Tiempos respuesta Siemens": 20.0,
    "Iniciativa / Proactividad ante el trabajo": 20.0,
    "Conocimientos": 20.0
}

# ---------------------------------------------------------
# INICIALIZACIÓN ESTRUCTURAS SQL
# ---------------------------------------------------------
def inicializar_esquema_sql_evaluaciones():
    tables_sql = [
        """CREATE TABLE IF NOT EXISTS config_evaluaciones (
            id SERIAL PRIMARY KEY, media_objetivo NUMERIC DEFAULT 8.0, updated_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()
        );
        INSERT INTO config_evaluaciones (id, media_objetivo) VALUES (1, 8.0) ON CONFLICT (id) DO NOTHING;""",
        
        """CREATE TABLE IF NOT EXISTS config_apartados_eval (
            id SERIAL PRIMARY KEY, nombre_apartado VARCHAR(255) UNIQUE NOT NULL, habilitado BOOLEAN DEFAULT TRUE, peso NUMERIC DEFAULT 20.0, updated_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()
        );""",
        
        """CREATE TABLE IF NOT EXISTS evaluaciones_trimestrales (
            id SERIAL PRIMARY KEY, empleado_id INT REFERENCES empleados(id), nombre_empleado VARCHAR(255), anio INT NOT NULL, trimestre VARCHAR(10) NOT NULL, puntuacion_total NUMERIC, observaciones TEXT, habilitado BOOLEAN DEFAULT TRUE, fecha_registro TIMESTAMP WITH TIMEZONE DEFAULT NOW(), UNIQUE(empleado_id, anio, trimestre)
        );""",
        
        """CREATE TABLE IF NOT EXISTS evaluacion_detalles (
            id SERIAL PRIMARY KEY, evaluacion_id INT REFERENCES evaluaciones_trimestrales(id) ON DELETE CASCADE, apartado VARCHAR(255), tipo VARCHAR(255), puntuacion NUMERIC, comentario TEXT, concepto VARCHAR(255), fecha_registro TIMESTAMP WITH TIMEZONE DEFAULT NOW()
        );""",
        
        """CREATE TABLE IF NOT EXISTS auditoria_evaluaciones (
            id SERIAL PRIMARY KEY, evaluacion_id INT, empleado_nombre VARCHAR(255), anio INT, trimestre VARCHAR(10), concepto VARCHAR(255), valor_anterior TEXT, valor_nuevo TEXT, usuario_modificador VARCHAR(255), fecha_modificacion TIMESTAMP WITH TIMEZONE DEFAULT NOW(), motivo TEXT
        );""",
        
        """CREATE TABLE IF NOT EXISTS analisis_ia_empleados (
            id SERIAL PRIMARY KEY, empleado_id INT REFERENCES empleados(id), nombre_empleado VARCHAR(255), anio INT NOT NULL, modelo_ia VARCHAR(100), prompt_utilizado TEXT, analisis_texto TEXT, creado_por VARCHAR(255), activo BOOLEAN DEFAULT TRUE, fecha_generacion TIMESTAMP WITH TIMEZONE DEFAULT NOW()
        );""",
        
        """CREATE TABLE IF NOT EXISTS autorizaciones_examen (
            id SERIAL PRIMARY KEY, empleado_id INT REFERENCES empleados(id), apartado VARCHAR(255), fecha_autorizacion TIMESTAMP WITH TIMEZONE DEFAULT NOW()
        );""",
        
        """CREATE TABLE IF NOT EXISTS config_tiempos_preguntas (
            id SERIAL PRIMARY KEY, tiempos_segundos INT DEFAULT 45, updated_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()
        );""",
        
        """CREATE TABLE IF NOT EXISTS config_prompts (
            id SERIAL PRIMARY KEY, nombre VARCHAR(255) UNIQUE NOT NULL, valor TEXT, modelo_gemini VARCHAR(255), modelo_claude VARCHAR(255), modelo_openai VARCHAR(255)
        );"""
    ]

    for q in tables_sql:
        try:
            supabase.rpc("ejecutar_sql_directo", {"query": q}).execute()
        except Exception:
            pass

    try:
        res_cfg = supabase.table("config_apartados_eval").select("id").execute()
        if not res_cfg.data:
            for ap_nom, ap_peso in APARTADOS_CONFIG.items():
                supabase.table("config_apartados_eval").insert({
                    "nombre_apartado": ap_nom,
                    "habilitado": True,
                    "peso": ap_peso
                }).execute()
    except Exception:
        pass

inicializar_esquema_sql_evaluaciones()

# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE CONFIGURACIÓN Y SQL
# ---------------------------------------------------------
def obtener_config_apartados():
    try:
        res = supabase.table("config_apartados_eval").select("*").execute()
        if res.data:
            return {row["nombre_apartado"]: {"habilitado": row["habilitado"], "peso": float(row["peso"])} for row in res.data}
    except Exception:
        pass
    return {k: {"habilitado": True, "peso": v} for k, v in APARTADOS_CONFIG.items()}

def guardar_config_apartado(nombre, habilitado, peso):
    try:
        supabase.table("config_apartados_eval").upsert({
            "nombre_apartado": nombre,
            "habilitado": habilitado,
            "peso": float(peso),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }, on_conflict="nombre_apartado").execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar configuración de apartado: {e}")
        return False

def calcular_media_evaluacion(evaluaciones_trimestrales, config_apartados):
    q_validos = [q for q in evaluaciones_trimestrales if q.get("habilitado", True) and q.get("puntuacion_total") is not None]
    if not q_validos:
        return 0.0
    
    totales_q = [q["puntuacion_total"] for q in q_validos]
    return sum(totales_q) / len(totales_q)

def obtener_media_objetivo_config():
    try:
        res = supabase.table("config_evaluaciones").select("media_objetivo").eq("id", 1).execute()
        if res.data and res.data[0].get("media_objetivo") is not None:
            return float(res.data[0]["media_objetivo"])
    except Exception:
        pass
    return 8.0

def guardar_media_objetivo_config(nueva_media):
    try:
        supabase.table("config_evaluaciones").upsert({
            "id": 1,
            "media_objetivo": float(nueva_media),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar media objetivo: {e}")
        return False

def obtener_tiempo_pregunta_config():
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
if "cambios_pendientes_excel" not in st.session_state:
    st.session_state.cambios_pendientes_excel = None

TIEMPO_LIMITE_PREGUNTA = obtener_tiempo_pregunta_config()
UMBRAL_APROBADO_PORCENTAJE = 70.0

PROMPT_DEFECTO_EXAMEN = f"""Genera un banco de EXACTAMENTE 50 preguntas tipo test por cada temática detectada en el documento.
Para cada pregunta, asigna por defecto el nivel de dificultad "dificil" y establece el campo "tipo" como "examen".
Cada pregunta debe incluir la propiedad "tiempo_segundos": {TIEMPO_LIMITE_PREGUNTA}.

Responde ÚNICAMENTE con un array JSON estructurado exactamente de la siguiente forma:
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

PROMPT_DEFECTO_TRIMESTRAL = """Como experto en evaluaciones de empleados de empresa, quiero que me hagas una evaluacion del empleado selecionado, tanto los datos de este año como los anteriores. Con graficas, y como experto debes indicar cual es la media del objetivo en estas caracteristicas."""

TEXTO_EXAMEN_GLOBAL_INFO = f"""En el examen global, se incluirán exactamente 15 preguntas distribuidas equitativamente entre las distintas temáticas. Se aplicará un tiempo máximo por pregunta de {TIEMPO_LIMITE_PREGUNTA} segundos."""

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
                    raise Exception("SDK de Anthropic/Claude no disponible.")
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
                raise Exception(f"Respuesta vacía de Gemini ({mod}).")
        except Exception as err:
            ultimo_error = err
            continue

    raise Exception(f"Error tras consultar todos los modelos de IA. Último error: {ultimo_error}")

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
            tab_examenes, tab_trimestrales, tab_admin_manual, tab_admin_resultados, tab_admin_export, tab_admin_analisis, tab_admin_informes_ia, tab_admin_gestion = st.tabs([
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
            tab_examenes, tab_emp_trimestrales, tab_mis_resultados, tab_mi_analisis = st.tabs([
                "📝 Realizar Examen", 
                "📊 Informes Evaluaciones trimestrales",
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
            except Exception:
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
                examenes_disponibles = [ex for ex in raw_examenes if ex.get("activo") is True or ex.get("activo") is None]
            except Exception as e:
                examenes_disponibles = []
                st.error(f"Error al cargar manuales: {e}")

            if examenes_disponibles:
                st.subheader("📋 Seleccionar Modalidad")
                tab_global, tab_manual = st.tabs(["🌐 Examen Global", "📘 Examen por Manual"])
                
                with tab_global:
                    num_p_global = obtener_num_preguntas_config("global")
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
                    num_p_manual = obtener_num_preguntas_config("manual")
                    
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

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: EVALUACIONES TRIMESTRALES
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_trimestrales:
            with tab_trimestrales:
                st.subheader("📊 Gestión de Evaluaciones Trimestrales (Q1 - Q4)")
                
                config_apartados = obtener_config_apartados()

                with st.expander("⚙️ Configuración de Apartados, Habilitación, Pesos y Media Objetivo"):
                    media_objetivo_actual = obtener_media_objetivo_config()
                    c_med1, c_med2 = st.columns([3, 1])
                    with c_med1:
                        nueva_media_obj = st.number_input("Establecer Media del Objetivo:", min_value=0.0, max_value=100.0, value=media_objetivo_actual, step=0.1)
                    with c_med2:
                        st.write("")
                        st.write("")
                        if st.button("Guardar Media Objetivo", use_container_width=True):
                            if guardar_media_objetivo_config(nueva_media_obj):
                                st.success("✅ Media del objetivo actualizada correctamente.")
                                time.sleep(1)
                                st.rerun()

                    st.markdown("---")
                    st.markdown("##### 🛠️ Edición de Apartados (Habilitación y Pesos)")
                    
                    with st.form("form_config_apartados"):
                        nuevos_pesos_hab = {}
                        for ap_nombre, ap_info in config_apartados.items():
                            c_ap1, c_ap2 = st.columns([2, 2])
                            with c_ap1:
                                is_hab = st.checkbox(f"Habilitar {ap_nombre}", value=ap_info["habilitado"], key=f"hab_{ap_nombre}")
                            with c_ap2:
                                p_val = st.number_input(f"Peso para {ap_nombre} (%)", min_value=0.0, max_value=100.0, value=ap_info["peso"], step=1.0, key=f"peso_{ap_nombre}")
                            nuevos_pesos_hab[ap_nombre] = {"habilitado": is_hab, "peso": p_val}
                        
                        if st.form_submit_button("Guardar Configuración de Apartados"):
                            for ap_nombre, datos_cfg in nuevos_pesos_hab.items():
                                guardar_config_apartado(ap_nombre, datos_cfg["habilitado"], datos_cfg["peso"])
                            st.success("✅ Configuración de apartados guardada en SQL.")
                            time.sleep(1)
                            st.rerun()

                st.markdown("### 📤 Cargar Archivo Excel de Evaluación Trimestral")
                archivo_excel = st.file_uploader("Subir documento Excel (.xlsx)", type=["xlsx"])

                if archivo_excel is not None and st.session_state.cambios_pendientes_excel is None:
                    try:
                        xl = pd.ExcelFile(archivo_excel)
                        pestanas = [p for p in xl.sheet_names if str(p).strip().upper() in ["Q1", "Q2", "Q3", "Q4"]]
                        
                        if not pestanas:
                            st.error("❌ El documento subido no contiene pestañas llamadas Q1, Q2, Q3 o Q4.")
                        else:
                            res_emp_sql = supabase.table("empleados").select("id, nombre").execute()
                            dict_empleados = {e["nombre"].strip().lower(): e for e in (res_emp_sql.data or [])}

                            cambios_detectados = []
                            registros_nuevos = []

                            for p in pestanas:
                                df_q = pd.read_excel(xl, sheet_name=p, header=None)
                                
                                val_emp = str(df_q.iloc[7, 0]).strip() if df_q.shape[0] >= 8 else ""
                                val_anio_raw = df_q.iloc[9, 0] if df_q.shape[0] >= 10 else None
                                
                                try:
                                    val_anio = int(float(str(val_anio_raw).replace(",", ".")))
                                except Exception:
                                    val_anio = datetime.datetime.now().year

                                emp_match = dict_empleados.get(val_emp.lower())
                                if not emp_match:
                                    st.error(f"❌ El empleado '{val_emp}' indicado en la pestaña {p} no existe en la BD.")
                                    continue

                                puntuacion_total_val = None
                                observaciones_val = ""
                                items_detalles = []
                                apartado_actual_ctx = ""

                                for idx_row, row in df_q.iterrows():
                                    col_a = str(row[0]).strip() if not pd.isna(row[0]) else ""
                                    col_b = str(row[1]).strip() if len(row) > 1 and not pd.isna(row[1]) else ""
                                    
                                    if "observaciones generales:" in col_a.lower() or "observaciones generales:" in col_b.lower():
                                        if idx_row + 1 < df_q.shape[0]:
                                            obs_abajo = df_q.iloc[idx_row + 1, 0]
                                            if not pd.isna(obs_abajo):
                                                observaciones_val = str(obs_abajo).strip()

                                    if col_a in APARTADOS_CONFIG.keys():
                                        apartado_actual_ctx = col_a

                                    if "puntuacion total" in col_a.lower():
                                        try:
                                            puntuacion_total_val = float(row[2])
                                        except Exception:
                                            pass

                                    if "puntuacion total" in col_a.lower() or "porciento de puntuacion" in col_a.lower():
                                        continue

                                    val_c = row[2] if len(row) > 2 else None
                                    val_d = str(row[3]).strip() if len(row) > 3 and not pd.isna(row[3]) else ""

                                    if not pd.isna(val_c):
                                        try:
                                            num_c = float(val_c)
                                            items_detalles.append({
                                                "apartado": apartado_actual_ctx,
                                                "tipo": col_a if col_a != apartado_actual_ctx else "",
                                                "puntuacion": num_c,
                                                "comentario": val_d,
                                                "concepto": f"{col_a} {val_d}".strip()
                                            })
                                        except ValueError:
                                            pass

                                res_exist = supabase.table("evaluaciones_trimestrales").select("*")\
                                    .eq("empleado_id", emp_match["id"])\
                                    .eq("anio", val_anio)\
                                    .eq("trimestre", str(p).strip().upper()).execute()

                                if res_exist.data:
                                    eval_db = res_exist.data[0]
                                    if eval_db.get("puntuacion_total") != puntuacion_total_val:
                                        cambios_detectados.append({
                                            "evaluacion_id": eval_db["id"],
                                            "empleado_id": emp_match["id"],
                                            "empleado_nombre": emp_match["nombre"],
                                            "anio": val_anio,
                                            "trimestre": str(p).strip().upper(),
                                            "concepto": "Puntuación Total",
                                            "valor_viejo": eval_db.get("puntuacion_total"),
                                            "valor_nuevo": puntuacion_total_val,
                                            "observaciones": observaciones_val,
                                            "detalles": items_detalles
                                        })
                                else:
                                    registros_nuevos.append({
                                        "empleado_id": emp_match["id"],
                                        "nombre_empleado": emp_match["nombre"],
                                        "anio": val_anio,
                                        "trimestre": str(p).strip().upper(),
                                        "puntuacion_total": puntuacion_total_val,
                                        "observaciones": observaciones_val,
                                        "detalles": items_detalles
                                    })

                            if cambios_detectados:
                                st.session_state.cambios_pendientes_excel = {
                                    "cambios": cambios_detectados,
                                    "nuevos": registros_nuevos
                                }
                                st.rerun()
                            elif registros_nuevos:
                                for reg in registros_nuevos:
                                    res_ins = supabase.table("evaluaciones_trimestrales").insert({
                                        "empleado_id": reg["empleado_id"],
                                        "nombre_empleado": reg["nombre_empleado"],
                                        "anio": reg["anio"],
                                        "trimestre": reg["trimestre"],
                                        "puntuacion_total": reg["puntuacion_total"],
                                        "observaciones": reg["observaciones"],
                                        "habilitado": True
                                    }).execute()

                                    if res_ins.data:
                                        eval_id = res_ins.data[0]["id"]
                                        for det in reg["detalles"]:
                                            supabase.table("evaluacion_detalles").insert({
                                                "evaluacion_id": eval_id,
                                                "apartado": det.get("apartado"),
                                                "tipo": det.get("tipo"),
                                                "puntuacion": det.get("puntuacion"),
                                                "comentario": det.get("comentario"),
                                                "concepto": det.get("concepto")
                                            }).execute()
                                st.success("✅ Datos de evaluaciones trimestrales guardados exitosamente.")
                                time.sleep(1)
                                st.rerun()

                    except Exception as err_xl:
                        st.error(f"❌ Error al procesar el archivo Excel: {err_xl}")

                if st.session_state.cambios_pendientes_excel:
                    p_cambios = st.session_state.cambios_pendientes_excel["cambios"]
                    p_nuevos = st.session_state.cambios_pendientes_excel["nuevos"]

                    st.warning("⚠️ Se han detectado cambios en datos previamente registrados:")
                    df_diff = pd.DataFrame(p_cambios)[["empleado_nombre", "anio", "trimestre", "concepto", "valor_viejo", "valor_nuevo"]]
                    st.table(df_diff)

                    with st.form("form_confirmar_cambios_excel"):
                        usr_modifica = st.text_input("👤 Nombre de la persona que modifica (Obligatorio):*", value=st.session_state.user_nombre)
                        motivo_mod = st.text_area("📋 Motivo del cambio (Obligatorio):*")
                        
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            btn_aceptar_cambios = st.form_submit_button("✅ Aceptar y Actualizar Cambios", use_container_width=True)
                        with col_c2:
                            btn_cancelar_cambios = st.form_submit_button("❌ Cancelar", use_container_width=True)

                        if btn_aceptar_cambios:
                            if not usr_modifica.strip() or not motivo_mod.strip():
                                st.error("❌ Todos los campos son obligatorios.")
                            else:
                                for c_item in p_cambios:
                                    supabase.table("auditoria_evaluaciones").insert({
                                        "evaluacion_id": c_item["evaluacion_id"],
                                        "empleado_nombre": c_item["empleado_nombre"],
                                        "anio": c_item["anio"],
                                        "trimestre": c_item["trimestre"],
                                        "concepto": c_item["concepto"],
                                        "valor_anterior": str(c_item["valor_viejo"]),
                                        "valor_nuevo": str(c_item["valor_nuevo"]),
                                        "usuario_modificador": usr_modifica.strip(),
                                        "motivo": motivo_mod.strip()
                                    }).execute()

                                    supabase.table("evaluaciones_trimestrales").update({
                                        "puntuacion_total": c_item["valor_nuevo"],
                                        "observaciones": c_item["observaciones"]
                                    }).eq("id", c_item["evaluacion_id"]).execute()

                                st.session_state.cambios_pendientes_excel = None
                                st.success("✅ Cambios actualizados y registrados en la auditoría.")
                                time.sleep(1)
                                st.rerun()

                        if btn_cancelar_cambios:
                            st.session_state.cambios_pendientes_excel = None
                            st.rerun()

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: CARGAR MANUAL / PROMPT
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_manual:
            with tab_admin_manual:
                st.subheader("📄 Cargar Nuevo Manual en PDF y Generar Examen con IA")
                
                pdf_file = st.file_uploader("Selecciona el archivo PDF del Manual:", type=["pdf"])
                nombre_manual_input = st.text_input("Nombre del Manual / Apartado:")
                
                prompt_manual_input = st.text_area("Prompt para la IA:", value=PROMPT_DEFECTO_EXAMEN, height=180)
                modelo_ia_sel = st.selectbox("Seleccionar modelo de IA:", obtener_modelos_ia_disponibles())

                if st.button("🚀 Procesar PDF y Generar Banco de Preguntas", use_container_width=True):
                    if not pdf_file or not nombre_manual_input.strip():
                        st.error("❌ Por favor adjunta un PDF e indica el nombre del manual.")
                    else:
                        with st.spinner("Procesando PDF y consultando IA..."):
                            try:
                                reader = PdfReader(pdf_file)
                                texto_pdf = ""
                                for page in reader.pages:
                                    t_p = page.extract_text()
                                    if t_p:
                                        texto_pdf += t_p + "\n"

                                prompt_completo = f"{prompt_manual_input}\n\nDOCUMENTO DE REFERENCIA:\n{texto_pdf[:25000]}"
                                res_ia = consultar_ia(modelo_ia_sel, prompt_completo)

                                json_clean = res_ia.replace("```json", "").replace("```", "").strip()
                                raw_preguntas = json.loads(json_clean)

                                preguntas_validas = []
                                for item_p in raw_preguntas:
                                    p_norm = normalizar_pregunta_json(item_p)
                                    if p_norm:
                                        preguntas_validas.append(p_norm)

                                if preguntas_validas:
                                    supabase.table("examenes").insert({
                                        "apartado": nombre_manual_input.strip(),
                                        "preguntas_json": preguntas_validas,
                                        "activo": True
                                    }).execute()
                                    st.success(f"✅ Examen guardado exitosamente con {len(preguntas_validas)} preguntas.")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("❌ No se pudieron normalizar las preguntas del JSON generado.")
                            except Exception as e:
                                st.error(f"❌ Error durante el procesamiento: {e}")

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: RESULTADOS / EDICIÓN Y AUDITORÍA
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Resultados de Exámenes y Corrección Manual")
                
                try:
                    res_intentos_all = supabase.table("intentos_examen").select("*").eq("activo", True).order("fecha_inicio", desc=True).execute()
                    intentos_todos = res_intentos_all.data if res_intentos_all.data else []
                except Exception as e:
                    intentos_todos = []
                    st.error(f"Error al cargar intentos: {e}")

                if intentos_todos:
                    opciones_intentos = [f"#{i['id']} - {i['nombre_empleado']} ({i['apartado']}) - Nota: {i['nota']} - {i['fecha_inicio'][:16]}" for i in intentos_todos]
                    sel_intento_txt = st.selectbox("Selecciona un intento para auditoría / edición:", opciones_intentos)
                    intento_target_id = int(sel_intento_txt.split(" - ")[0].replace("#", ""))
                    
                    intento_obj = next((i for i in intentos_todos if i["id"] == intento_target_id), None)
                    if intento_obj:
                        st.markdown(f"**Empleado:** {intento_obj['nombre_empleado']} | **Apartado:** {intento_obj['apartado']} | **Nota:** `{intento_obj['nota']} / 10`")
                        
                        if REPORTLAB_DISPONIBLE:
                            pdf_data = generar_pdf_resultado(intento_obj)
                            if pdf_data:
                                st.download_button(
                                    "📥 Descargar PDF de Resultados",
                                    data=pdf_data,
                                    file_name=f"resultado_examen_{intento_obj['id']}.pdf",
                                    mime="application/pdf"
                                )

                        respuestas_lista = intento_obj.get("respuestas_usuario", [])
                        if respuestas_lista:
                            st.markdown("##### ✏️ Modificación de Preguntas y Respuestas")
                            for p_idx, p_objetivo in enumerate(respuestas_lista):
                                with st.expander(f"Pregunta {p_idx + 1}: {p_objetivo.get('pregunta', '')[:80]}..."):
                                    st.write(f"**Pregunta completa:** {p_objetivo.get('pregunta')}")
                                    st.write(f"**Respuesta del usuario:** {p_objetivo.get('opcion_elegida')}")
                                    st.write(f"**Respuesta correcta actual:** {p_objetivo.get('respuesta_correcta_texto')}")
                                    
                                    opciones_disponibles = p_objetivo.get("opciones_posibles", [])
                                    texto_respuesta_correcta = p_objetivo.get("respuesta_correcta_texto", "")

                                    with st.form(key=f"form_editar_pregunta_{intento_target_id}_{p_idx}"):
                                        nueva_respuesta_corr = st.selectbox(
                                            "Marcar respuesta correcta oficial:",
                                            options=opciones_disponibles if opciones_disponibles else [texto_respuesta_correcta],
                                            index=opciones_disponibles.index(texto_respuesta_correcta) if (opciones_disponibles and texto_respuesta_correcta in opciones_disponibles) else 0
                                        )
                                        es_correcta_manual = st.checkbox("Marcar como respuesta CORRECTA para el empleado", value=p_objetivo.get("es_correcta", False))
                                        motivo_edicion = st.text_input("Motivo de la corrección:", value="Corrección por administración")

                                        if st.form_submit_button("💾 Guardar Corrección en el Examen"):
                                            respuestas_lista[p_idx]["respuesta_correcta_texto"] = nueva_respuesta_corr
                                            respuestas_lista[p_idx]["es_correcta"] = es_correcta_manual

                                            total_p = len(respuestas_lista)
                                            correctas = sum(1 for r in respuestas_lista if r.get("es_correcta"))
                                            nueva_nota = round((correctas / total_p) * 10, 2) if total_p > 0 else 0.0
                                            nuevo_porcentaje = round((correctas / total_p) * 100, 2) if total_p > 0 else 0.0

                                            supabase.table("intentos_examen").update({
                                                "respuestas_usuario": respuestas_lista,
                                                "nota": nueva_nota,
                                                "porcentaje_obtenido": nuevo_porcentaje
                                            }).eq("id", intento_target_id).execute()

                                            supabase.table("auditoria_evaluaciones").insert({
                                                "evaluacion_id": intento_target_id,
                                                "empleado_nombre": intento_obj.get("nombre_empleado"),
                                                "concepto": f"Edición Examen #{intento_target_id} Pregunta {p_idx+1}",
                                                "valor_anterior": f"Nota: {intento_obj.get('nota')}",
                                                "valor_nuevo": f"Nota: {nueva_nota}",
                                                "usuario_modificador": st.session_state.user_nombre,
                                                "motivo": motivo_edicion
                                            }).execute()

                                            st.success("✅ Examen corregido y recalculado exitosamente.")
                                            time.sleep(1)
                                            st.rerun()

                        st.markdown("---")
                        if st.button("🗑️ Desactivar / Eliminar este Intento", key=f"del_intento_{intento_target_id}"):
                            supabase.table("intentos_examen").update({"activo": False}).eq("id", intento_target_id).execute()
                            st.success("Intento desactivado.")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.info("No hay intentos de examen registrados.")

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: EXPORTACIÓN Y AUTORIZACIONES
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación de Exámenes y Gestión de Autorizaciones")
                
                st.markdown("##### 🔓 Autorizaciones para Repetición de Exámenes")
                res_emp = supabase.table("empleados").select("id, nombre").eq("activo", True).execute()
                empleados_list = res_emp.data if res_emp.data else []
                
                col_aut1, col_aut2, col_aut3 = st.columns(3)
                with col_aut1:
                    emp_sel_aut = st.selectbox("Empleado:", [e["nombre"] for e in empleados_list], key="sel_emp_aut")
                with col_aut2:
                    res_m = supabase.table("examenes").select("apartado").eq("activo", True).execute()
                    manuales_list = [m["apartado"] for m in (res_m.data or [])] + ["GLOBAL COMPLETO"]
                    manual_sel_aut = st.selectbox("Apartado / Examen:", manuales_list, key="sel_man_aut")
                with col_aut3:
                    st.write("")
                    st.write("")
                    if st.button("Habilitar Intento Extra", use_container_width=True):
                        emp_obj = next((e for e in empleados_list if e["nombre"] == emp_sel_aut), None)
                        if emp_obj:
                            supabase.table("autorizaciones_examen").insert({
                                "empleado_id": emp_obj["id"],
                                "apartado": manual_sel_aut
                            }).execute()
                            st.success(f"✅ Autorización concedida a {emp_sel_aut} para {manual_sel_aut}.")

                st.markdown("---")
                st.markdown("##### 📊 Exportar Histórico de Intentos")
                res_exp = supabase.table("intentos_examen").select("id, nombre_empleado, apartado, nota, porcentaje_obtenido, fecha_inicio, sobrepasado_tiempo").eq("activo", True).execute()
                if res_exp.data:
                    df_exp = pd.DataFrame(res_exp.data)
                    st.dataframe(df_exp, use_container_width=True)
                    csv_data = df_exp.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Descargar Reporte Completo CSV", data=csv_data, file_name="reporte_examenes.csv", mime="text/csv")

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: ANALÍTICA E IA
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_analisis:
            with tab_admin_analisis:
                st.subheader("📈 Analítica Global del Desempeño")
                
                res_all_int = supabase.table("intentos_examen").select("*").eq("activo", True).execute()
                if res_all_int.data:
                    df_all = pd.DataFrame(res_all_int.data)
                    
                    st.markdown("##### 🏆 Promedio de Notas por Empleado")
                    prom_emp = df_all.groupby("nombre_empleado")["nota"].mean().reset_index()
                    st.bar_chart(prom_emp.set_index("nombre_empleado"))

                    st.markdown("##### 📘 Promedio de Notas por Manual / Examen")
                    prom_man = df_all.groupby("apartado")["nota"].mean().reset_index()
                    st.bar_chart(prom_man.set_index("apartado"))
                else:
                    st.info("No hay datos suficientes para analíticas.")

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: INFORMES IA
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_informes_ia:
            with tab_admin_informes_ia:
                st.subheader("🤖 Generación e Informes de Evaluación por IA")
                
                res_emp = supabase.table("empleados").select("id, nombre").eq("activo", True).execute()
                emp_list_ia = res_emp.data if res_emp.data else []
                
                emp_ia_sel = st.selectbox("Seleccionar Trabajador:", [e["nombre"] for e in emp_list_ia], key="sel_emp_ia")
                anio_ia_sel = st.number_input("Año de evaluación:", value=datetime.datetime.now().year, step=1)
                modelo_ia_rep = st.selectbox("Modelo IA:", obtener_modelos_ia_disponibles(), key="sel_mod_ia_rep")
                prompt_ia_custom = st.text_area("Prompt para Informe de Evaluación:", value=PROMPT_DEFECTO_TRIMESTRAL, height=120)

                if st.button("🤖 Generar Informe Profesional IA", use_container_width=True):
                    emp_obj = next((e for e in emp_list_ia if e["nombre"] == emp_ia_sel), None)
                    if emp_obj:
                        with st.spinner("Generando análisis cuantitativo y cualitativo con IA..."):
                            res_evals = supabase.table("evaluaciones_trimestrales").select("*").eq("empleado_id", emp_obj["id"]).execute()
                            datos_eval = json.dumps(res_evals.data) if res_evals.data else "Sin datos"
                            
                            prompt_final = f"{prompt_ia_custom}\n\nDATOS DEL TRABAJADOR ({emp_ia_sel}):\n{datos_eval}"
                            informe_res = consultar_ia(modelo_ia_rep, prompt_final)

                            supabase.table("analisis_ia_empleados").insert({
                                "empleado_id": emp_obj["id"],
                                "nombre_empleado": emp_ia_sel,
                                "anio": anio_ia_sel,
                                "modelo_ia": modelo_ia_rep,
                                "prompt_utilizado": prompt_ia_custom,
                                "analisis_texto": informe_res,
                                "creado_por": st.session_state.user_nombre
                            }).execute()

                            st.success("✅ Informe generado exitosamente.")
                            st.markdown(informe_res)

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: GESTIÓN Y CONFIGURACIÓN
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Gestión de Usuarios y Parámetros del Sistema")
                
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    st.markdown("##### ⏱️ Configuración de Tiempos y Límite de Preguntas")
                    tiempo_actual = obtener_tiempo_pregunta_config()
                    nuevo_tiempo_inp = st.number_input("Tiempo por pregunta (segundos):", min_value=10, max_value=300, value=tiempo_actual)
                    
                    num_g_actual = obtener_num_preguntas_config("global")
                    nuevo_num_g = st.number_input("Preguntas para Examen Global:", min_value=1, max_value=100, value=num_g_actual)
                    
                    num_m_actual = obtener_num_preguntas_config("manual")
                    nuevo_num_m = st.number_input("Preguntas por Manual:", min_value=1, max_value=100, value=num_m_actual)

                    if st.button("💾 Guardar Parámetros de Examen", use_container_width=True):
                        guardar_tiempo_pregunta_config(nuevo_tiempo_inp)
                        guardar_num_preguntas_config("global", nuevo_num_g)
                        guardar_num_preguntas_config("manual", nuevo_num_m)
                        st.success("✅ Parámetros guardados correctamente.")
                        time.sleep(1)
                        st.rerun()

                with col_g2:
                    st.markdown("##### 👤 Crear Nuevo Empleado")
                    with st.form("form_crear_empleado"):
                        nom_nuevo_emp = st.text_input("Nombre Completo:")
                        pwd_nuevo_emp = st.text_input("Contraseña:", type="password")
                        es_admin_chk = st.checkbox("¿Es Administrador CROMA?")
                        
                        if st.form_submit_button("➕ Crear Empleado"):
                            if nom_nuevo_emp.strip() and pwd_nuevo_emp.strip():
                                supabase.table("empleados").insert({
                                    "nombre": nom_nuevo_emp.strip(),
                                    "password_hash": pwd_nuevo_emp.strip(),
                                    "es_admin_croma": es_admin_chk,
                                    "activo": True
                                }).execute()
                                st.success(f"✅ Empleado {nom_nuevo_emp} registrado correctamente.")
                                time.sleep(1)
                                st.rerun()

        # ---------------------------------------------------------
        # PESTAÑAS PARA USUARIOS / EMPLEADOS NORMALES
        # ---------------------------------------------------------
        if not st.session_state.es_croma:
            with tab_emp_trimestrales:
                st.subheader("📊 Mis Evaluaciones Trimestrales")
                res_mis_evals = supabase.table("evaluaciones_trimestrales").select("*").eq("empleado_id", st.session_state.user_id).execute()
                if res_mis_evals.data:
                    df_me = pd.DataFrame(res_mis_evals.data)
                    st.dataframe(df_me[["anio", "trimestre", "puntuacion_total", "observaciones"]], use_container_width=True, hide_index=True)
                else:
                    st.info("No dispones de evaluaciones trimestrales registradas.")

            with tab_mis_resultados:
                st.subheader("📊 Mis Resultados e Historial de Exámenes")
                res_mis_int = supabase.table("intentos_examen").select("*").eq("empleado_id", st.session_state.user_id).eq("activo", True).order("fecha_inicio", desc=True).execute()
                if res_mis_int.data:
                    for mi_int in res_mis_int.data:
                        st.markdown(f"**Examen:** {mi_int['apartado']} | **Nota:** `{mi_int['nota']} / 10` ({mi_int['porcentaje_obtenido']}%) | **Fecha:** {mi_int['fecha_inicio'][:16]}")
                        if REPORTLAB_DISPONIBLE:
                            pdf_usr = generar_pdf_resultado(mi_int)
                            if pdf_usr:
                                st.download_button("Descargar Informe PDF", data=pdf_usr, file_name=f"resultado_{mi_int['id']}.pdf", mime="application/pdf", key=f"dl_usr_{mi_int['id']}")
                        st.write("---")
                else:
                    st.info("No has realizado ningún examen aún.")

            with tab_mi_analisis:
                st.subheader("📈 Mi Rendimiento e Informes IA")
                res_mis_ia = supabase.table("analisis_ia_empleados").select("*").eq("empleado_id", st.session_state.user_id).order("fecha_generacion", desc=True).execute()
                if res_mis_ia.data:
                    for r_ia in res_mis_ia.data:
                        with st.expander(f"Informe IA - Año {r_ia['anio']} ({r_ia['fecha_generacion'][:10]})"):
                            st.markdown(r_ia["analisis_texto"])
                else:
                    st.info("No hay informes de IA generados para tu perfil.")
