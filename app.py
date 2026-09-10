import streamlit as st
import datetime
import json
import time
import random
import os
import calendar
import io
import pandas as pd
import plotly.express as px
from google import genai
from google.genai import types
from pypdf import PdfReader
from supabase import create_client, Client

# Importar SDK de Anthropic (Claude)
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
# CONFIGURACIÓN PÁGINA Y ESTILOS INSPIRADOS EN motor.html
# ---------------------------------------------------------
st.set_page_config(page_title="Evaluaciones CROMA", layout="wide")

st.markdown("""
    <style>
    /* Estilos para legibilidad de las pestañas (Tabs) */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        color: var(--ink) !important;
        font-weight: 600 !important;
        font-size: 15px !important;
    }

    g.stTabs [data-baseweb="tab"][aria-selected="true"] [data-testid="stMarkdownContainer"] p {
        color: var(--accent) !important;
    }
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}

    :root {
        --bg: #fff3e4;
        --panel: #ffffff;
        --ink: #141b26;
        --muted: #5b6675;
        --line: #d7dde5;
        --line2: #e7ebf0;
        --accent: #ff7900;
        --accent-d: #e06d00;
        --red: #d92d20;
        --amber: #f59e0b;
        --green: #12b76a;
        --shadow: 0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.06);
        --mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
        --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    .stApp {
        background-color: var(--bg);
        color: var(--ink);
        font-family: var(--sans);
    }

    .block-container {
        max-width: 1060px;
        margin: 0 auto;
        padding: 24px 20px 80px;
    }

    /* Opciones del selector de respuestas estilo motor.html */
    .stRadio label {
        font-size: 15px !important;
        font-weight: 500 !important;
        color: var(--ink) !important;
    }
    
    .stRadio div[role='radiogroup'] > label {
        background-color: #ffffff !important;
        padding: 11px 13px !important;
        border-radius: 10px !important;
        border: 1px solid var(--line) !important;
        transition: all 0.12s ease-in-out;
        width: 100%;
        margin-bottom: 8px !important;
    }

    .stRadio div[role='radiogroup'] > label:hover {
        border-color: var(--accent) !important;
    }

    .pregunta-titulo {
        font-size: 16px !important;
        font-weight: 600 !important;
        color: var(--ink);
        margin-bottom: 12px;
        line-height: 1.4;
        padding: 18px;
        background-color: var(--panel);
        border: 1px solid var(--line);
        border-radius: 12px;
        box-shadow: var(--shadow);
    }

    .user-card {
        background-color: var(--panel) !important;
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: var(--shadow);
        transition: 0.15s;
    }

    .user-card:hover {
        border-color: var(--accent);
    }

    /* Botones primarios y secundarios */
    .stButton>button {
        background-color: var(--accent) !important;
        color: #ffffff !important;
        border: 1px solid var(--accent) !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        font-size: 15px !important;
        padding: 11px 18px !important;
    }

    .stButton>button:hover {
        background-color: var(--accent-d) !important;
        border-color: var(--accent-d) !important;
    }

    /* Inputs de texto y textareas */
    .stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
        border-radius: 10px !important;
        border: 1px solid var(--line) !important;
        background-color: #fbfcfd !important;
        color: var(--ink) !important;
        font-family: var(--sans) !important;
    }
    </style>
""", unsafe_allow_html=True)

# PALETA PLOTLY BASADA EN MOTOR.HTML
COLOR_ACCENT = "#ff7900"
COLOR_ACCENT_DARK = "#e06d00"
COLOR_GREEN = "#12b76a"
COLOR_RED = "#d92d20"
COLOR_AMBER = "#f59e0b"
FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'

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
# FUNCIONES AUXILIARES
# ---------------------------------------------------------
def obtener_tiempo_pregunta_config():
    try:
        res = supabase.table("config_prompts").select("prompt_texto").eq("nombre", "tiempo_pregunta_segundos").limit(1).execute()
        if res.data and res.data[0].get("prompt_texto"):
            return int(res.data[0]["prompt_texto"])
    except Exception:
        pass
    return 45

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

TIEMPO_LIMITE_PREGUNTA = obtener_tiempo_pregunta_config()

