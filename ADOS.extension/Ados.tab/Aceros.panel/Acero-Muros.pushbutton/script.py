# -*- coding: utf-8 -*-
# Acero de Refuerzo en Muros — Un solo archivo con ventana WPF incrustada.
# Ganchos independientes por dirección (H: uno compartido; V: superior e inferior).
# Acero creado de forma GRUPAL con SetLayoutAsNumberWithSpacing.
# Rotación de ganchos: H-Cara1 → 180°; V-Cara2 superior e inferior → 180°.
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

# ─── Conversiones ─────────────────────────────────────────────────────────────
def mm_a_pies(mm): return mm / 304.8
def pies_a_mm(p):  return p * 304.8
def cm_a_pies(cm): return cm / 30.48

# ─── Filtro de selección: solo muros ──────────────────────────────────────────
class FiltroMuros(ISelectionFilter):
    def AllowElement(self, elem):
        return (elem.Category is not None and
                elem.Category.Id.IntegerValue == int(BuiltInCategory.OST_Walls))
    def AllowReference(self, ref, point):
        return False

# ─── Geometría del muro ───────────────────────────────────────────────────────
def get_info_muro(muro):
    """Devuelve (longitud_mm, altura_mm, espesor_mm, eje_largo, eje_normal, origen)."""
    p_long = muro.get_Parameter(BuiltInParameter.CURVE_ELEM_LENGTH)
    p_alto = muro.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM)
    p_esp  = muro.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM)

    longitud_mm = pies_a_mm(p_long.AsDouble()) if p_long else 0.0
    altura_mm   = pies_a_mm(p_alto.AsDouble()) if p_alto else 0.0
    espesor_mm  = pies_a_mm(p_esp.AsDouble())  if p_esp  else 0.0

    loc   = muro.Location.Curve
    p_ini = loc.GetEndPoint(0)
    p_fin = loc.GetEndPoint(1)
    eje_largo  = (p_fin - p_ini).Normalize()
    eje_normal = XYZ(0, 0, 1).CrossProduct(eje_largo).Normalize()

    bb     = muro.get_BoundingBox(None)
    origen = XYZ(p_ini.X, p_ini.Y, bb.Min.Z)

    if longitud_mm < 1.0: longitud_mm = pies_a_mm(bb.Max.X - bb.Min.X)
    if altura_mm   < 1.0: altura_mm   = pies_a_mm(bb.Max.Z - bb.Min.Z)
    if espesor_mm  < 1.0: espesor_mm  = pies_a_mm(bb.Max.Y - bb.Min.Y)

    return longitud_mm, altura_mm, espesor_mm, eje_largo, eje_normal, origen

# ─── Distribución de barras ───────────────────────────────────────────────────
def calcular_grupo(longitud_mm, recubrimiento_mm, diametro_mm, espaciado_max_mm):
    """Devuelve (n_barras, espaciado_real_ft, offset_inicio_ft)."""
    zona_mm = longitud_mm - 2.0 * recubrimiento_mm - diametro_mm
    if zona_mm <= 0:
        return 1, 0.0, mm_a_pies(recubrimiento_mm + diametro_mm / 2.0)
    n_espacios = max(1, int(math.floor(zona_mm / espaciado_max_mm)))
    esp_real   = zona_mm / n_espacios
    n_barras   = n_espacios + 1
    offset_ini = recubrimiento_mm + diametro_mm / 2.0
    return n_barras, mm_a_pies(esp_real), mm_a_pies(offset_ini)

# ─── Rotación de ganchos ──────────────────────────────────────────────────────
def rotar_ganchos(rebar, ang_inicio_rad, ang_final_rad):
    """Aplica rotación (radianes) a los ganchos de inicio y/o fin.
    Pasa None para no tocar ese extremo.
    Nombres en español (modelo en español); ajustar si el modelo está en otro idioma.
    """
    for p in rebar.Parameters:
        nombre = p.Definition.Name
        if not p.IsReadOnly:
            if ang_inicio_rad is not None and nombre == 'Rotacion del gancho al inicio':
                p.Set(ang_inicio_rad)
            if ang_final_rad is not None and nombre == 'Rotacion del gancho al final':
                p.Set(ang_final_rad)

