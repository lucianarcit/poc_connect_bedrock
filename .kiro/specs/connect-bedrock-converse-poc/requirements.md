# Requirements Document

## Introduction

Este documento especifica os requisitos da POC-01: substituição da camada MCP (Model Context Protocol) na integração de chat do Amazon Connect por uma integração direta com a Amazon Bedrock Converse API. A infraestrutura existente do Amazon Connect (Chat Widget, Contact Flow, Initializer Lambda, SNS, SQS, DLQ) é preservada. Apenas o caminho de chamada de IA do Integrator muda: de MCP Client → Lambda Function URL → MCP Server para BedrockClient → bedrock-runtime Converse API.

O sistema deve responder perguntas dos usuários em português brasileiro usando um modelo Bedrock configurável, mantendo todos os padrões de confiabilidade existentes (idempotência, DLQ, retry, ID de correlação).

## Glossary

- **Integrator**: Função AWS Lambda que consome mensagens do SQS, processa-as e envia respostas de volta ao chat do Amazon Connect via Participant Service API.
- **BedrockClient**: Novo módulo de abstração (`src/shared/bedrock_client/`) responsável por toda comunicação com a Amazon Bedrock Converse API. O Integrator depende exclusivamente deste módulo para inferência de IA.
- **Converse API**: Método `converse` do Amazon Bedrock Runtime que aceita model ID, system prompt, mensagens e configuração de inferência, retornando texto gerado pelo modelo.
- **Participant Service**: API do Amazon Connect Participant Service usada para enviar mensagens de volta ao chat (via `SendMessage` com ConnectionToken).
- **ID de correlação**: Identificador único propagado em todas as entradas de log de um ciclo de processamento de mensagem, permitindo rastreamento ponta a ponta.
- **System Prompt**: Instrução de texto configurável enviada ao Bedrock que define o comportamento do modelo (idioma, tom, restrições).
- **Inference Configuration**: Parâmetros que controlam a geração do modelo: `maxTokens` e `temperature`, configurados via variáveis de ambiente.
- **MESSAGEMETADATA**: Tipo de evento SNS publicado pelo Amazon Connect contendo recibos de entrega e metadados, não conteúdo do usuário. Deve ser ignorado pelo Integrator.
- **DLQ (Fila de mensagens mortas)**: Fila que recebe mensagens após esgotadas as tentativas máximas de retry.
- **Idempotency Repository**: Mecanismo baseado em DynamoDB que previne processamento duplicado da mesma mensagem.

## Requirements

### Requirement 1: Recepção de Mensagens do Amazon Connect

**User Story:** Como operador do sistema, quero que o Integrator receba e parse mensagens de chat do Amazon Connect via pipeline SNS/SQS existente, para que as perguntas dos usuários cheguem à camada de processamento de IA.

#### Acceptance Criteria

1. QUANDO um registro SQS contendo uma notificação SNS com Type "MESSAGE", ParticipantRole "CUSTOMER", ContentType suportado e Content não vazio for recebido, O Integrator DEVE extrair o conteúdo da mensagem e invocar a camada de processamento de IA.
2. QUANDO um registro SQS contendo uma notificação SNS com Type "MESSAGEMETADATA" for recebido, O Integrator DEVE ignorar o registro sem invocar a camada de IA e sem reportá-lo como batch item failure.
3. QUANDO um registro SQS contendo uma notificação SNS com ParticipantRole "CUSTOM_BOT", "SYSTEM" ou "AGENT" for recebido, O Integrator DEVE ignorar o registro sem invocar a camada de IA e sem reportá-lo como batch item failure.
4. QUANDO uma mensagem com ContentType "text/plain" for recebida, O Integrator DEVE aceitá-la como tipo de conteúdo suportado para processamento.
5. QUANDO uma mensagem com ContentType "text/markdown" for recebida, O Integrator DEVE aceitá-la como tipo de conteúdo suportado para processamento.
6. SE um registro SQS contiver ContentType diferente de "text/plain" ou "text/markdown", ENTÃO O Integrator DEVE ignorar o registro sem invocar a camada de IA e sem reportá-lo como batch item failure.
7. SE o body de um registro SQS não for JSON válido ou não contiver a estrutura de envelope SNS esperada com campo Message parseável, ENTÃO O Integrator DEVE marcar o registro como batch item failure para que o SQS reenvie.
8. SE uma mensagem tiver Type "MESSAGE" e ParticipantRole "CUSTOMER" mas o campo Content estiver vazio ou contiver apenas espaços em branco, ENTÃO O Integrator DEVE ignorar o registro sem invocar a camada de IA e sem reportá-lo como batch item failure.

