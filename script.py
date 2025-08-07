# ────────────────────────────────────────────────────────────
# LACC 2025 • Analítica de Participantes (Streamlit + Plotly)
# Limpieza avanzada + 15+ visualizaciones + integración de formularios de equipos
# ────────────────────────────────────────────────────────────
import io
import os
import re
import glob
import unicodedata
from datetime import datetime
from collections import defaultdict, Counter

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ========== Configuración página ==========
st.set_page_config(page_title="LACC 2025 • BI de Participantes",
                   page_icon="📊", layout="wide")
st.title("📊 LACC 2025 • Analítica de Participantes")

# ========== Sidebar: Carga ==========
st.sidebar.markdown("## Carga de datos (participantes)")
up = st.sidebar.file_uploader(
    "📂 Sube tu CSV exportado (opcional)", type=["csv"])


def _csv_candidates():
    files = [f for f in glob.glob("*.csv")]
    pref = [f for f in files if re.search(
        r"LACC2025_participantes\.csv$", f, re.I)]
    if pref:
        return pref + [f for f in files if f not in pref]
    return files


csv_choice = None
if up is None:
    candidates = _csv_candidates()
    if len(candidates) == 0:
        st.sidebar.info(
            "No encontré CSV en la carpeta. Sube uno o copia un .csv a la raíz.")
    elif len(candidates) == 1:
        csv_choice = candidates[0]
        st.sidebar.success(f"Usando: **{csv_choice}** (carpeta)")
    else:
        csv_choice = st.sidebar.selectbox(
            "O elige un CSV de la carpeta:", candidates)
        st.sidebar.success(f"Usando: **{csv_choice}** (carpeta)")

st.sidebar.markdown("---")
use_forms = st.sidebar.checkbox(
    "➕ Integrar formularios de equipos desde Excel (carpeta)", value=True)
st.sidebar.caption(
    "Detecta automáticamente archivos Excel tipo *Form_* / *Inscripciones* y hojas que contengan columnas de equipo.")

# ========== Utilidades de limpieza ==========


def _tidy(s):
    if pd.isna(s):
        return ""
    s = str(s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _to_title_es(s):
    s = _tidy(s).lower()
    base = unicodedata.normalize("NFKD", s)
    base = "".join([c for c in base if not unicodedata.combining(c)])
    rep = {
        "medellin": "Medellín", "bogota": "Bogotá", "bogota d.c": "Bogotá D.C",
        "palmira valle": "Palmira", "quiro": "Quito", "quito": "Quito",
        "mexico": "México", "cdmx": "Ciudad De México",
    }
    s2 = rep.get(base, None)
    if s2:
        return s2
    return _tidy(s).title()


def _as_int_age(x):
    try:
        v = int(float(str(x).replace(",", ".").strip()))
        return v if 13 <= v <= 90 else np.nan
    except:
        return np.nan


# Patrones para países (incluye sinónimos y provincias frecuentes mapeadas a país)
_PATTERNS = [
    (r"colom|antioquia|cundinamarca|bogot|yopal|ibagu|medell[ií]n|huila|tunj|zipaquir|itagu[ií]|cartagena", "Colombia"),
    (r"ecuad", "Ecuador"),
    (r"per[uú]", "Perú"),
    (r"mex|ciudad de m[eé]xico|estado de m[eé]xico|cdmx|edomex|distrito federal|df", "México"),
    (r"chile", "Chile"),
    (r"costa\s*rica", "Costa Rica"),
    (r"guatemala", "Guatemala"),
    (r"rep[úu]blica\s*dominicana|dominican republic|dominicana",
     "República Dominicana"),
    (r"espa(n|ñ)a|spain", "España"),
    (r"brasil|brazil", "Brasil"),
    (r"argentin", "Argentina"),
    (r"panam", "Panamá"),
    (r"uruguay", "Uruguay"),
    (r"paraguay", "Paraguay"),
    (r"boliv", "Bolivia"),
    (r"venez", "Venezuela"),
    (r"salvador|san salvador", "El Salvador"),
    (r"hondur", "Honduras"),
    (r"nicarag", "Nicaragua"),
    (r"ee\.?uu\.?|estados\s*unidos|united\s*states|usa|ohio|atlanta|georgia", "Estados Unidos"),
]
_VALID_COUNTRIES = {x for _, x in _PATTERNS}


def _normalize_country(raw):
    s = _tidy(raw).lower()
    if not s or s in {"nan", "none", "n/a", "na"}:
        return np.nan
    tokens = re.split(r"[\/\-\|,;•]+|\s{2,}", s)
    tokens = [t.strip() for t in tokens if t.strip()]
    probe = tokens + [s]
    for t in probe:
        for pat, dest in _PATTERNS:
            if re.search(pat, t):
                return dest
    tlast = tokens[-1] if tokens else s
    tlast = unicodedata.normalize("NFKD", tlast)
    tlast = "".join(c for c in tlast if not unicodedata.combining(c))
    return _tidy(tlast).title()


def _country_from_lugar(raw):
    """Extrae país desde 'lugar_nacimiento' con reglas robustas."""
    if pd.isna(raw):
        return np.nan
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "ninguno", "n/a", "na"}:
        return np.nan
    s0 = unicodedata.normalize("NFKD", s).encode(
        "ascii", "ignore").decode("ascii").lower()
    s0 = s0.replace(".", " ").replace("_", " ")
    s0 = re.sub(r"\s+", " ", s0)

    direct = [
        (r"\b(el\s*salvador)\b", "El Salvador"),
        (r"\b(brazil|brasil)\b", "Brasil"),
        (r"\b(chile)\b", "Chile"),
        (r"\b(costa\s*rica)\b", "Costa Rica"),
        (r"\b(argentina)\b", "Argentina"),
        (r"\b(peru|lima)\b", "Perú"),
        (r"\b(ecuador)\b", "Ecuador"),
        (r"\b(guatemala)\b", "Guatemala"),
        (r"\b(honduras)\b", "Honduras"),
        (r"\b(nicaragua)\b", "Nicaragua"),
        (r"\b(uruguay)\b", "Uruguay"),
        (r"\b(paraguay)\b", "Paraguay"),
        (r"\b(bolivia)\b", "Bolivia"),
        (r"\b(panama)\b", "Panamá"),
        (r"\b(espana|spain)\b", "España"),
        (r"\b(venezuela)\b", "Venezuela"),
        (r"\b(mexico|cdmx|distrito federal|df|edomex|estado de mexico|tula de allende|atlanta|ohio|georgia)\b", "México"),
        (r"\b(eu|ee ?uu|usa|united states)\b", "Estados Unidos"),
        (r"\b(republica\s*dominicana|dominican republic|dominicana)\b",
         "República Dominicana"),
    ]
    for pat, out in direct:
        if re.search(pat, s0):
            # excepciones: ciudades MX listadas arriba ya devuelven México
            return out

    pistas_col = r"(antioquia|medellin|medell[ií]n|itag[uü]i|bogota|cundinamarca|tolima|ibague|huila|neiva|tunja|zipaquira|cartagena|yopal|santa marta|barranco de loba|ciudad bolivar)"
    if re.search(pistas_col, s0):
        return "Colombia"

    tokens = re.split(r"[,\-/|•]+", s0)
    tokens = [t.strip() for t in tokens if t.strip()]
    for t in tokens[::-1]:
        c = _normalize_country(t)
        if isinstance(c, str) and len(c) >= 3:
            return c
    if re.search(r"colom", s0):
        return "Colombia"
    return np.nan


