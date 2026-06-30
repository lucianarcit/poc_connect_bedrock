# Implementation Plan: POC Bedrock Converse

## Overview

Este plano implementa a substituição da camada MCP pela integração direta com a Amazon Bedrock Converse API no pipeline de chat do Amazon Connect. A implementação é dividida em 11 fases sequenciais, cada uma com gate de aprovação antes de avançar.

**Linguagem:** Python 3.12
**Infraestrutura:** Terraform (HCL)
**Testes:** pytest + Hypothesis (PBT)

## Tasks

### Fase 0 — Segurança e Inventário

- [x] 0. Confirmar isolamento antes de qualquer implementação
  - [x] 0.1 Confirmar branch e repositório
    - **Objetivo:** Verificar que estamos no repositório correto e na branch dedicada à POC Bedrock
    - **Arquivos:** N/A (verificação git)
    - **Dependências:** Nenhuma
    - **Passos:**
      1. Executar `git remote -v` e confirmar repositório `poc_connect_bedrock`
      2. Executar `git branch --show-current` e confirmar branch dedicada
      3. Registrar nome da branch para referência
    - **Testes:** Output do git corresponde ao esperado
    - **Critério de conclusão:** Branch e repositório confirmados documentalmente
    - **Requisitos:** 15.4

  - [x] 0.2 Confirmar ausência de terraform.tfstate da POC MCP
    - **Objetivo:** Garantir que nenhum estado Terraform da POC MCP foi copiado para este projeto
    - **Arquivos:** `terraform/` (verificação)
    - **Dependências:** 0.1
    - **Passos:**
      1. Verificar se existe `terraform/terraform.tfstate` — deve estar ausente ou pertencer à POC Bedrock
      2. Verificar conteúdo de qualquer `.tfstate` existente por referências a `connect-mcp-poc`
      3. Verificar `.terraform/` por estado remoto apontando para MCP
    - **Testes:** Nenhum arquivo `.tfstate` contém referências a `connect-mcp-poc`
    - **Critério de conclusão:** Ausência de estado MCP confirmada
    - **Requisitos:** 9.11, 15.1

  - [x] 0.3 Confirmar ausência de backend remoto compartilhado
    - **Objetivo:** Garantir que o backend Terraform não aponta para estado da POC MCP
    - **Arquivos:** `terraform/providers.tf`, `terraform/terraform.tf`
    - **Dependências:** 0.1
    - **Passos:**
      1. Inspecionar `providers.tf` e `terraform.tf` por configuração de backend
      2. Se houver backend remoto (S3, etc.), confirmar que a key/path é exclusiva da POC Bedrock
      3. Se backend local, confirmar que o estado pertence à POC Bedrock
    - **Testes:** Backend não referencia prefixo `connect-mcp-poc`
    - **Critério de conclusão:** Independência de backend confirmada
    - **Requisitos:** 9.1, 9.11, 15.1

  - [x] 0.4 Confirmar prefixo de recurso atual
    - **Objetivo:** Verificar que `terraform/locals.tf` usa o prefixo `connect-bedrock-poc`
    - **Arquivos:** `terraform/locals.tf`
    - **Dependências:** 0.1
    - **Passos:**
      1. Ler `terraform/locals.tf` e buscar definição de prefixo
      2. Confirmar que o valor é `connect-bedrock-poc` (não `connect-mcp-poc`)
      3. Se ainda estiver `connect-mcp-poc`, registrar como pendência para Fase 4
    - **Testes:** Prefixo em locals.tf é `connect-bedrock-poc` ou está marcado para alteração
    - **Critério de conclusão:** Estado atual do prefixo documentado
    - **Requisitos:** 9.2, 15.2

  - [x] 0.5 Inventariar arquivos MCP a serem removidos deste repositório
    - **Objetivo:** Listar todos os arquivos e referências MCP que devem ser removidos da POC Bedrock (sem afetar POC MCP original)
    - **Arquivos:** `src/shared/mcp_client/`, `src/mcp_server/`, `terraform/function_url.tf`, `scripts/smoke_test_mcp.ps1`, `scripts/diagnose_mcp.ps1`
    - **Dependências:** 0.1
    - **Passos:**
      1. Listar arquivos em `src/shared/mcp_client/` — candidatos a remoção
      2. Listar arquivos em `src/mcp_server/` — candidatos a remoção
      3. Listar referências a MCP em `terraform/` (function_url.tf, iam.tf, lambda.tf, outputs.tf)
      4. Listar scripts MCP em `scripts/` (smoke_test_mcp.ps1, diagnose_mcp.ps1)
      5. Documentar lista completa para execução na Fase 3 e Fase 4
    - **Testes:** Lista completa produzida sem omissões
    - **Critério de conclusão:** Inventário MCP completo e documentado
    - **Requisitos:** 9.4, 9.5, 15.4

  - [x] 0.6 Confirmar valores existentes de infraestrutura
    - **Objetivo:** Confirmar que os valores de configuração da infraestrutura estão corretos para replicação
    - **Arquivos:** `terraform/variables.tf`, `src/integrator/config.py`
    - **Dependências:** 0.1
    - **Passos:**
      1. Confirmar: Integrator timeout = 60s (`var.integrator_timeout`)
      2. Confirmar: SQS visibility timeout = 360s (`var.sqs_visibility_timeout`)
      3. Confirmar: Lease duration = 90s (`var.lease_duration_seconds`)
      4. Confirmar: maxReceiveCount = 3 (`var.sqs_max_receive_count`)
      5. Confirmar: Batch size = 5 (`var.integrator_batch_size`)
      6. Confirmar: Lambda memory = 256 MB (`var.lambda_memory_mb`)
      7. Registrar valores confirmados
    - **Testes:** Todos os 6 valores confirmados nos arquivos fonte
    - **Critério de conclusão:** Valores documentados e validados
    - **Requisitos:** 7.3, 7.4, 9.10

  - [x] 0.7 Criar checklist de proteção contra impacto na POC MCP
    - **Objetivo:** Criar documento de verificação pré-plan que será usado em todas as fases de Terraform
    - **Arquivos:** `docs/pre-plan-checklist.md` (novo)
    - **Dependências:** 0.2, 0.3, 0.4, 0.5, 0.6
    - **Passos:**
      1. Criar checklist com verificações obrigatórias antes de qualquer `terraform plan`:
         - Nenhum `.tfstate` copiado da MCP presente
         - Nenhuma key de backend remoto apontando para estado MCP
         - Workspace dedicado à POC Bedrock
         - `locals.prefix = "connect-bedrock-poc"`
         - Plan não contém destroy/replace de recurso `connect-mcp-poc-*`
      2. Incluir script conceitual PowerShell de validação pré-plan
      3. Definir critério de abort: qualquer menção a `connect-mcp-poc` no plan output
    - **Testes:** Documento criado com todas as verificações listadas
    - **Critério de conclusão:** Checklist revisável e pronta para uso nas fases seguintes
    - **Requisitos:** 9.11, 15.5, 15.6

- [x] 1. GATE Fase 0 — Isolamento confirmado
  - Ensure all tests pass, ask the user if questions arise.
  - **Critério:** NENHUMA implementação inicia até que todas as verificações de isolamento estejam concluídas e documentadas.

### Fase 1 — Descoberta do Modelo Bedrock

- [ ] 2. Descobrir e validar modelo Bedrock (requer acesso AWS real)
  - [~] 2.1 Listar modelos disponíveis em us-east-1
    - **Objetivo:** Obter lista real de modelos disponíveis na região de deploy
    - **Arquivos:** N/A (comando AWS CLI)
    - **Dependências:** 0.7 (Gate Fase 0 aprovado)
    - **Passos:**
      1. Executar `aws bedrock list-foundation-models --region us-east-1 --output json`
      2. Filtrar modelos que suportam `InferenceTypesSupported: ON_DEMAND`
      3. Identificar candidatos: Amazon Nova Lite, Amazon Nova Micro, Claude 3 Haiku
      4. Registrar lista completa de modelos disponíveis
    - **Testes:** Comando retorna lista não vazia de modelos
    - **Critério de conclusão:** Lista de modelos disponíveis registrada
    - **Requisitos:** 10.1
    - **⚠️ Requer:** Acesso AWS real com credenciais válidas

  - [~] 2.2 Verificar suporte à Converse API
    - **Objetivo:** Confirmar que os modelos candidatos suportam o método `converse` do Bedrock Runtime
    - **Arquivos:** N/A (verificação AWS)
    - **Dependências:** 2.1
    - **Passos:**
      1. Para cada candidato, verificar documentação de suporte à Converse API
      2. Testar chamada `converse` com mensagem mínima para cada candidato
      3. Registrar quais modelos responderam com sucesso
    - **Testes:** Pelo menos um modelo responde via Converse API sem erro
    - **Critério de conclusão:** Suporte à Converse API confirmado para candidatos viáveis
    - **Requisitos:** 10.1, 2.1
    - **⚠️ Requer:** Acesso AWS real

  - [~] 2.3 Verificar acesso na conta
    - **Objetivo:** Confirmar que o modelo está habilitado/acessível na conta AWS atual
    - **Arquivos:** N/A (verificação AWS)
    - **Dependências:** 2.2
    - **Passos:**
      1. Executar `aws bedrock get-foundation-model --model-identifier <model_id> --region us-east-1`
      2. Verificar se retorna sem AccessDeniedException
      3. Se EULA necessária (Anthropic), verificar aceitação no console
      4. Registrar status de acesso para cada candidato
    - **Testes:** `get-foundation-model` retorna informações do modelo sem erro
    - **Critério de conclusão:** Acesso confirmado para pelo menos um modelo
    - **Requisitos:** 10.1
    - **⚠️ Requer:** Acesso AWS real

  - [~] 2.4 Testar candidatos em português
    - **Objetivo:** Verificar qualidade de geração em português brasileiro para cada candidato
    - **Arquivos:** N/A (teste interativo AWS)
    - **Dependências:** 2.3
    - **Passos:**
      1. Enviar pergunta em português ("Qual é a capital do Brasil?") via Converse API para cada candidato
      2. Avaliar qualidade da resposta: idioma correto, coerência, clareza
      3. Enviar pergunta de suporte ("Como resetar minha senha?") com system prompt padrão
      4. Comparar qualidade entre candidatos
      5. Registrar resultados de cada teste
    - **Testes:** Resposta em português brasileiro coerente e gramaticalmente correta
    - **Critério de conclusão:** Qualidade de geração em pt-BR avaliada e documentada
    - **Requisitos:** 4.2, 10.1
    - **⚠️ Requer:** Acesso AWS real

  - [~] 2.5 Verificar foundation model vs inference profile
    - **Objetivo:** Determinar se o modelo selecionado deve ser invocado como foundation model direto ou via inference profile
    - **Arquivos:** N/A (verificação AWS)
    - **Dependências:** 2.4
    - **Passos:**
      1. Verificar se o model ID contém prefixo de região (`us.`, `eu.`, `ap.`)
      2. Se sim, executar `aws bedrock list-inference-profiles --region us-east-1`
      3. Identificar o ARN correto (foundation model ARN vs inference profile ARN)
      4. Testar policy IAM com ARN específico
      5. Registrar tipo de invocação e formato de ARN
    - **Testes:** Tipo de invocação (foundation model ou inference profile) determinado
    - **Critério de conclusão:** Formato de ARN para IAM policy definido
    - **Requisitos:** 9.8, 11.3
    - **⚠️ Requer:** Acesso AWS real

  - [~] 2.6 Validar ARN para IAM
    - **Objetivo:** Confirmar que o ARN específico do modelo funciona como Resource em policy IAM `bedrock:InvokeModel`
    - **Arquivos:** N/A (verificação AWS)
    - **Dependências:** 2.5
    - **Passos:**
      1. Criar policy de teste com `bedrock:InvokeModel` limitado ao ARN específico
      2. Testar invocação com essa policy
      3. Se funcionar, registrar ARN validado
      4. Se não funcionar (resource-level permissions não suportadas), documentar necessidade de wildcard
    - **Testes:** Invocação com ARN específico funciona ou wildcard necessário é documentado
    - **Critério de conclusão:** ARN para IAM policy validado com evidência
    - **Requisitos:** 9.8, 11.3
    - **⚠️ Requer:** Acesso AWS real + permissões IAM

  - [~] 2.7 Registrar modelo escolhido, região e evidência
    - **Objetivo:** Documentar formalmente a decisão do modelo com todas as evidências coletadas
    - **Arquivos:** `docs/model-selection-evidence.md` (novo)
    - **Dependências:** 2.4, 2.5, 2.6
    - **Passos:**
      1. Registrar: model ID escolhido, região, tipo (foundation/inference profile)
      2. Registrar: data da verificação, conta AWS, resultados dos testes em pt-BR
      3. Registrar: formato de ARN validado para IAM
      4. Registrar: custo por 1K tokens (input/output) com fonte oficial
      5. Registrar: se wildcard IAM é necessário e motivo
    - **Testes:** Documento contém todos os campos obrigatórios
    - **Critério de conclusão:** Decisão formal documentada com evidências
    - **Requisitos:** 10.3

  - [~] 2.8 Medir latência inicial
    - **Objetivo:** Medir latência P50 e P99 da Converse API para o modelo escolhido
    - **Arquivos:** `docs/model-selection-evidence.md` (atualizado)
    - **Dependências:** 2.7
    - **Passos:**
      1. Executar 10 chamadas consecutivas à Converse API com pergunta padrão em pt-BR
      2. Registrar latência de cada chamada em ms
      3. Calcular P50, P90, P99
      4. Verificar se P99 < BEDROCK_TIMEOUT_SECONDS (20s)
      5. Registrar condições do teste (data, hora, região, modelo, tamanho do input)
    - **Testes:** P99 < 20s; todas as chamadas retornam resposta válida
    - **Critério de conclusão:** Latência medida e registrada com condições do teste
    - **Requisitos:** 10.3
    - **⚠️ Requer:** Acesso AWS real

  - [~] 2.9 Decidir BEDROCK_MODEL_ID
    - **Objetivo:** Decisão final do valor para a variável de ambiente BEDROCK_MODEL_ID
    - **Arquivos:** `docs/model-selection-evidence.md` (atualizado)
    - **Dependências:** 2.7, 2.8
    - **Passos:**
      1. Com base em todas as evidências (disponibilidade, pt-BR, latência, custo, IAM), definir o model ID final
      2. Registrar valor exato do BEDROCK_MODEL_ID escolhido
      3. Confirmar que o valor será usado em `terraform/variables.tf` e no smoke test
      4. Marcar decisão como FINAL — somente alterar com nova evidência
    - **Testes:** Model ID definido e registrado
    - **Critério de conclusão:** Valor de BEDROCK_MODEL_ID decidido formalmente
    - **Requisitos:** 2.2, 10.1, 10.2, 10.4

