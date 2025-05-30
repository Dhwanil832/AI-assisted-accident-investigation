# runserver.ps1

# (1) Temporarily allow this script to run in this session
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

# (2) Activate your venv
& "$PSScriptRoot\venv\Scripts\Activate.ps1"

# (3) Launch Django’s development server
python.exe "$PSScriptRoot\manage.py" runserver
