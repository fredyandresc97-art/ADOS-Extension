# -*- coding: utf-8 -*-
"""
Acabados de Muros — Copia Exacta
----------------------------------
Crea un acabado de muro copiando EXACTAMENTE el muro base
(perfil personalizado, remate inclinado, restricciones por cara,
altura variable — todo se hereda) y desplazándolo lateralmente
a la cara seleccionada por el usuario.

La selección y el cálculo de desplazamiento son idénticos al
script "Acabados por Cara": el usuario clica la cara del muro
donde quiere el acabado, y el punto de clic define la posición.

Diferencia clave vs "Acabados por Niveles":
  - No se usan nivel base / restricción superior / desfases.
  - El muro resultante es una copia 1:1 del original desplazada.
  - El tipo de muro del acabado se cambia después de copiar.

Esquinas: se resuelven geométricamente (intersección de líneas)
igual que en el script de niveles.

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
    JoinGeometryUtils, ElementTransformUtils, ElementId
)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# ─────────────────────────────────────────────────────────────
# Conversiones
# ─────────────────────────────────────────────────────────────
def mm_a_ft(mm): return mm / 304.8
def cm_a_ft(cm): return cm / 30.48


# ─────────────────────────────────────────────────────────────
# Filtro: solo caras de muros
# ─────────────────────────────────────────────────────────────
class FiltroCaraMuro(ISelectionFilter):
    def AllowElement(self, elem):
        if elem is None or elem.Category is None:
            return False
        return elem.Category.Id.IntegerValue == int(BuiltInCategory.OST_Walls)
    def AllowReference(self, ref, point):
        return True


# ─────────────────────────────────────────────────────────────
# Tipos de muro disponibles
# ─────────────────────────────────────────────────────────────
wall_types_col = FilteredElementCollector(doc).OfClass(WallType).ToElements()
tipos_muro = {}
for wt in wall_types_col:
    p = wt.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
    if p:
        n = p.AsString()
        if n:
            tipos_muro[n] = wt

if not tipos_muro:
    SW.MessageBox.Show('No se encontraron tipos de muro.', 'Error',
                       SW.MessageBoxButton.OK, SW.MessageBoxImage.Error)
    import sys; sys.exit()

nombres_muro     = sorted(tipos_muro.keys())
DEFAULT_ACABADO  = 'TARRAJEO'
idx_default_muro = (nombres_muro.index(DEFAULT_ACABADO)
                    if DEFAULT_ACABADO in nombres_muro else 0)


# ─────────────────────────────────────────────────────────────
# XAML — sin niveles ni desfases, solo tipo de acabado
# ─────────────────────────────────────────────────────────────
XAML = u"""
<Window
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
    Title="Acabados \u2014 Copia Exacta"
    Width="460" SizeToContent="Height"
    ResizeMode="NoResize"
    WindowStartupLocation="CenterScreen"
    Background="#F0F2F5"
    FontFamily="Segoe UI" FontSize="12">
  <StackPanel Margin="14">

    <!-- Encabezado -->
    <Border Background="#F9B233" CornerRadius="6" Padding="14,10" Margin="0,0,0,12">
      <StackPanel>
        <TextBlock Text="Acabados de Muros \u2014 Copia Exacta"
                   FontSize="15" FontWeight="Bold" Foreground="Black"/>
        <TextBlock Text="Copia el muro base y lo desplaza a la cara seleccionada  \u2014  Ados Software"
                   FontSize="10" Foreground="#000000" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>

    <!-- Tipo de acabado -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="TIPO DE MURO ACABADO" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <ComboBox x:Name="cbTipoMuro" Height="28" Padding="4,0"/>
      </StackPanel>
    </Border>

    <!-- Info -->
    <Border Background="#FFF8E7" CornerRadius="6" Padding="10,8" Margin="0,0,0,8"
            BorderBrush="#F9B233" BorderThickness="1">
      <StackPanel>
        <TextBlock FontSize="10" Foreground="#555" TextWrapping="Wrap"
          Text="El acabado ser\u00e1 una copia exacta del muro base: mismo perfil, mismo remate inclinado, mismas restricciones. Solo se cambia el tipo de muro y se desplaza a la cara seleccionada."/>
        <TextBlock FontSize="10" Foreground="#922B21" TextWrapping="Wrap" Margin="0,6,0,0"
          Text="\u26a0  Selecciona todas las caras en una sola operaci\u00f3n para que las esquinas se resuelvan autom\u00e1ticamente."/>
      </StackPanel>
    </Border>

    <!-- Selección -->
    <Border Background="White" CornerRadius="6" Padding="12" Margin="0,0,0,8"
            BorderBrush="#BFBFBF" BorderThickness="1">
      <StackPanel>
        <TextBlock Text="CARAS SELECCIONADAS" FontSize="10" FontWeight="Bold"
                   Foreground="#000000" Margin="0,0,0,8"/>
        <Button x:Name="btnSeleccionar"
                Content="Seleccionar Caras de Muros en Revit"
                Height="32" Cursor="Hand"
                Background="#FDE3B5" Foreground="#000000"
                FontWeight="SemiBold" BorderBrush="#F9B233" BorderThickness="1"/>
        <TextBlock x:Name="lblContador" Text="Ninguna cara seleccionada."
                   Foreground="#999" FontSize="11"
                   HorizontalAlignment="Center" Margin="0,6,0,0"/>
      </StackPanel>
    </Border>

    <!-- Botones -->
    <Grid Margin="0,4,0,0">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="*"/>
        <ColumnDefinition Width="10"/>
        <ColumnDefinition Width="2*"/>
      </Grid.ColumnDefinitions>
      <Button x:Name="btnCancelar" Grid.Column="0" Content="Cancelar"
              Height="34" Cursor="Hand" Background="#EEEEEE" Foreground="#555"
              BorderBrush="#BFBFBF" BorderThickness="1"/>
      <Button x:Name="btnAceptar" Grid.Column="2" Content="Crear Copias"
              Height="34" Cursor="Hand" Background="#F9B233" Foreground="Black"
              FontWeight="Bold" BorderThickness="0"/>
    </Grid>

  </StackPanel>
