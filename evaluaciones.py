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

# Importar SDK de OpenAI - Opcional
try:
    import openai
    OPENAI_DISPONIBLE = True
except ImportError:
    OPENAI_DISPONIBLE = False

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
# CREDENCIALES Y CLIENTES
# ---------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")
CLAUDE_API_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")

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

# --- FUNCIÓN PARA OBTENER LOS MODELOS DISPONIBLES DESDE config_prompts ---
def obtener_modelos_disponibles_db():
    modelos = []
    try:
        res = supabase.table("config_prompts").select("*").execute().data
        if res:
            for r in res:
                mod_oa = r.get("modelo_openai") or (
                    r.get("valor") if "openai" in r.get("nombre", "").lower() else None
                )
                if mod_oa and mod_oa != "EMPTY":
                    modelos.append({"proveedor": "openai", "nombre_modelo": mod_oa})

                mod_gem = r.get("modelo_gemini") or (
                    r.get("valor") if "gemini" in r.get("nombre", "").lower() else None
                )
                if mod_gem and mod_gem != "EMPTY":
                    modelos.append({"proveedor": "gemini", "nombre_modelo": mod_gem})

        if not modelos:
            modelos = [
                {"proveedor": "openai", "nombre_modelo": "gpt-4o"},
                {"proveedor": "openai", "nombre_modelo": "gpt-4o-mini"},
                {"proveedor": "gemini", "nombre_modelo": "gemini-2.5-flash"},
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
            {"proveedor": "gemini", "nombre_modelo": "gemini-2.5-flash"},
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


# --- CONSULTA IA UNIFICADA Y GENERACIÓN MULTIMODELO ---
def consultar_ia(prompt_o_modelo, prompt_o_proveedor=None, sistema_o_modelo=None):
    """
    Función de consulta flexible que admite tanto la firma unificada por modelo simple
    como la firma de proveedor-modelo específica.
    """
    if prompt_o_proveedor is None:
        # Firma simple: consultar_ia(modelo, prompt)
        modelo = prompt_o_modelo
        prompt = prompt_o_proveedor
        sistema = sistema_o_modelo or ""
        
        modelos_disponibles = obtener_modelos_ia_disponibles()
        cola_modelos = [modelo] + [m for m in modelos_disponibles if m != modelo]
        
        ultimo_error = None
        for mod in cola_modelos:
            try:
                if "claude" in str(mod).lower():
                    if CLAUDE_DISPONIBLE and claude_client:
                        mensaje = claude_client.messages.create(
                            model=mod,
                            max_tokens=4096,
                            system=sistema if sistema else "Eres un asistente experto en análisis de datos y evaluación formativa.",
                            messages=[{"role": "user", "content": prompt_o_modelo}]
                        )
                        return mensaje.content[0].text
                    else:
                        raise Exception("SDK de Anthropic/Claude no disponible.")
                else:
                    if not gemini_client:
                        raise Exception("El cliente de Gemini no está configurado.")
                    
                    p_final = f"{sistema}\n\n{prompt_o_modelo}" if sistema else prompt_o_modelo
                    config_gen = types.GenerateContentConfig()
                    if "JSON" in str(prompt_o_modelo).upper():
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

        raise Exception(f"Error tras intentar con todos los modelos. Último error: {ultimo_error}")

    else:
        # Firma multimodelo: consultar_ia(prompt_completo, proveedor, nombre_modelo)
        prompt_completo = prompt_o_modelo
        proveedor = prompt_o_proveedor
        nombre_modelo = sistema_o_modelo

        try:
            if proveedor == "openai":
                if not OPENAI_API_KEY:
                    return False, "Falta configurar 'OPENAI_API_KEY' en los Secrets."
                if not OPENAI_DISPONIBLE:
                    return False, "Librería 'openai' no instalada."

                client = openai.OpenAI(api_key=OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model=nombre_modelo,
                    messages=[{"role": "user", "content": prompt_completo}],
                    temperature=0.7,
                )
                return True, response.choices[0].message.content

            elif proveedor == "gemini":
                if not GEMINI_API_KEY or not gemini_client:
                    return False, "Falta configurar 'GEMINI_API_KEY' o el cliente no está inicializado."

                res = gemini_client.models.generate_content(
                    model=nombre_modelo,
                    contents=prompt_completo
                )
                return True, res.text

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
            df_det = df_det[df_det["apartado"].map(lambda x: apts_hab.get(x, True))]
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
                    f"### 🤖 Informe generado con {mod_nom} ({prov.upper()})\n\n{res_texto}"
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
                    df_det["apartado"].map(lambda x: apts_habilitados.get(x, True))
                ]
                df_det = df_det[~df_det["subapartado"].isin(sub_ocultos)]

                if not df_det.empty:
                    ptos_obtenidos = float(df_det["puntuacion"].sum())
                    ptos_max_q = float(len(df_det) * 5.0)
                    nota_10 = (ptos_obtenidos / ptos_max_q) * 10 if ptos_max_q > 0 else 0
                    ptos_aprobar = (media_objetivo_sql / 10.0) * ptos_max_q

                    puntuaciones_obtenidas.append(ptos_obtenidos)
                    puntuaciones_maximas.append(ptos_max_q)
                    notas_sobre_10.append(nota_10)

                    estado_q = (
                        "🟢 APROBADO" if nota_10 >= media_objetivo_sql else "🔴 SUSPENSO"
                    )

                    with st.expander(f"📊 {q_nombre} - Estado: {estado_q}", expanded=True):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Puntos Obtenidos", f"{round(ptos_obtenidos, 2)} pts")
                        c2.metric("Puntos Máximos Habilitados", f"{round(ptos_max_q, 2)} pts")
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
                                f"**Observaciones Generales del Q:** {q['observaciones']}"
                            )

                        st.markdown("**Desglose por Apartados:**")
                        for apartado, group in df_det.groupby("apartado"):
                            st.markdown(f"#### 📌 {apartado}")
                            for _, row in group.iterrows():
                                col1, col2 = st.columns([3, 1])
                                col1.write(f"• **{row['subapartado']}**")
                                if row.get("observaciones"):
                                    col1.caption(f"Obs: {row['observaciones']}")
                                col2.metric("Puntuación", f"{row['puntuacion']} pts")
                            st.divider()

        if puntuaciones_obtenidas:
            total_puntos_obt = sum(puntuaciones_obtenidas)
            total_puntos_max = sum(puntuaciones_maximas)
            nota_media_anual = (
                sum(notas_sobre_10) / len(notas_sobre_10) if notas_sobre_10 else 0
            )
            min_puntos_aprobar_anual = (media_objetivo_sql / 10.0) * total_puntos_max

            st.markdown("---")
            st.subheader("🏆 Resumen Anual Global (Trimestres Habilitados)")

            col_g1, col_g2, col_g3, col_g4 = st.columns(4)
            col_g1.metric(
                "Puntos Totales Obtenidos", f"{round(total_puntos_obt, 2)} pts"
            )
            col_g2.metric(
                "Puntuación Máxima Posible", f"{round(total_puntos_max, 2)} pts"
            )
            col_g3.metric(
                f"Mínimo Global para Aprobar ({media_objetivo_sql}/10)",
                f"{round(min_puntos_aprobar_anual, 2)} pts",
            )
            col_g4.metric(
                "Nota Media Anual (Escala 0 - 10)", f"{round(nota_media_anual, 2)} / 10"
            )

            if nota_media_anual >= media_objetivo_sql:
                st.success(
                    f"🎉 **ESTADO ANUAL: APROBADO** (Nota: {round(nota_media_anual, 2)}/10"
                    f" - Objetivo Requerido: {media_objetivo_sql})"
                )
            else:
                st.error(
                    f"⚠️ **ESTADO ANUAL: SUSPENSO** (Nota: {round(nota_media_anual, 2)}/10"
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
                    st.caption(f"Informe actualizado el: {inf_resp[0]['created_at']}")
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
            pwd_db = usuario.get("password") or usuario.get("contrasena") or "1234"
            if pwd_input == pwd_db or not pwd_input:
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

    # MENÚ PRINCIPAL
    else:
        st.info(f"🎯 **Criterio de Evaluación:** Para obtener un resultado **APROBADO**, debes alcanzar una nota mínima de **{UMBRAL_APROBADO_PORCENTAJE / 10} / 10** ({int(UMBRAL_APROBADO_PORCENTAJE)}% de aciertos). Tiempo configurado por pregunta: **{TIEMPO_LIMITE_PREGUNTA} segundos**.")

        if st.session_state.es_croma:
            (
                tab_examenes,
                tab_admin_manual,
                tab_admin_resultados,
                tab_admin_export,
                tab_admin_analisis,
                tab_admin_informes_ia,
                tab_admin_gestion,
                tab_admin_trimestral,
            ) = st.tabs([
                "📝 Realizar Examen",
                "📄 Cargar Manual / Prompt",
                "📊 Resultados / Edición",
                "📥 Exportación Exámenes e Importación Datos",
                "📈 Analítica e IA",
                "🤖 Informes IA",
                "⚙️ Gestión y Configuración",
                "📋 Evaluaciones Trimestrales",
            ])
        else:
            (
                tab_examenes,
                tab_mis_resultados,
                tab_mi_analisis,
                tab_emp_trimestral,
            ) = st.tabs([
                "📝 Realizar Examen",
                "📊 Mis Resultados e Historial",
                "📈 Mi Rendimiento e Informes IA",
                "📋 Evaluaciones Trimestrales",
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
                                
                                registrar_inicio_examen_bd(nombre_apt, ex_obj["id"])
                                st.session_state.examen_activo = True
                                st.rerun()

        # TAB: EVALUACIONES TRIMESTRALES DE EMPLEADOS
        tab_trimestral_target = tab_admin_trimestral if st.session_state.es_croma else tab_emp_trimestral
        with tab_trimestral_target:
            st.subheader("📋 Evaluaciones Trimestrales")
            anio_actual = datetime.datetime.now().year
            sel_anio_eval = st.number_input("Selecciona el año:", min_value=2020, max_value=2030, value=anio_actual, key="num_anio_eval")
            
            if st.session_state.es_croma:
                res_emp = supabase.table("empleados").select("id, nombre").eq("activo", True).execute()
                list_emp = res_emp.data if res_emp.data else []
                if list_emp:
                    map_emp = {e["nombre"]: e["id"] for e in list_emp}
                    emp_sel_eval = st.selectbox("Selecciona Empleado:", list(map_emp.keys()))
                    if emp_sel_eval:
                        renderizar_mis_evaluaciones(map_emp[emp_sel_eval], emp_sel_eval, sel_anio_eval)
            else:
                renderizar_mis_evaluaciones(st.session_state.user_id, st.session_state.user_nombre, sel_anio_eval)

        # ADMIN CROMA - EXPORTACIÓN E IMPORTACIÓN CSV COMPLETO
        if st.session_state.es_croma and tab_admin_export:
            with tab_admin_export:
                st.subheader("📥 Exportación e Importación Datos CSV")
                archivo_csv_import = st.file_uploader("Seleccionar archivo CSV para importar:", type=["csv"], key="csv_import_uploader_tab")
                
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
                            for idx_row, row in df_csv.iterrows():
                                nombre_emp = str(row.get("nombre_empleado") or row.get("nombre empleado") or "").strip()
                                emp_id = map_empleados.get(nombre_emp.lower(), None)
                                
                                resp_raw = row.get("respuestas_usuario", "[]")
                                try:
                                    resp_json = json.loads(resp_raw) if isinstance(resp_raw, str) else resp_raw
                                except Exception:
                                    resp_json = []

                                fecha_inicio_clean = limpiar_timestamp_sql(row.get("fecha_inicio"))
                                fecha_fin_clean = limpiar_timestamp_sql(row.get("fecha_fin"))

                                registro_nuevo = {
                                    "empleado_id": emp_id,
                                    "nombre_empleado": nombre_emp if nombre_emp else "Desconocido",
                                    "apartado": str(row.get("apartado") or row.get("Apartado") or "General"),
                                    "fecha_inicio": fecha_inicio_clean,
                                    "fecha_fin": fecha_fin_clean,
                                    "tiempo_total_segundos": int(row.get("tiempo_total_segundos") or 0),
                                    "nota": float(row.get("nota") or 0.0),
                                    "porcentaje_obtenido": float(row.get("porcentaje_obtenido") or 0.0),
                                    "respuestas_usuario": resp_json,
                                    "activo": True
                                }
                                supabase.table("intentos_examen").insert(registro_nuevo).execute()
                                registros_insertados += 1

                            st.success(f"✅ ¡Importación finalizada! Se insertaron {registros_insertados} registros correctamente.")
                        except Exception as err_imp:
                            st.error(f"❌ Error al importar CSV: {err_imp}")