### Requirement 2: Invocação da Bedrock Converse API

**User Story:** Como operador do sistema, quero que o Integrator envie mensagens dos usuários ao Amazon Bedrock via Converse API, para que o sistema gere respostas assistidas por IA.

#### Acceptance Criteria

1. QUANDO uma mensagem do usuário com conteúdo de texto não vazio (1 a 4096 caracteres inclusive) estiver pronta para processamento, O BedrockClient DEVE chamar o método `converse` do Amazon Bedrock Runtime com o model ID configurado, system prompt, mensagem do usuário e configuração de inferência, e DEVE retornar o texto extraído de todos os blocos de conteúdo do tipo texto conforme o Requisito 3.
2. O BedrockClient DEVE ler o identificador do modelo da variável de ambiente BEDROCK_MODEL_ID.
3. O BedrockClient DEVE ler a contagem máxima de tokens da variável de ambiente BEDROCK_MAX_TOKENS com valor padrão de 1024, aceitando valores inteiros entre 1 e 4096.
4. O BedrockClient DEVE ler a temperature da variável de ambiente BEDROCK_TEMPERATURE com valor padrão de 0.7, aceitando valores decimais entre 0.0 e 1.0 inclusive.
5. O BedrockClient DEVE ler o system prompt da variável de ambiente BEDROCK_SYSTEM_PROMPT com um valor padrão que instrua o modelo a responder em português, ser claro e objetivo, atuar como agente de suporte, não inventar informações e informar quando não tiver dados suficientes.
6. O BedrockClient DEVE construir a requisição da Converse API com a mensagem do usuário no parâmetro `messages` usando role "user" e um único bloco de conteúdo de texto.
7. O Integrator NÃO DEVE chamar o cliente boto3 bedrock-runtime diretamente; toda comunicação com Bedrock DEVE passar pelo módulo BedrockClient.
8. SE a variável de ambiente BEDROCK_MODEL_ID não estiver definida ou estiver vazia, ENTÃO O BedrockClient DEVE lançar um erro de configuração no momento da inicialização sem chamar a Converse API.
9. SE a chamada à Converse API falhar por throttling, indisponibilidade do serviço ou erro do modelo, ENTÃO O BedrockClient DEVE lançar uma exceção indicando a categoria da falha (erro transitório ou erro fatal) para que o chamador decida se deve retentar.
10. SE a chamada à Converse API não retornar resposta dentro do BEDROCK_TIMEOUT_SECONDS configurado (padrão 20 segundos), ENTÃO O BedrockClient DEVE abortar a requisição e lançar uma exceção de timeout. O timeout do Bedrock DEVE ser sempre pelo menos 5 segundos menor que o timeout da Lambda Integrator para permitir margem para leituras no DynamoDB, descriptografia KMS, chamadas ao Participant Service e finalização.

### Requirement 3: Extração da Resposta e Entrega

**User Story:** Como usuário final, quero receber a resposta gerada pela IA no chat do Amazon Connect, para que minha pergunta seja respondida.

#### Acceptance Criteria

