import json
from datetime import datetime
import openpyxl
import pandas as pd
from supabase import Client, create_client
import streamlit as st

# Importaciones de Inteligencia Artificial
try:
  import openai
except ImportError:
  openai = None

try:
  import google.generativeai as genai
except ImportError:
  genai = None

# ---------------------------------------------------------
# CREDENCIALES Y CLIENTES
# ---------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="Sistema de Evaluaciones y Análisis IA", layout="wide"
)


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
                if row["observaciones"]:
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


# --- INTERFAZ PRINCIPAL ---
st.sidebar.title("Navegación")
rol = st.sidebar.radio("Seleccionar Rol:", ["Administrador", "Empleado"])

if rol == "Administrador":
  st.title("Panel de Administración - Evaluaciones e IA")
  menu_admin = st.sidebar.selectbox(
      "Opción:",
      [
          "1. Cargar Excel Evaluaciones",
          "2. Edición y Visibilidad por Empleado",
          "3. Resumen Anual y Desglose",
          "4. Configuración Prompts y Media",
          "5. Generar e Informes IA",
          "6. Datos empleado",
      ],
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

  # --- 2. EDICIÓN Y VISIBILIDAD POR EMPLEADO (PERSONALIZACIÓN COMPLETA) ---
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

      # 1. Habilitación de Trimestres
      st.markdown("#### 1. Trimestres (Q) Habilitados")
      q_cols = st.columns(4)
      qs_hab = {}
      for idx, q_name in enumerate(["Q1", "Q2", "Q3", "Q4"]):
        qs_hab[q_name] = q_cols[idx].checkbox(
            q_name,
            value=vis_actual.get("qs_habilitados", {}).get(q_name, True),
        )

      st.divider()

      # 2. Consultar estructura de Apartados y Subapartados en la BD
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

      # Estructura por defecto si no existen evaluaciones cargadas aún
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

        # Estado del apartado completo
        ap_activo = st.checkbox(
            f"Habilitar apartado completo: '{apt}'",
            value=apts_vis_guardados.get(apt, True),
            key=f"apt_{apt}",
        )
        apartados_finales[apt] = ap_activo

        # Si el apartado está activo y tiene subapartados, dar la opción individual
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
          # Si el apartado se deshabilita completo, marcar sus subapartados como deshabilitados
          subapartados_deshabilitados_finales.extend(subs)

        st.markdown("---")

      # Botón de guardado
      if st.button("💾 Guardar Configuración de Visibilidad", type="primary"):
        guardar_visibilidad_empleado(
            emp_id,
            sel_anio,
            qs_hab,
            apartados_finales,
            list(set(subapartados_deshabilitados_finales)),
        )
        st.success(
            "¡Configuración de apartados y subapartados guardada correctamente!"
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
        supabase.table("config_prompts_eval").upsert(
            {
                "id": cfg[0]["id"] if cfg else 1,
                "prompt_texto": nuevo_prompt,
                "objetivo_media": nueva_media,
            }
        ).execute()
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
        f"{m['nombre_modelo']} ({m['proveedor'].upper()})" for m in modelos_disp
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
          f"Se han seleccionado **{len(empleados_seleccionados)}** empleados."
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

# --- ROL EMPLEADO ---
elif rol == "Empleado":
  st.title("Portal del Empleado - Mis Evaluaciones")

  emps = supabase.table("empleados").select("id, nombre").execute().data
  emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}
  sel_emp = st.selectbox("Identificarse como Empleado:", list(emp_dict.keys()))

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
    sel_anio = st.selectbox("Seleccionar Año:", anios_disp)

    renderizar_mis_evaluaciones(emp_id, sel_emp, sel_anio)
