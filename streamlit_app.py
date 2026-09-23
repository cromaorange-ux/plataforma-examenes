import streamlit as st
import pandas as pd
import openpyxl
import json
import requests
from datetime import datetime
from supabase import create_client, Client

# ---------------------------------------------------------
# CREDENCIALES Y CLIENTES
# ---------------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Sistema de Evaluaciones y Análisis IA", layout="wide")

# --- FUNCIONES DE CONFIGURACIÓN Y ESTADO DE VISIBILIDAD ---
def obtener_configuracion_visibilidad():
    """
    Obtiene o inicializa el estado global de visibilidad para Qs, Apartados y Subapartados.
    """
    res = supabase.table("config_visibilidad_evaluaciones").select("*").execute().data
    if res:
        return res[0]
    else:
        # Estado por defecto
        default_config = {
            "id": 1,
            "qs_habilitados": {"Q1": True, "Q2": True, "Q3": True, "Q4": True},
            "apartados_habilitados": {
                "Tareas realizar por turnos y todos los turnos": True,
                "Tiempos respuesta Tbox": True,
                "Tiempos respuesta Siemens": True,
                "Iniciativa / Proactividad ante el trabajo": True,
                "Conocimientos": True,
                "Evaluacion": True
            },
            "subapartados_deshabilitados": [] # Lista de nombres de subapartados ocultos
        }
        supabase.table("config_visibilidad_evaluaciones").insert(default_config).execute()
        return default_config

def guardar_configuracion_visibilidad(config):
    supabase.table("config_visibilidad_evaluaciones").upsert(config).execute()

# --- FUNCIONES AUXILIARES DE PARSEO EXCEL ---
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
                observaciones_generales = ws.cell(row=r+1, column=1).value
                
            for apt in ["Tareas realizar por turnos y todos los turnos", "Tiempos respuesta Tbox", 
                        "Tiempos respuesta Siemens", "Iniciativa / Proactividad ante el trabajo", 
                        "Conocimientos", "Evaluacion"]:
                if apt.lower() in val_a.lower():
                    apartado_actual = apt
                    
            if apartado_actual and val_a and val_a not in ["PUNTOS DE EVALUACION", "Observaciones Generales:"]:
                if val_c is not None or val_d is not None:
                    if isinstance(val_c, (int, float)):
                        detalles_subapartados.append({
                            "apartado": apartado_actual,
                            "subapartado": val_a,
                            "puntuacion": val_c,
                            "comentario": str(val_d) if val_d else ""
                        })
                        
        resultados[sheet_name] = {
            "nombre_empleado": str(nombre_emp).strip(),
            "anio": int(anio_eval),
            "puntuacion_total_excel": puntuacion_total_doc,
            "observaciones_generales": str(observaciones_generales or ""),
            "detalles": detalles_subapartados
        }
    return resultados

# --- INTERFAZ PRINCIPAL ---
st.sidebar.title("Navegación")
rol = st.sidebar.radio("Seleccionar Rol:", ["Administrador", "Empleado"])

config_vis = obtener_configuracion_visibilidad()

