# -*- coding: utf-8 -*-

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import TaskDialog
from pyrevit import revit

doc = revit.doc

# Buscar habitaciones
rooms = FilteredElementCollector(doc)\
    .OfCategory(BuiltInCategory.OST_Rooms)\
    .WhereElementIsNotElementType()\
    .ToElements()

rooms_to_delete = []

# Revisar habitaciones
for room in rooms:
    if room.Area == 0:
        rooms_to_delete.append(room.Id)

# Ejecutar eliminación
if rooms_to_delete:

    t = Transaction(doc, "Eliminar habitaciones con área 0")
    t.Start()

    for room_id in rooms_to_delete:
        doc.Delete(room_id)

    t.Commit()

    # Ventana Revit
    TaskDialog.Show( "Proceso completado","{} habitaciones eliminadas correctamente.".format(len(rooms_to_delete)))

else:

    TaskDialog.Show("Sin resultados", "No se encontraron habitaciones vacías.")