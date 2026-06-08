# -*- coding: utf-8 -*-
"""
Acabados de Muros Exteriores — Selección por Cara  v5
------------------------------------------------------
Esquinas resueltas geométricamente:
  - Se calculan todas las curvas de acabado desplazadas primero.
  - Se detectan pares de acabados que forman esquina (exterior o interior).
  - Se calcula el punto de intersección real de cada par.
  - Se ajustan los extremos de ambas curvas al punto de intersección.
  - Resultado: esquinas perfectas sin depender del Join para el corte.
  - Join automático acabados↔base y acabados entre sí (para unión BIM).
  - Desfases de base y superior en cm.

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
from System.Windows.Markup import XamlReader
from System.Xml import XmlReader
from System.IO import StringReader

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    Transaction, XYZ, Line, Wall, WallType, Level,
    JoinGeometryUtils
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# ─────────────────────────────────────────────────────────────
# Conversiones
# ─────────────────────────────────────────────────────────────
def mm_a_ft(mm): return mm / 304.8
def cm_a_ft(cm): return cm / 30.48


# ─────────────────────────────────────────────────────────────
# Filtro: solo caras de muros
# ─────────────────────────────────────────────────────────────
class FiltroCaraMuro(ISelectionFilter):
    def AllowElement(self, elem):
        if elem is None or elem.Category is None:
            return False
        return elem.Category.Id.IntegerValue == int(BuiltInCategory.OST_Walls)
    def AllowReference(self, ref, point):
        return True


# ─────────────────────────────────────────────────────────────
# Tipos de muro
# ─────────────────────────────────────────────────────────────
wall_types_col = FilteredElementCollector(doc).OfClass(WallType).ToElements()
tipos_muro = {}
for wt in wall_types_col:
    p = wt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
    if p:
        n = p.AsString()
        if n:
            tipos_muro[n] = wt

if not tipos_muro:
    SW.MessageBox.Show('No se encontraron tipos de muro.', 'Error',
                       SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

nombres_muro     = sorted(tipos_muro.keys())
DEFAULT_ACABADO  = 'TARRAJEO'
idx_default_muro = (nombres_muro.index(DEFAULT_ACABADO)
                    if DEFAULT_ACABADO in nombres_muro else 0)

# ─────────────────────────────────────────────────────────────
# Niveles
# ─────────────────────────────────────────────────────────────
niveles_col   = sorted(
    FilteredElementCollector(doc).OfClass(Level).ToElements(),
    key=lambda lv: lv.Elevation)
nombres_nivel = [lv.Name for lv in niveles_col]

if not nombres_nivel:
    SW.MessageBox.Show('No se encontraron niveles.', 'Error',
                       SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()


# ─────────────────────────────────────────────────────────────
# XAML
# ─────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acabados de Muros \u2014 Selecci\u00f3n por Cara"
    Width="480" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">
  <StackPanel Margin="14">

    <!-- Encabezado -->
    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Acabados de Muros Exteriores"
                   FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Crea acabados pegados a la cara seleccionada  \u2014  Ados Software"
                   FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <!-- Tipo de acabado -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="TIPO DE MURO ACABADO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbTipoMuro" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <!-- Niveles -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="12"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <StackPanel Grid.Column="0">
          <TextBlock Text="NIVEL BASE" FontSize="10" FontWeight="Bold"
                     Foreground="#000000" Margin="0,0,0,8"/>
          <ComboBox x:Name="cbNivelBase" Height="28" Padding="4,0"/>
        </StackPanel>
        <StackPanel Grid.Column="2">
          <TextBlock Text="RESTRICCI\u00d3N SUPERIOR" FontSize="10" FontWeight="Bold"
                     Foreground="#000000" Margin="0,0,0,8"/>
          <ComboBox x:Name="cbNivelTop" Height="28" Padding="4,0"/>
        </StackPanel>
      </Grid>
    </Border>

    <!-- Desfases -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="DESFASES (cm)" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,10"/>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="12"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Desfase base (cm)" FontSize="10" Foreground="#555" Margin="0,0,0,4"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="65"/>
              </Grid.ColumnDefinitions>
              <TextBlock Text="\u2191 sube  \u2193 baja" FontSize="9" Foreground="#999"
                         VerticalAlignment="Center" Grid.Column="0"/>
              <TextBox x:Name="txtDesfaseBase" Text="0" Grid.Column="1"
                       Padding="4,3" BorderBrush="#BFBFBF" BorderThickness="1" Margin="4,0,0,0"/>
            </Grid>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Desfase superior (cm)" FontSize="10" Foreground="#555" Margin="0,0,0,4"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="65"/>
              </Grid.ColumnDefinitions>
              <TextBlock Text="\u2191 sube  \u2193 baja" FontSize="9" Foreground="#999"
                         VerticalAlignment="Center" Grid.Column="0"/>
              <TextBox x:Name="txtDesfaseTop" Text="0" Grid.Column="1"
                       Padding="4,3" BorderBrush="#BFBFBF" BorderThickness="1" Margin="4,0,0,0"/>
            </Grid>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <!-- Info -->
    <Border Background="#FFF8E7" CornerRadius="6" Padding="10,8" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1">
      <TextBlock FontSize="10" Foreground="#555" TextWrapping="Wrap"
        Text="Clica la cara del muro donde quieres el acabado. Las esquinas se calculan geom\u00e9tricamente \u2014 selecciona todas las caras en una sola operaci\u00f3n para que el script pueda resolverlas."/>
    </Border>

    <!-- Selección -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="CARAS SELECCIONADAS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar Caras de Muros en Revit"
                Height="32" Cursor="Hand"
                Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador" Text="Ninguna cara seleccionada."
                   Foreground="#999" FontSize="11"
                   HorizontalAlignment="Center" Margin="0,6,0,0"/>
      </StackPanel>
    </Border>

    <!-- Botones -->
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
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear Acabados"
              Height="34" Cursor="Hand"
              Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
</Window>
"""


