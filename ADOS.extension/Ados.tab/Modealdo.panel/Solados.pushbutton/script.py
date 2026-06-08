# -*- coding: utf-8 -*-
"""
Solados bajo Zapatas y Vigas
------------------------------
Crea un piso (Floor) de categoría SUELO debajo de:
  - Zapatas (OST_StructuralFoundation): desfase en las 4 direcciones.
  - Vigas   (OST_StructuralFraming):    desfase SOLO transversal (ancho + desfase
            a cada lado). La longitud va desde la cara interna de columna a cara
            interna de columna (igual que la lógica de estribos), SIN desfase
            longitudinal, para que el solado no entre dentro de las columnas.

Elaborado por: Ing. Andrés Angel  —  Ados Software
"""
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xml')

import math
import System
import System.Windows as SW
import System.Windows.Controls as SWC
from System.Windows.Markup import XamlReader
from System.Xml import XmlReader
from System.IO import StringReader

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    Transaction, XYZ, Line, CurveLoop, FloorType, Level,
    JoinGeometryUtils
)
from Autodesk.Revit.DB import Floor as RvtFloor
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# ──────────────────────────────────────────────────────────────────────────────
# Conversiones
# ──────────────────────────────────────────────────────────────────────────────
def cm_a_ft(cm):  return cm / 30.48
def ft_a_cm(ft):  return ft * 30.48
def mm_a_ft(mm):  return mm / 304.8
def ft_a_mm(ft):  return ft * 304.8


# ──────────────────────────────────────────────────────────────────────────────
# Filtro de selección (zapatas + vigas)
# ──────────────────────────────────────────────────────────────────────────────
class FiltroZapatasVigas(ISelectionFilter):
    def AllowElement(self, elem):
        if elem is None or elem.Category is None:
            return False
        cat_id = elem.Category.Id.IntegerValue
        return cat_id in (
            int(BuiltInCategory.OST_StructuralFoundation),
            int(BuiltInCategory.OST_StructuralFraming),
        )
    def AllowReference(self, ref, point):
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Tipos de suelo disponibles en el documento
# ──────────────────────────────────────────────────────────────────────────────
floor_types_col = (FilteredElementCollector(doc)
                   .OfClass(FloorType)
                   .ToElements())

tipos_suelo = {}
for ft in floor_types_col:
    p = ft.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
    if p:
        nombre = p.AsString()
        if nombre:
            tipos_suelo[nombre] = ft