### Fase 2 — BedrockClient

- [ ] 3. Implementar módulo BedrockClient
  - [ ] 3.1 Criar `src/shared/bedrock_client/__init__.py`
    - **Objetivo:** Criar o ponto de entrada do módulo com exports públicos
    - **Arquivos:** `src/shared/bedrock_client/__init__.py` (novo)
    - **Dependências:** 0.7 (Gate Fase 0)
    - **Passos:**
      1. Criar diretório `src/shared/bedrock_client/`
      2. Criar `__init__.py` com imports públicos: `BedrockClient`, `BedrockConfigurationError`, `BedrockTransientError`, `BedrockFatalError`, `BedrockTimeoutError`
    - **Testes:** Import do módulo funciona sem erro
    - **Critério de conclusão:** Módulo importável com interface pública definida
    - **Requisitos:** 8.1

  - [~] 3.2 Criar `src/shared/bedrock_client/config.py`
    - **Objetivo:** Implementar leitura e validação de variáveis de ambiente do BedrockClient
    - **Arquivos:** `src/shared/bedrock_client/config.py` (novo)
    - **Dependências:** 3.1
    - **Passos:**
      1. Criar classe ou funções para ler variáveis de ambiente:
         - `BEDROCK_MODEL_ID` — obrigatória, não vazia
         - `BEDROCK_MAX_TOKENS` — padrão 1024, range [1, 4096]
         - `BEDROCK_TEMPERATURE` — padrão 0.7, range [0.0, 1.0]
         - `BEDROCK_SYSTEM_PROMPT` — padrão com instruções em pt-BR
         - `BEDROCK_TIMEOUT_SECONDS` — padrão 20, range [5, Lambda timeout - 5]
         - `AWS_REGION` — padrão "us-east-1"
      2. Implementar validação de ranges numéricos
      3. Lançar `BedrockConfigurationError` se validação falhar
    - **Testes:** Validação unitária em Fase 5
    - **Critério de conclusão:** Configuração lida e validada corretamente
    - **Requisitos:** 2.2, 2.3, 2.4, 2.5, 8.2, 8.7, 10.5

  - [~] 3.3 Criar `src/shared/bedrock_client/exceptions.py`
    - **Objetivo:** Definir hierarquia de exceções do módulo BedrockClient
    - **Arquivos:** `src/shared/bedrock_client/exceptions.py` (novo)
    - **Dependências:** 3.1
    - **Passos:**
      1. Implementar `BedrockError` (base) com `error_code` opcional
      2. Implementar `BedrockConfigurationError` (erro de config)
      3. Implementar `BedrockTransientError` (retry apropriado)
      4. Implementar `BedrockFatalError` (sem retry, FAILED_FINAL)
      5. Implementar `BedrockTimeoutError` (subtipo de transient)
    - **Testes:** Hierarquia de herança correta; `isinstance` funciona
    - **Critério de conclusão:** Todas as 5 classes de exceção implementadas
    - **Requisitos:** 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 8.6

  - [~] 3.4 Criar `src/shared/bedrock_client/response_parser.py`
    - **Objetivo:** Implementar extração de texto da resposta da Converse API
    - **Arquivos:** `src/shared/bedrock_client/response_parser.py` (novo)
    - **Dependências:** 3.1
    - **Passos:**
      1. Definir constante `FALLBACK_MESSAGE = "Desculpe, não consegui gerar uma resposta. Por favor, tente reformular sua pergunta."`
      2. Implementar função `extract_text_from_response(response: dict) -> str`
      3. Localizar `output.message.content` na resposta
      4. Se content é None ou lista vazia → retornar FALLBACK_MESSAGE
      5. Filtrar blocos com chave "text" e valor não vazio/whitespace
      6. Se nenhum bloco válido → retornar FALLBACK_MESSAGE
      7. Concatenar valores com `"\n"` e retornar
    - **Testes:** Validação unitária em Fase 5
    - **Critério de conclusão:** Parser extrai texto corretamente para todos os cenários da tabela do design §9
    - **Requisitos:** 3.1, 3.2, 3.3, 3.6

  - [~] 3.5 Criar `src/shared/bedrock_client/client.py`
    - **Objetivo:** Implementar a classe BedrockClient principal com método `converse`
    - **Arquivos:** `src/shared/bedrock_client/client.py` (novo)
    - **Dependências:** 3.2, 3.3, 3.4
    - **Passos:**
      1. Implementar `__init__` que lê config via módulo config e cria boto3 client `bedrock-runtime`
      2. Configurar `botocore.config.Config` com `connect_timeout=5` e `read_timeout=BEDROCK_TIMEOUT_SECONDS`
      3. Implementar método `converse(user_message, correlation_id, remaining_time_ms) -> str`
      4. Verificar `remaining_time_ms` antes de chamar: abort se < (BEDROCK_TIMEOUT_SECONDS * 1000) + 5000
      5. Montar requisição com modelId, system, messages, inferenceConfig
      6. Chamar `self._client.converse(...)` e medir latência
      7. Delegar parsing da resposta ao `response_parser.extract_text_from_response`
      8. Retornar texto extraído
    - **Testes:** Validação unitária em Fase 5
    - **Critério de conclusão:** Classe BedrockClient funcional com método converse
    - **Requisitos:** 2.1, 2.6, 2.7, 8.2, 8.3

  - [~] 3.6 Implementar validação de variáveis na inicialização
    - **Objetivo:** Garantir que `BedrockConfigurationError` é lançado se BEDROCK_MODEL_ID ausente/vazio ou valores numéricos fora dos ranges
    - **Arquivos:** `src/shared/bedrock_client/config.py`, `src/shared/bedrock_client/client.py`
    - **Dependências:** 3.2, 3.5
    - **Passos:**
      1. Em `config.py`, validar que `BEDROCK_MODEL_ID` não é vazia
      2. Validar BEDROCK_MAX_TOKENS no range [1, 4096]
      3. Validar BEDROCK_TEMPERATURE no range [0.0, 1.0]
      4. Validar BEDROCK_TIMEOUT_SECONDS >= 5
      5. Lançar `BedrockConfigurationError` com mensagem descritiva para cada falha
    - **Testes:** Validação unitária em Fase 5
    - **Critério de conclusão:** Todas as validações implementadas com mensagens claras
    - **Requisitos:** 2.3, 2.4, 2.8, 10.5

  - [~] 3.7 Implementar criação do cliente boto3
    - **Objetivo:** Criar cliente bedrock-runtime com região e timeout configurados
    - **Arquivos:** `src/shared/bedrock_client/client.py`
    - **Dependências:** 3.5, 3.6
    - **Passos:**
      1. Criar `boto3.client("bedrock-runtime", region_name=config.region, config=botocore_config)`
      2. `botocore.config.Config(connect_timeout=5, read_timeout=timeout_seconds)`
      3. Armazenar como atributo de instância para reutilização entre invocações (warm start)
    - **Testes:** Cliente criado sem erro com variáveis válidas
    - **Critério de conclusão:** Cliente boto3 criado e reutilizável
    - **Requisitos:** 8.2

  - [~] 3.8 Implementar montagem da requisição Converse API
    - **Objetivo:** Construir o payload correto para a chamada `converse`
    - **Arquivos:** `src/shared/bedrock_client/client.py`
    - **Dependências:** 3.5
    - **Passos:**
      1. Montar `system=[{"text": system_prompt}]`
      2. Montar `messages=[{"role": "user", "content": [{"text": user_message}]}]`
      3. Montar `inferenceConfig={"maxTokens": max_tokens, "temperature": temperature}`
      4. Usar `modelId=config.model_id`
    - **Testes:** Requisição montada conforme estrutura do design §8
    - **Critério de conclusão:** Payload da requisição segue especificação exata
    - **Requisitos:** 2.1, 2.6, 4.1

  - [~] 3.9 Implementar parsing multi-bloco da resposta
    - **Objetivo:** Extrair texto de respostas com múltiplos blocos de conteúdo
    - **Arquivos:** `src/shared/bedrock_client/response_parser.py`
    - **Dependências:** 3.4
    - **Passos:**
      1. Iterar sobre `content` filtrando blocos com chave "text"
      2. Ignorar blocos sem "text" (image, toolUse, etc.)
      3. Ignorar blocos com texto vazio ou apenas whitespace
      4. Concatenar blocos válidos com `"\n"`
      5. Retornar FALLBACK_MESSAGE se nenhum bloco válido
    - **Testes:** Todos os cenários da tabela do design §9
    - **Critério de conclusão:** Parser lida corretamente com 0, 1 e N blocos de texto
    - **Requisitos:** 3.2, 3.3, 3.6

  - [~] 3.10 Implementar mensagem de fallback
    - **Objetivo:** Retornar mensagem amigável quando resposta do modelo é vazia ou sem texto
    - **Arquivos:** `src/shared/bedrock_client/response_parser.py`
    - **Dependências:** 3.4
    - **Passos:**
      1. Definir constante FALLBACK_MESSAGE em português
      2. Usar como retorno para: content vazio, content ausente, somente blocos não-texto, blocos com texto vazio
    - **Testes:** FALLBACK_MESSAGE retornado para todos os cenários sem texto válido
    - **Critério de conclusão:** Fallback implementado e consistente
    - **Requisitos:** 3.3, 3.6

  - [~] 3.11 Implementar classificação de erros
    - **Objetivo:** Mapear exceções boto3/botocore para hierarquia de exceções do módulo
    - **Arquivos:** `src/shared/bedrock_client/client.py`
    - **Dependências:** 3.3, 3.5
    - **Passos:**
      1. Capturar `ClientError` do botocore
      2. Extrair `error_code` da resposta
      3. Mapear: ThrottlingException → `BedrockTransientError`
      4. Mapear: ServiceUnavailableException → `BedrockTransientError`
      5. Mapear: ModelTimeoutException → `BedrockTransientError`
      6. Mapear: AccessDeniedException → `BedrockFatalError`
      7. Mapear: ValidationException → `BedrockFatalError`
      8. Mapear: ModelNotFoundException → `BedrockFatalError`
      9. Mapear: Outros ClientError → `BedrockFatalError`
      10. Capturar ReadTimeoutError/ConnectTimeoutError → `BedrockTimeoutError`
    - **Testes:** Cada exceção AWS mapeada para a categoria correta
    - **Critério de conclusão:** Todos os 10 mapeamentos implementados conforme tabela do design §10
    - **Requisitos:** 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7

  - [~] 3.12 Implementar timeout e verificação de tempo restante
    - **Objetivo:** Abortar chamada ao Bedrock se não houver tempo suficiente na Lambda
    - **Arquivos:** `src/shared/bedrock_client/client.py`
    - **Dependências:** 3.5
    - **Passos:**
      1. Receber `remaining_time_ms` como parâmetro do método `converse`
      2. Se `remaining_time_ms` fornecido e < `(BEDROCK_TIMEOUT_SECONDS * 1000) + 5000`:
         - Lançar `BedrockTimeoutError("Insufficient remaining Lambda time")`
      3. Aplicar `read_timeout` via botocore.config para controle de socket
      4. Capturar `ReadTimeoutError` e converter para `BedrockTimeoutError`
    - **Testes:** Abort antes da chamada quando tempo insuficiente
    - **Critério de conclusão:** Duas camadas de timeout implementadas (pré-chamada e socket)
    - **Requisitos:** 2.10, 8.7

  - [~] 3.13 Implementar logging sanitizado
    - **Objetivo:** Registrar métricas de diagnóstico sem expor dados sensíveis em NENHUM nível de log
    - **Arquivos:** `src/shared/bedrock_client/client.py`
    - **Dependências:** 3.5
    - **Passos:**
      1. Registrar em INFO: `model_id`, `latency_ms`, `correlation_id`, `content_length`, `response_length`
      2. Registrar em WARNING (erro): `error_code`, `error_category`, `latency_ms`, `correlation_id`
      3. NUNCA registrar: conteúdo da mensagem, resposta do modelo, tokens, credentials (em NENHUM nível)
      4. Usar `extra={}` para campos estruturados
      5. Verificar que nenhum f-string ou format inclui conteúdo de mensagem
    - **Testes:** Teste de sanitização em Fase 5
    - **Critério de conclusão:** Zero dados sensíveis nos logs em qualquer nível (incluindo DEBUG)
    - **Requisitos:** 8.4, 8.5, 11.1, 11.2, 11.5

  - [~] 3.14 Criar system prompt padrão
    - **Objetivo:** Definir o system prompt padrão em português com todas as instruções obrigatórias
    - **Arquivos:** `src/shared/bedrock_client/config.py`
    - **Dependências:** 3.2
    - **Passos:**
      1. Definir constante com texto do system prompt padrão contendo:
         - "Responda sempre em português brasileiro"
         - "Seja claro e objetivo nas respostas"
         - "Atue como agente virtual de suporte"
         - "Não invente informações que não estejam disponíveis"
         - "Informe ao usuário quando não tiver dados suficientes para responder"
      2. Usar padrão se `BEDROCK_SYSTEM_PROMPT` não definida ou vazia
      3. Usar override se `BEDROCK_SYSTEM_PROMPT` definida
    - **Testes:** System prompt padrão contém todas as instruções obrigatórias
    - **Critério de conclusão:** System prompt com 5 instruções obrigatórias implementado
    - **Requisitos:** 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7

