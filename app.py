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

# ---------------------------------------------------------
# INICIALIZACIÓN ESTRUCTURAS SQL
# ---------------------------------------------------------
def inicializar_esquema_sql_evaluaciones():
    """
    Crea las estructuras necesarias en SQL para Evaluaciones e Informes.
    """
    try:
        supabase.rpc("ejecutar_sql_directo", {
            "query": """
            CREATE TABLE IF NOT EXISTS config_evaluaciones (
                id SERIAL PRIMARY KEY,
                media_objetivo NUMERIC DEFAULT 8.0,
                updated_at TIMESTAMP WITH TIMEZONE DEFAULT NOW()
            );
            INSERT INTO config_evaluaciones (id, media_objetivo) 
            VALUES (1, 8.0) ON CONFLICT (id) DO NOTHING;
            """
        }).execute()
    except Exception:
        pass

    try:
        supabase.rpc("ejecutar_sql_directo", {
            "query": """
            CREATE TABLE IF NOT EXISTS evaluaciones_trimestrales (
                id SERIAL PRIMARY KEY,
                empleado_id INT REFERENCES empleados(id),
                nombre_empleado VARCHAR(255),
                anio INT NOT NULL,
                trimestre VARCHAR(10) NOT NULL,
                puntuacion_total NUMERIC,
                observaciones TEXT,
                fecha_registro TIMESTAMP WITH TIMEZONE DEFAULT NOW(),
                UNIQUE(empleado_id, anio, trimestre)
            );
            """
        }).execute()
    except Exception:
        pass

    try:
        supabase.rpc("ejecutar_sql_directo", {
            "query": """
            CREATE TABLE IF NOT EXISTS evaluacion_detalles (
                id SERIAL PRIMARY KEY,
                evaluacion_id INT REFERENCES evaluaciones_trimestrales(id) ON DELETE CASCADE,
                concepto VARCHAR(255),
                puntuacion NUMERIC,
                fecha_registro TIMESTAMP WITH TIMEZONE DEFAULT NOW()
            );
            """
        }).execute()
    except Exception:
        pass

    try:
        supabase.rpc("ejecutar_sql_directo", {
            "query": """
            CREATE TABLE IF NOT EXISTS auditoria_evaluaciones (
                id SERIAL PRIMARY KEY,
                evaluacion_id INT,
                empleado_nombre VARCHAR(255),
                anio INT,
                trimestre VARCHAR(10),
                concepto VARCHAR(255),
                valor_anterior TEXT,
                valor_nuevo TEXT,
                usuario_modificador VARCHAR(255),
                fecha_modificacion TIMESTAMP WITH TIMEZONE DEFAULT NOW(),
                motivo TEXT
            );
            """
        }).execute()
    except Exception:
        pass

    try:
        supabase.rpc("ejecutar_sql_directo", {
            "query": """
            CREATE TABLE IF NOT EXISTS analisis_ia_empleados (
                id SERIAL PRIMARY KEY,
                empleado_id INT REFERENCES empleados(id),
                nombre_empleado VARCHAR(255),
                anio INT NOT NULL,
                modelo_ia VARCHAR(100),
                prompt_utilizado TEXT,
                analisis_texto TEXT,
                creado_por VARCHAR(255),
                activo BOOLEAN DEFAULT TRUE,
                fecha_generacion TIMESTAMP WITH TIMEZONE DEFAULT NOW()
            );
            """
        }).execute()
    except Exception:
        pass

inicializar_esquema_sql_evaluaciones()

# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE CONFIGURACIÓN Y SQL
# ---------------------------------------------------------
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