if not tipos_suelo:
    SW.MessageBox.Show(
        'No se encontraron tipos de piso en el documento.',
        'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

nombres_suelo = sorted(tipos_suelo.keys())
DEFAULT_SOLADO = 'EST_Concreto_21MPa_7cm'
idx_default = (nombres_suelo.index(DEFAULT_SOLADO)
               if DEFAULT_SOLADO in nombres_suelo else 0)


# ──────────────────────────────────────────────────────────────────────────────
# INTERFAZ WPF
# ──────────────────────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Solados bajo Zapatas y Vigas"
    Width="430" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">

  <StackPanel Margin="14">

    <!-- Encabezado -->
    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Solados bajo Zapatas y Vigas"
                   FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Crea solados de suelo bajo cimentaciones y vigas  —  Ados Software"
                   FontSize="10" Foreground="#222" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <!-- Tipo de Solado -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="TIPO DE SOLADO" FontSize="10" FontWeight="Bold"
                   Foreground="#555" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbSolado" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <!-- Desfase -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="DESFASE" FontSize="10" FontWeight="Bold"
                   Foreground="#555" Margin="0,0,0,8"/>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="65"/>
          </Grid.ColumnDefinitions>
          <TextBlock Text="Desfase hacia afuera (cm):"
                     VerticalAlignment="Center" Grid.Column="0"/>
          <TextBox x:Name="txtDesfase" Text="5" Grid.Column="1"
                   Padding="4,3" BorderBrush="#BFBFBF" BorderThickness="1"
                   HorizontalAlignment="Stretch"/>
        </Grid>
        <Border Background="#FFF8E7" CornerRadius="4" Padding="8,6" Margin="0,8,0,0"
                BorderBrush="#F9B233" BorderThickness="1">
          <StackPanel>
            <TextBlock FontSize="10" Foreground="#555" TextWrapping="Wrap"
                       Text="Zapatas: desfase en las 4 direcciones."/>
            <TextBlock FontSize="10" Foreground="#555" TextWrapping="Wrap" Margin="0,2,0,0"
                       Text="Vigas: desfase solo transversal (ancho + desfase a cada lado). La longitud va de cara interna de columna a cara interna de columna."/>
          </StackPanel>
        </Border>
      </StackPanel>
    </Border>

    <!-- Selección -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="ELEMENTOS" FontSize="10" FontWeight="Bold"
                   Foreground="#555" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar Zapatas y/o Vigas en Revit"
                Height="32" Cursor="Hand"
                Background="#FDE3B5" Foreground="#000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador"
                   Text="Ningún elemento seleccionado."
                   Foreground="#999" FontSize="11"
                   HorizontalAlignment="Center" Margin="0,6,0,0"/>
      </StackPanel>
    </Border>

    <!-- Botones -->
    <Grid Margin="0,4,0,0">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="10"/>
        <ColumnDefinition Width="2*"/>
      </Grid.ColumnDefinitions>
      <Button x:Name="btnCancelar" Grid.Column="0" Content="Cancelar"
              Height="34" Cursor="Hand"
              Background="#EEEEEE" Foreground="#555"
              BorderBrush="#BFBFBF" BorderThickness="1"/>
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear Solados"
              Height="34" Cursor="Hand"
              Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
</Window>
"""


class FormSolados(object):
    def __init__(self):
        self.resultado   = None
        self.elem_ids    = []
        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.cbSolado    = self.win.FindName('cbSolado')
        self.txtDesfase  = self.win.FindName('txtDesfase')
        self.lblContador = self.win.FindName('lblContador')

        for n in nombres_suelo:
            self.cbSolado.Items.Add(n)
        self.cbSolado.SelectedIndex = idx_default

        self.win.FindName('btnSeleccionar').Click += self.OnSeleccionar
        self.win.FindName('btnCancelar').Click    += self.OnCancelar
        self.win.FindName('btnAceptar').Click     += self.OnAceptar

    def OnSeleccionar(self, sender, e):
        self.win.Hide()
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element,
                FiltroZapatasVigas(),
                'Selecciona zapatas y/o vigas, luego presiona ENTER')

            id_found   = int(BuiltInCategory.OST_StructuralFoundation)
            id_framing = int(BuiltInCategory.OST_StructuralFraming)
            zapatas = vigas = 0
            self.elem_ids = []

            for ref in refs:
                elem   = doc.GetElement(ref.ElementId)
                cat_id = elem.Category.Id.IntegerValue
                self.elem_ids.append(ref.ElementId)
                if cat_id == id_found:   zapatas += 1
                elif cat_id == id_framing: vigas  += 1

            self.lblContador.Text = '{} zapata(s)  y  {} viga(s) seleccionadas.'.format(
                zapatas, vigas)
        except Exception:
            self.lblContador.Text = 'Seleccion cancelada.'
        self.win.ShowDialog()

    def OnAceptar(self, sender, e):
        if not self.elem_ids:
            SW.MessageBox.Show('No has seleccionado ningún elemento.',
                'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        try:
            desfase = float(self.txtDesfase.Text.replace(',', '.'))
        except ValueError:
            SW.MessageBox.Show('El desfase debe ser un número.',
                'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = {
            'desfase_cm':  desfase,
            'tipo_nombre': self.cbSolado.SelectedItem,
        }
        self.win.Close()

    def OnCancelar(self, sender, e):
        self.resultado = None
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.resultado


# ──────────────────────────────────────────────────────────────────────────────
# Mostrar ventana
# ──────────────────────────────────────────────────────────────────────────────
form = FormSolados()
res  = form.show()
if res is None:
    import sys; sys.exit()

desfase_ft     = cm_a_ft(res['desfase_cm'])
floor_type_obj = tipos_suelo[res['tipo_nombre']]
floor_type_id  = floor_type_obj.Id
elem_ids       = form.elem_ids


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades de geometría
# ──────────────────────────────────────────────────────────────────────────────

def nivel_mas_cercano(z_ft):
    """Level más cercano por debajo de z_ft."""
    niveles = (FilteredElementCollector(doc).OfClass(Level).ToElements())
    candidatos = [lv for lv in niveles if lv.Elevation <= z_ft + 0.001]
    if not candidatos:
        candidatos = list(niveles)
    return min(candidatos, key=lambda lv: abs(lv.Elevation - z_ft))


def crear_floor_no_estructural(curve_loop, z_ft, tipo_id):
    """
    Crea un Floor (suelo, NO estructural) con el CurveLoop dado.
    Usa Floor.Create() de Revit 2024 con isStructural=False.
    """
    nivel = nivel_mas_cercano(z_ft)
    loops = System.Collections.Generic.List[CurveLoop]()
    loops.Add(curve_loop)

    # isStructural = False  →  categoría Floors (suelo), no cimentación
    piso = RvtFloor.Create(doc, loops, tipo_id, nivel.Id, False, None, 0.0)

    # Ajustar altura exacta respecto al nivel
    offset_vs_nivel = z_ft - nivel.Elevation
    param = piso.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
    if param and not param.IsReadOnly:
        param.Set(offset_vs_nivel)
    return piso


def loop_desde_4_puntos(a, b, c, d):
    """CurveLoop cerrado a partir de 4 esquinas (sentido horario o antihorario)."""
    loop = CurveLoop()
    loop.Append(Line.CreateBound(a, b))
    loop.Append(Line.CreateBound(b, c))
    loop.Append(Line.CreateBound(c, d))
    loop.Append(Line.CreateBound(d, a))
    return loop


# ──────────────────────────────────────────────────────────────────────────────
# Detección de columna en extremo de viga  (mismo algoritmo que estribos)
# ──────────────────────────────────────────────────────────────────────────────

def cara_interna_columna(doc, p_extremo, eje_hacia_interior, longitud_viga_ft):
    """
    Busca la columna estructural cuyo BoundingBox contenga p_extremo.
    Devuelve la distancia (en pies) desde p_extremo hasta la cara interna
    de esa columna (medida a lo largo de eje_hacia_interior).
    Si no hay columna, devuelve 0.

    p_extremo          : XYZ del extremo de la LocationCurve de la viga
    eje_hacia_interior : vector unitario que apunta al INTERIOR de la viga
    longitud_viga_ft   : longitud total de la viga (para no pasarse de la mitad)
    """
    columnas = (FilteredElementCollector(doc)
                .OfCategory(BuiltInCategory.OST_StructuralColumns)
                .WhereElementIsNotElementType()
                .ToElements())

    tol = mm_a_ft(50.0)   # 5 cm de tolerancia

    col_bb = None
    for col in columnas:
        bb = col.get_BoundingBox(None)
        if bb is None:
            continue
        if (bb.Min.X - tol <= p_extremo.X <= bb.Max.X + tol and
            bb.Min.Y - tol <= p_extremo.Y <= bb.Max.Y + tol and
            bb.Min.Z - tol <= p_extremo.Z <= bb.Max.Z + tol):
            col_bb = bb
            break

    if col_bb is None:
        return 0.0

    # Proyectar las 8 esquinas del BB de la columna sobre el eje longitudinal
    esquinas = [
        XYZ(col_bb.Min.X, col_bb.Min.Y, col_bb.Min.Z),
        XYZ(col_bb.Max.X, col_bb.Min.Y, col_bb.Min.Z),
        XYZ(col_bb.Min.X, col_bb.Max.Y, col_bb.Min.Z),
        XYZ(col_bb.Max.X, col_bb.Max.Y, col_bb.Min.Z),
        XYZ(col_bb.Min.X, col_bb.Min.Y, col_bb.Max.Z),
        XYZ(col_bb.Max.X, col_bb.Min.Y, col_bb.Max.Z),
        XYZ(col_bb.Min.X, col_bb.Max.Y, col_bb.Max.Z),
        XYZ(col_bb.Max.X, col_bb.Max.Y, col_bb.Max.Z),
    ]
    proyecciones = [(esq - p_extremo).DotProduct(eje_hacia_interior)
                    for esq in esquinas]

    max_proy = max(proyecciones)
    if max_proy <= 0:
        return 0.0

    # Limitar a la mitad de la viga para no solapar
    return min(max_proy, longitud_viga_ft / 2.0)


# ──────────────────────────────────────────────────────────────────────────────
# Sección de la viga
# ──────────────────────────────────────────────────────────────────────────────

def get_seccion_viga(viga):
    """Devuelve (ancho_ft, alto_ft) de la sección."""
    sym = viga.Symbol

    bip_w = BuiltInParameter.STRUCTURAL_SECTION_COMMON_WIDTH
    bip_h = BuiltInParameter.STRUCTURAL_SECTION_COMMON_HEIGHT
    pw = sym.get_Parameter(bip_w)
    ph = sym.get_Parameter(bip_h)
    if pw and ph and pw.AsDouble() > 0 and ph.AsDouble() > 0:
        return pw.AsDouble(), ph.AsDouble()

    ancho = alto = None
    for p in sym.Parameters:
        try:
            nom = p.Definition.Name.lower()
            val = p.AsDouble()
            if val <= 0: continue
            if nom in ('b', 'ancho', 'width', 'base'):  ancho = val
            elif nom in ('h', 'alto', 'height', 'peralte', 'd'): alto = val
        except Exception:
            pass

    if ancho is None or alto is None:
        bb = viga.get_BoundingBox(None)
        if bb:
            dz = bb.Max.Z - bb.Min.Z
            dx = bb.Max.X - bb.Min.X
            dy = bb.Max.Y - bb.Min.Y
            if alto  is None: alto  = dz
            if ancho is None: ancho = min(dx, dy)

    return (ancho or cm_a_ft(30)), (alto or cm_a_ft(50))


# ──────────────────────────────────────────────────────────────────────────────
# Procesamiento de ZAPATA
# ──────────────────────────────────────────────────────────────────────────────

def procesar_zapata(elem):
    """
    CurveLoop del solado bajo una zapata.
    Desfase en las 4 direcciones a partir del BoundingBox.
    """
    bb = elem.get_BoundingBox(None)
    if bb is None:
        return None

    z  = bb.Min.Z   # cara inferior de la zapata
    cx = (bb.Min.X + bb.Max.X) / 2.0
    cy = (bb.Min.Y + bb.Max.Y) / 2.0
    dx = (bb.Max.X - bb.Min.X) / 2.0 + desfase_ft
    dy = (bb.Max.Y - bb.Min.Y) / 2.0 + desfase_ft

    p1 = XYZ(cx - dx, cy - dy, z)
    p2 = XYZ(cx + dx, cy - dy, z)
    p3 = XYZ(cx + dx, cy + dy, z)
    p4 = XYZ(cx - dx, cy + dy, z)
    return loop_desde_4_puntos(p1, p2, p3, p4), z


# ──────────────────────────────────────────────────────────────────────────────
# Procesamiento de VIGA
# ──────────────────────────────────────────────────────────────────────────────

def procesar_viga(viga):
    """
    CurveLoop del solado bajo una viga.

    Longitud : de cara interna de columna inicial a cara interna de columna final
               (sin desfase longitudinal extra → el solado no entra en columnas).
    Ancho    : ancho de la viga + desfase a cada lado (desfase_ft × 2 en total).
    Z        : cara inferior de la viga (BoundingBox.Min.Z).
    """
    loc   = viga.Location
    curva = loc.Curve
    p0    = curva.GetEndPoint(0)
    p1    = curva.GetEndPoint(1)

    vec_long = p1 - p0
    long_ft  = vec_long.GetLength()
    if long_ft < 0.01:
        return None

    eje_long = vec_long.Normalize()
    eje_long_neg = XYZ(-eje_long.X, -eje_long.Y, -eje_long.Z)

    # Vector perpendicular horizontal (ancho de la viga)
    z_global = XYZ(0, 0, 1)
    if abs(eje_long.DotProduct(z_global)) > 0.99:
        perp = XYZ(1, 0, 0)
    else:
        perp = eje_long.CrossProduct(z_global).Normalize()

    ancho_ft, alto_ft = get_seccion_viga(viga)

    # Z inferior real desde BoundingBox
    bb = viga.get_BoundingBox(None)
    z_bot = bb.Min.Z if bb else p0.Z

    # ── Detectar penetración de columnas en cada extremo ─────────────────────
    # p0 y p1 son los puntos de la LocationCurve (eje neutro de la viga).
    # cara_interna_columna devuelve cuántos pies avanzar DESDE el extremo
    # hacia el interior para salir de la columna.
    pen_ini_ft = cara_interna_columna(doc, p0,  eje_long,     long_ft)
    pen_fin_ft = cara_interna_columna(doc, p1,  eje_long_neg, long_ft)

    # Puntos de inicio y fin del solado (sobre el eje neutro, en z_bot)
    p_inicio = XYZ(p0.X + eje_long.X * pen_ini_ft,
                   p0.Y + eje_long.Y * pen_ini_ft,
                   z_bot)
    p_fin    = XYZ(p1.X + eje_long_neg.X * pen_fin_ft,
                   p1.Y + eje_long_neg.Y * pen_fin_ft,
                   z_bot)

    long_libre = (p_fin - p_inicio).GetLength()
    if long_libre < 0.01:
        return None

    # Semi-ancho del solado = mitad del ancho de viga + desfase transversal
    semi_ancho = ancho_ft / 2.0 + desfase_ft

    # 4 esquinas del rectángulo
    a = XYZ(p_inicio.X - perp.X * semi_ancho, p_inicio.Y - perp.Y * semi_ancho, z_bot)
    b = XYZ(p_fin.X    - perp.X * semi_ancho, p_fin.Y    - perp.Y * semi_ancho, z_bot)
    c = XYZ(p_fin.X    + perp.X * semi_ancho, p_fin.Y    + perp.Y * semi_ancho, z_bot)
    d = XYZ(p_inicio.X + perp.X * semi_ancho, p_inicio.Y + perp.Y * semi_ancho, z_bot)

    return loop_desde_4_puntos(a, b, c, d), z_bot


# ──────────────────────────────────────────────────────────────────────────────
# Transacción
# ──────────────────────────────────────────────────────────────────────────────
id_found   = int(BuiltInCategory.OST_StructuralFoundation)
id_framing = int(BuiltInCategory.OST_StructuralFraming)

creados  = 0
errores  = 0
detalle  = []
pisos_creados = []   # lista de Floor para luego aplicar Join

# ── Transacción 1: crear todos los Floors ────────────────────────────────────
with Transaction(doc, 'Solados bajo Zapatas y Vigas') as t:
    t.Start()

    for eid in elem_ids:
        elem = doc.GetElement(eid)
        if elem is None:
            continue
        cat_id = elem.Category.Id.IntegerValue

        try:
            if cat_id == id_found:
                res_geo = procesar_zapata(elem)
            elif cat_id == id_framing:
                res_geo = procesar_viga(elem)
            else:
                continue

            if res_geo is None:
                detalle.append('ID {}: sin geometria valida.'.format(eid.IntegerValue))
                errores += 1
                continue

            loop, z_ft = res_geo
            piso = crear_floor_no_estructural(loop, z_ft, floor_type_id)
            pisos_creados.append(piso)
            creados += 1

        except Exception as ex:
            detalle.append('ID {}: {}'.format(eid.IntegerValue, str(ex)))
            errores += 1

    t.Commit()

# ── Transacción 2: unir Floors que se solapan (Join Geometry) ────────────────
# Revit requiere que los elementos existan en el documento antes de poder
# unirlos, por eso se hace en una segunda transacción independiente.
unidos = 0
if len(pisos_creados) > 1:
    with Transaction(doc, 'Unir Solados solapados') as t2:
        t2.Start()
        n = len(pisos_creados)
        for i in range(n):
            for j in range(i + 1, n):
                p1 = pisos_creados[i]
                p2 = pisos_creados[j]
                try:
                    # Solo unir si sus BoundingBoxes se tocan o solapan
                    bb1 = p1.get_BoundingBox(None)
                    bb2 = p2.get_BoundingBox(None)
                    if bb1 is None or bb2 is None:
                        continue
                    # Comprobar solapamiento en X, Y (Z es casi igual para
                    # solados del mismo nivel, no es necesario comprobarlo)
                    tol = mm_a_ft(1.0)   # 1 mm de tolerancia
                    solapa = (bb1.Min.X - tol < bb2.Max.X and
                              bb1.Max.X + tol > bb2.Min.X and
                              bb1.Min.Y - tol < bb2.Max.Y and
                              bb1.Max.Y + tol > bb2.Min.Y)
                    if not solapa:
                        continue
                    # Verificar que no estén ya unidos
                    if JoinGeometryUtils.AreElementsJoined(doc, p1, p2):
                        continue
                    JoinGeometryUtils.JoinGeometry(doc, p1, p2)
                    unidos += 1
                except Exception:
                    pass   # si no se pueden unir (geometría no coincidente) se ignora
        t2.Commit()

# ── Resumen ───────────────────────────────────────────────────────────────────
msg = 'Solados creados : {}\nUniones aplicadas: {}\nErrores         : {}'.format(
    creados, unidos, errores)
if detalle:
    msg += '\n\nDetalle:\n' + '\n'.join(detalle[:10])
    if len(detalle) > 10:
        msg += '\n... y {} mas.'.format(len(detalle) - 10)

SW.MessageBox.Show(msg, 'Resultado — Solados',
                   SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)