- [~] 4. Checkpoint — BedrockClient implementado
  - Ensure all tests pass, ask the user if questions arise.
  - **Critério:** Módulo `src/shared/bedrock_client/` completo com todas as classes, config, parser, client e exceções. Código compila sem erros de sintaxe.

### Fase 3 — Integração com Integrator

- [ ] 5. Adaptar Integrator para usar BedrockClient
  - [~] 5.1 Remover dependência do MCPClient (somente neste repositório)
    - **Objetivo:** Remover imports e referências ao MCPClient do processor do Integrator
    - **Arquivos:** `src/integrator/processor.py`
    - **Dependências:** 3.5 (BedrockClient pronto)
    - **Passos:**
      1. Remover imports de `shared.mcp_client` (MCPClient, MCPClientError, ToolResult, ToolSelector)
      2. Remover `_is_transient_mcp_error` helper function
      3. Remover parâmetros `mcp_client` e `tool_selector` do `__init__`
      4. Remover variáveis de ambiente MCP (`MCP_SERVER_URL`, `MCP_TIMEOUT_SECONDS`, `MCP_MAX_RETRIES`)
      5. Remover criação de `SigV4Auth` no `from_environment`
      6. NÃO remover diretório `src/shared/mcp_client/` ainda (preservar para referência)
    - **Testes:** Processor compila sem erros; imports MCP removidos
    - **Critério de conclusão:** Zero referências a MCPClient no processor
    - **Requisitos:** 9.5

  - [~] 5.2 Injetar BedrockClient no processor
    - **Objetivo:** Substituir MCPClient por BedrockClient como provedor de IA no MessageProcessor
    - **Arquivos:** `src/integrator/processor.py`
    - **Dependências:** 5.1, 3.5
    - **Passos:**
      1. Adicionar import de `shared.bedrock_client.BedrockClient`
      2. Adicionar import de exceções Bedrock (`BedrockTransientError`, `BedrockFatalError`, `BedrockTimeoutError`)
      3. Substituir parâmetro `mcp_client` por `bedrock_client: BedrockClient` no `__init__`
      4. No `from_environment`, criar instância de BedrockClient (sem parâmetros — lê env vars internamente)
      5. Atualizar método `process` para chamar `self._bedrock.converse(msg.content, correlation_id, remaining_time_ms)`
    - **Testes:** Processor aceita BedrockClient; método process chama converse
    - **Critério de conclusão:** BedrockClient integrado como dependência do processor
    - **Requisitos:** 2.7, 8.3

  - [~] 5.3 Preservar event parser
    - **Objetivo:** Confirmar que o event_parser.py permanece inalterado
    - **Arquivos:** `src/integrator/event_parser.py`
    - **Dependências:** 5.1
    - **Passos:**
      1. Verificar que event_parser.py não foi modificado
      2. Confirmar que parse_sqs_batch continua funcionando com mesma interface
      3. Confirmar extração de SNS envelope e classificação de tipos
    - **Testes:** Event parser funciona identicamente ao original
    - **Critério de conclusão:** Event parser preservado sem modificações
    - **Requisitos:** 1.1, 1.7

  - [~] 5.4 Preservar skip de MESSAGEMETADATA
    - **Objetivo:** Confirmar que eventos MESSAGEMETADATA continuam sendo ignorados
    - **Arquivos:** `src/integrator/event_parser.py`, `src/integrator/handler.py`
    - **Dependências:** 5.3
    - **Passos:**
      1. Verificar lógica de skip para Type != "MESSAGE"
      2. Confirmar que MESSAGEMETADATA não invoca BedrockClient
      3. Confirmar que MESSAGEMETADATA não aparece em batchItemFailures
    - **Testes:** Evento MESSAGEMETADATA resulta em skip limpo
    - **Critério de conclusão:** Comportamento MESSAGEMETADATA preservado
    - **Requisitos:** 1.2

  - [~] 5.5 Preservar filtragem de roles ignoradas
    - **Objetivo:** Confirmar que roles CUSTOM_BOT, SYSTEM, AGENT continuam ignoradas
    - **Arquivos:** `src/integrator/event_parser.py`
    - **Dependências:** 5.3
    - **Passos:**
      1. Verificar lógica de filtragem por ParticipantRole
      2. Confirmar que roles não-CUSTOMER resultam em skip
      3. Confirmar que skip não gera batchItemFailure
    - **Testes:** Roles não-CUSTOMER ignoradas silenciosamente
    - **Critério de conclusão:** Filtragem de roles preservada
    - **Requisitos:** 1.3

  - [~] 5.6 Preservar suporte a text/plain e text/markdown
    - **Objetivo:** Confirmar que ambos ContentTypes são aceitos para processamento
    - **Arquivos:** `src/integrator/event_parser.py`
    - **Dependências:** 5.3
    - **Passos:**
      1. Verificar aceitação de `text/plain`
      2. Verificar aceitação de `text/markdown`
      3. Verificar rejeição silenciosa de outros ContentTypes
    - **Testes:** Ambos tipos aceitos; outros rejeitados sem failure
    - **Critério de conclusão:** ContentTypes suportados preservados
    - **Requisitos:** 1.4, 1.5, 1.6

  - [~] 5.7 Gerar correlation_id antes do parsing
    - **Objetivo:** Implementar resolução de correlation_id como primeiro passo para cada registro SQS
    - **Arquivos:** `src/integrator/handler.py`
    - **Dependências:** 5.1
    - **Passos:**
      1. Para cada registro SQS, ANTES de parsear, resolver correlation_id:
         - Prioridade 1: SNS MessageAttributes (`correlation_id`, `X-Correlation-Id`)
         - Prioridade 2: Campos no payload após parse (`correlationId`, `correlation_id`)
         - Prioridade 3: Gerar UUID v4
      2. Incluir `correlation_id` em TODA entrada de log a partir deste ponto
      3. Passar correlation_id ao BedrockClient.converse()
      4. Definir constante `CORRELATION_ID_ATTRIBUTE_KEYS`
    - **Testes:** Correlation ID presente em todas as entradas de log
    - **Critério de conclusão:** Correlation ID gerado/propagado como primeiro passo
    - **Requisitos:** 5.1, 5.2, 5.3, 5.4, 5.5

  - [~] 5.8 Preservar idempotência
    - **Objetivo:** Confirmar que o mecanismo de idempotência permanece funcional
    - **Arquivos:** `src/integrator/idempotency_repository.py`, `src/integrator/handler.py`
    - **Dependências:** 5.1
    - **Passos:**
      1. Verificar que `try_acquire` continua sendo chamado antes do processamento
      2. Verificar estados: PROCESSING, COMPLETED, FAILED_FINAL
      3. Verificar lease duration de 90s
      4. Verificar tratamento de DUPLICATE_COMPLETED e ALREADY_PROCESSING
      5. Verificar `mark_completed` e `mark_failed_final` nos caminhos corretos
    - **Testes:** Fluxo de idempotência funcional ponta a ponta
    - **Critério de conclusão:** Idempotência preservada sem alterações
    - **Requisitos:** 7.2, 7.4

  - [~] 5.9 Preservar renovação de token
    - **Objetivo:** Confirmar que o mecanismo de token renewal permanece funcional
    - **Arquivos:** `src/integrator/processor.py`
    - **Dependências:** 5.2
    - **Passos:**
      1. Verificar que `_send_response` detecta TOKEN_EXPIRED
      2. Verificar que `_try_renew_and_retry` renova via CreateParticipantConnection
      3. Verificar que novo token é persistido criptografado no DynamoDB
      4. Verificar que SendMessage é retentado uma vez com novo token
    - **Testes:** Token renewal funcional no fluxo adaptado
    - **Critério de conclusão:** Renovação de token preservada
    - **Requisitos:** 7.5

  - [~] 5.10 Mapear erros transitórios do Bedrock para batchItemFailures
    - **Objetivo:** Implementar tratamento de BedrockTransientError/BedrockTimeoutError como fail item
    - **Arquivos:** `src/integrator/processor.py`
    - **Dependências:** 5.2
    - **Passos:**
      1. No método `process`, capturar `BedrockTransientError` (inclui `BedrockTimeoutError`)
      2. Registrar log WARNING com correlation_id, error_code, latency_ms
      3. Retornar `True` (should_fail) para que o handler reporte como batchItemFailure
      4. SQS re-entregará a mensagem após visibility timeout (360s)
    - **Testes:** BedrockTransientError → should_fail=True → batchItemFailure
    - **Critério de conclusão:** Erros transitórios geram retry via SQS
    - **Requisitos:** 6.1, 6.3, 6.4, 6.6

  - [~] 5.11 Mapear erros fatais do Bedrock para mensagem + FAILED_FINAL
    - **Objetivo:** Implementar tratamento de BedrockFatalError: enviar mensagem de erro ao usuário e marcar FAILED_FINAL
    - **Arquivos:** `src/integrator/processor.py`
    - **Dependências:** 5.2
    - **Passos:**
      1. No método `process`, capturar `BedrockFatalError`
      2. Chamar `_handle_fatal_with_response` com GENERIC_ERROR_MESSAGE
      3. Mensagem: "Desculpe, não consegui processar sua solicitação no momento. Por favor, tente novamente em alguns instantes."
      4. Marcar idempotência como FAILED_FINAL
      5. Registrar log WARNING com correlation_id, error_code
    - **Testes:** BedrockFatalError → mensagem de erro ao usuário + FAILED_FINAL
    - **Critério de conclusão:** Erros fatais resultam em mensagem amigável ao usuário
    - **Requisitos:** 6.2, 6.5, 6.7

  - [~] 5.12 Implementar passagem de remaining_time_ms ao BedrockClient
    - **Objetivo:** Passar o tempo restante da Lambda ao BedrockClient para proteção de timeout
    - **Arquivos:** `src/integrator/processor.py`, `src/integrator/handler.py`
    - **Dependências:** 5.2
    - **Passos:**
      1. No handler, obter `context.get_remaining_time_in_millis()` para cada record
      2. Passar `remaining_time_ms` ao processor.process()
      3. Processor passa ao `bedrock_client.converse(msg.content, correlation_id, remaining_time_ms)`
      4. BedrockClient valida margem antes de chamar Bedrock
    - **Testes:** remaining_time_ms propagado corretamente ao BedrockClient
    - **Critério de conclusão:** Proteção de timeout integrada no fluxo
    - **Requisitos:** 2.10, 8.7

- [~] 6. Checkpoint — Integração Bedrock completa
  - Ensure all tests pass, ask the user if questions arise.
  - **Critério:** Processor usa BedrockClient; erros classificados corretamente; padrões de confiabilidade preservados; correlation_id propagado.

### Fase 4 — Terraform Independente

