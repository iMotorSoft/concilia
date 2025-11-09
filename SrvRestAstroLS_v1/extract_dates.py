
import openpyxl
from datetime import datetime

def extract_date_range(file_path, column_name="A", start_row=3):
    try:
        workbook = openpyxl.load_workbook(file_path)
        sheet = workbook.active
        
        dates = []
        for row_index in range(start_row, sheet.max_row + 1):
            cell_value = sheet[f"{column_name}{row_index}"].value
            if cell_value:
                try:
                    # Attempt to parse various date formats
                    if isinstance(cell_value, datetime):
                        dates.append(cell_value.date())
                    elif isinstance(cell_value, (int, float)):
                        # openpyxl might convert dates to numbers
                        # Assuming Excel's date system (1900-based)
                        dates.append(datetime.fromtimestamp((cell_value - 25569) * 86400).date())
                    else:
                        # Try common string formats
                        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y'):
                            try:
                                dates.append(datetime.strptime(str(cell_value).split(" ")[0], fmt).date())
                                break
                            except ValueError:
                                continue
                except Exception as e:
                    # print(f"Could not parse date from cell {column_name}{row_index}: {cell_value} - {e}")
                    pass

        if dates:
            min_date = min(dates)
            max_date = max(dates)
            print(f"Rango de fechas detectado: Desde {min_date} hasta {max_date}")
        else:
            print("No se encontraron fechas válidas en la columna especificada.")

    except FileNotFoundError:
        print(f"Error: El archivo no se encontró en la ruta: {file_path}")
    except Exception as e:
        print(f"Ocurrió un error: {e}")

if __name__ == "__main__":
    excel_file_path = "/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/SpendIQ/Doc/FCE/Conciliacion/PILAGA PATAGONIA AGOST-SEPT.xlsx"
    extract_date_range(excel_file_path)
