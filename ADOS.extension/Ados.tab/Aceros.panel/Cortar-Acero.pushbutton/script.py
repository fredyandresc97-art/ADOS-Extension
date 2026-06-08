# -*- coding: utf-8 -*-
"""
Cortar Acero con Traslapo
--------------------------
Selecciona una barra, haz clic en el punto de corte, y el script la divide
en dos con traslapo automático (50 × diámetro).

Barra A (inicio → corte): queda fija.
Barra B (corte-traslapo → fin): se extiende hacia atrás.

Crea barras individuales para cada posición del grupo original,
preservando la posición exacta de cada una.

Elaborado por: Ing. Andres Angel
"""
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
import math
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInParameter, BuiltInCategory,
    Transaction, XYZ, Line, ElementId
)
from Autodesk.Revit.DB.Structure import (
    RebarBarType, RebarHookType, Rebar, RebarStyle, RebarHookOrientation
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from pyrevit import forms, script

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

def mm_a_pies(mm): return mm / 304.8
def pies_a_mm(p):  return p * 304.8

FACTOR_TRASLAPO = 50

class FiltroRebar(ISelectionFilter):
    def AllowElement(self, elem):
        return isinstance(elem, Rebar)
    def AllowReference(self, ref, point):
        return False

def proyectar_en_linea(punto, linea):
    p0 = linea.GetEndPoint(0)
    p1 = linea.GetEndPoint(1)
    v  = p1 - p0
    L2 = v.DotProduct(v)
    if L2 < 1e-12:
        return p0, 0.0
    w = punto - p0
    t = max(0.0, min(1.0, w.DotProduct(v) / L2))
    proy = XYZ(p0.X + v.X*t, p0.Y + v.Y*t, p0.Z + v.Z*t)
    return proy, t

def get_curva_rebar(rebar, bar_index=0):
    """Obtiene la curva central de la barra en la posición bar_index."""
    try:
        from Autodesk.Revit.DB.Structure import MultiplanarOption
        curvas = rebar.GetCenterlineCurves(
            False, True, False,
            MultiplanarOption.IncludeOnlyPlanarCurves, bar_index)
    except Exception:
        try:
            curvas = rebar.GetCenterlineCurves(False, True, False)
        except Exception:
            curvas = None
    if curvas and curvas.Count > 0:
        return curvas[0]
    return None

def get_todas_curvas(rebar):
    """
    Obtiene la curva central de CADA barra en el grupo.
    Si barPositionIndex no funciona (devuelve la misma curva),
    calcula las posiciones manualmente a partir de la primera curva,
    la dirección perpendicular y el espaciado.
    """
    n = 1
    try:
        n = rebar.NumberOfBarPositions
    except Exception:
        pass

    if n <= 1:
        c = get_curva_rebar(rebar, 0)
        return [c] if c else []

    # Intentar obtener curvas individuales por barPositionIndex
    curvas = []
    for i in range(n):
        c = get_curva_rebar(rebar, i)
        if c:
            curvas.append(c)

    if len(curvas) < 2:
        c = get_curva_rebar(rebar, 0)
        return [c] if c else []

    # Verificar si barPositionIndex realmente devuelve curvas diferentes
    p0_first = curvas[0].GetEndPoint(0)
    p0_second = curvas[1].GetEndPoint(0)
    dist = (p0_second - p0_first).GetLength()

    if dist > 1e-6:
        # barPositionIndex funciona: devuelve curvas en posiciones diferentes
        return curvas
    else:
        # barPositionIndex NO funciona: todas son la misma curva.
        # Calcular posiciones manualmente usando el espaciado y la dirección.
        c0 = curvas[0]
        p_start = c0.GetEndPoint(0)
        p_end   = c0.GetEndPoint(1)
        bar_dir = (p_end - p_start).Normalize()

        # Espaciado
        try:
            accessor = rebar.GetShapeDrivenAccessor()
            array_len = accessor.ArrayLength
            spacing = array_len / (n - 1) if n > 1 else 0.0
        except Exception:
            return [c0]

        # Dirección de distribución: perpendicular horizontal al eje de la barra
        z_global = XYZ(0, 0, 1)
        if abs(bar_dir.Z) > 0.9:
            perp = bar_dir.CrossProduct(XYZ(1, 0, 0))
        else:
            perp = bar_dir.CrossProduct(z_global)
        if perp.GetLength() < 1e-6:
            perp = XYZ(0, 1, 0)
        else:
            perp = perp.Normalize()

        # La curva devuelta podría ser la del centro del grupo, la primera, o la última.
        # Asumimos que es la primera barra (posición 0) y distribuimos hacia +perp.
        # Si queda mal, probamos con centrado.
        # Para determinar: usamos el BoundingBox del host.
        host_id = rebar.GetHostId()
        host = doc.GetElement(host_id)
        bb_host = host.get_BoundingBox(None) if host else None

        # Centro del host en la dirección perpendicular
        if bb_host:
            centro_host_perp = (XYZ(bb_host.Min.X, bb_host.Min.Y, bb_host.Min.Z) + 
                                XYZ(bb_host.Max.X, bb_host.Max.Y, bb_host.Max.Z))
            centro_host_perp = XYZ(centro_host_perp.X/2.0, centro_host_perp.Y/2.0, 
                                   centro_host_perp.Z/2.0)
            # Proyección del punto de la barra y del centro del host en dirección perp
            proy_bar = p_start.DotProduct(perp)
            proy_centro = centro_host_perp.DotProduct(perp)
            # Si la barra está en un extremo (lejos del centro), es la primera o última
            half_array = array_len / 2.0
            if abs(proy_bar - proy_centro) < spacing * 0.5:
                # La curva está cerca del centro → es la del medio, centrar distribución
                offset_inicio = -half_array
            elif proy_bar > proy_centro:
                # La barra está en el lado +perp → primera barra, distribuir hacia -perp
                perp = XYZ(-perp.X, -perp.Y, -perp.Z)
                offset_inicio = 0.0
            else:
                # La barra está en el lado -perp → primera barra, distribuir hacia +perp
                offset_inicio = 0.0
        else:
            # Sin host BB: asumir la curva está centrada
            offset_inicio = -array_len / 2.0

        resultado = []
        for i in range(n):
            d = offset_inicio + spacing * i
            p0 = XYZ(p_start.X + perp.X*d, p_start.Y + perp.Y*d, p_start.Z + perp.Z*d)
            p1 = XYZ(p_end.X + perp.X*d, p_end.Y + perp.Y*d, p_end.Z + perp.Z*d)
            resultado.append(Line.CreateBound(p0, p1))
        return resultado

def orientar_ganchos(rebar, ang_inicio, ang_final):
    for p in rebar.Parameters:
        try:
            nombre = p.Definition.Name
            if ang_inicio is not None and ('gancho al inicio' in nombre.lower() or 'gancho al inicio' in nombre) and not p.IsReadOnly:
                p.Set(ang_inicio)
            if ang_final is not None and ('gancho al final' in nombre.lower() or 'gancho al final' in nombre) and not p.IsReadOnly:
                p.Set(ang_final)
        except Exception:
            pass

# ─── Flujo principal ──────────────────────────────────────────────────────────
try:
    ref_rebar = uidoc.Selection.PickObject(
        ObjectType.Element, FiltroRebar(),
        'Selecciona la barra de refuerzo a cortar')
except Exception:
    script.exit()

rebar_orig = doc.GetElement(ref_rebar.ElementId)

# Tipo y diámetro
bar_type_id = rebar_orig.GetTypeId()
bar_type    = doc.GetElement(bar_type_id)
try:
    dp = bar_type.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER)
    diametro_ft = dp.AsDouble() if dp else mm_a_pies(12.0)