- [ ] 7. Configurar infraestrutura Terraform independente
  - [~] 7.1 Confirmar estado independente
    - **Objetivo:** Verificar/criar backend Terraform exclusivo para a POC Bedrock
    - **Arquivos:** `terraform/providers.tf`, `terraform/terraform.tf`
    - **Dependências:** 0.7 (Gate Fase 0)
    - **Passos:**
      1. Se usando backend local: confirmar que `.tfstate` é exclusivo da POC Bedrock
      2. Se usando backend remoto: criar key/path dedicado
      3. Garantir zero compartilhamento com estado da POC MCP
    - **Testes:** Estado Terraform é independente e exclusivo
    - **Critério de conclusão:** Backend Terraform isolado confirmado
    - **Requisitos:** 9.1, 15.1

  - [~] 7.2 Alterar prefixo para `connect-bedrock-poc`
    - **Objetivo:** Atualizar `terraform/locals.tf` com o novo prefixo de recursos
    - **Arquivos:** `terraform/locals.tf`
    - **Dependências:** 7.1
    - **Passos:**
      1. Alterar valor do prefixo de `connect-mcp-poc` para `connect-bedrock-poc`
      2. Verificar que todos os nomes derivados usam o novo prefixo
      3. Confirmar: Lambda names, SQS names, SNS names, DynamoDB names, IAM role names, log group names
    - **Testes:** `grep "connect-mcp-poc" terraform/locals.tf` retorna vazio
    - **Critério de conclusão:** Todos os nomes de recurso usam prefixo `connect-bedrock-poc`
    - **Requisitos:** 9.2, 15.2

  - [~] 7.3 Remover provisionamento MCP deste repositório
    - **Objetivo:** Remover recursos MCP Server Lambda, IAM role e log group da configuração Terraform
    - **Arquivos:** `terraform/lambda.tf`, `terraform/iam.tf`, `terraform/monitoring.tf`
    - **Dependências:** 7.2, 0.5
    - **Passos:**
      1. Remover `aws_lambda_function.mcp_server` de `lambda.tf`
      2. Remover `aws_iam_role.mcp_server` e policies associadas de `iam.tf`
      3. Remover `aws_cloudwatch_log_group.mcp_server` de monitoring ou logs
      4. Remover quaisquer outputs referentes ao MCP Server
      5. NÃO executar plan/apply — apenas edição dos arquivos .tf
    - **Testes:** Arquivos .tf não contêm definições de recurso MCP Server
    - **Critério de conclusão:** Provisionamento MCP removido dos arquivos Terraform
    - **Requisitos:** 9.4

  - [~] 7.4 Remover Function URL deste repositório
    - **Objetivo:** Remover configuração de Lambda Function URL do Terraform
    - **Arquivos:** `terraform/function_url.tf`
    - **Dependências:** 7.3
    - **Passos:**
      1. Remover ou esvaziar `terraform/function_url.tf`
      2. Remover quaisquer referências à function URL em outros arquivos .tf
      3. Remover outputs de function_url
    - **Testes:** Nenhuma referência a `function_url` nos arquivos Terraform
    - **Critério de conclusão:** Function URL completamente removida da config
    - **Requisitos:** 9.4

  - [~] 7.5 Remover permissões MCP do IAM
    - **Objetivo:** Remover `lambda:InvokeFunctionUrl` e permissões MCP do Integrator IAM role
    - **Arquivos:** `terraform/iam.tf`
    - **Dependências:** 7.3
    - **Passos:**
      1. Remover permission `lambda:InvokeFunctionUrl` do Integrator role
      2. Remover quaisquer referências ao MCP Server ARN nas policies
      3. Manter demais permissões do Integrator (DynamoDB, SQS, KMS, ConnectParticipant, SNS)
    - **Testes:** IAM do Integrator não contém permissões MCP
    - **Critério de conclusão:** Permissões MCP removidas; demais preservadas
    - **Requisitos:** 9.5

  - [~] 7.6 Adicionar variáveis BEDROCK_* ao Terraform
    - **Objetivo:** Criar variáveis Terraform para configuração do Bedrock
    - **Arquivos:** `terraform/variables.tf`
    - **Dependências:** 7.2
    - **Passos:**
      1. Adicionar `variable "bedrock_model_id"` (tipo string, sem default, obrigatória, com validation)
      2. Adicionar `variable "bedrock_max_tokens"` (tipo number, default 1024)
      3. Adicionar `variable "bedrock_temperature"` (tipo number, default 0.7)
      4. Adicionar `variable "bedrock_system_prompt"` (tipo string, default "")
      5. Adicionar `variable "bedrock_timeout_seconds"` (tipo number, default 20)
      6. Adicionar validation: `bedrock_model_id` não pode ser vazio
    - **Testes:** `terraform validate` passa com as novas variáveis
    - **Critério de conclusão:** Todas as 5 variáveis Bedrock definidas
    - **Requisitos:** 9.7, 9.9, 10.2

  - [~] 7.7 Adicionar permissão `bedrock:InvokeModel` ao IAM
    - **Objetivo:** Conceder permissão ao Integrator para invocar modelos Bedrock
    - **Arquivos:** `terraform/iam.tf`
    - **Dependências:** 7.5, 7.6, 2.6
    - **Passos:**
      1. Adicionar statement IAM com Action `bedrock:InvokeModel`
      2. Resource: ARN validado na Fase 1 (task 2.6)
      3. Se wildcard necessário, usar `*` e adicionar comentário documentando limitação
      4. Associar policy à IAM role do Integrator
    - **Testes:** Policy contém `bedrock:InvokeModel` com Resource correto
    - **Critério de conclusão:** Permissão Bedrock configurada com menor privilégio possível
    - **Requisitos:** 9.8, 11.3
    - **⚠️ Bloqueado até:** Decisão do modelo (Fase 1, task 2.6)

  - [~] 7.8 Usar ARN específico validado
    - **Objetivo:** Garantir que o Resource do IAM policy usa o ARN validado (não hardcoded)
    - **Arquivos:** `terraform/iam.tf`
    - **Dependências:** 7.7, 2.6
    - **Passos:**
      1. Construir ARN dinamicamente a partir de `var.bedrock_model_id` e data sources
      2. Se foundation model: `arn:aws:bedrock:${region}::foundation-model/${model_id}`
      3. Se inference profile: usar ARN com account ID
      4. Se wildcard necessário: usar `*` com comentário
    - **Testes:** ARN no Terraform corresponde ao ARN validado na Fase 1
    - **Critério de conclusão:** ARN construído dinamicamente e validado
    - **Requisitos:** 9.8, 11.3

  - [~] 7.9 Manter wildcard apenas se tecnicamente necessário
    - **Objetivo:** Documentar decisão de usar wildcard (se aplicável) com justificativa
    - **Arquivos:** `terraform/iam.tf`, `docs/known-limitations.md`
    - **Dependências:** 7.8
    - **Passos:**
      1. Se ARN específico funciona: usar ARN específico (nenhuma ação adicional)
      2. Se wildcard necessário: adicionar comentário em iam.tf explicando motivo
      3. Se wildcard: registrar em `docs/known-limitations.md` como limitação de segurança
    - **Testes:** Decisão documentada (ARN específico ou wildcard com justificativa)
    - **Critério de conclusão:** Escopo IAM definido com justificativa documentada
    - **Requisitos:** 9.8, 11.3

  - [~] 7.10 Configurar variáveis de ambiente BEDROCK_* na Lambda Integrator
    - **Objetivo:** Adicionar variáveis de ambiente Bedrock na configuração da Lambda Integrator
    - **Arquivos:** `terraform/lambda.tf`
    - **Dependências:** 7.6
    - **Passos:**
      1. Remover env vars MCP: `MCP_SERVER_URL`, `MCP_TIMEOUT_SECONDS`, `MCP_MAX_RETRIES`
      2. Adicionar `BEDROCK_MODEL_ID = var.bedrock_model_id`
      3. Adicionar `BEDROCK_MAX_TOKENS = tostring(var.bedrock_max_tokens)`
      4. Adicionar `BEDROCK_TEMPERATURE = tostring(var.bedrock_temperature)`
      5. Adicionar `BEDROCK_SYSTEM_PROMPT = var.bedrock_system_prompt`
      6. Adicionar `BEDROCK_TIMEOUT_SECONDS = tostring(var.bedrock_timeout_seconds)`
      7. Manter demais env vars: `SESSIONS_TABLE_NAME`, `IDEMPOTENCY_TABLE_NAME`, `KMS_KEY_ID`, `LEASE_DURATION_SECONDS`
    - **Testes:** Lambda Integrator em lambda.tf contém todas as variáveis BEDROCK_* e nenhuma MCP_*
    - **Critério de conclusão:** Variáveis de ambiente do Integrator atualizadas
    - **Requisitos:** 9.5, 9.7

  - [~] 7.11 Provisionar recursos próprios (SNS, SQS, DLQ, KMS, DynamoDB, Lambda)
    - **Objetivo:** Confirmar que todos os recursos usam prefixo `connect-bedrock-poc` e são independentes
    - **Arquivos:** `terraform/sns.tf`, `terraform/sqs.tf`, `terraform/kms.tf`, `terraform/dynamodb.tf`, `terraform/lambda.tf`
    - **Dependências:** 7.2
    - **Passos:**
      1. Verificar SNS topic com nome `connect-bedrock-poc-*`
      2. Verificar SQS queue com nome `connect-bedrock-poc-*`
      3. Verificar DLQ com nome `connect-bedrock-poc-*`
      4. Verificar KMS key com alias `connect-bedrock-poc-*`
      5. Verificar DynamoDB tables com nomes `connect-bedrock-poc-*`
      6. Verificar Lambda functions com nomes `connect-bedrock-poc-*`
      7. Verificar CloudWatch log groups com nomes corretos
    - **Testes:** Todos os nomes de recurso contêm prefixo `connect-bedrock-poc`
    - **Critério de conclusão:** Recursos totalmente independentes e com nomes distintos
    - **Requisitos:** 9.2, 9.10, 15.2

  - [~] 7.12 Criar Contact Flow separado
    - **Objetivo:** Configurar Contact Flow dedicado à POC Bedrock (separado do flow MCP)
    - **Arquivos:** `terraform/` (novo recurso ou data source)
    - **Dependências:** 7.11
    - **Passos:**
      1. Decidir: criar novo Contact Flow via Terraform OU documentar criação manual
      2. Se Terraform: criar `aws_connect_contact_flow` com nome `connect-bedrock-poc-*`
      3. Se manual: documentar em `docs/deployment-guide.md` os passos de criação
      4. Garantir que NÃO modifica o flow ativo da POC MCP
      5. Associar com Initializer Lambda da POC Bedrock
    - **Testes:** Contact Flow referenciado não é o flow MCP ativo
    - **Critério de conclusão:** Contact Flow separado definido (Terraform ou documentado)
    - **Requisitos:** 9.3, 15.3

  - [~] 7.13 Atualizar outputs
    - **Objetivo:** Remover outputs MCP e adicionar outputs Bedrock
    - **Arquivos:** `terraform/outputs.tf`
    - **Dependências:** 7.3, 7.6, 7.10
    - **Passos:**
      1. Remover outputs referentes a MCP Server (function_url, mcp_server_name)
      2. Adicionar output `bedrock_model_id`
      3. Adicionar output `integrator_function_name`
      4. Manter outputs relevantes: queue_url, dlq_url, table names
    - **Testes:** Outputs não referenciam MCP; novos outputs Bedrock presentes
    - **Critério de conclusão:** Outputs atualizados para refletir POC Bedrock
    - **Requisitos:** 9.4, 9.7

  - [~] 7.14 Revisar monitoring
    - **Objetivo:** Preservar alarmes existentes e adicionar alarme de latência Bedrock
    - **Arquivos:** `terraform/monitoring.tf`
    - **Dependências:** 7.3
    - **Passos:**
      1. Preservar alarmes: FailedFinal, DLQ, Errors, Throttles
      2. Remover alarmes específicos do MCP Server (se existirem)
      3. Adicionar alarme para latência alta do Bedrock (opcional para POC)
      4. Atualizar nomes de alarmes com prefixo `connect-bedrock-poc`
    - **Testes:** Alarmes essenciais preservados; nomes com prefixo correto
    - **Critério de conclusão:** Monitoring atualizado para POC Bedrock
    - **Requisitos:** 9.10

  - [~] 7.15 Criar validação pré-plan
    - **Objetivo:** Implementar script que valida segurança antes de executar `terraform plan`
    - **Arquivos:** `scripts/validate_pre_plan.ps1` (novo)
    - **Dependências:** 0.7, 7.2
    - **Passos:**
      1. Verificar que `terraform/locals.tf` não contém `connect-mcp-poc`
      2. Verificar ausência de `.tfstate` com recursos MCP
      3. Executar `terraform plan -out=plan.tfplan`
      4. Verificar output do plan por menções a `connect-mcp-poc`
      5. Se qualquer verificação falhar: abortar com mensagem de erro clara
      6. Registrar: "ABORT: Prefixo MCP detectado" ou "ABORT: Plan contém destroy/replace de recurso MCP"
    - **Testes:** Script detecta e bloqueia plans que afetariam POC MCP
    - **Critério de conclusão:** Script de validação pré-plan funcional
    - **Requisitos:** 9.11, 15.6

- [~] 8. GATE Fase 4 — Terraform revisado
  - Ensure all tests pass, ask the user if questions arise.
  - **Critério:** Qualquer `terraform plan` mencionando `connect-mcp-poc` DEVE falhar na revisão. NÃO executar apply nesta fase.
  - **⚠️ AUTORIZAÇÃO NECESSÁRIA:** Não executar `terraform apply` sem aprovação explícita do operador.

### Fase 5 — Testes

