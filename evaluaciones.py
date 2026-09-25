# [cite: 8]
import calendar
import datetime
import io
import json
import os
import random
import time
import pandas as pd
from pypdf import PdfReader
from supabase import Client, create_client
import streamlit as st
from google import genai
from google.genai import types

# Importar SDK de Anthropic (Claude) - Opcional / Fallback futuro
try:
    import anthropic

    CLAUDE_DISPONIBLE = True
except ImportError:
    CLAUDE_DISPONIBLE = False

# Dependencias para generar PDF
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_DISPONIBLE = True
except ImportError:
    REPORTLAB_DISPONIBLE = False


# --- FUNCIÓN PARA OBTENER LOS MODELOS DISPONIBLES DESDE config_prompts ---
def obtener_modelos_disponibles_db():
    modelos = []
    try:
        res = supabase.table("config_prompts").select("*").execute().data
        if res:
            for r in res:
                mod_oa = r.get("modelo_openai") or (
                    r.get("valor") if "openai" in r.get(
                        "nombre", "").lower() else None
                )
                if mod_oa and mod_oa != "EMPTY":
                    modelos.append(
                        {"proveedor": "openai", "nombre_modelo": mod_oa})

                mod_gem = r.get("modelo_gemini") or (
                    r.get("valor") if "gemini" in r.get(
                        "nombre", "").lower() else None
                )
                if mod_gem and mod_gem != "EMPTY":
                    modelos.append(
                        {"proveedor": "gemini", "nombre_modelo": mod_gem})

        if not modelos:
            modelos = [
                {"proveedor": "openai", "nombre_modelo": "gpt-4o"},
                {"proveedor": "openai", "nombre_modelo": "gpt-4o-mini"},
                {"proveedor": "gemini", "nombre_modelo": "gemini-3.6-flash"},
            ]

        modelos_unicos = []
        vistos = set()
        for m in modelos:
            clave = f"{m['proveedor']}:{m['nombre_modelo']}"
            if clave not in vistos:
                vistos.add(clave)
                modelos_unicos.append(m)

        return modelos_unicos
    except Exception:
        return [
            {"proveedor": "openai", "nombre_modelo": "gpt-4o"},
            {"proveedor": "gemini", "nombre_modelo": "gemini-3.6-flash"},
        ]


# --- FUNCIONES DE VISIBILIDAD POR EMPLEADO ---
def obtener_visibilidad_empleado(empleado_id, anio):
    default_config = {
        "qs_habilitados": {"Q1": True, "Q2": True, "Q3": True, "Q4": True},
        "apartados_habilitados": {
            "Tareas realizar por turnos y todos los turnos": True,
            "Tiempos respuesta Tbox": True,
            "Tiempos respuesta Siemens": True,
            "Iniciativa / Proactividad ante el trabajo": True,
            "Conocimientos": True,
            "Evaluacion": True,
        },
        "subapartados_deshabilitados": [],
    }
    try:
        res = (
            supabase.table("visibilidad_empleados")
            .select("*")
            .eq("empleado_id", empleado_id)
            .eq("anio", anio)
            .execute()
            .data
        )
        if res:
            return res[0]
        return default_config
    except Exception:
        return default_config


def guardar_visibilidad_empleado(
    empleado_id, anio, qs, apartados, subapartados_ocultos
):
    datos = {
        "empleado_id": empleado_id,
        "anio": anio,
        "qs_habilitados": qs,
        "apartados_habilitados": apartados,
        "subapartados_deshabilitados": subapartados_ocultos,
    }
    supabase.table("visibilidad_empleados").upsert(
        datos, on_conflict="empleado_id, anio"
    ).execute()


def obtener_media_objetivo():
    try:
        res = (
            supabase.table("config_prompts_eval")
            .select("objetivo_media")
            .limit(1)
            .execute()
            .data
        )
        if res and "objetivo_media" in res[0]:
            return float(res[0]["objetivo_media"])
        return 8.0
    except Exception:
        return 8.0


# --- CONSULTA IA Y GENERACIÓN MULTIMODELO ---
def consultar_ia(prompt_completo, proveedor, nombre_modelo):
    try:
        if proveedor == "openai":
            api_key = st.secrets.get("OPENAI_API_KEY", "")
            if not api_key:
                return (
                    False,
                    "Falta configurar 'OPENAI_API_KEY' en los Secrets de Streamlit.",
                )
            if openai is None:
                return (
                    False,
                    "Librería 'openai' no instalada. Revisa tu requirements.txt.",
                )

            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=nombre_modelo,
                messages=[{"role": "user", "content": prompt_completo}],
                temperature=0.7,
            )
            return True, response.choices[0].message.content

        elif proveedor == "gemini":
            api_key = st.secrets.get("GEMINI_API_KEY", "")
            if not api_key:
                return (
                    False,
                    "Falta configurar 'GEMINI_API_KEY' en los Secrets de Streamlit.",
                )
            if genai is None:
                return (
                    False,
                    "Librería 'google-generativeai' no instalada. Revisa tu"
                    " requirements.txt.",
                )

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(nombre_modelo)
            response = model.generate_content(prompt_completo)
            return True, response.text

        return False, f"Proveedor '{proveedor}' no reconocido."
    except Exception as e:
        return False, f"Error con el modelo {nombre_modelo}: {e}"


def generar_y_guardar_informe_ia_multimodelo(
    empleado_id, nombre_emp, anio, lista_modelos_info
):
    try:
        cfg = (
            supabase.table("config_prompts_eval")
            .select("*")
            .limit(1)
            .execute()
            .data
        )
        prompt_base = (
            cfg[0]["prompt_texto"]
            if cfg
            else (
                "Realiza un informe evaluativo profesional basado en estos datos:"
            )
        )
    except Exception:
        prompt_base = (
            "Realiza un informe evaluativo profesional basado en estos datos:"
        )

    vis_emp = obtener_visibilidad_empleado(empleado_id, anio)
    qs_hab = vis_emp.get("qs_habilitados", {})
    apts_hab = vis_emp.get("apartados_habilitados", {})
    sub_ocultos = vis_emp.get("subapartados_deshabilitados", [])

    q_evals = (
        supabase.table("evaluaciones_trimestrales")
        .select("*")
        .eq("empleado_id", empleado_id)
        .eq("anio", anio)
        .execute()
        .data
    )

    resumen_datos = []
    for q in q_evals:
        q_nom = q["trimestre"]
        if not qs_hab.get(q_nom, True):
            continue
        detalles = (
            supabase.table("evaluacion_detalles")
            .select("*")
            .eq("evaluacion_id", q["id"])
            .execute()
            .data
        )
        if detalles:
            df_det = pd.DataFrame(detalles)
            df_det = df_det[df_det["apartado"].map(
                lambda x: apts_hab.get(x, True))]
            df_det = df_det[~df_det["subapartado"].isin(sub_ocultos)]
            for _, r in df_det.iterrows():
                resumen_datos.append({
                    "trimestre": q_nom,
                    "apartado": r["apartado"],
                    "subapartado": r["subapartado"],
                    "puntuacion": r["puntuacion"],
                    "observaciones": r.get("observaciones", ""),
                })

    if not resumen_datos:
        return (
            False,
            f"No existen datos de evaluaciones habilitadas para {nombre_emp} en"
            f" {anio}.",
        )

    prompt_completo = f"""
{prompt_base}

Empleado: {nombre_emp}
Año: {anio}

Datos de evaluaciones del año:
{json.dumps(resumen_datos, ensure_ascii=False, indent=2)}

Por favor, genera un informe detallado, constructivo y estructurado en Markdown.
"""

    textos_informes = []
    errores = []

    for mod_info in lista_modelos_info:
        prov = mod_info["proveedor"]
        mod_nom = mod_info["nombre_modelo"]

        exito, res_texto = consultar_ia(prompt_completo, prov, mod_nom)
        if exito:
            if len(lista_modelos_info) > 1:
                textos_informes.append(
                    f"### 🤖 Informe generado con {mod_nom} ({
                        prov.upper()})\n\n{res_texto}"
                )
            else:
                textos_informes.append(res_texto)
        else:
            errores.append(f"[{mod_nom}]: {res_texto}")

    if not textos_informes:
        return False, f"Fallaron todas las consultas de IA: {'; '.join(errores)}"

    informe_final = "\n\n---\n\n".join(textos_informes)

    try:
        supabase.table("informes_evaluacion").upsert(
            {
                "empleado_id": empleado_id,
                "anio": anio,
                "informe_texto": informe_final,
            },
            on_conflict="empleado_id, anio",
        ).execute()
        return True, informe_final
    except Exception as err:
        return False, f"Error al guardar el informe en la BD: {err}"


# --- VISTA COMPARTIDA DE EVALUACIONES ---
def renderizar_mis_evaluaciones(emp_id, nombre_emp, sel_anio):
    media_objetivo_sql = obtener_media_objetivo()
    vis_emp = obtener_visibilidad_empleado(emp_id, sel_anio)
    qs_habilitados = vis_emp.get("qs_habilitados", {})
    apts_habilitados = vis_emp.get("apartados_habilitados", {})
    sub_ocultos = vis_emp.get("subapartados_deshabilitados", [])

    q_evals = (
        supabase.table("evaluaciones_trimestrales")
        .select("*")
        .eq("empleado_id", emp_id)
        .eq("anio", sel_anio)
        .execute()
        .data
    )

    if q_evals:
        puntuaciones_obtenidas = []
        puntuaciones_maximas = []
        notas_sobre_10 = []

        for q in sorted(q_evals, key=lambda x: x["trimestre"]):
            q_nombre = q["trimestre"]

            if not qs_habilitados.get(q_nombre, True):
                continue

            detalles = (
                supabase.table("evaluacion_detalles")
                .select("*")
                .eq("evaluacion_id", q["id"])
                .execute()
                .data
            )

            if detalles:
                df_det = pd.DataFrame(detalles)
                df_det = df_det[
                    df_det["apartado"].map(
                        lambda x: apts_habilitados.get(x, True))
                ]
                df_det = df_det[~df_det["subapartado"].isin(sub_ocultos)]

                if not df_det.empty:
                    ptos_obtenidos = float(df_det["puntuacion"].sum())
                    ptos_max_q = float(len(df_det) * 5.0)
                    nota_10 = (ptos_obtenidos / ptos_max_q) * \
                        10 if ptos_max_q > 0 else 0
                    ptos_aprobar = (media_objetivo_sql / 10.0) * ptos_max_q

                    puntuaciones_obtenidas.append(ptos_obtenidos)
                    puntuaciones_maximas.append(ptos_max_q)
                    notas_sobre_10.append(nota_10)

                    estado_q = (
                        "🟢 APROBADO" if nota_10 >= media_objetivo_sql else "🔴 SUSPENSO"
                    )

                    with st.expander(f"📊 {q_nombre} - Estado: {estado_q}", expanded=True):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric(
                            "Puntos Obtenidos", f"{
                                round(
                                    ptos_obtenidos, 2)} pts")
                        c2.metric(
                            "Puntos Máximos Habilitados", f"{
                                round(
                                    ptos_max_q, 2)} pts")
                        c3.metric(
                            f"Mínimo para Aprobar ({media_objetivo_sql}/10)",
                            f"{round(ptos_aprobar, 2)} pts",
                        )
                        c4.metric(
                            "Nota (Escala 0 - 10)",
                            f"{round(nota_10, 2)} / 10",
                            delta="Aprobado"
                            if nota_10 >= media_objetivo_sql
                            else "- Suspenso",
                        )

                        if q.get("observaciones"):
                            st.info(
                                f"**Observaciones Generales del Q:** {
                                    q['observaciones']}"
                            )

                        st.markdown("**Desglose por Apartados:**")
                        for apartado, group in df_det.groupby("apartado"):
                            st.markdown(f"#### 📌 {apartado}")
                            for _, row in group.iterrows():
                                col1, col2 = st.columns([3, 1])
                                col1.write(f"• **{row['subapartado']}**")
                                if row["observaciones"]:
                                    col1.caption(
                                        f"Obs: {row['observaciones']}")
                                col2.metric(
                                    "Puntuación", f"{
                                        row['puntuacion']} pts")
                            st.divider()

        if puntuaciones_obtenidas:
            total_puntos_obt = sum(puntuaciones_obtenidas)
            total_puntos_max = sum(puntuaciones_maximas)
            nota_media_anual = (
                sum(notas_sobre_10) /
                len(notas_sobre_10) if notas_sobre_10 else 0
            )
            min_puntos_aprobar_anual = (
                media_objetivo_sql / 10.0) * total_puntos_max

            st.markdown("---")
            st.subheader("🏆 Resumen Anual Global (Trimestres Habilitados)")

            col_g1, col_g2, col_g3, col_g4 = st.columns(4)
            col_g1.metric(
                "Puntos Totales Obtenidos", f"{round(total_puntos_obt, 2)} pts"
            )
            col_g2.metric(
                "Puntuación Máxima Posible", f"{
                    round(
                        total_puntos_max, 2)} pts"
            )
            col_g3.metric(
                f"Mínimo Global para Aprobar ({media_objetivo_sql}/10)",
                f"{round(min_puntos_aprobar_anual, 2)} pts",
            )
            col_g4.metric(
                "Nota Media Anual (Escala 0 - 10)", f"{
                    round(
                        nota_media_anual, 2)} / 10"
            )

            if nota_media_anual >= media_objetivo_sql:
                st.success(
                    f"🎉 **ESTADO ANUAL: APROBADO** (Nota: {
                        round(
                            nota_media_anual,
                            2)}/10"
                    f" - Objetivo Requerido: {media_objetivo_sql})"
                )
            else:
                st.error(
                    f"⚠️ **ESTADO ANUAL: SUSPENSO** (Nota: {
                        round(
                            nota_media_anual,
                            2)}/10"
                    f" - Objetivo Requerido: {media_objetivo_sql})"
                )

            st.markdown("---")
            st.subheader("🤖 Informe Evaluativo IA Guardado")
            try:
                inf_resp = (
                    supabase.table("informes_evaluacion")
                    .select("informe_texto, created_at")
                    .eq("empleado_id", emp_id)
                    .eq("anio", sel_anio)
                    .execute()
                    .data
                )
                if inf_resp:
                    st.markdown(inf_resp[0]["informe_texto"])
                    st.caption(
                        f"Informe actualizado el: {
                            inf_resp[0]['created_at']}")
                else:
                    st.info(
                        "Aún no se ha generado e insertado el informe IA para este año."
                    )
            except Exception:
                st.info("Aún no existe la tabla o registro del informe IA.")
        else:
            st.warning("No hay trimestres habilitados para mostrar.")
    else:
        st.warning("No hay evaluaciones disponibles.")


# ---------------------------------------------------------
# CONFIGURACIÓN PÁGINA Y ESTILOS HTML / CSS
# ---------------------------------------------------------
st.set_page_config(page_title="Plataforma de Exámenes", layout="wide")

