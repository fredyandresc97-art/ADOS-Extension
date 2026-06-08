# -*- coding: utf-8 -*-
# Armadura en zapatas con ventana WPF (un solo archivo). La lógica de armado es
# la misma de tu versión; lo único que cambia es el formulario: ahora es una
# ventana WPF incrustada (XAML_VENTANA) en vez de los dos formularios de rpw.
# El acero superior aparece en una sección que se muestra al marcar la casilla.
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
import math
import System
from Autodesk.Revit.DB import (FilteredElementCollector, BuiltInParameter, BuiltInCategory, Transaction, XYZ, Line)
from Autodesk.Revit.DB.Structure import (RebarBarType, RebarHookType, Rebar, RebarStyle, RebarHookOrientation)
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import forms, script

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# ─── Conversiones ─────────────────────────────────────────────────────────────
def mm_a_pies(mm):
    return mm / 304.8

def pies_a_mm(pies):
    return pies * 304.8

# ─── Lógica de distribución ───────────────────────────────────────────────────
def calcular_distribucion(longitud_mm, recubrimiento_mm, diametro_mm, espaciado_mm):
    lm     = (longitud_mm - 2 * recubrimiento_mm) - diametro_mm
    M      = int(math.floor(1 + lm / espaciado_mm))
    xd     = lm / M
    offset = recubrimiento_mm + diametro_mm / 2.0
    return M + 1, xd, offset

# ─── Ejes locales de la zapata ────────────────────────────────────────────────
def get_ejes_locales(zapata):
    transform = zapata.GetTransform()
    eje_x  = transform.BasisX
    eje_y  = transform.BasisY
    eje_z  = transform.BasisZ
    origen = transform.Origin
    if eje_x.X < 0 or (eje_x.X == 0 and eje_x.Y < 0):
        eje_x = eje_x.Negate()
    if eje_y.Y < 0 or (eje_y.Y == 0 and eje_y.X < 0):
        eje_y = eje_y.Negate()
    return eje_x, eje_y, eje_z, origen

# ─── Dimensiones locales de la zapata ─────────────────────────────────────────
def get_dimensiones_locales(zapata):
    param_largo = zapata.get_Parameter(BuiltInParameter.STRUCTURAL_FOUNDATION_LENGTH)
    param_ancho = zapata.get_Parameter(BuiltInParameter.STRUCTURAL_FOUNDATION_WIDTH)
    param_alto  = zapata.get_Parameter(BuiltInParameter.STRUCTURAL_FOUNDATION_THICKNESS)
    largo_mm = pies_a_mm(param_largo.AsDouble()) if param_largo else None
    ancho_mm = pies_a_mm(param_ancho.AsDouble()) if param_ancho else None
    alto_mm  = pies_a_mm(param_alto.AsDouble())  if param_alto  else None
    if not largo_mm or not ancho_mm:
        bbox     = zapata.get_BoundingBox(None)
        largo_mm = pies_a_mm(bbox.Max.X - bbox.Min.X)
        ancho_mm = pies_a_mm(bbox.Max.Y - bbox.Min.Y)
        alto_mm  = pies_a_mm(bbox.Max.Z - bbox.Min.Z)
    return largo_mm, ancho_mm, alto_mm

# ─── Recopilar datos del archivo ──────────────────────────────────────────────
barra_tipos = FilteredElementCollector(doc).OfClass(RebarBarType).ToElements()
diametros    = {}
diametros_mm = {}
for bt in barra_tipos:
    nombre = bt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    diametros[nombre] = bt.Id
    dia_param = bt.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER)
    if dia_param:
        diametros_mm[nombre] = pies_a_mm(dia_param.AsDouble())

if not diametros:
    forms.alert('No se encontraron tipos de barra en el archivo.', exitscript=True)

gancho_tipos = FilteredElementCollector(doc).OfClass(RebarHookType).ToElements()
ganchos = {'Sin gancho': None}
for gt in gancho_tipos:
    nombre = gt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    ganchos[nombre] = gt.Id