except Exception:
    diametro_ft = mm_a_pies(12.0)
diametro_mm = pies_a_mm(diametro_ft)

# Ganchos
hook_start = None
hook_end   = None
try:
    p_hk = rebar_orig.get_Parameter(BuiltInParameter.REBAR_ELEM_HOOK_START_TYPE)
    if p_hk:
        hk_id = p_hk.AsElementId()
        if hk_id.IntegerValue > 0:
            hook_start = doc.GetElement(hk_id)
except Exception:
    pass
try:
    p_hk = rebar_orig.get_Parameter(BuiltInParameter.REBAR_ELEM_HOOK_END_TYPE)
    if p_hk:
        hk_id = p_hk.AsElementId()
        if hk_id.IntegerValue > 0:
            hook_end = doc.GetElement(hk_id)
except Exception:
    pass

# Rotación de ganchos
rot_inicio = None
rot_final  = None
for p in rebar_orig.Parameters:
    try:
        nombre = p.Definition.Name
        if ('gancho al inicio' in nombre.lower()) and not p.IsReadOnly:
            rot_inicio = p.AsDouble()
        if ('gancho al final' in nombre.lower()) and not p.IsReadOnly:
            rot_final = p.AsDouble()
    except Exception:
        pass

# Host
host_id = rebar_orig.GetHostId()
host    = doc.GetElement(host_id)