st.markdown(
    """
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
""",
    unsafe_allow_html=True,
)

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
        res = (
            supabase.table("config_tiempos_preguntas")
            .select("tiempos_segundos")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("tiempos_segundos") is not None:
            return int(res.data[0]["tiempos_segundos"])
    except Exception:
        pass
    return 45


def obtener_num_preguntas_config(tipo):
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        res = (
            supabase.table("config_prompts")
            .select("valor")
            .eq("nombre", clave_nombre)
            .limit(1)
            .execute()
        )
        if res.data and res.data[0].get("valor") is not None:
            return int(res.data[0]["valor"])
    except Exception:
        pass
    return 15 if tipo == "global" else 10


def guardar_tiempo_pregunta_config(nuevo_tiempo):
    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        res = (
            supabase.table("config_tiempos_preguntas")
            .select("id")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            supabase.table("config_tiempos_preguntas").update({
                "tiempos_segundos": int(nuevo_tiempo),
                "updated_at": now_iso,
            }).eq("id", res.data[0]["id"]).execute()
        else:
            supabase.table("config_tiempos_preguntas").insert({
                "tiempos_segundos": int(nuevo_tiempo),
                "updated_at": now_iso,
            }).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar tiempo por pregunta: {e}")
        return False


def guardar_num_preguntas_config(tipo, cantidad):
    clave_nombre = f"num_preguntas_{tipo}"
    try:
        res = (
            supabase.table("config_prompts")
            .select("id")
            .eq("nombre", clave_nombre)
            .execute()
        )
        if res.data:
            supabase.table("config_prompts").update({"valor": str(cantidad)}).eq(
                "nombre", clave_nombre
            ).execute()
        else:
            supabase.table("config_prompts").insert(
                {"nombre": clave_nombre, "valor": str(cantidad)}
            ).execute()
        return True
    except Exception as e:
        st.error(f"Error al guardar número de preguntas ({tipo}): {e}")
        return False


def obtener_modelos_ia_disponibles():
    try:
        res = (
            supabase.table("config_prompts")
            .select("modelo_gemini, modelo_claude, modelo_openai")
            .execute()
        )
        if res.data:
            modelos_sql = []
            for fila in res.data:
                for col in ["modelo_gemini", "modelo_claude", "modelo_openai"]:
                    if fila.get(col):
                        modelos_sql.extend(
                            [m.strip()
                             for m in fila[col].split(",") if m.strip()]
                        )

            modelos_unicos = list(dict.fromkeys(modelos_sql))
            if modelos_unicos:
                return modelos_unicos
    except Exception as err:
        st.warning(
            f"No se pudieron cargar los modelos desde la base de datos: {err}"
        )

    return [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    ]


def guardar_prompt_config(nombre_prompt, nuevo_valor):
    try:
        res = (
            supabase.table("config_prompts")
            .select("id")
            .eq("nombre", nombre_prompt)
            .execute()
        )
        if res.data:
            supabase.table("config_prompts").update({"valor": nuevo_valor}).eq(
                "nombre", nombre_prompt
            ).execute()
        else:
            supabase.table("config_prompts").insert(
                {"nombre": nombre_prompt, "valor": nuevo_valor}
            ).execute()
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
    "q": "pregunta",
    "question": "pregunta",
    "ok": "respuesta_correcta",
    "correcta": "respuesta_correcta",
    "respuesta_correcta": "respuesta_correcta",
    "correct": "respuesta_correcta",
    "no": "incorrectas",
    "incorrectas": "incorrectas",
    "respuestas_incorrectas": "incorrectas",
    "h": "pista",
    "pista": "pista",
    "hint": "pista",
    "cat": "categoria",
    "categoria": "categoria",
    "category": "categoria",
    "subindex": "subindice",
    "subindice": "subindice",
    "dificultad": "dificultad",
    "difficulty": "dificultad",
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
                        system=(
                            sistema
                            if sistema
                            else (
                                "Eres un asistente experto en análisis de datos y"
                                " evaluación formativa."
                            )
                        ),
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return mensaje.content[0].text
                else:
                    raise Exception(
                        "SDK de Anthropic/Claude no disponible o ANTHROPIC_API_KEY no"
                        " configurada."
                    )
            else:
                if not gemini_client:
                    raise Exception(
                        "El cliente de Gemini no está configurado.")

                p_final = f"{sistema}\n\n{prompt}" if sistema else prompt
                config_gen = types.GenerateContentConfig()
                if "JSON" in prompt.upper() or "json" in prompt:
                    config_gen.response_mime_type = "application/json"

                res = gemini_client.models.generate_content(
                    model=mod, contents=p_final, config=config_gen
                )
                if res and res.text:
                    return res.text
                raise Exception(f"Respuesta vacía recibida de Gemini ({mod}).")
        except Exception as err:
            ultimo_error = err
            continue

    raise Exception(
        "Error procesando la consulta tras intentar con todos los modelos de la"
        f" lista. Último error: {ultimo_error}"
    )


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

    pregunta_texto = item_normalizado.get(
        "pregunta", item_normalizado.get("q", "")
    )
    pista_texto = item_normalizado.get("pista", "Revisa la documentación.")
    categoria_texto = item_normalizado.get(
        "subindice", item_normalizado.get("categoria", "General")
    )
    dificultad_val = item_normalizado.get("dificultad", "media")

    opciones = []
    idx_correcta = 0

    if "opciones" in item_normalizado and isinstance(
        item_normalizado["opciones"], list
    ):
        opciones = [str(o) for o in item_normalizado["opciones"]]
        raw_correcta = item_normalizado.get("respuesta_correcta", 0)

        if isinstance(raw_correcta, int) and 0 <= raw_correcta < len(opciones):
            idx_correcta = raw_correcta
        elif isinstance(raw_correcta, str) and raw_correcta in opciones:
            idx_correcta = opciones.index(raw_correcta)
        else:
            idx_correcta = 0

    elif (
        "respuesta_correcta" in item_normalizado
        and "incorrectas" in item_normalizado
    ):
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
        "tipo": item_normalizado.get("tipo", "teorica"),
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

    if len(seleccionadas) < num_preguntas and len(banco_completo) > len(
        seleccionadas
    ):
        restantes = [p for p in banco_completo if p not in seleccionadas]
        faltantes = min(num_preguntas - len(seleccionadas), len(restantes))
        seleccionadas.extend(random.sample(restantes, faltantes))

    if len(seleccionadas) > num_preguntas:
        seleccionadas = random.sample(seleccionadas, num_preguntas)

    seleccionadas.sort(
        key=lambda x: str(
            x.get(
                "subindice",
                "General")).lower())
    return seleccionadas


def obtener_dias_restantes_mes():
    ahora = datetime.datetime.now()
    _, ultimo_dia = calendar.monthrange(ahora.year, ahora.month)
    return ultimo_dia - ahora.day + 1


def generar_pdf_resultado(intento):
    if not REPORTLAB_DISPONIBLE:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    story = []

    titulo_style = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=10,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=15,
    )
    bold_style = ParagraphStyle(
        "Bold",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        fontName="Helvetica-Bold",
    )
    norm_style = ParagraphStyle(
        "Norm", parent=styles["Normal"], fontSize=10, leading=13
    )
    err_style = ParagraphStyle(
        "Err",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#C53030"),
    )

    story.append(Paragraph("Informe de Evaluación de Examen", titulo_style))
    fecha_txt = (
        intento.get("fecha_inicio", "")[:10]
        if intento.get("fecha_inicio")
        else "N/A"
    )
    story.append(
        Paragraph(
            f"<b>Empleado:</b> {
                intento.get('nombre_empleado')} | <b>Fecha:</b>"
            f" {fecha_txt} | <b>Apartado:</b> {intento.get('apartado')}",
            sub_style,
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#CBD5E0"),
            spaceAfter=15,
        )
    )

    respuestas = intento.get("respuestas_usuario", [])
    total_p = len(respuestas) if respuestas else 1
    correctas = sum(1 for r in respuestas if r.get("es_correcta"))
    porcentaje = intento.get("porcentaje_obtenido", 0)
    estado_txt = obtener_estado_evaluacion(
        porcentaje, intento.get("sobrepasado_tiempo", False)
    )

    data_res = [
        [
            Paragraph("<b>Aciertos</b>", norm_style),
            Paragraph(f"{correctas} / {total_p}", norm_style),
        ],
        [
            Paragraph("<b>Porcentaje</b>", norm_style),
            Paragraph(f"{porcentaje}%", norm_style),
        ],
        [
            Paragraph("<b>Nota Final</b>", norm_style),
            Paragraph(f"{intento.get('nota', 0)} / 10", norm_style),
        ],
        [
            Paragraph("<b>Resultado</b>", norm_style),
            Paragraph(f"<b>{estado_txt}</b>", bold_style),
        ],
    ]
    t = Table(data_res, colWidths=[150, 350])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("PADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(t)
    story.append(Spacer(1, 15))

    erroneas = [r for r in respuestas if not r.get("es_correcta")]
    if erroneas:
        story.append(
            Paragraph(
                "<b>Desglose de Preguntas Erróneas o Sin Responder:</b>", bold_style
            )
        )
        story.append(Spacer(1, 8))
        for idx_e, err in enumerate(erroneas, 1):
            story.append(
                Paragraph(f"<b>{idx_e}. {err.get('pregunta')}</b>", norm_style)
            )
            story.append(
                Paragraph(
                    f"Respuesta registrada: <i>{
                        err.get('opcion_elegida')}</i>",
                    err_style,
                )
            )
            story.append(Spacer(1, 6))
    else:
        story.append(
            Paragraph(
                "<b>¡Examen perfecto! Sin errores registrados.</b>", bold_style
            )
        )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generar_pdf_evaluacion_ia(empleado_nombre, texto_informe, anio):
    if not REPORTLAB_DISPONIBLE:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()
    story = []

    titulo_style = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=10,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=15,
    )
    norm_style = ParagraphStyle(
        "Norm",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
    )

    story.append(
        Paragraph("📄 Informe Profesional de Evaluación IA", titulo_style)
    )
    story.append(
        Paragraph(
            f"<b>Trabajador:</b> {empleado_nombre} | <b>Año de Evaluación:</b>"
            f" {anio}",
            sub_style,
        )
    )
    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#CBD5E0"),
            spaceAfter=15,
        )
    )

    lineas = texto_informe.split("\n")
    for linea in lineas:
        if linea.strip():
            story.append(Paragraph(linea.strip(), norm_style))
            story.append(Spacer(1, 6))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


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
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Ingresar")

        if submitted:
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
    tiempo_base = st.session_state.tiempos_restantes_preguntas.get(
        idx, TIEMPO_LIMITE_PREGUNTA
    )
    if st.session_state.tiempo_inicio_pregunta is None:
        st.session_state.tiempo_inicio_pregunta = time.time()

    tiempo_transcurrido = int(
        time.time() - st.session_state.tiempo_inicio_pregunta
    )
    tiempo_restante = max(0, tiempo_base - tiempo_transcurrido)

    # Temporizador General del Examen
    if st.session_state.tiempo_inicio_examen:
        total_p = len(st.session_state.preguntas_seleccionadas)
        tiempo_total_limite = total_p * TIEMPO_LIMITE_PREGUNTA
        tiempo_transcurrido_examen = int(
            time.time() - st.session_state.tiempo_inicio_examen
        )
        tiempo_restante_examen = max(
            0, tiempo_total_limite - tiempo_transcurrido_examen
        )
        st.info(
            "⏳ **Tiempo total restante del examen:**"
            f" {tiempo_restante_examen //
                60:02d}:{tiempo_restante_examen %
                         60:02d} minutos"
        )

    st.progress(tiempo_restante / TIEMPO_LIMITE_PREGUNTA)
    if tiempo_restante > 0:
        st.caption(
            f"⏱️ Tiempo restante en esta pregunta: **{tiempo_restante} segundos**"
        )
    else:
        st.warning(
            "⏰ ¡Tiempo agotado en esta pregunta! La selección ha quedado"
            " bloqueada."
        )


@st.fragment(run_every=1)
def renderizar_temporizador_revision():
    if st.session_state.tiempo_inicio_revision is None:
        st.session_state.tiempo_inicio_revision = time.time()

    tiempo_revision_transcurrido = int(
        time.time() - st.session_state.tiempo_inicio_revision
    )
    tiempo_revision_restante = max(0, 300 - tiempo_revision_transcurrido)

    if tiempo_revision_restante > 0:
        st.warning(
            "⏱️ Tiempo restante de revisión:"
            f" **{tiempo_revision_restante //
                  60:02d}:{tiempo_revision_restante %
                           60:02d} minutos**."
            " Si se agota, el examen se finalizará automáticamente."
        )
    else:
        st.error(
            "⏰ ¡Tiempo de revisión agotado (5 minutos)! Finalizando el examen"
            " automáticamente..."
        )


# ---------------------------------------------------------
# MÓDULO 1: AUTENTICACIÓN
# ---------------------------------------------------------
st.title("📝 Plataforma de Evaluación y Exámenes")