PROMPT_DEFECTO = """Genera un banco de EXACTAMENTE 50 preguntas tipo test por cada temática/sección basadas en el documento. 

Requisitos estrictos para el JSON:
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

        # ---------------------------------------------------------
        # PESTAÑA ADMINISTRADOR: EVALUACIONES TRIMESTRALES
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_trimestrales:
            with tab_trimestrales:
                st.subheader("📊 Gestión de Evaluaciones Trimestrales (Q1 - Q4)")
                
                media_objetivo_actual = obtener_media_objetivo_config()
                with st.expander("⚙️ Configuración de la Media Objetivo en Características"):
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

                st.markdown(f"**Media de Objetivo Actual:** `{media_objetivo_actual}`")
                st.markdown("---")

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
                                    st.error(f"❌ El empleado '{val_emp}' indicado en A8 de la pestaña {p} no existe en la base de datos SQL.")
                                    continue

                                puntuacion_total_val = None
                                observaciones_val = ""
                                items_detalles = []

                                for idx_row, row in df_q.iterrows():
                                    texto_a = str(row[0]).strip() if not pd.isna(row[0]) else ""
                                    
                                    if "puntuacion total" in texto_a.lower():
                                        try:
                                            puntuacion_total_val = float(row[2])
                                        except Exception:
                                            pass
                                    elif "observaciones" in texto_a.lower():
                                        observaciones_val = str(row[1]) if not pd.isna(row[1]) else ""

                                    if "puntuacion total" in texto_a.lower() or "porciento de puntuacion" in texto_a.lower():
                                        continue

                                    val_c = row[2] if len(row) > 2 else None
                                    val_d = str(row[3]).strip() if len(row) > 3 and not pd.isna(row[3]) else ""

                                    if not pd.isna(val_c):
                                        try:
                                            num_c = float(val_c)
                                            if val_d:
                                                items_detalles.append({"concepto": val_d, "puntuacion": num_c})
                                        except ValueError:
                                            pass

                                res_exist = supabase.table("evaluaciones_trimestrales").select("*")\
                                    .eq("empleado_id", emp_match["id"])\
                                    .eq("anio", val_anio)\
                                    .eq("trimestre", str(p).strip().upper()).execute()

                                if res_exist.data:
                                    eval_db = res_exist.data[0]
                                    res_det_db = supabase.table("evaluacion_detalles").select("*").eq("evaluacion_id", eval_db["id"]).execute()
                                    detalles_db = {d["concepto"]: d["puntuacion"] for d in (res_det_db.data or [])}

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
                                            "tipo": "total",
                                            "observaciones": observaciones_val,
                                            "detalles": items_detalles
                                        })

                                    for item_n in items_detalles:
                                        c_nom = item_n["concepto"]
                                        val_n = item_n["puntuacion"]
                                        val_v = detalles_db.get(c_nom)
                                        if val_v is not None and val_v != val_n:
                                            cambios_detectados.append({
                                                "evaluacion_id": eval_db["id"],
                                                "empleado_id": emp_match["id"],
                                                "empleado_nombre": emp_match["nombre"],
                                                "anio": val_anio,
                                                "trimestre": str(p).strip().upper(),
                                                "concepto": c_nom,
                                                "valor_viejo": val_v,
                                                "valor_nuevo": val_n,
                                                "tipo": "detalle",
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
                                        "observaciones": reg["observaciones"]
                                    }).execute()

                                    if res_ins.data:
                                        eval_id = res_ins.data[0]["id"]
                                        for det in reg["detalles"]:
                                            supabase.table("evaluacion_detalles").insert({
                                                "evaluacion_id": eval_id,
                                                "concepto": det["concepto"],
                                                "puntuacion": det["puntuacion"]
                                            }).execute()
                                st.success("✅ Datos de evaluaciones trimestrales guardados exitosamente en SQL.")
                                time.sleep(1.5)
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
                            if not usr_modifica.strip():
                                st.error("❌ El nombre de la persona que modifica es obligatorio.")
                            elif not motivo_mod.strip():
                                st.error("❌ El motivo del cambio es obligatorio.")
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

                                    if c_item["tipo"] == "total":
                                        supabase.table("evaluaciones_trimestrales").update({
                                            "puntuacion_total": c_item["valor_nuevo"],
                                            "observaciones": c_item["observaciones"]
                                        }).eq("id", c_item["evaluacion_id"]).execute()
                                    else:
                                        supabase.table("evaluacion_detalles").update({
                                            "puntuacion": c_item["valor_nuevo"]
                                        }).eq("evaluacion_id", c_item["evaluacion_id"]).eq("concepto", c_item["concepto"]).execute()

                                for reg in p_nuevos:
                                    res_ins = supabase.table("evaluaciones_trimestrales").insert({
                                        "empleado_id": reg["empleado_id"],
                                        "nombre_empleado": reg["nombre_empleado"],
                                        "anio": reg["anio"],
                                        "trimestre": reg["trimestre"],
                                        "puntuacion_total": reg["puntuacion_total"],
                                        "observaciones": reg["observaciones"]
                                    }).execute()

                                    if res_ins.data:
                                        eval_id = res_ins.data[0]["id"]
                                        for det in reg["detalles"]:
                                            supabase.table("evaluacion_detalles").insert({
                                                "evaluacion_id": eval_id,
                                                "concepto": det["concepto"],
                                                "puntuacion": det["puntuacion"]
                                            }).execute()

                                st.session_state.cambios_pendientes_excel = None
                                st.success("✅ Cambios actualizados y registrados en la auditoría correctamente.")
                                time.sleep(1)
                                st.rerun()

                        if btn_cancelar_cambios:
                            st.session_state.cambios_pendientes_excel = None
                            st.rerun()

                st.markdown("---")
                st.markdown("### 📈 Resumen Anual y Evaluación por Empleado")

                res_emp_trim = supabase.table("empleados").select("id, nombre").eq("activo", True).order("nombre", desc=False).execute()
                lista_emp_trim = res_emp_trim.data if res_emp_trim.data else []

                if lista_emp_trim:
                    dict_emp_trim = {e["nombre"]: e["id"] for e in lista_emp_trim}
                    c_sel1, c_sel2 = st.columns(2)
                    with c_sel1:
                        emp_trim_sel_nom = st.selectbox("👤 Selecciona Empleado:", list(dict_emp_trim.keys()), key="sel_emp_trim_admin")
                    with c_sel2:
                        res_anios_q = supabase.table("evaluaciones_trimestrales").select("anio").execute()
                        anios_q_list = sorted(list(set([a["anio"] for a in (res_anios_q.data or []) if a.get("anio")])), reverse=True)
                        if not anios_q_list:
                            anios_q_list = [datetime.datetime.now().year]
                        anio_q_sel = st.selectbox("📅 Selecciona Año:", anios_q_list, key="sel_anio_trim_admin")

                    emp_trim_id_val = dict_emp_trim[emp_trim_sel_nom]

                    res_evals_emp = supabase.table("evaluaciones_trimestrales").select("*")\
                        .eq("empleado_id", emp_trim_id_val)\
                        .eq("anio", anio_q_sel).execute()

                    evals_emp_data = res_evals_emp.data if res_evals_emp.data else []

                    if evals_emp_data:
                        df_q_emp = pd.DataFrame(evals_emp_data)
                        media_anual_q = df_q_emp["puntuacion_total"].mean()
                        
                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            st.metric("📊 Resumen Anual (Media de los Q)", f"{round(media_anual_q, 2)}")
                        with col_m2:
                            st.metric("🎯 Media del Objetivo", f"{media_objetivo_actual}")

                        st.markdown("##### 📌 Desglose Trimestral")
                        st.bar_chart(df_q_emp.set_index("trimestre")["puntuacion_total"], use_container_width=True)

                        st.markdown("---")
                        st.markdown("### 🤖 Generar Informe de Evaluación Experta con IA")

                        cfg_p_trim = None
                        try:
                            res_cfg_t = supabase.table("config_prompts").select("*").eq("nombre", "prompt_evaluacion_trimestral").limit(1).execute()
                            if res_cfg_t.data:
                                cfg_p_trim = res_cfg_t.data[0]
                        except Exception:
                            pass

                        prompt_defecto_t = cfg_p_trim.get("valor") if cfg_p_trim and cfg_p_trim.get("valor") else PROMPT_DEFECTO_TRIMESTRAL

                        prompt_trim_input = st.text_area("💬 Prompt editable para la Evaluación del Empleado:", value=prompt_defecto_t, height=120)
                        guardar_p_trim_chk = st.checkbox("💾 Guardar este prompt en la base de datos SQL")

                        modelos_ia_q = obtener_modelos_ia_disponibles()
                        modelos_q_sel = st.multiselect("🤖 Selección múltiple de IAs a consultar:", options=modelos_ia_q, default=[modelos_ia_q[0]] if modelos_ia_q else [])

                        if st.button("🚀 Ejecutar Evaluación Experta IA", use_container_width=True):
                            if guardar_p_trim_chk:
                                guardar_prompt_config("prompt_evaluacion_trimestral", prompt_trim_input)

                            res_hist = supabase.table("evaluaciones_trimestrales").select("*").eq("empleado_id", emp_trim_id_val).execute()
                            hist_data = res_hist.data if res_hist.data else []

                            contexto_prompt = f"{prompt_trim_input}\n\n[EMPLEADO]: {emp_trim_sel_nom}\n[AÑO SELECCIONADO]: {anio_q_sel}\n[MEDIA OBJETIVO EN CARACTERÍSTICAS]: {media_objetivo_actual}\n[HISTÓRICO TRIMS SQL]:\n{json.dumps(hist_data, indent=2, ensure_ascii=False)}"

                            for mod in modelos_q_sel:
                                with st.spinner(f"Consultando {mod}..."):
                                    try:
                                        res_ia_q = consultar_ia(mod, contexto_prompt)
                                        st.markdown(f"#### 🧠 Resultado ({mod})")
                                        st.info(res_ia_q)

                                        supabase.table("analisis_ia_empleados").insert({
                                            "empleado_id": emp_trim_id_val,
                                            "nombre_empleado": emp_trim_sel_nom,
                                            "anio": int(anio_q_sel),
                                            "modelo_ia": mod,
                                            "prompt_utilizado": prompt_trim_input,
                                            "analisis_texto": res_ia_q,
                                            "creado_por": st.session_state.user_nombre,
                                            "activo": True
                                        }).execute()
                                        st.success(f"✅ Resultado guardado en SQL para {emp_trim_sel_nom}.")
                                    except Exception as err_ia_q:
                                        st.error(f"Error al consultar {mod}: {err_ia_q}")

                    else:
                        st.warning(f"No hay registros de evaluaciones trimestrales para {emp_trim_sel_nom} en el año {anio_q_sel}.")

        # ---------------------------------------------------------
        # PESTAÑA EMPLEADO: INFORMES EVALUACIONES TRIMESTRALES
        # ---------------------------------------------------------
        if not st.session_state.es_croma and tab_emp_trimestrales:
            with tab_emp_trimestrales:
                st.subheader("📊 Informes Evaluaciones trimestrales")
                
                media_objetivo_val = obtener_media_objetivo_config()
                st.info(f"🎯 **Media del Objetivo en estas características:** `{media_objetivo_val}`")

                res_anios_emp_q = supabase.table("evaluaciones_trimestrales").select("anio")\
                    .eq("empleado_id", st.session_state.user_id).execute()
                anios_q_emp_list = sorted(list(set([a["anio"] for a in (res_anios_emp_q.data or []) if a.get("anio")])), reverse=True)

                if not anios_q_emp_list:
                    anios_q_emp_list = [datetime.datetime.now().year]

                anio_q_emp_sel = st.selectbox("📅 Selecciona el año de evaluación:", options=anios_q_emp_list, index=0)

                res_q_emp = supabase.table("evaluaciones_trimestrales").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("anio", anio_q_emp_sel)\
                    .order("trimestre", desc=False).execute()

                datos_q_emp = res_q_emp.data if res_q_emp.data else []

                if datos_q_emp:
                    df_q_usr = pd.DataFrame(datos_q_emp)
                    st.markdown("##### 📈 Datos Obtenidos por Q")
                    st.bar_chart(df_q_usr.set_index("trimestre")["puntuacion_total"], use_container_width=True)
                    st.dataframe(df_q_usr[["trimestre", "puntuacion_total", "observaciones"]].rename(columns={
                        "trimestre": "Trimestre (Q)",
                        "puntuacion_total": "Puntuación Obtenida",
                        "observaciones": "Observaciones"
                    }), use_container_width=True, hide_index=True)
                else:
                    st.write("No hay registros trimestrales para el año seleccionado.")

                st.markdown("---")
                st.markdown("### 📄 Informe de Evaluación por IA")

                res_inf_emp = supabase.table("analisis_ia_empleados").select("*")\
                    .eq("empleado_id", st.session_state.user_id)\
                    .eq("anio", anio_q_emp_sel)\
                    .eq("activo", True)\
                    .order("fecha_generacion", desc=True).execute()

                informes_emp = res_inf_emp.data if res_inf_emp.data else []

                if informes_emp:
                    inf_e = informes_emp[0]
                    st.success(f"🤖 **Informe de Evaluación ({inf_e.get('modelo_ia', 'IA')}) - Año {anio_q_emp_sel}**")
                    st.info(inf_e.get("analisis_texto"))
                    
                    pdf_emp_b = generar_pdf_evaluacion_ia(st.session_state.user_nombre, inf_e.get("analisis_texto", ""), anio_q_emp_sel)
                    if pdf_emp_b:
                        st.download_button(
                            label="📄 Descargar Informe PDF",
                            data=pdf_emp_b,
                            file_name=f"Evaluacion_Trimestral_{st.session_state.user_nombre}_{anio_q_emp_sel}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                else:
                    st.warning("No tienes ningún informe de evaluación habilitado para visualizar en este año.")

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

        # ---------------------------------------------------------
        # ADMIN CROMA - EXPORTACIÓN E IMPORTACIÓN
        # ---------------------------------------------------------
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
                        
                        opcion_elegida = st.selectbox("Selecciona el examen a exportar:", opciones_examenes, key="exp_select_intento")
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
                                key=f"btn_dl_excel_{examen_sel['id']}",
                                use_container_width=True
                            )

                        with col_exp_b:
                            pdf_bytes = generar_pdf_resultado(examen_sel)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Descargar PDF de este Examen",
                                    data=pdf_bytes,
                                    file_name=f"informe_examen_{examen_sel['id']}.pdf",
                                    mime="application/pdf",
                                    key=f"btn_dl_pdf_{examen_sel['id']}",
                                    use_container_width=True
                                )

                        st.markdown("---")
                        st.markdown("### 📊 Exportación Consolidada de Todos los Exámenes")
                        df_todos_exp = pd.DataFrame(intentos_exp_filtrados)
                        buffer_todos_excel = io.BytesIO()
                        with pd.ExcelWriter(buffer_todos_excel, engine='openpyxl') as writer:
                            df_todos_exp.to_excel(writer, index=False, sheet_name="General_Examenes")

                        st.download_button(
                            label=f"📥 Descargar Excel Consolidado ({len(intentos_exp_filtrados)} registros - {anio_exp_sel})",
                            data=buffer_todos_excel.getvalue(),
                            file_name=f"consolidado_examenes_{anio_exp_sel}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                else:
                    st.write("No hay exámenes registrados para exportación.")

        # ---------------------------------------------------------
        # ADMIN CROMA - ANALÍTICA E IA
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_analisis:
            with tab_admin_analisis:
                st.subheader("📈 Analítica Global e Inteligencia de Negocio")
                
                res_emp_all = supabase.table("empleados").select("id, nombre").eq("activo", True).order("nombre").execute()
                emp_all = res_emp_all.data if res_emp_all.data else []

                if emp_all:
                    dict_emp_all = {e["nombre"]: e["id"] for e in emp_all}
                    emp_analisis_sel = st.selectbox("👤 Selecciona Empleado para ver Analítica Global:", list(dict_emp_all.keys()), key="sel_emp_analisis")
                    emp_analisis_id = dict_emp_all[emp_analisis_sel]

                    res_int_emp = supabase.table("intentos_examen").select("*")\
                        .eq("empleado_id", emp_analisis_id)\
                        .eq("activo", True)\
                        .order("fecha_inicio", desc=False).execute()
                    intentos_emp_all = res_int_emp.data if res_int_emp.data else []

                    if intentos_emp_all:
                        df_emp_an = pd.DataFrame(intentos_emp_all)
                        df_emp_an["fecha"] = df_emp_an["fecha_inicio"].str[:10]

                        c_m1, c_m2, c_m3 = st.columns(3)
                        with c_m1:
                            st.metric("Total Exámenes Realizados", len(df_emp_an))
                        with c_m2:
                            st.metric("Nota Media Global", f"{round(df_emp_an['nota'].mean(), 2)} / 10")
                        with c_m3:
                            aprobados_count = sum(1 for p in df_emp_an['porcentaje_obtenido'] if p >= UMBRAL_APROBADO_PORCENTAJE)
                            st.metric("Tasa de Aprobado", f"{round((aprobados_count / len(df_emp_an)) * 100, 1)}%")

                        st.markdown("##### 📈 Evolución Histórica de Notas")
                        st.line_chart(df_emp_an.set_index("fecha")["nota"], use_container_width=True)

                        todas_resp_emp = []
                        for it in intentos_emp_all:
                            resp = it.get("respuestas_usuario", [])
                            if isinstance(resp, list):
                                todas_resp_emp.extend(resp)

                        if todas_resp_emp:
                            df_resp_all = pd.DataFrame(todas_resp_emp)
                            if "subindice" not in df_resp_all.columns:
                                df_resp_all["subindice"] = df_resp_all.get("categoria", "General")
                            df_resp_all["subindice"] = df_resp_all["subindice"].fillna("General")

                            resumen_sub = df_resp_all.groupby("subindice").agg(
                                Aciertos=('es_correcta', lambda x: sum(x == True)),
                                Fallos=('es_correcta', lambda x: sum(x == False)),
                                Total=('es_correcta', 'count')
                            ).reset_index()
                            resumen_sub["% Acierto"] = (resumen_sub["Aciertos"] / resumen_sub["Total"] * 100).round(2)

                            st.markdown("##### 📊 Rendimiento por Subíndice / Categoría")
                            st.bar_chart(resumen_sub.set_index("subindice")[["Aciertos", "Fallos"]], use_container_width=True)
                            st.dataframe(resumen_sub, use_container_width=True, hide_index=True)
                    else:
                        st.info("Este empleado aún no ha realizado ningún examen.")

        # ---------------------------------------------------------
        # ADMIN CROMA - INFORMES IA
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_informes_ia:
            with tab_admin_informes_ia:
                st.subheader("🤖 Informes Generados por IA y Visibilidad")
                
                res_informes_ia = supabase.table("analisis_ia_empleados").select("*").order("fecha_generacion", desc=True).execute()
                lista_informes_ia = res_informes_ia.data if res_informes_ia.data else []

                if lista_informes_ia:
                    for inf in lista_informes_ia:
                        e_nom = inf.get("nombre_empleado", "Empleado")
                        anio_inf = inf.get("anio", "N/A")
                        mod_inf = inf.get("modelo_ia", "IA")
                        act_inf = inf.get("activo", True)
                        f_gen = inf.get("fecha_generacion", "")[:10]

                        with st.expander(f"📄 Informe #{inf['id']} - {e_nom} | Año {anio_inf} | {mod_inf} | {'🟢 Visible para Empleado' if act_inf else '🔴 Oculto'}"):
                            st.write(f"**Creado por:** {inf.get('creado_por')} el {f_gen}")
                            st.info(inf.get("analisis_texto"))

                            c_i1, c_i2 = st.columns(2)
                            with c_i1:
                                nuevo_estado_act = not act_inf
                                btn_txt = "🔴 Ocultar al Empleado" if act_inf else "🟢 Habilitar Visibilidad"
                                if st.button(btn_txt, key=f"btn_vis_{inf['id']}", use_container_width=True):
                                    supabase.table("analisis_ia_empleados").update({"activo": nuevo_estado_act}).eq("id", inf["id"]).execute()
                                    st.success("✅ Visibilidad del informe actualizada.")
                                    time.sleep(1)
                                    st.rerun()

                            with c_i2:
                                pdf_inf_b = generar_pdf_evaluacion_ia(e_nom, inf.get("analisis_texto", ""), anio_inf)
                                if pdf_inf_b:
                                    st.download_button(
                                        label="📄 Descargar Informe PDF",
                                        data=pdf_inf_b,
                                        file_name=f"Informe_IA_{e_nom}_{anio_inf}.pdf",
                                        mime="application/pdf",
                                        key=f"pdf_ia_dl_{inf['id']}",
                                        use_container_width=True
                                    )
                else:
                    st.info("No se han generado informes de evaluación por IA hasta el momento.")

        # ---------------------------------------------------------
        # ADMIN CROMA - GESTIÓN Y CONFIGURACIÓN
        # ---------------------------------------------------------
        if st.session_state.es_croma and tab_admin_gestion:
            with tab_admin_gestion:
                st.subheader("⚙️ Gestión Global del Sistema y Configuración")
                
                subtab_emp, subtab_aut, subtab_prompts = st.tabs(["👤 Empleados", "🔓 Autorizaciones Examen", "💬 Prompts y Parámetros"])

                with subtab_emp:
                    st.markdown("### 👥 Listado y Edición de Empleados")
                    res_emp_gest = supabase.table("empleados").select("*").order("id").execute()
                    emp_gest_data = res_emp_gest.data if res_emp_gest.data else []

                    if emp_gest_data:
                        for eg in emp_gest_data:
                            c_e1, c_e2, c_e3 = st.columns([2, 2, 2])
                            with c_e1:
                                st.write(f"**{eg['nombre']}** ({'Admin CROMA' if eg.get('es_admin_croma') else 'Empleado'})")
                            with c_e2:
                                chk_ia = st.checkbox("Análisis IA Habilitado", value=eg.get("analisis_ia_habilitado", True), key=f"chk_ia_emp_{eg['id']}")
                            with c_e3:
                                chk_act = st.checkbox("Usuario Activo", value=eg.get("activo", True), key=f"chk_act_emp_{eg['id']}")

                            if chk_ia != eg.get("analisis_ia_habilitado") or chk_act != eg.get("activo"):
                                supabase.table("empleados").update({
                                    "analisis_ia_habilitado": chk_ia,
                                    "activo": chk_act
                                }).eq("id", eg["id"]).execute()
                                st.success(f"✅ Estado de {eg['nombre']} actualizado.")
                                time.sleep(1)
                                st.rerun()

                with subtab_aut:
                    st.markdown("### 🔓 Habilitar Intento Extra a Empleado")
                    
                    res_emp_a = supabase.table("empleados").select("id, nombre").eq("activo", True).execute()
                    emp_a_data = res_emp_a.data if res_emp_a.data else []

                    res_ex_a = supabase.table("examenes").select("apartado").eq("activo", True).execute()
                    ex_a_list = ["GLOBAL COMPLETO"] + [e["apartado"] for e in (res_ex_a.data or [])]

                    if emp_a_data:
                        dict_emp_a = {e["nombre"]: e["id"] for e in emp_a_data}
                        with st.form("form_autorizacion_extra"):
                            emp_aut_sel = st.selectbox("Selecciona Empleado:", list(dict_emp_a.keys()))
                            apt_aut_sel = st.selectbox("Selecciona Examen / Apartado:", ex_a_list)
                            btn_dar_aut = st.form_submit_button("🔓 Conceder Autorización de Re-intento")

                            if btn_dar_aut:
                                emp_id_aut = dict_emp_a[emp_aut_sel]
                                supabase.table("autorizaciones_examen").insert({
                                    "empleado_id": emp_id_aut,
                                    "apartado": apt_aut_sel
                                }).execute()
                                st.success(f"✅ Se concedió re-intento a {emp_aut_sel} para '{apt_aut_sel}'.")

                with subtab_prompts:
                    st.markdown("### 💬 Configuración de Parámetros y Prompts Predeterminados")
                    
                    t_pregunta_actual = obtener_tiempo_pregunta_config()
                    n_p_global_actual = obtener_num_preguntas_config("global")
                    n_p_manual_actual = obtener_num_preguntas_config("manual")

                    c_p1, c_p2, c_p3 = st.columns(3)
                    with c_p1:
                        nuevo_t_preg = st.number_input("⏱️ Segundos por pregunta:", min_value=10, max_value=300, value=t_pregunta_actual, step=5)
                    with c_p2:
                        nuevo_n_glob = st.number_input("🌐 Preguntas Examen Global:", min_value=5, max_value=50, value=n_p_global_actual, step=1)
                    with c_p3:
                        nuevo_n_man = st.number_input("📘 Preguntas Examen Manual:", min_value=5, max_value=50, value=n_p_manual_actual, step=1)

                    if st.button("Guardar Parámetros de Tiempos y Preguntas", use_container_width=True):
                        guardar_tiempo_pregunta_config(nuevo_t_preg)
                        guardar_num_preguntas_config("global", nuevo_n_glob)
                        guardar_num_preguntas_config("manual", nuevo_n_man)
                        st.success("✅ Parámetros de examen actualizados correctamente.")
                        time.sleep(1)
                        st.rerun()

                    st.markdown("---")
                    st.markdown("#### 💬 Editar Prompts Generales")
                    
                    # Comprobar de forma segura si cfg_ex_p fue definida y tiene datos
                    cfg_ex_p_obj = locals().get('cfg_ex_p', None)

                    if cfg_ex_p_obj and getattr(cfg_ex_p_obj, 'data', None) and len(cfg_ex_p_obj.data) > 0 and cfg_ex_p_obj.data[0]:
                        p_ex_val = cfg_ex_p_obj.data[0].get("valor") or PROMPT_DEFECTO_EXAMEN
                    else:
                        p_ex_val = PROMPT_DEFECTO_EXAMEN
                    
                    prompt_ex_edit = st.text_area("Prompt Generador de Preguntas de Examen (JSON):", value=p_ex_val, height=180)
                    if st.button("Guardar Prompt de Examen", use_container_width=True):
                        guardar_prompt_config("prompt_examen", prompt_ex_edit)
                        st.success("✅ Prompt de Examen actualizado.")