# ─────────────────────────────────────────────────────────────
# Formulario
# ─────────────────────────────────────────────────────────────
class FormAcabados(object):
    def __init__(self):
        self.resultado = None
        self.caras     = []

        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.cbTipoMuro     = self.win.FindName('cbTipoMuro')
        self.cbNivelBase    = self.win.FindName('cbNivelBase')
        self.cbNivelTop     = self.win.FindName('cbNivelTop')
        self.txtDesfaseBase = self.win.FindName('txtDesfaseBase')
        self.txtDesfaseTop  = self.win.FindName('txtDesfaseTop')
        self.lblContador    = self.win.FindName('lblContador')

        for n in nombres_muro:
            self.cbTipoMuro.Items.Add(n)
        self.cbTipoMuro.SelectedIndex = idx_default_muro

        for n in nombres_nivel:
            self.cbNivelBase.Items.Add(n)
            self.cbNivelTop.Items.Add(n)
        self.cbNivelBase.SelectedIndex = 0
        self.cbNivelTop.SelectedIndex  = min(1, len(nombres_nivel) - 1)

        self.win.FindName('btnSeleccionar').Click += self.OnSeleccionar
        self.win.FindName('btnCancelar').Click    += self.OnCancelar
        self.win.FindName('btnAceptar').Click     += self.OnAceptar

    def OnSeleccionar(self, sender, e):
        self.win.Hide()
        self.caras = []
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Face,
                FiltroCaraMuro(),
                u'Clica las caras de muro \u2014 Enter para confirmar')

            muros_set = set()
            for ref in refs:
                wall = doc.GetElement(ref.ElementId)
                if wall is None:
                    continue
                self.caras.append({
                    'wall_id':      ref.ElementId,
                    'global_point': ref.GlobalPoint,
                    'orient_ext':   wall.Orientation,
                })
                muros_set.add(ref.ElementId.IntegerValue)

            n  = len(self.caras)
            nm = len(muros_set)
            self.lblContador.Text = (
                u'{} cara(s) en {} muro(s).'.format(n, nm) if n > 0
                else u'No se reconocieron caras v\u00e1lidas.')
        except Exception:
            self.lblContador.Text = u'Selecci\u00f3n cancelada.'
        self.win.ShowDialog()

    def OnAceptar(self, sender, e):
        if not self.caras:
            SW.MessageBox.Show(u'No hay caras seleccionadas.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        try:
            dsf_base = float(self.txtDesfaseBase.Text.replace(',', '.'))
            dsf_top  = float(self.txtDesfaseTop.Text.replace(',', '.'))
        except ValueError:
            SW.MessageBox.Show(u'Los desfases deben ser n\u00fameros.',
                u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        idx_b = self.cbNivelBase.SelectedIndex
        idx_t = self.cbNivelTop.SelectedIndex
        if idx_b < 0 or idx_t < 0:
            SW.MessageBox.Show(u'Selecciona niveles v\u00e1lidos.',
                u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = {
            'tipo_nombre':     self.cbTipoMuro.SelectedItem,
            'nivel_base':      niveles_col[idx_b],
            'nivel_top':       niveles_col[idx_t],
            'desfase_base_ft': cm_a_ft(dsf_base),
            'desfase_top_ft':  cm_a_ft(dsf_top),
        }
        self.win.Close()

    def OnCancelar(self, sender, e):
        self.resultado = None
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.resultado


# ─────────────────────────────────────────────────────────────
# Mostrar ventana
# ─────────────────────────────────────────────────────────────
form = FormAcabados()
res  = form.show()
if res is None:
    import sys; sys.exit()

tipo_muro_obj   = tipos_muro[res['tipo_nombre']]
tipo_muro_id    = tipo_muro_obj.Id
nivel_base      = res['nivel_base']
nivel_top       = res['nivel_top']
desfase_base_ft = res['desfase_base_ft']
desfase_top_ft  = res['desfase_top_ft']
caras_data      = form.caras

# Espesor del acabado
espesor_acabado_ft = mm_a_ft(0.0)
try:
    cp = tipo_muro_obj.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM)
    if cp:
        espesor_acabado_ft = cp.AsDouble()
except Exception:
    pass

z_base_nivel = nivel_base.Elevation
z_top_nivel  = nivel_top.Elevation
altura_ft    = (z_top_nivel - z_base_nivel) + desfase_top_ft - desfase_base_ft
if altura_ft < mm_a_ft(100.0):
    altura_ft = mm_a_ft(3000.0)
z_arranque   = z_base_nivel + desfase_base_ft


# ─────────────────────────────────────────────────────────────
# Utilidades geométricas
# ─────────────────────────────────────────────────────────────
def proyectar_sobre_linea_xy(punto, linea):
    p0    = linea.GetEndPoint(0)
    p1    = linea.GetEndPoint(1)
    dir_l = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0.0)
    lng   = dir_l.GetLength()
    if lng < 1e-6:
        return p0
    dir_l = dir_l.Normalize()
    v = XYZ(punto.X - p0.X, punto.Y - p0.Y, 0.0)
    t = v.DotProduct(dir_l)
    return XYZ(p0.X + dir_l.X * t, p0.Y + dir_l.Y * t, punto.Z)


def dir_xy(linea):
    p0 = linea.GetEndPoint(0)
    p1 = linea.GetEndPoint(1)
    v  = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0.0)
    lg = v.GetLength()
    return v.Normalize() if lg > 1e-6 else XYZ(1, 0, 0)