1. QUANDO a Converse API retornar uma resposta com um único bloco de conteúdo de texto, O BedrockClient DEVE extrair o texto de `output.message.content[0].text`.
2. QUANDO a Converse API retornar uma resposta com múltiplos blocos de conteúdo, O BedrockClient DEVE extrair apenas os blocos do tipo "text", concatenar seus valores de texto separados por um único caractere de nova linha (`\n`) e ignorar blocos que não sejam de texto.
3. QUANDO a Converse API retornar uma resposta onde o array de content estiver vazio ou o campo content estiver ausente, O BedrockClient DEVE retornar a mensagem de fallback "Desculpe, não consegui gerar uma resposta. Por favor, tente reformular sua pergunta.".
4. QUANDO o BedrockClient retornar texto extraído, O Integrator DEVE enviar o texto ao usuário via Participant Service SendMessage API usando o ConnectionToken descriptografado da sessão.
5. QUANDO a resposta for enviada com sucesso ao chat, O Idempotency Repository DEVE marcar a mensagem como COMPLETED.
6. QUANDO a Converse API retornar uma resposta contendo apenas blocos de conteúdo não-texto e nenhum bloco de texto, O BedrockClient DEVE retornar a mesma mensagem de fallback utilizada para array de content vazio.

### Requirement 4: Resposta em Português

**User Story:** Como usuário final, quero receber respostas em português, para que eu possa entender o assistente de IA no meu idioma.

#### Acceptance Criteria

1. O BedrockClient DEVE passar o texto do system prompt no parâmetro `system` da Converse API como um único bloco de conteúdo de texto.
2. O system prompt padrão do BedrockClient DEVE conter a instrução exata "Responda sempre em português brasileiro".
3. O system prompt padrão do BedrockClient DEVE conter uma instrução direcionando o modelo a fornecer respostas claras e objetivas (ex.: "Seja claro e objetivo nas respostas").
4. O system prompt padrão do BedrockClient DEVE conter uma instrução direcionando o modelo a se comportar como agente virtual de suporte (ex.: "Atue como agente virtual de suporte").
5. O system prompt padrão do BedrockClient DEVE conter uma instrução direcionando o modelo a não fabricar informações indisponíveis (ex.: "Não invente informações que não estejam disponíveis").
6. O system prompt padrão do BedrockClient DEVE conter uma instrução direcionando o modelo a informar o usuário quando não tiver dados suficientes para responder (ex.: "Informe ao usuário quando não tiver dados suficientes para responder").
7. SE a variável de ambiente BEDROCK_SYSTEM_PROMPT estiver definida, ENTÃO O BedrockClient DEVE usar o valor fornecido como system prompt em vez do padrão, sem exigir que as instruções padrão estejam presentes no override.

### Requirement 5: Propagação do ID de Correlação

**User Story:** Como operador do sistema, quero um ID de correlação presente em todas as entradas de log do ciclo de vida de uma mensagem, para que eu possa rastrear problemas ponta a ponta.

#### Acceptance Criteria

1. QUANDO o evento não contiver um campo de ID de correlação reconhecido nos seus atributos de mensagem ou payload, O Integrator DEVE gerar um ID de correlação como string UUID v4 e incluí-lo como campo de nível superior chamado "correlation_id" em toda entrada de log estruturado emitida durante o ciclo de processamento dessa mensagem.
2. QUANDO o evento contiver um campo de ID de correlação reconhecido nos seus atributos de mensagem ou payload, O Integrator DEVE propagar o valor recebido e incluí-lo como campo de nível superior chamado "correlation_id" em toda entrada de log estruturado emitida durante o ciclo de processamento dessa mensagem.
3. QUANDO invocar a Converse API, O BedrockClient DEVE incluir o ID de correlação na entrada de log da requisição e na entrada de log da resposta como campo de nível superior chamado "correlation_id".
4. QUANDO enviar a resposta via Participant Service, O Integrator DEVE incluir o ID de correlação como campo de nível superior chamado "correlation_id" nas entradas de log de tentativa de envio e resultado do envio.
5. SE uma entrada de log for emitida durante o ciclo de processamento de uma mensagem e não contiver o campo "correlation_id", ENTÃO O sistema DEVE tratar isso como um defeito — toda entrada de log entre recepção da mensagem e disposição final (COMPLETED ou FAILED_FINAL) deve conter o ID de correlação.