def _coalesce(df, candidates, default=None):
    for c in candidates:
        if c and c in df.columns:
            return c
    return default


def _clean_email(x):
    s = _tidy(x).lower()
    if s in {"null@gmail.com", "ninguno@no.com", "correo@correo.com", "test@test.com", "n/a", "na"}:
        return np.nan
    return s


def _norm_team(x):
    s = _tidy(x)
    s = re.sub(r"\s+", " ", s).strip(" .-_")
    return s if s else np.nan


def _person_id(row):
    if "correo" in row and pd.notna(row["correo"]) and str(row["correo"]).strip():
        return str(row["correo"]).lower().strip()
    key = " ".join([
        str(row.get("nombres", "")).strip().lower(),
        str(row.get("apellidos", "")).strip().lower(),
        str(row.get("ciudad", "")).strip().lower()
    ]).strip()
    return key if key else np.nan


def _first_csv_in_folder():
    return csv_choice

# ========== Lector robusto de formularios Excel (equipos) ==========


def _detect_header_row(df_raw):
    looks = ["equipo", "categoria", "modalidad", "nombres",
             "apellidos", "lugar_nacimiento", "pais", "country", "correo"]
    for i in range(min(5, len(df_raw))):
        row = [str(x).strip().lower() for x in list(df_raw.iloc[i, :].values)]
        score = sum(any(re.search(k, c) for c in row) for k in looks)
        if score >= 2:
            return i
    return None


def _read_team_sheet(path, sheet_name):
    probe = pd.read_excel(path, sheet_name=sheet_name, nrows=6, header=None)
    hdr = _detect_header_row(probe)
    if hdr is None:
        return None
    df = pd.read_excel(path, sheet_name=sheet_name, header=hdr)
    df.columns = [str(c).strip().lower() for c in df.columns]

    mincols = any(c in df.columns for c in ["equipo", "team"])
    minperson = any(c in df.columns for c in [
                    "nombres", "nombre", "first_name"]) or "correo" in df.columns
    if not (mincols and minperson):
        return None

    col_equipo = _coalesce(df, ["equipo", "team"])
    col_nom = _coalesce(df, ["nombres", "nombre", "first_name"])
    col_ape = _coalesce(df, ["apellidos", "apellido", "last_name"])
    col_mail = _coalesce(df, ["correo", "email", "mail"])
    # guardamos el nombre exacto para decidir función de país
    col_pais_raw = _coalesce(
        df, ["pais", "country", "lugar_nacimiento", "lugarnacimiento", "lugar de nacimiento"])
    col_mod = _coalesce(df, ["modalidad", "modality"])
    col_cat = _coalesce(df, ["categoria", "category"])

    keep = {}
    if col_equipo:
        keep["equipo"] = df[col_equipo].map(_norm_team)
    if col_nom:
        keep["nombres"] = df[col_nom].map(_tidy).str.title()
    if col_ape:
        keep["apellidos"] = df[col_ape].map(_tidy).str.title()
    if col_mail:
        keep["correo"] = df[col_mail].map(_clean_email)
    if col_pais_raw:
        if re.search(r"lugar", col_pais_raw):
            keep["pais_src"] = df[col_pais_raw].map(_country_from_lugar)
        else:
            keep["pais_src"] = df[col_pais_raw].map(_normalize_country)
    if col_mod:
        keep["modalidad_src"] = df[col_mod].astype(str).str.lower().str.strip()
    if col_cat:
        keep["categoria_src"] = df[col_cat].astype(str).str.lower().str.strip()

    out = pd.DataFrame(keep)
    if "equipo" in out:
        out["equipo"] = out["equipo"].replace({"": np.nan})
        out = out.dropna(subset=["equipo"])
    if "modalidad_src" in out:
        out["modalidad_src"] = out["modalidad_src"].replace(
            {"presencail": "presencial", "on line": "virtual", "online": "virtual"})
        out["modalidad_src"] = np.where(
            out["modalidad_src"].eq("virtual"), "Virtual", "Presencial")
    if "categoria_src" in out:
        out["categoria_src"] = out["categoria_src"].replace(
            {"academic": "academico", "countries": "pais"})
        out["categoria_src"] = out["categoria_src"].str.capitalize()
    return out


def read_team_forms_from_root():
    forms = []
    excel_files = [f for f in glob.glob("*.xlsx")+glob.glob("*.xls")
                   if re.search(r"(Form|Inscrip|CTF|Gobierno|Público|Publico|Women|EIA)", f, re.I)]
    for f in excel_files:
        try:
            xls = pd.ExcelFile(f)
            for sh in xls.sheet_names:
                df = _read_team_sheet(f, sh)
                if df is not None and not df.empty:
                    df["__file"] = f
                    df["__sheet"] = sh
                    forms.append(df)
        except Exception:
            continue
    if not forms:
        return pd.DataFrame()
    out = pd.concat(forms, ignore_index=True).drop_duplicates()
    out["persona_id"] = out.apply(
        lambda r: str(r["correo"]).lower().strip() if pd.notna(r.get("correo", np.nan)) and str(r.get("correo", "")).strip()
        else ("{} {}".format(_tidy(r.get("nombres", "")).lower(), _tidy(r.get("apellidos", "")).lower()).strip() or np.nan),
        axis=1
    )
    out["persona_id"] = out["persona_id"].replace({"": np.nan})
    return out

# ========== Carga principal ==========