- [ ] 9. Implementar testes unitários do BedrockClient
  - [~] 9.1 Testes unitários de configuração
    - **Objetivo:** Testar validação de variáveis de ambiente em `bedrock_client/config.py`
    - **Arquivos:** `tests/unit/test_bedrock_config.py` (novo)
    - **Dependências:** 3.2, 3.6
    - **Passos:**
      1. Testar BEDROCK_MODEL_ID ausente → `BedrockConfigurationError`
      2. Testar BEDROCK_MODEL_ID vazio → `BedrockConfigurationError`
      3. Testar BEDROCK_MAX_TOKENS=0 → erro
      4. Testar BEDROCK_MAX_TOKENS=5000 → erro
      5. Testar BEDROCK_MAX_TOKENS=1024 → sucesso
      6. Testar BEDROCK_TEMPERATURE=1.5 → erro
      7. Testar BEDROCK_TEMPERATURE=-0.1 → erro
      8. Testar BEDROCK_TEMPERATURE=0.0 → sucesso
      9. Testar BEDROCK_TEMPERATURE=1.0 → sucesso
      10. Testar BEDROCK_TIMEOUT_SECONDS=4 → erro
      11. Testar system prompt padrão contém as 5 instruções obrigatórias
      12. Testar override de system prompt via variável de ambiente
    - **Testes:** Todos os cenários de validação cobertos
    - **Critério de conclusão:** 12+ testes unitários passando
    - **Requisitos:** 2.3, 2.4, 2.5, 2.8, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 10.5, 12.3

  - [~] 9.2 Testes unitários do response parser
    - **Objetivo:** Testar extração de texto para todos os cenários de resposta da Converse API
    - **Arquivos:** `tests/unit/test_bedrock_response_parser.py` (novo)
    - **Dependências:** 3.4, 3.9, 3.10
    - **Passos:**
      1. Testar bloco único de texto → retorna texto exato
      2. Testar múltiplos blocos de texto → concatenação com `\n`
      3. Testar mix texto + não-texto → apenas texto extraído
      4. Testar content vazio `[]` → fallback
      5. Testar content ausente (None) → fallback
      6. Testar somente blocos não-texto → fallback
      7. Testar blocos com texto vazio ou whitespace → fallback
    - **Testes:** 7 cenários cobrindo tabela completa do design §9
    - **Critério de conclusão:** Todos os cenários de parsing testados
    - **Requisitos:** 3.1, 3.2, 3.3, 3.6, 12.1, 12.2, 12.3, 12.10

  - [~] 9.3 Testes unitários de exceções e classificação de erros
    - **Objetivo:** Testar mapeamento de exceções AWS para hierarquia do módulo
    - **Arquivos:** `tests/unit/test_bedrock_exceptions.py` (novo)
    - **Dependências:** 3.3, 3.11
    - **Passos:**
      1. Testar ThrottlingException → `BedrockTransientError`
      2. Testar ServiceUnavailableException → `BedrockTransientError`
      3. Testar ModelTimeoutException → `BedrockTransientError`
      4. Testar AccessDeniedException → `BedrockFatalError`
      5. Testar ValidationException → `BedrockFatalError`
      6. Testar ModelNotFoundException → `BedrockFatalError`
      7. Testar ClientError desconhecido → `BedrockFatalError`
      8. Testar ReadTimeoutError → `BedrockTimeoutError`
      9. Testar ConnectTimeoutError → `BedrockTimeoutError`
      10. Testar hierarquia: `BedrockTimeoutError` é subtipo de `BedrockTransientError`
    - **Testes:** 10 cenários de classificação de erro
    - **Critério de conclusão:** Todos os mapeamentos de erro testados
    - **Requisitos:** 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 12.4, 12.5, 12.6

  - [~] 9.4 Testes unitários de timeout
    - **Objetivo:** Testar comportamento de timeout em ambas as camadas (pré-chamada e socket)
    - **Arquivos:** `tests/unit/test_bedrock_timeout.py` (novo)
    - **Dependências:** 3.12
    - **Passos:**
      1. Testar abort pré-chamada quando remaining_time_ms insuficiente → `BedrockTimeoutError`
      2. Testar chamada permitida quando remaining_time_ms suficiente
      3. Testar comportamento quando remaining_time_ms=None (sem verificação pré-chamada)
      4. Testar ReadTimeoutError do botocore → `BedrockTimeoutError`
      5. Testar ConnectTimeoutError do botocore → `BedrockTimeoutError`
    - **Testes:** 5 cenários de timeout
    - **Critério de conclusão:** Ambas as camadas de timeout testadas
    - **Requisitos:** 2.10, 8.7, 12.6

  - [~] 9.5 Testes unitários de sanitização de logs
    - **Objetivo:** Verificar que dados sensíveis NUNCA aparecem nos logs em NENHUM nível
    - **Arquivos:** `tests/unit/test_log_sanitization.py` (novo)
    - **Dependências:** 3.13
    - **Passos:**
      1. Executar chamada com sucesso e capturar saída de log em TODOS os níveis
      2. Verificar ausência do conteúdo da mensagem do usuário
      3. Verificar ausência do conteúdo da resposta do modelo
      4. Verificar presença de: `latency_ms`, `correlation_id`, `model_id`
      5. Executar chamada com erro e repetir verificações
      6. Testar com logging em nível DEBUG — conteúdo NUNCA aparece
      7. Verificar ausência de tokens (ConnectionToken, ParticipantToken)
    - **Testes:** 7+ verificações de sanitização cobrindo TODOS os níveis de log
    - **Critério de conclusão:** Zero dados sensíveis nos logs; métricas presentes
    - **Requisitos:** 8.4, 8.5, 11.1, 11.2, 11.5

  - [~] 9.6 Testes unitários do handler adaptado
    - **Objetivo:** Testar handler do Integrator com BedrockClient mockado
    - **Arquivos:** `tests/unit/test_handler.py` (novo ou adaptado)
    - **Dependências:** 5.2, 5.10, 5.11
    - **Passos:**
      1. Testar fluxo completo: MESSAGE/CUSTOMER → BedrockClient → SendMessage → COMPLETED
      2. Testar MESSAGEMETADATA → skip sem chamar Bedrock
      3. Testar roles ignoradas → skip sem chamar Bedrock
      4. Testar BedrockTransientError → batchItemFailure
      5. Testar BedrockFatalError → mensagem de erro + FAILED_FINAL
      6. Testar batch com mix de sucesso e falha → partial batch response
    - **Testes:** 6+ cenários do handler
    - **Critério de conclusão:** Handler funciona corretamente com BedrockClient
    - **Requisitos:** 1.1, 1.2, 1.3, 7.1, 12.7, 12.8

  - [~] 9.7 Testes de idempotência
    - **Objetivo:** Testar que o mecanismo de idempotência continua funcional
    - **Arquivos:** `tests/unit/test_idempotency.py` (novo ou adaptado)
    - **Dependências:** 5.8
    - **Passos:**
      1. Testar ACQUIRED → processamento normal
      2. Testar DUPLICATE_COMPLETED → skip sem chamar Bedrock
      3. Testar FAILED_FINAL → skip sem chamar Bedrock
      4. Testar ALREADY_PROCESSING → batchItemFailure
      5. Testar DynamoDBTransientError → batchItemFailure
      6. Testar mark_completed após sucesso
      7. Testar mark_failed_final após erro fatal
    - **Testes:** 7 cenários de idempotência
    - **Critério de conclusão:** Todos os estados de idempotência testados
    - **Requisitos:** 7.2, 7.4, 7.6

  - [~] 9.8 Testes de partial batch response
    - **Objetivo:** Testar que batchItemFailures é reportado corretamente
    - **Arquivos:** `tests/unit/test_partial_batch.py` (novo ou adaptado)
    - **Dependências:** 5.10
    - **Passos:**
      1. Testar batch com 1 sucesso e 1 falha → apenas falha em batchItemFailures
      2. Testar batch com todas as mensagens com sucesso → batchItemFailures vazio
      3. Testar batch com todas as mensagens com falha → todos em batchItemFailures
      4. Testar que itemIdentifier usa o SQS messageId correto
    - **Testes:** 4 cenários de partial batch
    - **Critério de conclusão:** Partial batch response correto em todos os cenários
    - **Requisitos:** 7.1

  - [~] 9.9 Testes de MESSAGEMETADATA
    - **Objetivo:** Testar filtragem correta de eventos MESSAGEMETADATA
    - **Arquivos:** `tests/unit/test_event_parser.py` (adaptado)
    - **Dependências:** 5.4
    - **Passos:**
      1. Testar evento com Type="MESSAGEMETADATA" → skip
      2. Confirmar que Bedrock NÃO é invocado
      3. Confirmar que registro NÃO aparece em batchItemFailures
    - **Testes:** MESSAGEMETADATA ignorado corretamente
    - **Critério de conclusão:** Filtragem de MESSAGEMETADATA testada
    - **Requisitos:** 1.2, 12.8

  - [~] 9.10 Testes de filtragem por role
    - **Objetivo:** Testar que roles não-CUSTOMER são ignoradas
    - **Arquivos:** `tests/unit/test_event_parser.py` (adaptado)
    - **Dependências:** 5.5
    - **Passos:**
      1. Testar ParticipantRole="CUSTOM_BOT" → skip
      2. Testar ParticipantRole="SYSTEM" → skip
      3. Testar ParticipantRole="AGENT" → skip
      4. Testar ParticipantRole="CUSTOMER" → processado
    - **Testes:** 4 cenários de role
    - **Critério de conclusão:** Filtragem de roles testada
    - **Requisitos:** 1.3

  - [~] 9.11 Testes de ContentType
    - **Objetivo:** Testar aceitação de text/plain e text/markdown e rejeição de outros
    - **Arquivos:** `tests/unit/test_event_parser.py` (adaptado)
    - **Dependências:** 5.6
    - **Passos:**
      1. Testar ContentType="text/plain" → processado
      2. Testar ContentType="text/markdown" → processado
      3. Testar ContentType="application/json" → skip
      4. Testar ContentType="image/png" → skip
    - **Testes:** 4 cenários de ContentType
    - **Critério de conclusão:** ContentType suportados e rejeitados testados
    - **Requisitos:** 1.4, 1.5, 1.6

  - [ ]* 9.12 Testes baseados em propriedades (PBT)
    - **Objetivo:** Implementar testes PBT com Hypothesis para as 9 propriedades do design
    - **Arquivos:** `tests/unit/test_message_routing_props.py`, `tests/unit/test_bedrock_config_props.py`, `tests/unit/test_bedrock_client_props.py`, `tests/unit/test_response_parser_props.py`, `tests/unit/test_bedrock_exceptions_props.py`, `tests/unit/test_log_sanitization_props.py` (novos)
    - **Dependências:** 9.1–9.11
    - **Passos:**
      1. **Property 1:** Roteamento correto de mensagens válidas — gerar mensagens com Type="MESSAGE", Role="CUSTOMER", ContentType válido, Content não vazio → Bedrock invocado
      2. **Property 2:** Filtragem de mensagens irrelevantes — gerar mensagens com qualquer combinação inválida → Bedrock NÃO invocado E sem batchItemFailure
      3. **Property 3:** Validação numérica — gerar MAX_TOKENS fora [1,4096] ou TEMPERATURE fora [0.0,1.0] → BedrockConfigurationError
      4. **Property 4:** Construção da requisição — gerar mensagens 1-4096 chars → requisição contém modelId, system, messages, inferenceConfig corretos
      5. **Property 5:** Extração de texto — gerar listas de blocos → concatenação correta ou fallback
      6. **Property 6:** Classificação de erros — gerar ClientError com códigos variados → categoria correta
      7. **Property 7:** Fluxo de sucesso → COMPLETED — gerar cenários de sucesso → idempotência marcada COMPLETED
      8. **Property 8:** Sanitização de logs — gerar mensagens diversas → conteúdo NUNCA nos logs
      9. **Property 9:** Correlation ID universal — gerar mensagens → todas as entradas de log com mesmo correlation_id
      10. Usar `@settings(max_examples=100)` para cada propriedade
    - **Testes:** 9 testes PBT com 100+ exemplos cada
    - **Critério de conclusão:** Todas as 9 propriedades do design validadas com Hypothesis
    - **Requisitos:** 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10

- [ ] 10. Implementar testes de integração
  - [~] 10.1 Teste de integração: fluxo completo MESSAGE/CUSTOMER
    - **Objetivo:** Testar fluxo ponta a ponta com BedrockClient mockado
    - **Arquivos:** `tests/integration/test_integrator_bedrock_flow.py` (novo)
    - **Dependências:** 5.2, 9.6
    - **Passos:**
      1. Montar evento SQS com MESSAGE/CUSTOMER válido
      2. Mock BedrockClient retornando texto válido
      3. Mock ParticipantService retornando sucesso
      4. Mock DynamoDB para idempotência e sessão
      5. Verificar: Bedrock chamado com conteúdo correto
      6. Verificar: resposta enviada via ParticipantService
      7. Verificar: idempotência marcada COMPLETED
    - **Testes:** Fluxo completo integrado
    - **Critério de conclusão:** Fluxo MESSAGE → Bedrock → SendMessage → COMPLETED funcional
    - **Requisitos:** 12.7

  - [~] 10.2 Teste de integração: roteamento de mensagens
    - **Objetivo:** Testar roteamento correto de diferentes tipos de evento
    - **Arquivos:** `tests/integration/test_message_routing.py` (novo)
    - **Dependências:** 9.9, 9.10, 9.11
    - **Passos:**
      1. Testar MESSAGEMETADATA → nenhuma chamada ao Bedrock
      2. Testar roles ignoradas → nenhuma chamada ao Bedrock
      3. Testar ContentType não suportado → nenhuma chamada ao Bedrock
      4. Testar content vazio → nenhuma chamada ao Bedrock
      5. Testar MESSAGE/CUSTOMER/text/plain → Bedrock invocado
    - **Testes:** 5 cenários de roteamento integrado
    - **Critério de conclusão:** Roteamento correto para todos os tipos de evento
    - **Requisitos:** 12.8

  - [~] 10.3 Teste de integração: correlation_id
    - **Objetivo:** Verificar que correlation_id é propagado em TODAS as entradas de log do ciclo
    - **Arquivos:** `tests/integration/test_correlation_id.py` (novo)
    - **Dependências:** 5.7
    - **Passos:**
      1. Executar processamento completo de mensagem capturando logs
      2. Extrair todas as entradas de log emitidas
      3. Verificar que TODAS contêm o campo `correlation_id`
      4. Verificar que o valor é o MESMO em todas as entradas
      5. Testar com correlation_id propagado do evento
      6. Testar com correlation_id gerado (UUID v4)
    - **Testes:** Correlation ID presente e consistente em todos os logs
    - **Critério de conclusão:** 100% das entradas de log contêm correlation_id correto
    - **Requisitos:** 5.1, 5.2, 5.3, 5.4, 5.5, 12.9

  - [ ]* 10.4 Testes PBT de integração
    - **Objetivo:** Implementar Property 7 e Property 9 como testes de integração com Hypothesis
    - **Arquivos:** `tests/integration/test_integrator_bedrock_flow.py`, `tests/integration/test_correlation_id_props.py` (novos)
    - **Dependências:** 10.1, 10.3, 9.12
    - **Passos:**
      1. **Property 7:** Gerar cenários de sucesso variados → COMPLETED sempre marcado
      2. **Property 9:** Gerar mensagens diversas → correlation_id presente em TODOS os logs
      3. Usar `@settings(max_examples=100)` para ambas
    - **Testes:** 2 testes PBT de integração
    - **Critério de conclusão:** Properties 7 e 9 validadas em contexto de integração
    - **Requisitos:** 12.7, 12.9

  - [~] 10.5 Verificar cobertura de testes
    - **Objetivo:** Executar suíte completa e verificar cobertura mínima
    - **Arquivos:** N/A (execução de testes)
    - **Dependências:** 9.1–9.12, 10.1–10.4
    - **Passos:**
      1. Executar `pytest tests/ -v --tb=short --cov=src --cov-report=term-missing`
      2. Verificar cobertura de `src/shared/bedrock_client/` ≥ 90%
      3. Verificar cobertura de `src/integrator/processor.py` ≥ 80%
      4. Identificar linhas não cobertas e avaliar necessidade de testes adicionais
    - **Testes:** Relatório de cobertura gerado
    - **Critério de conclusão:** Cobertura mínima atingida; gaps avaliados
    - **Requisitos:** 12.1–12.10