# ─── Valores por defecto de la ventana (edítalos a tu gusto) ──────────────────
# Deben coincidir EXACTAMENTE con el nombre del tipo en el modelo; si no
# coinciden, el ComboBox muestra la primera opción (no falla).
DEF_DIAMETRO_INF = '13M'
DEF_DIAMETRO_SUP = '13M'
DEF_GANCHO_INF   = 'Estándar - 90°.'
DEF_GANCHO_SUP   = 'Estándar - 90°.'

# ─── Ventana WPF incrustada (XAML como texto) ─────────────────────────────────
XAML_VENTANA = """
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Armadura en Zapatas"
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
        <TextBlock Text="Armadura en Zapatas" FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Instala parilla de acero inferior y superior --- Ados Software" FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <!-- Acero inferior -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BDBDBD" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="ACERO INFERIOR" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Grid Margin="0,0,0,6">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Diametro de barra" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbDiametro" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Recubrimiento (mm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtRecub" Text="75" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
        </Grid>
        <Grid Margin="0,0,0,6">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Espaciado maximo (mm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtEspaciado" Text="200" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Forma de gancho" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbGancho" Height="28" Padding="4,0"/>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <!-- Casilla acero superior -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BDBDBD" BorderThickness="1">
      <CheckBox x:Name="chkSuperior" Content="  Crear acero superior" FontWeight="SemiBold"/>
    </Border>

    <!-- Acero superior (oculto hasta marcar la casilla) -->
    <Border x:Name="panelSuperior" Background="#FFFBF3" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1" Visibility="Collapsed">
      <StackPanel>
        <TextBlock Text="ACERO SUPERIOR" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Grid Margin="0,0,0,6">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Diametro de barra" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbDiametroSup" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Espaciado maximo (mm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtEspSup" Text="200" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
        </Grid>
        <TextBlock Text="Forma de gancho" Foreground="#555" Margin="0,0,0,3"/>
        <ComboBox x:Name="cbGanchoSup" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <!-- Seleccion zapatas -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BDBDBD" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="ZAPATAS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar zapatas en Revit"
                Height="32" Cursor="Hand"
                Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador"
                   Text="Ninguna zapata seleccionada"
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
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear acero"
              Height="34" Cursor="Hand"
              Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
  </ScrollViewer>
</Window>
"""