@st.cache_data(show_spinner=False)
def load_and_clean(file, csv_choice):
    # CSV principal
    if file is not None:
        df = pd.read_csv(file, low_memory=False)
        src = getattr(file, "name", "subido.csv")
    else:
        if not csv_choice:
            st.stop()
        df = pd.read_csv(csv_choice, low_memory=False)
        src = csv_choice

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]

    # mapear columnas
    col_nombre = _coalesce(df, ["nombres", "nombres1"])
    col_apellido = _coalesce(df, ["apellidos"])
    col_correo = _coalesce(df, ["correo", "email", "mail"])
    col_ciudad = _coalesce(df, ["ciudad", "city"])
    col_country = _coalesce(
        df, ["country", "pais", "nacionalidad", "lugar_nacimiento", "lugarnacimiento"])
    col_modal = _coalesce(df, ["modalidad", "modality"])
    col_att = _coalesce(df, ["attendance"])
    col_edad = _coalesce(df, ["edad", "age"])
    col_equipo = _coalesce(df, ["equipo", "equipoir", "team"])
    col_sector = _coalesce(df, ["sector"])
    col_carrera = _coalesce(df, ["carrera"])
    col_univ = _coalesce(
        df, ["universidad", "entidad", "institucionedu", "instituciongob"])

    # strings básicos
    for c in [col_nombre, col_apellido, col_ciudad, col_modal, col_att, col_equipo, col_sector, col_carrera, col_univ]:
        if c in df:
            df[c] = df[c].apply(_tidy)

    # nombre/apellido bonitos
    if col_nombre in df:
        df["nombres"] = df[col_nombre].apply(
            lambda s: _tidy(s).title() if s else np.nan)
    if col_apellido in df:
        df["apellidos"] = df[col_apellido].apply(
            lambda s: _tidy(s).title() if s else np.nan)

    # correo
    if col_correo in df:
        df["correo"] = df[col_correo].apply(_clean_email)
    else:
        df["correo"] = np.nan

    # ciudad
    if col_ciudad in df:
        df["ciudad"] = df[col_ciudad].apply(
            _to_title_es).replace({"": "Desconocida"})
    else:
        df["ciudad"] = np.nan

    # país (usa normalizador; si la columna es lugar_nacimiento aplica extractor específico)
    if col_country in df:
        if re.search(r"lugar", col_country):
            df["pais"] = df[col_country].apply(_country_from_lugar)
        else:
            df["pais"] = df[col_country].apply(_normalize_country)
        # Si además existe lugar_nacimiento y país quedó vacío, rellena desde ahí
        col_lugar = _coalesce(df, ["lugar_nacimiento", "lugarnacimiento"])
        if col_lugar in df:
            pais_from_lugar = df[col_lugar].apply(_country_from_lugar)
            mask = df["pais"].isna() | df["pais"].astype(
                str).str.strip().eq("") | df["pais"].eq("Desconocido")
            df.loc[mask, "pais"] = pais_from_lugar
    else:
        df["pais"] = np.nan

    # edad
    if col_edad in df:
        edades = df[col_edad].apply(_as_int_age)
        df["edad"] = edades.fillna(
            round(edades.median())) if edades.notna().any() else np.nan
    else:
        df["edad"] = np.nan

    # modalidad declarada
    if col_modal in df:
        mod = df[col_modal].str.lower().str.strip()
        mod = mod.replace({"presencail": "presencial",
                          "on line": "virtual", "online": "virtual"})
        df["modalidad"] = np.where(mod.eq("virtual"), "Virtual", "Presencial")
    else:
        df["modalidad"] = "Presencial"

    # attendance (sin dato → Virtual)
    att = (df[col_att].astype(str).str.lower().str.strip()
           if col_att in df else pd.Series(index=df.index, dtype=object))
    att = att.replace({"sin dato attendance": "", "nan": "",
                      "none": "", "": "", "asistio": "asistió"})
    df["attendance"] = np.where(att.eq("asistió"), "Asistió", "Virtual")

    # equipo / sector / carrera / universidad
    df["equipo"] = (df[col_equipo] if col_equipo in df else np.nan).replace(
        {"": np.nan})
    df["sector"] = (df[col_sector] if col_sector in df else np.nan)
    df["carrera"] = (df[col_carrera] if col_carrera in df else np.nan)
    df["universidad"] = (df[col_univ] if col_univ in df else np.nan)

    # deduplicación fuerte
    before = len(df)
    if "correo" in df:
        df = df.drop_duplicates(subset=["correo"], keep="first")
    alt_keys = [k for k in ["nombres", "apellidos",
                            "docnumero", "telefono"] if k in df.columns]
    if alt_keys:
        df = df.drop_duplicates(subset=alt_keys, keep="first")
    removed = before - len(df)

    # ordenar columnas útiles al frente
    first = ["nombres", "apellidos", "correo", "pais", "ciudad", "modalidad",
             "attendance", "edad", "equipo", "universidad", "carrera", "sector"]
    cols = first + [c for c in df.columns if c not in first]
    df = df[cols]

    qc = {
        "archivo": src,
        "filas": len(df),
        "duplicados_eliminados": removed,
        "sin_correo": int(df["correo"].isna().sum()),
        "sin_pais": int(df["pais"].isna().sum()),
        "sin_ciudad": int(df["ciudad"].isna().sum()),
    }
    return df.reset_index(drop=True), qc


if up is None and not _first_csv_in_folder():
    st.info("👈 Sube un CSV o deja un CSV en la carpeta (elige uno en la barra lateral).")
    st.stop()

data, qc = load_and_clean(up, csv_choice)
st.success(
    f"✅ Cargado **{qc['archivo']}** • Filas: **{qc['filas']}** • Duplicados eliminados: **{qc['duplicados_eliminados']}**")
# === Hero: posicionamiento LATAM (cifra de YouTube editable) ===
YT_TOTAL = 4000  # cambia si tienes el número exacto (p.ej. 4213)

st.markdown(f"""
<style>
  .hero-black {{
    padding:16px 18px;
    border-radius:14px;
    background:#000;               /* fondo negro */
    color:#fff !important;         /* texto blanco */
    border:1px solid #222;         /* borde sutil */
    box-shadow: 0 8px 24px rgba(0,0,0,.35);
  }}
  .hero-black h3, .hero-black p, .hero-black b, .hero-black strong {{
    color:#fff !important;         /* fuerza blanco en títulos y negritas */
  }}
</style>

<div class="hero-black">
  <h3 style="margin:0;">
    🏆 LACC 2025 se consolida como el <b>evento de ciberseguridad más grande de Latinoamérica</b>
  </h3>
  <p style="margin:6px 0 0;">
    🎥 Participación en YouTube: <b>+{YT_TOTAL:,}</b> espectadores en el canal oficial.<br/>
    🌎 Representatividad LATAM y alcance regional sostenido.
  </p>
</div>
""", unsafe_allow_html=True)


# Mensaje espejo en la barra lateral
st.sidebar.markdown(
    f"**🏆 Hito 2025:** Más de **{YT_TOTAL:,}** espectadores en YouTube. "
    "LACC se afianza como el evento referente de **ciberseguridad en LATAM**."
)


# Ciudad: desconocida → Medellín (y normaliza Medellín)
data["ciudad"] = data["ciudad"].fillna("Medellín").replace(
    {"Desconocida": "Medellín", "Medellin": "Medellín"})

# ========== Integración de formularios de equipos ==========
teams_form = pd.DataFrame()
if use_forms:
    teams_form = read_team_forms_from_root()
    if teams_form.empty:
        st.warning(
            "No encontré formularios de equipos útiles en Excel. (¿Nombres de columnas distintos?)")
    else:
        st.success(
            f"📒 Formularios integrados: **{teams_form['__file'].nunique()}** archivo(s), **{len(teams_form)}** filas.")

# # ========== Descargas ==========
# buf = io.BytesIO()
# data.to_csv(buf, index=False, encoding="utf-8-sig")
# st.download_button("⬇️ Descargar CSV limpio", data=buf.getvalue(),
#                    file_name="LACC2025_limpio.csv", mime="text/csv")


