# -*- coding: utf-8 -*-
"""
Acero Longitudinal en Vigas (Pórtico)
--------------------------------------
Crea UNA barra longitudinal continua de extremo a extremo de varias vigas
colineales (pórtico recto). Capas: inferior, superior e intermedios laterales.

El longitudinal va DENTRO del fleje, por eso:
    offset = recubrimiento + diámetro_fleje + diámetro_varilla/2

Ganchos configurables, ambos (inicio y fin) apuntando en la MISMA dirección.

Ventana WPF incrustada (forms.WPFWindow de pyRevit).
Elaborado por: Ing. Andres Angel
"""
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
import math
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInParameter, BuiltInCategory,
    Transaction, XYZ, Line
)
from Autodesk.Revit.DB.Structure import (
    RebarBarType, RebarHookType, Rebar, RebarStyle, RebarHookOrientation
)
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import forms, script

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# ─── Conversiones ─────────────────────────────────────────────────────────────
def cm_a_pies(cm):  return cm / 30.48
def pies_a_cm(p):   return p * 30.48
def mm_a_pies(mm):  return mm / 304.8

# ─── Reparto uniforme ─────────────────────────────────────────────────────────
def reparto(a, b, n):
    """n posiciones uniformes entre a y b inclusive. n==1 -> punto medio."""
    if n <= 1:
        return [(a + b) / 2.0]
    paso = (b - a) / (n - 1)
    return [a + paso * i for i in range(n)]

# ─── Orientación de ganchos ───────────────────────────────────────────────────
def orientar_ganchos(rebar, ang_inicio, ang_final):
    """Fija rotación de ganchos (radianes). None = no tocar."""
    for p in rebar.Parameters:
        if ang_inicio is not None and p.Definition.Name == 'Rotación del gancho al inicio' and not p.IsReadOnly:
            p.Set(ang_inicio)
        if ang_final is not None and p.Definition.Name == 'Rotación del gancho al final' and not p.IsReadOnly:
            p.Set(ang_final)

# ─── Geometría del pórtico (vigas colineales) ─────────────────────────────────
def get_geometria_portico(vigas):
    """
    A partir de una lista de vigas colineales devuelve:
        p_ini, p_fin    – extremos globales del pórtico (pies)
        eje_long        – vector unitario a lo largo del pórtico
        eje_ancho       – transversal horizontal (unitario)
        eje_alto        – vertical / peralte (unitario)
        ancho_cm, alto_cm – sección (de la primera viga)
        long_total_cm   – longitud total del pórtico

    Toma todos los puntos extremos de las LocationCurve, los proyecta sobre
    la dirección general y se queda con los dos más alejados.
    """
    # Dirección general: usar la primera viga
    loc0   = vigas[0].Location
    curva0 = loc0.Curve
    a0 = curva0.GetEndPoint(0)
    b0 = curva0.GetEndPoint(1)
    eje_long = (b0 - a0).Normalize()

    # Recolectar todos los puntos extremos de todas las vigas
    puntos = []
    for v in vigas:
        c = v.Location.Curve
        puntos.append(c.GetEndPoint(0))
        puntos.append(c.GetEndPoint(1))

    # Proyectar cada punto sobre el eje_long desde a0; quedarnos con min y max
    proy_min = None; proy_max = None
    p_ini = None; p_fin = None
    for pt in puntos:
        d = (pt - a0).DotProduct(eje_long)
        if proy_min is None or d < proy_min:
            proy_min = d; p_ini = pt
        if proy_max is None or d > proy_max:
            proy_max = d; p_fin = pt

    long_total_cm = pies_a_cm((p_fin - p_ini).GetLength())

    # Ejes transversales
    z_global = XYZ(0, 0, 1)
    if abs(eje_long.DotProduct(z_global)) > 0.99:
        eje_ancho = XYZ(1, 0, 0)
    else:
        eje_ancho = eje_long.CrossProduct(z_global).Normalize()
    eje_alto = eje_ancho.CrossProduct(eje_long).Normalize()

    # Sección de la primera viga
    ancho_cm, alto_cm = get_seccion_viga(vigas[0])
    alto_ft_local = cm_a_pies(alto_cm)

    # Corrección por desplazamiento vertical (Z offset).
    # BoundingBox.Max.Z NO es confiable porque incluye la línea analítica.
    # BoundingBox.Min.Z SÍ refleja la cara inferior real de la viga.
    # La cara superior real = Min.Z + altura de la sección.
    bb0 = vigas[0].get_BoundingBox(None)
    if bb0:
        z_real_top = bb0.Min.Z + alto_ft_local
        p_ini = XYZ(p_ini.X, p_ini.Y, z_real_top)
        p_fin = XYZ(p_fin.X, p_fin.Y, z_real_top)

    return (p_ini, p_fin, eje_long, eje_ancho, eje_alto,
            ancho_cm, alto_cm, long_total_cm)

