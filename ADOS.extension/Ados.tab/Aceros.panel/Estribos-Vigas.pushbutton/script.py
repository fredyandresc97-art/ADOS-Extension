# -*- coding: utf-8 -*-
"""
Flejes (Estribos) en Vigas — E1-E2-E1
--------------------------------------
Igual que columnas pero el eje de distribución es la LocationCurve de la viga.
Funciona con vigas en cualquier dirección del espacio (no alineadas a X/Y/Z).

Interfaz WPF — Ing. Andres Angel
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
import System.Windows.Media as SWM
from System.Windows.Markup import XamlReader
from System.Xml import XmlReader
from System.IO import StringReader

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInParameter, BuiltInCategory,
    Transaction, XYZ, Line, Options
)
from Autodesk.Revit.DB.Structure import (
    RebarBarType, RebarHookType, Rebar, RebarStyle, RebarHookOrientation
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

def mm_a_pies(mm): return mm / 304.8
def pies_a_mm(p):  return p * 304.8

# ─── Filtro: solo marcos estructurales (vigas) ────────────────────────────────
class FiltroVigas(ISelectionFilter):
    def AllowElement(self, elem):
        return (elem.Category is not None and
                elem.Category.Id.IntegerValue ==
                int(BuiltInCategory.OST_StructuralFraming))
    def AllowReference(self, ref, point): return False

# ─── Geometría de la viga ─────────────────────────────────────────────────────
def get_info_viga(viga):
    """
    Devuelve:
        p_ini (XYZ)  – punto inicial de la viga en pies (eje longitudinal)
        eje_long     – vector unitario a lo largo de la viga
        eje_ancho    – vector unitario transversal horizontal (ancho)
        eje_alto     – vector unitario vertical (peralte)
        ancho_mm     – ancho de la sección
        alto_mm      – alto (peralte) de la sección
        longitud_mm  – longitud total de la viga
    """
    # Eje longitudinal desde la LocationCurve
    loc = viga.Location
    curva = loc.Curve
    p_ini = curva.GetEndPoint(0)
    p_fin = curva.GetEndPoint(1)

    vec_long = p_fin - p_ini
    longitud_mm = pies_a_mm(vec_long.GetLength())
    eje_long = vec_long.Normalize()

    # Eje vertical global de referencia
    z_global = XYZ(0, 0, 1)

    # Eje transversal horizontal (ancho) = perpendicular al eje long y a Z
    # Si la viga es vertical (caso raro), usamos X global como fallback
    if abs(eje_long.DotProduct(z_global)) > 0.99:
        eje_ancho = XYZ(1, 0, 0)
    else:
        eje_ancho = eje_long.CrossProduct(z_global).Normalize()

    # Eje del peralte (alto) = perpendicular al eje long y al ancho
    eje_alto = eje_ancho.CrossProduct(eje_long).Normalize()

    # Dimensiones de la sección
    ancho_mm, alto_mm = get_seccion_viga(viga)

    # Corrección por desplazamiento vertical (Z offset / "Valor de desfase Z").
    # BoundingBox.Max.Z NO es confiable (incluye línea analítica).
    # BoundingBox.Min.Z SÍ refleja la cara inferior real de la viga.
    # Cara superior real = Min.Z + altura de la sección.
    bb = viga.get_BoundingBox(None)
    if bb:
        alto_ft = mm_a_pies(alto_mm)
        z_real_top = bb.Min.Z + alto_ft
        p_ini = XYZ(p_ini.X, p_ini.Y, z_real_top)

    # p_ini.Z ya es la cara superior REAL de la viga (corregida por BoundingBox).
    # Siempre bajamos alto/2 para llegar al centro de la sección.
    desplaz_vert_mm = -alto_mm / 2.0

    return (p_ini, eje_long, eje_ancho, eje_alto,
            ancho_mm, alto_mm, longitud_mm, desplaz_vert_mm)

def get_seccion_viga(viga):
    """Lee ancho y alto de la sección de la viga."""
    # Intentar parámetros comunes de sección
    p_ancho = viga.Symbol.get_Parameter(BuiltInParameter.STRUCTURAL_SECTION_COMMON_WIDTH) \
              if viga.Symbol.get_Parameter(BuiltInParameter.STRUCTURAL_SECTION_COMMON_WIDTH) else None
    p_alto  = viga.Symbol.get_Parameter(BuiltInParameter.STRUCTURAL_SECTION_COMMON_HEIGHT) \
              if viga.Symbol.get_Parameter(BuiltInParameter.STRUCTURAL_SECTION_COMMON_HEIGHT) else None

    if p_ancho and p_alto and p_ancho.AsDouble() > 0 and p_alto.AsDouble() > 0:
        return pies_a_mm(p_ancho.AsDouble()), pies_a_mm(p_alto.AsDouble())

    # Fallback: buscar parámetros por nombre típico (b, h, Ancho, Alto)
    ancho_mm = None; alto_mm = None
    for p in viga.Symbol.Parameters:
        try:
            nombre = p.Definition.Name.lower()
            val = pies_a_mm(p.AsDouble())
            if val <= 0: continue
            if nombre in ('b', 'ancho', 'width', 'base'):
                ancho_mm = val
            elif nombre in ('h', 'alto', 'height', 'peralte', 'd'):
                alto_mm = val
        except Exception:
            pass

    # Fallback final: BoundingBox
    if ancho_mm is None or alto_mm is None:
        bb = viga.get_BoundingBox(None)
        dx = pies_a_mm(bb.Max.X - bb.Min.X)
        dy = pies_a_mm(bb.Max.Y - bb.Min.Y)
        dz = pies_a_mm(bb.Max.Z - bb.Min.Z)
        # El alto suele ser dz; el ancho el menor de dx,dy
        if alto_mm is None:  alto_mm  = dz
        if ancho_mm is None: ancho_mm = min(dx, dy)

    return ancho_mm, alto_mm

# ─── Crear grupo de estribos en una viga ──────────────────────────────────────
def crear_grupo_estribos(doc, viga, centro_pies,
                         ancho_mm, alto_mm, rec_mm,
                         bar_type, hook_type,
                         eje_long, eje_ancho, eje_alto,
                         num_barras, espaciado_mm, hacia_adelante=True):
    """
    Crea un estribo cerrado en la sección de la viga en 'centro_pies'
    y lo distribuye a lo largo del eje longitudinal con SetLayoutAsNumberWithSpacing.

    El estribo se dibuja en el plano (eje_ancho, eje_alto), perpendicular
    al eje longitudinal de la viga. Funciona en cualquier orientación.
    """
    semi_a = mm_a_pies((ancho_mm - 2.0 * rec_mm) / 2.0)
    semi_h = mm_a_pies((alto_mm  - 2.0 * rec_mm) / 2.0)
    c = centro_pies

    # 4 vértices del estribo en el plano transversal (ancho x alto)
    p0 = XYZ(c.X - eje_ancho.X*semi_a - eje_alto.X*semi_h,
             c.Y - eje_ancho.Y*semi_a - eje_alto.Y*semi_h,
             c.Z - eje_ancho.Z*semi_a - eje_alto.Z*semi_h)
    p1 = XYZ(c.X + eje_ancho.X*semi_a - eje_alto.X*semi_h,
             c.Y + eje_ancho.Y*semi_a - eje_alto.Y*semi_h,
             c.Z + eje_ancho.Z*semi_a - eje_alto.Z*semi_h)
    p2 = XYZ(c.X + eje_ancho.X*semi_a + eje_alto.X*semi_h,
             c.Y + eje_ancho.Y*semi_a + eje_alto.Y*semi_h,
             c.Z + eje_ancho.Z*semi_a + eje_alto.Z*semi_h)
    p3 = XYZ(c.X - eje_ancho.X*semi_a + eje_alto.X*semi_h,
             c.Y - eje_ancho.Y*semi_a + eje_alto.Y*semi_h,
             c.Z - eje_ancho.Z*semi_a + eje_alto.Z*semi_h)

    curvas = [Line.CreateBound(p0,p1), Line.CreateBound(p1,p2),
              Line.CreateBound(p2,p3), Line.CreateBound(p3,p0)]

    # La normal del layout es el eje longitudinal de la viga
    normal = eje_long if hacia_adelante else XYZ(-eje_long.X, -eje_long.Y, -eje_long.Z)

    rebar = Rebar.CreateFromCurves(
        doc, RebarStyle.StirrupTie, bar_type,
        hook_type, hook_type, viga, normal, curvas,
        RebarHookOrientation.Left, RebarHookOrientation.Right, True, True)

    if num_barras >= 2:
        rebar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            num_barras, mm_a_pies(espaciado_mm), True, True, True)
    return rebar

def penetracion_columna_en_extremo(doc, viga, p_extremo, eje_long, longitud_viga_pies):
    """
    Busca columnas estructurales cuyo BoundingBox contenga el punto extremo
    de la viga. Si encuentra una, calcula cuánto penetra la columna en la viga
    medido a lo largo del eje longitudinal (en mm). Si no hay columna, 0.

    p_extremo  : XYZ del extremo de la viga (en pies)
    eje_long   : vector unitario hacia el INTERIOR de la viga desde ese extremo
    """
    # Recolectar todas las columnas estructurales (sin filtro geométrico de Revit,
    # que no es estable en esta versión de IronPython) y filtrar manualmente.
    collector = FilteredElementCollector(doc)
    collector = collector.OfCategory(BuiltInCategory.OST_StructuralColumns)
    collector = collector.WhereElementIsNotElementType()
    columnas  = collector.ToElements()

    if columnas is None:
        return 0.0

    tol = mm_a_pies(50.0)  # 5 cm de tolerancia

    # Buscar manualmente la columna cuyo BoundingBox contiene el punto extremo
    col = None
    for candidata in columnas:
        bb = candidata.get_BoundingBox(None)
        if bb is None:
            continue
        if (bb.Min.X - tol <= p_extremo.X <= bb.Max.X + tol and
            bb.Min.Y - tol <= p_extremo.Y <= bb.Max.Y + tol and
            bb.Min.Z - tol <= p_extremo.Z <= bb.Max.Z + tol):
            col = candidata
            break

    if col is None:
        return 0.0

    bb = col.get_BoundingBox(None)
    if bb is None:
        return 0.0

    # 8 esquinas del bounding box de la columna
    esquinas = [
        XYZ(bb.Min.X, bb.Min.Y, bb.Min.Z), XYZ(bb.Max.X, bb.Min.Y, bb.Min.Z),
        XYZ(bb.Min.X, bb.Max.Y, bb.Min.Z), XYZ(bb.Max.X, bb.Max.Y, bb.Min.Z),
        XYZ(bb.Min.X, bb.Min.Y, bb.Max.Z), XYZ(bb.Max.X, bb.Min.Y, bb.Max.Z),
        XYZ(bb.Min.X, bb.Max.Y, bb.Max.Z), XYZ(bb.Max.X, bb.Max.Y, bb.Max.Z),
    ]
    # Proyectar cada esquina sobre el eje longitudinal desde el extremo
    proyecciones = []
    for esq in esquinas:
        v = esq - p_extremo
        proy = v.DotProduct(eje_long)  # distancia a lo largo del eje (pies)
        proyecciones.append(proy)

    # La penetración es hasta dónde llega la columna hacia el interior de la viga
    # (proyección máxima positiva, acotada a la mitad de la viga)
    max_proy = max(proyecciones)
    if max_proy <= 0:
        return 0.0
    penetracion_mm = pies_a_mm(min(max_proy, longitud_viga_pies / 2.0))
    return penetracion_mm

def penetracion_viga_en_extremo(doc, viga_actual_id, p_extremo, eje_long, longitud_viga_pies):
    """
    Busca vigas transversales (OST_StructuralFraming) cuyo BoundingBox contenga
    el punto extremo de la viga analizada. Si encuentra una, calcula cuánto
    penetra esa viga transversal hacia el interior medido en mm a lo largo de
    eje_long. Si no hay viga transversal, retorna 0.

    p_extremo         : XYZ del extremo de la viga (en pies)
    eje_long          : vector unitario hacia el INTERIOR de la viga desde ese extremo
    longitud_viga_pies: longitud total de la viga en pies (para acotar el resultado)
    """
    collector = FilteredElementCollector(doc)
    collector = collector.OfCategory(BuiltInCategory.OST_StructuralFraming)
    collector = collector.WhereElementIsNotElementType()
    vigas = collector.ToElements()

    if vigas is None:
        return 0.0

    tol = mm_a_pies(50.0)  # 5 cm de tolerancia

    viga_trans = None
    for cand in vigas:
        # Excluir la viga actual para que no se detecte a sí misma
        if cand.Id == viga_actual_id:
            continue
        bb = cand.get_BoundingBox(None)
        if bb is None:
            continue
        if (bb.Min.X - tol <= p_extremo.X <= bb.Max.X + tol and
            bb.Min.Y - tol <= p_extremo.Y <= bb.Max.Y + tol and
            bb.Min.Z - tol <= p_extremo.Z <= bb.Max.Z + tol):
            viga_trans = cand
            break

    if viga_trans is None:
        return 0.0

    bb = viga_trans.get_BoundingBox(None)
    if bb is None:
        return 0.0

    # 8 esquinas del bounding box de la viga transversal
    esquinas = [
        XYZ(bb.Min.X, bb.Min.Y, bb.Min.Z), XYZ(bb.Max.X, bb.Min.Y, bb.Min.Z),
        XYZ(bb.Min.X, bb.Max.Y, bb.Min.Z), XYZ(bb.Max.X, bb.Max.Y, bb.Min.Z),
        XYZ(bb.Min.X, bb.Min.Y, bb.Max.Z), XYZ(bb.Max.X, bb.Min.Y, bb.Max.Z),
        XYZ(bb.Min.X, bb.Max.Y, bb.Max.Z), XYZ(bb.Max.X, bb.Max.Y, bb.Max.Z),
    ]
    proyecciones = []
    for esq in esquinas:
        v = esq - p_extremo
        proy = v.DotProduct(eje_long)
        proyecciones.append(proy)

    max_proy = max(proyecciones)
    if max_proy <= 0:
        return 0.0
    penetracion_mm = pies_a_mm(min(max_proy, longitud_viga_pies / 2.0))
    return penetracion_mm

def calcular_N_y_espaciado(longitud_mm, espaciado_maximo_mm):
    if longitud_mm <= 0 or espaciado_maximo_mm <= 0:
        return 2, longitud_mm
    N = max(2, int(math.ceil(longitud_mm / espaciado_maximo_mm)) + 1)
    return N, longitud_mm / (N - 1)

# ─── Recopilar tipos ──────────────────────────────────────────────────────────
barra_tipos = FilteredElementCollector(doc).OfClass(RebarBarType).ToElements()
diametros = {}; diametros_mm = {}
for bt in barra_tipos:
    n = bt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    diametros[n] = bt.Id
    dp = bt.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER)
    if dp: diametros_mm[n] = pies_a_mm(dp.AsDouble())

gancho_tipos = FilteredElementCollector(doc).OfClass(RebarHookType).ToElements()
ganchos = {}
for gt in gancho_tipos:
    n = gt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    ganchos[n] = gt.Id

nombres_diametros = sorted(diametros.keys())
nombres_ganchos   = sorted(ganchos.keys(), key=lambda n: (0 if '135' in n else 1, n))

# ─── XAML ─────────────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Flejes en Vigas"
    Width="400" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">

  <ScrollViewer VerticalScrollBarVisibility="Auto">
  <StackPanel Margin="14">

    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Flejes en Vigas" FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Instala flejes en vigas eligiendo la distribución --- Ados Software" FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="BARRA Y RECUBRIMIENTO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Grid Margin="0,0,0,6">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Diámetro del estribo" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbDiametro" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Recubrimiento (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtRecub" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
        </Grid>
        <TextBlock Text="Tipo de gancho" Foreground="#555" Margin="0,0,0,3"/>
        <ComboBox x:Name="cbGancho" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#DCDCDC" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="LONGITUD LIBRE" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,4"/>
        <TextBlock Foreground="#777" FontSize="11" Margin="0,0,0,8" TextWrapping="Wrap">
          Distancia desde cada extremo de la viga hasta el primer y último estribo.
        </TextBlock>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Offset inicio (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtOffsetInf" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Offset fin (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtOffsetSup" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="DISTRIBUCIÓN" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Grid Margin="0,0,0,10">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <Border Grid.Column="0" CornerRadius="4,0,0,4" BorderBrush="#F9B233" BorderThickness="1">
            <RadioButton x:Name="rbUniforme" Content="  Uniforme"
                         GroupName="modo" IsChecked="True"
                         Padding="8,6" FontWeight="SemiBold"/>
          </Border>
          <Border Grid.Column="1" CornerRadius="0,4,4,0" BorderBrush="#F9B233" BorderThickness="1,1,1,1" Margin="-1,0,0,0">
            <RadioButton x:Name="rbZonas" Content="  E1 — E2 — E1"
                         GroupName="modo"
                         Padding="8,6" FontWeight="SemiBold"/>
          </Border>
        </Grid>

        <StackPanel x:Name="panelUniforme">
          <TextBlock Foreground="#666" FontSize="11" Margin="0,0,0,8" TextWrapping="Wrap">
            Un solo espaciado constante a lo largo de toda la viga.
          </TextBlock>
          <TextBlock Text="Espaciado entre estribos (mm)" Foreground="#555" Margin="0,0,0,3"/>
          <TextBox x:Name="txtEspUni" Text="200" Height="28" Padding="6,4"
                   BorderBrush="#BDBDBD" BorderThickness="1"/>
        </StackPanel>

        <StackPanel x:Name="panelZonas" Visibility="Collapsed">
          <TextBlock Foreground="#666" FontSize="11" Margin="0,0,0,10" TextWrapping="Wrap">
            Estribos más juntos en los apoyos (extremos) y más separados en el centro de la luz.
          </TextBlock>
          <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8" Margin="0,0,0,8"
                  BorderBrush="#F9B233" BorderThickness="1">
            <StackPanel>
              <TextBlock Text="ZONA  E1  —  Apoyos (extremos)" FontWeight="Bold"
                         Foreground="#000000" Margin="0,0,0,6"/>
              <Grid>
                <Grid.ColumnDefinitions>
                  <ColumnDefinition Width="*"/>
                  <ColumnDefinition Width="10"/>
                  <ColumnDefinition Width="*"/>
                </Grid.ColumnDefinitions>
                <StackPanel Grid.Column="0">
                  <TextBlock Text="Estribos por extremo" Foreground="#555" Margin="0,0,0,3"/>
                  <TextBox x:Name="txtNExt" Text="6" Height="28" Padding="6,4"
                           BorderBrush="#BDBDBD" BorderThickness="1"/>
                </StackPanel>
                <StackPanel Grid.Column="2">
                  <TextBlock Text="Espaciado (mm)" Foreground="#555" Margin="0,0,0,3"/>
                  <TextBox x:Name="txtEspExt" Text="100" Height="28" Padding="6,4"
                           BorderBrush="#BDBDBD" BorderThickness="1"/>
                </StackPanel>
              </Grid>
            </StackPanel>
          </Border>
          <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8"
                  BorderBrush="#F9B233" BorderThickness="1">
            <StackPanel>
              <TextBlock Text="ZONA  E2  —  Centro de la luz" FontWeight="Bold"
                         Foreground="#000000" Margin="0,0,0,6"/>
              <TextBlock Text="Espaciado máximo (mm)" Foreground="#555" Margin="0,0,0,3"/>
              <TextBox x:Name="txtEspCen" Text="200" Height="28" Padding="6,4"
                       BorderBrush="#BDBDBD" BorderThickness="1"/>
            </StackPanel>
          </Border>
        </StackPanel>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="VIGAS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar vigas en Revit"
                Height="32" Cursor="Hand"
                Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador"
                   Text="Ninguna viga seleccionada"
                   Foreground="#999" FontSize="11"
                   HorizontalAlignment="Center" Margin="0,6,0,0"/>
      </StackPanel>
    </Border>

    <Grid>
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="10"/>
        <ColumnDefinition Width="2*"/>
      </Grid.ColumnDefinitions>
      <Button x:Name="btnCancelar" Grid.Column="0" Content="Cancelar"
              Height="34" Cursor="Hand"
              Background="#EEEEEE" Foreground="#555"
              BorderBrush="#BFBFBF" BorderThickness="1"/>
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear estribos"
              Height="34" Cursor="Hand"
              Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
  </ScrollViewer>
</Window>
"""

