# -*- coding: utf-8 -*-
"""
Flejes (Estribos) en Columnas — E1-E2-E1
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
    Transaction, XYZ, Line
)
from Autodesk.Revit.DB.Structure import (
    RebarBarType, RebarHookType, Rebar, RebarStyle, RebarHookOrientation
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

def mm_a_pies(mm): return mm / 304.8
def pies_a_mm(p):  return p * 304.8

class FiltroColumnas(ISelectionFilter):
    def AllowElement(self, elem):
        return (elem.Category is not None and
                elem.Category.Id.IntegerValue ==
                int(BuiltInCategory.OST_StructuralColumns))
    def AllowReference(self, ref, point): return False

def get_info_columna(col):
    tf    = col.GetTransform()
    eje_x = tf.BasisX; eje_y = tf.BasisY; eje_z = tf.BasisZ
    bb       = col.get_BoundingBox(None)
    ancho_mm = pies_a_mm(bb.Max.X - bb.Min.X)
    largo_mm = pies_a_mm(bb.Max.Y - bb.Min.Y)
    z_base   = bb.Min.Z
    cx = tf.Origin.X; cy = tf.Origin.Y
    p_alto = col.get_Parameter(BuiltInParameter.INSTANCE_LENGTH_PARAM)
    altura_mm = pies_a_mm(p_alto.AsDouble()) if (p_alto and p_alto.AsDouble() > 0) \
                else pies_a_mm(bb.Max.Z - bb.Min.Z)
    return cx, cy, z_base, ancho_mm, largo_mm, altura_mm, eje_x, eje_y, eje_z

def crear_grupo_estribos(doc, col, cx, cy, z_sem,
                         ancho_mm, largo_mm, rec_mm,
                         bar_type, hook_type,
                         eje_x, eje_y, eje_z,
                         num_barras, espaciado_mm, hacia_arriba=True):
    semi_a = mm_a_pies((ancho_mm - 2.0 * rec_mm) / 2.0)
    semi_l = mm_a_pies((largo_mm - 2.0 * rec_mm) / 2.0)
    c  = XYZ(cx, cy, z_sem)
    p0 = XYZ(c.X - eje_x.X*semi_a - eje_y.X*semi_l, c.Y - eje_x.Y*semi_a - eje_y.Y*semi_l, c.Z - eje_x.Z*semi_a - eje_y.Z*semi_l)
    p1 = XYZ(c.X + eje_x.X*semi_a - eje_y.X*semi_l, c.Y + eje_x.Y*semi_a - eje_y.Y*semi_l, c.Z + eje_x.Z*semi_a - eje_y.Z*semi_l)
    p2 = XYZ(c.X + eje_x.X*semi_a + eje_y.X*semi_l, c.Y + eje_x.Y*semi_a + eje_y.Y*semi_l, c.Z + eje_x.Z*semi_a + eje_y.Z*semi_l)
    p3 = XYZ(c.X - eje_x.X*semi_a + eje_y.X*semi_l, c.Y - eje_x.Y*semi_a + eje_y.Y*semi_l, c.Z - eje_x.Z*semi_a + eje_y.Z*semi_l)
    curvas = [Line.CreateBound(p0,p1), Line.CreateBound(p1,p2),
              Line.CreateBound(p2,p3), Line.CreateBound(p3,p0)]
    normal = eje_z if hacia_arriba else XYZ(-eje_z.X, -eje_z.Y, -eje_z.Z)
    rebar  = Rebar.CreateFromCurves(
        doc, RebarStyle.StirrupTie, bar_type,
        hook_type, hook_type, col, normal, curvas,
        RebarHookOrientation.Left, RebarHookOrientation.Right, True, True)
    if num_barras >= 2:
        rebar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            num_barras, mm_a_pies(espaciado_mm), True, True, True)
    return rebar

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

# ─── XAML limpio — sin DropShadow ni TextTransform ───────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Flejes en Columnas"
    Width="400" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">

  <ScrollViewer VerticalScrollBarVisibility="Auto">
  <StackPanel Margin="14">

    <!-- Encabezado -->
    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Flejes en Columnas" FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Instala flejes en columnas eligiendo la distribución --- Ados Software" FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <!-- Barra y recubrimiento -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#DCDCDC" BorderThickness="1">
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

    <!-- Offsets -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#DCDCDC" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="LONGITUD LIBRE" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,4"/>
        <TextBlock Foreground="#777" FontSize="11" Margin="0,0,0,8" TextWrapping="Wrap">
          Distancia desde la cara del elemento hasta el primer y último estribo.
        </TextBlock>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Offset inferior (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtOffsetInf" Text="1" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Offset superior (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtOffsetSup" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <!-- Distribución -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#DCDCDC" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="DISTRIBUCIÓN" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>

        <!-- Radio buttons modo -->
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

        <!-- Panel uniforme -->
        <StackPanel x:Name="panelUniforme">
          <TextBlock Foreground="#666" FontSize="11" Margin="0,0,0,8" TextWrapping="Wrap">
            Un solo espaciado constante a lo largo de toda la columna.
          </TextBlock>
          <TextBlock Text="Espaciado entre estribos (mm)" Foreground="#555" Margin="0,0,0,3"/>
          <TextBox x:Name="txtEspUni" Text="200" Height="28" Padding="6,4"
                   BorderBrush="#BDBDBD" BorderThickness="1"/>
        </StackPanel>

        <!-- Panel zonas (oculto por defecto) -->
        <StackPanel x:Name="panelZonas" Visibility="Collapsed">
          <TextBlock Foreground="#666" FontSize="11" Margin="0,0,0,10" TextWrapping="Wrap">
            Estribos más juntos en los nodos (inicio y fin) y más separados en la zona central.
          </TextBlock>

          <!-- E1 -->
          <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8" Margin="0,0,0,8"
                  BorderBrush="#F9B233" BorderThickness="1">
            <StackPanel>
              <TextBlock Text="ZONA  E1  —  Extremos" FontWeight="Bold"
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

          <!-- E2 -->
          <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8"
                  BorderBrush="#F9B233" BorderThickness="1">
            <StackPanel>
              <TextBlock Text="ZONA  E2  —  Central" FontWeight="Bold"
                         Foreground="#000000" Margin="0,0,0,6"/>
              <TextBlock Text="Espaciado máximo (mm)" Foreground="#555" Margin="0,0,0,3"/>
              <TextBox x:Name="txtEspCen" Text="200" Height="28" Padding="6,4"
                       BorderBrush="#BDBDBD" BorderThickness="1"/>
            </StackPanel>
          </Border>
        </StackPanel>

      </StackPanel>
    </Border>

    <!-- Selección columnas -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="COLUMNAS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar columnas en Revit"
                Height="32" Cursor="Hand"
                Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador"
                   Text="Ninguna columna seleccionada"
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
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear estribos"
              Height="34" Cursor="Hand"
              Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
  </ScrollViewer>
</Window>
"""