# ---------------------------------------------------------
# AUTENTICACIÓN Y NAVEGACIÓN PRINCIPAL
# ---------------------------------------------------------
st.markdown('<div style="display:flex; align-items:center; gap:12px; margin-bottom:6px;"><span style="width:12px; height:12px; border-radius:50%; background:var(--accent); display:inline-block;"></span><span style="font-family:var(--mono); font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted);">CROMA · MasOrange / AGH Ibérica</span></div>', unsafe_allow_html=True)
st.title("Evaluaciones CROMA")

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
                    <h3 style="margin:0; font-size:16px;">👤 {u['nombre']}</h3>
                    <p style="color: var(--muted); font-size: 13px; margin:4px 0 0;">{"Administrador" if u.get("es_admin_croma") else "Empleado"}</p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Acceder", key=f"usr_btn_{u['id']}", use_container_width=True):
                    st.session_state.user_id = u["id"]
                    st.session_state.user_nombre = u["nombre"]
                    st.session_state.es_croma = u.get("es_admin_croma", False)
                    st.session_state.autenticado = True
                    st.rerun()

else:
    col_usr, col_logout = st.columns([4, 1])
    with col_usr:
        st.write(f"Bienvenido/a, **{st.session_state.user_nombre}** ({'Administrador CROMA' if st.session_state.es_croma else 'Empleado'})")
    with col_logout:
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.autenticado = False
            st.rerun()

    st.markdown("---")

    # PESTAÑAS ADMINISTRACIÓN / CLIENTE
    if st.session_state.es_croma:
        tab_analisis, tab_config = st.tabs([
            "📈 Dashboard / Analítica",
            "⚙️ Configuración de IA y Modelos (SQL config_prompts)"
        ])

        # ---------------------------------------------------------
        # PESTAÑA 1: ANALÍTICA Y GRÁFICAS
        # ---------------------------------------------------------
        with tab_analisis:
            st.subheader("📊 Muestras e Históricos")

            try:
                res_intentos = supabase.table("intentos_examen").select("*").execute()
                intentos_data = res_intentos.data if res_intentos.data else []
            except Exception as e:
                intentos_data = []
                st.error(f"Error cargando los resultados: {e}")

            if intentos_data:
                df = pd.DataFrame(intentos_data)
                
                # Normalización de Fechas
                df["fecha_dt"] = pd.to_datetime(df["fecha_inicio"], errors="coerce")
                df = df.dropna(subset=["fecha_dt"])  # Opcional: descarta filas sin fecha válida
                df["fecha_formateada"] = df["fecha_dt"].dt.strftime("%d-%m-%Y")

                # 1. GRÁFICA DE BARRAS: HISTÓRICO ACUMULADO POR TEMA/SUBÍNDICE (Barras Horizontales)
                st.markdown("**📊 Histórico Acumulado por Tema/Subíndice**")
                
                subindices_list = []
                for _, row in df.iterrows():
                    respuestas = row.get("respuestas_usuario", [])
                    if isinstance(respuestas, list):
                        for r in respuestas:
                            subindices_list.append({
                                "subindice": r.get("subindice", "General"),
                                "es_correcta": 1 if r.get("es_correcta") else 0
                            })
                
                if subindices_list:
                    df_sub = pd.DataFrame(subindices_list)
                    df_sub_agg = df_sub.groupby("subindice").agg(
                        Aciertos=('es_correcta', 'sum'),
                        Total=('es_correcta', 'count')
                    ).reset_index()

                    # Gráfica de Barras (orientation='h')
                    fig_barras = px.bar(
                        df_sub_agg,
                        x="Aciertos",
                        y="subindice",
                        orientation="h",
                        text="Aciertos",
                        color_discrete_sequence=[COLOR_ACCENT]
                    )
                    fig_barras.update_layout(
                        font_family=FONT_FAMILY,
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        xaxis=dict(gridcolor='#e7ebf0', title="Total de Aciertos"),
                        yaxis=dict(title="Tema / Subíndice", categoryorder="total ascending")
                    )
                    st.plotly_chart(fig_barras, use_container_width=True)

                st.markdown("---")

                # 2. GRÁFICA DE COLUMNAS: HISTÓRICO COMPLETO POR EMPLEADO (Columnas Verticales)
                st.markdown("**📊 Gráficas y Métricas por Empleado (Histórico Completo SQL)**")
                
                # Construir etiqueta inferior: Nombre + dd-mm-aaaa
                df["empleado_fecha"] = df["nombre_empleado"].astype(str) + " (" + df["fecha_formateada"].astype(str) + ")"

                # Gráfica de Columna (orientation='v' por defecto en px.bar si x es la variable categórica)
                fig_columnas = px.bar(
                    df,
                    x="empleado_fecha",
                    y="porcentaje_obtenido",
                    text="porcentaje_obtenido",
                    color_discrete_sequence=[COLOR_ACCENT_DARK],
                    labels={"empleado_fecha": "Empleado y Fecha", "porcentaje_obtenido": "Porcentaje (%)"}
                )
                fig_columnas.update_traces(texttemplate='%{text}%', textposition='outside')
                fig_columnas.update_layout(
                    font_family=FONT_FAMILY,
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    yaxis=dict(gridcolor='#e7ebf0', range=[0, 110], title="Porcentaje de Aciertos (%)"),
                    xaxis=dict(title="Empleado (dd-mm-aaaa)", tickangle=-45)
                )
                st.plotly_chart(fig_columnas, use_container_width=True)

            else:
                st.info("No hay registros en la base de datos para mostrar las gráficas.")

        # ---------------------------------------------------------
        # PESTAÑA 2: CONFIGURACIÓN DE IA Y MODELOS (config_prompts)
        # ---------------------------------------------------------
        with tab_config:
            st.subheader("⚙️ Configuración de IA y Modelos (SQL config_prompts)")
            st.caption("Administra, edita y ajusta los Prompts por defecto y Modelos asociados en la base de datos.")

            try:
                res_config = supabase.table("config_prompts").select("*").execute()
                prompts_list = res_config.data if res_config.data else []
            except Exception as e:
                prompts_list = []
                st.error(f"Error al conectar con la tabla config_prompts: {e}")

            if prompts_list:
                # Opciones de selección
                nombres_prompts = [p["nombre"] for p in prompts_list]
                prompt_sel = st.selectbox("Selecciona la configuración a editar:", nombres_prompts)

                cfg_item = next((p for p in prompts_list if p["nombre"] == prompt_sel), None)

                if cfg_item:
                    with st.form("form_edit_prompt"):
                        st.markdown(f"**Editando registro:** `{cfg_item['nombre']}`")
                        
                        prompt_texto_edit = st.text_area(
                            "Prompt / Texto de Configuración:",
                            value=cfg_item.get("prompt_texto", ""),
                            height=220
                        )

                        col_m1, col_m2 = st.columns(2)
                        with col_m1:
                            mod_gemini_edit = st.text_input(
                                "Modelos Gemini por defecto (separados por coma):",
                                value=cfg_item.get("modelo_gemini", "gemini-2.5-pro, gemini-2.5-flash")
                            )
                        with col_m2:
                            mod_claude_edit = st.text_input(
                                "Modelos Claude por defecto (separados por coma):",
                                value=cfg_item.get("modelo_claude", "claude-3-5-sonnet-20241022")
                            )

                        btn_guardar = st.form_submit_button("💾 Guardar Cambios en config_prompts")

                        if btn_guardar:
                            try:
                                supabase.table("config_prompts").update({
                                    "prompt_texto": prompt_texto_edit,
                                    "modelo_gemini": mod_gemini_edit,
                                    "modelo_claude": mod_claude_edit
                                }).eq("id", cfg_item["id"]).execute()
                                
                                st.success(f"¡Configuración de '{cfg_item['nombre']}' actualizada con éxito!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as err:
                                st.error(f"Error actualizando la base de datos: {err}")

            st.markdown("---")
            st.markdown("**Crear nueva configuración o Prompt global/de examen**")
            
            with st.expander("➕ Añadir nuevo registro a config_prompts"):
                with st.form("form_new_prompt"):
                    nuevo_nombre = st.text_input("Nombre de la configuración (e.g., prompt_global, prompt_examen):")
                    nuevo_texto = st.text_area("Contenido del Prompt:")
                    nuevo_gemini = st.text_input("Modelo Gemini por defecto:", value="gemini-2.5-pro")
                    nuevo_claude = st.text_input("Modelo Claude por defecto:", value="claude-3-5-sonnet-20241022")

                    btn_crear = st.form_submit_button("Crear Registro")

                    if btn_crear:
                        if nuevo_nombre.strip():
                            try:
                                supabase.table("config_prompts").insert({
                                    "nombre": nuevo_nombre.strip(),
                                    "prompt_texto": nuevo_texto,
                                    "modelo_gemini": nuevo_gemini,
                                    "modelo_claude": nuevo_claude
                                }).execute()
                                st.success("Registro insertado correctamente.")
                                time.sleep(1)
                                st.rerun()
                            except Exception as err:
                                st.error(f"Error al insertar: {err}")
                        else:
                            st.warning("Debes asignar un nombre a la configuración.")
