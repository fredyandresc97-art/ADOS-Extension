# -*- coding: utf-8 -*-
"""
Acotado Automatico de Ejes v2
Elaborado por: Ing. Andres Angel  -  Ados Software
"""
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xml')

import System.Windows as SW
from System.Windows.Markup import XamlReader
from System.Xml import XmlReader
from System.IO import StringReader

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory,
    Transaction, SubTransaction,
    Line, XYZ, ReferenceArray, Reference,
    DimensionType, DimensionStyleType, ViewPlan, DatumExtentType, Grid
)
from Autodesk.Revit.UI import TaskDialog
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
view  = uidoc.ActiveView

# ─────────────────────────────────────────────────────────────
# Validar vista de planta
# ─────────────────────────────────────────────────────────────
if not isinstance(view, ViewPlan):
    TaskDialog.Show(u'Error',
        u'Esta herramienta solo funciona en vistas de planta.')
    import sys; sys.exit()

# ─────────────────────────────────────────────────────────────
# Primer tipo de cota LINEAL disponible
# ─────────────────────────────────────────────────────────────
dim_type = None
for _dt in FilteredElementCollector(doc).OfClass(DimensionType).ToElements():
    try:
        if _dt.StyleType == DimensionStyleType.Linear:
            dim_type = _dt
            break
    except: pass

if dim_type is None:
    TaskDialog.Show(u'Error',
        u'No se encontro un tipo de cota lineal en el proyecto.')
    import sys; sys.exit()

# ─────────────────────────────────────────────────────────────
# Filtro de seleccion: solo ejes
# ─────────────────────────────────────────────────────────────
class FiltroEjes(ISelectionFilter):
    def AllowElement(self, elem): return isinstance(elem, Grid)
    def AllowReference(self, ref, point): return True

# ─────────────────────────────────────────────────────────────
# Utilidades de geometria
# ─────────────────────────────────────────────────────────────
def curva_eje(grid):
    try:
        cs = grid.GetCurvesInView(DatumExtentType.ViewSpecific, view)
        if cs and cs.Count > 0: return cs[0]
    except: pass
    try:
        cs = grid.GetCurvesInView(DatumExtentType.Model, view)
        if cs and cs.Count > 0: return cs[0]
    except: pass
    return grid.Curve

def es_vertical(grid):
    c = curva_eje(grid)
    if c is None: return False
    p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
    return abs(p1.Y - p0.Y) >= abs(p1.X - p0.X)

def bbox(grid_list):
    xs, ys = [], []
    for g in grid_list:
        c = curva_eje(g)
        if c:
            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
            xs += [p0.X, p1.X]; ys += [p0.Y, p1.Y]
    return min(xs), max(xs), min(ys), max(ys)

# ─────────────────────────────────────────────────────────────
# XAML — identidad Ados
# ─────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acotado de Ejes"
    Width="460" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">
  <StackPanel Margin="14">

    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Acotado de Ejes"
                   FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Crea cotas en X e Y a partir de los ejes seleccionados  -  Ados Software"
                   FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <Border Background="#FFF8E7" CornerRadius="6" Padding="10,8" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1">
      <TextBlock FontSize="10" Foreground="#555" TextWrapping="Wrap"
        Text="Selecciona los ejes a acotar. El script separara automaticamente los ejes en X e Y y creara una cota por grupo, posicionada cerca del extremo de los ejes."/>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="EJES A ACOTAR" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar" Content="Seleccionar ejes en Revit"
                Height="32" Cursor="Hand" Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador" Text="Ningun eje seleccionado."
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
      <Button x:Name="btnAcotar" Grid.Column="2" Content="Crear Cotas"
              Height="34" Cursor="Hand" Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
