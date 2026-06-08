# -*- coding: utf-8 -*-
# Botón en UN SOLO archivo: la ventana WPF va incrustada como texto (XAML_VENTANA)
# y se carga desde el mismo script. Toda la lógica de refuerzo y las calibraciones
# de gancho son las de la versión definitiva; lo único distinto respecto a esa
# versión es el formulario (antes rpw, ahora ventana WPF incrustada).
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
import math
from Autodesk.Revit.DB import (FilteredElementCollector, BuiltInParameter, BuiltInCategory, Transaction, XYZ, Line)
from Autodesk.Revit.DB.Structure import (RebarBarType, RebarHookType, Rebar, RebarStyle, RebarHookOrientation)
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import forms, script

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# ─── Conversiones ─────────────────────────────────────────────────────────────
def cm_a_pies(cm):
    """Convierte centímetros a pies (unidad interna de Revit). 1 pie = 30.48 cm."""
    return cm / 30.48

def pies_a_cm(pies):
    """Convierte pies a centímetros."""
    return pies * 30.48

# ─── Reparto uniforme de posiciones ───────────────────────────────────────────
def reparto(a, b, n):
    """Devuelve n posiciones uniformes entre a y b (inclusive).

    Si n == 1 devuelve el punto medio. Se usa para ubicar las varillas a lo
    largo de cada dimensión de la sección.
    """
    if n <= 1:
        return [(a + b) / 2.0]
    paso = (b - a) / (n - 1)
    return [a + paso * i for i in range(n)]

# ─── Orientación del gancho ───────────────────────────────────────────────────
def orientar_ganchos(rebar, ang_inicio, ang_final):
    """Fija la rotación de los ganchos de la barra (en RADIANES).

    - ang_inicio -> 'Rotación del gancho al inicio' = gancho INFERIOR.
    - ang_final  -> 'Rotación del gancho al final'  = gancho SUPERIOR.
    Pasa None en cualquiera de los dos para NO modificarlo.
    Recordatorio: 180° = math.pi rad. Los nombres de parámetro dependen del
    idioma del modelo (aquí, español). Ver  # [GANCHO]  en el cuerpo del script.
    """
    for p in rebar.Parameters:
        if ang_inicio is not None and p.Definition.Name == 'Rotación del gancho al inicio' and not p.IsReadOnly:
            p.Set(ang_inicio)
        if ang_final is not None and p.Definition.Name == 'Rotación del gancho al final' and not p.IsReadOnly:
            p.Set(ang_final)

# ─── Recopilar tipos de barra y de gancho del modelo ──────────────────────────
barra_tipos   = FilteredElementCollector(doc).OfClass(RebarBarType).ToElements()
diametros     = {}   # nombre -> ElementId
diametros_ft  = {}   # nombre -> diámetro en pies
for bt in barra_tipos:
    nombre = bt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    diametros[nombre] = bt.Id
    dia_param = bt.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER)
    if dia_param:
        diametros_ft[nombre] = dia_param.AsDouble()

if not diametros:
    forms.alert('No se encontraron tipos de barra en el archivo.', exitscript=True)

gancho_tipos = FilteredElementCollector(doc).OfClass(RebarHookType).ToElements()
ganchos = {'Sin gancho': None}
for gt in gancho_tipos:
    nombre = gt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString()
    ganchos[nombre] = gt.Id

# ─── Valores por defecto del formulario ───────────────────────────────────────

DEF_DIAM_FLEJE   = '10M'
DEF_DIAM_VARILLA = '13M'
DEF_GANCHO_INF   = 'Estándar - 90°.'
DEF_GANCHO_SUP   = 'Sin gancho'


ROT_INF_IZQ_CON_SUP = math.pi   # con gancho superior -> inferior afuera
ROT_INF_IZQ_SIN_SUP = 0.0       # sin gancho superior -> inferior afuera
ROT_SUP_IZQ         = math.pi   # gancho superior hacia adentro (si existe)
# -- Grupo derecho (cara X máxima, exterior = +X), espejo del izquierdo:
ROT_INF_DER_CON_SUP = 0.0       # con gancho superior -> inferior afuera (por confirmar)
ROT_INF_DER_SIN_SUP = math.pi   # sin gancho superior -> inferior afuera
ROT_SUP_DER         = 0.0       # gancho superior hacia adentro (si existe, por confirmar)
# -- Grupos intermedios por cara (distribuidos en X). Exterior = -Y (cara inferior)
#    y +Y (cara superior). Calibrado: el gancho inferior sale hacia afuera.
ROT_INF_CARAINF_CON_SUP = 0.0       # cara Y mínima, con gancho superior
ROT_INF_CARAINF_SIN_SUP = math.pi   # cara Y mínima, sin gancho superior
ROT_SUP_CARAINF         = 0.0       # gancho superior cara Y mínima (si existe)
ROT_INF_CARASUP_CON_SUP = math.pi   # cara Y máxima, con gancho superior
ROT_INF_CARASUP_SIN_SUP = 0.0       # cara Y máxima, sin gancho superior
ROT_SUP_CARASUP         = math.pi   # gancho superior cara Y máxima (si existe)