# ─── Recopilar tipos de barra y gancho ───────────────────────────────────────
barra_tipos = FilteredElementCollector(doc).OfClass(RebarBarType).ToElements()
diametros       = {}
diametros_mm_map = {}
for bt in barra_tipos:
    nombre = bt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    diametros[nombre] = bt.Id
    dp = bt.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER)
    if dp: diametros_mm_map[nombre] = pies_a_mm(dp.AsDouble())

if not diametros:
    SW.MessageBox.Show('No se encontraron tipos de barra en el archivo.',
                       'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

gancho_tipos = FilteredElementCollector(doc).OfClass(RebarHookType).ToElements()
ganchos = {'Sin gancho': None}
for gt in gancho_tipos:
    nombre = gt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    ganchos[nombre] = gt.Id

nombres_diametros = sorted(diametros.keys())
nombres_ganchos   = ['Sin gancho'] + sorted(k for k in ganchos.keys() if k != 'Sin gancho')

# ─── Valores por defecto ──────────────────────────────────────────────────────
DEF_DIAM   = '13M'
DEF_GANCHO = 'Sin gancho'

# ─── XAML ─────────────────────────────────────────────────────────────────────
XAML_VENTANA = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acero de Refuerzo en Muros"
    Width="500" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">

  <Window.Resources>
    <Style x:Key="BotonAdos" TargetType="Button">
      <Setter Property="FontWeight" Value="Bold"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Style.Triggers>
        <Trigger Property="IsMouseOver" Value="True">
          <Setter Property="Background" Value="#D7D7D7"/>
        </Trigger>
        <Trigger Property="IsPressed" Value="True">
          <Setter Property="Background" Value="#BDBDBD"/>
        </Trigger>
      </Style.Triggers>
    </Style>
  </Window.Resources>

  <ScrollViewer VerticalScrollBarVisibility="Auto" MaxHeight="700">
  <StackPanel Margin="14">

    <!-- Encabezado -->
    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,10">
      <StackPanel>
        <TextBlock Text="Acero de Refuerzo en Muros" FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Armado horizontal y vertical en muros --- Ados Software" FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <!-- Recubrimiento + Modo de armado (un solo box) -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#DCDCDC" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="Recubrimiento" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,6"/>
        <Grid Margin="0,0,0,12">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="8"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Recubrimiento (mm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtRecub" Text="30" Height="28" Padding="6,4"
                     BorderBrush="#DCDCDC" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Desfase inferior (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtDesfaseInf" Text="25" Height="28" Padding="6,4"
                     BorderBrush="#DCDCDC" BorderThickness="1"/>
          </StackPanel>
        </Grid>
        <TextBlock Text="MODO DE ARMADO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,6"/>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="8"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <Border Grid.Column="0" CornerRadius="4" BorderBrush="#DCDCDC" BorderThickness="1" Padding="4,2">
            <RadioButton x:Name="rbUnaCara" Content="Una Cara / Eje" GroupName="modo"
                         IsChecked="False" Padding="4,4" FontWeight="SemiBold"
                         HorizontalAlignment="Center"/>
          </Border>
          <Border Grid.Column="2" CornerRadius="4" BorderBrush="#DCDCDC" BorderThickness="1" Padding="4,2">
            <RadioButton x:Name="rbDosCaras" Content="Dos Caras" GroupName="modo"
                         IsChecked="True" Padding="4,4" FontWeight="SemiBold"
                         HorizontalAlignment="Center"/>
          </Border>
        </Grid>
      </StackPanel>
    </Border>

    <!-- ══════════ CARA 1 ══════════ -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1">
      <StackPanel>
        <TextBlock x:Name="lblCara1" Text="CARA 1  —  Cara exterior (normal -)"
                   FontSize="10" FontWeight="Bold" Foreground="#000000" Margin="0,0,0,8"/>

        <!-- Horizontal Cara 1 -->
        <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8" Margin="0,0,0,8"
                BorderBrush="#F9B233" BorderThickness="1">
          <StackPanel>
            <TextBlock Text="HORIZONTAL  —  a lo largo del muro" FontWeight="SemiBold"
                       Foreground="#000000" Margin="0,0,0,8"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
              </Grid.ColumnDefinitions>
              <StackPanel Grid.Column="0">
                <TextBlock Text="Diametro" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbDiamH1" Height="28" Padding="4,0"/>
              </StackPanel>
              <StackPanel Grid.Column="2">
                <TextBlock Text="Espaciado max. (mm)" Foreground="#555" Margin="0,0,0,3"/>
                <TextBox x:Name="txtEspH1" Text="200" Height="28" Padding="6,4"
                         BorderBrush="#DCDCDC" BorderThickness="1"/>
              </StackPanel>
              <StackPanel Grid.Column="4">
                <TextBlock Text="Forma de Gancho" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbGanchoH1" Height="28" Padding="4,0"/>
              </StackPanel>
            </Grid>
          </StackPanel>
        </Border>

        <!-- Vertical Cara 1 -->
        <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8"
                BorderBrush="#F9B233" BorderThickness="1">
          <StackPanel>
            <TextBlock Text="VERTICAL  —  a lo alto del muro" FontWeight="SemiBold"
                       Foreground="#000000" Margin="0,0,0,8"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
              </Grid.ColumnDefinitions>
              <StackPanel Grid.Column="0">
                <TextBlock Text="Diametro" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbDiamV1" Height="28" Padding="4,0"/>
              </StackPanel>
              <StackPanel Grid.Column="2">
                <TextBlock Text="Espaciado max. (mm)" Foreground="#555" Margin="0,0,0,3"/>
                <TextBox x:Name="txtEspV1" Text="200" Height="28" Padding="6,4"
                         BorderBrush="#DCDCDC" BorderThickness="1"/>
              </StackPanel>
            </Grid>
            <Grid Margin="0,8,0,0">
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
              </Grid.ColumnDefinitions>
              <StackPanel Grid.Column="0">
                <TextBlock Text="Gancho superior" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbGanchoV1Sup" Height="28" Padding="4,0"/>
              </StackPanel>
              <StackPanel Grid.Column="2">
                <TextBlock Text="Gancho inferior" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbGanchoV1Inf" Height="28" Padding="4,0"/>
              </StackPanel>
            </Grid>
          </StackPanel>
        </Border>

      </StackPanel>
    </Border>

    <!-- ══════════ CARA 2 ══════════ -->
    <Border x:Name="panelCara2" Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="CARA 2  —  Cara interior (normal +)" FontSize="10"
                   FontWeight="Bold" Foreground="#000000" Margin="0,0,0,8"/>

        <!-- Horizontal Cara 2 -->
        <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8" Margin="0,0,0,8"
                BorderBrush="#F9B233" BorderThickness="1">
          <StackPanel>
            <TextBlock Text="HORIZONTAL  —  a lo largo del muro" FontWeight="SemiBold"
                       Foreground="#000000" Margin="0,0,0,8"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
              </Grid.ColumnDefinitions>
              <StackPanel Grid.Column="0">
                <TextBlock Text="Diametro" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbDiamH2" Height="28" Padding="4,0"/>
              </StackPanel>
              <StackPanel Grid.Column="2">
                <TextBlock Text="Espaciado max. (mm)" Foreground="#555" Margin="0,0,0,3"/>
                <TextBox x:Name="txtEspH2" Text="200" Height="28" Padding="6,4"
                         BorderBrush="#DCDCDC" BorderThickness="1"/>
              </StackPanel>
              <StackPanel Grid.Column="4">
                <TextBlock Text="Forma de Gancho" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbGanchoH2" Height="28" Padding="4,0"/>
              </StackPanel>
            </Grid>
          </StackPanel>
        </Border>

        <!-- Vertical Cara 2 -->
        <Border Background="#FFFBF3" CornerRadius="4" Padding="10,8"
                BorderBrush="#F9B233" BorderThickness="1">
          <StackPanel>
            <TextBlock Text="VERTICAL  —  a lo alto del muro" FontWeight="SemiBold"
                       Foreground="#000000" Margin="0,0,0,8"/>
            <Grid>
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
              </Grid.ColumnDefinitions>
              <StackPanel Grid.Column="0">
                <TextBlock Text="Diametro" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbDiamV2" Height="28" Padding="4,0"/>
              </StackPanel>
              <StackPanel Grid.Column="2">
                <TextBlock Text="Espaciado max. (mm)" Foreground="#555" Margin="0,0,0,3"/>
                <TextBox x:Name="txtEspV2" Text="200" Height="28" Padding="6,4"
                         BorderBrush="#DCDCDC" BorderThickness="1"/>
              </StackPanel>
            </Grid>
            <Grid Margin="0,8,0,0">
              <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="8"/>
                <ColumnDefinition Width="*"/>
              </Grid.ColumnDefinitions>
              <StackPanel Grid.Column="0">
                <TextBlock Text="Gancho superior" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbGanchoV2Sup" Height="28" Padding="4,0"/>
              </StackPanel>
              <StackPanel Grid.Column="2">
                <TextBlock Text="Gancho inferior" Foreground="#555" Margin="0,0,0,3"/>
                <ComboBox x:Name="cbGanchoV2Inf" Height="28" Padding="4,0"/>
              </StackPanel>
            </Grid>
          </StackPanel>
        </Border>

      </StackPanel>
    </Border>

    <!-- Selección de muros -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,10"
            BorderBrush="#F9B233" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="MUROS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar muro en Revit"
                Height="32" Style="{StaticResource BotonAdos}"
                Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador"
                   Text="Ningun muro seleccionado"
                   Foreground="#999" FontSize="11"
                   HorizontalAlignment="Center" Margin="0,6,0,0"/>
      </StackPanel>
    </Border>

    <!-- Botones -->
    <Grid Margin="0,0,0,4">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="10"/>
        <ColumnDefinition Width="2*"/>
      </Grid.ColumnDefinitions>
      <Button x:Name="btnCancelar" Grid.Column="0" Content="Cancelar"
              Height="34" Style="{StaticResource BotonAdos}"
              Background="#EEEEEE" Foreground="#555"
              BorderBrush="#BFBFBF" BorderThickness="1"/>
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear acero"
              Height="34" Style="{StaticResource BotonAdos}"
              Background="#F9B233" Foreground="Black"
              BorderThickness="0"/>
    </Grid>

  </StackPanel>
  </ScrollViewer>
</Window>
"""

# ─── Clase formulario WPF ─────────────────────────────────────────────────────
class FormMuros(object):
    def __init__(self):
        self.resultado = None
        self.muros_ids = []

        reader   = XmlReader.Create(StringReader(XAML_VENTANA))
        self.win = XamlReader.Load(reader)

        # Controles
        self.txtRecub      = self.win.FindName('txtRecub')
        self.txtDesfaseInf = self.win.FindName('txtDesfaseInf')
        self.rbUnaCara     = self.win.FindName('rbUnaCara')
        self.rbDosCaras    = self.win.FindName('rbDosCaras')
        self.panelCara2    = self.win.FindName('panelCara2')
        self.lblCara1      = self.win.FindName('lblCara1')
        # Cara 1
        self.cbDiamH1      = self.win.FindName('cbDiamH1')
        self.txtEspH1      = self.win.FindName('txtEspH1')
        self.cbGanchoH1    = self.win.FindName('cbGanchoH1')
        self.cbDiamV1      = self.win.FindName('cbDiamV1')
        self.txtEspV1      = self.win.FindName('txtEspV1')
        self.cbGanchoV1Sup = self.win.FindName('cbGanchoV1Sup')
        self.cbGanchoV1Inf = self.win.FindName('cbGanchoV1Inf')
        # Cara 2
        self.cbDiamH2      = self.win.FindName('cbDiamH2')
        self.txtEspH2      = self.win.FindName('txtEspH2')
        self.cbGanchoH2    = self.win.FindName('cbGanchoH2')
        self.cbDiamV2      = self.win.FindName('cbDiamV2')
        self.txtEspV2      = self.win.FindName('txtEspV2')
        self.cbGanchoV2Sup = self.win.FindName('cbGanchoV2Sup')
        self.cbGanchoV2Inf = self.win.FindName('cbGanchoV2Inf')
        self.lblContador   = self.win.FindName('lblContador')

        # Poblar diámetros
        for cb in [self.cbDiamH1, self.cbDiamV1, self.cbDiamH2, self.cbDiamV2]:
            for n in nombres_diametros: cb.Items.Add(n)
            self._set_default(cb, DEF_DIAM)

        # Poblar ganchos
        for cb in [self.cbGanchoH1, self.cbGanchoV1Sup, self.cbGanchoV1Inf,
                   self.cbGanchoH2, self.cbGanchoV2Sup, self.cbGanchoV2Inf]:
            for n in nombres_ganchos: cb.Items.Add(n)
            self._set_default(cb, DEF_GANCHO)

        # Eventos
        self.rbUnaCara.Checked  += self.on_modo_changed
        self.rbDosCaras.Checked += self.on_modo_changed
        self.win.FindName('btnSeleccionar').Click += self.on_seleccionar
        self.win.FindName('btnAceptar').Click     += self.on_aceptar
        self.win.FindName('btnCancelar').Click    += self.on_cancelar

    def _set_default(self, combo, nombre):
        if combo.Items.Contains(nombre): combo.SelectedItem = nombre
        elif combo.Items.Count > 0:      combo.SelectedIndex = 0

    def on_modo_changed(self, sender, e):
        if self.rbDosCaras.IsChecked:
            self.panelCara2.Visibility = SW.Visibility.Visible
            self.lblCara1.Text = 'CARA 1  —  Cara exterior (normal -)'
        else:
            self.panelCara2.Visibility = SW.Visibility.Collapsed
            self.lblCara1.Text = 'CARA UNICA  /  EJE DEL MURO'

    def on_seleccionar(self, sender, e):
        self.win.Hide()
        try:
            ref = uidoc.Selection.PickObject(
                ObjectType.Element, FiltroMuros(),
                'Selecciona un muro')
            self.muros_ids = [ref.ElementId]
            self.lblContador.Text       = '1 muro seleccionado'
            self.lblContador.Foreground = SWM.Brushes.DarkGreen
        except Exception:
            self.lblContador.Text       = 'Seleccion cancelada. Intenta de nuevo.'
            self.lblContador.Foreground = SWM.Brushes.Gray
        self.win.ShowDialog()

    def on_aceptar(self, sender, e):
        if not self.muros_ids:
            SW.MessageBox.Show('Selecciona al menos un muro antes de continuar.',
                               'Sin muros', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        try:
            recub      = float(self.txtRecub.Text)
            desfase_inf = float(self.txtDesfaseInf.Text)
            esp_h1     = float(self.txtEspH1.Text)
            esp_v1     = float(self.txtEspV1.Text)
        except ValueError:
            SW.MessageBox.Show('Recubrimiento, desfase y espaciados deben ser numericos.',
                               'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return

        dos_caras = bool(self.rbDosCaras.IsChecked)
        if dos_caras:
            try:
                esp_h2 = float(self.txtEspH2.Text)
                esp_v2 = float(self.txtEspV2.Text)
            except ValueError:
                SW.MessageBox.Show('Espaciados de Cara 2 deben ser numericos.',
                                   'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
                return
        else:
            esp_h2 = esp_h1
            esp_v2 = esp_v1

        self.resultado = {
            'recub'         : recub,
            'desfase_inf'   : desfase_inf,
            'dos_caras'     : dos_caras,
            'diam_h1'       : str(self.cbDiamH1.SelectedItem),
            'esp_h1'        : esp_h1,
            'gancho_h1'     : str(self.cbGanchoH1.SelectedItem),
            'diam_v1'       : str(self.cbDiamV1.SelectedItem),
            'esp_v1'        : esp_v1,
            'gancho_v1_sup' : str(self.cbGanchoV1Sup.SelectedItem),
            'gancho_v1_inf' : str(self.cbGanchoV1Inf.SelectedItem),
            'diam_h2'       : str(self.cbDiamH2.SelectedItem),
            'esp_h2'        : esp_h2,
            'gancho_h2'     : str(self.cbGanchoH2.SelectedItem),
            'diam_v2'       : str(self.cbDiamV2.SelectedItem),
            'esp_v2'        : esp_v2,
            'gancho_v2_sup' : str(self.cbGanchoV2Sup.SelectedItem),
            'gancho_v2_inf' : str(self.cbGanchoV2Inf.SelectedItem),
        }
        self.win.Close()

    def on_cancelar(self, sender, e):
        self.resultado = None
        self.win.Close()

    def show(self):
        self.win.ShowDialog()
        return self.resultado

# ─── Mostrar formulario ───────────────────────────────────────────────────────
form = FormMuros()
res  = form.show()

if res is None:
    import sys; sys.exit()

# ─── Resolver entradas ────────────────────────────────────────────────────────
recubrimiento_mm = res['recub']
desfase_inf_ft   = cm_a_pies(res['desfase_inf'])   # convertir cm → pies
dos_caras        = res['dos_caras']

def resolver_gancho(nombre):
    gid = ganchos.get(nombre)
    return doc.GetElement(gid) if gid else None

# Cara 1
diam_h1_mm  = diametros_mm_map.get(res['diam_h1'], 12.0)
diam_v1_mm  = diametros_mm_map.get(res['diam_v1'], 12.0)
bar_h1      = doc.GetElement(diametros[res['diam_h1']])
bar_v1      = doc.GetElement(diametros[res['diam_v1']])
esp_h1_mm   = res['esp_h1']
esp_v1_mm   = res['esp_v1']
hk_h1       = resolver_gancho(res['gancho_h1'])
hk_v1_sup   = resolver_gancho(res['gancho_v1_sup'])
hk_v1_inf   = resolver_gancho(res['gancho_v1_inf'])

# Cara 2
diam_h2_mm  = diametros_mm_map.get(res['diam_h2'], 12.0)
diam_v2_mm  = diametros_mm_map.get(res['diam_v2'], 12.0)
bar_h2      = doc.GetElement(diametros[res['diam_h2']])
bar_v2      = doc.GetElement(diametros[res['diam_v2']])
esp_h2_mm   = res['esp_h2']
esp_v2_mm   = res['esp_v2']
hk_h2       = resolver_gancho(res['gancho_h2'])
hk_v2_sup   = resolver_gancho(res['gancho_v2_sup'])
hk_v2_inf   = resolver_gancho(res['gancho_v2_inf'])

muros_seleccionados = form.muros_ids

# ─── Offsets de cara desde el eje del muro ───────────────────────────────────
def off_cara_exterior(espesor_mm, recub_mm, diam_ext_mm):
    return -(espesor_mm / 2.0 - recub_mm - diam_ext_mm / 2.0)

def off_cara_interior(espesor_mm, recub_mm, diam_ext_mm):
    return  (espesor_mm / 2.0 - recub_mm - diam_ext_mm / 2.0)

# ─── Rotación de ganchos ──────────────────────────────────────────────────────
def rotar_ganchos(rebar, ang_inicio, ang_final):
    """Fija la rotación de los ganchos de la barra (en RADIANES).

    - ang_inicio -> 'Rotación del gancho al inicio' = gancho INFERIOR.
    - ang_final  -> 'Rotación del gancho al final'  = gancho SUPERIOR.
    Pasa None en cualquiera de los dos para NO modificarlo.
    """
    for p in rebar.Parameters:
        if ang_inicio is not None and p.Definition.Name == u'Rotación del gancho al inicio' and not p.IsReadOnly:
            p.Set(ang_inicio)
        if ang_final is not None and p.Definition.Name == u'Rotación del gancho al final' and not p.IsReadOnly:
            p.Set(ang_final)

# ─── Crear grupo de barras HORIZONTALES ───────────────────────────────────────
def crear_horizontales(muro, bar_type, diam_mm, esp_mm, recub_mm,
                       offset_cara_mm, hk_ini, hk_fin,
                       rot_ini_rad=None, rot_fin_rad=None):
    """Grupo grupal de barras horizontales distribuidas en altura.
    rot_ini_rad / rot_fin_rad: rotación del gancho en ese extremo (None = no tocar).
    """
    longitud_mm, altura_mm, espesor_mm, eje_largo, eje_normal, origen = get_info_muro(muro)

    n_barras, esp_ft, offset_ini_ft = calcular_grupo(altura_mm, recub_mm, diam_mm, esp_mm)

    long_util_ft = mm_a_pies(longitud_mm - 2.0 * recub_mm)
    recub_ft     = mm_a_pies(recub_mm)
    off_cara     = mm_a_pies(offset_cara_mm)

    # El inicio de la barra arranca recub_ft después del origen del muro
    cx    = origen.X + eje_normal.X * off_cara + eje_largo.X * recub_ft
    cy    = origen.Y + eje_normal.Y * off_cara + eje_largo.Y * recub_ft
    z_sem = origen.Z + offset_ini_ft

    p_ini = XYZ(cx, cy, z_sem)
    p_fin = XYZ(cx + eje_largo.X * long_util_ft,
                cy + eje_largo.Y * long_util_ft, z_sem)

    rebar = Rebar.CreateFromCurves(
        doc, RebarStyle.Standard, bar_type,
        hk_ini, hk_fin, muro,
        XYZ(0, 0, 1),
        [Line.CreateBound(p_ini, p_fin)],
        RebarHookOrientation.Right, RebarHookOrientation.Right,
        True, True
    )
    if n_barras >= 2:
        rebar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            n_barras, esp_ft, True, True, True)

    # Rotación de ganchos si se especifica
    if rot_ini_rad is not None or rot_fin_rad is not None:
        rotar_ganchos(rebar, rot_ini_rad, rot_fin_rad)

    return rebar

# ─── Crear grupo de barras VERTICALES ──────────────────────────────────────── ────────────────────────────────────────
def crear_verticales(muro, bar_type, diam_mm, esp_mm, recub_mm,
                     offset_cara_mm, hk_inf, hk_sup,
                     rot_inf_rad=None, rot_sup_rad=None,
                     desfase_inf_ft=0.0):
    """Grupo grupal de barras verticales distribuidas a lo largo del muro.
    hk_inf / rot_inf_rad : gancho y rotación del extremo inferior (hookTypeAtStart).
    hk_sup / rot_sup_rad : gancho y rotación del extremo superior (hookTypeAtEnd).
    desfase_inf_ft       : extensión hacia abajo más allá de la base del muro (pies).
    """
    longitud_mm, altura_mm, espesor_mm, eje_largo, eje_normal, origen = get_info_muro(muro)

    n_barras, esp_ft, offset_ini_ft = calcular_grupo(longitud_mm, recub_mm, diam_mm, esp_mm)

    alto_util_ft = mm_a_pies(altura_mm - 2.0 * recub_mm)
    off_cara     = mm_a_pies(offset_cara_mm)

    x_sem = origen.X + eje_largo.X * offset_ini_ft + eje_normal.X * off_cara
    y_sem = origen.Y + eje_largo.Y * offset_ini_ft + eje_normal.Y * off_cara

    # z_bot baja adicionalmente el desfase inferior (hacia la cimentación)
    z_bot = origen.Z + mm_a_pies(recub_mm) - desfase_inf_ft
    z_top = origen.Z + mm_a_pies(recub_mm) + alto_util_ft

    p_bot = XYZ(x_sem, y_sem, z_bot)
    p_top = XYZ(x_sem, y_sem, z_top)

    # hookTypeAtStart = extremo inferior (p_bot) = hk_inf
    # hookTypeAtEnd   = extremo superior (p_top) = hk_sup
    rebar = Rebar.CreateFromCurves(
        doc, RebarStyle.Standard, bar_type,
        hk_inf, hk_sup, muro,
        XYZ(eje_largo.X, eje_largo.Y, 0),
        [Line.CreateBound(p_bot, p_top)],
        RebarHookOrientation.Right, RebarHookOrientation.Right,
        True, True
    )
    if n_barras >= 2:
        rebar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            n_barras, esp_ft, True, True, True)

    # Rotación de ganchos si se especifica
    # ang_inicio = extremo inferior (p_bot = hookTypeAtStart)
    # ang_final  = extremo superior (p_top = hookTypeAtEnd)
    if rot_inf_rad is not None or rot_sup_rad is not None:
        rotar_ganchos(rebar, rot_inf_rad, rot_sup_rad)

    return rebar

# ─── Transacción principal ────────────────────────────────────────────────────
# Reglas de rotación de ganchos:
#   Cara 1 - Horizontal : rot_ini = rot_fin = math.pi (180°) en ambos extremos
#   Cara 1 - Vertical   : sin rotación adicional (ganchos tal como los define el tipo)
#   Cara 2 - Horizontal : sin rotación adicional
#   Cara 2 - Vertical   : rot_inf = rot_sup = math.pi (180°) — espejo de la cara 1

ROT_180 = math.pi   # 180 grados en radianes

total_muros = 0

with Transaction(doc, 'Acero de refuerzo en muros') as t:
    t.Start()

    for eid in muros_seleccionados:
        muro = doc.GetElement(eid)
        try:
            longitud_mm, altura_mm, espesor_mm, eje_largo, eje_normal, origen = \
                get_info_muro(muro)
        except Exception:
            continue

        if not dos_caras:
            # ── Una cara / Eje: todo en el plano medio ────────────────────────
            crear_horizontales(muro, bar_h1, diam_h1_mm, esp_h1_mm,
                               recubrimiento_mm, 0.0, hk_h1, hk_h1,
                               rot_ini_rad=ROT_180, rot_fin_rad=ROT_180)
            crear_verticales  (muro, bar_v1, diam_v1_mm, esp_v1_mm,
                               recubrimiento_mm, 0.0, hk_v1_inf, hk_v1_sup,
                               desfase_inf_ft=desfase_inf_ft)
        else:
            # ── Cara 1 (exterior, normal-) ────────────────────────────────────
            off_h1 = off_cara_exterior(espesor_mm, recubrimiento_mm, diam_h1_mm)
            crear_horizontales(muro, bar_h1, diam_h1_mm, esp_h1_mm,
                               recubrimiento_mm, off_h1, hk_h1, hk_h1,
                               rot_ini_rad=ROT_180, rot_fin_rad=ROT_180)
            off_v1 = off_h1 + diam_h1_mm / 2.0 + diam_v1_mm / 2.0
            crear_verticales(muro, bar_v1, diam_v1_mm, esp_v1_mm,
                             recubrimiento_mm, off_v1, hk_v1_inf, hk_v1_sup,
                             desfase_inf_ft=desfase_inf_ft)

            # ── Cara 2 (interior, normal+) ────────────────────────────────────
            off_h2 = off_cara_interior(espesor_mm, recubrimiento_mm, diam_h2_mm)
            crear_horizontales(muro, bar_h2, diam_h2_mm, esp_h2_mm,
                               recubrimiento_mm, off_h2, hk_h2, hk_h2)
            off_v2 = off_h2 - (diam_h2_mm / 2.0 + diam_v2_mm / 2.0)
            crear_verticales(muro, bar_v2, diam_v2_mm, esp_v2_mm,
                             recubrimiento_mm, off_v2, hk_v2_inf, hk_v2_sup,
                             rot_inf_rad=ROT_180, rot_sup_rad=ROT_180,
                             desfase_inf_ft=desfase_inf_ft)

        total_muros += 1

    t.Commit()

# ─── Mensaje final ────────────────────────────────────────────────────────────
modo_txt = 'Dos caras' if dos_caras else 'Una cara / Eje'
SW.MessageBox.Show(
    'Acero de refuerzo creado con exito\n'
    'Muros armados : {}\n'
    'Modo          : {}'.format(total_muros, modo_txt),
    'Listo',
    SW.MessageBoxButton.OK,
    SW.MessageBoxImage.Information
)