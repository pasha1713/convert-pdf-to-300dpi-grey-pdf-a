@echo off
for %%f in (*_pdfa.pdf) do (
    set "name=%%~nf"
    setlocal enabledelayedexpansion
    set "name=!name:_pdfa=!"
    move "%%f" "!name!.pdf"
    endlocal
)