### Requirement 6: Tratamento de Erros — Erros do Bedrock

**User Story:** Como operador do sistema, quero que erros do Bedrock sejam tratados de forma elegante com retry ou fallback apropriado, para que os usuários recebam uma resposta e erros transitórios sejam retentados.

#### Acceptance Criteria

1. SE a Converse API retornar ThrottlingException, ENTÃO O BedrockClient DEVE lançar um erro transitório que faz o Integrator falhar o item SQS para retry.
2. SE a Converse API retornar AccessDeniedException, ENTÃO O BedrockClient DEVE lançar um erro fatal que faz o Integrator enviar uma mensagem de erro predefinida em português ao usuário e marcar a mensagem como FAILED_FINAL.
3. SE a chamada à Converse API exceder o timeout definido pela variável de ambiente BEDROCK_TIMEOUT_SECONDS (padrão 20 segundos), ENTÃO O BedrockClient DEVE lançar um erro transitório que faz o Integrator falhar o item SQS para retry.
4. SE a Converse API retornar ModelTimeoutException, ENTÃO O BedrockClient DEVE lançar um erro transitório que faz o Integrator falhar o item SQS para retry.
5. SE a Converse API retornar ValidationException, ENTÃO O BedrockClient DEVE lançar um erro fatal que faz o Integrator enviar uma mensagem de erro predefinida em português ao usuário e marcar a mensagem como FAILED_FINAL.
6. SE a Converse API retornar ServiceUnavailableException, ENTÃO O BedrockClient DEVE lançar um erro transitório que faz o Integrator falhar o item SQS para retry.
7. SE qualquer ClientError inesperado ocorrer durante a chamada à Converse API, ENTÃO O BedrockClient DEVE registrar o código de erro e lançar um erro fatal que faz o Integrator enviar uma mensagem de erro predefinida em português ao usuário e marcar a mensagem como FAILED_FINAL.
8. SE um erro transitório fizer o item SQS ser recebido mais de 3 vezes (o maxReceiveCount configurado), ENTÃO A fila SQS DEVE entregar a mensagem à DLQ sem mais retentativas.

### Requirement 7: Preservação dos Padrões de Confiabilidade Existentes

**User Story:** Como operador do sistema, quero que todos os padrões de confiabilidade existentes (DLQ, idempotência, partial batch failure) permaneçam funcionais, para que a migração não degrade a resiliência do sistema.

#### Acceptance Criteria

1. O Integrator DEVE continuar a usar partial batch response reporting (batchItemFailures) para o event source mapping do SQS.
2. O Integrator DEVE continuar a verificar idempotência antes de processar cada mensagem usando o Idempotency Repository.
3. QUANDO uma mensagem exceder a contagem máxima de retry de 3 configurada na redrive policy do SQS, A fila SQS DEVE entregar a mensagem à DLQ.
4. O Integrator DEVE continuar a usar o mecanismo de idempotência baseado em lease do DynamoDB com estados PROCESSING, COMPLETED e FAILED_FINAL e duração de lease de 90 segundos.
5. O Integrator DEVE preservar a lógica de renovação de token existente (descriptografar ConnectionToken, enviar mensagem, renovar se erro TOKEN_EXPIRED, retentar uma vez).
6. SE uma tentativa de aquisição de idempotência falhar por erro transitório do DynamoDB, ENTÃO O Integrator DEVE marcar o item SQS como batch item failure para retry.

### Requirement 8: Módulo de Abstração BedrockClient

**User Story:** Como desenvolvedor, quero a integração com Bedrock encapsulada em um módulo dedicado, para que o Integrator permaneça desacoplado do provedor de IA específico.

#### Acceptance Criteria