def interseccion_lineas_xy(p0, d0, p1, d1):
    dx  = p1.X - p0.X
    dy  = p1.Y - p0.Y
    det = d0.X * (-d1.Y) - d0.Y * (-d1.X)
    if abs(det) < 1e-9:
        return None
    t  = (dx * (-d1.Y) - dy * (-d1.X)) / det
    return XYZ(p0.X + t * d0.X, p0.Y + t * d0.Y, p0.Z)


def extremo_mas_cercano_punto(ci, punto):
    p0 = ci['p0']
    p1 = ci['p1']
    d0 = math.sqrt((p0.X-punto.X)**2 + (p0.Y-punto.Y)**2)
    d1 = math.sqrt((p1.X-punto.X)**2 + (p1.Y-punto.Y)**2)
    return (0, d0) if d0 <= d1 else (1, d1)


# ─────────────────────────────────────────────────────────────
# Paso 1: calcular curvas desplazadas
# ─────────────────────────────────────────────────────────────
curvas_info = []

for cara in caras_data:
    wall = doc.GetElement(cara['wall_id'])
    if wall is None:
        curvas_info.append(None)
        continue

    orient_ext = cara['orient_ext']
    gp         = cara['global_point']
    loc_curve  = wall.Location.Curve

    p_proy   = proyectar_sobre_linea_xy(gp, loc_curve)
    vec_clic = XYZ(gp.X - p_proy.X, gp.Y - p_proy.Y, 0.0)
    dot      = vec_clic.DotProduct(orient_ext)
    sentido  = 1 if dot >= 0 else -1

    dist_lc_a_cara = vec_clic.GetLength()
    semi           = espesor_acabado_ft / 2.0
    d_total        = dist_lc_a_cara + semi

    dx = orient_ext.X * sentido * d_total
    dy = orient_ext.Y * sentido * d_total

    p0_orig = loc_curve.GetEndPoint(0)
    p1_orig = loc_curve.GetEndPoint(1)

    np0 = XYZ(p0_orig.X + dx, p0_orig.Y + dy, z_arranque)
    np1 = XYZ(p1_orig.X + dx, p1_orig.Y + dy, z_arranque)

    curvas_info.append({
        'p0':      np0,
        'p1':      np1,
        'dir':     dir_xy(loc_curve),
        'sentido': sentido,
        'wall_id': cara['wall_id'],
    })