# ─── Ventana WPF incrustada (XAML como texto) ─────────────────────────────────
XAML_VENTANA = """
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acero Longitudinal en Columnas"
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
        <TextBlock Text="Acero Longitudinal en Columnas" FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Instala refuerzo longitudinal --- Ados Software" FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <!-- Barra y recubrimiento -->
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
            <TextBlock Text="Diametro de varilla" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbDiamVarilla" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Recubrimiento (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtRecub" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BFBFBF" BorderThickness="1"/>
          </StackPanel>
        </Grid>
        <TextBlock Text="Diametro de flejes" Foreground="#555" Margin="0,0,0,3"/>
        <ComboBox x:Name="cbDiamFleje" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <!-- Ganchos -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="GANCHOS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Gancho inferior" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbGanchoInf" Height="28" Padding="4,0"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Gancho superior" Foreground="#555" Margin="0,0,0,3"/>
            <ComboBox x:Name="cbGanchoSup" Height="28" Padding="4,0"/>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <!-- Distribucion de varillas -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="DISTRIBUCION DE VARILLAS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,4"/>
        <TextBlock Foreground="#777" FontSize="11" Margin="0,0,0,8" TextWrapping="Wrap">
          Cantidad de varillas por cara en cada direccion.
        </TextBlock>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Varillas en X (por cara)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtCantX" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Varillas en Y (por cara)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtCantY" Text="3" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <!-- Longitudes de desarrollo -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="LONGITUDES DE DESARROLLO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,4"/>
        <TextBlock Foreground="#777" FontSize="11" Margin="0,0,0,8" TextWrapping="Wrap">
          Extension de la barra mas alla de la columna (0 = sin extender).
        </TextBlock>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="10"/>
            <ColumnDefinition Width="*"/>
          </Grid.ColumnDefinitions>
          <StackPanel Grid.Column="0">
            <TextBlock Text="Desarrollo inferior (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtDesInf" Text="0" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
          <StackPanel Grid.Column="2">
            <TextBlock Text="Desarrollo superior (cm)" Foreground="#555" Margin="0,0,0,3"/>
            <TextBox x:Name="txtDesSup" Text="0" Height="28" Padding="6,4"
                     BorderBrush="#BDBDBD" BorderThickness="1"/>
          </StackPanel>
        </Grid>
      </StackPanel>
    </Border>

    <!-- Seleccion columnas -->
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
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear acero"
              Height="34" Cursor="Hand"
              Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
  </ScrollViewer>
</Window>
"""