# def export_excel(df):
#     try:
#         with pd.ExcelWriter("LACC2025_report.xlsx", engine="xlsxwriter") as xl:
#             df.to_excel(xl, index=False, sheet_name="Limpio")
#             pd.crosstab(df["pais"], df["modalidad"]).to_excel(
#                 xl, sheet_name="Pais x Modalidad")
#             pd.crosstab(df["pais"], df["attendance"]).to_excel(
#                 xl, sheet_name="Pais x Attendance")
#             (df.groupby("pais")["equipo"].nunique().rename("equipos_unicos")
#                .reset_index().to_excel(xl, index=False, sheet_name="Equipos por país"))
#     except ModuleNotFoundError:
#         try:
#             with pd.ExcelWriter("LACC2025_report.xlsx", engine="openpyxl") as xl:
#                 df.to_excel(xl, index=False, sheet_name="Limpio")
#                 pd.crosstab(df["pais"], df["modalidad"]).to_excel(
#                     xl, sheet_name="Pais x Modalidad")
#                 pd.crosstab(df["pais"], df["attendance"]).to_excel(
#                     xl, sheet_name="Pais x Attendance")
#                 (df.groupby("pais")["equipo"].nunique().rename("equipos_unicos")
#                    .reset_index().to_excel(xl, index=False, sheet_name="Equipos por país"))
#         except ModuleNotFoundError:
#             st.warning(
#                 "⚠️ No encontré 'xlsxwriter' ni 'openpyxl'. Instala uno: pip install xlsxwriter ó pip install openpyxl")


# export_excel(data)

# if os.path.exists("LACC2025_report.xlsx"):
#     with open("LACC2025_report.xlsx", "rb") as f:
#         st.download_button("⬇️ Descargar Excel (resúmenes)",
#                            data=f.read(), file_name="LACC2025_report.xlsx")

# st.divider()

# ========== Filtros ==========
st.subheader("🎛️ Filtros")
c_f1, c_f2, c_f3 = st.columns(3)
pais_sel = c_f1.multiselect("País", sorted(
    [p for p in data["pais"].dropna().unique()]), default=[])
mod_sel = c_f2.multiselect("Modalidad", ["Presencial", "Virtual"], default=[])
att_sel = c_f3.multiselect("Attendance", ["Asistió", "Virtual"], default=[])

df = data.copy()
if pais_sel:
    df = df[df["pais"].isin(pais_sel)]
if mod_sel:
    df = df[df["modalidad"].isin(mod_sel)]
if att_sel:
    df = df[df["attendance"].isin(att_sel)]

# ========== KPIs ==========
st.subheader("📌 Indicadores clave")
total = len(df)
asistio = int((df["attendance"] == "Asistió").sum())
virtual = int((df["attendance"] == "Virtual").sum())
paises = int(df["pais"].nunique(dropna=True))
edad_prom = (df["edad"].mean() if df["edad"].notna().any() else np.nan)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Registros", total)
c2.metric("Asistieron (presencial)", asistio)
c3.metric("Virtual (con presencia)", virtual)
c4.metric("Países", paises)
c5.metric("Edad promedio", f"{edad_prom:.1f}" if pd.notna(
    edad_prom) else "s/d")
st.caption(
    "**Nota:** *“Sin dato attendance” y vacíos se normalizan a **Virtual***.")


def show(fig, text):
    st.plotly_chart(fig, use_container_width=True)
    st.markdown(text)

# ========== Visualizaciones ==========
st.divider()
st.subheader("📈 Visualizaciones con insights")

# 1) Attendance (pie)
fig1 = px.pie(df, names="attendance",
              title="Asistencia real (Asistió vs Virtual)")
show(fig1, f"**{asistio}** asistieron; **{virtual}** virtual/no presencial.")

# 2) Modalidad (pie)
fig2 = px.pie(df, names="modalidad",
              title="Modalidad declarada en inscripción")
show(fig2, "Preferencia de registro.")

# 3) Edades (hist)
fig3 = px.histogram(df, x="edad", nbins=20, title="Distribución de edades")
fig3.update_layout(xaxis_title="Edad (años)", yaxis_title="Participantes")
med = df["edad"].median() if df["edad"].notna().any() else np.nan
show(fig3, f"Mediana ~ **{med:.0f}** años." if pd.notna(med)
     else "Sin datos de edad.")

# 4) Top ciudades
if df["ciudad"].notna().any():
    top_city = df["ciudad"].value_counts().nlargest(10).reset_index()
    top_city.columns = ["Ciudad", "Participantes"]
    fig4 = px.bar(top_city, x="Participantes", y="Ciudad",
                  orientation="h", title="Top 10 ciudades")
    fig4.update_layout(yaxis={'categoryorder': 'total ascending'})
    lead = f"**{top_city.iloc[0]['Ciudad']}** lidera" if len(top_city) else ""
    show(fig4, f"{lead}. 'Desconocida' se trató como **Medellín**.")

# 5) Top países
if df["pais"].notna().any():
    top_c = df["pais"].value_counts().nlargest(10).reset_index()
    top_c.columns = ["País", "Participantes"]
    fig5 = px.bar(top_c, x="País", y="Participantes",
                  title="Países con más participantes (Top 10)")
    show(fig5, "Normalización de países a partir de nacionalidad/ciudad/lugar.")