# ─────────────────────────────────────────────────────────────
# Paso 2: ajustar esquinas geométricamente
# ─────────────────────────────────────────────────────────────
TOL_ESQUINA = cm_a_ft(60.0)
n_curvas    = len(curvas_info)

for i in range(n_curvas):
    ci = curvas_info[i]
    if ci is None:
        continue
    for j in range(i + 1, n_curvas):
        cj = curvas_info[j]
        if cj is None:
            continue
        if ci['wall_id'].IntegerValue == cj['wall_id'].IntegerValue:
            continue

        cross = ci['dir'].X * cj['dir'].Y - ci['dir'].Y * cj['dir'].X
        if abs(cross) < 0.1:
            continue

        pt_cruz = interseccion_lineas_xy(ci['p0'], ci['dir'],
                                          cj['p0'], cj['dir'])
        if pt_cruz is None:
            continue

        idx_i, dist_i = extremo_mas_cercano_punto(ci, pt_cruz)
        idx_j, dist_j = extremo_mas_cercano_punto(cj, pt_cruz)

        if dist_i > TOL_ESQUINA or dist_j > TOL_ESQUINA:
            continue

        if idx_i == 0:
            ci['p0'] = XYZ(pt_cruz.X, pt_cruz.Y, ci['p0'].Z)
        else:
            ci['p1'] = XYZ(pt_cruz.X, pt_cruz.Y, ci['p1'].Z)

        if idx_j == 0:
            cj['p0'] = XYZ(pt_cruz.X, pt_cruz.Y, cj['p0'].Z)
        else:
            cj['p1'] = XYZ(pt_cruz.X, pt_cruz.Y, cj['p1'].Z)


# ─────────────────────────────────────────────────────────────
# Paso 3: crear los muros
# ─────────────────────────────────────────────────────────────
creados       = 0
errores       = 0
detalle       = []
muros_creados = []