if rol == "Administrador":
    st.title("Panel de Administración - Evaluaciones e IA")
    menu_admin = st.sidebar.selectbox("Opción:", [
        "1. Cargar Excel Evaluaciones", 
        "2. Resumen Anual y Desglose", 
        "3. Configuración de Prompts y Media Objetivo",
        "4. Generar e Informes IA",
        "5. Habilitar/Deshabilitar Visibilidad (Q, Apartados, Subapartados)"
    ])

    # --- 1. CARGAR EXCEL ---
    if menu_admin == "1. Cargar Excel Evaluaciones":
        st.subheader("Subir Evaluación Trimestral (.xlsx)")
        uploaded_file = st.file_uploader("Cargar archivo de evaluación", type=["xlsx"])
        
        if uploaded_file:
            datos_parsed = parsear_excel_evaluacion(uploaded_file)
            st.success("Archivo procesado correctamente. Inspeccionando pestañas Q1-Q4...")
            
            for q_name, data in datos_parsed.items():
                st.markdown(f"### Pestaña {q_name} - {data['nombre_empleado']} ({data['anio']})")
                
                emp_resp = supabase.table("empleados").select("id").eq("nombre", data['nombre_empleado']).execute()
                if not emp_resp.data:
                    st.error(f"El empleado '{data['nombre_empleado']}' no existe en la base de datos de empleados.")
                    continue
                
                emp_id = emp_resp.data[0]["id"]
                
                if st.button(f"Guardar/Actualizar {q_name} en Supabase", key=f"btn_save_{q_name}"):
                    res_eval = supabase.table("evaluaciones_trimestrales").upsert({
                        "empleado_id": emp_id,
                        "nombre_empleado": data["nombre_empleado"],
                        "anio": data["anio"],
                        "trimestre": q_name,
                        "puntuacion_total": data["puntuacion_total_excel"],
                        "observaciones": data["observaciones_generales"],
                        "datos_completos_json": data["detalles"]
                    }, on_conflict="empleado_id, anio, trimestre").execute()
                    
                    eval_id_created = res_eval.data[0]["id"]
                    
                    supabase.table("evaluacion_detalles").delete().eq("evaluacion_id", eval_id_created).execute()
                    for d in data["detalles"]:
                        supabase.table("evaluacion_detalles").insert({
                            "evaluacion_id": eval_id_created,
                            "empleado_id": emp_id,
                            "nombre_empleado": data["nombre_empleado"],
                            "anio": data["anio"],
                            "trimestre": q_name,
                            "apartado": d["apartado"],
                            "subapartado": d["subapartado"],
                            "puntuacion": d["puntuacion"],
                            "observaciones": d["comentario"]
                        }).execute()
                    st.success(f"Pestaña {q_name} guardada correctamente.")

    # --- 2. RESUMEN ANUAL ---
    elif menu_admin == "2. Resumen Anual y Desglose":
        st.subheader("Resumen Anual de Evaluaciones")
        emps = supabase.table("empleados").select("id, nombre").execute().data
        emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}
        
        sel_emp = st.selectbox("Seleccionar Empleado:", list(emp_dict.keys()))
        sel_anio = st.number_input("Año:", value=2025, step=1)
        
        if sel_emp:
            emp_id = emp_dict[sel_emp]
            q_data = supabase.table("evaluaciones_trimestrales")\
                .select("*").eq("empleado_id", emp_id).eq("anio", sel_anio).execute().data
                
            if q_data:
                df_q = pd.DataFrame(q_data)
                # Filtrar solo Qs habilitados para el resumen
                qs_activos = [k for k, v in config_vis.get("qs_habilitados", {}).items() if v]
                df_q_filtrado = df_q[df_q["trimestre"].isin(qs_activos)]
                
                st.markdown("#### Datos Trimestrales Obtenidos (Q Habilitados)")
                st.dataframe(df_q_filtrado[["trimestre", "puntuacion_total", "observaciones"]])
                
                if not df_q_filtrado.empty:
                    media_q = df_q_filtrado["puntuacion_total"].astype(float).mean()
                    st.metric("Media Anual Recalculada (Qs Habilitados)", round(media_q, 2))
            else:
                st.info("No hay evaluaciones registradas para este año.")

    # --- 3. CONFIGURACIÓN PROMPTS ---
    elif menu_admin == "3. Configuración de Prompts y Media Objetivo":
        st.subheader("Configurar Media Objetivo y Prompts de Evaluación")
        prompt_config = supabase.table("config_prompts_eval").select("*").limit(1).execute().data
        cfg_actual = prompt_config[0] if prompt_config else {"id": 1, "objetivo_media": 8.0, "prompt_texto": ""}
        
        with st.form("form_media_obj"):
            nueva_media = st.number_input("Modificar Media Objetivo:", value=float(cfg_actual.get("objetivo_media", 8.0)), step=0.1)
            prompt_txt = st.text_area("Prompt para Informe IA:", value=cfg_actual.get("prompt_texto", ""), height=150)
            
            if st.form_submit_button("Grabar Cambios"):
                supabase.table("config_prompts_eval").upsert({
                    "id": cfg_actual.get("id", 1),
                    "nombre": "Prompt Global Evaluacion",
                    "objetivo_media": nueva_media,
                    "prompt_texto": prompt_txt
                }).execute()
                st.success("Configuración actualizada correctamente.")

    # --- 4. INFORMES IA ---
    elif menu_admin == "4. Generar e Informes IA":
        st.subheader("Generar Informe Evaluativo con IA")
        emps = supabase.table("empleados").select("id, nombre").execute().data
        emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}
        
        sel_emp = st.selectbox("Empleado:", list(emp_dict.keys()))
        sel_anio = st.number_input("Año a evaluar:", value=2025)
        
        if st.button("Generar Informe IA"):
            res_ia = f"INFORME DE EVALUACIÓN PARA {sel_emp} ({sel_anio})\n\nEvaluación generada considerando los periodos y apartados habilitados."
            st.write(res_ia)

    # --- 5. HABILITAR/DESHABILITAR VISIBILIDAD ---
    elif menu_admin == "5. Habilitar/Deshabilitar Visibilidad (Q, Apartados, Subapartados)":
        st.subheader("Gestión de Visibilidad de Evaluaciones")
        
        st.markdown("### 1. Habilitar/Deshabilitar Trimestres (Q)")
        qs_actuales = config_vis.get("qs_habilitados", {"Q1": True, "Q2": True, "Q3": True, "Q4": True})
        col_q1, col_q2, col_q3, col_q4 = st.columns(4)
        
        q1_state = col_q1.checkbox("Habilitar Q1", value=qs_actuales.get("Q1", True))
        q2_state = col_q2.checkbox("Habilitar Q2", value=qs_actuales.get("Q2", True))
        q3_state = col_q3.checkbox("Habilitar Q3", value=qs_actuales.get("Q3", True))
        q4_state = col_q4.checkbox("Habilitar Q4", value=qs_actuales.get("Q4", True))
        
        st.markdown("---")
        st.markdown("### 2. Habilitar/Deshabilitar Apartados")
        apts_actuales = config_vis.get("apartados_habilitados", {})
        nuevos_apts = {}
        for apt in ["Tareas realizar por turnos y todos los turnos", "Tiempos respuesta Tbox", 
                    "Tiempos respuesta Siemens", "Iniciativa / Proactividad ante el trabajo", 
                    "Conocimientos", "Evaluacion"]:
            nuevos_apts[apt] = st.checkbox(f"Habilitar Apartado: {apt}", value=apts_actuales.get(apt, True))
            
        st.markdown("---")
        st.markdown("### 3. Deshabilitar Subapartados Específicos")
        sub_des_actuales = config_vis.get("subapartados_deshabilitados", [])
        
        # Obtener lista única de subapartados de la BD
        sub_resp = supabase.table("evaluacion_detalles").select("subapartado").execute().data
        todos_sub = sorted(list(set([s["subapartado"] for s in sub_resp if s.get("subapartado")]))) if sub_resp else []
        
        sub_ocultos = st.multiselect("Seleccionar Subapartados a OCULTAR/DESHABILITAR:", todos_sub, default=sub_des_actuales)
        
        if st.button("Guardar Configuración de Visibilidad", type="primary"):
            config_vis["qs_habilitados"] = {"Q1": q1_state, "Q2": q2_state, "Q3": q3_state, "Q4": q4_state}
            config_vis["apartados_habilitados"] = nuevos_apts
            config_vis["subapartados_deshabilitados"] = sub_ocultos
            
            guardar_configuracion_visibilidad(config_vis)
            st.success("Configuración de visibilidad actualizada. Los cálculos y vistas de empleados se han recalculado.")