def ancho_columna_en_extremo(doc, p_extremo, eje_long):
    """
    Busca una columna estructural cuyo BoundingBox contenga el punto extremo
    del pórtico. Devuelve la dimensión de la columna proyectada sobre el eje
    longitudinal de la viga (en pies). Si no hay columna, 0.
    """
    collector = FilteredElementCollector(doc)
    collector = collector.OfCategory(BuiltInCategory.OST_StructuralColumns)
    collector = collector.WhereElementIsNotElementType()
    columnas  = collector.ToElements()
    if columnas is None:
        return 0.0

    tol = cm_a_pies(5.0)
    col = None
    for cand in columnas:
        bb = cand.get_BoundingBox(None)
        if bb is None:
            continue
        if (bb.Min.X - tol <= p_extremo.X <= bb.Max.X + tol and
            bb.Min.Y - tol <= p_extremo.Y <= bb.Max.Y + tol and
            bb.Min.Z - tol <= p_extremo.Z <= bb.Max.Z + tol):
            col = cand
            break
    if col is None:
        return 0.0

    bb = col.get_BoundingBox(None)
    esquinas = [
        XYZ(bb.Min.X, bb.Min.Y, bb.Min.Z), XYZ(bb.Max.X, bb.Min.Y, bb.Min.Z),
        XYZ(bb.Min.X, bb.Max.Y, bb.Min.Z), XYZ(bb.Max.X, bb.Max.Y, bb.Min.Z),
        XYZ(bb.Min.X, bb.Min.Y, bb.Max.Z), XYZ(bb.Max.X, bb.Min.Y, bb.Max.Z),
        XYZ(bb.Min.X, bb.Max.Y, bb.Max.Z), XYZ(bb.Max.X, bb.Max.Y, bb.Max.Z),
    ]
    # Proyectar las esquinas sobre el eje longitudinal y medir el rango
    proys = [(e - p_extremo).DotProduct(eje_long) for e in esquinas]
    ancho_col_ft = max(proys) - min(proys)
    return ancho_col_ft

def get_seccion_viga(viga):
    """Lee ancho y alto (cm) de la sección de la viga."""
    sym = viga.Symbol
    bip_w = getattr(BuiltInParameter, 'STRUCTURAL_SECTION_COMMON_WIDTH', None)
    bip_h = getattr(BuiltInParameter, 'STRUCTURAL_SECTION_COMMON_HEIGHT', None)
    p_w = sym.get_Parameter(bip_w) if bip_w else None
    p_h = sym.get_Parameter(bip_h) if bip_h else None
    if p_w and p_h and p_w.AsDouble() > 0 and p_h.AsDouble() > 0:
        return pies_a_cm(p_w.AsDouble()), pies_a_cm(p_h.AsDouble())

    ancho_cm = None; alto_cm = None
    for p in sym.Parameters:
        try:
            nombre = p.Definition.Name.lower()
            val = pies_a_cm(p.AsDouble())
            if val <= 0: continue
            if nombre in ('b', 'ancho', 'width', 'base'):
                ancho_cm = val
            elif nombre in ('h', 'alto', 'height', 'peralte', 'd'):
                alto_cm = val
        except Exception:
            pass

    if ancho_cm is None or alto_cm is None:
        bb = viga.get_BoundingBox(None)
        dz = pies_a_cm(bb.Max.Z - bb.Min.Z)
        dx = pies_a_cm(bb.Max.X - bb.Min.X)
        dy = pies_a_cm(bb.Max.Y - bb.Min.Y)
        if alto_cm  is None: alto_cm  = dz
        if ancho_cm is None: ancho_cm = min(dx, dy)
    return ancho_cm, alto_cm

# ─── Recopilar tipos de barra y gancho ────────────────────────────────────────
barra_tipos  = FilteredElementCollector(doc).OfClass(RebarBarType).ToElements()
diametros    = {}
diametros_ft = {}
for bt in barra_tipos:
    nombre = bt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    diametros[nombre] = bt.Id
    dp = bt.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER)
    if dp: diametros_ft[nombre] = dp.AsDouble()