</Window>
"""

# ─────────────────────────────────────────────────────────────
# Formulario
# ─────────────────────────────────────────────────────────────
class FormEjes(object):
    def __init__(self):
        self.resultado = None
        self.grids     = []

        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.lblContador = self.win.FindName('lblContador')

        self.win.FindName('btnSeleccionar').Click += self.OnSeleccionar
        self.win.FindName('btnCancelar').Click    += self.OnCancelar
        self.win.FindName('btnAcotar').Click      += self.OnAcotar

    def OnSeleccionar(self, sender, e):
        self.win.Hide()
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, FiltroEjes(),
                u'Selecciona los ejes a acotar (Enter para confirmar)')
            self.grids = [doc.GetElement(r.ElementId) for r in refs
                          if isinstance(doc.GetElement(r.ElementId), Grid)]

            if not self.grids:
                self.lblContador.Text = u'No se seleccionaron ejes.'
                self.lblContador.Foreground = SW.Media.Brushes.DarkRed
            else:
                n_v = sum(1 for g in self.grids if     es_vertical(g))
                n_h = sum(1 for g in self.grids if not es_vertical(g))
                self.lblContador.Foreground = SW.Media.Brushes.DarkGreen
                self.lblContador.Text = (
                    u'{} eje(s) seleccionado(s)  —  '
                    u'{} vertical(es)  |  {} horizontal(es)'.format(
                        len(self.grids), n_v, n_h))

        except Exception as ex:
            if 'Cancel' in str(ex) or 'Escape' in str(ex):
                self.lblContador.Text = u'Seleccion cancelada.'
            else:
                self.lblContador.Foreground = SW.Media.Brushes.DarkRed
                self.lblContador.Text = u'Error: {}'.format(str(ex)[:120])

        self.win.ShowDialog()

    def OnAcotar(self, sender, e):
        if not self.grids:
            SW.MessageBox.Show(u'Selecciona al menos un eje primero.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        grids_v = [g for g in self.grids if     es_vertical(g)]
        grids_h = [g for g in self.grids if not es_vertical(g)]
        if len(grids_v) < 2 and len(grids_h) < 2:
            SW.MessageBox.Show(
                u'Se necesitan al menos 2 ejes en la misma direccion para crear una cota.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = {'grids_v': grids_v, 'grids_h': grids_h}
        self.win.Close()

    def OnCancelar(self, sender, e):
        self.resultado = None
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.resultado

# ─────────────────────────────────────────────────────────────
# Ejecutar formulario
# ─────────────────────────────────────────────────────────────
form = FormEjes()
res  = form.show()
if res is None:
    import sys; sys.exit()

grids_v = sorted(res['grids_v'], key=lambda g: curva_eje(g).GetEndPoint(0).X)
grids_h = sorted(res['grids_h'], key=lambda g: curva_eje(g).GetEndPoint(0).Y)

# Offset proporcional a la escala de la vista (10 mm en papel)
scale = 100.0
try: scale = float(view.Scale)
except: pass
offset_ft = scale * -10.0 / 304.8
pad_ft    = scale * 5.0  / 304.8

z = 0.0
try:
    if hasattr(view, 'GenLevel') and view.GenLevel:
        z = view.GenLevel.Elevation
except: pass

# ─────────────────────────────────────────────────────────────
# Crear cotas
# ─────────────────────────────────────────────────────────────
creadas = 0
errores = []

with Transaction(doc, u'Acotado de Ejes') as t:
    t.Start()

    # Ejes verticales → cota horizontal, encima (Y_max + offset)
    if len(grids_v) >= 2:
        st = SubTransaction(doc)
        st.Start()
        try:
            x_min, x_max, y_min, y_max = bbox(grids_v)
            y_cota = y_max + offset_ft
            line = Line.CreateBound(XYZ(x_min - pad_ft, y_cota, z),
                                    XYZ(x_max + pad_ft, y_cota, z))
            refs = ReferenceArray()
            for g in grids_v: refs.Append(Reference(g))
            if dim_type: doc.Create.NewDimension(view, line, refs, dim_type)
            else:        doc.Create.NewDimension(view, line, refs)
            st.Commit(); creadas += 1
        except Exception as ex:
            st.RollBack()
            errores.append(u'Cotas X: {}'.format(str(ex)[:120]))

    # Ejes horizontales → cota vertical, a la izquierda (X_min - offset)
    if len(grids_h) >= 2:
        st = SubTransaction(doc)
        st.Start()
        try:
            x_min, x_max, y_min, y_max = bbox(grids_h)
            x_cota = x_min - offset_ft
            line = Line.CreateBound(XYZ(x_cota, y_min - pad_ft, z),
                                    XYZ(x_cota, y_max + pad_ft, z))
            refs = ReferenceArray()
            for g in grids_h: refs.Append(Reference(g))
            if dim_type: doc.Create.NewDimension(view, line, refs, dim_type)
            else:        doc.Create.NewDimension(view, line, refs)
            st.Commit(); creadas += 1
        except Exception as ex:
            st.RollBack()
            errores.append(u'Cotas Y: {}'.format(str(ex)[:120]))

    t.Commit()

# ─────────────────────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────────────────────
msg = (u'Cotas creadas : {}\n'
       u'Ejes en X     : {}\n'
       u'Ejes en Y     : {}').format(creadas, len(grids_v), len(grids_h))
if errores:
    msg += u'\n\nErrores:\n' + u'\n'.join(errores)

TaskDialog.Show(u'Acotado de Ejes', msg)