1. O módulo BedrockClient DEVE residir em `src/shared/bedrock_client/` e expor sua interface pública através de `__init__.py`.
2. O BedrockClient DEVE criar o cliente boto3 bedrock-runtime internamente usando a região AWS lida da variável de ambiente `AWS_REGION` (padrão `us-east-1`) e o model ID lido da variável de ambiente `BEDROCK_MODEL_ID`.
3. O BedrockClient DEVE expor um método que aceita uma string de mensagem do usuário (1 a 4096 caracteres) e retorna o texto da resposta do modelo extraído da resposta da Converse API.
4. O BedrockClient DEVE registrar em log a latência da chamada à Converse API em milissegundos sem registrar o conteúdo da mensagem.
5. O BedrockClient NÃO DEVE registrar em log a mensagem completa do usuário ou a resposta completa do modelo no nível INFO ou inferior.
6. SE a chamada à Converse API falhar ou atingir timeout, ENTÃO O BedrockClient DEVE registrar em log o código de erro, mensagem de erro e latência em milissegundos, e lançar uma exceção específica do módulo contendo os detalhes do erro.
7. O BedrockClient DEVE aplicar um timeout por chamada configurável via variável de ambiente `BEDROCK_TIMEOUT_SECONDS` (padrão 20 segundos) ao invocar a Converse API. O timeout configurado DEVE ser sempre pelo menos 5 segundos menor que o timeout da Lambda Integrator.

### Requirement 9: Infraestrutura Terraform Independente para a POC Bedrock

**User Story:** Como operador de infraestrutura, quero que a POC Bedrock use estado do Terraform independente e nomes de recursos distintos, para que a POC MCP original nunca seja afetada por alterações neste projeto.

#### Acceptance Criteria

1. A configuração Terraform da POC Bedrock DEVE usar um estado do Terraform independente e NÃO DEVE referenciar, importar, modificar ou destruir recursos gerenciados pelo estado da POC MCP original.
2. A POC Bedrock DEVE usar um prefixo de nome de recurso distinto, como `connect-bedrock-poc`, em vez do prefixo original `connect-mcp-poc`.
3. A POC Bedrock DEVE provisionar um fluxo de contato do Amazon Connect separado ou uma cópia explicitamente duplicada, e NÃO DEVE modificar o fluxo de contato ativo da POC MCP.
4. A configuração Terraform da POC Bedrock NÃO DEVE provisionar um novo MCP Server Lambda, Lambda Function URL, IAM role do MCP Server ou recursos de monitoramento específicos do MCP.
5. O Integrator da POC Bedrock NÃO DEVE conter MCP_SERVER_URL ou permissões de invocação MCP.
6. Remover recursos MCP da configuração do repositório Bedrock DEVE significar excluí-los da nova infraestrutura independente, não destruir recursos pertencentes à POC MCP original.
7. A configuração Terraform DEVE adicionar as variáveis de ambiente BEDROCK_MODEL_ID, BEDROCK_MAX_TOKENS, BEDROCK_TEMPERATURE e BEDROCK_SYSTEM_PROMPT à Lambda Integrator, referenciando as variáveis Terraform correspondentes.
8. A configuração Terraform DEVE restringir `bedrock:InvokeModel` ao ARN do foundation model ou inference profile configurado sempre que a AWS suportar escopo em nível de recurso para aquele modo de invocação. Acesso wildcard DEVE ser usado apenas quando tecnicamente necessário e DEVE ser documentado.
9. A configuração Terraform DEVE adicionar uma variável `bedrock_model_id` do tipo string com valor padrão definido como um identificador de modelo Bedrock válido.
10. A configuração Terraform DEVE provisionar seus próprios SNS topic, fila SQS, DLQ, chave KMS, tabelas DynamoDB, Initializer Lambda e log groups do CloudWatch com o prefixo específico da POC Bedrock.
11. ANTES de executar `terraform plan`, O processo de deploy DEVE verificar: nenhum `terraform.tfstate` copiado do projeto MCP está presente; nenhuma chave de backend remoto aponta para o estado da POC MCP; o workspace Terraform selecionado é dedicado à POC Bedrock; os nomes de recursos usam o prefixo específico da POC Bedrock; o plan não contém operação de destroy ou replace afetando recursos MCP.