with Transaction(doc, u'Acabados de Muros \u2014 por Cara') as t:
    t.Start()

    for idx, ci in enumerate(curvas_info):
        if ci is None:
            errores += 1
            detalle.append(u'Cara {}: muro no encontrado.'.format(idx))
            muros_creados.append(None)
            continue
        try:
            np0 = ci['p0']
            np1 = ci['p1']

            if np0.DistanceTo(np1) < mm_a_ft(10.0):
                detalle.append(u'Cara {}: curva muy corta.'.format(idx))
                errores += 1
                muros_creados.append(None)
                continue

            curva_acabado = Line.CreateBound(np0, np1)

            muro_acabado = Wall.Create(
                doc, curva_acabado, tipo_muro_id,
                nivel_base.Id, altura_ft, 0.0, False, False)

            try:
                p_off = muro_acabado.get_Parameter(BuiltInParameter.WALL_BASE_OFFSET)
                if p_off and not p_off.IsReadOnly:
                    p_off.Set(desfase_base_ft)
            except Exception:
                pass

            try:
                p_top_type = muro_acabado.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE)
                if p_top_type and not p_top_type.IsReadOnly:
                    p_top_type.Set(nivel_top.Id)
            except Exception:
                pass

            try:
                p_top_off = muro_acabado.get_Parameter(BuiltInParameter.WALL_TOP_OFFSET)
                if p_top_off and not p_top_off.IsReadOnly:
                    p_top_off.Set(desfase_top_ft)
            except Exception:
                pass

            muros_creados.append(muro_acabado)
            creados += 1

        except Exception as ex:
            detalle.append(u'Cara {}: {}'.format(idx, str(ex)))
            errores += 1
            muros_creados.append(None)

    t.Commit()


# ─────────────────────────────────────────────────────────────
# Paso 4: Join acabados↔base y entre sí
# ─────────────────────────────────────────────────────────────
def bboxes_solapan(bb1, bb2):
    tol = mm_a_ft(5.0)
    return (bb1.Min.X - tol < bb2.Max.X and
            bb1.Max.X + tol > bb2.Min.X and
            bb1.Min.Y - tol < bb2.Max.Y and
            bb1.Max.Y + tol > bb2.Min.Y)


def hacer_join(elem_a, elem_b):
    try:
        if JoinGeometryUtils.AreElementsJoined(doc, elem_a, elem_b):
            return True
        bb1 = elem_a.get_BoundingBox(None)
        bb2 = elem_b.get_BoundingBox(None)
        if bb1 and bb2 and bboxes_solapan(bb1, bb2):
            JoinGeometryUtils.JoinGeometry(doc, elem_a, elem_b)
            return True
    except Exception:
        pass
    return False


unidos        = 0
muros_validos = [(i, m) for i, m in enumerate(muros_creados) if m is not None]

if muros_validos:
    with Transaction(doc, u'Join \u2014 Acabados') as t2:
        t2.Start()

        for i, muro_ac in muros_validos:
            if i >= len(caras_data):
                continue
            muro_base = doc.GetElement(caras_data[i]['wall_id'])
            if muro_base and hacer_join(muro_base, muro_ac):
                unidos += 1

        for a, (i, mi) in enumerate(muros_validos):
            for b, (j, mj) in enumerate(muros_validos):
                if b <= a:
                    continue
                if hacer_join(mi, mj):
                    unidos += 1

        t2.Commit()


# ─────────────────────────────────────────────────────────────
# Resumen
# ─────────────────────────────────────────────────────────────
msg = (u'Acabados creados : {}\n'
       u'Uniones aplicadas: {}\n'
       u'Errores          : {}').format(creados, unidos, errores)
if detalle:
    msg += u'\n\nDetalle:\n' + u'\n'.join(detalle[:10])
    if len(detalle) > 10:
        msg += u'\n... y {} m\u00e1s.'.format(len(detalle) - 10)

SW.MessageBox.Show(msg, u'Resultado \u2014 Acabados de Muros',
                   SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)