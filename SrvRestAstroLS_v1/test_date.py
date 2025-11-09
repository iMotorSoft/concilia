import pandas as pd

# Ajustá el nombre del archivo si es necesario
archivo = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/PILAGA PATAGONIA AGOST-SEPT.xlsx"

# Leemos la hoja activa (o poné el nombre si sabés cuál es)
df = pd.read_excel(archivo, sheet_name=None)  # lee todas las hojas

# Buscamos la hoja que tenga la columna "Fecha"
for hoja, data in df.items():
    if "Fecha" in data.columns:
        # Convertimos a datetime y limpiamos NaT
        data["Fecha"] = pd.to_datetime(data["Fecha"], errors="coerce")
        fechas = data["Fecha"].dropna()
        if not fechas.empty:
            print(f"Hoja: {hoja}")
            print("Fecha inicial:", fechas.min().strftime("%d/%m/%Y"))
            print("Fecha final:  ", fechas.max().strftime("%d/%m/%Y"))
            break
else:
    print("No se encontró columna 'Fecha' en ninguna hoja.")