# ─── Ventana WPF (reemplaza al formulario rpw) ────────────────────────────────
class VentanaAceroColumnas(forms.WPFWindow):
    """Crea la ventana a partir del XAML incrustado y conecta los eventos."""

    def __init__(self):
        forms.WPFWindow.__init__(self, XAML_VENTANA, literal_string=True)
        self.columnas = []
        self.aceptado = False

        nombres_diam = sorted(diametros.keys())
        nombres_ganchos = ['Sin gancho'] + sorted(k for k in ganchos.keys() if k != 'Sin gancho')
        for n in nombres_diam:
            self.cbDiamVarilla.Items.Add(n)
            self.cbDiamFleje.Items.Add(n)
        for n in nombres_ganchos:
            self.cbGanchoInf.Items.Add(n)
            self.cbGanchoSup.Items.Add(n)

        self._set_default(self.cbDiamVarilla, DEF_DIAM_VARILLA)
        self._set_default(self.cbDiamFleje, DEF_DIAM_FLEJE)
        self._set_default(self.cbGanchoInf, DEF_GANCHO_INF)
        self._set_default(self.cbGanchoSup, DEF_GANCHO_SUP)

        self.btnSeleccionar.Click += self.on_seleccionar
        self.btnAceptar.Click += self.on_aceptar
        self.btnCancelar.Click += self.on_cancelar

    def _set_default(self, combo, nombre):
        """Preselecciona `nombre` si existe; si no, la primera opción."""
        if combo.Items.Contains(nombre):
            combo.SelectedItem = nombre
        elif combo.Items.Count > 0:
            combo.SelectedIndex = 0

    def on_seleccionar(self, sender, args):
        """Oculta la ventana, deja elegir columnas estructurales y reaparece."""
        self.Hide()
        try:
            referencias = uidoc.Selection.PickObjects(
                ObjectType.Element,
                'Selecciona las columnas y presiona ENTER para confirmar')
            id_cat = int(BuiltInCategory.OST_StructuralColumns)
            self.columnas = []
            rechazados = 0
            for ref in referencias:
                elem = doc.GetElement(ref.ElementId)
                if elem.Category.Id.IntegerValue == id_cat:
                    self.columnas.append(ref.ElementId)
                else:
                    rechazados += 1
            if rechazados > 0:
                self.lblContador.Text = 'Columnas: {} ({} ignorados)'.format(len(self.columnas), rechazados)
            else:
                self.lblContador.Text = 'Columnas seleccionadas: {}'.format(len(self.columnas))
        except Exception:
            self.lblContador.Text = 'Seleccion cancelada. Intenta de nuevo.'
        finally:
            self.ShowDialog()

    def on_aceptar(self, sender, args):
        """Valida, guarda los valores y cierra la ventana."""
        if not self.columnas:
            forms.alert('No seleccionaste ninguna columna.')
            return
        try:
            self.recub   = float(self.txtRecub.Text)
            self.des_inf = float(self.txtDesInf.Text)
            self.des_sup = float(self.txtDesSup.Text)
            self.cant_x  = int(float(self.txtCantX.Text))
            self.cant_y  = int(float(self.txtCantY.Text))
        except ValueError:
            forms.alert('Recubrimiento, desarrollos y cantidades deben ser numericos.')
            return
        if self.cant_x < 2 or self.cant_y < 2:
            forms.alert('Se necesitan al menos 2 varillas por cara en X y en Y.')
            return
        self.nom_var   = self.cbDiamVarilla.SelectedItem
        self.nom_fleje = self.cbDiamFleje.SelectedItem
        self.nom_g_inf = self.cbGanchoInf.SelectedItem
        self.nom_g_sup = self.cbGanchoSup.SelectedItem
        self.aceptado = True
        self.Close()

    def on_cancelar(self, sender, args):
        self.aceptado = False
        self.Close()

# ─── Mostrar ventana ──────────────────────────────────────────────────────────
# ─── Mostrar ventana ──────────────────────────────────────────────────────────
ventana = VentanaAceroColumnas()
ventana.ShowDialog()

if not ventana.aceptado:
    script.exit()   # salida limpia de pyRevit (no abre la consola de salida)

columnas_seleccionadas = ventana.columnas

# ─── Resolver entradas ────────────────────────────────────────────────────────
recubrimiento_cm  = ventana.recub
desarrollo_inf_cm = ventana.des_inf
desarrollo_sup_cm = ventana.des_sup
cant_x = ventana.cant_x
cant_y = ventana.cant_y

# Diámetros de varilla y de fleje (en pies) a partir de la selección.
nombre_var   = ventana.nom_var
nombre_fleje = ventana.nom_fleje
d_var_ft   = diametros_ft.get(nombre_var, cm_a_pies(1.3))
d_fleje_ft = diametros_ft.get(nombre_fleje, cm_a_pies(1.0))
bar_type_var = doc.GetElement(diametros[nombre_var])

id_g_inf = ganchos.get(ventana.nom_g_inf)
id_g_sup = ganchos.get(ventana.nom_g_sup)
hk_inf = doc.GetElement(id_g_inf) if id_g_inf else None
hk_sup = doc.GetElement(id_g_sup) if id_g_sup else None

# Desplazamiento del eje de la varilla hacia adentro (queda dentro del fleje).
offset_ft = cm_a_pies(recubrimiento_cm) + d_fleje_ft + d_var_ft / 2.0