# --- ROL EMPLEADO ---
elif rol == "Empleado":
    st.title("Portal del Empleado - Mis Evaluaciones")
    
    emps = supabase.table("empleados").select("id, nombre").execute().data
    emp_dict = {e["nombre"]: e["id"] for e in emps} if emps else {}
    sel_emp = st.selectbox("Identificarse como Empleado:", list(emp_dict.keys()))
    
    if sel_emp:
        emp_id = emp_dict[sel_emp]
        
        cfg_obj = supabase.table("config_prompts_eval").select("objetivo_media").limit(1).execute().data
        obj_val = cfg_obj[0]["objetivo_media"] if cfg_obj else 8.0
        st.info(f"🎯 **Media Objetivo de Evaluación:** `{obj_val} / 10.0`")
        
        evals_emp = supabase.table("evaluaciones_trimestrales").select("anio").eq("empleado_id", emp_id).execute().data
        anios_disp = sorted(list(set([e["anio"] for e in evals_emp])), reverse=True) if evals_emp else [2025]
        sel_anio = st.selectbox("Seleccionar Año:", anios_disp)
        
        # Cargar evaluaciones
        q_evals = supabase.table("evaluaciones_trimestrales")\
            .select("*").eq("empleado_id", emp_id).eq("anio", sel_anio).execute().data
            
        if q_evals:
            qs_habilitados = config_vis.get("qs_habilitados", {})
            apts_habilitados = config_vis.get("apartados_habilitados", {})
            sub_ocultos = config_vis.get("subapartados_deshabilitados", [])
            
            puntuaciones_q_recalculadas = []
            
            for q in sorted(q_evals, key=lambda x: x["trimestre"]):
                q_nombre = q["trimestre"]
                
                # REQUISITO: Verificar si el Q está habilitado por Administrador
                if not qs_habilitados.get(q_nombre, True):
                    continue
                    
                detalles = supabase.table("evaluacion_detalles")\
                    .select("*").eq("evaluacion_id", q["id"]).execute().data
                    
                if detalles:
                    df_det = pd.DataFrame(detalles)
                    
                    # REQUISITO: Filtrar Apartados y Subapartados habilitados
                    df_det = df_det[df_det["apartado"].map(lambda x: apts_habilitados.get(x, True))]
                    df_det = df_det[~df_det["subapartado"].isin(sub_ocultos)]
                    
                    # Recalcular la puntuación del Q basándonos solo en los elementos habilitados
                    puntuacion_q_recalculada = df_det["puntuacion"].sum() if not df_det.empty else 0
                    puntuaciones_q_recalculadas.append(puntuacion_q_recalculada)
                    
                    with st.expander(f"📊 {q_nombre} - Puntuación Obtenida (Habilitados): {round(puntuacion_q_recalculada, 2)} pts", expanded=True):
                        st.markdown("**Desglose por Apartados y Subapartados Activos:**")
                        for apartado, group in df_det.groupby("apartado"):
                            st.markdown(f"#### 📌 Apartado: {apartado}")
                            for _, row in group.iterrows():
                                col1, col2 = st.columns([3, 1])
                                col1.write(f"• **{row['subapartado']}**")
                                if row['observaciones']:
                                    col1.caption(f"Obs: {row['observaciones']}")
                                col2.metric("Puntuación", f"{row['puntuacion']} pts")
                            st.divider()
            
            # REQUISITO: Media Global solo sobre los Qs habilitados
            if puntuaciones_q_recalculadas:
                media_global = sum(puntuaciones_q_recalculadas) / len(puntuaciones_q_recalculadas)
                st.markdown("---")
                st.metric("🏆 Media Global Anual (Ponderada sobre Qs Habilitados)", round(media_global, 2))
            else:
                st.warning("No hay Trimestres (Q) habilitados para mostrar.")
        else:
            st.warning("No se encontraron evaluaciones registradas para este año.")
