# -*- coding: utf-8 -*-
"""
Acabados de Muros — Por Habitación v11
----------------------------------------
1. Leer vértices del boundary con Finish
2. Desplazar cada segmento perpendicularmente al interior (área con signo)
3. Crear un muro de acabado por segmento
4. Join entre acabados y con el muro base de cada segmento

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
    JoinGeometryUtils,
    SpatialElementBoundaryOptions, SpatialElementBoundaryLocation
)
from Autodesk.Revit.DB.Architecture import Room
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
view  = uidoc.ActiveView

def mm_a_ft(mm): return mm / 304.8
def cm_a_ft(cm): return cm / 30.48
def dist2d(a, b): return math.sqrt((a.X-b.X)**2+(a.Y-b.Y)**2)

# ─────────────────────────────────────────────────────────────
# Tipos de muro y niveles
# ─────────────────────────────────────────────────────────────
wall_types_col = FilteredElementCollector(doc).OfClass(WallType).ToElements()
tipos_muro = {}
for wt in wall_types_col:
    p = wt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
    if p:
        n = p.AsString()
        if n: tipos_muro[n] = wt

if not tipos_muro:
    SW.MessageBox.Show('No se encontraron tipos de muro.', 'Error',
        SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

nombres_muro     = sorted(tipos_muro.keys())
DEFAULT_ACABADO  = 'TARRAJEO'
idx_default_muro = (nombres_muro.index(DEFAULT_ACABADO)
                    if DEFAULT_ACABADO in nombres_muro else 0)

niveles_col   = sorted(FilteredElementCollector(doc).OfClass(Level).ToElements(),
                       key=lambda lv: lv.Elevation)
nombres_nivel = [lv.Name for lv in niveles_col]

if not nombres_nivel:
    SW.MessageBox.Show('No se encontraron niveles.', 'Error',
        SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

idx_nivel_vista = 0
try:
    if hasattr(view, 'GenLevel') and view.GenLevel:
        for i, lv in enumerate(niveles_col):
            if lv.Id == view.GenLevel.Id:
                idx_nivel_vista = i; break
except: pass

# ─────────────────────────────────────────────────────────────
# Filtro: solo habitaciones
# ─────────────────────────────────────────────────────────────
class FiltroHabitacion(ISelectionFilter):
    def AllowElement(self, elem): return isinstance(elem, Room)
    def AllowReference(self, ref, point): return True

# ─────────────────────────────────────────────────────────────
# Leer vértices y ElementId por segmento
# ─────────────────────────────────────────────────────────────
def leer_vertices(room, z_nivel):
    bnd_opts = SpatialElementBoundaryOptions()
    bnd_opts.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    boundaries = room.GetBoundarySegments(bnd_opts)

    vertices     = []
    sep_ids      = []
    seg_elem_ids = []
    if not boundaries: return vertices, sep_ids, seg_elem_ids

    vistos = set()
    for loop in boundaries:
        for seg in loop:
            try:
                p = seg.GetCurve().GetEndPoint(0)
                vertices.append(XYZ(p.X, p.Y, z_nivel))
                eid = seg.ElementId
                seg_elem_ids.append(eid)
                if eid and eid.IntegerValue > 0 and eid.IntegerValue not in vistos:
                    elem = doc.GetElement(eid)
                    if elem is not None and elem.Category is not None:
                        if elem.Category.Id.IntegerValue == int(BuiltInCategory.OST_RoomSeparationLines):
                            sep_ids.append(eid)
                            vistos.add(eid.IntegerValue)
            except: pass
        break

    return vertices, sep_ids, seg_elem_ids

# ─────────────────────────────────────────────────────────────
# XAML
# ─────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acabados por Habitación"
    Width="480" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">
  <StackPanel Margin="14">

    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Acabados de Muros — Por Habitación"
                   FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Crea acabados a partir del contorno de una habitación  —  Ados Software"
                   FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="TIPO DE MURO ACABADO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbTipoMuro" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="*"/><ColumnDefinition Width="12"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <StackPanel Grid.Column="0">
          <TextBlock Text="NIVEL BASE" FontSize="10" FontWeight="Bold"
                     Foreground="#000000" Margin="0,0,0,8"/>
          <ComboBox x:Name="cbNivelBase" Height="28" Padding="4,0"/>
        </StackPanel>
        <StackPanel Grid.Column="2">
          <TextBlock Text="RESTRICCIÓN SUPERIOR" FontSize="10" FontWeight="Bold"
                     Foreground="#000000" Margin="0,0,0,8"/>
          <ComboBox x:Name="cbNivelTop" Height="28" Padding="4,0"/>
        </StackPanel>
      </Grid>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="DESFASES (cm)" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,10"/>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/><ColumnDefinition Width="12"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Desfase base (cm)" FontSize="10" Foreground="#555" Margin="0,0,0,4"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/><ColumnDefinition Width="65"/>
              </Grid.ColumnDefinitions>
              <TextBlock Text="↑ sube  ↓ baja" FontSize="9" Foreground="#999"
                         VerticalAlignment="Center" Grid.Column="0"/>
              <TextBox x:Name="txtDesfaseBase" Text="0" Grid.Column="1"
                       Padding="4,3" BorderBrush="#BFBFBF" BorderThickness="1" Margin="4,0,0,0"/>
            </Grid>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Desfase superior (cm)" FontSize="10" Foreground="#555" Margin="0,0,0,4"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/><ColumnDefinition Width="65"/>
              </Grid.ColumnDefinitions>
              <TextBlock Text="↑ sube  ↓ baja" FontSize="9" Foreground="#999"
                         VerticalAlignment="Center" Grid.Column="0"/>
              <TextBox x:Name="txtDesfaseTop" Text="0" Grid.Column="1"
                       Padding="4,3" BorderBrush="#BFBFBF" BorderThickness="1" Margin="4,0,0,0"/>
            </Grid>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <Border Background="#FFF8E7" CornerRadius="6" Padding="10,8" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1">
      <TextBlock FontSize="10" Foreground="#555" TextWrapping="Wrap"
        Text="Selecciona una habitación existente. Se crea un acabado por cada segmento del contorno incluyendo las caras de las columnas."/>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="HABITACIÓN" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar" Content="Seleccionar habitación en Revit"
                Height="32" Cursor="Hand" Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador" Text="Ninguna habitación seleccionada."
                   Foreground="#999" FontSize="11" HorizontalAlignment="Center"
                   Margin="0,6,0,0" TextWrapping="Wrap"/>
      </StackPanel>
    </Border>

    <Grid>
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/><ColumnDefinition Width="10"/>
        <ColumnDefinition Width="2*"/>
      </Grid.ColumnDefinitions>
      <Button x:Name="btnCancelar" Grid.Column="0" Content="Cancelar"
              Height="34" Cursor="Hand" Background="#EEEEEE" Foreground="#555"
              BorderBrush="#BFBFBF" BorderThickness="1"/>
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear Acabados"
              Height="34" Cursor="Hand" Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>
  </StackPanel>
</Window>
"""