# ─── Función auxiliar: crear un conjunto de varillas verticales ───────────────
def crear_set_vertical(columna, x, y_ini, num, sep_ft, z_bot, z_top, ang_inicio, ang_final, normal=None):
    """Crea un conjunto de `num` varillas verticales.

    La barra semilla se ubica en (x, y_ini) y el conjunto se distribuye a lo
    largo de `normal` (por defecto +Y) con separación `sep_ft`. Si num == 1 se
    crea una sola barra (sin distribución). `ang_inicio` y `ang_final` definen la
    rotación de los ganchos inferior y superior (None = no tocar).
    """
    if normal is None:
        normal = XYZ(0, 1, 0)   # por defecto, distribución a lo largo de Y
    p_bot = XYZ(x, y_ini, z_bot)
    p_top = XYZ(x, y_ini, z_top)
    rebar = Rebar.CreateFromCurves(
        doc, RebarStyle.Standard, bar_type_var, hk_inf, hk_sup, columna,
        normal,
        [Line.CreateBound(p_bot, p_top)],
        RebarHookOrientation.Right, RebarHookOrientation.Right, True, True
    )
    if num >= 2:
        rebar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
            num, sep_ft, True, True, True)
    orientar_ganchos(rebar, ang_inicio, ang_final)   # [GANCHO] punto de calibración
    return rebar

# ─── Transacción ──────────────────────────────────────────────────────────────
with Transaction(doc, 'Acero longitudinal en columnas') as t:
    t.Start()

    for eid in columnas_seleccionadas:
        columna = doc.GetElement(eid)

        bbox = columna.get_BoundingBox(None)
        xmin, xmax = bbox.Min.X, bbox.Max.X
        ymin, ymax = bbox.Min.Y, bbox.Max.Y
        z_base, z_tope = bbox.Min.Z, bbox.Max.Z

        # Cota inferior/superior de las varillas: se extienden por desarrollo.
        z_bot = z_base - cm_a_pies(desarrollo_inf_cm)   # hacia la zapata / col. inferior
        z_top = z_tope + cm_a_pies(desarrollo_sup_cm)   # hacia arriba

        # Posiciones de las varillas dentro del fleje.
        xpos = reparto(xmin + offset_ft, xmax - offset_ft, cant_x)
        ypos = reparto(ymin + offset_ft, ymax - offset_ft, cant_y)

        y_ini = ypos[0]
        y_fin = ypos[-1]
        sep_borde = (y_fin - y_ini) / (cant_y - 1)   # separación de los conjuntos de borde

        hay_gancho_sup = hk_sup is not None
        if hay_gancho_sup:
            ang_inf_izq = ROT_INF_IZQ_CON_SUP
            ang_sup_izq = ROT_SUP_IZQ
        else:
            ang_inf_izq = ROT_INF_IZQ_SIN_SUP
            ang_sup_izq = None
        crear_set_vertical(columna, xpos[0], y_ini, cant_y, sep_borde, z_bot, z_top, ang_inf_izq, ang_sup_izq)

        if cant_x >= 3:
            x_int_ini = xpos[1]       # primera posición intermedia en X
            x_int_fin = xpos[-2]      # última posición intermedia en X
            num_int   = cant_x - 2    # cantidad de barras por cara intermedia
            sep_int   = (x_int_fin - x_int_ini) / (num_int - 1) if num_int >= 2 else 0.0
            normal_x  = XYZ(1, 0, 0)  # distribución a lo largo de X

            # Cara Y mínima (inferior, exterior = -Y)
            if hay_gancho_sup:
                ang_inf_ci, ang_sup_ci = ROT_INF_CARAINF_CON_SUP, ROT_SUP_CARAINF
            else:
                ang_inf_ci, ang_sup_ci = ROT_INF_CARAINF_SIN_SUP, None
            crear_set_vertical(columna, x_int_ini, ypos[0], num_int, sep_int,
                               z_bot, z_top, ang_inf_ci, ang_sup_ci, normal_x)

            # Cara Y máxima (superior, exterior = +Y)
            if hay_gancho_sup:
                ang_inf_cs, ang_sup_cs = ROT_INF_CARASUP_CON_SUP, ROT_SUP_CARASUP
            else:
                ang_inf_cs, ang_sup_cs = ROT_INF_CARASUP_SIN_SUP, None
            crear_set_vertical(columna, x_int_ini, ypos[-1], num_int, sep_int,
                               z_bot, z_top, ang_inf_cs, ang_sup_cs, normal_x)

        if hay_gancho_sup:
            ang_inf_der = ROT_INF_DER_CON_SUP
            ang_sup_der = ROT_SUP_DER
        else:
            ang_inf_der = ROT_INF_DER_SIN_SUP
            ang_sup_der = None
        crear_set_vertical(columna, xpos[-1], y_ini, cant_y, sep_borde, z_bot, z_top, ang_inf_der, ang_sup_der)

    t.Commit()

forms.alert('Acero longitudinal creado en {} columna(s).'.format(len(columnas_seleccionadas)))