### Requirement 10: Seleção e Configuração do Modelo

**User Story:** Como operador do sistema, quero que o modelo Bedrock seja configurável e documentado, para que eu possa trocar de modelo sem alterações de código e entender os trade-offs de custo-desempenho.

#### Acceptance Criteria

1. A configuração Terraform DEVE definir uma variável `bedrock_model_id` do tipo string com valor padrão definido como um model ID da classe Amazon Nova ou Claude Haiku disponível em us-east-1 que suporte a Converse API e geração em português.
2. A configuração Terraform DEVE passar o valor da variável `bedrock_model_id` para a Lambda Integrator como variável de ambiente BEDROCK_MODEL_ID.
3. A documentação DEVE registrar: o modelo selecionado e a região; a data em que o preço foi verificado; a fonte oficial de precificação; a latência medida no smoke test real; e as condições do teste e número de amostras. A documentação NÃO DEVE apresentar um valor de latência não medido como resultado observado.
4. QUANDO a variável de ambiente BEDROCK_MODEL_ID for alterada para um model ID válido diferente da Converse API, O BedrockClient DEVE usar o novo modelo sem necessidade de alterações de código.
5. SE a variável de ambiente BEDROCK_MODEL_ID estiver vazia ou não definida na inicialização, ENTÃO O BedrockClient DEVE lançar um erro de configuração com mensagem indicando o nome da variável faltante, impedindo a Lambda de processar requisições.

### Requirement 11: Restrições de Segurança e Logging

**User Story:** Como auditor de segurança, quero dados sensíveis excluídos dos logs e permissões IAM com escopo de menor privilégio, para que o sistema atenda as melhores práticas de segurança.

#### Acceptance Criteria

1. O BedrockClient NÃO DEVE registrar em log headers de autorização, credenciais AWS, connection tokens ou participant tokens em nenhum nível de log.
2. O BedrockClient NÃO DEVE registrar em log o conteúdo completo de mensagens do usuário ou respostas do modelo no nível INFO ou inferior; no nível DEBUG, conteúdo de mensagens PODE ser registrado truncado para um máximo de 100 caracteres.
3. A configuração Terraform DEVE restringir `bedrock:InvokeModel` ao ARN do foundation model ou inference profile configurado sempre que a AWS suportar escopo em nível de recurso para aquele modo de invocação. Acesso wildcard DEVE ser usado apenas quando tecnicamente necessário e DEVE ser documentado como limitação conhecida.
4. O Integrator DEVE preservar a criptografia KMS existente para tokens armazenados no DynamoDB, criptografando ParticipantToken e ConnectionToken via chave KMS antes da escrita e descriptografando após a leitura.
5. O Integrator NÃO DEVE passar connection tokens, participant tokens ou conteúdo de mensagens como valores em nenhuma entrada de log em nenhum nível; metadados como contact_id, message_id e content_length PODEM ser registrados.

### Requirement 12: Testes Unitários e de Integração

**User Story:** Como desenvolvedor, quero cobertura de testes abrangente para o BedrockClient e a integração com o Integrator, para que eu possa fazer deploy das alterações com confiança.

#### Acceptance Criteria