</Window>
"""


# ─────────────────────────────────────────────────────────────
# Formulario
# ─────────────────────────────────────────────────────────────
class FormCopiaExacta(object):
    def __init__(self):
        self.resultado = None
        self.caras     = []

        reader   = XmlReader.Create(StringReader(XAML))
        self.win = XamlReader.Load(reader)

        self.cbTipoMuro  = self.win.FindName('cbTipoMuro')
        self.lblContador = self.win.FindName('lblContador')

        for n in nombres_muro:
            self.cbTipoMuro.Items.Add(n)
        self.cbTipoMuro.SelectedIndex = idx_default_muro

        self.win.FindName('btnSeleccionar').Click += self.OnSeleccionar
        self.win.FindName('btnCancelar').Click    += self.OnCancelar
        self.win.FindName('btnAceptar').Click     += self.OnAceptar

    def OnSeleccionar(self, sender, e):
        self.win.Hide()
        self.caras = []
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Face,
                FiltroCaraMuro(),
                u'Clica las caras de muro \u2014 Enter para confirmar')

            muros_set = set()
            for ref in refs:
                wall = doc.GetElement(ref.ElementId)
                if wall is None:
                    continue
                self.caras.append({
                    'wall_id':      ref.ElementId,
                    'global_point': ref.GlobalPoint,
                    'orient_ext':   wall.Orientation,
                })
                muros_set.add(ref.ElementId.IntegerValue)

            n  = len(self.caras)
            nm = len(muros_set)
            self.lblContador.Text = (
                u'{} cara(s) en {} muro(s).'.format(n, nm) if n > 0
                else u'No se reconocieron caras v\u00e1lidas.')
        except Exception:
            self.lblContador.Text = u'Selecci\u00f3n cancelada.'
        self.win.ShowDialog()

    def OnAceptar(self, sender, e):
        if not self.caras:
            SW.MessageBox.Show(u'No hay caras seleccionadas.',
                u'Aviso', SW.MessageBoxButton.OK, SW.MessageBoxImage.Warning)
            return
        self.resultado = {
            'tipo_nombre': self.cbTipoMuro.SelectedItem,
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
form = FormCopiaExacta()
res  = form.show()
if res is None:
    import sys; sys.exit()

tipo_muro_obj = tipos_muro[res['tipo_nombre']]
tipo_muro_id  = tipo_muro_obj.Id
caras_data    = form.caras

# Espesor del acabado (para centrar el eje de la copia)
espesor_acabado_ft = mm_a_ft(0.0)
try:
    cp = tipo_muro_obj.get_Parameter(BuiltInParameter.WALL_ATTR_WIDTH_PARAM)
    if cp:
        espesor_acabado_ft = cp.AsDouble()
except Exception:
    pass


# ─────────────────────────────────────────────────────────────
# Utilidades geométricas
# ─────────────────────────────────────────────────────────────
def proyectar_sobre_linea_xy(punto, linea):
    p0    = linea.GetEndPoint(0)
    p1    = linea.GetEndPoint(1)
    dir_l = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0.0)
    lng   = dir_l.GetLength()
    if lng < 1e-6:
        return p0
    dir_l = dir_l.Normalize()
    v = XYZ(punto.X - p0.X, punto.Y - p0.Y, 0.0)
    t = v.DotProduct(dir_l)
    return XYZ(p0.X + dir_l.X * t, p0.Y + dir_l.Y * t, punto.Z)


def dir_xy(linea):
    p0 = linea.GetEndPoint(0)
    p1 = linea.GetEndPoint(1)
    v  = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0.0)
    lg = v.GetLength()
    return v.Normalize() if lg > 1e-6 else XYZ(1, 0, 0)


def interseccion_lineas_xy(p0, d0, p1, d1):
    dx  = p1.X - p0.X
    dy  = p1.Y - p0.Y
    det = d0.X * (-d1.Y) - d0.Y * (-d1.X)
    if abs(det) < 1e-9:
        return None
    t  = (dx * (-d1.Y) - dy * (-d1.X)) / det
    return XYZ(p0.X + t * d0.X, p0.Y + t * d0.Y, p0.Z)


def extremo_mas_cercano_pt(ci, punto):
    """ci es dict con 'vec' (XYZ de traslación) y 'loc_curve' (Line original)."""
    lc = ci['loc_curve']
    dx = ci['vec'].X
    dy = ci['vec'].Y
    p0_orig = lc.GetEndPoint(0)
    p1_orig = lc.GetEndPoint(1)
    p0 = XYZ(p0_orig.X + dx, p0_orig.Y + dy, p0_orig.Z)
    p1 = XYZ(p1_orig.X + dx, p1_orig.Y + dy, p1_orig.Z)
    d0 = math.sqrt((p0.X-punto.X)**2 + (p0.Y-punto.Y)**2)
    d1 = math.sqrt((p1.X-punto.X)**2 + (p1.Y-punto.Y)**2)
    return (0, d0) if d0 <= d1 else (1, d1)


# ─────────────────────────────────────────────────────────────
# Paso 1: calcular vector de traslación para cada cara
# ─────────────────────────────────────────────────────────────
# El vector es puramente horizontal (X, Y) — la copia mantiene
# su Z original (hereda el perfil del muro base).
traslaciones = []   # lista de dicts con info de traslación

for cara in caras_data:
    wall = doc.GetElement(cara['wall_id'])
    if wall is None:
        traslaciones.append(None)
        continue

    orient_ext = cara['orient_ext']
    gp         = cara['global_point']
    loc_curve  = wall.Location.Curve

    # Sentido: exterior (+1) o interior (-1)
    p_proy   = proyectar_sobre_linea_xy(gp, loc_curve)
    vec_clic = XYZ(gp.X - p_proy.X, gp.Y - p_proy.Y, 0.0)
    dot      = vec_clic.DotProduct(orient_ext)
    sentido  = 1 if dot >= 0 else -1

    # Distancia desde LocationCurve a la cara + semiespesor del acabado
    dist_lc_a_cara = vec_clic.GetLength()
    semi           = espesor_acabado_ft / 2.0
    d_total        = dist_lc_a_cara + semi

    # Vector de traslación (solo X, Y — Z se preserva de la copia)
    vec = XYZ(
        orient_ext.X * sentido * d_total,
        orient_ext.Y * sentido * d_total,
        0.0
    )

    traslaciones.append({
        'wall_id':   cara['wall_id'],
        'vec':       vec,
        'sentido':   sentido,
        'loc_curve': loc_curve,
        'dir':       dir_xy(loc_curve),
    })


# ─────────────────────────────────────────────────────────────
# Paso 2: ajustar esquinas geométricamente
# ─────────────────────────────────────────────────────────────
# Para cada par que forma esquina, calculamos la intersección
# de las líneas desplazadas y ajustamos el extremo más cercano.
# En "copia exacta" el ajuste se hace moviendo la LocationCurve
# ANTES de copiar, alargando o acortando el muro copiado.

TOL_ESQUINA = cm_a_ft(60.0)

n_tr = len(traslaciones)

# Precalcular p0/p1 desplazados de cada curva para la detección
def pts_desplazados(ti):
    lc = ti['loc_curve']
    dx = ti['vec'].X
    dy = ti['vec'].Y
    p0 = lc.GetEndPoint(0)
    p1 = lc.GetEndPoint(1)
    return (XYZ(p0.X + dx, p0.Y + dy, p0.Z),
            XYZ(p1.X + dx, p1.Y + dy, p1.Z))

# Guardamos ajustes de extremos: {i: {0: XYZ_nuevo, 1: XYZ_nuevo}}
ajustes = {i: {} for i in range(n_tr)}

for i in range(n_tr):
    ti = traslaciones[i]
    if ti is None:
        continue
    for j in range(i + 1, n_tr):
        tj = traslaciones[j]
        if tj is None:
            continue
        if ti['wall_id'].IntegerValue == tj['wall_id'].IntegerValue:
            continue

        # Paralelos → sin esquina
        cross = ti['dir'].X * tj['dir'].Y - ti['dir'].Y * tj['dir'].X
        if abs(cross) < 0.1:
            continue

        # Puntos desplazados
        pi0, pi1 = pts_desplazados(ti)
        pj0, pj1 = pts_desplazados(tj)

        # Intersección de las dos líneas infinitas desplazadas
        pt_cruz = interseccion_lineas_xy(pi0, ti['dir'], pj0, tj['dir'])
        if pt_cruz is None:
            continue

        # Distancia del cruce a los extremos más cercanos
        di0 = math.sqrt((pi0.X-pt_cruz.X)**2 + (pi0.Y-pt_cruz.Y)**2)
        di1 = math.sqrt((pi1.X-pt_cruz.X)**2 + (pi1.Y-pt_cruz.Y)**2)
        dj0 = math.sqrt((pj0.X-pt_cruz.X)**2 + (pj0.Y-pt_cruz.Y)**2)
        dj1 = math.sqrt((pj1.X-pt_cruz.X)**2 + (pj1.Y-pt_cruz.Y)**2)

        idx_i = 0 if di0 <= di1 else 1
        dist_i = di0 if idx_i == 0 else di1
        idx_j = 0 if dj0 <= dj1 else 1
        dist_j = dj0 if idx_j == 0 else dj1

        if dist_i > TOL_ESQUINA or dist_j > TOL_ESQUINA:
            continue

        # Guardar nuevo extremo (en coordenadas del muro SIN desplazar,
        # porque lo aplicaremos como nueva LocationCurve antes de copiar)
        dx_i = ti['vec'].X
        dy_i = ti['vec'].Y
        dx_j = tj['vec'].X
        dy_j = tj['vec'].Y

        # El cruce está en coordenadas desplazadas → restar el vector para
        # obtener el extremo en coordenadas originales del muro base
        ajustes[i][idx_i] = XYZ(pt_cruz.X - dx_i, pt_cruz.Y - dy_i, 0.0)
        ajustes[j][idx_j] = XYZ(pt_cruz.X - dx_j, pt_cruz.Y - dy_j, 0.0)


# ─────────────────────────────────────────────────────────────
# Paso 3: copiar y trasladar cada muro
# ─────────────────────────────────────────────────────────────
creados       = 0
errores       = 0
detalle       = []
muros_creados = []

with Transaction(doc, u'Acabados \u2014 Copia Exacta') as t:
    t.Start()

    for idx, ti in enumerate(traslaciones):
        if ti is None:
            errores += 1
            detalle.append(u'Cara {}: muro no encontrado.'.format(idx))
            muros_creados.append(None)
            continue
        try:
            wall = doc.GetElement(ti['wall_id'])

            # ── Copiar el muro ────────────────────────────────────────────
            ids = System.Collections.Generic.List[ElementId]()
            ids.Add(ti['wall_id'])
            nuevos_ids = ElementTransformUtils.CopyElements(
                doc, ids, XYZ(0, 0, 0))   # copia en el mismo sitio

            if not nuevos_ids or nuevos_ids.Count == 0:
                raise Exception(u'CopyElements no devolvió elementos.')

            muro_copia = doc.GetElement(nuevos_ids[0])

            # ── Cambiar el tipo al acabado seleccionado ───────────────────
            muro_copia.ChangeTypeId(tipo_muro_id)

            # ── Ajustar extremos de la LocationCurve si hay esquina ───────
            loc_orig = wall.Location.Curve
            p0_orig  = loc_orig.GetEndPoint(0)
            p1_orig  = loc_orig.GetEndPoint(1)

            aj = ajustes.get(idx, {})
            if aj:
                # Reconstruir los extremos con los ajustes de esquina
                if 0 in aj:
                    p0_nuevo = XYZ(aj[0].X, aj[0].Y, p0_orig.Z)
                else:
                    p0_nuevo = p0_orig
                if 1 in aj:
                    p1_nuevo = XYZ(aj[1].X, aj[1].Y, p1_orig.Z)
                else:
                    p1_nuevo = p1_orig

                if p0_nuevo.DistanceTo(p1_nuevo) > mm_a_ft(10.0):
                    nueva_curva = Line.CreateBound(p0_nuevo, p1_nuevo)
                    muro_copia.Location.Curve = nueva_curva

            # ── Trasladar lateralmente ────────────────────────────────────
            vec = ti['vec']
            ElementTransformUtils.MoveElement(doc, muro_copia.Id, vec)

            muros_creados.append(muro_copia)
            creados += 1

        except Exception as ex:
            detalle.append(u'Cara {}: {}'.format(idx, str(ex)))
            errores += 1
            muros_creados.append(None)

    t.Commit()


# ─────────────────────────────────────────────────────────────
# Paso 4: Join acabados↔base y acabados entre sí
# ─────────────────────────────────────────────────────────────
def bboxes_solapan(bb1, bb2):
    tol = mm_a_ft(5.0)
    return (bb1.Min.X - tol < bb2.Max.X and
            bb1.Max.X + tol > bb2.Min.X and
            bb1.Min.Y - tol < bb2.Max.Y and
            bb1.Max.Y + tol > bb2.Min.Y)


def hacer_join(elem_a, elem_b):
    try:
        if JoinGeometryUtils.AreElementsJoined(doc, elem_a, elem_b):
            return True
        bb1 = elem_a.get_BoundingBox(None)
        bb2 = elem_b.get_BoundingBox(None)
        if bb1 and bb2 and bboxes_solapan(bb1, bb2):
            JoinGeometryUtils.JoinGeometry(doc, elem_a, elem_b)
            return True
    except Exception:
        pass
    return False


unidos       = 0
muros_validos = [(i, m) for i, m in enumerate(muros_creados) if m is not None]

if muros_validos:
    with Transaction(doc, u'Join \u2014 Acabados Copia') as t2:
        t2.Start()

        for i, muro_ac in muros_validos:
            if i >= len(caras_data):
                continue
            muro_base = doc.GetElement(caras_data[i]['wall_id'])
            if muro_base and hacer_join(muro_base, muro_ac):
                unidos += 1

        for a, (i, mi) in enumerate(muros_validos):
            for b, (j, mj) in enumerate(muros_validos):
                if b <= a:
                    continue
                if hacer_join(mi, mj):
                    unidos += 1

        t2.Commit()


# ─────────────────────────────────────────────────────────────
# Resumen
# ─────────────────────────────────────────────────────────────
msg = (u'Copias creadas   : {}\n'
       u'Uniones aplicadas: {}\n'
       u'Errores          : {}').format(creados, unidos, errores)
if detalle:
    msg += u'\n\nDetalle:\n' + u'\n'.join(detalle[:10])
    if len(detalle) > 10:
        msg += u'\n... y {} m\u00e1s.'.format(len(detalle) - 10)

SW.MessageBox.Show(msg, u'Resultado \u2014 Acabados Copia Exacta',
                   SW.MessageBoxButton.OK, SW.MessageBoxImage.Information)