- [~] 11. Checkpoint — Suíte de testes completa
  - Ensure all tests pass, ask the user if questions arise.
  - **Critério:** `pytest tests/ -v` executa sem falhas. Cobertura de bedrock_client ≥ 90%.

### Fase 6 — Smoke Test

- [ ] 12. Implementar script de smoke test
  - [~] 12.1 Criar `scripts/smoke_test_bedrock.ps1`
    - **Objetivo:** Criar o arquivo base do script de smoke test
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1` (novo)
    - **Dependências:** 3.5 (BedrockClient pronto)
    - **Passos:**
      1. Criar arquivo PowerShell com cabeçalho e descrição
      2. Definir estrutura base: validação de credenciais → configuração → chamada → resultado
      3. Definir exit codes: 0 = sucesso, 1 = falha
    - **Testes:** Script é sintaticamente válido
    - **Critério de conclusão:** Arquivo criado com estrutura base
    - **Requisitos:** 13.1

  - [~] 12.2 Implementar validação de credenciais
    - **Objetivo:** Verificar credenciais AWS antes de prosseguir com o teste
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1`
    - **Dependências:** 12.1
    - **Passos:**
      1. Executar `aws sts get-caller-identity`
      2. Se falhar: imprimir erro "Credenciais AWS não configuradas" e exit 1
      3. Se sucesso: imprimir Account ID, ARN e região
    - **Testes:** Script detecta credenciais inválidas e exibe mensagem clara
    - **Critério de conclusão:** Validação de credenciais implementada
    - **Requisitos:** 13.2, 13.3

  - [~] 12.3 Implementar leitura de BEDROCK_MODEL_ID
    - **Objetivo:** Resolver model ID da variável de ambiente ou default do Terraform
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1`
    - **Dependências:** 12.1
    - **Passos:**
      1. Ler `$env:BEDROCK_MODEL_ID`
      2. Se não definida: usar valor padrão definido na variável Terraform `bedrock_model_id`
      3. Imprimir model ID resolvido
    - **Testes:** Model ID resolvido corretamente (env var ou default)
    - **Critério de conclusão:** Resolução de model ID implementada
    - **Requisitos:** 13.4

  - [~] 12.4 Usar mesma classe BedrockClient da Lambda
    - **Objetivo:** Instanciar BedrockClient real (mesma classe usada pelo Integrator)
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1`
    - **Dependências:** 12.3, 3.5
    - **Passos:**
      1. Configurar PYTHONPATH para incluir `src/`
      2. Instanciar BedrockClient com model ID resolvido e config padrão
      3. Capturar BedrockConfigurationError se config inválida
    - **Testes:** BedrockClient instanciado sem erro de configuração
    - **Critério de conclusão:** Mesma classe do Lambda usada no smoke test
    - **Requisitos:** 13.5

  - [~] 12.5 Implementar envio de pergunta de teste em português
    - **Objetivo:** Enviar pergunta curta (≤50 chars) em pt-BR ao Bedrock e aguardar resposta
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1`
    - **Dependências:** 12.4
    - **Passos:**
      1. Definir pergunta de teste: "Qual é a capital do Brasil?" (≤50 chars)
      2. Gerar correlation_id (UUID v4)
      3. Chamar `bedrock_client.converse(pergunta, correlation_id)`
      4. Aguardar no máximo BEDROCK_TIMEOUT_SECONDS (padrão 20s)
    - **Testes:** Chamada retorna resposta em pt-BR
    - **Critério de conclusão:** Pergunta enviada e resposta recebida
    - **Requisitos:** 13.6

  - [~] 12.6 Implementar validação de resposta e saída
    - **Objetivo:** Validar resposta não vazia e registrar resultado com métricas
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1`
    - **Dependências:** 12.5
    - **Passos:**
      1. Verificar que resposta não é vazia e comprimento > 0
      2. Imprimir: texto da resposta, latência em ms, correlation_id
      3. Se resposta válida: exit 0
      4. Se resposta vazia ou erro: imprimir tipo e mensagem de erro, exit 1
    - **Testes:** Exit code correto para sucesso e falha
    - **Critério de conclusão:** Smoke test reporta resultado com métricas
    - **Requisitos:** 13.7, 13.8

  - [~] 12.7 Implementar tratamento de erros de credencial, modelo e permissão
    - **Objetivo:** Tratamento específico para erros comuns com mensagens claras
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1`
    - **Dependências:** 12.6
    - **Passos:**
      1. Tratar BedrockConfigurationError: mensagem sobre variável ausente
      2. Tratar AccessDeniedException: mensagem sobre permissão IAM insuficiente
      3. Tratar ModelNotFoundException: mensagem sobre modelo não encontrado
      4. Tratar credenciais ausentes: mensagem sobre `aws configure`
      5. Todos os erros: exit 1 com mensagem descritiva
    - **Testes:** Cada tipo de erro produz mensagem clara e exit 1
    - **Critério de conclusão:** Erros comuns tratados com mensagens úteis
    - **Requisitos:** 13.8

- [~] 13. Checkpoint — Smoke test implementado
  - Ensure all tests pass, ask the user if questions arise.
  - **Critério:** Script `scripts/smoke_test_bedrock.ps1` completo. Smoke test DEVE ser executado com sucesso ANTES de prosseguir para teste de chat.
  - **⚠️ Requer:** Acesso AWS real para execução

### Fase 7 — Deploy Seguro

- [ ] 14. Preparar e executar deploy (requer autorização)
  - [~] 14.1 Build Initializer
    - **Objetivo:** Empacotar Lambda Initializer em ZIP
    - **Arquivos:** `packages/initializer.zip` (gerado)
    - **Dependências:** 11 (Gate testes), 13 (Gate smoke test)
    - **Passos:**
      1. Executar `scripts/build_lambdas.ps1` ou equivalente
      2. Verificar que `packages/initializer.zip` foi gerado
      3. Verificar que contém todos os módulos necessários
    - **Testes:** ZIP gerado com tamanho > 0 e estrutura correta
    - **Critério de conclusão:** Initializer empacotado
    - **Requisitos:** 14.3

  - [~] 14.2 Build Integrator
    - **Objetivo:** Empacotar Lambda Integrator em ZIP (com BedrockClient, sem MCPClient)
    - **Arquivos:** `packages/integrator.zip` (gerado)
    - **Dependências:** 14.1
    - **Passos:**
      1. Executar build do Integrator
      2. Verificar que `packages/integrator.zip` contém `shared/bedrock_client/`
      3. Verificar que NÃO contém `shared/mcp_client/`
      4. Verificar que NÃO contém `mcp_server/`
    - **Testes:** ZIP contém bedrock_client e não contém mcp_client
    - **Critério de conclusão:** Integrator empacotado com dependências corretas
    - **Requisitos:** 9.5

  - [~] 14.3 Verificar ZIPs
    - **Objetivo:** Validar integridade dos pacotes Lambda gerados
    - **Arquivos:** `packages/initializer.zip`, `packages/integrator.zip`
    - **Dependências:** 14.1, 14.2
    - **Passos:**
      1. Listar conteúdo de cada ZIP e verificar módulos esperados
      2. Verificar tamanho (< limite AWS Lambda de 250MB descompactado)
      3. Verificar que dependências estão incluídas (boto3 vem do runtime Lambda)
    - **Testes:** ZIPs válidos com conteúdo esperado
    - **Critério de conclusão:** Pacotes Lambda validados
    - **Requisitos:** 14.3

  - [~] 14.4 Gerar novo Terraform plan
    - **Objetivo:** Gerar plan após build (hashes dos ZIPs atualizados)
    - **Arquivos:** `terraform/` (execução)
    - **Dependências:** 14.3, 7.15
    - **Passos:**
      1. Executar script de validação pré-plan (`scripts/validate_pre_plan.ps1`)
      2. Executar `terraform plan -out=plan.tfplan`
      3. Salvar output textual do plan para revisão
    - **Testes:** Plan gerado sem erros; validação pré-plan passa
    - **Critério de conclusão:** Plan gerado e pronto para revisão
    - **Requisitos:** 9.11, 15.6
    - **⚠️ Requer:** Acesso AWS real

  - [~] 14.5 Revisar add/change/destroy/replace no plan
    - **Objetivo:** Revisar operações do plan garantindo isolamento da POC MCP
    - **Arquivos:** N/A (revisão de output)
    - **Dependências:** 14.4
    - **Passos:**
      1. Verificar: nenhum `destroy` de recurso existente
      2. Verificar: nenhum `replace` de recurso `connect-mcp-poc-*`
      3. Verificar: apenas `add` e `change` em recursos `connect-bedrock-poc-*`
      4. Contar: total de resources to add, change, destroy
      5. Se qualquer menção a `connect-mcp-poc` no plan: ABORTAR
    - **Testes:** Plan contém apenas operações seguras em recursos Bedrock
    - **Critério de conclusão:** Plan revisado e aprovado como seguro
    - **Requisitos:** 9.11, 15.6

  - [~] 14.6 Validar prefixos no plan
    - **Objetivo:** Confirmar que todos os recursos do plan usam prefixo `connect-bedrock-poc`
    - **Arquivos:** N/A (revisão)
    - **Dependências:** 14.5
    - **Passos:**
      1. Extrair nomes de recursos do plan output
      2. Verificar que TODOS usam prefixo `connect-bedrock-poc`
      3. Verificar ausência de `connect-mcp-poc` em qualquer nome
    - **Testes:** 100% dos recursos com prefixo correto
    - **Critério de conclusão:** Prefixos validados
    - **Requisitos:** 9.2, 15.2

  - [~] 14.7 Validar IAM no plan
    - **Objetivo:** Confirmar que IAM policies incluem `bedrock:InvokeModel` e excluem permissões MCP
    - **Arquivos:** N/A (revisão do plan)
    - **Dependências:** 14.5
    - **Passos:**
      1. Verificar presença de `bedrock:InvokeModel` na policy do Integrator
      2. Verificar ausência de `lambda:InvokeFunctionUrl`
      3. Verificar Resource do statement Bedrock (ARN específico ou wildcard documentado)
    - **Testes:** IAM correto no plan
    - **Critério de conclusão:** Permissões IAM validadas no plan
    - **Requisitos:** 9.5, 9.8, 11.3

  - [~] 14.8 Obter autorização explícita para apply
    - **Objetivo:** Receber aprovação do operador antes de executar `terraform apply`
    - **Arquivos:** N/A
    - **Dependências:** 14.5, 14.6, 14.7
    - **Passos:**
      1. Apresentar resumo do plan ao operador: resources add/change/destroy
      2. Confirmar que nenhuma operação afeta POC MCP
      3. Aguardar aprovação explícita por escrito
    - **Testes:** Aprovação documentada
    - **Critério de conclusão:** Autorização explícita obtida
    - **Requisitos:** 15.5
    - **⚠️ AUTORIZAÇÃO NECESSÁRIA:** Não prosseguir sem aprovação

  - [~] 14.9 Executar apply
    - **Objetivo:** Aplicar plan autorizado
    - **Arquivos:** N/A (execução Terraform)
    - **Dependências:** 14.8
    - **Passos:**
      1. Executar `terraform apply plan.tfplan`
      2. Registrar output do apply (resources created/changed)
      3. Verificar conclusão sem erros
    - **Testes:** Apply conclui sem erros
    - **Critério de conclusão:** Infraestrutura provisionada
    - **Requisitos:** 15.5
    - **⚠️ AUTORIZAÇÃO NECESSÁRIA:** Só executar após aprovação em 14.8
    - **⚠️ Requer:** Acesso AWS real

  - [~] 14.10 Verificação pós-deploy
    - **Objetivo:** Confirmar que recursos foram criados corretamente
    - **Arquivos:** N/A (verificação AWS)
    - **Dependências:** 14.9
    - **Passos:**
      1. Verificar Lambda Integrator criada com env vars BEDROCK_*
      2. Verificar Lambda Initializer criada
      3. Verificar SQS/SNS/DLQ criados com nomes corretos
      4. Verificar DynamoDB tables criadas
      5. Verificar IAM role com `bedrock:InvokeModel`
      6. Verificar event source mapping criado (enabled=false se aplicável)
    - **Testes:** Todos os recursos existem com configuração correta
    - **Critério de conclusão:** Deploy validado
    - **Requisitos:** 9.10

  - [~] 14.11 Executar smoke test real pós-deploy
    - **Objetivo:** Executar `scripts/smoke_test_bedrock.ps1` contra infraestrutura real
    - **Arquivos:** `scripts/smoke_test_bedrock.ps1`
    - **Dependências:** 14.10
    - **Passos:**
      1. Configurar env vars com valores reais do deploy
      2. Executar `powershell -File scripts/smoke_test_bedrock.ps1`
      3. Verificar exit code 0
      4. Registrar latência medida e resposta
    - **Testes:** Smoke test exit 0; resposta em pt-BR; latência registrada
    - **Critério de conclusão:** Smoke test real bem-sucedido
    - **Requisitos:** 13.7
    - **⚠️ Requer:** Acesso AWS real + infraestrutura provisionada

  - [~] 14.12 Validação de logs pós-deploy
    - **Objetivo:** Verificar que logs do CloudWatch estão formatados corretamente
    - **Arquivos:** N/A (verificação CloudWatch)
    - **Dependências:** 14.11
    - **Passos:**
      1. Verificar log group da Lambda Integrator existe
      2. Verificar que logs do smoke test aparecem formatados como JSON
      3. Verificar presença de `correlation_id`, `model_id`, `latency_ms`
      4. Verificar ausência de conteúdo sensível nos logs
    - **Testes:** Logs estruturados com campos obrigatórios; sem dados sensíveis
    - **Critério de conclusão:** Observabilidade validada em produção
    - **Requisitos:** 5.3, 11.1, 11.2
    - **⚠️ Requer:** Acesso AWS real

### Fase 8 — Contact Flow e Chat Real

- [ ] 15. Configurar e testar chat real
  - [~] 15.1 Criar/duplicar Contact Flow separado para POC Bedrock
    - **Objetivo:** Ter Contact Flow dedicado à POC Bedrock sem modificar flow MCP
    - **Arquivos:** N/A (Amazon Connect Console ou Terraform)
    - **Dependências:** 14.10 (deploy concluído)
    - **Passos:**
      1. Criar novo Contact Flow OU duplicar existente no Amazon Connect
      2. Nomear com prefixo `connect-bedrock-poc`
      3. NÃO modificar o flow ativo da POC MCP
    - **Testes:** Novo flow existe; flow MCP inalterado
    - **Critério de conclusão:** Contact Flow separado criado
    - **Requisitos:** 9.3, 15.3

  - [~] 15.2 Associar Contact Flow com Bedrock Initializer
    - **Objetivo:** Configurar flow para invocar a Lambda Initializer da POC Bedrock
    - **Arquivos:** N/A (Amazon Connect Console)
    - **Dependências:** 15.1
    - **Passos:**
      1. Configurar bloco InvokeLambda no flow para chamar `connect-bedrock-poc-dev-initializer`
      2. Configurar timeout do bloco
      3. Configurar tratamento de erro no flow
    - **Testes:** Flow invoca Initializer Bedrock (não MCP)
    - **Critério de conclusão:** Flow conectado ao Initializer correto
    - **Requisitos:** 9.3

  - [~] 15.3 Validar retorno SUCCESS do Initializer
    - **Objetivo:** Confirmar que Initializer retorna status SUCCESS ao Contact Flow
    - **Arquivos:** N/A (teste funcional)
    - **Dependências:** 15.2
    - **Passos:**
      1. Iniciar chat via Contact Flow Bedrock
      2. Verificar que Initializer executa sem erro
      3. Verificar retorno de `$.External.Status = "SUCCESS"` ao flow
    - **Testes:** Initializer retorna SUCCESS
    - **Critério de conclusão:** Inicialização do chat funcional
    - **Requisitos:** 9.10
    - **⚠️ Requer:** Acesso AWS real + Contact Flow configurado

  - [~] 15.4 Validar timeout do Initializer
    - **Objetivo:** Confirmar que Initializer completa dentro do timeout de 8s
    - **Arquivos:** N/A (verificação de logs)
    - **Dependências:** 15.3
    - **Passos:**
      1. Verificar duração da execução do Initializer nos logs
      2. Confirmar < 8s
    - **Testes:** Execução < 8s
    - **Critério de conclusão:** Timeout do Initializer respeitado
    - **Requisitos:** 9.10

  - [~] 15.5 Publicar Contact Flow Bedrock
    - **Objetivo:** Publicar o flow para torná-lo disponível para testes de chat
    - **Arquivos:** N/A (Amazon Connect Console)
    - **Dependências:** 15.3
    - **Passos:**
      1. Publicar Contact Flow no Amazon Connect
      2. Verificar que ficou ativo
      3. Confirmar que flow MCP continua publicado e inalterado
    - **Testes:** Flow Bedrock publicado; flow MCP inalterado
    - **Critério de conclusão:** Flow disponível para chat
    - **Requisitos:** 9.3, 15.3

  - [~] 15.6 Testar chat real
    - **Objetivo:** Enviar mensagem real via Chat Widget e receber resposta do Bedrock
    - **Arquivos:** N/A (teste manual via Chat Widget)
    - **Dependências:** 15.5, 14.11
    - **Passos:**
      1. Abrir Chat Widget conectado ao Contact Flow Bedrock
      2. Enviar pergunta em português
      3. Aguardar resposta (< 30s esperado)
      4. Verificar que resposta foi recebida
    - **Testes:** Mensagem enviada → resposta recebida no chat
    - **Critério de conclusão:** Chat funcional ponta a ponta
    - **Requisitos:** 3.4
    - **⚠️ Requer:** Acesso AWS real + Chat Widget configurado

  - [~] 15.7 Validar resposta em português
    - **Objetivo:** Confirmar que a resposta do Bedrock está em português brasileiro
    - **Arquivos:** N/A (validação manual)
    - **Dependências:** 15.6
    - **Passos:**
      1. Verificar idioma da resposta (pt-BR)
      2. Verificar coerência e clareza
      3. Enviar 2-3 perguntas adicionais variadas
    - **Testes:** Todas as respostas em português e coerentes
    - **Critério de conclusão:** Modelo responde em pt-BR conforme system prompt
    - **Requisitos:** 4.2

  - [~] 15.8 Buscar logs por correlation_id
    - **Objetivo:** Rastrear ciclo completo de uma mensagem via correlation_id nos logs
    - **Arquivos:** N/A (CloudWatch Logs)
    - **Dependências:** 15.6
    - **Passos:**
      1. Identificar correlation_id de uma mensagem processada
      2. Buscar em CloudWatch Logs por esse correlation_id
      3. Verificar que TODAS as entradas do ciclo contêm o mesmo valor
      4. Verificar sequência: parsing → idempotência → sessão → Bedrock → SendMessage → COMPLETED
    - **Testes:** Todas as entradas do ciclo rastreáveis por correlation_id
    - **Critério de conclusão:** Rastreabilidade ponta a ponta confirmada
    - **Requisitos:** 5.1, 5.3, 5.4
    - **⚠️ Requer:** Acesso AWS real

  - [~] 15.9 Verificar ausência de FAILED_FINAL
    - **Objetivo:** Confirmar que nenhuma mensagem do teste ficou em FAILED_FINAL
    - **Arquivos:** N/A (CloudWatch Logs + DynamoDB)
    - **Dependências:** 15.6
    - **Passos:**
      1. Buscar logs por "FAILED_FINAL" no período do teste
      2. Verificar que nenhuma mensagem do teste foi marcada como falha final
      3. Confirmar status COMPLETED para todas as mensagens
    - **Testes:** Zero FAILED_FINAL durante teste de chat
    - **Critério de conclusão:** Processamento bem-sucedido para todas as mensagens
    - **Requisitos:** 7.2

  - [~] 15.10 Confirmar POC MCP ainda funcional
    - **Objetivo:** Verificar que a POC MCP original não foi afetada
    - **Arquivos:** N/A (teste manual via Chat Widget MCP)
    - **Dependências:** 15.6
    - **Passos:**
      1. Abrir Chat Widget conectado ao Contact Flow MCP (original)
      2. Enviar mensagem de teste
      3. Verificar que resposta é recebida normalmente
      4. Confirmar que infraestrutura MCP continua operacional
    - **Testes:** Chat MCP funcional e independente
    - **Critério de conclusão:** Isolamento confirmado — ambas as POCs coexistem
    - **Requisitos:** 15.3, 15.4
    - **⚠️ Requer:** Acesso AWS real + Chat Widget MCP

### Fase 9 — Documentação

- [ ] 16. Criar documentação completa
  - [~] 16.1 Atualizar README.md
    - **Objetivo:** Atualizar README com arquitetura Bedrock, pré-requisitos, estrutura e quickstart
    - **Arquivos:** `README.md`
    - **Dependências:** 14.10 (deploy concluído), 15.6 (chat funcional)
    - **Passos:**
      1. Descrever arquitetura Bedrock Converse (visão geral)
      2. Listar pré-requisitos (AWS CLI, Terraform, Python, acesso Bedrock)
      3. Mostrar estrutura do repositório atualizada
      4. Fornecer instruções de quickstart (testes locais e smoke test)
      5. Referenciar documentação detalhada em `docs/`
    - **Testes:** README completo com seções obrigatórias
    - **Critério de conclusão:** README atualizado para refletir POC Bedrock
    - **Requisitos:** 14.1

  - [~] 16.2 Criar docs/architecture.md
    - **Objetivo:** Documentar arquitetura com diagrama Mermaid e responsabilidades
    - **Arquivos:** `docs/architecture.md` (novo/reescrito)
    - **Dependências:** 14.10
    - **Passos:**
      1. Incluir diagrama Mermaid: Usuário → Connect → SNS → SQS → Integrator → BedrockClient → Converse API → Participant Service → Usuário
      2. Descrever responsabilidade de cada componente
      3. Documentar fluxo de retry e DLQ
      4. Documentar isolamento da POC MCP
    - **Testes:** Diagrama e descrições completas
    - **Critério de conclusão:** Arquitetura documentada com diagrama
    - **Requisitos:** 14.2

  - [~] 16.3 Criar docs/deployment-guide.md
    - **Objetivo:** Documentar passos de deploy com pré-requisitos e verificação
    - **Arquivos:** `docs/deployment-guide.md` (novo/reescrito)
    - **Dependências:** 14.10
    - **Passos:**
      1. Seção de pré-requisitos: ferramentas, permissões AWS, variáveis de ambiente
      2. Passos numerados: infraestrutura → build → deploy → verificação
      3. Incluir validação pré-plan obrigatória
      4. Incluir smoke test como gate pré-chat
    - **Testes:** Guia seguível por outro desenvolvedor
    - **Critério de conclusão:** Deploy guide completo e sequencial
    - **Requisitos:** 14.3

  - [~] 16.4 Criar docs/testing-strategy.md
    - **Objetivo:** Documentar estratégia de testes com comandos e cobertura
    - **Arquivos:** `docs/testing-strategy.md` (novo)
    - **Dependências:** 10.5
    - **Passos:**
      1. Descrever testes unitários, integração, PBT e smoke test
      2. Incluir comandos para executar cada categoria
      3. Definir limiar mínimo de cobertura
      4. Listar propriedades testadas com Hypothesis
    - **Testes:** Documento com comandos executáveis e limiares definidos
    - **Critério de conclusão:** Estratégia de testes documentada
    - **Requisitos:** 14.4

  - [~] 16.5 Criar docs/troubleshooting.md
    - **Objetivo:** Documentar cenários de erro com sintomas, causas e ações corretivas
    - **Arquivos:** `docs/troubleshooting.md` (reescrito)
    - **Dependências:** 14.10
    - **Passos:**
      1. Cenário: AccessDeniedException — sintomas, causas, ação
      2. Cenário: ThrottlingException — sintomas, causas, ação
      3. Cenário: ModelNotFoundException — sintomas, causas, ação
      4. Cenário: Token expirado — sintomas, causas, ação
      5. Cenário: BedrockConfigurationError no cold start — sintomas, causas, ação
    - **Testes:** Cenários cobrem erros mais comuns
    - **Critério de conclusão:** Troubleshooting com mínimo 4 cenários documentados
    - **Requisitos:** 14.5

  - [~] 16.6 Criar docs/security.md
    - **Objetivo:** Documentar permissões IAM, KMS e regras de sanitização de log
    - **Arquivos:** `docs/security.md` (novo/reescrito)
    - **Dependências:** 14.10
    - **Passos:**
      1. Documentar IAM roles por Lambda (Initializer, Integrator)
      2. Documentar uso de KMS para criptografia de tokens
      3. Documentar regras de sanitização: campos permitidos vs proibidos
      4. Documentar princípio de menor privilégio aplicado
    - **Testes:** Documento cobre IAM, KMS e logging
    - **Critério de conclusão:** Segurança documentada completamente
    - **Requisitos:** 14.6

  - [~] 16.7 Criar docs/bedrock-converse-flow.md
    - **Objetivo:** Documentar estrutura da requisição Converse API e parsing de resposta
    - **Arquivos:** `docs/bedrock-converse-flow.md` (novo)
    - **Dependências:** 3.5
    - **Passos:**
      1. Documentar estrutura da requisição (modelId, messages, system, inferenceConfig)
      2. Documentar lógica de parsing multi-bloco
      3. Documentar parâmetros configuráveis (max tokens, temperature, timeout)
      4. Incluir exemplos de requisição e resposta
    - **Testes:** Documento técnico com exemplos concretos
    - **Critério de conclusão:** Fluxo Converse documentado com exemplos
    - **Requisitos:** 14.7

  - [~] 16.8 Criar docs/migration-from-mcp.md
    - **Objetivo:** Documentar componentes removidos, adicionados e alterados na migração
    - **Arquivos:** `docs/migration-from-mcp.md` (novo)
    - **Dependências:** 5.1, 7.3
    - **Passos:**
      1. Documentar componentes removidos: MCP Server, MCPClient, Function URL, SigV4
      2. Documentar componentes adicionados: BedrockClient, Converse API integration
      3. Documentar componentes alterados: processor, IAM roles, env vars
      4. Documentar que a POC MCP continua funcional e independente
    - **Testes:** Documento cobre removed/added/changed
    - **Critério de conclusão:** Migração documentada completamente
    - **Requisitos:** 14.8

  - [~] 16.9 Criar docs/cost-considerations.md
    - **Objetivo:** Estimar custos da Bedrock Converse API com premissas declaradas
    - **Arquivos:** `docs/cost-considerations.md` (novo)
    - **Dependências:** 2.7 (modelo escolhido)
    - **Passos:**
      1. Declarar premissas: tokens de input/output por mensagem, conversas mensais
      2. Calcular custo estimado com preço oficial do modelo selecionado
      3. Comparar com custo do MCP (Lambda invocations + Function URL)
      4. Incluir fonte oficial de precificação e data de consulta
    - **Testes:** Estimativa com premissas claras e fonte oficial
    - **Critério de conclusão:** Custos estimados com premissas documentadas
    - **Requisitos:** 14.9
    - **⚠️ Bloqueado até:** Modelo selecionado (Fase 1)

  - [~] 16.10 Criar docs/known-limitations.md
    - **Objetivo:** Listar limitações da POC organizadas por categoria
    - **Arquivos:** `docs/known-limitations.md` (novo)
    - **Dependências:** 15.6 (chat testado)
    - **Passos:**
      1. Categoria Infraestrutura: estado local, sem multi-region, etc.
      2. Categoria Funcionalidade: single-turn, sem RAG, sem knowledge base
      3. Categoria Segurança: wildcard IAM (se aplicável), sem WAF
      4. Categoria Escalabilidade: sem provisioned throughput, throttling limits
      5. Incluir potencial resolução em produção para cada limitação
    - **Testes:** Limitações listadas com descrição e resolução potencial
    - **Critério de conclusão:** Limitações documentadas por categoria
    - **Requisitos:** 14.10

  - [~] 16.11 Criar skill connect-bedrock-debugger
    - **Objetivo:** Criar Kiro skill para debugging do fluxo Bedrock
    - **Arquivos:** `.kiro/skills/connect-bedrock-debugger.md` (novo)
    - **Dependências:** 14.10
    - **Passos:**
      1. Definir skill com contexto sobre a arquitetura Bedrock
      2. Incluir instruções para rastrear problemas por correlation_id
      3. Incluir referências aos logs estruturados e campos importantes
      4. Incluir cenários comuns de debug (timeout, AccessDenied, throttling)
    - **Testes:** Skill criada com conteúdo útil
    - **Critério de conclusão:** Skill funcional para debugging
    - **Requisitos:** 14.5

  - [~] 16.12 Criar steering bedrock-debugging.md
    - **Objetivo:** Criar Kiro steering file para guiar debugging do Bedrock
    - **Arquivos:** `.kiro/steering/bedrock-debugging.md` (novo)
    - **Dependências:** 16.11
    - **Passos:**
      1. Definir workflow de debugging passo a passo
      2. Incluir comandos AWS CLI úteis para investigação
      3. Incluir padrões de busca em CloudWatch Logs
      4. Incluir checklist de verificação pós-problema
    - **Testes:** Steering file com instruções acionáveis
    - **Critério de conclusão:** Guia de debugging criado
    - **Requisitos:** 14.5

- [~] 17. Checkpoint — Documentação completa
  - Ensure all tests pass, ask the user if questions arise.
  - **Critério:** Todos os 12 documentos criados com conteúdo substantivo. Links internos funcionais.

### Fase 10 — Encerramento

- [ ] 18. Encerrar POC e obter autorização
  - [~] 18.1 Revisar git diff
    - **Objetivo:** Revisar todas as alterações realizadas antes de commit
    - **Arquivos:** N/A (git)
    - **Dependências:** 17 (Checkpoint documentação)
    - **Passos:**
      1. Executar `git diff --stat` para visão geral das alterações
      2. Verificar que nenhum arquivo da POC MCP foi alterado inadvertidamente
      3. Verificar que não há arquivos sensíveis (`.env`, credentials) no diff
      4. Verificar que `terraform.tfstate` não está incluído no commit
    - **Testes:** Diff revisado; sem alterações acidentais
    - **Critério de conclusão:** Alterações revisadas e aprovadas
    - **Requisitos:** 15.4, 15.5

  - [~] 18.2 Executar suíte completa de testes
    - **Objetivo:** Rodar todos os testes uma última vez para confirmação final
    - **Arquivos:** N/A (execução pytest)
    - **Dependências:** 18.1
    - **Passos:**
      1. Executar `pytest tests/ -v --tb=short --cov=src --cov-report=term-missing`
      2. Confirmar 100% dos testes passando
      3. Registrar cobertura final
    - **Testes:** Suíte completa verde
    - **Critério de conclusão:** Todos os testes passam na versão final
    - **Requisitos:** 12.1–12.10

  - [~] 18.3 Validar links da documentação
    - **Objetivo:** Verificar que links internos entre documentos funcionam
    - **Arquivos:** `docs/*.md`, `README.md`
    - **Dependências:** 16.1–16.12
    - **Passos:**
      1. Verificar links relativos entre documentos
      2. Verificar que todos os arquivos referenciados existem
      3. Corrigir links quebrados (se houver)
    - **Testes:** Zero links quebrados
    - **Critério de conclusão:** Documentação com links válidos
    - **Requisitos:** 14.1–14.10

  - [~] 18.4 Revisar Terraform plan final
    - **Objetivo:** Gerar plan final e confirmar estado limpo
    - **Arquivos:** N/A (Terraform)
    - **Dependências:** 18.1
    - **Passos:**
      1. Executar `terraform plan` e verificar "No changes" (se já aplicado)
      2. Se não aplicado: verificar que plan não contém surpresas
      3. Confirmar isolamento: zero referências a `connect-mcp-poc`
    - **Testes:** Plan limpo ou apenas operações esperadas
    - **Critério de conclusão:** Estado Terraform consistente
    - **Requisitos:** 9.11, 15.6
    - **⚠️ Requer:** Acesso AWS real

  - [~] 18.5 Registrar modelo escolhido
    - **Objetivo:** Documentar formalmente o modelo usado na POC com evidências finais
    - **Arquivos:** `docs/model-selection-evidence.md`
    - **Dependências:** 2.9, 14.11
    - **Passos:**
      1. Confirmar BEDROCK_MODEL_ID final utilizado no deploy
      2. Registrar modelo, região, tipo (foundation/inference profile)
      3. Registrar data do deploy e teste real
    - **Testes:** Documento atualizado com informações finais
    - **Critério de conclusão:** Modelo documentado com evidência de funcionamento
    - **Requisitos:** 10.3

  - [~] 18.6 Registrar latência medida
    - **Objetivo:** Documentar latência medida no ambiente real (não estimativa)
    - **Arquivos:** `docs/model-selection-evidence.md`
    - **Dependências:** 14.11, 15.6
    - **Passos:**
      1. Registrar latência do smoke test real (P50, P90, P99)
      2. Registrar latência do chat real (se disponível nos logs)
      3. Registrar condições: data, região, modelo, número de amostras
      4. NÃO registrar valores estimados como medidos
    - **Testes:** Latência documentada com condições do teste
    - **Critério de conclusão:** Latência real registrada com evidência
    - **Requisitos:** 10.3

  - [~] 18.7 Registrar limitações encontradas
    - **Objetivo:** Atualizar known-limitations.md com limitações descobertas durante implementação
    - **Arquivos:** `docs/known-limitations.md`
    - **Dependências:** 15.6
    - **Passos:**
      1. Revisar issues encontrados durante implementação
      2. Adicionar limitações não previstas no design
      3. Atualizar status de limitações previstas (confirmadas ou não)
    - **Testes:** Limitações atualizadas com dados reais
    - **Critério de conclusão:** Limitações refletem experiência real da implementação
    - **Requisitos:** 14.10

  - [~] 18.8 Obter autorização para commit
    - **Objetivo:** Receber aprovação explícita para criar commit com todas as alterações
    - **Arquivos:** N/A
    - **Dependências:** 18.1, 18.2, 18.3
    - **Passos:**
      1. Apresentar resumo: arquivos alterados, testes passando, cobertura
      2. Confirmar que operador aprova o commit
      3. Aguardar aprovação explícita por escrito
    - **Testes:** Aprovação documentada
    - **Critério de conclusão:** Autorização de commit obtida
    - **Requisitos:** 15.5
    - **⚠️ AUTORIZAÇÃO NECESSÁRIA:** Não commitar sem aprovação

  - [~] 18.9 Obter autorização para push
    - **Objetivo:** Receber aprovação explícita para push ao repositório remoto
    - **Arquivos:** N/A
    - **Dependências:** 18.8
    - **Passos:**
      1. Confirmar branch correta para push
      2. Confirmar que não é push direto para main/master
      3. Aguardar aprovação explícita do operador
    - **Testes:** Aprovação documentada
    - **Critério de conclusão:** Autorização de push obtida
    - **Requisitos:** 15.5
    - **⚠️ AUTORIZAÇÃO NECESSÁRIA:** Não fazer push sem aprovação

  - [~] 18.10 Registrar critérios de aceitação finais
    - **Objetivo:** Confirmar que todos os critérios de aceitação foram atendidos
    - **Arquivos:** `docs/acceptance-criteria-final.md` (novo)
    - **Dependências:** 18.2, 18.5, 18.6, 18.7
    - **Passos:**
      1. Para cada requisito (1-15): marcar como atendido ou com ressalva
      2. Registrar evidência de cada item atendido
      3. Listar itens com ressalvas e justificativas
      4. Registrar: data de conclusão, modelo utilizado, latência medida
      5. Confirmar: POC MCP inalterada e funcional
    - **Testes:** Documento com status de cada requisito
    - **Critério de conclusão:** Todos os critérios revisados e documentados
    - **Requisitos:** 1.1–15.6

## Notes

- Tasks marcadas com `*` são opcionais e podem ser puladas para MVP mais rápido
- Cada task referencia requisitos específicos para rastreabilidade
- Checkpoints garantem validação incremental
- Testes de propriedade (PBT) validam propriedades universais de corretude com Hypothesis
- Testes unitários validam exemplos específicos e edge cases
- **Gates** entre fases impedem avanço sem confirmação de isolamento e qualidade
- Tasks com **⚠️ Requer: Acesso AWS real** não podem ser executadas sem credenciais válidas
- Tasks com **⚠️ AUTORIZAÇÃO NECESSÁRIA** requerem aprovação explícita do operador
- Tasks com **⚠️ Bloqueado até** dependem de uma decisão ou resultado anterior
- NÃO executar `terraform apply`, `git commit` ou `git push` sem autorização explícita
- O smoke test DEVE ser executado ANTES de qualquer teste de chat real

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1"] },
    { "id": 1, "tasks": ["0.2", "0.3", "0.4", "0.5", "0.6"] },
    { "id": 2, "tasks": ["0.7"] },
    { "id": 3, "tasks": ["2.1", "3.1"] },
    { "id": 4, "tasks": ["2.2", "3.2", "3.3", "3.4"] },
    { "id": 5, "tasks": ["2.3", "3.5", "3.14"] },
    { "id": 6, "tasks": ["2.4", "3.6", "3.7", "3.8", "3.9", "3.10"] },
    { "id": 7, "tasks": ["2.5", "3.11", "3.12", "3.13"] },
    { "id": 8, "tasks": ["2.6"] },
    { "id": 9, "tasks": ["2.7"] },
    { "id": 10, "tasks": ["2.8"] },
    { "id": 11, "tasks": ["2.9"] },
    { "id": 12, "tasks": ["5.1", "7.1"] },
    { "id": 13, "tasks": ["5.2", "5.3", "5.7", "5.8", "7.2"] },
    { "id": 14, "tasks": ["5.4", "5.5", "5.6", "5.9", "5.10", "5.11", "5.12", "7.3", "7.6"] },
    { "id": 15, "tasks": ["7.4", "7.5", "7.10", "7.11"] },
    { "id": 16, "tasks": ["7.7", "7.12", "7.13", "7.14"] },
    { "id": 17, "tasks": ["7.8"] },
    { "id": 18, "tasks": ["7.9", "7.15"] },
    { "id": 19, "tasks": ["9.1", "9.2", "9.3", "9.4", "9.5"] },
    { "id": 20, "tasks": ["9.6", "9.7", "9.8", "9.9", "9.10", "9.11"] },
    { "id": 21, "tasks": ["9.12", "10.1", "10.2", "10.3"] },
    { "id": 22, "tasks": ["10.4", "10.5"] },
    { "id": 23, "tasks": ["12.1"] },
    { "id": 24, "tasks": ["12.2", "12.3"] },
    { "id": 25, "tasks": ["12.4"] },
    { "id": 26, "tasks": ["12.5"] },
    { "id": 27, "tasks": ["12.6", "12.7"] },
    { "id": 28, "tasks": ["14.1"] },
    { "id": 29, "tasks": ["14.2"] },
    { "id": 30, "tasks": ["14.3"] },
    { "id": 31, "tasks": ["14.4"] },
    { "id": 32, "tasks": ["14.5", "14.6", "14.7"] },
    { "id": 33, "tasks": ["14.8"] },
    { "id": 34, "tasks": ["14.9"] },
    { "id": 35, "tasks": ["14.10"] },
    { "id": 36, "tasks": ["14.11"] },
    { "id": 37, "tasks": ["14.12"] },
    { "id": 38, "tasks": ["15.1"] },
    { "id": 39, "tasks": ["15.2"] },
    { "id": 40, "tasks": ["15.3", "15.4"] },
    { "id": 41, "tasks": ["15.5"] },
    { "id": 42, "tasks": ["15.6"] },
    { "id": 43, "tasks": ["15.7", "15.8", "15.9", "15.10"] },
    { "id": 44, "tasks": ["16.1", "16.2", "16.3", "16.4", "16.5", "16.6", "16.7", "16.8", "16.9", "16.10", "16.11"] },
    { "id": 45, "tasks": ["16.12"] },
    { "id": 46, "tasks": ["18.1"] },
    { "id": 47, "tasks": ["18.2", "18.3", "18.4", "18.5", "18.6", "18.7"] },
    { "id": 48, "tasks": ["18.8"] },
    { "id": 49, "tasks": ["18.9"] },
    { "id": 50, "tasks": ["18.10"] }
  ]
}
```