# ─── Ventana WPF ──────────────────────────────────────────────────────────────
class VentanaZapatas(forms.WPFWindow):
    """Crea la ventana a partir del XAML incrustado y conecta los eventos."""

    def __init__(self):
        forms.WPFWindow.__init__(self, XAML_VENTANA, literal_string=True)
        self.zapatas = []
        self.aceptado = False

        nombres_diam = sorted(diametros.keys())
        nombres_ganchos = ['Sin gancho'] + sorted(k for k in ganchos.keys() if k != 'Sin gancho')
        for n in nombres_diam:
            self.cbDiametro.Items.Add(n)
            self.cbDiametroSup.Items.Add(n)
        for n in nombres_ganchos:
            self.cbGancho.Items.Add(n)
            self.cbGanchoSup.Items.Add(n)

        self._set_default(self.cbDiametro, DEF_DIAMETRO_INF)
        self._set_default(self.cbDiametroSup, DEF_DIAMETRO_SUP)
        self._set_default(self.cbGancho, DEF_GANCHO_INF)
        self._set_default(self.cbGanchoSup, DEF_GANCHO_SUP)

        self.chkSuperior.Checked += self.on_toggle_sup
        self.chkSuperior.Unchecked += self.on_toggle_sup
        self.btnSeleccionar.Click += self.on_seleccionar
        self.btnAceptar.Click += self.on_aceptar
        self.btnCancelar.Click += self.on_cancelar

    def _set_default(self, combo, nombre):
        """Preselecciona `nombre` si existe; si no, la primera opción."""
        if combo.Items.Contains(nombre):
            combo.SelectedItem = nombre
        elif combo.Items.Count > 0:
            combo.SelectedIndex = 0

    def on_toggle_sup(self, sender, args):
        """Muestra u oculta la sección de acero superior según la casilla."""
        if self.chkSuperior.IsChecked:
            self.panelSuperior.Visibility = System.Windows.Visibility.Visible
        else:
            self.panelSuperior.Visibility = System.Windows.Visibility.Collapsed

    def on_seleccionar(self, sender, args):
        """Oculta la ventana, deja elegir zapatas y vuelve a mostrarse."""
        self.Hide()
        try:
            referencias = uidoc.Selection.PickObjects(
                ObjectType.Element,
                'Selecciona las zapatas y presiona ENTER para confirmar')
            id_cat = int(BuiltInCategory.OST_StructuralFoundation)
            self.zapatas = []
            rechazados = 0
            for ref in referencias:
                elem = doc.GetElement(ref.ElementId)
                if elem.Category.Id.IntegerValue == id_cat:
                    self.zapatas.append(ref.ElementId)
                else:
                    rechazados += 1
            if rechazados > 0:
                self.lblContador.Text = 'Zapatas: {} ({} ignorados)'.format(len(self.zapatas), rechazados)
            else:
                self.lblContador.Text = 'Zapatas seleccionadas: {}'.format(len(self.zapatas))
        except Exception:
            self.lblContador.Text = 'Seleccion cancelada. Intenta de nuevo.'
        finally:
            self.ShowDialog()

    def on_aceptar(self, sender, args):
        """Valida, guarda los valores y cierra la ventana."""
        if not self.zapatas:
            forms.alert('No seleccionaste ninguna zapata.')
            return
        try:
            self.recub     = float(self.txtRecub.Text)
            self.espaciado = float(self.txtEspaciado.Text)
        except ValueError:
            forms.alert('Recubrimiento y Espaciado deben ser numericos.')
            return
        self.crear_sup = bool(self.chkSuperior.IsChecked)
        if self.crear_sup:
            try:
                self.esp_sup = float(self.txtEspSup.Text)
            except ValueError:
                forms.alert('Espaciado superior debe ser numerico.')
                return
            self.nom_diam_sup   = self.cbDiametroSup.SelectedItem
            self.nom_gancho_sup = self.cbGanchoSup.SelectedItem
        self.nom_diam   = self.cbDiametro.SelectedItem
        self.nom_gancho = self.cbGancho.SelectedItem
        self.aceptado = True
        self.Close()

    def on_cancelar(self, sender, args):
        self.aceptado = False
        self.Close()

# ─── Mostrar ventana ──────────────────────────────────────────────────────────
ventana = VentanaZapatas()
ventana.ShowDialog()

if not ventana.aceptado:
    script.exit()   # salida limpia de pyRevit (no abre la consola de salida)

# ─── Resolver entradas ────────────────────────────────────────────────────────
zapatas_seleccionadas = ventana.zapatas
recubrimiento_mm = ventana.recub
espaciado_mm     = ventana.espaciado
crear_superior   = ventana.crear_sup

diametro_mm = diametros_mm.get(ventana.nom_diam, 12.0)
bar_type    = doc.GetElement(diametros[ventana.nom_diam])
id_gancho   = ganchos.get(ventana.nom_gancho)
hook_type   = doc.GetElement(id_gancho) if id_gancho else None

# Acero superior (solo si se activó)
espaciado_sup_mm = None
bar_type_sup     = None
hook_type_sup    = None
diametro_sup_mm  = 12.0
if crear_superior:
    espaciado_sup_mm = ventana.esp_sup
    diametro_sup_mm  = diametros_mm.get(ventana.nom_diam_sup, 12.0)
    bar_type_sup     = doc.GetElement(diametros[ventana.nom_diam_sup])
    id_gancho_sup    = ganchos.get(ventana.nom_gancho_sup)
    hook_type_sup    = doc.GetElement(id_gancho_sup) if id_gancho_sup else None