1. QUANDO uma resposta da Converse API contiver um único bloco de texto em `output.message.content[0].text`, O teste unitário DEVE verificar que o BedrockClient retorna exatamente essa string de texto sem modificação.
2. QUANDO uma resposta da Converse API contiver múltiplos blocos de conteúdo de texto, O teste unitário DEVE verificar que o BedrockClient retorna todos os blocos de texto unidos por um único caractere de nova linha ("\n") em ordem.
3. QUANDO uma resposta da Converse API contiver um array de content vazio, O teste unitário DEVE verificar que o BedrockClient retorna a mensagem de fallback predefinida em português indicando que o modelo não conseguiu gerar uma resposta.
4. QUANDO o cliente boto3 bedrock-runtime lançar ThrottlingException durante uma chamada à Converse API, O teste unitário DEVE verificar que o BedrockClient lança uma exceção classificada como erro transitório (ErrorCategory.TRANSIENT).
5. QUANDO o cliente boto3 bedrock-runtime lançar AccessDeniedException durante uma chamada à Converse API, O teste unitário DEVE verificar que o BedrockClient lança uma exceção classificada como erro fatal (ErrorCategory.FATAL).
6. QUANDO o cliente boto3 bedrock-runtime lançar ReadTimeoutError ou a duração da chamada exceder o timeout configurado, O teste unitário DEVE verificar que o BedrockClient lança uma exceção classificada como erro transitório (ErrorCategory.TRANSIENT).
7. QUANDO o Integrator receber um registro SQS contendo um evento MESSAGE com ParticipantRole "CUSTOMER", O teste de integração DEVE verificar que ele invoca o BedrockClient com o conteúdo da mensagem e envia o texto retornado via Participant Service SendMessage, usando um BedrockClient mockado.
8. QUANDO o Integrator receber um registro SQS contendo um evento MESSAGEMETADATA, O teste de integração DEVE verificar que nenhuma chamada é feita ao BedrockClient e o registro não é reportado em batchItemFailures.
9. QUANDO uma mensagem é processada ponta a ponta no teste de integração, O teste DEVE capturar a saída de log estruturado e verificar que toda entrada de log emitida entre recepção da mensagem e conclusão contém o mesmo valor do campo correlation_id.
10. QUANDO a Converse API retornar uma resposta com pelo menos um bloco de conteúdo de texto não vazio, O teste unitário DEVE verificar que o método de extração do BedrockClient retorna uma string não vazia com comprimento de pelo menos 1 caractere.

### Requirement 13: Script de Smoke Test

**User Story:** Como desenvolvedor, quero um script de smoke test que valide o BedrockClient contra um endpoint Bedrock real, para que eu possa verificar conectividade e acesso ao modelo antes do deploy completo.

#### Acceptance Criteria

1. O script de smoke test DEVE estar localizado em `scripts/smoke_test_bedrock.ps1`.
2. QUANDO executado, O smoke test DEVE chamar `aws sts get-caller-identity` e SE a chamada falhar, ENTÃO O smoke test DEVE encerrar com código de saída diferente de zero e imprimir uma mensagem de erro indicando que as credenciais AWS não estão configuradas.
3. QUANDO executado, O smoke test DEVE imprimir o account ID da AWS, ARN e região retornados pela chamada STS caller identity.
4. QUANDO executado, O smoke test DEVE ler o BEDROCK_MODEL_ID da variável de ambiente e SE a variável não estiver definida, ENTÃO O smoke test DEVE usar o mesmo valor padrão definido na variável Terraform `bedrock_model_id`.
5. QUANDO executado, O smoke test DEVE instanciar a mesma classe BedrockClient usada pelo Integrator, passando o model ID resolvido e a configuração de inferência padrão.
6. QUANDO executado, O smoke test DEVE enviar uma pergunta de teste de no máximo 50 caracteres em português ao BedrockClient e aguardar no máximo o BEDROCK_TIMEOUT_SECONDS configurado (padrão 20 segundos) por uma resposta.
7. QUANDO o BedrockClient retornar uma resposta não vazia, O smoke test DEVE imprimir o texto da resposta, a latência da chamada em milissegundos e o ID de correlação, e então encerrar com código de saída 0.
8. SE o BedrockClient retornar uma resposta vazia ou lançar um erro, ENTÃO O smoke test DEVE encerrar com código de saída 1 e imprimir o tipo de erro e a mensagem de erro no console.

### Requirement 14: Documentação