# 6) Mapa por país (ISO-3) — paleta **pastel** con **Colombia** en tono más fuerte
if df["pais"].notna().any():
    iso3_map = {
        "Colombia": "COL", "Cooombiano": "COL", "Costarricense": "CRI", "Dominicana": "DOM", "Dominicano": "DOM",
        "Ecuador": "ECU", "Ecuatoriana": "ECU", "Ecuatoriano": "ECU", "Guatemalteco": "GTM",
        "México": "MEX", "Mexico": "MEX", "Perú": "PER", "Peru": "PER", "Per": "PER",
        "Chile": "CHL", "Costa Rica": "CRI", "Guatemala": "GTM", "República Dominicana": "DOM", "Republica Dominicana": "DOM",
        "España": "ESP", "Brasil": "BRA", "Argentina": "ARG", "Panamá": "PAN", "Uruguay": "URY", "Paraguay": "PRY",
        "Bolivia": "BOL", "Venezuela": "VEN", "El Salvador": "SLV", "Honduras": "HND", "Nicaragua": "NIC",
        "Estados Unidos": "USA", "United States": "USA", "USA": "USA"
    }

    geo = df["pais"].dropna().value_counts().reset_index()
    geo.columns = ["pais_es", "participants"]
    geo["iso3"] = geo["pais_es"].map(iso3_map)

    faltantes = sorted(set(geo.loc[geo["iso3"].isna(), "pais_es"].tolist()))
    geo = geo.dropna(subset=["iso3"])

    if not geo.empty:
        # Bins por cuantiles para asegurar contraste visual
        n_unique = geo["participants"].nunique()
        q = min(5, n_unique) if n_unique > 0 else 1
        if q < 2:
            # si todos valen igual, hacemos una sola categoría
            geo["bin"] = 0
            edges = [geo["participants"].min(), geo["participants"].max()]
        else:
            geo["bin"], edges = pd.qcut(
                geo["participants"], q=q, labels=False, retbins=True, duplicates="drop")

        # Etiquetas legibles del rango
        labels = []
        for i in range(len(edges)-1):
            a, b = int(edges[i]), int(edges[i+1])
            if i == len(edges)-2:
                labels.append(f"{a}–{b}")
            else:
                labels.append(f"{a}–{b-1}")
        if len(labels) == 0:
            labels = ["Todos"]

        # asignar etiqueta por bin
        def _lab(i):
            try:
                return labels[int(i)]
            except:
                return labels[0]
        geo["bin_label"] = geo["bin"].apply(_lab)

        # Forzar Colombia al bin superior (más oscuro) si existe
        if (geo["iso3"] == "COL").any():
            top_label = labels[-1]
            geo.loc[geo["iso3"] == "COL", "bin_label"] = top_label

        # Paleta pastel (verde) de claro→fuerte
        pastel_green = ['#E8F5E9', '#C8E6C9', '#A5D6A7',
                        '#81C784', '#43A047']  # última = más fuerte
        # si hay menos bins, recorta
        palette = pastel_green[:len(labels)]
        color_map = {labels[i]: palette[i] for i in range(len(labels))}

        fig6 = px.choropleth(
            geo,
            locations="iso3",
            color="bin_label",            # categórico
            hover_name="pais_es",
            locationmode="ISO-3",
            color_discrete_map=color_map,
            title="Mapa de participación por país (pastel, Colombia más fuerte)"
        )
        fig6.update_traces(marker_line_color="white", marker_line_width=0.5)
        fig6.update_layout(
            geo=dict(scope="world", showcountries=True),
            margin=dict(l=0, r=0, t=60, b=0),
            legend_title_text="Rango de participantes"
        )
        fig6.update_traces(hovertemplate="<b>%{hovertext}</b><br>Participantes: %{customdata[0]}<extra></extra>",
                           customdata=np.stack([geo["participants"]], axis=-1))
        show(fig6, "Escala **pastel** por rangos; **Colombia** en el rango más fuerte.")
    else:
        st.info("No hay países mapeados a ISO-3 para el mapa.")
    if faltantes:
        st.caption("⚠️ Países sin mapeo ISO-3 (no se pintan): " +
                   ", ".join(faltantes))

# 7) Carreras (Top 15, AGRUPADAS: todo lo de Sistemas/Informática junto)
if "carrera" in df.columns and df["carrera"].notna().any():
    def _norm_carrera(x):
        s = _tidy(x)
        if not s:
            return np.nan
        s_ascii = unicodedata.normalize("NFKD", s).encode(
            "ascii", "ignore").decode("ascii")
        s_low = re.sub(r"[^a-z0-9\s/+\-]", " ", s_ascii.lower())
        s_low = re.sub(r"\s+", " ", s_low).strip()
        if re.search(r"(sistem|system|informatic|computaci)", s_low):
            return "Ingeniería de Sistemas / Informática"
        return _tidy(s).title()

    carreras_norm = df["carrera"].map(_norm_carrera)
    top_car = (carreras_norm.value_counts(dropna=True)
               .nlargest(15)
               .reset_index())
    top_car.columns = ["Carrera/Programa", "Participantes"]
    fig7 = px.bar(top_car, x="Participantes", y="Carrera/Programa",
                  orientation="h", title="Carreras / Programas (Top 15, agrupadas)")
    fig7.update_layout(yaxis={'categoryorder': 'total ascending'})
    show(fig7, "Formaciones más frecuentes. **Todas las variantes de Sistemas/Informática/Computación** se agrupan.")

# 8) Sector ↔ País (treemap + stacked) con normalización y reconciliación
if ("sector" in df.columns) or ("categoria" in df.columns):

    def _norm_sector_val(x):
        s = _tidy(x)
        if not s:
            return np.nan
        s0 = unicodedata.normalize('NFKD', s).encode(
            'ascii', 'ignore').decode('ascii').lower()
        s0 = re.sub(r'[^a-z]+', ' ', s0).strip()
        if re.search(r'\bacadem|univers|estudiant', s0):
            return 'Académico'
        if re.search(r'\bindustr|empresa|privad', s0):
            return 'Industria'
        if re.search(r'\bgob|gov|public|mil', s0):
            return 'Gobierno'
        if re.search(r'\bpais|countr', s0):
            return 'País'
        return np.nan

    if "sector" in df.columns:
        src = df["sector"]
        if "categoria" in df.columns:
            src = src.where(src.notna() & src.astype(
                str).str.strip().ne(""), df["categoria"])
    else:
        src = df["categoria"] if "categoria" in df.columns else pd.Series(
            index=df.index, dtype=object)

    df["sector_norm"] = src.map(_norm_sector_val)

    # heurísticas para completar vacíos
    if "universidad" in df.columns:
        df.loc[df["sector_norm"].isna() & df["universidad"].notna(),
               "sector_norm"] = "Académico"
    if "correo" in df.columns:
        correo_low = df["correo"].astype(str).str.lower()
        df.loc[df["sector_norm"].isna() & correo_low.str.contains(
            r'(@.*gov|@.*gob|@.*mil|\.gov|\.gob)'), "sector_norm"] = "Gobierno"

    pais_col = df["pais"].fillna("Desconocido")

    total_reg = len(df)
    mapeados = int(df["sector_norm"].notna().sum())
    sin_sector = int(df["sector_norm"].isna().sum())

    treedata = (df[df["sector_norm"].notna()]
                .assign(pais=pais_col)
                .groupby(["sector_norm", "pais"])
                .size().reset_index(name="Participantes"))

    if not treedata.empty:
        fig8 = px.treemap(
            treedata,
            path=["sector_norm", "pais"],
            values="Participantes",
            title="Sectores representados por país (normalizado)"
        )
        fig8.update_traces(textinfo="label+value")
        show(fig8, f"Registros con sector mapeado: **{mapeados}** / **{total_reg}**  •  Sin sector: **{sin_sector}**. "
             "Categorías: Académico, Industria, Gobierno y País.")
    else:
        st.info("No hay datos suficientes para treemap de Sector por país.")

    st.subheader("Sector por país (Top 12 países)")
    top_countries = pais_col.value_counts().head(12).index.tolist()
    stacked = (df[df["sector_norm"].notna() & pais_col.isin(top_countries)]
               .assign(pais=pais_col)
               .groupby(["pais", "sector_norm"])
               .size().reset_index(name="Participantes"))
    if not stacked.empty:
        fig8b = px.bar(
            stacked, x="pais", y="Participantes", color="sector_norm",
            barmode="stack", title="Distribución por sector en países con más registros"
        )
        fig8b.update_layout(legend_title="Sector")
        show(fig8b, "Las barras por país deben sumar ≈ al total de registros de ese país (si difiere, son filas sin sector).")
    else:
        st.caption("No se pudo construir la barra apilada (falta sector o país).")

