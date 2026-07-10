@echo off
:: Duplo-clique para iniciar a app
:: Inicia servidor HTTP na porta 8080 e abre o navegador

echo.
echo ========================================
echo   POC Bedrock - Iniciando app local
echo ========================================
echo.

cd /d "%~dp0"

:: Abrir navegador com delay
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8080/connect-bedrock-widget-test.html"

:: Iniciar servidor
echo   URL: http://localhost:8080/connect-bedrock-widget-test.html
echo   Feche esta janela para parar o servidor.
echo.
cd demo
python -m http.server 8080 --bind 127.0.0.1