class FormFlejes(object):
    def __init__(self):
        self.resultado = None
        self.vigas_ids = []
        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.cbDiametro  = self.win.FindName('cbDiametro')
        self.cbGancho    = self.win.FindName('cbGancho')
        self.txtRecub    = self.win.FindName('txtRecub')
        self.txtOffInf   = self.win.FindName('txtOffsetInf')
        self.txtOffSup   = self.win.FindName('txtOffsetSup')
        self.rbUniforme  = self.win.FindName('rbUniforme')
        self.rbZonas     = self.win.FindName('rbZonas')
        self.panelUni    = self.win.FindName('panelUniforme')
        self.panelZon    = self.win.FindName('panelZonas')
        self.txtEspUni   = self.win.FindName('txtEspUni')
        self.txtNExt     = self.win.FindName('txtNExt')
        self.txtEspExt   = self.win.FindName('txtEspExt')
        self.txtEspCen   = self.win.FindName('txtEspCen')
        self.lblContador = self.win.FindName('lblContador')

        for n in nombres_diametros:
            self.cbDiametro.Items.Add(n)
        if self.cbDiametro.Items.Count > 0:
            self.cbDiametro.SelectedIndex = 0
        for n in nombres_ganchos:
            self.cbGancho.Items.Add(n)
        if self.cbGancho.Items.Count > 0:
            self.cbGancho.SelectedIndex = 0

        self.win.FindName('btnSeleccionar').Click += self.OnSeleccionar
        self.win.FindName('btnCancelar').Click    += self.OnCancelar
        self.win.FindName('btnAceptar').Click     += self.OnAceptar
        self.rbUniforme.Checked += self.OnModoChanged
        self.rbZonas.Checked    += self.OnModoChanged

    def OnModoChanged(self, sender, e):
        if self.rbZonas.IsChecked:
            self.panelUni.Visibility = SW.Visibility.Collapsed
            self.panelZon.Visibility = SW.Visibility.Visible
        else:
            self.panelUni.Visibility = SW.Visibility.Visible
            self.panelZon.Visibility = SW.Visibility.Collapsed

    def OnSeleccionar(self, sender, e):
        self.win.Hide()
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, FiltroVigas(),
                'Selecciona vigas y presiona ENTER')
            self.vigas_ids = [r.ElementId for r in refs]
            n = len(self.vigas_ids)
            self.lblContador.Text       = '{} viga{} seleccionada{}'.format(
                n, 's' if n != 1 else '', 's' if n != 1 else '')
            self.lblContador.Foreground = SWM.Brushes.DarkGreen
        except Exception:
            self.lblContador.Text       = 'Seleccion cancelada'
            self.lblContador.Foreground = SWM.Brushes.Gray
        self.win.ShowDialog()

    def OnCancelar(self, sender, e):
        self.resultado = None
        self.win.Close()

    def OnAceptar(self, sender, e):
        try:
            r = {
                'recub'     : float(self.txtRecub.Text) * 10.0,
                'offset_inf': float(self.txtOffInf.Text) * 10.0,
                'offset_sup': float(self.txtOffSup.Text) * 10.0,
                'diametro'  : str(self.cbDiametro.SelectedItem),
                'gancho'    : str(self.cbGancho.SelectedItem),
                'modo_zonas': bool(self.rbZonas.IsChecked),
                'esp_uni'   : float(self.txtEspUni.Text),
                'n_ext'     : int(float(self.txtNExt.Text)),
                'esp_ext'   : float(self.txtEspExt.Text),
                'esp_cen'   : float(self.txtEspCen.Text),
            }
        except Exception as ex:
            SW.MessageBox.Show('Verifica los campos numericos.\n\n' + str(ex),
                'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        if not self.vigas_ids:
            SW.MessageBox.Show('Selecciona al menos una viga antes de continuar.',
                'Sin vigas', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = r
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.resultado

# ─── Mostrar formulario ───────────────────────────────────────────────────────
form = FormFlejes()
res  = form.show()
if res is None:
    import sys; sys.exit()

recubrimiento_mm = res['recub']
offset_ini_mm    = res['offset_inf']
offset_fin_mm    = res['offset_sup']
modo_zonas       = res['modo_zonas']
esp_uni_mm       = res['esp_uni']
n_ext            = res['n_ext']
esp_ext_mm       = res['esp_ext']
esp_cen_mm       = res['esp_cen']
diametro_id      = diametros[res['diametro']]
gancho_id        = ganchos[res['gancho']]
diametro_mm      = diametros_mm.get(res['diametro'], 10.0)
bar_type         = doc.GetElement(diametro_id)
hook_type        = doc.GetElement(gancho_id)
vigas_seleccionadas = form.vigas_ids

# ─── Transacción ──────────────────────────────────────────────────────────────
total_grupos = 0

with Transaction(doc, 'Flejes en vigas') as t:
    t.Start()
    for eid in vigas_seleccionadas:
        viga = doc.GetElement(eid)
        try:
            (p_ini, eje_long, eje_ancho, eje_alto,
             ancho_mm, alto_mm, longitud_mm, desplaz_vert_mm) = get_info_viga(viga)
        except Exception:
            continue

        # Vector de desplazamiento vertical para centrar el estribo en la sección
        dv = mm_a_pies(desplaz_vert_mm)
        offset_centro = XYZ(eje_alto.X*dv, eje_alto.Y*dv, eje_alto.Z*dv)

        # Detectar apoyo en cada extremo: columna o viga transversal.
        # En el extremo inicial el eje apunta hacia adentro (+eje_long).
        # En el extremo final apunta hacia adentro (-eje_long).
        longitud_pies = mm_a_pies(longitud_mm)
        p_fin_viga = XYZ(p_ini.X + eje_long.X*longitud_pies,
                         p_ini.Y + eje_long.Y*longitud_pies,
                         p_ini.Z + eje_long.Z*longitud_pies)
        eje_long_neg = XYZ(-eje_long.X, -eje_long.Y, -eje_long.Z)

        pen_col_ini_mm = penetracion_columna_en_extremo(
            doc, viga, p_ini, eje_long, longitud_pies)
        pen_col_fin_mm = penetracion_columna_en_extremo(
            doc, viga, p_fin_viga, eje_long_neg, longitud_pies)

        pen_vt_ini_mm = penetracion_viga_en_extremo(
            doc, eid, p_ini, eje_long, longitud_pies)
        pen_vt_fin_mm = penetracion_viga_en_extremo(
            doc, eid, p_fin_viga, eje_long_neg, longitud_pies)

        # Usar la mayor penetración detectada en cada extremo
        pen_ini_mm = max(pen_col_ini_mm, pen_vt_ini_mm)
        pen_fin_mm = max(pen_col_fin_mm, pen_vt_fin_mm)

        # Offset efectivo = penetración del apoyo + offset normal del usuario.
        # Si no hay apoyo detectado (penetración 0), queda solo el offset del usuario.
        offset_ini_efectivo = pen_ini_mm + offset_ini_mm
        offset_fin_efectivo = pen_fin_mm + offset_fin_mm

        longitud_libre_mm = longitud_mm - offset_ini_efectivo - offset_fin_efectivo
        if longitud_libre_mm <= 0: continue

        # Punto de inicio de la zona libre (usa offset EFECTIVO + centrado vertical)
        d_ini = mm_a_pies(offset_ini_efectivo)
        c_ini = XYZ(
            p_ini.X + eje_long.X*d_ini + offset_centro.X,
            p_ini.Y + eje_long.Y*d_ini + offset_centro.Y,
            p_ini.Z + eje_long.Z*d_ini + offset_centro.Z)
        d_fin = mm_a_pies(longitud_mm - offset_fin_efectivo)
        c_fin = XYZ(
            p_ini.X + eje_long.X*d_fin + offset_centro.X,
            p_ini.Y + eje_long.Y*d_fin + offset_centro.Y,
            p_ini.Z + eje_long.Z*d_fin + offset_centro.Z)

        def punto_en(dist_desde_ini_mm):
            d = mm_a_pies(offset_ini_efectivo + dist_desde_ini_mm)
            return XYZ(p_ini.X + eje_long.X*d + offset_centro.X,
                       p_ini.Y + eje_long.Y*d + offset_centro.Y,
                       p_ini.Z + eje_long.Z*d + offset_centro.Z)

        try:
            if not modo_zonas:
                N, esp = calcular_N_y_espaciado(longitud_libre_mm, esp_uni_mm)
                if N < 2: continue
                crear_grupo_estribos(doc, viga, c_ini,
                    ancho_mm, alto_mm, recubrimiento_mm,
                    bar_type, hook_type, eje_long, eje_ancho, eje_alto,
                    N, esp, hacia_adelante=True)
                total_grupos += 1
            else:
                zona_ext_mm  = esp_ext_mm * (n_ext - 1)
                if zona_ext_mm > longitud_libre_mm * 0.45:
                    zona_ext_mm = longitud_libre_mm * 0.45
                esp_ext_real = zona_ext_mm / (n_ext - 1) if n_ext > 1 else esp_ext_mm

                # E1 inicio (desde c_ini hacia adelante)
                crear_grupo_estribos(doc, viga, c_ini,
                    ancho_mm, alto_mm, recubrimiento_mm,
                    bar_type, hook_type, eje_long, eje_ancho, eje_alto,
                    n_ext, esp_ext_real, hacia_adelante=True)
                total_grupos += 1

                # E1 fin (desde c_fin hacia atrás)
                crear_grupo_estribos(doc, viga, c_fin,
                    ancho_mm, alto_mm, recubrimiento_mm,
                    bar_type, hook_type, eje_long, eje_ancho, eje_alto,
                    n_ext, esp_ext_real, hacia_adelante=False)
                total_grupos += 1

                # E2 central
                dist_ult_e1_ini = zona_ext_mm
                dist_pri_e1_fin = longitud_libre_mm - zona_ext_mm
                dist_ini_e2     = dist_ult_e1_ini + esp_cen_mm
                dist_fin_e2     = dist_pri_e1_fin - esp_cen_mm
                long_cen_mm     = dist_fin_e2 - dist_ini_e2

                if long_cen_mm >= 0:
                    if long_cen_mm < 1.0:
                        crear_grupo_estribos(doc, viga,
                            punto_en((dist_ini_e2 + dist_fin_e2)/2.0),
                            ancho_mm, alto_mm, recubrimiento_mm,
                            bar_type, hook_type, eje_long, eje_ancho, eje_alto,
                            1, esp_cen_mm, hacia_adelante=True)
                        total_grupos += 1
                    else:
                        N_c, esp_c = calcular_N_y_espaciado(long_cen_mm, esp_cen_mm)
                        if N_c >= 2:
                            crear_grupo_estribos(doc, viga,
                                punto_en(dist_ini_e2),
                                ancho_mm, alto_mm, recubrimiento_mm,
                                bar_type, hook_type, eje_long, eje_ancho, eje_alto,
                                N_c, esp_c, hacia_adelante=True)
                            total_grupos += 1
        except Exception:
            continue
    t.Commit()

modo_txt = 'E1-E2-E1' if modo_zonas else 'Uniforme'
SW.MessageBox.Show(
    'Se crearon {} grupo(s) de estribos\nen {} viga(s)\nDistribucion: {}'.format(
        total_grupos, len(vigas_seleccionadas), modo_txt),
    'Listo', SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)