if not diametros:
    forms.alert('No se encontraron tipos de barra en el archivo.', exitscript=True)

gancho_tipos = FilteredElementCollector(doc).OfClass(RebarHookType).ToElements()
ganchos = {'Sin gancho': None}
for gt in gancho_tipos:
    nombre = gt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    ganchos[nombre] = gt.Id

# ─── Valores por defecto ──────────────────────────────────────────────────────
DEF_DIAM_FLEJE   = '10M'
DEF_DIAM_VARILLA = '13M'
DEF_GANCHO_INI   = 'Estándar - 180°.'
DEF_GANCHO_FIN   = 'Estándar - 180°.'

# ─── XAML de la ventana ───────────────────────────────────────────────────────
XAML_VENTANA = """
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acero Longitudinal en Vigas (Portico)"
    Width="410" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">

  <ScrollViewer VerticalScrollBarVisibility="Auto">
  <StackPanel Margin="14">

    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Acero Longitudinal en Vigas (Portico)" FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Instala acero continuo en vigas del mismo portico --- Ados Software" FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
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
            <TextBlock Text="Diametro inferior" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbDiamInf" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Diametro superior" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbDiamSup" Height="28" Padding="4,0"/>
          </StackPanel>
        </Grid>
        <Grid Margin="0,0,0,6">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Diametro intermedio" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbDiamInt" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Recubrimiento (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtRecub" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BFBFBF" BorderThickness="1"/>
          </StackPanel>
        </Grid>
        <TextBlock Text="Diametro de flejes (que ya tiene la viga)" Foreground="#555" Margin="0,0,0,3"/>
        <ComboBox x:Name="cbDiamFleje" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="GANCHOS (ambos en la misma direccion)" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Grid Margin="0,0,0,6">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Gancho inicio" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbGanchoIni" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Gancho fin" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbGanchoFin" Height="28" Padding="4,0"/>
          </StackPanel>
        </Grid>
        <TextBlock Text="Direccion de los ganchos" Foreground="#555" Margin="0,0,0,3"/>
        <ComboBox x:Name="cbDirGancho" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="DISTRIBUCION DE VARILLAS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,4"/>
        <TextBlock Foreground="#777" FontSize="11" Margin="0,0,0,8" TextWrapping="Wrap">
          Cantidad de varillas en cada cara de la seccion de la viga.
        </TextBlock>
        <Grid Margin="0,0,0,6">
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Varillas inferiores" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtCantInf" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BFBFBF" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Varillas superiores" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtCantSup" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BFBFBF" BorderThickness="1"/>
          </StackPanel>
        </Grid>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Niveles intermedios (0 = ninguno)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtNivInt" Text="0" Height="28" Padding="6,4"
                     BorderBrush="#BFBFBF" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Varillas por nivel" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtBarrInt" Text="2" Height="28" Padding="6,4"
                     BorderBrush="#BFBFBF" BorderThickness="1"/>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="VIGAS DEL PORTICO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar vigas en linea"
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
              BorderBrush="#BDBDBD" BorderThickness="1"/>
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear acero"
              Height="34" Cursor="Hand"
              Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
  </ScrollViewer>
</Window>
"""

# Direcciones de gancho disponibles (texto -> ángulo en radianes)
DIRECCIONES_GANCHO = {
    'Hacia abajo': 0.0,
    'Hacia arriba': math.pi,
}