# ─── Clase formulario ─────────────────────────────────────────────────────────
class FormFlejes(object):
    def __init__(self):
        self.resultado    = None
        self.columnas_ids = []
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
                ObjectType.Element, FiltroColumnas(),
                'Selecciona columnas y presiona ENTER')
            self.columnas_ids = [r.ElementId for r in refs]
            n = len(self.columnas_ids)
            self.lblContador.Text       = '{} columna{} seleccionada{}'.format(
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
            SW.MessageBox.Show(
                'Verifica los campos numericos.\n\n' + str(ex),
                'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        if not self.columnas_ids:
            SW.MessageBox.Show(
                'Selecciona al menos una columna antes de continuar.',
                'Sin columnas', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
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
offset_inf_mm    = res['offset_inf']
offset_sup_mm    = res['offset_sup']
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
columnas_seleccionadas = form.columnas_ids

# ─── Transacción ──────────────────────────────────────────────────────────────
total_grupos = 0

with Transaction(doc, 'Flejes en columnas') as t:
    t.Start()
    for eid in columnas_seleccionadas:
        col = doc.GetElement(eid)
        try:
            cx, cy, z_base, ancho_mm, largo_mm, altura_mm, eje_x, eje_y, eje_z = \
                get_info_columna(col)
        except Exception:
            continue

        longitud_libre_mm = altura_mm - offset_inf_mm - offset_sup_mm
        if longitud_libre_mm <= 0: continue

        z_ini_libre = z_base + mm_a_pies(offset_inf_mm)
        z_fin_libre = z_base + mm_a_pies(altura_mm - offset_sup_mm)

        try:
            if not modo_zonas:
                N, esp = calcular_N_y_espaciado(longitud_libre_mm, esp_uni_mm)
                if N < 2: continue
                crear_grupo_estribos(doc, col, cx, cy, z_ini_libre,
                    ancho_mm, largo_mm, recubrimiento_mm,
                    bar_type, hook_type, eje_x, eje_y, eje_z,
                    N, esp, hacia_arriba=True)
                total_grupos += 1
            else:
                zona_inf_mm  = esp_ext_mm * (n_ext - 1)
                if zona_inf_mm > longitud_libre_mm * 0.45:
                    zona_inf_mm = longitud_libre_mm * 0.45
                esp_ext_real = zona_inf_mm / (n_ext - 1) if n_ext > 1 else esp_ext_mm

                crear_grupo_estribos(doc, col, cx, cy, z_ini_libre,
                    ancho_mm, largo_mm, recubrimiento_mm,
                    bar_type, hook_type, eje_x, eje_y, eje_z,
                    n_ext, esp_ext_real, hacia_arriba=True)
                total_grupos += 1

                crear_grupo_estribos(doc, col, cx, cy, z_fin_libre,
                    ancho_mm, largo_mm, recubrimiento_mm,
                    bar_type, hook_type, eje_x, eje_y, eje_z,
                    n_ext, esp_ext_real, hacia_arriba=False)
                total_grupos += 1

                z_ult_e1_inf = z_ini_libre + mm_a_pies(zona_inf_mm)
                z_pri_e1_sup = z_fin_libre - mm_a_pies(zona_inf_mm)
                z_ini_e2     = z_ult_e1_inf + mm_a_pies(esp_cen_mm)
                z_fin_e2     = z_pri_e1_sup - mm_a_pies(esp_cen_mm)
                long_cen_mm  = pies_a_mm(z_fin_e2 - z_ini_e2)

                if long_cen_mm >= 0:
                    if long_cen_mm < 1.0:
                        crear_grupo_estribos(doc, col, cx, cy, (z_ini_e2+z_fin_e2)/2.0,
                            ancho_mm, largo_mm, recubrimiento_mm,
                            bar_type, hook_type, eje_x, eje_y, eje_z,
                            1, esp_cen_mm, hacia_arriba=True)
                        total_grupos += 1
                    else:
                        N_c, esp_c = calcular_N_y_espaciado(long_cen_mm, esp_cen_mm)
                        if N_c >= 2:
                            crear_grupo_estribos(doc, col, cx, cy, z_ini_e2,
                                ancho_mm, largo_mm, recubrimiento_mm,
                                bar_type, hook_type, eje_x, eje_y, eje_z,
                                N_c, esp_c, hacia_arriba=True)
                            total_grupos += 1
        except Exception:
            continue
    t.Commit()

modo_txt = 'E1-E2-E1' if modo_zonas else 'Uniforme'
SW.MessageBox.Show(
    'Se crearon {} grupo(s) de estribos\nen {} columna(s)\nDistribucion: {}'.format(
        total_grupos, len(columnas_seleccionadas), modo_txt),
    'Listo', SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)
