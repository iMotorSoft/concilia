BSD

source .venv/bin/activate

rm -rf .venv           # limpiar entorno
uv cache prune         # (opcional) limpiar caché
uv sync                # recrear entorno según pyproject
uv run python ls_iMotorSoft_Srv01.py  # correr tu app



rsync -avz \
    /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/clientA/dist/ \
    administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/concilia/SrvRestAstroLS_v1/clientA/dist/
    
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude '*.pyc' --exclude '_uploads' --exclude 'storage' --exclude 'clientA/' --exclude '.env' --exclude '.venv/' /media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/concilia/SrvRestAstroLS_v1/ administrator@imotorsoft.com:/home/administrator/project/iMotorSoft/ai/concilia/SrvRestAstroLS_v1/  