# ─── Ventana ──────────────────────────────────────────────────────────────────
class VentanaAceroVigas(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, XAML_VENTANA, literal_string=True)
        self.vigas = []
        self.aceptado = False

        nombres_diam    = sorted(diametros.keys())
        nombres_ganchos = ['Sin gancho'] + sorted(k for k in ganchos.keys() if k != 'Sin gancho.')
        for n in nombres_diam:
            self.cbDiamInf.Items.Add(n)
            self.cbDiamSup.Items.Add(n)
            self.cbDiamInt.Items.Add(n)
            self.cbDiamFleje.Items.Add(n)
        for n in nombres_ganchos:
            self.cbGanchoIni.Items.Add(n)
            self.cbGanchoFin.Items.Add(n)
        for n in ['Hacia abajo', 'Hacia arriba']:
            self.cbDirGancho.Items.Add(n)

        self._set_default(self.cbDiamInf, DEF_DIAM_VARILLA)
        self._set_default(self.cbDiamSup, DEF_DIAM_VARILLA)
        self._set_default(self.cbDiamInt, DEF_DIAM_VARILLA)
        self._set_default(self.cbDiamFleje, DEF_DIAM_FLEJE)
        self._set_default(self.cbGanchoIni, DEF_GANCHO_INI)
        self._set_default(self.cbGanchoFin, DEF_GANCHO_FIN)
        self.cbDirGancho.SelectedIndex = 0

        self.btnSeleccionar.Click += self.on_seleccionar
        self.btnAceptar.Click     += self.on_aceptar
        self.btnCancelar.Click    += self.on_cancelar

    def _set_default(self, combo, nombre):
        if combo.Items.Contains(nombre):
            combo.SelectedItem = nombre
        elif combo.Items.Count > 0:
            combo.SelectedIndex = 0

    def on_seleccionar(self, sender, args):
        self.Hide()
        try:
            referencias = uidoc.Selection.PickObjects(
                ObjectType.Element,
                'Selecciona las vigas en linea y presiona ENTER')
            id_cat = int(BuiltInCategory.OST_StructuralFraming)
            self.vigas = []
            rechazados = 0
            for ref in referencias:
                elem = doc.GetElement(ref.ElementId)
                if elem.Category.Id.IntegerValue == id_cat:
                    self.vigas.append(ref.ElementId)
                else:
                    rechazados += 1
            if rechazados > 0:
                self.lblContador.Text = 'Vigas: {} ({} ignorados)'.format(len(self.vigas), rechazados)
            else:
                self.lblContador.Text = 'Vigas seleccionadas: {}'.format(len(self.vigas))
        except Exception:
            self.lblContador.Text = 'Seleccion cancelada. Intenta de nuevo.'
        finally:
            self.ShowDialog()

    def on_aceptar(self, sender, args):
        if not self.vigas:
            forms.alert('No seleccionaste ninguna viga.')
            return
        try:
            self.recub    = float(self.txtRecub.Text)
            self.cant_inf = int(float(self.txtCantInf.Text))
            self.cant_sup = int(float(self.txtCantSup.Text))
            self.niv_int  = int(float(self.txtNivInt.Text))
            self.barr_int = int(float(self.txtBarrInt.Text))
        except ValueError:
            forms.alert('Recubrimiento y cantidades deben ser numericos.')
            return
        if self.cant_inf < 2 or self.cant_sup < 2:
            forms.alert('Se necesitan al menos 2 varillas en cara inferior y superior.')
            return
        self.nom_inf   = self.cbDiamInf.SelectedItem
        self.nom_sup   = self.cbDiamSup.SelectedItem
        self.nom_int   = self.cbDiamInt.SelectedItem
        self.nom_fleje = self.cbDiamFleje.SelectedItem
        self.nom_g_ini = self.cbGanchoIni.SelectedItem
        self.nom_g_fin = self.cbGanchoFin.SelectedItem
        self.dir_gancho = self.cbDirGancho.SelectedItem
        self.aceptado = True
        self.Close()

    def on_cancelar(self, sender, args):
        self.aceptado = False
        self.Close()

# ─── Mostrar ventana ──────────────────────────────────────────────────────────
ventana = VentanaAceroVigas()
ventana.ShowDialog()
if not ventana.aceptado:
    script.exit()

vigas_ids = ventana.vigas

# ─── Resolver entradas ────────────────────────────────────────────────────────
recubrimiento_cm = ventana.recub
cant_inf = ventana.cant_inf
cant_sup = ventana.cant_sup
niv_int  = ventana.niv_int
barr_int = ventana.barr_int

nombre_inf   = ventana.nom_inf
nombre_sup   = ventana.nom_sup
nombre_int   = ventana.nom_int
nombre_fleje = ventana.nom_fleje

d_inf_ft   = diametros_ft.get(nombre_inf, cm_a_pies(1.3))
d_sup_ft   = diametros_ft.get(nombre_sup, cm_a_pies(1.3))
d_int_ft   = diametros_ft.get(nombre_int, cm_a_pies(1.3))
d_fleje_ft = diametros_ft.get(nombre_fleje, cm_a_pies(1.0))

bar_type_inf = doc.GetElement(diametros[nombre_inf])
bar_type_sup = doc.GetElement(diametros[nombre_sup])
bar_type_int = doc.GetElement(diametros[nombre_int])

