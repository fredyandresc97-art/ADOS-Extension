# -*- coding: utf-8 -*-
"""
Acotado de Elementos Estructurales v4
Cadena: |ancho1| gap |ancho2| gap |ancho3|
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
    FilteredElementCollector, BuiltInCategory, ElementId,
    Transaction,
    Line, XYZ, ReferenceArray,
    DimensionType, DimensionStyleType, ViewPlan, Grid,
    Options, Solid, PlanarFace, GeometryInstance, UV
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
# Primer tipo de cota lineal
# ─────────────────────────────────────────────────────────────
dim_type = None
for _dt in FilteredElementCollector(doc).OfClass(DimensionType).ToElements():
    try:
        if _dt.StyleType == DimensionStyleType.Linear:
            dim_type = _dt; break
    except: pass

if dim_type is None:
    TaskDialog.Show(u'Error', u'No se encontro un tipo de cota lineal en el proyecto.')
    import sys; sys.exit()

# ─────────────────────────────────────────────────────────────
# Categorias
# ─────────────────────────────────────────────────────────────
CATEGORIAS = {
    u'Zapatas':  BuiltInCategory.OST_StructuralFoundation,
    u'Columnas': BuiltInCategory.OST_StructuralColumns,
}
nombres_cat = [u'Zapatas', u'Columnas']

# ─────────────────────────────────────────────────────────────
# Filtros de seleccion
# ─────────────────────────────────────────────────────────────
class FiltroEje(ISelectionFilter):
    def AllowElement(self, elem): return isinstance(elem, Grid)
    def AllowReference(self, ref, point): return True

class FiltroElementos(ISelectionFilter):
    def __init__(self, bic):
        self.cat_id = ElementId(bic)
    def AllowElement(self, elem):
        return (elem.Category is not None and
                elem.Category.Id == self.cat_id)
    def AllowReference(self, ref, point): return True

# ─────────────────────────────────────────────────────────────
# Direccion dominante del eje
# ─────────────────────────────────────────────────────────────
def direction_from_grid(grid):
    p0 = grid.Curve.GetEndPoint(0)
    p1 = grid.Curve.GetEndPoint(1)
    return XYZ(0, 1, 0) if abs(p1.Y - p0.Y) >= abs(p1.X - p0.X) else XYZ(1, 0, 0)

# ─────────────────────────────────────────────────────────────
# Referencias de cara extrema en la direccion dada
#
# Recorre el solido del elemento buscando caras PlanarFace cuya
# normal apunte en la direccion de medicion (umbral 0.5).
# Devuelve (min_pos, ref_min, max_pos, ref_max) o None.
# ─────────────────────────────────────────────────────────────
def get_extent_refs(element, direction):
    """
    Devuelve (min_pos, ref_min, max_pos, ref_max) para las caras extremas
    en la direccion indicada, o None si no se encuentran referencias validas.

    Estrategia doble:
      1. GetInstanceGeometry()  - geometria transformada, refs en espacio proyecto.
      2. GetSymbolGeometry()    - geometria del simbolo + transform manual de posicion.
         Necesario cuando la familia tiene geometria anidada y las refs de instancia
         son None (caso comun en algunas familias de zapatas).
    """
    opts = Options()
    opts.ComputeReferences        = True
    opts.IncludeNonVisibleObjects = True

    # Acumula (posicion_en_direccion, Reference)
    collected = []

    def scan_face(face, pos_point):
        """Agrega la cara a collected si tiene normal alineada y ref valida."""
        if not isinstance(face, PlanarFace): return
        if abs(face.FaceNormal.DotProduct(direction)) < 0.5: return
        ref = face.Reference
        if ref is None: return
        collected.append((pos_point.DotProduct(direction), ref))

    def scan_solid_instance(solid):
        """Recorre las caras de un solido de GetInstanceGeometry."""
        if solid.Volume <= 1e-9: return
        for face in solid.Faces:
            try:
                bb  = face.GetBoundingBox()
                mid = UV((bb.Min.U + bb.Max.U) * 0.5,
                         (bb.Min.V + bb.Max.V) * 0.5)
                scan_face(face, face.Evaluate(mid))
            except: pass

    def scan_solid_symbol(solid, transform):
        """
        Recorre las caras de un solido de GetSymbolGeometry.
        Aplica el transform del GeometryInstance para obtener
        la posicion en espacio proyecto.
        """
        if solid.Volume <= 1e-9: return
        for face in solid.Faces:
            if not isinstance(face, PlanarFace): continue
            # La normal debe evaluarse en espacio proyecto
            world_normal = transform.OfVector(face.FaceNormal)
            if abs(world_normal.DotProduct(direction)) < 0.5: continue
            ref = face.Reference
            if ref is None: continue
            try:
                bb  = face.GetBoundingBox()
                mid = UV((bb.Min.U + bb.Max.U) * 0.5,
                         (bb.Min.V + bb.Max.V) * 0.5)
                # Transformar el punto del simbolo al espacio proyecto
                world_pt = transform.OfPoint(face.Evaluate(mid))
                collected.append((world_pt.DotProduct(direction), ref))
            except: pass

    def walk_instance(geom_inst):
        """Recorre un GeometryInstance: primero por instancia, luego por simbolo."""
        n_before = len(collected)

        # --- estrategia 1: geometria de instancia (refs en espacio proyecto) ---
        try:
            for sub in geom_inst.GetInstanceGeometry():
                if isinstance(sub, Solid):
                    scan_solid_instance(sub)
                elif isinstance(sub, GeometryInstance):
                    walk_instance(sub)          # recursion para familias anidadas
        except: pass

        # --- estrategia 2 (fallback): geometria de simbolo + transform ----------
        # Solo si la estrategia 1 no encontro ninguna referencia valida
        if len(collected) == n_before:
            try:
                t = geom_inst.Transform
                for sub in geom_inst.GetSymbolGeometry():
                    if isinstance(sub, Solid):
                        scan_solid_symbol(sub, t)
            except: pass

    try:
        for item in element.get_Geometry(opts):
            if isinstance(item, Solid):
                scan_solid_instance(item)       # familia de sistema
            elif isinstance(item, GeometryInstance):
                walk_instance(item)             # familia cargada / anidada
    except: pass

    if len(collected) < 2:
        return None

    collected.sort(key=lambda x: x[0])
    mn_pos, mn_ref = collected[0]
    mx_pos, mx_ref = collected[-1]

    if abs(mx_pos - mn_pos) < 1e-6:
        return None

    return mn_pos, mn_ref, mx_pos, mx_ref

# ─────────────────────────────────────────────────────────────
# XAML — identidad Ados
# ─────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acotado de Elementos Estructurales"
    Width="460" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">
  <StackPanel Margin="14">

    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Acotado de Elementos Estructurales"
                   FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Cadena: ancho + separacion por elemento  -  Ados Software"
                   FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="CATEGORIA" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbCategoria" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="1. EJE DE REFERENCIA  (define la direccion)" FontSize="10"
                   FontWeight="Bold" Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnEje" Content="Seleccionar eje en Revit"
                Height="32" Cursor="Hand" Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblEje" Text="Ningun eje seleccionado."
                   Foreground="#999" FontSize="11" HorizontalAlignment="Center"
                   Margin="0,6,0,0" TextWrapping="Wrap"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="2. ELEMENTOS A ACOTAR" FontSize="10"
                   FontWeight="Bold" Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnElems" Content="Seleccionar elementos en Revit"
                Height="32" Cursor="Hand" Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblElems" Text="Ningun elemento seleccionado."
                   Foreground="#999" FontSize="11" HorizontalAlignment="Center"
                   Margin="0,6,0,0" TextWrapping="Wrap"/>
      </StackPanel>
    </Border>

    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,12"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="LADO DE LA COTA" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbLado" Height="28" Padding="4,0"/>
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
LADOS_Y = [u'Izquierda', u'Derecha']
LADOS_X = [u'Arriba',    u'Abajo']

class FormAcotado(object):
    def __init__(self):
        self.resultado = None
        self.direction = None
        self.elementos = []

        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.cbCategoria = self.win.FindName('cbCategoria')
        self.cbLado      = self.win.FindName('cbLado')
        self.lblEje      = self.win.FindName('lblEje')
        self.lblElems    = self.win.FindName('lblElems')

        for n in nombres_cat:
            self.cbCategoria.Items.Add(n)
        self.cbCategoria.SelectedIndex = 0

        for op in LADOS_Y:
            self.cbLado.Items.Add(op)
        self.cbLado.SelectedIndex = 0

        self.win.FindName('btnEje').Click      += self.OnSelEje
        self.win.FindName('btnElems').Click    += self.OnSelElems
        self.win.FindName('btnCancelar').Click += self.OnCancelar
        self.win.FindName('btnAcotar').Click   += self.OnAcotar

    def _set_lados(self, es_y):
        self.cbLado.Items.Clear()
        for op in (LADOS_Y if es_y else LADOS_X):
            self.cbLado.Items.Add(op)
        self.cbLado.SelectedIndex = 0

    def OnSelEje(self, sender, e):
        self.win.Hide()
        try:
            ref  = uidoc.Selection.PickObject(
                ObjectType.Element, FiltroEje(),
                u'Selecciona el eje que define la direccion de acotado')
            grid           = doc.GetElement(ref.ElementId)
            self.direction = direction_from_grid(grid)
            es_y = self.direction.Y > 0.5
            self._set_lados(es_y)
            self.lblEje.Foreground = SW.Media.Brushes.DarkGreen
            self.lblEje.Text = u'Eje "{}"  —  {}  (acota en {})'.format(
                grid.Name,
                u'Vertical'   if es_y else u'Horizontal',
                u'Y'          if es_y else u'X')
        except Exception as ex:
            if 'Cancel' in str(ex) or 'Escape' in str(ex):
                self.lblEje.Text = u'Seleccion cancelada.'
            else:
                self.lblEje.Foreground = SW.Media.Brushes.DarkRed
                self.lblEje.Text = u'Error: {}'.format(str(ex)[:100])
        self.win.ShowDialog()

    def OnSelElems(self, sender, e):
        cat_nombre = self.cbCategoria.SelectedItem
        bic        = CATEGORIAS[cat_nombre]
        self.win.Hide()
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, FiltroElementos(bic),
                u'Selecciona los {} a acotar (Enter para confirmar)'.format(
                    cat_nombre.lower()))
            self.elementos = [doc.GetElement(r.ElementId) for r in refs]
            if self.elementos:
                self.lblElems.Foreground = SW.Media.Brushes.DarkGreen
                self.lblElems.Text = u'{} {} seleccionado(s).'.format(
                    len(self.elementos), cat_nombre.lower())
            else:
                self.lblElems.Text = u'No se seleccionaron elementos.'
        except Exception as ex:
            if 'Cancel' in str(ex) or 'Escape' in str(ex):
                self.lblElems.Text = u'Seleccion cancelada.'
            else:
                self.lblElems.Foreground = SW.Media.Brushes.DarkRed
                self.lblElems.Text = u'Error: {}'.format(str(ex)[:100])
        self.win.ShowDialog()

    def OnAcotar(self, sender, e):
        if self.direction is None:
            SW.MessageBox.Show(u'Selecciona el eje primero.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        if not self.elementos:
            SW.MessageBox.Show(u'Selecciona al menos un elemento.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = {
            'cat_nombre': self.cbCategoria.SelectedItem,
            'direction':  self.direction,
            'lado':       self.cbLado.SelectedItem,
            'elementos':  self.elementos,
        }
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
form = FormAcotado()
res  = form.show()
if res is None:
    import sys; sys.exit()

cat_nombre = res['cat_nombre']
direction  = res['direction']
lado       = res['lado']
elementos  = res['elementos']
mide_en_y  = direction.Y > 0.5

# ─────────────────────────────────────────────────────────────
# Obtener referencias por elemento y ordenar
# ─────────────────────────────────────────────────────────────
datos   = []
sin_ref = []

for elem in elementos:
    dato = get_extent_refs(elem, direction)
    if dato is None:
        sin_ref.append(elem.Id.IntegerValue)
        continue
    mn, rn, mx, rx = dato
    datos.append({'mn': mn, 'rn': rn, 'mx': mx, 'rx': rx})

if not datos:
    TaskDialog.Show(u'Sin geometria',
        u'No se obtuvieron referencias de cara en ningun elemento.\n\n'
        u'IDs sin referencia: {}\n\n'
        u'Posibles causas:\n'
        u'- La familia no tiene geometria solida visible\n'
        u'- Las caras estan orientadas en otra direccion'.format(
            str(sin_ref[:10])))
    import sys; sys.exit()

# Avisar si algunos elementos no se procesaron pero continuar
if sin_ref:
    TaskDialog.Show(u'Advertencia',
        u'{} elemento(s) sin referencias de cara fueron omitidos.\n'
        u'IDs: {}'.format(len(sin_ref), str(sin_ref[:10])))

# Ordenar por posicion minima en la direccion
datos.sort(key=lambda d: d['mn'])

# ─────────────────────────────────────────────────────────────
# ReferenceArray: [mn1, mx1, mn2, mx2, ...]
# Revit crea la cadena: |ancho1| gap |ancho2| gap |ancho3|
# ─────────────────────────────────────────────────────────────
refs = ReferenceArray()
for d in datos:
    refs.Append(d['rn'])
    refs.Append(d['rx'])

# ─────────────────────────────────────────────────────────────
# Linea de la cota (proporcional a la escala de la vista)
# ─────────────────────────────────────────────────────────────
scale = 100.0
try: scale = float(view.Scale)
except: pass
offset_ft = scale * 10.0 / 304.8   # 10 mm en papel → modelo
pad_ft    = scale *  5.0 / 304.8   #  5 mm en papel → modelo

z = 0.0
try:
    if hasattr(view, 'GenLevel') and view.GenLevel:
        z = view.GenLevel.Elevation
except: pass

# Bounding box del conjunto de elementos seleccionados
all_xs, all_ys = [], []
for e in elementos:
    try:
        bb = e.get_BoundingBox(view) or e.get_BoundingBox(None)
        if bb:
            all_xs += [bb.Min.X, bb.Max.X]
            all_ys += [bb.Min.Y, bb.Max.Y]
    except: pass

x_min = min(all_xs) if all_xs else 0.0
x_max = max(all_xs) if all_xs else 0.0
y_min = min(all_ys) if all_ys else 0.0
y_max = max(all_ys) if all_ys else 0.0

pos_min = datos[0]['mn']
pos_max = datos[-1]['mx']

if mide_en_y:
    # Linea vertical (paralela a Y)
    x_cota  = (x_min - offset_ft) if lado == u'Izquierda' else (x_max + offset_ft)
    p_start = XYZ(x_cota, pos_min - pad_ft, z)
    p_end   = XYZ(x_cota, pos_max + pad_ft, z)
else:
    # Linea horizontal (paralela a X)
    y_cota  = (y_max + offset_ft) if lado == u'Arriba' else (y_min - offset_ft)
    p_start = XYZ(pos_min - pad_ft, y_cota, z)
    p_end   = XYZ(pos_max + pad_ft, y_cota, z)

dim_line = Line.CreateBound(p_start, p_end)

# ─────────────────────────────────────────────────────────────
# Crear cota
# ─────────────────────────────────────────────────────────────
error_msg = u''
creada    = False

try:
    with Transaction(doc, u'Acotado de Elementos Estructurales') as t:
        t.Start()
        try:
            doc.Create.NewDimension(view, dim_line, refs, dim_type)
            t.Commit()
            creada = True
        except Exception as ex:
            error_msg = str(ex)
            try: t.RollBack()
            except: pass
except Exception as ex:
    error_msg = str(ex)

# ─────────────────────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────────────────────
if creada:
    TaskDialog.Show(u'Acotado de Elementos Estructurales',
        u'Cota creada correctamente.\n\n'
        u'Categoria  : {}\n'
        u'Elementos  : {}\n'
        u'Segmentos  : {}  (anchos + huecos)\n'
        u'Span total : {:.3f} m'.format(
            cat_nombre,
            len(datos),
            len(datos) * 2 - 1,
            (pos_max - pos_min) * 0.3048))
else:
    TaskDialog.Show(u'Error al crear la cota',
        u'NewDimension fallo:\n\n{}\n\n'
        u'Referencias encontradas: {}\n'
        u'Elementos procesados: {}'.format(
            error_msg, refs.Size, len(datos)))
