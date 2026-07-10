"""
Servidor HTTP local para testar o widget de chat.

Uso:
    python scripts/serve_demo.py

Acesse: http://localhost:8080/connect-bedrock-widget-test.html
"""

import http.server
import os
import sys

PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo")


def main() -> None:
    os.chdir(DIRECTORY)
    handler = http.server.SimpleHTTPRequestHandler
    with http.server.HTTPServer(("127.0.0.1", PORT), handler) as httpd:
        print(f"Servindo demo/ em http://localhost:{PORT}/")
        print(f"Abra: http://localhost:{PORT}/connect-bedrock-widget-test.html")
        print("Ctrl+C para parar")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado.")
            sys.exit(0)


if __name__ == "__main__":
    main()