id_g_ini = ganchos.get(ventana.nom_g_ini)
id_g_fin = ganchos.get(ventana.nom_g_fin)
hk_ini = doc.GetElement(id_g_ini) if id_g_ini else None
hk_fin = doc.GetElement(id_g_fin) if id_g_fin else None

ang_gancho = DIRECCIONES_GANCHO.get(ventana.dir_gancho, 0.0)

# Offset base hacia adentro del fleje (recubrimiento + fleje).
# El medio-diámetro de cada barra se suma por capa, ya que varían.
offset_base_ft = cm_a_pies(recubrimiento_cm) + d_fleje_ft

# ─── Geometría del pórtico ────────────────────────────────────────────────────
vigas = [doc.GetElement(eid) for eid in vigas_ids]
(p_ini, p_fin, eje_long, eje_ancho, eje_alto,
 ancho_cm, alto_cm, long_total_cm) = get_geometria_portico(vigas)

# Offset por columna en cada extremo.
# El punto inicial/final cae en el CENTRO de la columna. Lo recorremos hacia
# adentro: (1/2 ancho_columna_en_direccion_viga) - 3cm de recubrimiento.
REC_COL_CM = 3.0

ancho_col_ini_ft = ancho_columna_en_extremo(doc, p_ini, eje_long)
ancho_col_fin_ft = ancho_columna_en_extremo(doc, p_fin, eje_long)

offset_col_ini_ft = ancho_col_ini_ft/2.0 - cm_a_pies(REC_COL_CM) if ancho_col_ini_ft > 0 else 0.0
offset_col_fin_ft = ancho_col_fin_ft/2.0 - cm_a_pies(REC_COL_CM) if ancho_col_fin_ft > 0 else 0.0
if offset_col_ini_ft < 0: offset_col_ini_ft = 0.0
if offset_col_fin_ft < 0: offset_col_fin_ft = 0.0

# Mover p_ini hacia AFUERA (-eje_long) y p_fin hacia AFUERA (+eje_long)
p_ini = XYZ(p_ini.X - eje_long.X*offset_col_ini_ft,
            p_ini.Y - eje_long.Y*offset_col_ini_ft,
            p_ini.Z - eje_long.Z*offset_col_ini_ft)
p_fin = XYZ(p_fin.X + eje_long.X*offset_col_fin_ft,
            p_fin.Y + eje_long.Y*offset_col_fin_ft,
            p_fin.Z + eje_long.Z*offset_col_fin_ft)
long_total_cm = pies_a_cm((p_fin - p_ini).GetLength())

ancho_ft = cm_a_pies(ancho_cm)
alto_ft  = cm_a_pies(alto_cm)

# Posiciones transversales dentro de la sección (centradas en el eje de la viga)
# Eje ancho: de -ancho/2 a +ancho/2 ; eje alto: de -alto/2 a +alto/2
# Pero recordando que el eje de la LocationCurve está arriba (justif. Top),
# así que el centro de sección está alto/2 por debajo del eje.
# Las posiciones útiles dependen del diámetro de cada capa (medio-diámetro).
def semi_ancho_util(d_ft):
    return ancho_ft/2.0 - offset_base_ft - d_ft/2.0
def semi_alto_util(d_ft):
    return alto_ft/2.0 - offset_base_ft - d_ft/2.0

# Centro de la sección respecto al eje de la curva (bajamos medio peralte)
# El eje está en la parte superior -> centro = eje - alto/2 * eje_alto
def punto_seccion(dist_long_ft, u_ancho_ft, v_alto_ft):
    """
    Devuelve un XYZ en coordenadas globales.
    dist_long_ft : distancia a lo largo del pórtico desde p_ini
    u_ancho_ft   : desplazamiento transversal horizontal (eje_ancho)
    v_alto_ft    : desplazamiento vertical respecto al CENTRO de la sección
    """
    # Punto sobre el eje de la curva
    base = XYZ(
        p_ini.X + eje_long.X*dist_long_ft,
        p_ini.Y + eje_long.Y*dist_long_ft,
        p_ini.Z + eje_long.Z*dist_long_ft)
    # Bajar medio peralte para llegar al centro de la sección
    cx = base.X - eje_alto.X*(alto_ft/2.0)
    cy = base.Y - eje_alto.Y*(alto_ft/2.0)
    cz = base.Z - eje_alto.Z*(alto_ft/2.0)
    # Aplicar desplazamientos transversales
    return XYZ(
        cx + eje_ancho.X*u_ancho_ft + eje_alto.X*v_alto_ft,
        cy + eje_ancho.Y*u_ancho_ft + eje_alto.Y*v_alto_ft,
        cz + eje_ancho.Z*u_ancho_ft + eje_alto.Z*v_alto_ft)