# 9) Nivel educativo
if "nivel" in df.columns and df["nivel"].notna().any():
    niv = df["nivel"].str.lower().str.replace(
        "maestria", "maestría").str.replace("especializacion", "especialización")
    niv = niv.str.capitalize().value_counts().reset_index()
    niv.columns = ["Nivel", "Participantes"]
    fig9 = px.bar(niv, x="Nivel", y="Participantes", title="Nivel educativo")
    show(fig9, "Corrección de tildes aplicada.")

# 10) Modalidad × Attendance (heatmap)
pv = pd.crosstab(df["modalidad"], df["attendance"]).fillna(0)
fig10 = px.imshow(pv, text_auto=True,
                  title="Modalidad inscrita × Asistencia real")
show(fig10, "Cruce modalidad declarada vs asistencia.")

# ========= 11–12) Equipos (con formularios + CSV) =========
st.subheader("🧩 Equipos (consolidado)")


def _equipos_consolidado(data, teams_form):
    base = data.copy()
    base["equipo_ref"] = base["equipo"].map(_norm_team)
    base["persona_id"] = base.apply(_person_id, axis=1)
    base["pais_csv"] = base["pais"]

    if teams_form is None or teams_form.empty:
        return base, pd.DataFrame()

    tf = teams_form.copy()
    tf["equipo_ref"] = tf["equipo"].map(_norm_team)
    tf["equipo_ref"] = tf["equipo_ref"].replace({"": np.nan})
    tf = tf.dropna(subset=["equipo_ref"])

    tf["pais_form"] = tf.get("pais_src", np.nan)

    cols = ["equipo_ref", "persona_id", "correo", "nombres",
            "apellidos", "pais_form", "modalidad_src", "categoria_src"]
    tf = tf[[c for c in cols if c in tf.columns]].copy()

    merged = pd.concat([
        base[["equipo_ref", "persona_id", "correo", "pais_csv"]],
        tf
    ], ignore_index=True)

    merged["pais_persona"] = merged["pais_form"].fillna(merged["pais_csv"])
    merged["persona_key"] = merged["persona_id"].fillna(merged["correo"]).fillna("")
    merged = merged[merged["persona_key"].astype(str).str.len() > 0]

    # --- Overrides manuales de país por equipo (AQUÍ) ---
    team_country_override = {
        _norm_team("PWN4D3R0S"): "Colombia",
        # agrega más si hace falta:
        # _norm_team("OTRO_EQUIPO"): "México",
    }
    if not merged.empty:
        mask_ovr = merged["equipo_ref"].isin(team_country_override.keys())
        merged.loc[mask_ovr, "pais_persona"] = merged.loc[mask_ovr, "equipo_ref"].map(team_country_override)
        # (opcional) mini-log para verificar en pantalla
        if mask_ovr.any():
            aplicados = (merged.loc[mask_ovr]
                              .groupby("equipo_ref")["persona_key"]
                              .nunique()
                              .reset_index(name="miembros_afectados"))
            st.caption("🔧 Overrides de país aplicados:")
            for _, r in aplicados.iterrows():
                st.caption(f"- {r['equipo_ref']} → {team_country_override[r['equipo_ref']]} "
                           f"(miembros ajustados: {int(r['miembros_afectados'])})")

    return base, merged

base_csv, merged = _equipos_consolidado(data, teams_form)

if merged.empty or merged["equipo_ref"].dropna().empty:
    st.info("No hay suficientes datos de **equipo** para análisis profundo. Revisa formularios/csv.")
else:
    dom = (merged.dropna(subset=["equipo_ref", "pais_persona"])
                 .groupby(["equipo_ref", "pais_persona"])["persona_key"].nunique()
                 .reset_index(name="miembros"))
    dom_sorted = dom.sort_values(
        ["equipo_ref", "miembros"], ascending=[True, False])
    eq_dom = dom_sorted.groupby("equipo_ref", as_index=False).first().rename(
        columns={"pais_persona": "pais_eq", "miembros": "miembros_top"})
    eq_size = merged.groupby("equipo_ref")[
        "persona_key"].nunique().reset_index(name="tamanio_equipo")
    eq = eq_dom.merge(eq_size, on="equipo_ref", how="left")

    # 11) Equipos por país (país dominante)
    equipos_por_pais = (eq.dropna(subset=["pais_eq"])
                          .groupby("pais_eq")["equipo_ref"].nunique()
                          .sort_values(ascending=False)
                          .reset_index(name="equipos_únicos"))
    fig11 = px.bar(equipos_por_pais, x="pais_eq", y="equipos_únicos",
                   title="Equipos por país (país dominante)")
    show(
        fig11, f"Total de equipos únicos: **{eq['equipo_ref'].nunique()}** en **{equipos_por_pais.shape[0]}** países.")

    # 12) Tamaño promedio/mediana por país
    size_stats = (eq.dropna(subset=["pais_eq"])
                    .groupby("pais_eq")["tamanio_equipo"]
                    .agg(media="mean", mediana="median", max="max")
                    .round(1)
                    .reset_index()
                    .sort_values("media", ascending=False))
    fig12 = px.bar(size_stats, x="pais_eq", y="media",
                   title="Tamaño promedio de equipo por país")
    fig12.update_layout(yaxis_title="Miembros promedio por equipo")
    show(fig12, "Promedio de integrantes por equipo por país.")

    # Líder por país
    leaders = (eq.sort_values(["pais_eq", "tamanio_equipo"], ascending=[True, False])
                 .groupby("pais_eq", as_index=False).first()[["pais_eq", "equipo_ref", "tamanio_equipo"]])
    if not leaders.empty:
        st.markdown("**Equipo líder por país (mayor tamaño):**")
        for _, r in leaders.iterrows():
            st.markdown(
                f"- **{r['pais_eq']}** → *{r['equipo_ref']}* ({int(r['tamanio_equipo'])} integrantes)")

    # Distribución global tamaños
    dist = eq["tamanio_equipo"].value_counts().sort_index().reset_index()
    dist.columns = ["Tamaño de equipo", "Cantidad de equipos"]
    fig12b = px.bar(dist, x="Tamaño de equipo", y="Cantidad de equipos",
                    title="Distribución global de tamaños de equipo")
    show(fig12b, "¿Cuántos equipos de 2, 3, 4…?")

# 13) Universidades / Entidades (Top 15)
if df["universidad"].notna().any():
    u = df["universidad"].value_counts().nlargest(15).reset_index()
    u.columns = ["Universidad/Entidad", "Participantes"]
    fig13 = px.bar(u, x="Participantes", y="Universidad/Entidad",
                   orientation="h", title="Universidades / Entidades (Top 15)")
    fig13.update_layout(yaxis={'categoryorder': 'total ascending'})
    show(fig13, "Instituciones con mayor presencia.")

