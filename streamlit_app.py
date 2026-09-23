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
# Inicializar la conexión con Supabase usando los Secrets de Streamlit
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Sistema de Evaluaciones y Análisis IA", layout="wide")

# --- FUNCIONES AUXILIARES DE PARSEO EXCEL ---
MAPA_SUBAPARTADOS = {
    "Turno mañana": ("Tareas realizar por turnos y todos los turnos", 3),
    "Turno Fin de semana Mañana": ("Tareas realizar por turnos y todos los turnos", 3),
    "Turno Tarde": ("Tareas realizar por turnos y todos los turnos", 3),
    "Turno Noche": ("Tareas realizar por turnos y todos los turnos", 3),
    "Turno Fin de semana Noche": ("Tareas realizar por turnos y todos los turnos", 3),
    "Todos los turnos": ("Tareas realizar por turnos y todos los turnos", 3),
    "% menos de 1 %": ("Tiempos respuesta Tbox", 3), # O Siemens según el apartado
    "tiempo mas de 20 minutos": ("Tiempos respuesta Tbox", 3),
    "Numero alarmas mas de 15 minutos (inferior a 10)": ("Tiempos respuesta Tbox", 3),
    "Sugerencia de ideas / Mejoras / Realización de tabajos sin indicar nada": ("Iniciativa / Proactividad ante el trabajo", 3),
    "Conocimientos aplicados en puesto trabajo": ("Conocimientos", 1),
    "Teorica (ANUAL)": ("Evaluacion", 1),
    "Practica (ANUAL)": ("Evaluacion", 1),
    "Herramienta (ANUAL)": ("Evaluacion", 1),
    "Dejar operativo portatil desde 0": ("Evaluacion", 1)
}

def parsear_excel_evaluacion(uploaded_file):
    wb = openpyxl.load_workbook(uploaded_file, data_only=True)
    resultados = {}
    
    for sheet_name in ["Q1", "Q2", "Q3", "Q4"]:
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        
        # Obtener Nombre y Año
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
            
            # Buscar Puntuación Total
            if "Puntuacion total" in val_a or "Puntucion total" in val_a:
                puntuacion_total_doc = val_c
                
            # Buscar Observaciones Generales
            if "Observaciones Generales:" in val_a:
                observaciones_generales = ws.cell(row=r+1, column=1).value
                
            # Detectar Cabecera de Apartados
            for apt in ["Tareas realizar por turnos y todos los turnos", "Tiempos respuesta Tbox", 
                        "Tiempos respuesta Siemens", "Iniciativa / Proactividad ante el trabajo", 
                        "Conocimientos", "Evaluacion"]:
                if apt.lower() in val_a.lower():
                    apartado_actual = apt
                    
            # Detectar Subapartados y Valores
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

# --- CÁLCULO RECALCULADO CON APARTADOS HABILITADOS ---
def calcular_puntuacion_bd(detalles_subapartados):
    pesos_resp = supabase.table("config_apartados_pesos").select("*").execute()
    config_pesos = {item["apartado"]: item for item in pesos_resp.data}
    
    pesos_habilitados_suma = sum(v["peso_porcentaje"] for k, v in config_pesos.items() if v["habilitado"])
    if pesos_habilitados_suma == 0:
        return 0, 0
        
    puntuacion_obtenida_total = 0
    
    # Agrupar por apartado
    df = pd.DataFrame(detalles_subapartados)
    if df.empty:
        return 0, 0
        
    for apt, group in df.groupby("apartado"):
        cfg = config_pesos.get(apt, {"habilitado": True, "peso_porcentaje": 0})
        if not cfg["habilitado"]:
            continue
            
        puntos_obtenidos = group["puntuacion"].sum()
        # Normalizar el peso ajustado al 100%
        peso_ajustado = (cfg["peso_porcentaje"] / pesos_habilitados_suma) * 100
        # Puntos base según la suma
        puntuacion_obtenida_total += (puntos_obtenidos * (peso_ajustado / 100))
        
    porcentaje = (puntuacion_obtenida_total / 10.0) * 100 if puntuacion_obtenida_total <= 10 else puntuacion_obtenida_total
    return round(puntuacion_obtenida_total, 2), round(porcentaje, 2)

# --- INTERFAZ PRINCIPAL ---
st.sidebar.title("Navegación")
rol = st.sidebar.radio("Seleccionar Rol:", ["Administrador", "Empleado"])