long_total_ft = (p_fin - p_ini).GetLength()

# ─── Crear una barra longitudinal ─────────────────────────────────────────────
def crear_barra(viga_host, bar_type, u_ancho_ft, v_alto_ft, num, sep_ft, normal):
    """
    Crea una barra recta de extremo a extremo del pórtico, en la posición
    transversal (u_ancho, v_alto), y la distribuye 'num' veces a lo largo
    de 'normal' con separación sep_ft.
    """
    p0 = punto_seccion(0.0,            u_ancho_ft, v_alto_ft)
    p1 = punto_seccion(long_total_ft,  u_ancho_ft, v_alto_ft)
    rebar = Rebar.CreateFromCurves(
        doc, RebarStyle.Standard, bar_type, hk_ini, hk_fin, viga_host,
        normal,
        [Line.CreateBound(p0, p1)],
        RebarHookOrientation.Right, RebarHookOrientation.Right, True, True)
    if num >= 2:
        rebar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            num, sep_ft, True, True, True)
    # Ambos ganchos en la misma dirección
    orientar_ganchos(rebar, ang_gancho, ang_gancho)
    return rebar

# ─── Transacción ──────────────────────────────────────────────────────────────
viga_host = vigas[0]   # host de las barras (la primera viga del pórtico)
total_barras = 0

with Transaction(doc, 'Acero longitudinal en vigas') as t:
    t.Start()

    # Semi-útiles por capa (dependen del diámetro de cada una)
    sa_inf = semi_ancho_util(d_inf_ft)
    sa_sup = semi_ancho_util(d_sup_ft)
    sa_int = semi_ancho_util(d_int_ft)

    # Niveles verticales: el inferior usa su medio-diámetro, el superior el suyo
    v_inf = -semi_alto_util(d_inf_ft)   # cara inferior
    v_sup = +semi_alto_util(d_sup_ft)   # cara superior

    # ── Cara INFERIOR: distribuir en el ancho (normal = eje_ancho) ──
    if cant_inf >= 2:
        xs_inf = reparto(-sa_inf, sa_inf, cant_inf)
        sep_inf = (xs_inf[-1] - xs_inf[0]) / (cant_inf - 1)
    else:
        xs_inf = [0.0]; sep_inf = 0.0
    crear_barra(viga_host, bar_type_inf, xs_inf[0], v_inf, cant_inf, sep_inf, eje_ancho)
    total_barras += cant_inf

    # ── Cara SUPERIOR ──
    if cant_sup >= 2:
        xs_sup = reparto(-sa_sup, sa_sup, cant_sup)
        sep_sup = (xs_sup[-1] - xs_sup[0]) / (cant_sup - 1)
    else:
        xs_sup = [0.0]; sep_sup = 0.0
    crear_barra(viga_host, bar_type_sup, xs_sup[0], v_sup, cant_sup, sep_sup, eje_ancho)
    total_barras += cant_sup

    # ── Intermedios: filas horizontales en niveles intermedios ──
    # Cada nivel es una fila de 'barr_int' varillas repartidas en el ancho,
    # igual que inferior/superior pero a alturas intermedias.
    if niv_int >= 1 and barr_int >= 1:
        # Alturas de los niveles intermedios (entre inferior y superior, sin extremos)
        vs_niveles = reparto(v_inf, v_sup, niv_int + 2)[1:-1]

        if barr_int >= 2:
            xs_int = reparto(-sa_int, sa_int, barr_int)
            sep_int = (xs_int[-1] - xs_int[0]) / (barr_int - 1)
        else:
            xs_int = [0.0]; sep_int = 0.0

        for v_nivel in vs_niveles:
            crear_barra(viga_host, bar_type_int, xs_int[0], v_nivel, barr_int, sep_int, eje_ancho)
            total_barras += barr_int

    t.Commit()

forms.alert('Acero longitudinal creado.\n{} barras en pórtico de {:.2f} m ({} vigas).'.format(
    total_barras, long_total_cm/100.0, len(vigas)))