# === Normalización fuerte de país (demónimo, ciudad→país, prefijo 3 letras) ===


def _canon_pais(x):
    s = _tidy(x)
    if not s:
        return np.nan
    a = unicodedata.normalize("NFKD", s).encode(
        "ascii", "ignore").decode("ascii").lower()

    # 1) ciudades/departamentos muy frecuentes → país
    city_to_country = {
        # Colombia
        "bogota|bogota d\.c|medellin|antioquia|cundinamarca|soacha|apartado|el bagre|aquitania|yopal|ibague|tunj|huila|zipaquira|itagui|cartagena": "Colombia",
        # México
        "ciudad de mexico|cdmx|estado de mexico|edomex|hidalgo|guerrero|huehuetoca|tepeji|texontepec|tlaxcoapan|tultitlan|tula": "México",
        # El Salvador
        "san salvador": "El Salvador",
        # Argentina
        "la plata|buenos aires": "Argentina",
        # Brasil
        "salvador/ba|belo horizonte|miradouro|brasil": "Brasil",
        # Costa Rica
        r"\bcosta rica\b": "Costa Rica",
    }
    for pat, dest in city_to_country.items():
        if re.search(pat, a):
            return dest

    # 2) demónimos y variantes
    if re.search(r"colomb|cooomb", a):
        return "Colombia"
    if re.search(r"mexic|ciudad de mex|cdmx|edomex", a):
        return "México"
    if re.search(r"ecuad|ecuatorian", a):
        return "Ecuador"
    if re.search(r"\bperu?\b|^per$", a):
        return "Perú"
    if re.search(r"chile|chilena|chileno", a):
        return "Chile"
    if re.search(r"costa\s*rica|costarricen", a):
        return "Costa Rica"
    if re.search(r"dominican|dominican[oa]", a):
        return "República Dominicana"
    if re.search(r"brasil|brazil", a):
        return "Brasil"
    if re.search(r"argentin", a):
        return "Argentina"
    if re.search(r"boliv", a):
        return "Bolivia"
    if re.search(r"venez", a):
        return "Venezuela"
    if re.search(r"guatemal|guatemalte", a):
        return "Guatemala"
    if re.search(r"uruguay", a):
        return "Uruguay"
    if re.search(r"paraguay", a):
        return "Paraguay"
    if re.search(r"panam", a):
        return "Panamá"
    if re.search(r"hondur", a):
        return "Honduras"
    if re.search(r"nicarag", a):
        return "Nicaragua"
    if re.search(r"espan|espana", a):
        return "España"
    if re.search(r"ee\.?uu|estados unidos|united states|usa|ohio|atlanta|georgia", a):
        return "Estados Unidos"
    if re.search(r"el\s*salvador", a):
        return "El Salvador"

    # 3) respaldo por prefijo de 3 letras (solo letras)
    pref = re.sub(r"[^a-z]", "", a)[:3]
    pref_map = {
        "col": "Colombia", "mex": "México", "ecu": "Ecuador", "per": "Perú", "chi": "Chile",
        "cos": "Costa Rica", "bra": "Brasil", "arg": "Argentina", "ven": "Venezuela",
        "bol": "Bolivia", "gua": "Guatemala", "uru": "Uruguay", "par": "Paraguay",
        "pan": "Panamá", "dom": "República Dominicana", "sal": "El Salvador",
        "hon": "Honduras", "nic": "Nicaragua", "esp": "España", "est": "Estados Unidos", "usa": "Estados Unidos",
    }
    if pref in pref_map:
        return pref_map[pref]

    # si quedó algo tipo "Colombia" ya bien escrito
    return _to_title_es(s)


# crea una columna final canónica y úsala en TODOS los agregados/visuales por país
df["pais_final"] = df["pais"].apply(_canon_pais)

# 14) Modalidad por país (stacked)
# 14) Modalidad por país (stacked, usando pais_final y ordenado)
if df["pais_final"].notna().any():
    # totales por país para ordenar
    totales = (df.groupby("pais_final")["correo"]
                 .nunique()
                 .sort_values(ascending=False)
                 .reset_index(name="total"))
    # datos de la barra apilada
    mod_country = (df.groupby(["pais_final", "modalidad"])["correo"]
                     .nunique()
                     .reset_index(name="Participantes"))
    # unimos para poder ordenar por total desc
    mod_country = mod_country.merge(totales, on="pais_final", how="left") \
                             .sort_values(["total", "pais_final"], ascending=[False, True])

    # fijar el orden del eje X (de mayor a menor total)
    cat_order = totales["pais_final"].tolist()
    mod_country["pais_final"] = pd.Categorical(
        mod_country["pais_final"], categories=cat_order, ordered=True)

    fig14 = px.bar(
        mod_country,
        x="pais_final",
        y="Participantes",
        color="modalidad",
        barmode="stack",
        title="Modalidad declarada por país (ordenado por participantes únicos)"
    )
    fig14.update_layout(xaxis_title="País", legend_title="Modalidad")
    show(fig14, "Comparativa por país entre inscritos **Presencial** y **Virtual** (países normalizados con `_canon_pais`).")
else:
    st.info(
        "No hay países normalizados para mostrar la comparación de modalidad por país.")


# 15) Tasa de asistencia por país (normalizada y sobre personas únicas)
# --- Resumen por país (usar SIEMPRE pais_final y correos únicos) ---
st.subheader("🌎 Resumen por país (todos, de mayor a menor)")

resumen = (
    df.groupby("pais_final", dropna=True)
      .agg(
          participantes=("correo", "nunique"),        # personas únicas
          equipos=("equipo", lambda s: s.dropna().nunique()),
          presencial=("modalidad", lambda s: (s == "Presencial").sum()),
          virtual=("modalidad",   lambda s: (s == "Virtual").sum()),
          asistio=("attendance",  lambda s: (s == "Asistió").sum())
      )
      .reset_index()
      .rename(columns={"pais_final": "pais"})
)

# Mostrar tabla ordenada por participantes únicos
resumen = resumen.sort_values("participantes", ascending=False)
st.dataframe(resumen, use_container_width=True)
st.caption(f"Total países: {resumen.shape[0]}. Ordenado por **participantes únicos**.")

st.divider()

# === 15) Tasa de asistencia por país (consistente con 'resumen') ===
st.subheader("Tasa de asistencia por país (%)")

# Toggle opcional: tasa sobre todos o solo sobre inscritos Presencial
solo_presencial = st.toggle("Calcular tasa solo sobre inscritos Presencial", value=False)

if not resumen.empty:
    if solo_presencial:
        # Evita división por 0
        base = resumen.assign(den=resumen["presencial"].replace(0, np.nan))
        base["% Asistencia"] = (resumen["asistio"] / base["den"] * 100).round(1)
        nota = "Cálculo sobre **inscritos Presencial**: asistió / presencial."
    else:
        base = resumen.assign