# ─────────────────────────────────────────────────────────────
# Formulario
# ─────────────────────────────────────────────────────────────
class FormHabitacion(object):
    def __init__(self):
        self.resultado    = None
        self.vertices     = []
        self.room_id      = None
        self.sep_ids      = []
        self.seg_elem_ids = []

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
        self.cbNivelBase.SelectedIndex = idx_nivel_vista
        self.cbNivelTop.SelectedIndex  = min(idx_nivel_vista+1, len(nombres_nivel)-1)

        self.win.FindName('btnSeleccionar').Click += self.OnSeleccionar
        self.win.FindName('btnCancelar').Click    += self.OnCancelar
        self.win.FindName('btnAceptar').Click     += self.OnAceptar

    def OnSeleccionar(self, sender, e):
        self.win.Hide()
        self.vertices = []
        try:
            ref  = uidoc.Selection.PickObject(ObjectType.Element,
                       FiltroHabitacion(), u'Selecciona la habitación')
            room = doc.GetElement(ref.ElementId)

            if not isinstance(room, Room):
                self.lblContador.Text = u'No es una habitación.'
                self.win.ShowDialog(); return

            area_p = room.get_Parameter(BuiltInParameter.ROOM_AREA)
            if not area_p or area_p.AsDouble() < 0.001:
                self.lblContador.Text = u'La habitación no tiene área.'
                self.win.ShowDialog(); return

            z                           = niveles_col[self.cbNivelBase.SelectedIndex].Elevation
            vertices, sep_ids, seg_eids = leer_vertices(room, z)

            if not vertices:
                self.lblContador.Text = u'No se pudieron leer los vértices.'
                self.win.ShowDialog(); return

            self.vertices     = vertices
            self.room_id      = room.Id
            self.sep_ids      = sep_ids
            self.seg_elem_ids = seg_eids

            nombre_p = room.get_Parameter(BuiltInParameter.ROOM_NAME)
            nombre   = nombre_p.AsString() if nombre_p else u'Sin nombre'
            num_p    = room.get_Parameter(BuiltInParameter.ROOM_NUMBER)
            numero   = num_p.AsString() if num_p else u''

            self.lblContador.Foreground = SW.Media.Brushes.DarkGreen
            self.lblContador.Text = u'Hab. {} {} — {} vértices detectados.'.format(
                numero, nombre, len(vertices))

        except Exception as ex:
            if 'Cancel' in str(ex) or 'Escape' in str(ex):
                self.lblContador.Text = u'Cancelado.'
            else:
                self.lblContador.Foreground = SW.Media.Brushes.Red
                self.lblContador.Text = u'Error: {}'.format(str(ex)[:150])
        self.win.ShowDialog()

    def OnAceptar(self, sender, e):
        if not self.vertices:
            SW.MessageBox.Show(u'Selecciona una habitación primero.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        try:
            dsf_base = float(self.txtDesfaseBase.Text.replace(',','.'))
            dsf_top  = float(self.txtDesfaseTop.Text.replace(',','.'))
        except ValueError:
            SW.MessageBox.Show(u'Los desfases deben ser números.',
                u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = {
            'tipo_nombre':     self.cbTipoMuro.SelectedItem,
            'nivel_base':      niveles_col[self.cbNivelBase.SelectedIndex],
            'nivel_top':       niveles_col[self.cbNivelTop.SelectedIndex],
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
form = FormHabitacion()
res  = form.show()
if res is None:
    import sys; sys.exit()

tipo_muro_obj   = tipos_muro[res['tipo_nombre']]
tipo_muro_id    = tipo_muro_obj.Id
nivel_base      = res['nivel_base']
nivel_top       = res['nivel_top']
desfase_base_ft = res['desfase_base_ft']
desfase_top_ft  = res['desfase_top_ft']
vertices        = form.vertices
seg_elem_ids    = form.seg_elem_ids

espesor_acabado_ft = mm_a_ft(0.0)
try:
    cp = tipo_muro_obj.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM)
    if cp: espesor_acabado_ft = cp.AsDouble()
except: pass

z_base_nivel = nivel_base.Elevation
z_top_nivel  = nivel_top.Elevation
altura_ft    = (z_top_nivel - z_base_nivel) + desfase_top_ft - desfase_base_ft
if altura_ft < mm_a_ft(100.0): altura_ft = mm_a_ft(3000.0)
z_arranque   = z_base_nivel + desfase_base_ft

# ─────────────────────────────────────────────────────────────
# Crear un muro de acabado por segmento
# ─────────────────────────────────────────────────────────────
semi = espesor_acabado_ft / 2.0

area_signo = 0.0
n = len(vertices)
for i in range(n):
    j = (i + 1) % n
    area_signo += vertices[i].X * vertices[j].Y
    area_signo -= vertices[j].X * vertices[i].Y
es_ccw = area_signo > 0

creados = errores = 0
detalle = []
muros_creados = []          # (acabado, base_elem_id)

with Transaction(doc, u'Acabados por Habitación') as t:
    t.Start()
    for i in range(n):
        try:
            v0 = vertices[i]
            v1 = vertices[(i+1) % n]
            if dist2d(v0, v1) < mm_a_ft(3.0):
                continue

            seg_dx = v1.X - v0.X
            seg_dy = v1.Y - v0.Y
            seg_lg = math.sqrt(seg_dx**2 + seg_dy**2)
            if es_ccw:
                nx, ny = -seg_dy / seg_lg,  seg_dx / seg_lg
            else:
                nx, ny =  seg_dy / seg_lg, -seg_dx / seg_lg

            p0 = XYZ(v0.X + nx * semi, v0.Y + ny * semi, z_arranque)
            p1 = XYZ(v1.X + nx * semi, v1.Y + ny * semi, z_arranque)

            muro = Wall.Create(doc, Line.CreateBound(p0, p1),
                               tipo_muro_id, nivel_base.Id,
                               altura_ft, 0.0, False, False)
            try:
                p = muro.get_Parameter(BuiltInParameter.WALL_BASE_OFFSET)
                if p and not p.IsReadOnly: p.Set(desfase_base_ft)
            except: pass
            try:
                p = muro.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE)
                if p and not p.IsReadOnly: p.Set(nivel_top.Id)
            except: pass
            try:
                p = muro.get_Parameter(BuiltInParameter.WALL_TOP_OFFSET)
                if p and not p.IsReadOnly: p.Set(desfase_top_ft)
            except: pass

            base_eid = seg_elem_ids[i] if i < len(seg_elem_ids) else None
            muros_creados.append((muro, base_eid))
            creados += 1
        except Exception as ex:
            detalle.append(u'Seg {}: {}'.format(i, str(ex)))
            errores += 1
    t.Commit()

# ─────────────────────────────────────────────────────────────
# Join: acabados entre sí y cada acabado con su muro base
# ─────────────────────────────────────────────────────────────
def intentar_join(a, b):
    try:
        if JoinGeometryUtils.AreElementsJoined(doc, a, b): return True
        JoinGeometryUtils.JoinGeometry(doc, a, b)
        return True
    except: return False

unidos = 0
muros_validos = [m for m, _ in muros_creados if m is not None]

if muros_validos:
    with Transaction(doc, u'Join Acabados') as t2:
        t2.Start()
        # Join entre acabados adyacentes
        for a in range(len(muros_validos)):
            for b in range(a+1, len(muros_validos)):
                if intentar_join(muros_validos[a], muros_validos[b]):
                    unidos += 1
        # Join cada acabado con su muro base
        for acabado, base_eid in muros_creados:
            if acabado is None or base_eid is None or base_eid.IntegerValue <= 0:
                continue
            base_elem = doc.GetElement(base_eid)
            if base_elem is None or not isinstance(base_elem, Wall):
                continue
            if intentar_join(acabado, base_elem):
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
SW.MessageBox.Show(msg, u'Resultado — Acabados por Habitación',
                   SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)