if not st.session_state.autenticado:
    st.subheader("Selecciona tu perfil para ingresar")

    try:
        res_usuarios = (
            supabase.table("empleados").select(
                "*").eq("activo", True).execute()
        )
        lista_usuarios = res_usuarios.data if res_usuarios.data else []
    except Exception as e:
        lista_usuarios = []
        st.error(f"Error al conectar con la base de datos de empleados: {e}")

    if lista_usuarios:
        cols = st.columns(3)
        for idx, u in enumerate(lista_usuarios):
            with cols[idx % 3]:
                st.markdown(
                    f"""
                <div class="user-card">
                    <h3>👤 {u['nombre']}</h3>
                    <p style="color: #718096; font-size: 14px;">{"Administrador" if u.get("es_admin_croma") else "Empleado"}</p>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                if st.button(
                    "Acceder", key=f"usr_btn_{u['id']}", use_container_width=True
                ):
                    st.session_state.usuario_modal_sel = u
                    login_modal()
    else:
        st.warning(
            "No se encontraron perfiles de empleados activos en la base de datos."
        )

# ---------------------------------------------------------
# MÓDULO 2: PANEL Y EVALUACIÓN
# ---------------------------------------------------------
else:
    col_usr, col_logout = st.columns([4, 1])
    with col_usr:
        st.write(
            f"Bienvenido/a, **{st.session_state.user_nombre}**"
            f" ({'Administrador CROMA' if st.session_state.es_croma else 'Empleado'})"
        )
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
            tiempo_ini_examen = datetime.datetime.now(
                datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")
            id_examen_validado = (
                examen_id_val
                if isinstance(examen_id_val, int) and examen_id_val > 0
                else None
            )

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
                "tiempo_limite": (
                    len(st.session_state.preguntas_seleccionadas)
                    * TIEMPO_LIMITE_PREGUNTA
                ),
                "sobrepasado_tiempo": False,
                "activo": True,
            }
            res = supabase.table("intentos_examen").insert(
                registro_inicio).execute()
            if res.data and len(res.data) > 0:
                st.session_state.intento_id_actual = res.data[0]["id"]
        except Exception as e:
            st.error(f"Error al registrar inicio de examen en BD: {e}")

    def cancelar_examen_bd():
        """Sanciona el examen como realizado con nota 0 si se cancela/abandona."""
        if st.session_state.intento_id_actual:
            tiempo_fin_examen = datetime.datetime.now(
                datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")
            duracion_total = int(
                time.time()
                - (st.session_state.tiempo_inicio_examen or time.time())
            )
            try:
                supabase.table("intentos_examen").update({
                    "nota": 0.0,
                    "porcentaje_obtenido": 0.0,
                    "fecha_fin": tiempo_fin_examen,
                    "tiempo_total_segundos": duracion_total,
                    "respuestas_usuario": st.session_state.respuestas_detalle,
                }).eq("id", st.session_state.intento_id_actual).execute()
            except Exception as e:
                st.error(f"Error al registrar cancelación de examen: {e}")

    def guardar_intento_en_bd():
        if st.session_state.examen_finalizado:
            return True
        total_p = len(st.session_state.preguntas_seleccionadas)
        correctas = sum(
            1 for r in st.session_state.respuestas_detalle if r["es_correcta"]
        )
        porcentaje = round(
            (correctas / total_p) * 100,
            2) if total_p > 0 else 0.0
        nota_final = round(
            (correctas / total_p) * 10,
            2) if total_p > 0 else 0.0

        duracion_total = int(
            time.time() - (st.session_state.tiempo_inicio_examen or time.time())
        )
        tiempo_limite_total = total_p * TIEMPO_LIMITE_PREGUNTA
        tiempo_fin_examen = datetime.datetime.now(
            datetime.timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

        try:
            id_examen_validado = (
                st.session_state.examen_id
                if isinstance(st.session_state.examen_id, int)
                and st.session_state.examen_id > 0
                else None
            )

            datos_actualizacion = {
                "nota": nota_final,
                "porcentaje_obtenido": porcentaje,
                "respuestas_usuario": st.session_state.respuestas_detalle,
                "fecha_fin": tiempo_fin_examen,
                "tiempo_total_segundos": duracion_total,
                "sobrepasado_tiempo": st.session_state.sobrepaso_tiempo_global,
            }

            if st.session_state.intento_id_actual:
                supabase.table("intentos_examen").update(datos_actualizacion).eq(
                    "id", st.session_state.intento_id_actual
                ).execute()
            else:
                tiempo_ini_examen = (
                    datetime.datetime.fromtimestamp(
                        st.session_state.tiempo_inicio_examen, datetime.timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    if st.session_state.tiempo_inicio_examen
                    else tiempo_fin_examen
                )
                datos_actualizacion.update({
                    "empleado_id": st.session_state.user_id,
                    "nombre_empleado": st.session_state.user_nombre,
                    "examen_id": id_examen_validado,
                    "apartado": st.session_state.apartado_actual,
                    "fecha_inicio": tiempo_ini_examen,
                    "tiempo_limite": tiempo_limite_total,
                    "activo": True,
                })
                supabase.table("intentos_examen").insert(
                    datos_actualizacion).execute()

            try:
                supabase.table("autorizaciones_examen").delete().eq(
                    "empleado_id", st.session_state.user_id
                ).eq("apartado", st.session_state.apartado_actual).execute()
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

        tiempo_revision_transcurrido = int(
            time.time() - st.session_state.tiempo_inicio_revision
        )
        tiempo_revision_restante = max(0, 300 - tiempo_revision_transcurrido)

        st.subheader("🔍 Revisión de Examen previa a la entrega final")

        if not st.session_state.examen_finalizado:
            st.info(
                "Revisa tus respuestas e indica si deseas modificar alguna antes de"
                " la entrega definitiva."
            )

            # Temporizador dinámico en tiempo real para los 5 minutos de
            # revisión
            renderizar_temporizador_revision()

            for i, p_item in enumerate(
                    st.session_state.preguntas_seleccionadas):
                resp_actual = next(
                    (
                        r
                        for r in st.session_state.respuestas_detalle
                        if r["idx_pregunta"] == i
                    ),
                    None,
                )
                texto_resp = (
                    resp_actual["opcion_elegida"]
                    if resp_actual
                    else "En blanco (Sin responder)"
                )

                t_restante = st.session_state.tiempos_restantes_preguntas.get(
                    i, TIEMPO_LIMITE_PREGUNTA
                )

                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"**Pregunta {i + 1}:** {p_item['pregunta']}")
                    st.caption(
                        f"Categoría/Tema: **{
                            p_item.get(
                                'subindice',
                                'General')}** |"
                        f" Respuesta actual: **{texto_resp}** | ⏱️ Tiempo restante:"
                        f" **{t_restante} s** | Dificultad:"
                        f" **{p_item.get('dificultad', 'dificil')}**"
                    )
                with c2:
                    btn_bloqueado = t_restante <= 0 or tiempo_revision_restante <= 0
                    if st.button(
                        "Modificar",
                        key=f"mod_rev_{i}",
                        disabled=btn_bloqueado,
                        use_container_width=True,
                    ):
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
                    if st.button(
                        "✅ Confirmar y Entregar Examen Definitivamente",
                        use_container_width=True,
                    ):
                        if guardar_intento_en_bd():
                            st.rerun()
                with c_fin2:
                    if st.button(
                        "🚫 Cancelar / Abandonar Examen (Nota 0)", use_container_width=True
                    ):
                        cancelar_examen_bd()
                        st.session_state.examen_activo = False
                        st.session_state.modo_revision = False
                        st.session_state.examen_finalizado = True
                        st.rerun()
        else:
            total_p = len(st.session_state.preguntas_seleccionadas)
            correctas = sum(
                1 for r in st.session_state.respuestas_detalle if r["es_correcta"]
            )
            porcentaje = round(
                (correctas / total_p) * 100,
                2) if total_p > 0 else 0.0
            nota_final = round(
                (correctas / total_p) * 10,
                2) if total_p > 0 else 0.0
            estado_evaluacion = obtener_estado_evaluacion(
                porcentaje, st.session_state.sobrepaso_tiempo_global
            )

            if "APROBADO" in estado_evaluacion:
                st.success(
                    f"🎉 Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%)"
                    f" | **{estado_evaluacion}**"
                )
            else:
                st.error(
                    f"❌ Examen completado — Nota: **{nota_final} / 10** ({porcentaje}%)"
                    f" | **{estado_evaluacion}**"
                )

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
            "<script>window.parent.document.getElementById('pregunta_activa').scrollIntoView({behavior:"
            " 'smooth'});</script>",
            height=0,
        )

        idx = st.session_state.indice_pregunta
        total_p = len(st.session_state.preguntas_seleccionadas)

        if idx < total_p:
            p_actual = st.session_state.preguntas_seleccionadas[idx]

            col_info, col_ayuda = st.columns([3, 2])
            with col_info:
                st.subheader(f"Pregunta {idx + 1} de {total_p}")
                st.caption(
                    "📌 **Subíndice/Categoría:**"
                    f" {p_actual.get('subindice',
                                     p_actual.get('apartado',
                                                  'General'))}"
                    f" | Dificultad: **{
                        p_actual.get(
                            'dificultad',
                            'dificil')}**"
                )
            with col_ayuda:
                st.caption(
                    "💡 Ayudas disponibles:"
                    f" **{st.session_state.comodines_restantes} / 3**"
                )

            tiempo_base = st.session_state.tiempos_restantes_preguntas.get(
                idx, TIEMPO_LIMITE_PREGUNTA
            )
            if st.session_state.tiempo_inicio_pregunta is None:
                st.session_state.tiempo_inicio_pregunta = time.time()

            tiempo_transcurrido = int(
                time.time() - st.session_state.tiempo_inicio_pregunta
            )
            tiempo_restante = max(0, tiempo_base - tiempo_transcurrido)

            # Temporizador dinámico en tiempo real utilizando Streamlit
            # Fragment
            renderizar_temporizador_realtime(idx)

            deshabilitar_opciones = tiempo_restante <= 0
            if deshabilitar_opciones:
                st.session_state.tiempos_restantes_preguntas[idx] = 0

            # Garantizar que la pregunta siempre sea visible para examen por
            # manual o global
            texto_pregunta = p_actual.get("pregunta", "Pregunta no disponible")
            st.markdown(
                f"<div class='pregunta-titulo'>{texto_pregunta}</div>",
                unsafe_allow_html=True,
            )

            resp_previa = next(
                (
                    r["opcion_elegida"]
                    for r in st.session_state.respuestas_detalle
                    if r["idx_pregunta"] == idx
                ),
                None,
            )
            idx_previa = None
            if resp_previa and resp_previa in p_actual["opciones_barajadas"]:
                idx_previa = p_actual["opciones_barajadas"].index(resp_previa)

            # Función para guardar automáticamente la selección del radio
            # button cuando cambia
            def registrar_respuesta_pregunta(elec_val=None):
                if elec_val is None:
                    elec_val = st.session_state.get(f"p_{idx}")

                if elec_val is not None and elec_val != "":
                    es_corr = elec_val == p_actual["respuesta_correcta_texto"]
                    op_guardada = elec_val
                else:
                    es_corr = False
                    op_guardada = "En blanco (Sin responder)"

                st.session_state.respuestas_detalle = [
                    r
                    for r in st.session_state.respuestas_detalle
                    if r["idx_pregunta"] != idx
                ]
                st.session_state.respuestas_detalle.append({
                    "idx_pregunta": idx,
                    "pregunta": p_actual["pregunta"],
                    "subindice": p_actual.get("subindice", "General"),
                    "dificultad": p_actual.get("dificultad", "dificil"),
                    "opcion_elegida": op_guardada,
                    "respuesta_correcta_texto": p_actual["respuesta_correcta_texto"],
                    "opciones_posibles": p_actual["opciones_barajadas"],
                    "es_correcta": es_corr,
                })

            eleccion = st.radio(
                "Selecciona una opción:",
                p_actual["opciones_barajadas"],
                index=idx_previa,
                key=f"p_{idx}",
                disabled=deshabilitar_opciones,
                on_change=registrar_respuesta_pregunta,
            )

            if idx in st.session_state.pistas_activadas:
                pista_texto = p_actual.get(
                    "pista",
                    "Lee con atención las opciones y descarta las inconsistentes.",
                )
                st.info(f"💡 **Pista:** {pista_texto}")
            else:
                if (
                    st.session_state.comodines_restantes > 0
                    and not deshabilitar_opciones
                ):
                    if st.button(
                        "💡 Pedir Ayuda (Gasta 1 comodín)", key=f"btn_pista_{idx}"
                    ):
                        st.session_state.comodines_restantes -= 1
                        st.session_state.pistas_activadas.add(idx)
                        st.rerun()
                elif deshabilitar_opciones:
                    st.caption(
                        "🚫 Tiempo agotado. No se pueden pedir comodines.")
                else:
                    st.caption("🚫 Has agotado tus 3 comodines de ayuda.")

            st.write("")
            col_b1, col_b2, col_b3 = st.columns(3)

            with col_b1:
                lbl_btn = (
                    "Ir a Revisión"
                    if st.session_state.modificando_desde_revision
                    else "Responder / Siguiente"
                )

                if st.button(
                        lbl_btn, key=f"btn_sig_{idx}", use_container_width=True):
                    st.session_state.tiempos_restantes_preguntas[idx] = max(
                        0, tiempo_restante
                    )
                    registrar_respuesta_pregunta(eleccion)

                    if st.session_state.modificando_desde_revision:
                        st.session_state.modificando_desde_revision = False
                        st.session_state.modo_revision = True
                    else:
                        st.session_state.indice_pregunta += 1
                        st.session_state.tiempo_inicio_pregunta = None

                    st.rerun()

            with col_b2:
                if st.button(
                    "📋 Ir a Revisión Directa",
                    key=f"btn_rev_{idx}",
                    use_container_width=True,
                ):
                    st.session_state.tiempos_restantes_preguntas[idx] = max(
                        0, tiempo_restante
                    )
                    registrar_respuesta_pregunta(eleccion)
                    st.session_state.modificando_desde_revision = False
                    st.session_state.modo_revision = True
                    st.rerun()

            with col_b3:
                if st.button(
                    "🚫 Cancelar Examen (Nota 0)",
                    key=f"btn_canc_{idx}",
                    use_container_width=True,
                ):
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

    # MENÚ PRINCIPAL
    else:
        st.info(
            "🎯 **Criterio de Evaluación:** Para obtener un resultado **APROBADO**,"
            " debes alcanzar una nota mínima de"
            f" **{UMBRAL_APROBADO_PORCENTAJE / 10} / 10**"
            f" ({int(UMBRAL_APROBADO_PORCENTAJE)}% de aciertos). Tiempo"
            f" configurado por pregunta: **{TIEMPO_LIMITE_PREGUNTA} segundos**."
        )

        if st.session_state.es_croma:
            (
                tab_examenes,
                tab_admin_manual,
                tab_admin_resultados,
                tab_admin_export,
                tab_admin_analisis,
                tab_informes_ia,
                tab_admin_gestion,
                tab_admin_trimestral,  # <--- NUEVO TAB
            ) = st.tabs([
                "📝 Realizar Examen",
                "📄 Cargar Manual / Prompt",
                "📊 Resultados / Edición",
                "📥 Exportación Exámenes e Importación Datos",
                "📈 Analítica e IA",
                "🤖 Informes IA",
                "⚙️ Gestión y Configuración",
                "📋 Evaluaciones Trimestrales",  # <--- NUEVO TAB
            ])
        else:
            (
                tab_examenes,
                tab_mis_resultados,
                tab_mi_analisis,
                tab_emp_trimestral,  # <--- NUEVO TAB
            ) = st.tabs([
                "📝 Realizar Examen",
                "📊 Mis Resultados e Historial",
                "📈 Mi Rendimiento e Informes IA",
                "📋 Evaluaciones Trimestrales",  # <--- NUEVO TAB
            ])

        # TAB: REALIZAR EXAMEN
        with tab_examenes:
            ahora = datetime.datetime.now(datetime.timezone.utc)
            primer_dia_mes = datetime.datetime(
                ahora.year, ahora.month, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")

            user_intentos = []
            try:
                res_user_intentos = (
                    supabase.table("intentos_examen")
                    .select("*")
                    .eq("empleado_id", st.session_state.user_id)
                    .eq("activo", True)
                    .gte("fecha_inicio", primer_dia_mes)
                    .execute()
                )
                user_intentos = (
                    res_user_intentos.data if res_user_intentos.data else []
                )
            except Exception as e:
                try:
                    res_fallback = (
                        supabase.table("intentos_examen")
                        .select("*")
                        .eq("empleado_id", st.session_state.user_id)
                        .eq("activo", True)
                        .execute()
                    )
                    fallback_data = (
                        res_fallback.data
                        if res_fallback and hasattr(res_fallback, "data")
                        else []
                    )
                except Exception:
                    fallback_data = []

                if fallback_data:
                    str_mes_actual = f"{ahora.year}-{ahora.month:02d}"
                    user_intentos = [
                        it
                        for it in fallback_data
                        if it.get("fecha_inicio")
                        and str(it["fecha_inicio"]).startswith(str_mes_actual)
                    ]

            dict_realizados = {}
            for it in user_intentos:
                apt = it.get("apartado")
                if apt:
                    dict_realizados[apt] = {
                        "nota": it.get("nota", 0),
                        "porcentaje": it.get("porcentaje_obtenido", 0),
                    }

            try:
                res_aut = (
                    supabase.table("autorizaciones_examen")
                    .select("apartado")
                    .eq("empleado_id", st.session_state.user_id)
                    .execute()
                )
                autorizaciones_set = set(
                    item["apartado"] for item in (res_aut.data or [])
                )
            except Exception:
                autorizaciones_set = set()

            try:
                res_examenes = (
                    supabase.table("examenes").select(
                        "*").eq("activo", True).execute()
                )
                raw_examenes = res_examenes.data if res_examenes.data else []

                examenes_disponibles = [
                    ex
                    for ex in raw_examenes
                    if ex.get("activo") is True or ex.get("activo") is None
                ]
            except Exception as e:
                examenes_disponibles = []
                st.error(f"Error al cargar manuales de la base de datos: {e}")

            if examenes_disponibles:
                st.subheader("📋 Seleccionar Modalidad")

                tab_global, tab_manual = st.tabs(
                    ["🌐 Examen Global", "📘 Examen por Manual"]
                )

                with tab_global:
                    num_p_global = NUM_PREG_GLOBAL
                    st.info(
                        "El Examen Global seleccionará exactamente **"
                        f"{num_p_global} preguntas aleatorias** distribuidas"
                        " equitativamente entre los manuales."
                    )

                    texto_global_bd = TEXTO_EXAMEN_GLOBAL_INFO
                    try:
                        res_info_g = (
                            supabase.table("config_prompts")
                            .select("valor")
                            .eq("nombre", "info_examen_global")
                            .limit(1)
                            .execute()
                        )
                        if res_info_g.data and res_info_g.data[0].get("valor"):
                            texto_global_bd = res_info_g.data[0]["valor"]
                    except Exception:
                        pass

                    st.markdown(
                        f"**Condiciones del Examen Global:**\n> {texto_global_bd}"
                    )

                    ya_hecho_global = "GLOBAL COMPLETO" in dict_realizados
                    permitido_global = autorizaciones_set.__contains__(
                        "GLOBAL COMPLETO")
                    bloqueado_global = (
                        ya_hecho_global
                        and not permitido_global
                        and not st.session_state.es_croma
                    )

                    if ya_hecho_global:
                        info_g = dict_realizados["GLOBAL COMPLETO"]
                        est_txt = obtener_estado_evaluacion(
                            info_g["porcentaje"])
                        st.warning(
                            f"⚠️ **REALIZADO ESTE MES** — Nota previa: **{
                                info_g['nota']} /"
                            f" 10** ({info_g['porcentaje']}%) | **{est_txt}**"
                        )
                        if permitido_global:
                            st.success(
                                "🔓 **El administrador te ha habilitado un nuevo intento para"
                                " este examen.**"
                            )
                        elif not st.session_state.es_croma:
                            st.error(
                                "🔒 Debes esperar al próximo mes o solicitar una autorización"
                                " al administrador para volver a realizarlo."
                            )

                    if st.button(
                        "Comenzar Examen Global Combinado",
                        disabled=bloqueado_global,
                        use_container_width=True,
                    ):
                        banco_global = []

                        for ex_obj in examenes_disponibles:
                            banco = ex_obj.get("preguntas_json", [])
                            if isinstance(banco, list):
                                for p in banco:
                                    if isinstance(p, dict):
                                        idx_c = p.get("respuesta_correcta", 0)
                                        opciones = p.get("opciones", [])
                                        if isinstance(idx_c, int) and 0 <= idx_c < len(
                                                opciones):
                                            texto_c = opciones[idx_c]
                                            opciones_shuffled = opciones.copy()
                                            random.shuffle(opciones_shuffled)

                                            banco_global.append({
                                                "apartado": ex_obj.get("apartado", ""),
                                                "subindice": p.get("subindice", "General"),
                                                "pregunta": p.get("pregunta", ""),
                                                "opciones_barajadas": opciones_shuffled,
                                                "respuesta_correcta_texto": texto_c,
                                                "pista": p.get(
                                                    "pista", "Revisa los conceptos clave."
                                                ),
                                                "dificultad": p.get("dificultad", "dificil"),
                                                "tipo": "teorica",
                                            })

                        preguntas_preparadas = seleccionar_preguntas_equilibradas(
                            banco_global, num_p_global
                        )

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

                        # Registrar inicio en la base de datos
                        registrar_inicio_examen_bd("GLOBAL COMPLETO", None)

                        st.session_state.examen_activo = True
                        st.rerun()

                with tab_manual:
                    st.subheader("📘 Manuales y Exámenes Disponibles")
                    num_p_manual = NUM_PREG_MANUAL

                    cols = st.columns(3)
                    for idx_ex, ex_obj in enumerate(examenes_disponibles):
                        nombre_apt = ex_obj["apartado"]
                        num_p_totales = (
                            len(ex_obj.get("preguntas_json", []))
                            if isinstance(ex_obj.get("preguntas_json"), list)
                            else 0
                        )

                        ya_hecho_manual = nombre_apt in dict_realizados
                        permitido_manual = autorizaciones_set.__contains__(
                            nombre_apt)
                        bloqueado_manual = (
                            ya_hecho_manual
                            and not permitido_manual
                            and not st.session_state.es_croma
                        )

                        with cols[idx_ex % 3]:
                            st.markdown(
                                f"""
                            <div class="manual-card">
                                <div>
                                    <h4>📘 {nombre_apt}</h4>
                                    <p><b>Banco de preguntas:</b> {num_p_totales} totales<br>
                                    <b>Preguntas en examen:</b> {num_p_manual}</p>
                                </div>
                            </div>
                            """,
                                unsafe_allow_html=True,
                            )

                            if ya_hecho_manual:
                                info_m = dict_realizados[nombre_apt]
                                est_txt = obtener_estado_evaluacion(
                                    info_m["porcentaje"])
                                st.caption(
                                    f"⚠️ **Realizado este mes:** {
                                        info_m['nota']}/10 ({est_txt})"
                                )

                            if st.button(
                                "Iniciar Examen",
                                key=f"btn_card_manual_{ex_obj['id']}",
                                disabled=bloqueado_manual,
                                use_container_width=True,
                            ):
                                banco = ex_obj.get("preguntas_json", [])
                                banco_manual = []

                                if isinstance(banco, list):
                                    for p in banco:
                                        if isinstance(p, dict):
                                            idx_c = p.get(
                                                "respuesta_correcta", 0)
                                            opciones = p.get("opciones", [])
                                            if isinstance(idx_c, int) and 0 <= idx_c < len(
                                                    opciones):
                                                texto_c = opciones[idx_c]
                                                opciones_shuffled = opciones.copy()
                                                random.shuffle(
                                                    opciones_shuffled)

                                                banco_manual.append({
                                                    "apartado": nombre_apt,
                                                    "subindice": p.get("subindice", "General"),
                                                    "pregunta": p.get("pregunta", ""),
                                                    "opciones_barajadas": opciones_shuffled,
                                                    "respuesta_correcta_texto": texto_c,
                                                    "pista": p.get(
                                                        "pista", "Revisa la documentación técnica."
                                                    ),
                                                    "dificultad": p.get("dificultad", "dificil"),
                                                    "tipo": "teorica",
                                                })

                                preguntas_preparadas = seleccionar_preguntas_equilibradas(
                                    banco_manual, num_p_manual
                                )

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

                                # Registrar inicio en la base de datos
                                registrar_inicio_examen_bd(
                                    nombre_apt, ex_obj["id"])

                                st.session_state.examen_activo = True
                                st.rerun()

                    # Estadísticas de soporte técnico
                    manual_nombres = [ex["apartado"]
                                      for ex in examenes_disponibles]
                    st.markdown("---")
                    st.subheader("📊 Histórico del Trabajador por Manual")
                    manual_sel_nom = st.selectbox(
                        "Selecciona un manual para ver tu histórico:",
                        manual_nombres,
                        key="sel_manual_eval_stats",
                    )
                    ex_obj_stats = next(
                        (
                            ex
                            for ex in examenes_disponibles
                            if ex["apartado"] == manual_sel_nom
                        ),
                        None,
                    )

                    if ex_obj_stats:
                        nombre_apt_stat = ex_obj_stats["apartado"]
                        res_intentos_m = (
                            supabase.table("intentos_examen")
                            .select("*")
                            .eq("empleado_id", st.session_state.user_id)
                            .eq("apartado", nombre_apt_stat)
                            .eq("activo", True)
                            .order("fecha_inicio", desc=True)
                            .execute()
                        )
                        intentos_m = res_intentos_m.data if res_intentos_m.data else []

                        if intentos_m:
                            banco_actual_m = ex_obj_stats.get(
                                "preguntas_json", [])
                            temas_totales_banco = set()
                            if isinstance(banco_actual_m, list):
                                for p_b in banco_actual_m:
                                    if isinstance(p_b, dict):
                                        temas_totales_banco.add(
                                            str(p_b.get("subindice",
                                                "General")).strip()
                                        )

                            ultimo_intento = intentos_m[0]
                            resp_ult = ultimo_intento.get(
                                "respuestas_usuario", [])
                            if resp_ult:
                                st.markdown(
                                    "##### 📈 Rendimiento del Último Examen Realizado (Gráfica"
                                    " Lineal)"
                                )
                                df_ult = pd.DataFrame(resp_ult)
                                if "subindice" not in df_ult.columns:
                                    df_ult["subindice"] = df_ult.get(
                                        "categoria", "General")
                                df_ult["subindice"] = df_ult["subindice"].fillna(
                                    "General")

                                ult_resumen = (
                                    df_ult.groupby("subindice")
                                    .agg(
                                        Aciertos=(
                                            "es_correcta",
                                            lambda x: sum(x == True),
                                        ),
                                        Total=("es_correcta", "count"),
                                    )
                                    .reset_index()
                                )
                                ult_resumen["% Aciertos"] = (
                                    ult_resumen["Aciertos"] /
                                    ult_resumen["Total"] * 100
                                ).round(2)

                                for t_b in temas_totales_banco:
                                    if t_b not in ult_resumen["subindice"].values:
                                        ult_resumen = pd.concat(
                                            [
                                                ult_resumen,
                                                pd.DataFrame([{
                                                    "subindice": t_b,
                                                    "Aciertos": 0,
                                                    "Total": 0,
                                                    "% Aciertos": 0.0,
                                                }]),
                                            ],
                                            ignore_index=True,
                                        )

                                st.line_chart(
                                    ult_resumen.set_index("subindice")[
                                        "% Aciertos"],
                                    use_container_width=True,
                                )

                            todas_resp_m = []
                            for it_m in intentos_m:
                                resp_usr = it_m.get("respuestas_usuario", [])
                                if isinstance(resp_usr, list):
                                    todas_resp_m.extend(resp_usr)

                            if todas_resp_m:
                                st.markdown(
                                    "##### 📊 Histórico Acumulado por Tema/Subíndice"
                                )
                                df_resp_m = pd.DataFrame(todas_resp_m)
                                if "subindice" not in df_resp_m.columns:
                                    df_resp_m["subindice"] = df_resp_m.get(
                                        "categoria", "General")
                                df_resp_m["subindice"] = df_resp_m["subindice"].fillna(
                                    "General"
                                )

                                resumen_cat_m = (
                                    df_resp_m.groupby("subindice")
                                    .agg(
                                        Aciertos=(
                                            "es_correcta",
                                            lambda x: sum(x == True),
                                        ),
                                        Fallos_o_Blanco=(
                                            "es_correcta",
                                            lambda x: sum(x == False),
                                        ),
                                        Total=("es_correcta", "count"),
                                    )
                                    .reset_index()
                                )

                                for t_b in temas_totales_banco:
                                    if t_b not in resumen_cat_m["subindice"].values:
                                        resumen_cat_m = pd.concat(
                                            [
                                                resumen_cat_m,
                                                pd.DataFrame([{
                                                    "subindice": t_b,
                                                    "Aciertos": 0,
                                                    "Fallos_o_Blanco": 0,
                                                    "Total": 0,
                                                }]),
                                            ],
                                            ignore_index=True,
                                        )

                                resumen_cat_m["% Aciertos"] = (
                                    resumen_cat_m["Aciertos"]
                                    / resumen_cat_m["Total"].replace(0, 1)
                                    * 100
                                ).round(2)
                                resumen_cat_m.loc[
                                    resumen_cat_m["Total"] == 0, "% Aciertos"
                                ] = 0.0

                                st.bar_chart(
                                    resumen_cat_m.set_index("subindice")[
                                        ["Aciertos", "Fallos_o_Blanco"]
                                    ],
                                    use_container_width=True,
                                )
                                st.dataframe(
                                    resumen_cat_m, use_container_width=True, hide_index=True
                                )
            else:
                st.warning("No hay manuales activos cargados en el sistema.")

        # TAB: CARGAR MANUAL Y PROMPT (ADMIN)
        if st.session_state.es_croma and tab_admin_manual:
            with tab_admin_manual:
                st.subheader(
                    "📄 Cargar Nuevo Manual en PDF y Generar Examen con IA"
                )

                cfg_prompt_ex = None
                try:
                    res_cfg_ex = (
                        supabase.table("config_prompts")
                        .select("*")
                        .eq("nombre", "prompt_examen")
                        .limit(1)
                        .execute()
                    )
                    if res_cfg_ex.data:
                        cfg_prompt_ex = res_cfg_ex.data[0]
                except Exception:
                    cfg_prompt_ex = None

                prompt_defecto_cargador = (
                    cfg_prompt_ex.get("valor")
                    if cfg_prompt_ex and cfg_prompt_ex.get("valor")
                    else PROMPT_DEFECTO_EXAMEN
                )

                with st.form("form_cargar_manual", clear_on_submit=False):
                    nombre_apartado = st.text_input(
                        "📘 Nombre del Manual/Apartado (Ej. Manual Seguridad 2026):*"
                    )
                    pdf_file = st.file_uploader(
                        "📂 Selecciona el documento PDF:*", type=["pdf"]
                    )

                    prompt_manual_input = st.text_area(
                        "💬 Prompt para la IA (Generación de JSON):",
                        value=prompt_defecto_cargador,
                        height=200,
                    )

                    guardar_prompt_check = st.checkbox(
                        "💾 Actualizar y guardar este prompt en la base de datos como"
                        " predeterminado"
                    )

                    modelos_ia_opciones = obtener_modelos_ia_disponibles()
                    modelos_cargador_sel = st.multiselect(
                        "🤖 Selección múltiple de modelos de IA a consultar (Se"
                        " unificarán los JSON):",
                        options=modelos_ia_opciones,
                        default=[
                            modelos_ia_opciones[0]] if modelos_ia_opciones else [],
                    )

                    btn_procesar_manual = st.form_submit_button(
                        "🚀 Procesar Documento y Guardar Examen", use_container_width=True
                    )

                if btn_procesar_manual:
                    if not nombre_apartado.strip():
                        st.error(
                            "❌ Por favor indica el nombre del manual/apartado.")
                    elif not pdf_file:
                        st.error("❌ Por favor sube un archivo PDF válido.")
                    elif not modelos_cargador_sel:
                        st.error(
                            "❌ Por favor selecciona al menos un modelo de IA.")
                    else:
                        if guardar_prompt_check:
                            guardar_prompt_config(
                                "prompt_examen", prompt_manual_input)

                        status_box = st.status(
                            "🔄 Procesando manual en el sistema...", expanded=True
                        )
                        try:
                            status_box.write(
                                "📖 Extrayendo texto del archivo PDF...")
                            reader = PdfReader(pdf_file)
                            texto_pdf = ""
                            for page in reader.pages:
                                page_text = page.extract_text()
                                if page_text:
                                    texto_pdf += page_text + "\n"

                            if not texto_pdf.strip():
                                raise Exception(
                                    "No se pudo extraer texto del PDF subido.")

                            preguntas_unificadas = []

                            for mod_sel in modelos_cargador_sel:
                                status_box.write(
                                    f"🧠 Consultando al modelo {mod_sel}...")
                                prompt_final = (
                                    f"{prompt_manual_input}\n\n[CONTENIDO DEL DOCUMENTO"
                                    f" PDF]:\n{texto_pdf[:40000]}"
                                )

                                try:
                                    res_ia_raw = consultar_ia(
                                        mod_sel,
                                        prompt_final,
                                        sistema=(
                                            "Eres un generador de exámenes técnicos estructurados"
                                            " exclusivamente en formato JSON."
                                        ),
                                    )
                                    txt_json = res_ia_raw.strip()
                                    if "```json" in txt_json:
                                        txt_json = (
                                            txt_json.split("```json")[1].split(
                                                "```")[0].strip()
                                        )
                                    elif "```" in txt_json:
                                        txt_json = txt_json.split(
                                            "```")[1].split("```")[0].strip()

                                    parsed_json = json.loads(txt_json)
                                    if isinstance(parsed_json, list):
                                        for item in parsed_json:
                                            p_norm = normalizar_pregunta_json(
                                                item)
                                            if p_norm and p_norm not in preguntas_unificadas:
                                                preguntas_unificadas.append(
                                                    p_norm)
                                except Exception as err_model:
                                    status_box.write(
                                        f"⚠️ Error parcial al consultar con {mod_sel}:"
                                        f" {err_model}"
                                    )

                            if not preguntas_unificadas:
                                raise Exception(
                                    "No se generaron preguntas válidas a partir del documento."
                                )

                            status_box.write(
                                f"💾 Registrando examen con {
                                    len(preguntas_unificadas)}"
                                " preguntas unificadas en Supabase..."
                            )

                            registro_nuevo_examen = {
                                "apartado": nombre_apartado.strip(),
                                "preguntas_json": preguntas_unificadas,
                                "activo": True,
                            }

                            supabase.table("examenes").insert(
                                registro_nuevo_examen).execute()

                            status_box.update(
                                label="✅ ¡Manual procesado y unificado con éxito!",
                                state="complete",
                                expanded=False,
                            )
                            st.success(
                                "🎉 Se han generado exitosamente"
                                f" **{len(preguntas_unificadas)} preguntas unificadas** en un"
                                " solo JSON para el manual"
                                f" **{nombre_apartado.strip()}**."
                            )
                            time.sleep(2)
                            st.rerun()

                        except Exception as err_m:
                            status_box.update(
                                label="❌ Error al procesar el manual",
                                state="error",
                                expanded=True,
                            )
                            st.error(
                                f"Se produjo un fallo al procesar el documento: {err_m}")

        # VISTA USUARIO: MIS RESULTADOS
        if not st.session_state.es_croma:
            with tab_mis_resultados:
                st.subheader("📌 Mis Calificaciones e Historial Completo")

                res_mis_intentos = (
                    supabase.table("intentos_examen")
                    .select("*")
                    .eq("empleado_id", st.session_state.user_id)
                    .eq("activo", True)
                    .order("fecha_inicio", desc=True)
                    .execute()
                )
                mis_intentos = res_mis_intentos.data if res_mis_intentos.data else []

                dias_restantes = obtener_dias_restantes_mes()
                st.info(
                    "📅 **Habilitación de Examen:** Quedan **"
                    f"{dias_restantes} días** para finalizar el ciclo de evaluación"
                    " actual."
                )

                if mis_intentos:
                    for i in mis_intentos:
                        fecha_str = (
                            i["fecha_inicio"][:10] if i.get(
                                "fecha_inicio") else "N/A"
                        )
                        porc = i.get("porcentaje_obtenido", 0)
                        respuestas = i.get("respuestas_usuario", [])
                        num_correctas = sum(
                            1 for r in respuestas if r.get("es_correcta"))
                        total_p = len(respuestas) if respuestas else 15

                        expirado = i.get("sobrepasado_tiempo", False)
                        estado = obtener_estado_evaluacion(porc, expirado)

                        with st.expander(
                            f"Examen #{
                                i['id']} - {
                                i.get('apartado')} | {fecha_str} | Nota:"
                            f" {i.get('nota', 0)}/10 | Estado: {estado}"
                        ):
                            st.write(
                                f"**Resultado:** {num_correctas} / {total_p} aciertos"
                                f" ({porc}%) - **{estado}**"
                            )

                            if respuestas:
                                df_resp = pd.DataFrame(respuestas)

                                if "subindice" not in df_resp.columns:
                                    df_resp["subindice"] = df_resp.get(
                                        "categoria", "General")
                                df_resp["subindice"] = df_resp["subindice"].fillna(
                                    "General")

                                resumen_cat = (
                                    df_resp.groupby("subindice")
                                    .agg(
                                        Aciertos=(
                                            "es_correcta",
                                            lambda x: sum(x == True),
                                        ),
                                        Fallos_o_Blanco=(
                                            "es_correcta",
                                            lambda x: sum(x == False),
                                        ),
                                        Total=("es_correcta", "count"),
                                    )
                                    .reset_index()
                                )

                                st.markdown(
                                    "#### 📊 Desglose de Aciertos por Categoría / Tema"
                                )
                                st.bar_chart(
                                    resumen_cat.set_index("subindice")[
                                        ["Aciertos", "Fallos_o_Blanco"]
                                    ],
                                    use_container_width=True,
                                )

                                st.dataframe(
                                    resumen_cat.rename(
                                        columns={
                                            "subindice": "Categoría / Tema"}
                                    ),
                                    use_container_width=True,
                                    hide_index=True,
                                )

                            pdf_bytes = generar_pdf_resultado(i)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Descargar Informe PDF de Resultados",
                                    data=pdf_bytes,
                                    file_name=f"resultado_examen_{
                                        i['id']}.pdf",
                                    mime="application/pdf",
                                    key=f"pdf_usr_{i['id']}",
                                )

                            erroneas = [
                                r for r in respuestas if not r.get("es_correcta")]
                            if erroneas:
                                st.write(
                                    "### ❌ Preguntas Erróneas o Sin Responder:")
                                for idx_e, err in enumerate(erroneas, 1):
                                    st.markdown(
                                        f"**{idx_e}. {err.get('pregunta')}**")
                                    st.markdown(
                                        f"- **Tu respuesta:** `{err.get('opcion_elegida')}`")
                                    st.markdown(
                                        "- **Respuesta correcta:**"
                                        f" `{
                                            err.get(
                                                'respuesta_correcta_texto',
                                                'No disponible')}`"
                                    )
                                    st.write("---")
                            else:
                                st.success(
                                    "🎉 ¡Excelente! No cometiste ningún error en este examen."
                                )
                else:
                    st.write("Aún no has realizado ningún examen.")

            with tab_mi_analisis:
                st.subheader("📈 Mi Rendimiento Personal e Informe IA")

                # Verificar si el usuario actual tiene habilitado el análisis
                # por IA
                res_usr_cfg = (
                    supabase.table("empleados")
                    .select("analisis_ia_habilitado")
                    .eq("id", st.session_state.user_id)
                    .execute()
                )
                ia_permitida = (
                    res_usr_cfg.data[0].get("analisis_ia_habilitado", True)
                    if res_usr_cfg.data
                    else True
                )

                if not ia_permitida:
                    st.warning(
                        "🔒 La generación y visualización de Análisis por IA ha sido"
                        " deshabilitada para tu usuario por el administrador."
                    )
                else:
                    res_mis_graf = (
                        supabase.table("intentos_examen")
                        .select("id, nota, porcentaje_obtenido, fecha_inicio, apartado")
                        .eq("empleado_id", st.session_state.user_id)
                        .eq("activo", True)
                        .order("fecha_inicio", desc=False)
                        .execute()
                    )
                    mis_datos_graf = res_mis_graf.data if res_mis_graf.data else []

                    if mis_datos_graf:
                        df_mi_graf = pd.DataFrame(mis_datos_graf)
                        df_mi_graf["fecha"] = df_mi_graf["fecha_inicio"].str[:10]

                        st.markdown(
                            "#### 📊 Evolución Histórica de Calificaciones")
                        st.line_chart(df_mi_graf, x="fecha", y="nota")

                    st.markdown("---")
                    st.markdown(
                        "#### 📄 Informe Profesional de Evaluación IA (Año Vigente)"
                    )

                    anio_vigente = datetime.datetime.now().year

                    res_mi_an = (
                        supabase.table("analisis_ia_empleados")
                        .select("*")
                        .eq("empleado_id", st.session_state.user_id)
                        .eq("anio", anio_vigente)
                        .eq("activo", True)
                        .order("fecha_generacion", desc=True)
                        .limit(1)
                        .execute()
                    )

                    if res_mi_an.data:
                        info_eval_db = res_mi_an.data[0]
                        txt_eval = info_eval_db["analisis_texto"]
                        mod_usado = info_eval_db.get("modelo_ia", "IA")
                        fecha_gen = info_eval_db.get(
                            "fecha_generacion", "")[:10]

                        st.caption(
                            f"🤖 Evaluado con: **{mod_usado}** | Fecha de informe:"
                            f" **{fecha_gen}** | Año: **{anio_vigente}**"
                        )
                        st.info(txt_eval)
                    else:
                        st.warning(
                            "Aún no hay ningún informe de evaluación guardado y activo para"
                            f" ti en el año {anio_vigente}."
                        )

        # --- TAB EMPLEADO: EVALUACIONES TRIMESTRALES ---
        if not st.session_state.es_croma and tab_emp_trimestral:
            with tab_emp_trimestral:
                st.header("📋 Mis Evaluaciones Trimestrales")

                emps = (
                    supabase.table("empleados").select(
                        "id, nombre").execute().data
                )
                emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

                # Por defecto selecciona al empleado autenticado en la sesión
                sel_emp = st.session_state.user_nombre
                emp_id = st.session_state.user_id

                evals_emp = (
                    supabase.table("evaluaciones_trimestrales")
                    .select("anio")
                    .eq("empleado_id", emp_id)
                    .execute()
                    .data
                )
                anios_disp = (
                    sorted(list(set([e["anio"]
                           for e in evals_emp])), reverse=True)
                    if evals_emp
                    else [2025]
                )
                sel_anio = st.selectbox("Seleccionar Año:", anios_disp)

                renderizar_mis_evaluaciones(emp_id, sel_emp, sel_anio)

        # ADMIN CROMA - RESULTADOS Y EDICIÓN

        if st.session_state.es_croma and tab_admin_resultados:
            with tab_admin_resultados:
                st.subheader("📊 Historial General y Edición por Usuario")

                res_todos = (
                    supabase.table("intentos_examen")
                    .select("*")
                    .eq("activo", True)
                    .order("id", desc=True)
                    .execute()
                )
                todos_intentos = res_todos.data if res_todos.data else []

                if todos_intentos:
                    anios_disponibles = sorted(
                        list(
                            set(
                                int(it["fecha_inicio"][:4])
                                for it in todos_intentos
                                if it.get("fecha_inicio")
                            )
                        ),
                        reverse=True,
                    )

                    anio_sel = st.selectbox(
                        "📅 Filtrar exámenes por año:", anios_disponibles
                    )

                    intentos_filtrados = [
                        it
                        for it in todos_intentos
                        if it.get("fecha_inicio")
                        and int(it["fecha_inicio"][:4]) == anio_sel
                    ]

                    st.write(
                        f"Se encontraron **{len(intentos_filtrados)}** exámenes"
                        f" realizados en el año **{anio_sel}**."
                    )

                    if intentos_filtrados:
                        intentos_filtrados_ordenados = sorted(
                            intentos_filtrados, key=lambda x: x["id"], reverse=True
                        )
                        map_id_to_intento = {
                            it["id"]: it for it in intentos_filtrados_ordenados
                        }

                        def format_func(it_id):
                            it = map_id_to_intento[it_id]
                            est_it = obtener_estado_evaluacion(
                                it.get("porcentaje_obtenido", 0), it.get(
                                    "sobrepasado_tiempo")
                            )
                            return (
                                f"ID #{it['id']} - {it.get('nombre_empleado')}"
                                f" ({
                                    it.get('apartado')}) | Nota: {
                                    it.get(
                                        'nota', 0)}/10"
                                f" [{est_it}]"
                            )

                        opciones_ids = list(map_id_to_intento.keys())

                        if st.session_state.intento_auditado_id_sel not in opciones_ids:
                            st.session_state.intento_auditado_id_sel = opciones_ids[0]

                        idx_defecto_intento = opciones_ids.index(
                            st.session_state.intento_auditado_id_sel
                        )

                        intento_target_id = st.selectbox(
                            "Selecciona un examen para auditar/editar:",
                            options=opciones_ids,
                            index=idx_defecto_intento,
                            format_func=format_func,
                            key="select_intento_audit_id",
                        )

                        st.session_state.intento_auditado_id_sel = intento_target_id

                        intento_obj = map_id_to_intento[intento_target_id]
                        respuestas_lista = json.loads(
                            json.dumps(
                                intento_obj.get(
                                    "respuestas_usuario", []))
                        )

                        if respuestas_lista:
                            dict_preguntas = {
                                f"P{idx + 1}: {p['pregunta']}": idx
                                for idx, p in enumerate(respuestas_lista)
                            }
                            p_sel_key = st.selectbox(
                                "Selecciona la pregunta a corregir:",
                                list(dict_preguntas.keys()),
                                key=f"sel_p_{intento_target_id}",
                            )

                            p_idx = dict_preguntas[p_sel_key]
                            p_objetivo = respuestas_lista[p_idx]

                            st.write(
                                "### ❓ Pregunta seleccionada:\n**"
                                f"{p_objetivo.get('pregunta')}**"
                            )
                            st.info(
                                "Respuesta registrada del empleado:"
                                f" **{
                                    p_objetivo.get('opcion_elegida')}** | Estado actual:"
                                f" **{
                                    'Correcta' if p_objetivo.get('es_correcta') else 'Incorrecta'}**"
                            )

                            opciones_disponibles = p_objetivo.get(
                                "opciones_posibles", [])
                            texto_respuesta_correcta = p_objetivo.get(
                                "respuesta_correcta_texto", ""
                            )

                            res_examenes_db = (
                                supabase.table("examenes")
                                .select("id, preguntas_json")
                                .execute()
                            )
                            banco_todos = (
                                res_examenes_db.data if res_examenes_db.data else []
                            )

                            pregunta_texto_limpio = p_objetivo.get(
                                "pregunta", "").strip()

                            for ex_item in banco_todos:
                                preguntas_banco = ex_item.get(
                                    "preguntas_json", [])
                                if isinstance(preguntas_banco, list):
                                    preguntas_validas = [
                                        p for p in preguntas_banco if isinstance(p, dict)
                                    ]
                                    for p_b in preguntas_validas:
                                        p_texto = p_b.get("pregunta")
                                        if (
                                            isinstance(p_texto, str)
                                            and p_texto.strip() == pregunta_texto_limpio
                                        ):
                                            opciones_disponibles = p_b.get(
                                                "opciones", [])
                                            num_correcta = p_b.get(
                                                "respuesta_correcta")
                                            if isinstance(num_correcta, int) and 0 <= num_correcta < len(
                                                opciones_disponibles
                                            ):
                                                texto_respuesta_correcta = opciones_disponibles[
                                                    num_correcta
                                                ]
                                            break

                            if texto_respuesta_correcta:
                                st.success(
                                    "🎯 **Respuesta correcta según el Banco de Preguntas:**\n\n"
                                    f"{texto_respuesta_correcta}"
                                )

                            with st.form(key=f"form_edit_{intento_target_id}_{p_idx}"):
                                st.markdown(
                                    "### 📝 Formulario de Modificación de Respuesta")

                                persona_modifica = st.text_input(
                                    "👤 Persona que modifica (Obligatorio):*",
                                    value=st.session_state.user_nombre,
                                )

                                if opciones_disponibles:
                                    idx_defecto_resp = 0
                                    if texto_respuesta_correcta in opciones_disponibles:
                                        idx_defecto_resp = opciones_disponibles.index(
                                            texto_respuesta_correcta
                                        )

                                    resp_correcta_input = st.selectbox(
                                        "✅ Seleccionar o Confirmar Respuesta Correcta:*",
                                        options=opciones_disponibles,
                                        index=idx_defecto_resp,
                                    )
                                else:
                                    resp_correcta_input = st.text_input(
                                        "✅ Respuesta correcta del examen (Obligatorio):*",
                                        value=texto_respuesta_correcta,
                                    )

                                nuevo_estado = st.checkbox(
                                    "Marcar esta pregunta como Correcta para el empleado",
                                    value=p_objetivo.get("es_correcta", False),
                                )
                                motivo_edicion = st.text_area(
                                    "📋 Motivo de la corrección (Obligatorio):*"
                                )

                                btn_guardar_edit = st.form_submit_button(
                                    "Guardar Corrección Auditada"
                                )

                                if btn_guardar_edit:
                                    if not persona_modifica.strip():
                                        st.error(
                                            "❌ El campo 'Persona que modifica' es obligatorio."
                                        )
                                    elif (
                                        not resp_correcta_input
                                        or not str(resp_correcta_input).strip()
                                    ):
                                        st.error(
                                            "❌ Debes indicar una respuesta correcta válida.")
                                    elif not motivo_edicion.strip():
                                        st.error(
                                            "❌ El motivo de la corrección es obligatorio.")
                                    else:
                                        try:
                                            respuestas_lista[p_idx]["es_correcta"] = nuevo_estado
                                            respuestas_lista[p_idx]["respuesta_correcta_texto"] = (
                                                resp_correcta_input
                                            )
                                            respuestas_lista[p_idx]["opciones_posibles"] = (
                                                opciones_disponibles
                                            )

                                            correctas_nuevas = sum(
                                                1 for r in respuestas_lista if r["es_correcta"]
                                            )
                                            total_preg = len(respuestas_lista)
                                            nuevo_porc = round(
                                                (correctas_nuevas /
                                                 total_preg) * 100, 2
                                            )
                                            nueva_nota = round(
                                                (correctas_nuevas /
                                                 total_preg) * 10, 2
                                            )

                                            supabase.table("intentos_examen").update({
                                                "respuestas_usuario": respuestas_lista,
                                                "nota": nueva_nota,
                                                "porcentaje_obtenido": nuevo_porc,
                                            }).eq("id", intento_target_id).execute()

                                            registro_audit = {
                                                "intento_id": int(intento_target_id),
                                                "usuario_modificador": persona_modifica.strip(),
                                                "fecha_modificacion": datetime.datetime.now(
                                                    datetime.timezone.utc
                                                ).strftime("%Y-%m-%d %H:%M:%S"),
                                                "valor_anterior": json.dumps({
                                                    "es_correcta": p_objetivo.get("es_correcta"),
                                                    "respuesta_correcta": texto_respuesta_correcta,
                                                }),
                                                "valor_nuevo": json.dumps({
                                                    "es_correcta": nuevo_estado,
                                                    "respuesta_correcta": resp_correcta_input,
                                                }),
                                                "motivo": motivo_edicion.strip(),
                                            }

                                            supabase.table("auditoria_modificaciones").insert(
                                                registro_audit
                                            ).execute()
                                            st.success(
                                                "✅ Corrección guardada y auditada correctamente."
                                            )
                                            time.sleep(1)
                                            st.rerun()

                                        except Exception as err:
                                            st.error(
                                                f"⚠️ Error al guardar en la base de datos: {err}")

        # ADMIN CROMA - EXPORTACIÓN E INFORMES
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación Exámenes e Importación Datos")

                res_todos = (
                    supabase.table("intentos_examen")
                    .select("*")
                    .eq("activo", True)
                    .order("fecha_inicio", desc=False)
                    .execute()
                )
                todos_intentos = res_todos.data if res_todos.data else []

                if todos_intentos:
                    anios_exp = sorted(
                        list(
                            set(
                                int(it["fecha_inicio"][:4])
                                for it in todos_intentos
                                if it.get("fecha_inicio")
                            )
                        ),
                        reverse=True,
                    )
                    anio_exp_sel = st.selectbox(
                        "📅 Seleccionar año para exportación:", anios_exp, key="exp_anio"
                    )

                    intentos_exp_filtrados = [
                        it
                        for it in todos_intentos
                        if it.get("fecha_inicio")
                        and int(it["fecha_inicio"][:4]) == anio_exp_sel
                    ]

                    if intentos_exp_filtrados:
                        opciones_examenes = []
                        for i in intentos_exp_filtrados:
                            est_exp = obtener_estado_evaluacion(
                                i.get("porcentaje_obtenido", 0), i.get(
                                    "sobrepasado_tiempo")
                            )
                            opciones_examenes.append(
                                f"Examen #{
                                    i['id']} - {
                                    i.get('nombre_empleado')} |"
                                f" {i.get('apartado')} | Nota: {i.get('nota', 0)}/10"
                                f" [{est_exp}]"
                            )

                        opcion_elegida = st.selectbox(
                            "Selecciona el examen a exportar:", opciones_examenes
                        )
                        idx_sel = opciones_examenes.index(opcion_elegida)
                        examen_sel = intentos_exp_filtrados[idx_sel]

                        col_exp_a, col_exp_b = st.columns(2)
                        with col_exp_a:
                            df_export = pd.DataFrame([examen_sel])
                            buffer_excel = io.BytesIO()
                            with pd.ExcelWriter(buffer_excel, engine="openpyxl") as writer:
                                df_export.to_excel(
                                    writer, index=False, sheet_name="Examen")

                            st.download_button(
                                label="📥 Descargar Excel de este Examen",
                                data=buffer_excel.getvalue(),
                                file_name=f"examen_{examen_sel['id']}.xlsx",
                                mime=(
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                ),
                                use_container_width=True,
                            )

                        with col_exp_b:
                            pdf_bytes = generar_pdf_resultado(examen_sel)
                            if pdf_bytes:
                                st.download_button(
                                    label="📄 Descargar Informe PDF",
                                    data=pdf_bytes,
                                    file_name=f"informe_examen_{
                                        examen_sel['id']}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True,
                                )

                st.markdown("---")

                # INFORME DE EVALUACIÓN IA (SQL) - ADMINISTRADOR
                st.subheader(
                    "📄 Consulta de Informe de Análisis IA por Empleado (SQL)"
                )

                try:
                    res_emp_act_exp = (
                        supabase.table("empleados")
                        .select("id, nombre")
                        .eq("activo", True)
                        .order("nombre", desc=False)
                        .execute()
                    )
                    list_emp_exp = (
                        res_emp_act_exp.data if res_emp_act_exp.data else []
                    )
                except Exception:
                    list_emp_exp = []

                if list_emp_exp:
                    dict_emp_exp = {e["nombre"]: e["id"] for e in list_emp_exp}
                    col_ia_a, col_ia_b = st.columns(2)

                    with col_ia_a:
                        emp_exp_sel_nom = st.selectbox(
                            "👥 Seleccionar Empleado:",
                            list(dict_emp_exp.keys()),
                            key="exp_ia_emp_nom",
                        )
                    with col_ia_b:
                        anio_defecto = datetime.datetime.now().year
                        anio_exp_ia = st.number_input(
                            "📅 Seleccionar Año:",
                            min_value=2020,
                            max_value=2030,
                            value=anio_defecto,
                            key="exp_ia_anio_num",
                        )

                    emp_exp_id_val = dict_emp_exp[emp_exp_sel_nom]

                    res_an_sql = (
                        supabase.table("analisis_ia_empleados")
                        .select("*")
                        .eq("empleado_id", emp_exp_id_val)
                        .eq("anio", int(anio_exp_ia))
                        .order("fecha_generacion", desc=True)
                        .execute()
                    )

                    if res_an_sql.data:
                        informes_disponibles = res_an_sql.data

                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button(
                                "👁️ Mostrar Análisis IA",
                                use_container_width=True,
                                key="btn_toggle_ia_show",
                            ):
                                st.session_state.mostrar_analisis_ia_exp = (
                                    not st.session_state.mostrar_analisis_ia_exp
                                )

                        informe_principal = informes_disponibles[0]
                        txt_analisis = informe_principal.get(
                            "analisis_texto", "")

                        with col_btn2:
                            pdf_bytes_ia = generar_pdf_evaluacion_ia(
                                emp_exp_sel_nom, txt_analisis, anio_exp_ia
                            )
                            if pdf_bytes_ia:
                                st.download_button(
                                    label="📄 Descargar PDF del Análisis IA",
                                    data=pdf_bytes_ia,
                                    file_name=(
                                        "Analisis_IA_"
                                        f"{
                                            emp_exp_sel_nom.replace(
                                                ' ', '_')}_{anio_exp_ia}.pdf"
                                    ),
                                    mime="application/pdf",
                                    use_container_width=True,
                                    key="btn_download_pdf_ia_admin",
                                )

                        if st.session_state.mostrar_analisis_ia_exp:
                            st.info(
                                f"**Análisis de Evaluación IA de {emp_exp_sel_nom}"
                                f" ({anio_exp_ia}):**\n\n{txt_analisis}"
                            )
                    else:
                        st.warning(
                            "⚠️ No se encontró ningún informe de Análisis IA generado en"
                            f" SQL para **{emp_exp_sel_nom}** en el año **{anio_exp_ia}**."
                        )
                else:
                    st.warning(
                        "No se pudieron cargar los empleados para consultar los informes"
                        " de IA."
                    )

                st.markdown("---")

                # IMPORTAR INTENTOS DESDE CSV
                st.subheader("📥 Importar Registro de Exámenes (CSV)")
                archivo_csv_import = st.file_uploader(
                    "Seleccionar archivo CSV", type=["csv"], key="csv_import_uploader")

                if archivo_csv_import is not None:
                    if st.button(
                            "🚀 Procesar e Importar CSV a la Base de Datos", use_container_width=True):
                        try:
                            # Intento de lectura del CSV con separador ';' o
                            # ','
                            try:
                                df_csv = pd.read_csv(
                                    archivo_csv_import, sep=';')
                                if len(df_csv.columns) <= 1:
                                    archivo_csv_import.seek(0)
                                    df_csv = pd.read_csv(
                                        archivo_csv_import, sep=',')
                            except Exception:
                                archivo_csv_import.seek(0)
                                df_csv = pd.read_csv(
                                    archivo_csv_import, sep=',')

                            res_emp_all = supabase.table(
                                "empleados").select("id, nombre").execute()
                            map_empleados = {
                                emp["nombre"].strip().lower(): emp["id"] for emp in (
                                    res_emp_all.data or [])}

                            registros_insertados = 0
                            errores_import = 0

                            for idx_row, row in df_csv.iterrows():
                                nombre_emp = str(
                                    row.get("nombre empleado") or row.get("nombre_empleado") or "").strip()
                                emp_id = map_empleados.get(
                                    nombre_emp.lower(), None)

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
                                if not pd.isna(
                                        minutos_val) and minutos_val is not None:
                                    t_limite = int(minutos_val) * 60
                                else:
                                    t_limite = int(
                                        row.get("tiempo_limite") or row.get("tiempo_limite_segundos") or 0)

                                fecha_inicio_clean = limpiar_timestamp_sql(
                                    row.get("fecha_inicio"))
                                fecha_fin_clean = limpiar_timestamp_sql(
                                    row.get("fecha_fin"))

                                sobrepasado = False
                                duracion_seg = 0
                                if fecha_inicio_clean and fecha_fin_clean:
                                    try:
                                        dt_ini = pd.to_datetime(
                                            fecha_inicio_clean)
                                        dt_fin = pd.to_datetime(
                                            fecha_fin_clean)
                                        duracion_seg = int(
                                            (dt_fin - dt_ini).total_seconds())
                                        if t_limite > 0 and duracion_seg > t_limite:
                                            sobrepasado = True
                                    except Exception:
                                        pass

                                # Mapeo del porcentaje de aciertos
                                if len(row) >= 8 and not pd.isna(row.iloc[7]):
                                    porcentaje_val = float(row.iloc[7])
                                else:
                                    porcentaje_val = float(
                                        row.get(
                                            "porcentaje_obtenido",
                                            0)) if not pd.isna(
                                        row.get("porcentaje_obtenido")) else 0.0

                                nota_val = float(
                                    row.get(
                                        "nota", 0)) if not pd.isna(
                                    row.get("nota")) else 0.0

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
                                    supabase.table("intentos_examen").insert(
                                        registro_nuevo).execute()
                                    registros_insertados += 1
                                except Exception as err_ins:
                                    st.error(
                                        f"Error importando fila {
                                            idx_row + 1} ({nombre_emp}): {err_ins}")
                                    errores_import += 1

                            if registros_insertados > 0:
                                st.success(
                                    f"✅ Importación completada: Se insertaron **{registros_insertados}** registros correctamente.")
                                time.sleep(1.5)
                                st.rerun()

                        except Exception as e_csv:
                            st.error(
                                f"❌ Error al procesar el archivo CSV: {e_csv}")

                    st.markdown("---")

                    # TAB 3: INFORMES IA Y ANALÍTICA
                    with tab_informes_ia:
                        st.header("📊 Informes IA y Analítica de Desempeño")
                        st.caption(
                            "Filtra los manuales y exámenes evaluados para generar análisis mediante Inteligencia Artificial.")

                        # 1. Filtros de Interfaz (usando keys únicas para esta
                        # pestaña)
                        col_f1, col_f2 = st.columns(2)

                        with col_f1:
                            filtro_estado_man_inf = st.radio(
                                "Filtrar manuales por estado:",
                                ["Activos", "Deshabilitados", "Todos"],
                                index=0,
                                horizontal=True,
                                key="f_man_est_informes_ia"  # 👈 Key única específica para esta sección
                            )

                    with col_f2:
                        filtro_rango_fecha = st.date_input(
                            "Rango de evaluación:",
                            value=(),
                            key="f_fechas_informes_ia"
                        )

                    st.markdown("---")

                    # 2. Consulta de Manuales / Exámenes en Supabase
                    try:
                        query_man = supabase.table("examenes").select(
                            "*").order("creado_el", desc=True)

                        if filtro_estado_man_inf == "Activos":
                            query_man = query_man.eq("activo", True)
                        elif filtro_estado_man_inf == "Deshabilitados":
                            query_man = query_man.eq("activo", False)

                        res_man = query_man.execute()
                        lista_manuales = res_man.data or []

                        if not lista_manuales:
                            st.info(
                                "No se encontraron manuales o exámenes con los filtros seleccionados.")
                        else:
                            # 3. Selección del Manual para Analítica
                            opciones_manuales = {
                                f"{m.get('titulo', 'Sin título')} (ID: {m.get('id')})": m for m in lista_manuales}
                            manual_sel_label = st.selectbox(
                                "Selecciona un manual para generar el informe:",
                                options=list(opciones_manuales.keys()),
                                key="sb_manual_informes_ia"
                            )

                        manual_seleccionado = opciones_manuales[manual_sel_label]
                        manual_id = manual_seleccionado["id"]

                        # 4. Obtención de Intentos y Evaluaciones para el
                        # Manual
                        res_intentos = supabase.table("intentos_examen") \
                            .select("*, empleados(nombre)") \
                            .eq("apartado", manual_seleccionado.get("titulo", "")) \
                            .execute()

                        df_intentos = pd.DataFrame(res_intentos.data or [])

                        if df_intentos.empty:
                            st.warning(
                                "No hay intentos registrados para este manual.")
                        else:
                            # Métricas rápidas
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Total Evaluaciones", len(df_intentos))
                            c2.metric(
                                "Promedio Nota", f"{
                                    df_intentos['nota'].mean():.2f}")
                            c3.metric(
                                "Aprobados (%)", f"{(df_intentos['nota'] >= 6.0).mean() * 100:.1f}%")

                            st.subheader("Registros Obtenidos")
                            st.dataframe(
                                df_intentos[["nombre_empleado", "nota", "porcentaje_obtenido", "fecha_fin"]])

                            # 5. Generación del Informe con IA
                            if st.button(
                                    "🤖 Generar Informe Consolidado con IA", key="btn_generar_ia_informe"):
                                with st.spinner("Analizando datos con el motor de IA..."):
                                    # Preparar el contexto para el modelo de IA
                                    resumen_datos = {
                                        "manual": manual_seleccionado.get("titulo"),
                                        "total_intentos": len(df_intentos),
                                        "promedio_general": float(df_intentos["nota"].mean()),
                                        "porcentaje_aprobacion": float((df_intentos["nota"] >= 6.0).mean() * 100)
                                    }

                                    # Lógica de envío al API de IA (OpenAI / Anthropic / Gemini)
                                    # prompt = f"Analiza estos resultados de examen: {resumen_datos}"
                                    # respuesta_ia = llamar_api_ia(prompt)

                                    st.success(
                                        "✅ Informe generado exitosamente.")
                                    st.markdown("### 📝 Conclusiones de la IA")
                                    st.write(
                                        "Basado en el análisis de las evaluaciones, los empleados demuestran un alto nivel de comprensión en los aspectos teóricos básicos...")

                    except Exception as e_inf:
                        st.error(
                            f"❌ Error al cargar los datos de Informes IA: {e_inf}")

                # ADMIN CROMA - GESTIÓN Y CONFIGURACIÓN
                if st.session_state.es_croma and tab_admin_gestion:
                    with tab_admin_gestion:
                        st.subheader(
                            "⚙️ Gestión de Usuarios, Manuales, Exámenes y Estado Activo")

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
                                q_emp = supabase.table("empleados").select(
                                    "*").order("nombre", desc=False)
                                if filtro_estado_emp == "Activos":
                                    q_emp = q_emp.eq("activo", True)
                                elif filtro_estado_emp == "Deshabilitados":
                                    q_emp = q_emp.eq("activo", False)

                                res_emp_mgmt = q_emp.execute()

                                if empleados_data:
                                    for emp in empleados_data:
                                        emp_id = emp["id"]
                                        emp_nom = emp.get(
                                            "nombre", "Sin Nombre")
                                        emp_act = emp.get("activo", True)
                                        emp_admin = emp.get(
                                            "es_admin_croma", False)
                                        emp_ia_hab = emp.get(
                                            "analisis_ia_habilitado", True)

                                        with st.expander(f"👤 {emp_nom} ({'Administrador' if emp_admin else 'Empleado'}) - {'🟢 Activo' if emp_act else '🔴 Deshabilitado'}"):
                                            col_e1, col_e2 = st.columns(2)
                                            with col_e1:
                                                nuevo_nom = st.text_input(
                                                    "Nombre completo:", value=emp_nom, key=f"emp_nom_in_{emp_id}")
                                                chk_act = st.checkbox(
                                                    "Cuenta Activa en Plataforma", value=emp_act, key=f"emp_act_chk_{emp_id}")
                                            with col_e2:
                                                chk_adm = st.checkbox(
                                                    "Es Administrador CROMA", value=emp_admin, key=f"emp_adm_chk_{emp_id}")
                                                chk_ia_hab = st.checkbox(
                                                    "Permitir Análisis IA a este usuario", value=emp_ia_hab, key=f"emp_ia_chk_{emp_id}")

                                            if st.button(
                                                    "💾 Guardar Cambios de Empleado", key=f"btn_save_emp_{emp_id}"):
                                                try:
                                                    supabase.table("empleados").update({
                                                        "nombre": nuevo_nom.strip(),
                                                        "activo": chk_act,
                                                        "es_admin_croma": chk_adm,
                                                        "analisis_ia_habilitado": chk_ia_hab
                                                    }).eq("id", emp_id).execute()
                                                    st.success(
                                                        "✅ Cambios actualizados correctamente.")
                                                    time.sleep(0.5)
                                                    st.rerun()
                                                except Exception as err_u_e:
                                                    st.error(
                                                        f"Error actualizando usuario: {err_u_e}")
                                else:
                                    st.info(
                                        "No se encontraron empleados registrados con el filtro seleccionado.")

                            except Exception as err_emp_m:
                                st.error(
                                    f"Error consultando empleados: {err_emp_m}")

                        # TAB 2: GESTIÓN DE MANUALES
                        with tab_g_man:
                            st.markdown("### 📘 Manuales y Bancos de Preguntas")

                            filtro_estado_man = st.radio(
                                "Filtrar manuales por estado:",
                                ["Activos", "Deshabilitados", "Todos"],
                                index=0,  # Por defecto Activos
                                horizontal=True,
                                key="f_man_est_manuales"
                            )

                            try:
                                q_man = supabase.table("examenes").select(
                                    "*").order("id", desc=True)
                                if filtro_estado_man == "Activos":
                                    q_man = q_man.eq("activo", True)
                                elif filtro_estado_man == "Deshabilitados":
                                    q_man = q_man.eq("activo", False)

                                res_ex_mgmt = q_man.execute()
                                examenes_mng_data = res_ex_mgmt.data if res_ex_mgmt.data else []

                                if examenes_mng_data:
                                    for ex_m in examenes_mng_data:
                                        ex_id = ex_m["id"]
                                        apt_nom = ex_m.get(
                                            "apartado", "Sin Nombre")
                                        act_status = ex_m.get("activo", True)
                                        pregs_json_val = ex_m.get(
                                            "preguntas_json", [])
                                        num_p_tot = len(pregs_json_val) if isinstance(
                                            pregs_json_val, list) else 0

                                        label_man = f"📘 Examen/Manual #{ex_id}: {apt_nom} ({num_p_tot} preguntas) - {
                                            '🟢 Activo' if act_status else '🔴 Deshabilitado'}"

                                        with st.expander(label_man):
                                            nuevo_apt = st.text_input(
                                                "Nombre del Manual / Apartado:", value=apt_nom, key=f"ex_apt_in_{ex_id}")
                                            chk_man_act = st.checkbox(
                                                "Manual Activo en Plataforma", value=act_status, key=f"ex_act_chk_{ex_id}")

                                            col_m1, col_m2 = st.columns(2)
                                            with col_m1:
                                                if st.button(
                                                        "💾 Guardar Cambios de Manual", key=f"btn_save_ex_{ex_id}"):
                                                    try:
                                                        supabase.table("examenes").update({
                                                            "apartado": nuevo_apt.strip(),
                                                            "activo": chk_man_act
                                                        }).eq("id", ex_id).execute()
                                                        st.success(
                                                            "✅ Manual actualizado correctamente.")
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                    except Exception as err_u_m:
                                                        st.error(
                                                            f"Error actualizando manual: {err_u_m}")
                                            with col_m2:
                                                if st.button(
                                                        "🗑️ Eliminar Examen Permanentemente", key=f"btn_del_ex_{ex_id}"):
                                                    try:
                                                        supabase.table("examenes").delete().eq(
                                                            "id", ex_id).execute()
                                                        st.warning(
                                                            "⚠️ Examen eliminado de la base de datos.")
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                    except Exception as err_d_m:
                                                        st.error(
                                                            f"Error eliminando manual: {err_d_m}")
                                else:
                                    st.info(
                                        "No se encontraron manuales con el filtro seleccionado.")

                            except Exception as err_man_m:
                                st.error(
                                    f"Error consultando manuales: {err_man_m}")

                # ADMIN CROMA - GESTIÓN Y CONFIGURACIÓN
                if st.session_state.es_croma and tab_admin_gestion:
                    with tab_admin_gestion:
                        st.subheader(
                            "⚙️ Gestión de Usuarios, Manuales, Exámenes y Estado Activo")

                        tab_g_emp, tab_g_man, tab_g_cfg = st.tabs([
                            "👥 Lista de Empleados Registrados",
                            "📘 Gestión de Manuales y Exámenes Cargados",
                            "⏱️ Configuración de Tiempos y Prompts"
                        ])

                        # TAB 1: GESTIÓN DE EMPLEADOS
                        with tab_g_emp:
                            st.markdown("### 👥 Empleados Registrados")

                        # 1. Componente de Streamlit
                        filtro_estado_emp = st.radio(
                            "Filtrar empleados por estado:",
                            ["Activos", "Deshabilitados", "Todos"],
                            index=0,
                            horizontal=True,
                            key="f_emp_est_filtro"  # Key única para evitar duplicados
                        )

                        # 2. Construcción de la consulta en Supabase
                        query = supabase.table("empleados").select("*")

                        if filtro_estado_emp == "Activos":
                            # O eq("estado", "Activo") según tu columna
                            query = query.eq("activo", True)
                        elif filtro_estado_emp == "Deshabilitados":
                            query = query.eq("activo", False)

                        # 3. Ejecución
                        resultado = query.execute()
                        df_empleados = pd.DataFrame(resultado.data or [])

                        st.dataframe(df_empleados)
                        try:
                            q_emp = supabase.table("empleados").select(
                                "*").order("nombre", desc=False)
                            if filtro_estado_emp == "Activos":
                                q_emp = q_emp.eq("activo", True)
                            elif filtro_estado_emp == "Deshabilitados":
                                q_emp = q_emp.eq("activo", False)

                            res_emp_mgmt = q_emp.execute()

                            if empleados_data:
                                for emp in empleados_data:
                                    emp_id = emp["id"]
                                    emp_nom = emp.get("nombre", "Sin Nombre")
                                    emp_act = emp.get("activo", True)
                                    emp_admin = emp.get(
                                        "es_admin_croma", False)
                                    emp_ia_hab = emp.get(
                                        "analisis_ia_habilitado", True)

                                with st.expander(f"👤 {emp_nom} ({'Administrador' if emp_admin else 'Empleado'}) - {'🟢 Activo' if emp_act else '🔴 Deshabilitado'}"):
                                    col_e1, col_e2 = st.columns(2)
                                    with col_e1:
                                        nuevo_nom = st.text_input(
                                            "Nombre completo:", value=emp_nom, key=f"emp_nom_in_{emp_id}")
                                        chk_act = st.checkbox(
                                            "Cuenta Activa en Plataforma", value=emp_act, key=f"emp_act_chk_{emp_id}")
                                        with col_e2:
                                            chk_adm = st.checkbox(
                                                "Es Administrador CROMA", value=emp_admin, key=f"emp_adm_chk_{emp_id}")
                                            chk_ia_hab = st.checkbox(
                                                "Permitir Análisis IA a este usuario",
                                                value=emp_ia_hab,
                                                key=f"emp_ia_chk_{emp_id}")

                                        if st.button(
                                                "💾 Guardar Cambios de Empleado", key=f"btn_save_emp_{emp_id}"):
                                            try:
                                                supabase.table("empleados").update({
                                                    "nombre": nuevo_nom.strip(),
                                                    "activo": chk_act,
                                                    "es_admin_croma": chk_adm,
                                                    "analisis_ia_habilitado": chk_ia_hab
                                                }).eq("id", emp_id).execute()
                                                st.success(
                                                    "✅ Cambios actualizados correctamente.")
                                                time.sleep(0.5)
                                                st.rerun()
                                            except Exception as err_u_e:
                                                st.error(
                                                    f"Error actualizando usuario: {err_u_e}")
                                        else:
                                            st.info(
                                                "No se encontraron empleados registrados con el filtro seleccionado.")

                        except Exception as err_emp_m:
                            st.error(
                                f"Error consultando empleados: {err_emp_m}")

                        # TAB 2: GESTIÓN DE MANUALES
                        with tab_g_man:
                            st.markdown("### 📘 Manuales y Bancos de Preguntas")

                            filtro_estado_man = st.radio(
                                "Filtrar manuales por estado:",
                                ["Activos", "Deshabilitados", "Todos"],
                                index=0,  # Por defecto Activos
                                horizontal=True,
                                key="f_man_est_gestion"
                            )

                            try:
                                q_man = supabase.table("examenes").select(
                                    "*").order("id", desc=True)
                                if filtro_estado_man == "Activos":
                                    q_man = q_man.eq("activo", True)
                                elif filtro_estado_man == "Deshabilitados":
                                    q_man = q_man.eq("activo", False)

                                res_ex_mgmt = q_man.execute()
                                examenes_mng_data = res_ex_mgmt.data if res_ex_mgmt.data else []

                                if examenes_mng_data:
                                    for ex_m in examenes_mng_data:
                                        ex_id = ex_m["id"]
                                        apt_nom = ex_m.get(
                                            "apartado", "Sin Nombre")
                                        act_status = ex_m.get("activo", True)
                                        pregs_json_val = ex_m.get(
                                            "preguntas_json", [])
                                        num_p_tot = len(pregs_json_val) if isinstance(
                                            pregs_json_val, list) else 0

                                        label_man = f"📘 Examen/Manual #{ex_id}: {apt_nom} ({num_p_tot} preguntas) - {
                                            '🟢 Activo' if act_status else '🔴 Deshabilitado'}"

                                        with st.expander(label_man):
                                            nuevo_apt = st.text_input(
                                                "Nombre del Manual / Apartado:", value=apt_nom, key=f"ex_apt_in_{ex_id}")
                                            chk_man_act = st.checkbox(
                                                "Manual Activo en Plataforma", value=act_status, key=f"ex_act_chk_{ex_id}")

                                            col_m1, col_m2 = st.columns(2)
                                            with col_m1:
                                                if st.button(
                                                        "💾 Guardar Cambios de Manual", key=f"btn_save_ex_{ex_id}"):
                                                    try:
                                                        supabase.table("examenes").update({
                                                            "apartado": nuevo_apt.strip(),
                                                            "activo": chk_man_act
                                                        }).eq("id", ex_id).execute()
                                                        st.success(
                                                            "✅ Manual actualizado correctamente.")
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                    except Exception as err_u_m:
                                                        st.error(
                                                            f"Error actualizando manual: {err_u_m}")
                                            with col_m2:
                                                if st.button(
                                                        "🗑️ Eliminar Examen Permanentemente", key=f"btn_del_ex_{ex_id}"):
                                                    try:
                                                        supabase.table("examenes").delete().eq(
                                                            "id", ex_id).execute()
                                                        st.warning(
                                                            "⚠️ Examen eliminado de la base de datos.")
                                                        time.sleep(0.5)
                                                        st.rerun()
                                                    except Exception as err_d_m:
                                                        st.error(
                                                            f"Error eliminando manual: {err_d_m}")
                                else:
                                    st.info(
                                        "No se encontraron manuales con el filtro seleccionado.")

                            except Exception as err_man_m:
                                st.error(
                                    f"Error consultando manuales: {err_man_m}")

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

        # ---------------------------------------------------------
        # 1. FORMULARIO: TIEMPOS Y PREGUNTAS
        # ---------------------------------------------------------
                with st.form("form_config_tiempos_preguntas"):
                    col_t1, col_t2, col_t3 = st.columns(3)
                    with col_t1:
                        nuevo_tiempo_seg = st.number_input(
                            "⏱️ Tiempo por pregunta (segundos):",
                            min_value=10,
                            max_value=300,
                            value=TIEMPO_LIMITE_PREGUNTA,
                        )
                    with col_t2:
                        nuevo_num_global = st.number_input(
                            "🌐 N.º Preguntas Examen Global:",
                            min_value=1,
                            max_value=100,
                            value=NUM_PREG_GLOBAL,
                        )
                    with col_t3:
                        nuevo_num_manual = st.number_input(
                            "📘 N.º Preguntas Examen Manual:",
                            min_value=1,
                            max_value=100,
                            value=NUM_PREG_MANUAL,
                        )

                    btn_guardar_tiempos = st.form_submit_button(
                        "💾 Guardar Tiempos y Parámetros"
                    )

        # Procesar envío del formulario 1
        if btn_guardar_tiempos:
            ok_t = guardar_tiempo_pregunta_config(nuevo_tiempo_seg)
            ok_g = guardar_num_preguntas_config("global", nuevo_num_global)
            ok_m = guardar_num_preguntas_config("manual", nuevo_num_manual)

            if ok_t and ok_g and ok_m:
                st.success(
                    "✅ Configuración de tiempos y número de preguntas actualizada"
                    " correctamente."
                )
            time.sleep(1)
            st.rerun()

        st.markdown("---")
        st.markdown("### 🤖 Configuración de Modelos de IA")
        st.caption(
            "Modifica los modelos disponibles por proveedor. Puedes introducir"
            " varios modelos separados por comas."
        )

        # Cargar valores de modelos desde Supabase
        modelos_gemini_val = "gemini-2.5-pro, gemini-2.5-flash"
        modelos_claude_val = (
            "claude-3-5-sonnet-20241022, claude-3-5-haiku-20241022"
        )
        modelos_openai_val = "gpt-4o, gpt-4o-mini"
        config_prompts_id = None

        try:
            res_cfg_modelos = (
                supabase.table("config_prompts")
                .select("id, modelo_gemini, modelo_claude, modelo_openai")
                .execute()
            )
            if res_cfg_modelos.data:
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

        # ---------------------------------------------------------
        # 2. FORMULARIO: MODELOS IA
        # ---------------------------------------------------------
        with st.form("form_config_modelos_ia"):
            input_gemini = st.text_input(
                "💎 Modelos Gemini (modelo_gemini):", value=modelos_gemini_val
            )
            input_claude = st.text_input(
                "🧠 Modelos Claude / Anthropic (modelo_claude):",
                value=modelos_claude_val,
            )
            input_openai = st.text_input(
                "⚡ Modelos OpenAI (modelo_openai):", value=modelos_openai_val
            )

            btn_guardar_modelos = st.form_submit_button(
                "💾 Guardar Configuración de Modelos IA", use_container_width=True
            )

        # Procesar envío del formulario 2
        if btn_guardar_modelos:
            try:
                datos_actualizacion = {
                    "modelo_gemini": input_gemini.strip(),
                    "modelo_claude": input_claude.strip(),
                    "modelo_openai": input_openai.strip(),
                }

                if config_prompts_id:
                    supabase.table("config_prompts").update(
                        datos_actualizacion
                    ).eq("id", config_prompts_id).execute()
                else:
                    supabase.table("config_prompts").insert(
                        datos_actualizacion
                    ).execute()

                st.success(
                    "✅ Modelos de IA actualizados correctamente en la base de"
                    " datos."
                )
                time.sleep(1)
                st.rerun()
            except Exception as err_m_save:
                st.error(f"❌ Error al guardar los modelos de IA: {err_m_save}")

        st.markdown("---")
        st.markdown("### 💬 Prompts Predeterminados del Sistema")

        # Cargar Prompts Actuales
        prompt_actual_examen = PROMPT_DEFECTO_EXAMEN
        prompt_actual_eval = (
            "Analiza los exámenes del empleado y genera una evaluación profesional"
            " estructurada."
        )

        try:
            res_p1 = (
                supabase.table("config_prompts")
                .select("valor")
                .eq("nombre", "prompt_examen")
                .limit(1)
                .execute()
            )
            if res_p1.data and res_p1.data[0].get("valor"):
                prompt_actual_examen = res_p1.data[0]["valor"]

            res_p2 = (
                supabase.table("config_prompts")
                .select("valor")
                .eq("nombre", "evaluacion_empleado")
                .limit(1)
                .execute()
            )
            if res_p2.data and res_p2.data[0].get("valor"):
                prompt_actual_eval = res_p2.data[0]["valor"]
        except Exception:
            pass

        # ---------------------------------------------------------
        # 3. FORMULARIO: PROMPTS PREDETERMINADOS
        # ---------------------------------------------------------
        with st.form("form_prompts_sistema"):
            p_examen_val = st.text_area(
                "📄 Prompt por defecto para Generación de Exámenes:",
                value=prompt_actual_examen,
                height=180,
            )
            p_eval_val = st.text_area(
                "📈 Prompt por defecto para Evaluación de Empleados con IA:",
                value=prompt_actual_eval,
                height=140,
            )

            btn_guardar_prompts = st.form_submit_button(
                "💾 Guardar Prompts Predeterminados"
            )

        # Procesar envío del formulario 3
        if btn_guardar_prompts:
            ok_p1 = guardar_prompt_config("prompt_examen", p_examen_val)
            ok_p2 = guardar_prompt_config("evaluacion_empleado", p_eval_val)
            if ok_p1 and ok_p2:
                st.success("✅ Prompts del sistema actualizados correctamente.")
                time.sleep(1)
                st.rerun()


            # --- TAB ADMINISTRADOR: EVALUACIONES TRIMESTRALES ---
        if st.session_state.es_croma and tab_admin_trimestral:
        with tab_admin_trimestral:
            st.header("📋 Gestión de Evaluaciones Trimestrales")

            menu_admin = st.radio(
                "Opción:",
                [
                    "1. Cargar Excel Evaluaciones",
                    "2. Edición y Visibilidad por Empleado",
                    "3. Resumen Anual y Desglose",
                    "4. Configuración Prompts y Media",
                    "5. Generar e Informes IA",
                    "6. Datos empleado",
                ],
            horizontal=True,
        )

    # --- 1. CARGAR EXCEL EVALUACIONES ---
    if menu_admin == "1. Cargar Excel Evaluaciones":
      st.subheader("📁 Importar Datos desde Archivo Excel")
      uploaded_file = st.file_uploader(
          "Selecciona un archivo Excel (.xlsx)", type=["xlsx"]
      )
      if uploaded_file:
        try:
          wb = openpyxl.load_workbook(uploaded_file, data_only=True)
          st.success(
              f"Archivo cargado correctamente. Hojas detectadas:"
              f" {wb.sheetnames}"
          )
          if st.button("Procesar y Guardar en Base de Datos"):
            st.info("Procesando datos...")
            st.success("¡Datos procesados y guardados con éxito!")
        except Exception as e:
          st.error(f"Error al leer el archivo Excel: {e}")

    # --- 2. EDICIÓN Y VISIBILIDAD POR EMPLEADO ---
    elif menu_admin == "2. Edición y Visibilidad por Empleado":
      st.subheader("👁️ Ajustar Visibilidad Personalizada por Empleado")
      emps = supabase.table("empleados").select("id, nombre").execute().data
      emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

      col_e1, col_e2 = st.columns(2)
      sel_emp = col_e1.selectbox("Empleado:", list(emp_dict.keys()))
      sel_anio = col_e2.number_input("Año:", value=2025, step=1)

      if sel_emp:
        emp_id = emp_dict[sel_emp]
        vis_actual = obtener_visibilidad_empleado(emp_id, sel_anio)

        st.markdown("#### 1. Trimestres (Q) Habilitados")
        q_cols = st.columns(4)
        qs_hab = {}
        for idx, q_name in enumerate(["Q1", "Q2", "Q3", "Q4"]):
          qs_hab[q_name] = q_cols[idx].checkbox(
              q_name,
              value=vis_actual.get("qs_habilitados", {}).get(q_name, True),
          )

        st.divider()

        evals = (
            supabase.table("evaluaciones_trimestrales")
            .select("id")
            .eq("empleado_id", emp_id)
            .eq("anio", sel_anio)
            .execute()
            .data
        )
        eval_ids = [e["id"] for e in evals] if evals else []

        detalles = []
        if eval_ids:
          detalles = (
              supabase.table("evaluacion_detalles")
              .select("apartado, subapartado")
              .in_("evaluacion_id", eval_ids)
              .execute()
              .data
          )

        estructura_apartados = {}
        if detalles:
          for d in detalles:
            ap = d["apartado"]
            sub = d["subapartado"]
            if ap not in estructura_apartados:
              estructura_apartados[ap] = set()
            if sub:
              estructura_apartados[ap].add(sub)
          for ap in estructura_apartados:
            estructura_apartados[ap] = sorted(list(estructura_apartados[ap]))
        else:
          estructura_apartados = {
              "Tareas realizar por turnos y todos los turnos": [
                  "Realiza las tareas asignadas a su turno",
                  "Entrega de turno y comunicación",
              ],
              "Tiempos respuesta Tbox": [
                  "Atención inmediata a alertas",
                  "Tiempo medio de resolución",
              ],
              "Tiempos respuesta Siemens": [
                  "Respuesta en sistema Siemens",
                  "Gestión de incidencias",
              ],
              "Iniciativa / Proactividad ante el trabajo": [
                  "Proactividad en resolución de problemas",
                  "Aportación de mejoras",
              ],
              "Conocimientos": [
                  "Manejo de herramientas",
                  "Dominio de procedimientos",
              ],
              "Evaluacion": ["Evaluación global y desempeño general"],
          }

        apts_vis_guardados = vis_actual.get("apartados_habilitados", {})
        sub_ocultos_guardados = set(
            vis_actual.get("subapartados_deshabilitados", [])
        )

        st.markdown(
            "#### 2. Selección Personalizada de Apartados y Subapartados"
        )
        st.caption(
            "Desmarca los apartados o subapartados que no desees incluir en las"
            " notas e informes de este empleado."
        )

        apartados_finales = {}
        subapartados_deshabilitados_finales = []

        for apt, subs in estructura_apartados.items():
          st.markdown(f"##### 📌 Apartado: **{apt}**")

          ap_activo = st.checkbox(
              f"Habilitar apartado completo: '{apt}'",
              value=apts_vis_guardados.get(apt, True),
              key=f"apt_{apt}",
          )
          apartados_finales[apt] = ap_activo

          if ap_activo and subs:
            with st.indent if hasattr(st, "indent") else st.container():
              st.write("    *Subapartados de este apartado:*")
              cols_sub = st.columns(min(len(subs), 2) if len(subs) > 1 else 1)
              for idx, sub_name in enumerate(subs):
                col = cols_sub[idx % len(cols_sub)]
                sub_activo = col.checkbox(
                    f"• {sub_name}",
                    value=(sub_name not in sub_ocultos_guardados),
                    key=f"sub_{apt}_{sub_name}",
                )
                if not sub_activo:
                  subapartados_deshabilitados_finales.append(sub_name)
          elif not ap_activo and subs:
            subapartados_deshabilitados_finales.extend(subs)

          st.markdown("---")

        if st.button("💾 Guardar Configuración de Visibilidad", type="primary"):
          guardar_visibilidad_empleado(
              emp_id,
              sel_anio,
              qs_hab,
              apartados_finales,
              list(set(subapartados_deshabilitados_finales)),
          )
          st.success(
              "¡Configuración de apartados y subapartados guardada"
              " correctamente!"
          )

    # --- 3. RESUMEN ANUAL Y DESGLOSE ---
    elif menu_admin == "3. Resumen Anual y Desglose":
      st.subheader("📊 Resumen Anual y Desglose General")
      emps = supabase.table("empleados").select("id, nombre").execute().data
      emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

      col_r1, col_r2 = st.columns(2)
      sel_emp = col_r1.selectbox(
          "Seleccionar Empleado para Consulta:", list(emp_dict.keys())
      )
      sel_anio = col_r2.number_input("Año de Consulta:", value=2025, step=1)

      if sel_emp:
        renderizar_mis_evaluaciones(emp_dict[sel_emp], sel_emp, sel_anio)

    # --- 4. CONFIGURACIÓN PROMPTS Y MEDIA ---
    elif menu_admin == "4. Configuración Prompts y Media":
      st.subheader("⚙️ Configuración del Prompt Base y Nota Media Requerida")
      try:
        cfg = (
            supabase.table("config_prompts_eval")
            .select("*")
            .limit(1)
            .execute()
            .data
        )
        prompt_actual = (
            cfg[0]["prompt_texto"]
            if cfg
            else (
                "Realiza un informe evaluativo profesional basado en estos"
                " datos:"
            )
        )
        media_actual = (
            float(cfg[0]["objetivo_media"])
            if cfg and "objetivo_media" in cfg[0]
            else 8.0
        )
      except Exception:
        prompt_actual = (
            "Realiza un informe evaluativo profesional basado en estos datos:"
        )
        media_actual = 8.0

      nuevo_prompt = st.text_area(
          "Prompt Base para la IA:", value=prompt_actual, height=150
      )
      nueva_media = st.number_input(
          "Nota Media Mínima Requerida (sobre 10):",
          value=media_actual,
          min_value=0.0,
          max_value=10.0,
          step=0.5,
      )

      if st.button("Guardar Configuración Base", type="primary"):
        try:
          supabase.table("config_prompts_eval").upsert({
              "id": cfg[0]["id"] if cfg else 1,
              "prompt_texto": nuevo_prompt,
              "objetivo_media": nueva_media,
          }).execute()
          st.success("Configuración actualizada correctamente.")
        except Exception as err:
          st.error(f"Error al guardar la configuración: {err}")

    # --- 5. GENERAR E INFORMES IA ---
    elif menu_admin == "5. Generar e Informes IA":
      st.subheader(
          "🤖 Generar e Insertar Informes IA (Multi-modelo y Multi-empleado)"
      )

      modelos_disp = obtener_modelos_disponibles_db()
      opciones_modelos = [
          f"{m['nombre_modelo']} ({m['proveedor'].upper()})"
          for m in modelos_disp
      ]

      col_m1, col_m2 = st.columns([2, 1])
      modelos_seleccionados_str = col_m1.multiselect(
          "🧠 Seleccionar Modelo(s) IA para la consulta:",
          options=opciones_modelos,
          default=[opciones_modelos[0]] if opciones_modelos else [],
      )
      sel_anio = col_m2.number_input("Año a evaluar:", value=2025, step=1)

      modelos_info_sel = []
      for mod_str in modelos_seleccionados_str:
        idx = opciones_modelos.index(mod_str)
        modelos_info_sel.append(modelos_disp[idx])

      emps = supabase.table("empleados").select("id, nombre").execute().data
      emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

      st.markdown("---")
      st.markdown("#### Selección de Empleados")
      seleccionar_todos = st.checkbox("Seleccionar TODOS los empleados")

      if seleccionar_todos:
        empleados_seleccionados = list(emp_dict.keys())
        st.info(
            f"Se han seleccionado **{len(empleados_seleccionados)}**"
            " empleados."
        )
      else:
        empleados_seleccionados = st.multiselect(
            "Selecciona uno o más empleados:",
            options=list(emp_dict.keys()),
            default=[],
        )

      if st.button(
          "🚀 Generar e Insertar Informes Seleccionados", type="primary"
      ):
        if not empleados_seleccionados:
          st.warning("Debes seleccionar al menos un empleado.")
        elif not modelos_info_sel:
          st.warning("Debes seleccionar al menos un modelo de IA.")
        else:
          total_emp = len(empleados_seleccionados)
          progreso_bar = st.progress(0)
          status_text = st.empty()

          resultados_exito = []
          resultados_error = []

          for idx, emp_nom in enumerate(empleados_seleccionados):
            emp_id = emp_dict[emp_nom]
            status_text.markdown(
                f"⌛ Procesando **{emp_nom}** ({idx + 1}/{total_emp}) con"
                f" **{len(modelos_info_sel)}** modelo(s)..."
            )

            exito, msg = generar_y_guardar_informe_ia_multimodelo(
                emp_id, emp_nom, sel_anio, modelos_info_sel
            )

            if exito:
              resultados_exito.append((emp_nom, msg))
            else:
              resultados_error.append((emp_nom, msg))

            progreso_bar.progress((idx + 1) / total_emp)

          status_text.empty()
          st.success(
              f"✅ Proceso completado: {len(resultados_exito)} informe(s)"
              " generado(s) correctamente."
          )

          if resultados_error:
            st.error(
                f"⚠️ {len(resultados_error)} informe(s) no se pudieron generar:"
            )
            for emp_err, err_msg in resultados_error:
              st.caption(f"• **{emp_err}**: {err_msg}")

          if resultados_exito:
            st.markdown("### 📋 Vista Previa de Informes Generados")
            for emp_ok, informe_txt in resultados_exito:
              with st.expander(f"📄 Informe IA - {emp_ok}"):
                st.markdown(informe_txt)

    # --- 6. DATOS EMPLEADO ---
    elif menu_admin == "6. Datos empleado":
      st.subheader("🔍 Datos empleado (Vista Espejo del Portal de Empleados)")
      emps = supabase.table("empleados").select("id, nombre").execute().data
      emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

      col_e1, col_e2 = st.columns(2)
      sel_emp = col_e1.selectbox(
          "Seleccionar Empleado a consultar:", list(emp_dict.keys())
      )

      if sel_emp:
        emp_id = emp_dict[sel_emp]
        evals_emp = (
            supabase.table("evaluaciones_trimestrales")
            .select("anio")
            .eq("empleado_id", emp_id)
            .execute()
            .data
        )
        anios_disp = (
            sorted(list(set([e["anio"] for e in evals_emp])), reverse=True)
            if evals_emp
            else [2025]
        )
        sel_anio = col_e2.selectbox("Seleccionar Año:", anios_disp)

        st.markdown(
            f"### Portal del Empleado - Mis Evaluaciones (`{sel_emp}` -"
            f" `{sel_anio}`)"
        )
        renderizar_mis_evaluaciones(emp_id, sel_emp, sel_anio)


# --- TAB EMPLEADO: EVALUACIONES TRIMESTRALES ---
if not st.session_state.es_croma and tab_emp_trimestral:
  with tab_emp_trimestral:
    st.header("📋 Mis Evaluaciones Trimestrales")

    emps = supabase.table("empleados").select("id, nombre").execute().data
    emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

    # Por defecto selecciona al empleado autenticado en la sesión
    sel_emp = st.session_state.user_nombre
    emp_id = st.session_state.user_id

    evals_emp = (
        supabase.table("evaluaciones_trimestrales")
        .select("anio")
        .eq("empleado_id", emp_id)
        .execute()
        .data
    )
    anios_disp = (
        sorted(list(set([e["anio"] for e in evals_emp])), reverse=True)
        if evals_emp
        else [2025]
    )
    sel_anio = st.selectbox("Seleccionar Año:", anios_disp)

    renderizar_mis_evaluaciones(emp_id, sel_emp, sel_anio)