**User Story:** Como desenvolvedor ou operador, quero documentação completa cobrindo arquitetura, deploy, testes, troubleshooting e migração, para que a POC seja compreensível e reproduzível.

#### Acceptance Criteria

1. O projeto DEVE incluir um `README.md` atualizado que descreva a arquitetura Bedrock Converse, liste pré-requisitos, mostre a estrutura do repositório e forneça instruções de quickstart para execução local e testes.
2. O projeto DEVE incluir `docs/architecture.md` com um diagrama Mermaid mostrando o fluxo: Usuário → Connect → SNS → SQS → Integrator → BedrockClient → Converse API → Participant Service → Usuário, acompanhado de descrição da responsabilidade de cada componente.
3. O projeto DEVE incluir `docs/deployment-guide.md` com uma seção de pré-requisitos (ferramentas necessárias, permissões AWS, variáveis de ambiente) seguida de passos numerados cobrindo provisionamento de infraestrutura, empacotamento de Lambda, deploy e verificação pós-deploy.
4. O projeto DEVE incluir `docs/testing-strategy.md` descrevendo testes unitários, testes de integração e o smoke test, incluindo os comandos para executar cada categoria e o limiar mínimo de cobertura.
5. O projeto DEVE incluir `docs/troubleshooting.md` cobrindo no mínimo estes cenários de erro: AccessDeniedException, throttling do Bedrock (ThrottlingException), modelo não encontrado (ModelNotFoundException) e expiração de token, com sintomas, causas prováveis e ações corretivas para cada um.
6. O projeto DEVE incluir `docs/security.md` documentando permissões IAM por role de Lambda, uso de chave KMS para criptografia de tokens e regras de sanitização de log que previnem dados sensíveis de aparecerem nos logs do CloudWatch.
7. O projeto DEVE incluir `docs/bedrock-converse-flow.md` documentando a estrutura da requisição da Converse API (model ID, formato de mensagem, configuração de system prompt), a lógica de parsing da resposta e parâmetros de configuração (max tokens, temperature).
8. O projeto DEVE incluir `docs/migration-from-mcp.md` documentando componentes removidos (MCP server, MCP client, Function URL, SigV4 signing), componentes adicionados (BedrockClient, integração Converse API) e componentes alterados (processador do Integrator, IAM roles).
9. O projeto DEVE incluir `docs/cost-considerations.md` com custos estimados da Bedrock Converse API baseados em premissas declaradas para contagem de tokens de entrada/saída por mensagem e um número definido de conversas mensais.
10. O projeto DEVE incluir `docs/known-limitations.md` listando limitações da POC organizadas por categoria (infraestrutura, funcionalidade, segurança, escalabilidade) com breve descrição de cada limitação e sua potencial resolução em produção.

### Requirement 15: Isolamento da POC MCP Original

**User Story:** Como operador do sistema, quero a POC Bedrock completamente isolada da POC MCP original, para que nenhuma ação neste projeto possa quebrar a integração MCP funcionando.

#### Acceptance Criteria

1. A POC Bedrock DEVE usar um estado do Terraform separado e independente do estado da POC MCP.
2. A POC Bedrock DEVE usar nomes distintos de Lambda, fila, tópico, tabela, log group, IAM role e alarme que não colidam com os nomes de recursos da POC MCP.
3. A POC Bedrock DEVE usar um fluxo de contato separado ou uma cópia controlada do fluxo existente, e NÃO DEVE modificar o fluxo de contato ativo da POC MCP.
4. A implementação NÃO DEVE alterar o repositório MCP original ou qualquer recurso gerenciado por ele.
5. A implementação NÃO DEVE executar `terraform apply`, `git commit` ou `git push` sem autorização explícita do operador.
6. QUALQUER `terraform plan` contendo destruição ou substituição de um recurso cujo nome comece com o prefixo do projeto MCP DEVE falhar nos critérios de revisão e NÃO DEVE ser aplicado.
