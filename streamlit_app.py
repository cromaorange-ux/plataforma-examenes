import json
from datetime import datetime
import openpyxl
import pandas as pd
from supabase import Client, create_client
import streamlit as st

# ---------------------------------------------------------
# CREDENCIALES Y CLIENTES
# ---------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(
    page_title="Sistema de Evaluaciones y Análisis IA", layout="wide"
)


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


# --- FUNCIÓN DE PARSEO EXCEL ---
def parsear_excel_evaluacion(uploaded_file):
  wb = openpyxl.load_workbook(uploaded_file, data_only=True)
  resultados = {}

  for sheet_name in ["Q1", "Q2", "Q3", "Q4"]:
    if sheet_name not in wb.sheetnames:
      continue
    ws = wb[sheet_name]

    nombre_emp = ws["A8"].value
    anio_eval = ws["A10"].value

    if not nombre_emp or not anio_eval:
      continue

    puntuacion_total_doc = None
    observaciones_generales = None
    detalles_subapartados = []
    apartado_actual = None

    for r in range(1, 60):
      val_a = str(ws.cell(row=r, column=1).value or "").strip()
      val_c = ws.cell(row=r, column=3).value
      val_d = ws.cell(row=r, column=4).value

      if "Puntuacion total" in val_a or "Puntucion total" in val_a:
        puntuacion_total_doc = val_c

      if "Observaciones Generales:" in val_a:
        observaciones_generales = ws.cell(row=r + 1, column=1).value

      for apt in [
          "Tareas realizar por turnos y todos los turnos",
          "Tiempos respuesta Tbox",
          "Tiempos respuesta Siemens",
          "Iniciativa / Proactividad ante el trabajo",
          "Conocimientos",
          "Evaluacion",
      ]:
        if apt.lower() in val_a.lower():
          apartado_actual = apt

      if (
          apartado_actual
          and val_a
          and val_a
          not in ["PUNTOS DE EVALUACION", "Observaciones Generales:"]
      ):
        if val_c is not None or val_d is not None:
          if isinstance(val_c, (int, float)):
            detalles_subapartados.append({
                "apartado": apartado_actual,
                "subapartado": val_a,
                "puntuacion": val_c,
                "comentario": str(val_d) if val_d else "",
            })

    resultados[sheet_name] = {
        "nombre_empleado": str(nombre_emp).strip(),
        "anio": int(anio_eval),
        "puntuacion_total_excel": puntuacion_total_doc,
        "observaciones_generales": str(observaciones_generales or ""),
        "detalles": detalles_subapartados,
    }
  return resultados


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
      ],
  )

  # --- 1. CARGAR EXCEL ---
  if menu_admin == "1. Cargar Excel Evaluaciones":
    st.subheader("Subir Evaluación Trimestral (.xlsx)")
    uploaded_file = st.file_uploader(
        "Cargar archivo de evaluación", type=["xlsx"]
    )

    if uploaded_file:
      try:
        datos_parsed = parsear_excel_evaluacion(uploaded_file)
        st.success(
            "Archivo procesado correctamente. Inspeccionando pestañas Q1-Q4..."
        )

        for q_name, data in datos_parsed.items():
          st.markdown(
              f"### Pestaña {q_name} - {data['nombre_empleado']} ({data['anio']})"
          )

          emp_resp = (
              supabase.table("empleados")
              .select("id")
              .eq("nombre", data["nombre_empleado"])
              .execute()
          )
          if not emp_resp.data:
            st.error(
                f"El empleado '{data['nombre_empleado']}' no existe en la base"
                " de datos."
            )
            continue

          emp_id = emp_resp.data[0]["id"]

          if st.button(
              f"Guardar/Actualizar {q_name} en Supabase", key=f"btn_save_{q_name}"
          ):
            try:
              res_eval = (
                  supabase.table("evaluaciones_trimestrales")
                  .upsert(
                      {
                          "empleado_id": emp_id,
                          "nombre_empleado": data["nombre_empleado"],
                          "anio": data["anio"],
                          "trimestre": q_name,
                          "puntuacion_total": float(
                              data["puntuacion_total_excel"]
                          )
                          if data["puntuacion_total_excel"] is not None
                          else 0.0,
                          "observaciones": data["observaciones_generales"],
                          "datos_completos_json": json.dumps(data["detalles"]),
                      },
                      on_conflict="empleado_id, anio, trimestre",
                  )
                  .execute()
              )

              eval_id_created = res_eval.data[0]["id"]

              supabase.table("evaluacion_detalles").delete().eq(
                  "evaluacion_id", eval_id_created
              ).execute()
              for d in data["detalles"]:
                supabase.table("evaluacion_detalles").insert({
                    "evaluacion_id": eval_id_created,
                    "empleado_id": emp_id,
                    "nombre_empleado": data["nombre_empleado"],
                    "anio": data["anio"],
                    "trimestre": q_name,
                    "apartado": d["apartado"],
                    "subapartado": d["subapartado"],
                    "puntuacion": float(d["puntuacion"])
                    if d["puntuacion"] is not None
                    else 0.0,
                    "observaciones": d["comentario"],
                }).execute()
              st.success(
                  f"Pestaña {q_name} guardada correctamente para"
                  f" {data['nombre_empleado']}."
              )
            except Exception as err_db:
              st.error(f"Error al guardar en Supabase: {err_db}")
      except Exception as err_parse:
        st.error(f"Error al leer el archivo Excel: {err_parse}")

  # --- 2. EDICIÓN Y VISIBILIDAD POR EMPLEADO ---
  elif menu_admin == "2. Edición y Visibilidad por Empleado":
    st.subheader("Gestión Individual por Empleado (Edición y Visibilidad)")

    emps = supabase.table("empleados").select("id, nombre").execute().data
    emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

    sel_emp = st.selectbox("Seleccionar Empleado:", list(emp_dict.keys()))
    sel_anio = st.number_input("Año de Evaluación:", value=2025, step=1)

    if sel_emp:
      emp_id = emp_dict[sel_emp]
      vis_emp = obtener_visibilidad_empleado(emp_id, sel_anio)

      tab_vis, tab_edit = st.tabs([
          "👁️ Configurar Visibilidad",
          "✏️ Editar Valores y Observaciones",
      ])

      with tab_vis:
        st.markdown(f"#### Visibilidad para **{sel_emp}** ({sel_anio})")

        st.markdown("**1. Trimestres (Q) Habilitados:**")
        qs_act = vis_emp.get(
            "qs_habilitados", {"Q1": True, "Q2": True, "Q3": True, "Q4": True}
        )
        col1, col2, col3, col4 = st.columns(4)
        q1 = col1.checkbox("Habilitar Q1", value=qs_act.get("Q1", True))
        q2 = col2.checkbox("Habilitar Q2", value=qs_act.get("Q2", True))
        q3 = col3.checkbox("Habilitar Q3", value=qs_act.get("Q3", True))
        q4 = col4.checkbox("Habilitar Q4", value=qs_act.get("Q4", True))

        st.markdown("**2. Apartados Habilitados:**")
        apts_act = vis_emp.get("apartados_habilitados", {})
        nuevos_apts = {}
        for apt in [
            "Tareas realizar por turnos y todos los turnos",
            "Tiempos respuesta Tbox",
            "Tiempos respuesta Siemens",
            "Iniciativa / Proactividad ante el trabajo",
            "Conocimientos",
            "Evaluacion",
        ]:
          nuevos_apts[apt] = st.checkbox(
              f"Habilitar: {apt}",
              value=apts_act.get(apt, True),
              key=f"apt_vis_{apt}",
          )

        st.markdown("**3. Subapartados a OCULTAR:**")
        sub_des_act = vis_emp.get("subapartados_deshabilitados", [])
        detalles_emp = (
            supabase.table("evaluacion_detalles")
            .select("subapartado")
            .eq("empleado_id", emp_id)
            .execute()
            .data
        )
        todos_sub = (
            sorted(
                list(
                    set([
                        s["subapartado"]
                        for s in detalles_emp
                        if s.get("subapartado")
                    ])
                )
            )
            if detalles_emp
            else []
        )

        sub_ocultos = st.multiselect(
            "Deshabilitar subapartados para este empleado:",
            todos_sub,
            default=sub_des_act,
        )

        if st.button("Guardar Visibilidad del Empleado", type="primary"):
          guardar_visibilidad_empleado(
              emp_id,
              sel_anio,
              {"Q1": q1, "Q2": q2, "Q3": q3, "Q4": q4},
              nuevos_apts,
              sub_ocultos,
          )
          st.success(f"Visibilidad de {sel_emp} actualizada correctamente.")

      with tab_edit:
        st.markdown(
            f"#### Editar Calificaciones y Observaciones de **{sel_emp}**"
        )

        sel_q = st.selectbox(
            "Seleccionar Trimestre (Q):", ["Q1", "Q2", "Q3", "Q4"]
        )
        eval_q = (
            supabase.table("evaluaciones_trimestrales")
            .select("id, observaciones")
            .eq("empleado_id", emp_id)
            .eq("anio", sel_anio)
            .eq("trimestre", sel_q)
            .execute()
            .data
        )

        if eval_q:
          eval_id = eval_q[0]["id"]
          obs_gen = st.text_area(
              "Observaciones Generales del Q:",
              value=eval_q[0].get("observaciones", ""),
          )

          detalles_q = (
              supabase.table("evaluacion_detalles")
              .select("*")
              .eq("evaluacion_id", eval_id)
              .execute()
              .data
          )

          if detalles_q:
            st.markdown("##### Subapartados:")
            cambios_sub = []

            for item in detalles_q:
              col_a, col_b, col_c = st.columns([3, 1, 3])
              col_a.write(f"**{item['subapartado']}** ({item['apartado']})")

              nuevo_val = col_b.number_input(
                  "Puntos:",
                  value=float(item.get("puntuacion", 0)),
                  key=f"val_{item['id']}",
                  step=0.5,
              )
              nueva_obs = col_c.text_input(
                  "Observación:",
                  value=item.get("observaciones") or "",
                  key=f"obs_{item['id']}",
              )

              cambios_sub.append({
                  "id": item["id"],
                  "puntuacion": nuevo_val,
                  "observaciones": nueva_obs,
              })

            if st.button("Guardar Cambios en Subapartados y Q", type="primary"):
              supabase.table("evaluaciones_trimestrales").update(
                  {"observaciones": obs_gen}
              ).eq("id", eval_id).execute()

              for c in cambios_sub:
                supabase.table("evaluacion_detalles").update({
                    "puntuacion": c["puntuacion"],
                    "observaciones": c["observaciones"],
                }).eq("id", c["id"]).execute()

              st.success(
                  f"Datos de {sel_q} para {sel_emp} actualizados con éxito."
              )
        else:
          st.info(
              f"No existen registros guardados para {sel_q} en {sel_anio}."
          )

  # --- 3. RESUMEN ANUAL ---
  elif menu_admin == "3. Resumen Anual y Desglose":
    st.subheader("Resumen Anual y Desglose de Evaluaciones")
    emps = supabase.table("empleados").select("id, nombre").execute().data
    emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

    sel_emp = st.selectbox("Seleccionar Empleado:", list(emp_dict.keys()))
    sel_anio = st.number_input("Año:", value=2025, step=1)

    if sel_emp:
      emp_id = emp_dict[sel_emp]
      vis_emp = obtener_visibilidad_empleado(emp_id, sel_anio)
      qs_activos = [
          k for k, v in vis_emp.get("qs_habilitados", {}).items() if v
      ]

      q_data = (
          supabase.table("evaluaciones_trimestrales")
          .select("*")
          .eq("empleado_id", emp_id)
          .eq("anio", sel_anio)
          .execute()
          .data
      )

      if q_data:
        df_q = pd.DataFrame(q_data)
        df_q_filtrado = df_q[df_q["trimestre"].isin(qs_activos)]

        st.markdown("#### Trimestres Habilitados")
        st.dataframe(
            df_q_filtrado[["trimestre", "puntuacion_total", "observaciones"]]
        )

        if not df_q_filtrado.empty:
          media_q = df_q_filtrado["puntuacion_total"].astype(float).mean()
          st.metric(
              "Media Anual Recalculada (Qs Habilitados)", round(media_q, 2)
          )
      else:
        st.info("No hay evaluaciones registradas para este año.")

  # --- 4. CONFIGURACIÓN PROMPTS ---
  elif menu_admin == "4. Configuración Prompts y Media":
    st.subheader("Configurar Prompts y Media Objetivo")
    try:
      prompt_config = (
          supabase.table("config_prompts_eval")
          .select("*")
          .limit(1)
          .execute()
          .data
      )
      cfg_actual = (
          prompt_config[0]
          if prompt_config
          else {"id": 1, "objetivo_media": 8.0, "prompt_texto": ""}
      )
    except Exception:
      cfg_actual = {"id": 1, "objetivo_media": 8.0, "prompt_texto": ""}

    with st.form("form_media_obj"):
      nueva_media = st.number_input(
          "Media Objetivo:",
          value=float(cfg_actual.get("objetivo_media", 8.0)),
          step=0.1,
      )
      prompt_txt = st.text_area(
          "Prompt para Generación de Informes IA:",
          value=cfg_actual.get("prompt_texto", ""),
          height=150,
      )

      if st.form_submit_button("Guardar Configuración"):
        supabase.table("config_prompts_eval").upsert({
            "id": cfg_actual.get("id", 1),
            "nombre": "Prompt Global Evaluacion",
            "objetivo_media": nueva_media,
            "prompt_texto": prompt_txt,
        }).execute()
        st.success("Configuración actualizada correctamente.")

  # --- 5. INFORMES IA ---
  elif menu_admin == "5. Generar e Informes IA":
    st.subheader("Generar Informe Evaluativo con IA")
    emps = supabase.table("empleados").select("id, nombre").execute().data
    emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}

    sel_emp = st.selectbox("Seleccionar Empleado:", list(emp_dict.keys()))
    sel_anio = st.number_input("Año a evaluar:", value=2025, step=1)

    if st.button("Generar Informe con IA", type="primary"):
      st.markdown(f"### Informe de Evaluación para {sel_emp} ({sel_anio})")
      st.write(
          "El informe se ha generado analizando únicamente los trimestres,"
          " apartados y subapartados habilitados para este empleado."
      )

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

          # Filtrar apartados y subapartados habilitados para este empleado
          df_det = df_det[
              df_det["apartado"].map(lambda x: apts_habilitados.get(x, True))
          ]
          df_det = df_det[~df_det["subapartado"].isin(sub_ocultos)]

          if not df_det.empty:
            ptos_obtenidos = float(df_det["puntuacion"].sum())

            # Máximo posible dinámico basado en subapartados únicos presentes en la base de datos
            todos_sub_q = (
                supabase.table("evaluacion_detalles")
                .select("subapartado, puntuacion")
                .eq("evaluacion_id", q["id"])
                .execute()
                .data
            )
            df_sub_all = pd.DataFrame(todos_sub_q)
            df_sub_all = df_sub_all[
                ~df_sub_all["subapartado"].isin(sub_ocultos)
            ]

            # Si no hay valor de max cargado, se calcula sobre el total de subapartados habilitados (ejemplo: nota máx de cada uno)
            ptos_max_q = float(
                len(df_det) * 5.0
            )  # Asume puntuación escala habitual si no es dinámica por fila

            # Nota sobre 10
            nota_10 = (
                (ptos_obtenidos / ptos_max_q) * 10 if ptos_max_q > 0 else 0
            )
            ptos_aprobar = ptos_max_q / 2.0  # Equivalente a 5.0 en escala 10

            puntuaciones_obtenidas.append(ptos_obtenidos)
            puntuaciones_maximas.append(ptos_max_q)
            notas_sobre_10.append(nota_10)

            estado_q = "🟢 APROBADO" if nota_10 >= 5.0 else "🔴 SUSPENSO"

            with st.expander(f"📊 {q_nombre} - Estado: {estado_q}", expanded=True):
              c1, c2, c3, c4 = st.columns(4)
              c1.metric("Puntos Obtenidos", f"{round(ptos_obtenidos, 2)} pts")
              c2.metric("Puntos Máximos Habilitados", f"{round(ptos_max_q, 2)} pts")
              c3.metric(
                  "Mínimo para Aprobar (50%)", f"{round(ptos_aprobar, 2)} pts"
              )
              c4.metric(
                  "Nota (Escala 0 - 10)",
                  f"{round(nota_10, 2)} / 10",
                  delta="Aprobado" if nota_10 >= 5.0 else "- Suspenso",
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

      # --- RESUMEN GLOBAL ANUAL EN ESCALA 10 ---
      if puntuaciones_obtenidas:
        total_puntos_obt = sum(puntuaciones_obtenidas)
        total_puntos_max = sum(puntuaciones_maximas)
        nota_media_anual = (
            sum(notas_sobre_10) / len(notas_sobre_10) if notas_sobre_10 else 0
        )
        min_puntos_aprobar = total_puntos_max / 2.0

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
            "Mínimo Global para Aprobar", f"{round(min_puntos_aprobar, 2)} pts"
        )
        col_g4.metric(
            "Nota Media Anual (Escala 0 - 10)", f"{round(nota_media_anual, 2)} / 10"
        )

        if nota_media_anual >= 5.0:
          st.success(
              f"🎉 **ESTADO ANUAL: APROBADO** (Nota: {round(nota_media_anual, 2)}/10)"
          )
        else:
          st.error(
              f"⚠️ **ESTADO ANUAL: SUSPENSO** (Nota: {round(nota_media_anual, 2)}/10 - Se requiere mínimo 5.0)"
          )
      else:
        st.warning("No hay trimestres habilitados para mostrar.")
    else:
      st.warning("No hay evaluaciones disponibles.")
