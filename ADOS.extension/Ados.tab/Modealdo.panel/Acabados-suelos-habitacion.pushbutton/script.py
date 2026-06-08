# -*- coding: utf-8 -*-
"""
Acabados de Suelos — Por Habitación v1
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
import System.Windows as SW
from System.Windows.Markup import XamlReader
from System.Xml import XmlReader
from System.IO import StringReader
from System.Collections.Generic import List as CsList

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInParameter,
    Transaction, XYZ, Line, Floor, FloorType, Level,
    SpatialElementBoundaryOptions, SpatialElementBoundaryLocation,
    CurveLoop, CurveArray
)
from Autodesk.Revit.DB.Architecture import Room
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
view  = uidoc.ActiveView

def mm_a_ft(mm): return mm / 304.8
def cm_a_ft(cm): return cm / 30.48
def dist2d(a, b): return math.sqrt((a.X - b.X)**2 + (a.Y - b.Y)**2)

# ─────────────────────────────────────────────────────────────
# Tipos de suelo
# ─────────────────────────────────────────────────────────────
tipos_suelo = {}
for _ft in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
    _p = _ft.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
    if _p:
        _n = _p.AsString()
        if _n: tipos_suelo[_n] = _ft

if not tipos_suelo:
    SW.MessageBox.Show(u'No se encontraron tipos de suelo.', u'Error',
        SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

nombres_suelo = sorted(tipos_suelo.keys())

# ─────────────────────────────────────────────────────────────
# Niveles
# ─────────────────────────────────────────────────────────────
niveles_col   = sorted(FilteredElementCollector(doc).OfClass(Level).ToElements(),
                       key=lambda lv: lv.Elevation)
nombres_nivel = [lv.Name for lv in niveles_col]

if not nombres_nivel:
    SW.MessageBox.Show(u'No se encontraron niveles.', u'Error',
        SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

idx_nivel_vista = 0
try:
    if hasattr(view, 'GenLevel') and view.GenLevel:
        for _i, _lv in enumerate(niveles_col):
            if _lv.Id == view.GenLevel.Id:
                idx_nivel_vista = _i; break
except: pass

# ─────────────────────────────────────────────────────────────
# Filtro selección
# ─────────────────────────────────────────────────────────────
class FiltroHabitacion(ISelectionFilter):
    def AllowElement(self, elem): return isinstance(elem, Room)
    def AllowReference(self, ref, point): return True

# ─────────────────────────────────────────────────────────────
# Leer vértices del contorno (Z=0)
# ─────────────────────────────────────────────────────────────
def leer_vertices_room(room):
    opts = SpatialElementBoundaryOptions()
    opts.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    boundaries = room.GetBoundarySegments(opts)
    if not boundaries: return []
    verts = []
    for loop in boundaries:
        for seg in loop:
            try:
                p = seg.GetCurve().GetEndPoint(0)
                verts.append(XYZ(p.X, p.Y, 0.0))
            except: pass
        break
    return verts

# ─────────────────────────────────────────────────────────────
# Offset de polígono: + adentro, - afuera
# Usa normales internas por arista y desplaza cada vértice
# a lo largo del bisector de los dos segmentos adyacentes.
# ─────────────────────────────────────────────────────────────
def offset_poligono(verts, d):
    n = len(verts)
    if n < 3 or abs(d) < mm_a_ft(0.5): return verts

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += verts[i].X * verts[j].Y - verts[j].X * verts[i].Y
    ccw = area > 0

    enx, eny = [], []
    for i in range(n):
        j = (i + 1) % n
        dx = verts[j].X - verts[i].X
        dy = verts[j].Y - verts[i].Y
        lg = math.sqrt(dx*dx + dy*dy)
        if lg < 1e-10: enx.append(0.0); eny.append(0.0); continue
        if ccw:  enx.append(-dy/lg); eny.append( dx/lg)
        else:    enx.append( dy/lg); eny.append(-dx/lg)

    out = []
    for i in range(n):
        p = (i - 1) % n
        bx = enx[p] + enx[i]
        by = eny[p] + eny[i]
        bl = math.sqrt(bx*bx + by*by)
        if bl < 1e-8: bx, by = enx[i], eny[i]; bl = 1.0
        else: bx /= bl; by /= bl
        dot = bx * enx[i] + by * eny[i]
        if abs(dot) < 0.01: dot = 0.01
        scale = d / dot
        v = verts[i]
        out.append(XYZ(v.X + bx*scale, v.Y + by*scale, 0.0))
    return out

# ─────────────────────────────────────────────────────────────
# Construir CurveLoop desde lista de vértices
# ─────────────────────────────────────────────────────────────
def construir_loop(verts):
    # Elimina vértices demasiado cercanos al anterior
    if len(verts) < 3: return None
    clean = [verts[0]]
    for v in verts[1:]:
        if dist2d(clean[-1], v) > mm_a_ft(1.0):
            clean.append(v)
    while len(clean) > 3 and dist2d(clean[-1], clean[0]) <= mm_a_ft(1.0):
        clean.pop()
    if len(clean) < 3: return None

    cl = CurveLoop()
    n = len(clean)
    for i in range(n):
        cl.Append(Line.CreateBound(clean[i], clean[(i+1) % n]))
    return cl

# ─────────────────────────────────────────────────────────────
# XAML
# ─────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acabados de Suelos por Habitacion"
    Width="480" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">
  <StackPanel Margin="14">

    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Acabados de Suelos - Por Habitacion"
                   FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Crea suelos a partir del contorno de una habitacion  -  Ados Software"
                   FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="TIPO DE SUELO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbTipoSuelo" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="NIVEL" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbNivel" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

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
            <TextBlock Text="Altura desde nivel (cm)" FontSize="10" Foreground="#555" Margin="0,0,0,4"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="65"/>
              </Grid.ColumnDefinitions>
              <TextBlock Text="+ sube  - baja" FontSize="9" Foreground="#999"
                         VerticalAlignment="Center" Grid.Column="0"/>
              <TextBox x:Name="txtDesfaseV" Text="0" Grid.Column="1"
                       Padding="4,3" BorderBrush="#BFBFBF" BorderThickness="1" Margin="4,0,0,0"/>
            </Grid>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Horizontal (cm)" FontSize="10" Foreground="#555" Margin="0,0,0,4"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="65"/>
              </Grid.ColumnDefinitions>
              <TextBlock Text="+ adentro  - afuera" FontSize="9" Foreground="#999"
                         VerticalAlignment="Center" Grid.Column="0"/>
              <TextBox x:Name="txtDesfaseH" Text="0" Grid.Column="1"
                       Padding="4,3" BorderBrush="#BFBFBF" BorderThickness="1" Margin="4,0,0,0"/>
            </Grid>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <Border Background="#FFF8E7" CornerRadius="6" Padding="10,8" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1">
      <TextBlock FontSize="10" Foreground="#555" TextWrapping="Wrap"
        Text="Selecciona una habitacion. El suelo seguira el contorno con los desfases indicados."/>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="HABITACION" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar" Content="Seleccionar habitacion en Revit"
                Height="32" Cursor="Hand" Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador" Text="Ninguna habitacion seleccionada."
                   Foreground="#999" FontSize="11" HorizontalAlignment="Center"
                   Margin="0,6,0,0" TextWrapping="Wrap"/>
      </StackPanel>
    </Border>

    <Grid>
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="10"/>
        <ColumnDefinition Width="2*"/>
      </Grid.ColumnDefinitions>
      <Button x:Name="btnCancelar" Grid.Column="0" Content="Cancelar"
              Height="34" Cursor="Hand" Background="#EEEEEE" Foreground="#555"
              BorderBrush="#BFBFBF" BorderThickness="1"/>
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear Suelo"
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
        self.resultado = None
        self.vertices  = []

        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.cbTipoSuelo = self.win.FindName('cbTipoSuelo')
        self.cbNivel     = self.win.FindName('cbNivel')
        self.txtDesfaseV = self.win.FindName('txtDesfaseV')
        self.txtDesfaseH = self.win.FindName('txtDesfaseH')
        self.lblContador = self.win.FindName('lblContador')

        for n in nombres_suelo:
            self.cbTipoSuelo.Items.Add(n)
        self.cbTipoSuelo.SelectedIndex = 0

        for n in nombres_nivel:
            self.cbNivel.Items.Add(n)
        self.cbNivel.SelectedIndex = idx_nivel_vista

        self.win.FindName('btnSeleccionar').Click += self.OnSeleccionar
        self.win.FindName('btnCancelar').Click    += self.OnCancelar
        self.win.FindName('btnAceptar').Click     += self.OnAceptar

    def OnSeleccionar(self, sender, e):
        self.win.Hide()
        self.vertices = []
        try:
            ref  = uidoc.Selection.PickObject(ObjectType.Element,
                       FiltroHabitacion(), u'Selecciona la habitacion')
            room = doc.GetElement(ref.ElementId)

            if not isinstance(room, Room):
                self.lblContador.Text = u'No es una habitacion.'
                self.win.ShowDialog(); return

            area_p = room.get_Parameter(BuiltInParameter.ROOM_AREA)
            if not area_p or area_p.AsDouble() < 0.001:
                self.lblContador.Text = u'La habitacion no tiene area.'
                self.win.ShowDialog(); return

            verts = leer_vertices_room(room)
            if len(verts) < 3:
                self.lblContador.Text = u'Contorno insuficiente.'
                self.win.ShowDialog(); return

            self.vertices = verts

            nombre_p = room.get_Parameter(BuiltInParameter.ROOM_NAME)
            nombre   = nombre_p.AsString() if nombre_p else u'Sin nombre'
            num_p    = room.get_Parameter(BuiltInParameter.ROOM_NUMBER)
            numero   = num_p.AsString() if num_p else u''

            self.lblContador.Foreground = SW.Media.Brushes.DarkGreen
            self.lblContador.Text = u'Hab. {} {} - {} vertices detectados.'.format(
                numero, nombre, len(verts))

        except Exception as ex:
            if 'Cancel' in str(ex) or 'Escape' in str(ex):
                self.lblContador.Text = u'Cancelado.'
            else:
                self.lblContador.Foreground = SW.Media.Brushes.Red
                self.lblContador.Text = u'Error: {}'.format(str(ex)[:150])
        self.win.ShowDialog()

    def OnAceptar(self, sender, e):
        if not self.vertices:
            SW.MessageBox.Show(u'Selecciona una habitacion primero.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        try:
            dsf_v = float(self.txtDesfaseV.Text.replace(',', '.'))
            dsf_h = float(self.txtDesfaseH.Text.replace(',', '.'))
        except ValueError:
            SW.MessageBox.Show(u'Los desfases deben ser numeros.',
                u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = {
            'tipo_nombre': self.cbTipoSuelo.SelectedItem,
            'nivel':       niveles_col[self.cbNivel.SelectedIndex],
            'dsf_v_ft':    cm_a_ft(dsf_v),
            'dsf_h_ft':    cm_a_ft(dsf_h),
        }
        self.win.Close()

    def OnCancelar(self, sender, e):
        self.resultado = None
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.resultado

# ─────────────────────────────────────────────────────────────
# Ejecutar
# ─────────────────────────────────────────────────────────────
form = FormHabitacion()
res  = form.show()
if res is None:
    import sys; sys.exit()

tipo_suelo = tipos_suelo[res['tipo_nombre']]
nivel      = res['nivel']
dsf_v_ft   = res['dsf_v_ft']
dsf_h_ft   = res['dsf_h_ft']
vertices   = form.vertices

# Aplicar desfase horizontal
verts_off = offset_poligono(vertices, dsf_h_ft)
loop      = construir_loop(verts_off)

if loop is None:
    SW.MessageBox.Show(u'No se pudo construir el contorno del suelo.',
        u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

# ─────────────────────────────────────────────────────────────
# Crear suelo
# ─────────────────────────────────────────────────────────────
creado    = False
error_msg = u''

try:
    with Transaction(doc, u'Acabado de Suelo por Habitacion') as t:
        t.Start()

        floor = None
        # Revit 2022+ API
        try:
            loops_list = CsList[CurveLoop]()
            loops_list.Add(loop)
            floor = Floor.Create(doc, loops_list, tipo_suelo.Id, nivel.Id)
        except Exception:
            # Fallback Revit < 2022
            arr = CurveArray()
            enum = loop.GetEnumerator()
            while enum.MoveNext():
                arr.Append(enum.Current)
            floor = doc.Create.NewFloor(arr, tipo_suelo, nivel, False)

        if floor is not None and abs(dsf_v_ft) > mm_a_ft(0.1):
            p = floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
            if p and not p.IsReadOnly:
                p.Set(dsf_v_ft)

        t.Commit()
        creado = True

except Exception as ex:
    error_msg = str(ex)

# ─────────────────────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────────────────────
if creado:
    SW.MessageBox.Show(u'Suelo creado correctamente.', u'Resultado',
                       SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)
else:
    SW.MessageBox.Show(u'Error al crear el suelo:\n{}'.format(error_msg),
                       u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