# Curva de referencia (para proyectar el clic)
curva_ref = get_curva_rebar(rebar_orig, 0)
if curva_ref is None:
    forms.alert('No se pudo leer la geometria de la barra.', exitscript=True)

p_start = curva_ref.GetEndPoint(0)
p_end   = curva_ref.GetEndPoint(1)
longitud_total_mm = pies_a_mm((p_end - p_start).GetLength())

# Traslapo
traslapo_mm = diametro_mm * FACTOR_TRASLAPO
traslapo_ft = mm_a_pies(traslapo_mm)

# Todas las curvas del grupo (una por barra)
todas_curvas = get_todas_curvas(rebar_orig)
num_barras = len(todas_curvas)

# Punto de corte
try:
    punto_clic = uidoc.Selection.PickPoint(
        'Clic en el punto de corte (traslapo: {:.0f} mm = {:.0f} cm)'.format(
            traslapo_mm, traslapo_mm/10.0))
except Exception:
    script.exit()

punto_corte, t_corte = proyectar_en_linea(punto_clic, curva_ref)
dist_corte_mm = pies_a_mm((punto_corte - p_start).GetLength())

if dist_corte_mm < traslapo_mm:
    forms.alert('Punto de corte muy cerca del inicio ({:.0f} mm).\nTraslapo necesita {:.0f} mm.'.format(
        dist_corte_mm, traslapo_mm), exitscript=True)
if (longitud_total_mm - dist_corte_mm) < traslapo_mm:
    forms.alert('Punto de corte muy cerca del fin ({:.0f} mm).\nTraslapo necesita {:.0f} mm.'.format(
        longitud_total_mm - dist_corte_mm, traslapo_mm), exitscript=True)

# Dirección de la barra
vec_dir = (p_end - p_start).Normalize()

# Confirmar
long_a_mm = dist_corte_mm
long_b_mm = longitud_total_mm - dist_corte_mm + traslapo_mm

confirmar = forms.alert(
    'Diametro: {:.0f} mm\n'
    'Traslapo (50xO): {:.0f} mm = {:.0f} cm\n'
    'Barras en el grupo: {}\n\n'
    'Barra A: {:.0f} mm\n'
    'Barra B: {:.0f} mm\n\n'
    'Continuar?'.format(
        diametro_mm, traslapo_mm, traslapo_mm/10.0,
        num_barras, long_a_mm, long_b_mm),
    yes=True, no=True)

if not confirmar:
    script.exit()

# ─── Transacción ──────────────────────────────────────────────────────────────
with Transaction(doc, 'Cortar acero con traslapo') as t:
    t.Start()

    for curva_i in todas_curvas:
        pi_start = curva_i.GetEndPoint(0)
        pi_end   = curva_i.GetEndPoint(1)

        # Punto de corte para ESTA barra (misma posición relativa t_corte)
        corte_i = XYZ(
            pi_start.X + (pi_end.X - pi_start.X) * t_corte,
            pi_start.Y + (pi_end.Y - pi_start.Y) * t_corte,
            pi_start.Z + (pi_end.Z - pi_start.Z) * t_corte)

        # Barra A: inicio → corte
        curva_a = Line.CreateBound(pi_start, corte_i)

        # Barra B: (corte - traslapo) → fin
        p_b_start = XYZ(
            corte_i.X - vec_dir.X * traslapo_ft,
            corte_i.Y - vec_dir.Y * traslapo_ft,
            corte_i.Z - vec_dir.Z * traslapo_ft)
        curva_b = Line.CreateBound(p_b_start, pi_end)

        # Crear Barra A (mantiene gancho inicio, sin gancho final)
        rebar_a = Rebar.CreateFromCurves(
            doc, RebarStyle.Standard, bar_type,
            hook_start, None, host,
            XYZ(0, 0, 1),
            [curva_a],
            RebarHookOrientation.Right, RebarHookOrientation.Right,
            True, True)
        if rot_inicio is not None:
            orientar_ganchos(rebar_a, rot_inicio, None)

        # Crear Barra B (sin gancho inicio, mantiene gancho final)
        rebar_b = Rebar.CreateFromCurves(
            doc, RebarStyle.Standard, bar_type,
            None, hook_end, host,
            XYZ(0, 0, 1),
            [curva_b],
            RebarHookOrientation.Right, RebarHookOrientation.Right,
            True, True)
        if rot_final is not None:
            orientar_ganchos(rebar_b, None, rot_final)

    # Eliminar la barra original
    doc.Delete(rebar_orig.Id)

    t.Commit()

forms.alert(
    'Corte realizado.\n\n'
    '{} barras cortadas con {:.0f} cm de traslapo.'.format(
        num_barras, traslapo_mm/10.0))