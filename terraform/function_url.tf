# --- Lambda Function URL: MCP Server ---
#
# A Function URL é o endpoint HTTPS que o Integrator chama via SigV4.
# auth_type = AWS_IAM garante que apenas principals com permissão lambda:InvokeFunctionUrl
# e credenciais SigV4 válidas podem acessar.
#
# Nenhuma permission resource-based é criada (não há invoke público).
# O acesso é controlado exclusivamente pela IAM policy do Integrator (iam.tf).

resource "aws_lambda_function_url" "mcp_server" {
  function_name      = aws_lambda_function.mcp_server.function_name
  authorization_type = "AWS_IAM"

  cors {
    allow_origins = [] # Sem CORS — invocação server-to-server apenas
    allow_methods = []
    allow_headers = []
  }
}