# ─── Transacción única con todo ───────────────────────────────────────────────
with Transaction(doc, 'Armadura en zapatas') as t:
    t.Start()

    for eid in zapatas_seleccionadas:
        zapata = doc.GetElement(eid)
        eje_x, eje_y, eje_z, origen = get_ejes_locales(zapata)
        largo_mm, ancho_mm, alto_mm = get_dimensiones_locales(zapata)
        z_base = origen.Z - mm_a_pies(alto_mm)
        esquina = XYZ(
            origen.X - eje_x.X * mm_a_pies(largo_mm / 2.0) - eje_y.X * mm_a_pies(ancho_mm / 2.0),
            origen.Y - eje_x.Y * mm_a_pies(largo_mm / 2.0) - eje_y.Y * mm_a_pies(ancho_mm / 2.0),
            z_base
        )

        # ── CAPA INFERIOR X ───────────────────────────────────────────────────
        num_X, esp_X, offset_X = calcular_distribucion(
            ancho_mm, recubrimiento_mm, diametro_mm, espaciado_mm)
        z_capa_X = z_base + mm_a_pies(recubrimiento_mm + diametro_mm / 2.0)

        p1_X = XYZ(
            esquina.X + eje_y.X * mm_a_pies(offset_X) + eje_x.X * mm_a_pies(recubrimiento_mm),
            esquina.Y + eje_y.Y * mm_a_pies(offset_X) + eje_x.Y * mm_a_pies(recubrimiento_mm),
            z_capa_X
        )
        p2_X = XYZ(
            esquina.X + eje_y.X * mm_a_pies(offset_X) + eje_x.X * mm_a_pies(largo_mm - recubrimiento_mm),
            esquina.Y + eje_y.Y * mm_a_pies(offset_X) + eje_x.Y * mm_a_pies(largo_mm - recubrimiento_mm),
            z_capa_X
        )
        rebar_X = Rebar.CreateFromCurves(
            doc, RebarStyle.Standard, bar_type, hook_type, hook_type, zapata,
            XYZ(0, 1, 0), [Line.CreateBound(p1_X, p2_X)],
            RebarHookOrientation.Right, RebarHookOrientation.Right, True, True
        )
        rebar_X.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            num_X, mm_a_pies(esp_X), True, True, True)

        # ── CAPA INFERIOR Y ───────────────────────────────────────────────────
        offset_Y       = recubrimiento_mm + diametro_mm + diametro_mm / 2.0
        offset_Y_final = largo_mm - recubrimiento_mm - diametro_mm - diametro_mm / 2.0
        zona_efectiva_Y = offset_Y_final - offset_Y
        M_Y   = int(math.floor(1 + zona_efectiva_Y / espaciado_mm))
        esp_Y = zona_efectiva_Y / M_Y
        num_Y = M_Y + 1
        z_capa_Y = z_capa_X + mm_a_pies(diametro_mm)

        p1_Y = XYZ(
            esquina.X + eje_x.X * mm_a_pies(offset_Y) + eje_y.X * mm_a_pies(recubrimiento_mm),
            esquina.Y + eje_x.Y * mm_a_pies(offset_Y) + eje_y.Y * mm_a_pies(recubrimiento_mm),
            z_capa_Y
        )
        p2_Y = XYZ(
            esquina.X + eje_x.X * mm_a_pies(offset_Y) + eje_y.X * mm_a_pies(ancho_mm - recubrimiento_mm),
            esquina.Y + eje_x.Y * mm_a_pies(offset_Y) + eje_y.Y * mm_a_pies(ancho_mm - recubrimiento_mm),
            z_capa_Y
        )
        rebar_Y = Rebar.CreateFromCurves(
            doc, RebarStyle.Standard, bar_type, hook_type, hook_type, zapata,
            XYZ(1, 0, 0), [Line.CreateBound(p1_Y, p2_Y)],
            RebarHookOrientation.Left, RebarHookOrientation.Left, True, True
        )
        rebar_Y.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            num_Y, mm_a_pies(esp_Y), True, True, True)
        for p in rebar_Y.Parameters:
            if p.Definition.Name == 'Rotación del gancho al inicio' and not p.IsReadOnly:
                p.Set(math.pi)
            if p.Definition.Name == 'Rotación del gancho al final' and not p.IsReadOnly:
                p.Set(math.pi)

        # ── CAPAS SUPERIORES ──────────────────────────────────────────────────
        if crear_superior:
            z_capa_sup_X = origen.Z - mm_a_pies(recubrimiento_mm + diametro_sup_mm / 2.0)
            z_capa_sup_Y = z_capa_sup_X - mm_a_pies(diametro_sup_mm)

            # CAPA SUPERIOR X
            num_supX, esp_supX, offset_supX = calcular_distribucion(
                ancho_mm, recubrimiento_mm, diametro_sup_mm, espaciado_sup_mm)

            p1_supX = XYZ(
                esquina.X + eje_y.X * mm_a_pies(offset_supX) + eje_x.X * mm_a_pies(recubrimiento_mm),
                esquina.Y + eje_y.Y * mm_a_pies(offset_supX) + eje_x.Y * mm_a_pies(recubrimiento_mm),
                z_capa_sup_X
            )
            p2_supX = XYZ(
                esquina.X + eje_y.X * mm_a_pies(offset_supX) + eje_x.X * mm_a_pies(largo_mm - recubrimiento_mm),
                esquina.Y + eje_y.Y * mm_a_pies(offset_supX) + eje_x.Y * mm_a_pies(largo_mm - recubrimiento_mm),
                z_capa_sup_X
            )
            rebar_supX = Rebar.CreateFromCurves(
                doc, RebarStyle.Standard, bar_type_sup, hook_type_sup, hook_type_sup, zapata,
                XYZ(eje_y.X, eje_y.Y, 0), [Line.CreateBound(p1_supX, p2_supX)],
                RebarHookOrientation.Left, RebarHookOrientation.Left, True, True
            )
            rebar_supX.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
                num_supX, mm_a_pies(esp_supX), True, True, True)
            for p in rebar_supX.Parameters:
                if p.Definition.Name == 'Rotación del gancho al inicio' and not p.IsReadOnly:
                    p.Set(math.pi)
                if p.Definition.Name == 'Rotación del gancho al final' and not p.IsReadOnly:
                    p.Set(math.pi)

            # CAPA SUPERIOR Y
            offset_supY       = recubrimiento_mm + diametro_sup_mm + diametro_sup_mm / 2.0
            offset_supY_final = largo_mm - recubrimiento_mm - diametro_sup_mm - diametro_sup_mm / 2.0
            zona_efectiva_supY = offset_supY_final - offset_supY
            M_supY   = int(math.floor(1 + zona_efectiva_supY / espaciado_sup_mm))
            esp_supY = zona_efectiva_supY / M_supY
            num_supY = M_supY + 1

            p1_supY = XYZ(
                esquina.X + eje_x.X * mm_a_pies(offset_supY) + eje_y.X * mm_a_pies(recubrimiento_mm),
                esquina.Y + eje_x.Y * mm_a_pies(offset_supY) + eje_y.Y * mm_a_pies(recubrimiento_mm),
                z_capa_sup_Y
            )
            p2_supY = XYZ(
                esquina.X + eje_x.X * mm_a_pies(offset_supY) + eje_y.X * mm_a_pies(ancho_mm - recubrimiento_mm),
                esquina.Y + eje_x.Y * mm_a_pies(offset_supY) + eje_y.Y * mm_a_pies(ancho_mm - recubrimiento_mm),
                z_capa_sup_Y
            )
            rebar_supY = Rebar.CreateFromCurves(
                doc, RebarStyle.Standard, bar_type_sup, hook_type_sup, hook_type_sup, zapata,
                XYZ(eje_x.X, eje_x.Y, 0), [Line.CreateBound(p1_supY, p2_supY)],
                RebarHookOrientation.Left, RebarHookOrientation.Left, True, True
            )
            rebar_supY.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
                num_supY, mm_a_pies(esp_supY), True, True, True)

    t.Commit()

if crear_superior:
    forms.alert('Aceros creados con exito en {} zapatas (inferior + superior).'.format(
        len(zapatas_seleccionadas)))
else:
    forms.alert('Aceros inferiores creados con exito en {} zapatas.'.format(
        len(zapatas_seleccionadas)))