# ────────────────────────────────────────────────────────────
# 📒 Informe Ejecutivo (Markdown)
# ────────────────────────────────────────────────────────────
try:
    # — KPIs globales (consistentes con el resto del app) —
    registros = len(df)
    personas_unicas = int(df["correo"].nunique()) if "correo" in df.columns else registros
    asistio_n = int((df["attendance"] == "Asistió").sum()) if "attendance" in df.columns else 0
    virtual_n = int((df["attendance"] == "Virtual").sum()) if "attendance" in df.columns else 0
    tasa_global = (asistio_n / personas_unicas * 100) if personas_unicas else 0
    age_med = (int(df["edad"].median()) if "edad" in df.columns and df["edad"].notna().any() else None)

    # — Totales por país ya normalizados (usa la tabla 'resumen' del paso 15) —
    if "resumen" not in locals():
        resumen = (
            df.groupby("pais_final", dropna=True)
              .agg(
                  participantes=("correo", "nunique"),
                  equipos=("equipo", lambda s: s.dropna().nunique()),
                  presencial=("modalidad", lambda s: (s == "Presencial").sum()),
                  virtual=("modalidad",   lambda s: (s == "Virtual").sum()),
                  asistio=("attendance",  lambda s: (s == "Asistió").sum())
              ).reset_index().rename(columns={"pais_final":"pais"})
        )
    resumen = resumen.sort_values("participantes", ascending=False)

    # Top países por volumen
    top_paises = resumen.head(5)[["pais","participantes"]]
    top_paises_md = " • ".join([f"**{r.pais}** ({int(r.participantes)})" for r in top_paises.itertuples(index=False)])

    # Distribución de modalidad
    mod_counts = (df["modalidad"].value_counts() if "modalidad" in df.columns else pd.Series(dtype=int))
    mod_md = " · ".join([f"{idx}: **{val}**" for idx, val in mod_counts.items()]) if not mod_counts.empty else "s/d"

    # Universidades top (si aplica)
    if "universidad" in df.columns and df["universidad"].notna().any():
        unis = df["universidad"].dropna().value_counts().head(5).index.tolist()
        unis_md = ", ".join([f"**{u}**" for u in unis])
    else:
        unis_md = "s/d"

    # Carreras top (agrupando variantes de Sistemas/Informática)
    def _norm_carrera_summary(x):
        s = _tidy(x)
        if not s: return np.nan
        s2 = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii").lower()
        s2 = re.sub(r"[^a-z0-9\s/+\-]", " ", s2)
        if re.search(r"(sistem|system|informatic|computaci)", s2):
            return "Ingeniería de Sistemas / Informática"
        return _tidy(s).title()
    if "carrera" in df.columns and df["carrera"].notna().any():
        car_top = df["carrera"].map(_norm_carrera_summary).value_counts().head(5)
        car_md = " · ".join([f"**{k}** ({v})" for k,v in car_top.items()])
    else:
        car_md = "s/d"

    # Equipos únicos (desde CSV; si integraste formularios, ya se reflejan en el análisis de equipos)
    equipos_unicos = int(df["equipo"].dropna().apply(_norm_team).nunique()) if "equipo" in df.columns else 0

    # Tasa de asistencia por país (top 5) usando el mismo denominador de 'resumen'
    att_top = (
        resumen.assign(rate=(resumen["asistio"]/resumen["participantes"]*100).round(1))
               .sort_values(["rate","participantes"], ascending=[False, False])
               .head(5)[["pais","rate"]]
    )
    att_pais_md = " • ".join([f"**{r.pais}** ({r.rate}%)" for r in att_top.itertuples(index=False)]) if not att_top.empty else "s/d"

    st.markdown(f"""
---
## 🧠 Informe ejecutivo — LACC 2025

**Cobertura del dataset**
- Registros procesados: **{registros:,}** · Personas únicas (correo): **{personas_unicas:,}** · Países normalizados: **{resumen.shape[0]}**
- Modalidad declarada → {mod_md}
- Asistencia verificada: **{asistio_n:,}** (presencia/online) vs **{virtual_n:,}** virtual/no-presencial ⇒ **{tasa_global:.1f}%** de asistencia global
- Edad mediana: {age_med if age_med is not None else "s/d"}

**Dónde está la audiencia**
- Top países por participantes: {top_paises_md if len(top_paises)>0 else "s/d"}
- Tasa de asistencia líder (Top 5): {att_pais_md}

**Talento y formación**
- Programas/Carreras más presentes: {car_md}
- Principales universidades/entidades: {unis_md}
- Equipos declarados (únicos): **{equipos_unicos}**  · *Para equipos multinacionales se usa país dominante por mayoría de integrantes.*

**Metodología de limpieza (resumen reproducible)**
1. Normalización robusta de **país** desde `pais`, `nacionalidad` y **lugar_nacimiento** (demónimos, ciudades→país y prefijo de 3 letras).
2. Estandarización de **ciudad** (tildes/variantes); `Desconocida` → **Medellín** por criterio operativo.
3. Corrección de **modalidad** y **attendance**; vacíos y “sin dato” se normalizan a *Virtual* para evitar subconteo.
4. **Deduplicación** por correo y claves alternativas (nombre, apellido, doc/teléfono).
5. Agrupación semántica de **carreras** (todas las variantes de *Sistemas/Informática/Computación* se consolidan).
6. Integración de **formularios Excel** de equipos cuando existen; reconciliación por persona y equipo.

**Cómo leer los gráficos**
- *Mapa por país:* paleta pastel por cuantiles; el país con mayor volumen aparece en el tono más fuerte.
- *Modalidad × Attendance:* identifica *no-show* en inscritos presenciales.
- *Sector ↔ País:* treemap y barras apiladas comparables entre países.
- *Equipos:* tamaño promedio por país y equipo líder (más integrantes).

**Limitaciones y sesgos**
- Si alguien usó varios correos, la asistencia puede subestimarse (denominador = **personas únicas por correo**).
- Filas sin sector/país quedan fuera de algunos gráficos; se reportan faltantes.
- En equipos mixtos por país, se asigna **país dominante por mayoría**.

**Siguientes pasos sugeridos**
- Revisar outliers de edad y dominios de correo genéricos.
- Completar sector para filas faltantes (mejora comparativas por país).
- Cruzar con métricas de asistencia a charlas/talleres para medir conversión.

**Posicionamiento LATAM**
- LACC 2025 se consolida como el **evento de ciberseguridad más grande de Latinoamérica**.
- Audiencia **YouTube**: **+{YT_TOTAL:,}** espectadores en el canal oficial, reforzando el carácter **representativo de LATAM** en ciberseguridad.

> **Conclusión:** La participación se concentra en varios países (con **Colombia** a la cabeza), fuerte preferencia declarada por **Presencial**, y una asistencia efectiva global del **{tasa_global:.1f}%** que sirve como línea base para optimizar convocatoria y logística en la próxima edición.
---
""")
except Exception as e:
    st.warning(f"⚠️ No se pudo generar el informe ejecutivo: {e}")
