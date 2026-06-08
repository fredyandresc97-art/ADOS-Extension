# -*- coding: utf-8 -*-
"""
Generacion Automatica de Planos v1
Elaborado por: Ing. Andres Angel  -  Ados Software
"""
import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xml')

import re
import System.Windows as SW
from System.Windows.Markup import XamlReader
from System.Xml import XmlReader
from System.IO import StringReader

from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, BuiltInParameter,
    Transaction, SubTransaction, ViewSheet
)

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# ─────────────────────────────────────────────────────────────
# Tipos de hoja (TitleBlock)
# ─────────────────────────────────────────────────────────────
tipos_hoja = {}
for _tb in (FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_TitleBlocks)
            .WhereElementIsElementType()
            .ToElements()):
    try:
        _p_fam  = _tb.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
        _p_type = _tb.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        _fn = _p_fam.AsString()  if _p_fam  else u''
        _tn = _p_type.AsString() if _p_type else u''
        _nombre = u'{} : {}'.format(_fn, _tn).strip(u' :')
        if not _nombre:
            _nombre = u'TitleBlock-{}'.format(_tb.Id.IntegerValue)
        tipos_hoja[_nombre] = _tb
    except: pass

if not tipos_hoja:
    SW.MessageBox.Show(
        u'No se encontraron tipos de hoja (TitleBlock) en el proyecto.',
        u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

nombres_hoja = sorted(tipos_hoja.keys())

# Numeros de plano ya existentes en el proyecto
numeros_existentes = set(
    s.SheetNumber
    for s in FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
)

# ─────────────────────────────────────────────────────────────
# Utilidades de identificador
# ─────────────────────────────────────────────────────────────
def parsear_id(texto):
    """Devuelve (prefijo, numero_inicial, padding, sufijo)."""
    m = re.search(r'^(.*?)(\d+)(\D*)$', texto.strip())
    if not m:
        return texto.strip(), 1, 3, u''
    return m.group(1), int(m.group(2)), len(m.group(2)), m.group(3)

def generar_ids(texto, cantidad):
    prefix, start, padding, suffix = parsear_id(texto)
    return [u'{}{}{}'.format(prefix, str(start + i).zfill(padding), suffix)
            for i in range(cantidad)]

# ─────────────────────────────────────────────────────────────
# XAML
# ─────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Generacion de Planos"
    Width="500" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">
  <StackPanel Margin="14">

    <Border Background="#2D6EC8" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Generacion Automatica de Planos"
                   FontSize="15" FontWeight="Bold" Foreground="White"/>
        <TextBlock Text="Crea planos con numeracion automatica  -  Ados Software"
                   FontSize="10" Foreground="#CCDFF5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="TAMANO DE HOJA" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbHoja" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="3*"/>
          <ColumnDefinition Width="12"/>
          <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>
        <StackPanel Grid.Column="0">
          <TextBlock Text="NOMBRE DEL PLANO" FontSize="10" FontWeight="Bold"
                     Foreground="#000000" Margin="0,0,0,8"/>
          <TextBox x:Name="txtNombre" Height="28" Padding="4,4"
                   BorderBrush="#BFBFBF" BorderThickness="1"
                   Text="PLANTA ARQUITECTONICA"/>
        </StackPanel>
        <StackPanel Grid.Column="2">
          <TextBlock Text="CANTIDAD" FontSize="10" FontWeight="Bold"
                     Foreground="#000000" Margin="0,0,0,8"/>
          <TextBox x:Name="txtCantidad" Height="28" Padding="4,4"
                   BorderBrush="#BFBFBF" BorderThickness="1"
                   Text="1" TextAlignment="Center"/>
        </StackPanel>
      </Grid>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="IDENTIFICADOR INICIAL" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <TextBox x:Name="txtId" Height="28" Padding="4,4"
                 BorderBrush="#BFBFBF" BorderThickness="1"
                 Text="Pl-ARQ-001"/>
        <TextBlock Text="El numero final se incrementa por cada plano generado."
                   FontSize="9" Foreground="#999" Margin="0,5,0,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock x:Name="lblPreview" Text="VISTA PREVIA" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ListBox x:Name="lstPreview" MaxHeight="150" FontSize="11"
                 BorderBrush="#EEEEEE" BorderThickness="1"
                 Background="#FAFAFA" FontFamily="Consolas"/>
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
      <Button x:Name="btnCrear" Grid.Column="2" Content="Crear Planos"
              Height="34" Cursor="Hand" Background="#2D6EC8" Foreground="White"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
</Window>
"""

# ─────────────────────────────────────────────────────────────
# Formulario
# ─────────────────────────────────────────────────────────────
class FormPlanos(object):
    def __init__(self):
        self.resultado = None

        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.cbHoja      = self.win.FindName('cbHoja')
        self.txtCantidad = self.win.FindName('txtCantidad')
        self.txtNombre   = self.win.FindName('txtNombre')
        self.txtId       = self.win.FindName('txtId')
        self.lstPreview  = self.win.FindName('lstPreview')
        self.lblPreview  = self.win.FindName('lblPreview')

        for n in nombres_hoja:
            self.cbHoja.Items.Add(n)
        self.cbHoja.SelectedIndex = 0

        self.txtCantidad.TextChanged += self.ActualizarPreview
        self.txtId.TextChanged       += self.ActualizarPreview
        self.txtNombre.TextChanged   += self.ActualizarPreview

        self.win.FindName('btnCancelar').Click += self.OnCancelar
        self.win.FindName('btnCrear').Click    += self.OnCrear

        self.ActualizarPreview(None, None)

    def ActualizarPreview(self, sender, e):
        self.lstPreview.Items.Clear()
        try:
            cant = int(self.txtCantidad.Text.strip() or '0')
        except ValueError:
            self.lblPreview.Text = u'VISTA PREVIA  -  cantidad invalida'
            self.lblPreview.Foreground = SW.Media.Brushes.DarkRed
            return

        if cant < 1 or cant > 500:
            self.lblPreview.Text = u'VISTA PREVIA  -  rango valido: 1 a 500'
            self.lblPreview.Foreground = SW.Media.Brushes.DarkRed
            return

        id_texto = self.txtId.Text.strip() or u'PL-001'
        nombre   = self.txtNombre.Text.strip() or u'-'
        ids      = generar_ids(id_texto, cant)

        conflictos = sum(1 for x in ids if x in numeros_existentes)
        if conflictos:
            self.lblPreview.Text = u'VISTA PREVIA  -  {} plano(s)  |  {} conflicto(s) [!]'.format(
                cant, conflictos)
            self.lblPreview.Foreground = SW.Media.Brushes.DarkRed
        else:
            self.lblPreview.Text = u'VISTA PREVIA  -  {} plano(s)'.format(cant)
            self.lblPreview.Foreground = SW.Media.Brushes.Black

        for sid in ids:
            marca = u'  [!] ya existe' if sid in numeros_existentes else u''
            self.lstPreview.Items.Add(u'{}   {}{}'.format(sid, nombre, marca))

    def _validar(self):
        try:
            cant = int(self.txtCantidad.Text.strip())
        except ValueError:
            SW.MessageBox.Show(u'La cantidad debe ser un numero entero.',
                u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return None
        if cant < 1 or cant > 500:
            SW.MessageBox.Show(u'La cantidad debe estar entre 1 y 500.',
                u'Error', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return None

        nombre = self.txtNombre.Text.strip()
        if not nombre:
            SW.MessageBox.Show(u'Ingresa un nombre de plano.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return None

        id_texto = self.txtId.Text.strip()
        if not id_texto:
            SW.MessageBox.Show(u'Ingresa un identificador inicial.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return None

        ids = generar_ids(id_texto, cant)
        conflictos = [x for x in ids if x in numeros_existentes]
        if conflictos:
            msg = (u'Los siguientes identificadores ya existen en el proyecto:\n\n'
                   + u'\n'.join(conflictos[:10])
                   + (u'\n...' if len(conflictos) > 10 else u'')
                   + u'\n\nAjusta el identificador inicial.')
            SW.MessageBox.Show(msg, u'Conflicto de identificadores',
                SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return None

        return {
            'tipo_hoja': tipos_hoja[self.cbHoja.SelectedItem],
            'cantidad':  cant,
            'nombre':    nombre,
            'ids':       ids,
        }

    def OnCrear(self, sender, e):
        res = self._validar()
        if res is None: return
        self.resultado = res
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
form = FormPlanos()
res  = form.show()
if res is None:
    import sys; sys.exit()

tipo_hoja = res['tipo_hoja']
nombre    = res['nombre']
ids       = res['ids']

# ─────────────────────────────────────────────────────────────
# Crear planos en Revit
# ─────────────────────────────────────────────────────────────
creados = 0
errores = []

with Transaction(doc, u'Generar Planos') as t:
    t.Start()
    for sheet_num in ids:
        st = SubTransaction(doc)
        st.Start()
        try:
            sheet = ViewSheet.Create(doc, tipo_hoja.Id)
            sheet.SheetNumber = sheet_num
            p_name = sheet.get_Parameter(BuiltInParameter.SHEET_NAME)
            if p_name and not p_name.IsReadOnly:
                p_name.Set(nombre)
            st.Commit()
            creados += 1
        except Exception as ex:
            st.RollBack()
            errores.append(u'{}  ->  {}'.format(sheet_num, str(ex)[:80]))
    t.Commit()

# ─────────────────────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────────────────────
msg = u'Planos creados : {}\nErrores        : {}'.format(creados, len(errores))
if errores:
    msg += u'\n\nDetalle:\n' + u'\n'.join(errores[:10])

SW.MessageBox.Show(msg, u'Resultado - Generacion de Planos',
                   SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)