if rol == "Administrador":
    st.title("Panel de Administración - Evaluaciones e IA")
    menu_admin = st.sidebar.selectbox("Opción:", [
        "1. Cargar Excel Evaluaciones", 
        "2. Resumen Anual y Desglose", 
        "3. Configuración de Prompts y Media Objetivo",
        "4. Generar e Informes IA",
        "5. Habilitar/Deshabilitar Visibilidad"
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
                
                # Verificar coincidencia de empleado en Supabase
                emp_resp = supabase.table("empleados").select("id").eq("nombre", data['nombre_empleado']).execute()
                if not emp_resp.data:
                    st.error(f"El empleado '{data['nombre_empleado']}' no existe en la base de datos de empleados.")
                    continue
                
                emp_id = emp_resp.data[0]["id"]
                
                # Verificar si ya existe el registro
                eval_existente = supabase.table("evaluaciones_trimestrales")\
                    .select("id, datos_completos_json")\
                    .eq("empleado_id", emp_id)\
                    .eq("anio", data["anio"])\
                    .eq("trimestre", q_name).execute()
                
                hay_diferencias = False
                detalles_viejos = []
                
                if eval_existente.data:
                    eval_id = eval_existente.data[0]["id"]
                    det_viejos_resp = supabase.table("evaluacion_detalles").select("*").eq("evaluacion_id", eval_id).execute()
                    detalles_viejos = det_viejos_resp.data
                    
                    # Comparar datos
                    df_nuevos = pd.DataFrame(data["detalles"])
                    df_viejos = pd.DataFrame(detalles_viejos)
                    
                    if not df_viejos.empty:
                        # Detección simple de diferencias
                        if len(df_nuevos) != len(df_viejos) or float(data["puntuacion_total_excel"] or 0) != float(eval_existente.data[0].get("puntuacion_total") or 0):
                            hay_diferencias = True
                
                if hay_diferencias:
                    st.warning(f"Se han detectado diferencias con los datos almacenados de {q_name}.")
                    st.json({"Valores Nuevos Excel": data["detalles"]})
                    
                    with st.form(f"form_auditoria_{q_name}"):
                        usuario_mod = st.text_input("Tu Nombre (Usuario Modificador):", key=f"usr_{q_name}")
                        motivo_cambio = st.text_area("Motivo de la actualización:", key=f"mot_{q_name}")
                        confirmar = st.form_submit_button("Confirmar y Actualizar SQL")
                        
                        if confirmar:
                            if not usuario_mod or not motivo_cambio:
                                st.error("Debes indicar tu nombre y el motivo del cambio.")
                            else:
                                # Registrar Auditoría de subapartados
                                for d in data["detalles"]:
                                    supabase.table("auditoria_subapartados").insert({
                                        "evaluacion_id": eval_id,
                                        "empleado_id": emp_id,
                                        "anio": data["anio"],
                                        "trimestre": q_name,
                                        "seccion": d["apartado"],
                                        "subapartado": d["subapartado"],
                                        "valor_nuevo": d["puntuacion"],
                                        "valor_nuevo_texto": d["comentario"],
                                        "usuario_modificador": usuario_mod,
                                        "motivo": motivo_cambio
                                    }).execute()
                                
                                st.success(f"Dato de {q_name} actualizado y registrado en auditoría.")
                else:
                    if st.button(f"Guardar/Actualizar {q_name} en Supabase", key=f"btn_save_{q_name}"):
                        ptos_bd, pct_bd = calcular_puntuacion_bd(data["detalles"])
                        
                        # Upsert evaluacion trimestral
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
                        
                        # Limpiar y reinsertar detalles
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
        emp_dict = {e["nombre"]: e["id"] for e in emps}
        
        sel_emp = st.selectbox("Seleccionar Empleado:", list(emp_dict.keys()))
        sel_anio = st.number_input("Año:", value=2025, step=1)
        
        if sel_emp:
            emp_id = emp_dict[sel_emp]
            q_data = supabase.table("evaluaciones_trimestrales")\
                .select("*").eq("empleado_id", emp_id).eq("anio", sel_anio).execute().data
                
            if q_data:
                df_q = pd.DataFrame(q_data)
                st.markdown("#### Datos Trimestrales Obtenidos")
                st.dataframe(df_q[["trimestre", "puntuacion_total", "observaciones"]])
                
                # Resumen de la media de los Q almacenados
                media_q = df_q["puntuacion_total"].astype(float).mean()
                st.metric("Media Anual Obtenida (Promedio Q1-Q4)", round(media_q, 2))
            else:
                st.info("No hay evaluaciones registradas para este año.")

    # --- 3. CONFIGURACIÓN DE PROMPTS Y MEDIA OBJETIVO ---
    elif menu_admin == "3. Configuración de Prompts y Media Objetivo":
        st.subheader("Configurar Media Objetivo y Prompts de Evaluación")
        
        prompt_config = supabase.table("config_prompts_eval").select("*").limit(1).execute().data
        cfg_actual = prompt_config[0] if prompt_config else {"id": 1, "objetivo_media": 8.0, "prompt_texto": ""}
        
        st.markdown(f"**Media Objetivo Actual:** `{cfg_actual.get('objetivo_media', 8.0)}`")
        
        with st.form("form_media_obj"):
            nueva_media = st.number_input("Modificar Media Objetivo:", value=float(cfg_actual.get("objetivo_media", 8.0)), step=0.1)
            prompt_txt = st.text_area("Prompt para Informe IA:", value=cfg_actual.get("prompt_texto", ""), height=150)
            
            usr_mod = st.text_input("Tu Nombre (Obligatorio para guardar):")
            motivo_mod = st.text_input("Motivo del cambio (Obligatorio para guardar):")
            
            if st.form_submit_button("Grabar Cambios"):
                if not usr_mod or not motivo_mod:
                    st.error("Es obligatorio indicar la persona que cambia el dato y el motivo.")
                else:
                    # Guardar actualización
                    supabase.table("config_prompts_eval").upsert({
                        "id": cfg_actual.get("id", 1),
                        "nombre": "Prompt Global Evaluacion",
                        "objetivo_media": nueva_media,
                        "prompt_texto": prompt_txt,
                        "actualizado_por": usr_mod
                    }).execute()
                    
                    # Registrar Auditoría
                    supabase.table("auditoria_evaluaciones").insert({
                        "nombre_empleado": "CONFIG_SISTEMA",
                        "trimestre": "ANUAL",
                        "anio": datetime.now().year,
                        "metrica": "objetivo_media",
                        "valor_anterior": cfg_actual.get("objetivo_media", 8.0),
                        "valor_nuevo": nueva_media,
                        "usuario_modificador": usr_mod,
                        "motivo": motivo_mod
                    }).execute()
                    st.success("Configuración actualizada y auditada correctamente.")

    # --- 4. GENERAR INFORMES IA ---
    elif menu_admin == "4. Generar e Informes IA":
        st.subheader("Generar Informe Evaluativo con IA")
        emps = supabase.table("empleados").select("id, nombre").execute().data
        emp_dict = {e["nombre"]: e["id"] for e in emps}
        
        sel_emp = st.selectbox("Empleado:", list(emp_dict.keys()))
        sel_anio = st.number_input("Año a evaluar:", value=2025)
        
        # Opciones múltiples de Modelos IA
        modelos = supabase.table("modelos_ai").select("nombre_modelo").eq("activo", True).execute().data
        mod_list = [m["nombre_modelo"] for m in modelos] if modelos else ["gemini-2.5-flash", "gpt-4o", "claude-3-5-sonnet"]
        sel_modelo = st.selectbox("Seleccionar Modelo IA:", mod_list)
        
        if st.button("Generar Informe IA"):
            # Obtener datos acumulados
            q_data = supabase.table("evaluaciones_trimestrales")\
                .select("*").eq("empleado_id", emp_dict[sel_emp]).execute().data
            
            prompt_cfg = supabase.table("config_prompts_eval").select("*").limit(1).execute().data[0]
            
            prompt_final = f"""
            {prompt_cfg['prompt_texto']}
            
            Empleado: {sel_emp}
            Año: {sel_anio}
            Media Objetivo Requerida: {prompt_cfg['objetivo_media']}
            Histórico Trimestral Registrado: {json.dumps(q_data, default=str)}
            """
            
            # Simulación de respuesta de IA (Integrar la llamada HTTP al proveedor seleccionado)
            res_ia = f"INFORME DE EVALUACIÓN PARA {sel_emp} ({sel_anio})\n\n" \
                     f"El empleado presenta una trayectoria sostenida comparada contra la media objetivo de {prompt_cfg['objetivo_media']}.\n" \
                     f"Fortalezas: Cumplimiento de turnos y tiempos de respuesta.\nÁreas de Mejora: Seguimiento puntual de incidencias."
            
            st.markdown("### Resultado Generado:")
            st.write(res_ia)
            
            # Guardar resultado en SQL
            supabase.table("resultados_evaluacion_ia").insert({
                "empleado_id": emp_dict[sel_emp],
                "nombre_empleado": sel_emp,
                "anio": sel_anio,
                "modelo_ia": sel_modelo,
                "resultado_texto": res_ia,
                "visible_empleado": False, # Deshabilitado por defecto
                "creado_por": "Admin"
            }).execute()
            st.success("Informe guardado en base de datos.")

    # --- 5. VISIBILIDAD ---
    elif menu_admin == "5. Habilitar/Deshabilitar Visibilidad":
        st.subheader("Gestión de Visibilidad de Resultados para Empleados")
        
        filtro_est = st.selectbox("Filtrar Estado:", ["Todos", "Habilitados", "Deshabilitados"])
        res_query = supabase.table("resultados_evaluacion_ia").select("*").order("anio", ascending=False)
        
        if filtro_est == "Habilitados":
            res_query = res_query.eq("visible_empleado", True)
        elif filtro_est == "Deshabilitados":
            res_query = res_query.eq("visible_empleado", False)
            
        resultados = res_query.execute().data
        
        for item in resultados:
            col1, col2, col3 = st.columns([3, 2, 2])
            col1.write(f"**{item['nombre_empleado']}** - Año: {item['anio']} ({item['modelo_ia']})")
            es_visible = col2.checkbox("Visible para Empleado", value=item.get("visible_empleado", False), key=f"vis_{item['id']}")
            
            if col3.button("Actualizar", key=f"btn_vis_{item['id']}"):
                supabase.table("resultados_evaluacion_ia").update({"visible_empleado": es_visible}).eq("id", item['id']).execute()
                st.success("Estado actualizado.")

# --- ROL EMPLEADO ---
elif rol == "Empleado":
    st.title("Portal del Empleado - Mis Evaluaciones")
    
    # Selección de Empleado identificado
    emps = supabase.table("empleados").select("id, nombre").execute().data
    emp_dict = {e["nombre"]: e["id"] for e in emps}
    sel_emp = st.selectbox("Identificarse como Empleado:", list(emp_dict.keys()))
    
    if sel_emp:
        emp_id = emp_dict[sel_emp]
        
        # Mostrar Media Objetivo Global
        cfg_obj = supabase.table("config_prompts_eval").select("objetivo_media").limit(1).execute().data
        obj_val = cfg_obj[0]["objetivo_media"] if cfg_obj else 8.0
        
        st.info(f"🎯 **Media Objetivo de Evaluación de la Empresa:** `{obj_val} / 10.0`")
        
        # Obtener años disponibles
        evals_emp = supabase.table("evaluaciones_trimestrales").select("anio").eq("empleado_id", emp_id).execute().data
        anios_disp = sorted(list(set([e["anio"] for e in evals_emp])), reverse=True) if evals_emp else [2025]
        
        sel_anio = st.selectbox("Seleccionar Año:", anios_disp)
        
        # Cargar datos por Q
        q_evals = supabase.table("evaluaciones_trimestrales")\
            .select("*").eq("empleado_id", emp_id).eq("anio", sel_anio).execute().data
            
        if q_evals:
            for q in sorted(q_evals, key=lambda x: x["trimestre"]):
                with st.expander(f"📊 Evaluaciones Trimestrales - {q['trimestre']}", expanded=True):
                    # Cargar detalles por subapartado
                    detalles = supabase.table("evaluacion_detalles")\
                        .select("*").eq("evaluacion_id", q["id"]).execute().data
                        
                    if detalles:
                        df_det = pd.DataFrame(detalles)
                        st.markdown("**Desglose por Apartados y Subapartados:**")
                        st.table(df_det[["apartado", "subapartado", "puntuacion", "observaciones"]])
                    
                    st.write(f"**Puntuación Total Obtenida (Excel):** `{q['puntuacion_total']}`")
                    st.write(f"**Observaciones Generales:** {q['observaciones']}")
        else:
            st.warning("No se encontraron evaluaciones registradas para este año.")
            
        # Informe IA (Si está habilitado)
        st.markdown("---")
        st.subheader("Informe Evaluativo de IA")
        informes = supabase.table("resultados_evaluacion_ia")\
            .select("*").eq("empleado_id", emp_id).eq("anio", sel_anio).eq("visible_empleado", True).execute().data
            
        if informes:
            inf = informes[0]
            st.success(f"Informe disponible generado por modelo: {inf['modelo_ia']}")
            st.text(inf["resultado_texto"])
        else:
            st.info("No hay informes de IA visibles publicados para este periodo.")
            st.info("No hay informes de IA visibles publicados para este periodo.")
