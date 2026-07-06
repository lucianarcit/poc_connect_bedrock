# Requirements Document

## Introduction

Esta POC demonstra a integração entre Amazon Connect (chat) e Amazon Bedrock Knowledge Bases para responder perguntas de atendimento ao cliente utilizando RAG (Retrieval-Augmented Generation). O sistema recupera informações de documentos armazenados em S3, gera respostas fundamentadas com citações de fontes, e recusa respostas quando não há evidência suficiente nos documentos. O objetivo é validar o fluxo completo de RAG com geração fundamentada em um ambiente isolado.

## Glossary

- **Sistema_RAG**: Conjunto completo de componentes da POC que implementa o fluxo RAG, incluindo Lambdas, filas, tópicos, tabelas DynamoDB, Knowledge Base e bucket S3
- **Lambda_Initializer_RAG**: Função Lambda invocada pelo Contact Flow que inicializa o bot CUSTOM_BOT, configura streaming e persiste sessão
- **Lambda_Integrator_RAG**: Função Lambda que processa mensagens do chat via SQS, consulta a Knowledge Base e envia respostas ao widget
- **Knowledge_Base**: Recurso Amazon Bedrock Knowledge Bases que indexa documentos do S3 e fornece retrieval semântico com geração de respostas
- **KnowledgeBase_Client**: Módulo Python que encapsula chamadas à API RetrieveAndGenerate do Bedrock Agent Runtime
- **Participant_Service**: Módulo que envia mensagens de volta ao chat do Amazon Connect via Participant API
- **Contact_Flow_RAG**: Fluxo de contato no Amazon Connect configurado para o chat RAG
- **Bucket_Documentos**: Bucket S3 que armazena os documentos-fonte para indexação pela Knowledge Base
- **Vector_Store**: Armazenamento vetorial utilizado pela Knowledge Base para busca semântica (implementação a ser validada)
- **Citação**: Referência à fonte do documento utilizada para fundamentar a resposta, incluindo nome do documento e localização
- **Chunk**: Fragmento de documento recuperado pela Knowledge Base durante a busca semântica
- **Resposta_Fundamentada**: Resposta gerada pelo modelo que inclui citações das fontes consultadas
- **Resposta_Sem_Evidência**: Mensagem padrão informando que a informação não foi encontrada nos documentos disponíveis
- **Idempotência**: Garantia de que uma mensagem duplicada não gera resposta duplicada ao usuário
- **DLQ_RAG**: Dead-Letter Queue que recebe mensagens que falharam após máximo de retentativas
- **SNS_RAG**: Tópico SNS Standard que recebe eventos de streaming do Amazon Connect
- **SQS_RAG**: Fila SQS Standard que recebe mensagens do SNS_RAG e dispara a Lambda_Integrator_RAG
- **Prefixo_Recursos**: `connect-bedrock-rag-poc` — prefixo para todos os recursos AWS desta POC

## Requirements

### Requisito 1: Inicialização do Bot RAG no Contact Flow

**User Story:** Como usuário do chat, eu quero que o bot RAG seja inicializado automaticamente ao iniciar uma conversa, para que minhas perguntas sejam respondidas com base em documentos.

#### Critérios de Aceitação

1. WHEN o Contact_Flow_RAG invoca a Lambda_Initializer_RAG com evento contendo ContactId, InstanceId e Channel=CHAT, THE Lambda_Initializer_RAG SHALL executar StartContactStreaming, CreateParticipant e CreateParticipantConnection em sequência e retornar um STRING_MAP com campos "status" = "SUCCESS" e "botInitialized" = "true" ao Contact Flow em até 8 segundos
2. WHEN a Lambda_Initializer_RAG completa a inicialização com sucesso, THE Lambda_Initializer_RAG SHALL persistir a sessão no DynamoDB com os campos contact_id, participant_id, streaming_id, tokens (ParticipantToken e ConnectionToken) criptografados via KMS, connection_token_expiry, status=ACTIVE e expires_at com TTL de 24 horas
3. IF a Lambda_Initializer_RAG falha em qualquer etapa da inicialização, THEN THE Lambda_Initializer_RAG SHALL retornar um STRING_MAP com "status" = "ERROR", "botInitialized" = "false" e "errorCode" contendo um dos valores enumerados (INVALID_EVENT, INITIALIZATION_FAILED, INITIALIZATION_IN_PROGRESS_TIMEOUT) ao Contact Flow, sem incluir stack traces, mensagens de exceção internas ou ARNs de recursos na resposta
4. THE Lambda_Initializer_RAG SHALL utilizar recursos completamente isolados (SNS_RAG, tabelas DynamoDB exclusivas, chave KMS dedicada) identificáveis por prefixo ou tag específica do projeto RAG, sem compartilhar estado com outras POCs
5. IF a Lambda_Initializer_RAG recebe uma invocação para um ContactId que já possui sessão com status ACTIVE no DynamoDB, THEN THE Lambda_Initializer_RAG SHALL retornar "status" = "SUCCESS" e "botInitialized" = "true" sem executar novamente as chamadas às APIs do Connect
6. IF o evento recebido pela Lambda_Initializer_RAG não contém ContactId, InstanceARN ou possui Channel diferente de CHAT, THEN THE Lambda_Initializer_RAG SHALL retornar "status" = "ERROR" com "errorCode" = "INVALID_EVENT" sem executar chamadas às APIs do Connect

### Requisito 2: Processamento de Mensagens via Fila

**User Story:** Como operador do sistema, eu quero que mensagens do chat sejam processadas de forma assíncrona e resiliente via SNS/SQS, para que o sistema tolere falhas transitórias sem perda de mensagens.

#### Critérios de Aceitação

1. WHEN o Amazon Connect publica um evento de mensagem no SNS_RAG, THE SQS_RAG SHALL receber a mensagem via subscription SNS→SQS e disparar a Lambda_Integrator_RAG com batch size máximo de 5 registros e visibility timeout de 360 segundos
2. WHEN a Lambda_Integrator_RAG recebe um batch de registros SQS, THE Lambda_Integrator_RAG SHALL processar cada registro individualmente e retornar o resultado no formato partial batch response contendo apenas os itemIdentifier dos registros que falharam, permitindo que registros bem-sucedidos sejam removidos da fila independentemente
3. WHEN a Lambda_Integrator_RAG recebe um evento com ParticipantRole diferente de CUSTOMER ou Type diferente de MESSAGE, THE Lambda_Integrator_RAG SHALL considerar o evento como processado com sucesso (sem adicioná-lo à lista de falhas) e não executar processamento adicional
4. IF uma mensagem falha 3 vezes consecutivas (maxReceiveCount atingido), THEN THE SQS_RAG SHALL mover a mensagem para a DLQ_RAG onde será retida por 14 dias sem alteração do payload original
5. WHEN a Lambda_Integrator_RAG recebe uma mensagem válida do cliente, THE Lambda_Integrator_RAG SHALL verificar idempotência via DynamoDB usando o message_id do evento Connect como chave, adquirindo um lease de 90 segundos no estado PROCESSING; mensagens com status COMPLETED ou FAILED_FINAL SHALL ser ignoradas sem reprocessamento e registros de idempotência SHALL expirar após 24 horas via TTL
6. IF o DynamoDB retorna erro transitório (throttling, service unavailable) durante a verificação de idempotência, THEN THE Lambda_Integrator_RAG SHALL reportar o registro como falha no partial batch response para que o SQS realize retry automático

### Requisito 3: Consulta à Knowledge Base com RAG

**User Story:** Como usuário do chat, eu quero que minhas perguntas sejam respondidas com informações recuperadas de documentos reais, para que as respostas sejam precisas e confiáveis.

#### Critérios de Aceitação

1. WHEN a Lambda_Integrator_RAG recebe uma mensagem com ParticipantRole=CUSTOMER e Type=MESSAGE contendo texto não vazio, THE KnowledgeBase_Client SHALL chamar a API RetrieveAndGenerate do Bedrock Agent Runtime com a pergunta do usuário e o knowledgeBaseId obtido da variável de ambiente KNOWLEDGE_BASE_ID
2. WHEN a API RetrieveAndGenerate retorna uma resposta com citações, THE KnowledgeBase_Client SHALL extrair o texto gerado do campo output.text e a lista de citações do campo citations, incluindo para cada citação o URI do documento-fonte e o trecho referenciado
3. WHEN a API RetrieveAndGenerate retorna citações duplicadas (mesmo document URI e mesmo text span), THE KnowledgeBase_Client SHALL remover duplicatas antes de formatar a resposta, mantendo apenas a primeira ocorrência
4. THE KnowledgeBase_Client SHALL utilizar o modelo de geração definido pela variável de ambiente BEDROCK_MODEL_ARN; o valor inicial pretendido é o ARN do modelo amazon.nova-micro-v1:0, condicionado à validação de compatibilidade com a API RetrieveAndGenerate na região e conta utilizadas
5. THE KnowledgeBase_Client SHALL configurar timeout de chamada com valor padrão de 30 segundos, configurável via variável de ambiente BEDROCK_TIMEOUT_SECONDS no intervalo [5, 120] segundos
6. IF o tempo restante da Lambda (context.get_remaining_time_in_millis()) é inferior a (BEDROCK_TIMEOUT_SECONDS × 1000 + 5000) milissegundos, THEN THE KnowledgeBase_Client SHALL abortar sem realizar a chamada à API e a Lambda_Integrator_RAG SHALL marcar o item SQS como falha para retry em nova invocação

### Requisito 4: Respostas Fundamentadas com Citações

**User Story:** Como usuário do chat, eu quero que as respostas incluam referências aos documentos consultados, para que eu possa verificar a origem da informação.

#### Critérios de Aceitação

1. WHEN a Knowledge_Base retorna texto gerado acompanhado de pelo menos uma citação contendo nome do documento e identificador de localização (seção, página ou trecho), THE Lambda_Integrator_RAG SHALL formatar a resposta concatenando o texto gerado seguido de "Fonte: [nome do documento], [identificador de localização]." para cada citação, separando múltiplas fontes por ponto-e-vírgula
2. WHEN a Knowledge_Base retorna citações de 2 ou mais documentos diferentes, THE Lambda_Integrator_RAG SHALL listar todas as fontes distintas na resposta, até um máximo de 5 fontes, ordenadas pela relevância retornada pela Knowledge_Base
3. WHEN a resposta formatada (texto + citações) excede 15.000 bytes UTF-8, THE Lambda_Integrator_RAG SHALL truncar o texto da resposta preservando ao menos a primeira citação de fonte e adicionando reticências ("...") no ponto de corte do texto
4. IF a Knowledge_Base retorna texto gerado mas nenhuma citação associada, THEN THE Lambda_Integrator_RAG SHALL descartar o texto gerado e enviar exclusivamente a mensagem padrão: "Não encontrei essa informação nos documentos disponíveis."
5. THE Lambda_Integrator_RAG SHALL formatar respostas com no máximo 1.000 caracteres de texto gerado (excluindo o bloco de fontes) antes de aplicar truncamento, garantindo que a resposta total (texto + fontes) não exceda 15.000 bytes UTF-8

### Requisito 5: Tratamento de Ausência de Evidência

**User Story:** Como usuário do chat, eu quero receber uma mensagem clara quando o sistema não encontra informação relevante, para que eu saiba que a resposta não está disponível nos documentos.

#### Critérios de Aceitação

1. WHEN a Knowledge_Base retorna resposta sem citações ou com campo citations vazio, THE Lambda_Integrator_RAG SHALL responder com a mensagem padrão: "Não encontrei essa informação nos documentos disponíveis."
2. WHEN a Knowledge_Base retorna resposta vazia (output.text vazio ou nulo), THE Lambda_Integrator_RAG SHALL responder com a mensagem padrão sem inventar fontes ou informações
3. IF a Knowledge_Base retorna citações mas o texto gerado indica explicitamente ausência de informação (contendo frases como "não encontrei", "não há informação" ou "não tenho dados"), THEN THE Lambda_Integrator_RAG SHALL responder com a mensagem padrão de ausência de evidência
4. THE Lambda_Integrator_RAG SHALL emitir métrica estruturada "NoEvidenceResponseCount" com valor 1 para cada resposta sem evidência, permitindo monitoramento da cobertura dos documentos via CloudWatch Metric Filter

### Requisito 6: Tratamento de Erros e Resiliência

**User Story:** Como operador do sistema, eu quero que erros na consulta RAG sejam tratados adequadamente, para que o usuário receba feedback e o sistema mantenha estabilidade.

#### Critérios de Aceitação

1. IF a API RetrieveAndGenerate retorna ThrottlingException, ServiceUnavailableException, ModelTimeoutException ou InternalServerException, THEN THE Lambda_Integrator_RAG SHALL marcar o item SQS como falha para retry automático, até o máximo de 3 tentativas (maxReceiveCount) antes de encaminhar à DLQ
2. IF a API RetrieveAndGenerate retorna uma exceção classificada como erro fatal pelo cliente boto3 do bedrock-agent-runtime (incluindo mas não limitado a AccessDeniedException e ValidationException), THEN THE Lambda_Integrator_RAG SHALL enviar mensagem de erro ao usuário indicando impossibilidade de processar a solicitação e marcar a mensagem como FAILED_FINAL sem retry; o mapeamento exato de exceções SHALL ser baseado nas classes expostas pelo SDK na versão utilizada
3. IF o tempo restante da Lambda é inferior a (BEDROCK_TIMEOUT_SECONDS × 1000 + 5000) milissegundos, THEN THE Lambda_Integrator_RAG SHALL marcar o item SQS como falha para retry em nova invocação sem realizar a chamada à API Bedrock
4. IF o ConnectionToken retorna erro ExpiredTokenException durante o envio da resposta, THEN THE Lambda_Integrator_RAG SHALL renovar o token via CreateParticipantConnection usando o ParticipantToken armazenado e retentar o envio da resposta exatamente uma vez
5. THE Lambda_Integrator_RAG SHALL registrar todos os erros em formato JSON estruturado contendo os campos correlation_id, error_code e error_category como campos de primeiro nível, sem incluir conteúdo de mensagens do usuário ou respostas do modelo nos logs em nenhum nível de severidade

### Requisito 7: Armazenamento e Indexação de Documentos

**User Story:** Como operador do sistema, eu quero armazenar documentos de teste no S3 e indexá-los na Knowledge Base, para que o RAG tenha uma base de conhecimento controlada para validação.

#### Critérios de Aceitação

1. THE Bucket_Documentos SHALL armazenar documentos de teste em formato texto (.txt) ou PDF (.pdf), com tamanho máximo de 10 MB por documento e no máximo 50 documentos no total, acompanhados de metadados estruturados que incluam ao menos: identificador do documento, título, idioma e data de atualização
2. THE Knowledge_Base SHALL indexar os documentos do Bucket_Documentos utilizando um modelo de embeddings compatível com Amazon Bedrock; WHEN um job de ingestão concluir com status COMPLETE, THE Knowledge_Base SHALL tornar os documentos válidos disponíveis para recuperação semântica, e cada consulta individual SHALL retornar ou falhar explicitamente dentro do timeout configurado para a operação
3. WHEN um novo documento é adicionado ao Bucket_Documentos, THE Knowledge_Base SHALL permitir sincronização manual (start ingestion job) para reindexar o conteúdo, e o job de ingestão SHALL concluir com status de sucesso sem erros de parsing para todos os documentos válidos
4. THE Sistema_RAG SHALL validar extensão (.txt ou .pdf) e tamanho (máximo 10 MB) de cada documento antes de enviá-lo ao prefixo indexado do Bucket_Documentos; IF um documento falhar na validação, THEN THE Sistema_RAG SHALL registrar o motivo da rejeição em relatório estruturado e não incluí-lo no prefixo indexado
5. THE Bucket_Documentos SHALL aplicar criptografia server-side (SSE-S3 ou SSE-KMS) em todos os objetos armazenados, de modo que nenhum objeto persista em estado não criptografado
6. THE Sistema_RAG SHALL incluir ao menos 3 documentos de teste com conteúdo controlado e respostas esperadas conhecidas, cobrindo ao menos 2 temas distintos, para validação determinística das respostas RAG

### Requisito 8: Infraestrutura Isolada via Terraform

**User Story:** Como desenvolvedor, eu quero que toda a infraestrutura RAG seja provisionada via Terraform de forma completamente isolada, para que não haja conflito com outras POCs.

#### Critérios de Aceitação

1. THE Sistema_RAG SHALL utilizar o prefixo `connect-bedrock-rag-poc` combinado com o sufixo de ambiente (ex: `connect-bedrock-rag-poc-dev`) em todos os nomes de recursos AWS, de modo que nenhum nome de recurso colida com recursos da POC existente (`connect-bedrock-poc`)
2. THE Sistema_RAG SHALL utilizar estado Terraform em diretório próprio (`terraform-rag/` ou equivalente) com arquivo de state independente, sem referenciar ou compartilhar state files com o diretório `terraform/` da POC existente
3. THE Sistema_RAG SHALL criar recursos próprios e exclusivos para: Lambda_Initializer_RAG, Lambda_Integrator_RAG, SNS_RAG, SQS_RAG, DLQ_RAG, tabelas DynamoDB, Bucket_Documentos, Knowledge_Base, IAM roles, KMS key e log groups, cada um identificável pelo prefixo `connect-bedrock-rag-poc` e com tag `Project` que distinga esta POC da anterior
4. THE Sistema_RAG SHALL referenciar a instância Amazon Connect existente exclusivamente via data source ou variável de entrada (instance_id/instance_arn), sem declarar recurso `aws_connect_instance` no código Terraform
5. THE Sistema_RAG SHALL evitar wildcards em IAM Actions e restringir Resources aos ARNs específicos sempre que a ação suportar resource-level permissions; WHEN uma ação AWS exigir "Resource": "*", THE exceção SHALL ser documentada inline no código Terraform e restringida por condições IAM (Condition) sempre que possível, e permissions boundary SHALL ser aplicada em todas as IAM roles criadas
6. IF a execução de `terraform plan` para o Sistema_RAG reportar recursos pertencentes a outra POC no changeset, THEN THE Sistema_RAG SHALL falhar a validação, confirmando que o state não referencia recursos externos ao escopo RAG

### Requisito 9: Segurança e Proteção de Dados

**User Story:** Como operador do sistema, eu quero que tokens e dados sensíveis sejam protegidos, para que a POC siga práticas seguras mesmo em ambiente de validação.

#### Critérios de Aceitação

1. THE Lambda_Initializer_RAG SHALL criptografar ParticipantToken e ConnectionToken com KMS antes de persistir a sessão no DynamoDB, armazenando exclusivamente o CiphertextBlob opaco nos respectivos atributos; THE Lambda_Integrator_RAG SHALL descriptografar os tokens via KMS somente quando necessitar utilizá-los para enviar mensagens ao chat
2. THE Lambda_Integrator_RAG SHALL registrar logs estruturados em formato JSON sem incluir conteúdo de mensagens do usuário, respostas do modelo, tokens, credenciais ou chaves em nenhum nível de log, inclusive em campos de exceção ou stack traces
3. THE Sistema_RAG SHALL configurar TTL nas tabelas DynamoDB para expirar sessões e registros de idempotência após 24 horas (86400 segundos) a partir da última atualização do registro
4. THE Bucket_Documentos SHALL bloquear acesso público com as quatro configurações de S3 Block Public Access habilitadas: BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy e RestrictPublicBuckets
5. IF credenciais ou tokens são identificados em logs do CloudWatch, THEN THE Sistema_RAG SHALL acionar rotação das credenciais afetadas em até 1 hora após a detecção e registrar o incidente com timestamp de detecção e timestamp de conclusão da rotação

### Requisito 10: Observabilidade e Monitoramento

**User Story:** Como operador do sistema, eu quero ter visibilidade sobre o comportamento do RAG em produção, para identificar problemas rapidamente.

#### Critérios de Aceitação

1. THE Lambda_Integrator_RAG SHALL emitir métricas estruturadas em formato JSON com campos de primeiro nível para: RAGLatencyMs (latência da chamada RetrieveAndGenerate em milissegundos), CitedResponseCount (respostas com citação), NoEvidenceResponseCount (respostas sem evidência) e ErrorCount por error_category
2. THE Sistema_RAG SHALL criar log groups dedicados para Lambda_Initializer_RAG e Lambda_Integrator_RAG com retenção configurável via variável Terraform (padrão 14 dias)
3. THE Sistema_RAG SHALL configurar alarmes CloudWatch para: ApproximateNumberOfMessagesVisible na DLQ_RAG > 0, taxa de Errors da Lambda_Integrator_RAG > 2 em 2 períodos consecutivos de 5 minutos, e Throttles da Lambda_Integrator_RAG > 0
4. THE Lambda_Integrator_RAG SHALL propagar correlation_id (derivado do MessageId do evento Connect) em todos os logs de uma mesma mensagem, permitindo filtro por correlation_id nos CloudWatch Logs Insights

### Requisito 11: Validação e Testes

**User Story:** Como desenvolvedor, eu quero testes automatizados que validem o comportamento do KnowledgeBase_Client, para garantir corretude antes do deploy.

#### Critérios de Aceitação

1. THE KnowledgeBase_Client SHALL ter testes unitários com mocks que validem cada cenário a seguir com pelo menos um caso de teste: extração de citações de resposta válida, remoção de citações duplicadas (mesmo documento e localização), formatação de resposta com texto e fontes, tratamento de resposta sem citações, e tratamento de timeout da API RetrieveAndGenerate
2. THE KnowledgeBase_Client SHALL ter teste de propriedade que, para no mínimo 100 inputs gerados de respostas RAG válidas, valide que: nenhuma citação única desaparece após processamento, duplicatas são eliminadas, a ordem das primeiras ocorrências é preservada, o limite de 5 fontes é respeitado, e o texto final respeita os limites de 1.000 caracteres e 15.000 bytes UTF-8
3. THE Sistema_RAG SHALL manter cobertura de testes mínima de 80% em line coverage no código Python, medida por pytest-cov e aplicada como gate de falha na execução dos testes
4. WHEN o deploy da infraestrutura RAG é concluído com sucesso, THE Sistema_RAG SHALL executar um smoke test que envia uma pergunta de teste à Knowledge Base via API RetrieveAndGenerate e verifica que a resposta é recebida com status de sucesso em até 30 segundos
5. IF o smoke test falha ao receber resposta da Knowledge Base dentro de 30 segundos ou recebe erro da API, THEN THE Sistema_RAG SHALL reportar falha com o código de erro e encerrar o script de validação pós-deploy com código de saída diferente de zero

### Requisito 12: Decisões Pendentes Documentadas

**User Story:** Como desenvolvedor, eu quero que decisões técnicas pendentes estejam documentadas, para que sejam resolvidas de forma informada durante a implementação.

#### Critérios de Aceitação

1. THE Sistema_RAG SHALL documentar a decisão sobre o modelo de embeddings selecionado incluindo: modelo escolhido e alternativas consideradas, dimensão dos vetores gerados, suporte ao idioma português, custo por token estimado e fonte de precificação consultada, e conclusão com a razão da escolha
2. THE Sistema_RAG SHALL documentar a decisão sobre o vector store incluindo: no mínimo 2 alternativas comparadas (ex.: S3 Vectors, OpenSearch Serverless), e para cada alternativa os seguintes critérios avaliados: custo estimado mensal para o volume da POC, latência de consulta esperada, complexidade de provisionamento e limitações conhecidas, finalizando com a alternativa selecionada e a justificativa da escolha
3. THE Sistema_RAG SHALL documentar o schema de metadados dos documentos incluindo: lista de campos de metadados com nome, tipo de dado e se é obrigatório ou opcional para cada campo; e a estratégia de filtragem incluindo: quais campos são usados como filtro nas consultas, operadores de comparação aplicáveis e um exemplo de consulta filtrada
4. THE Sistema_RAG SHALL documentar a decisão entre usar Retrieve (chunks puros) vs RetrieveAndGenerate (geração integrada) incluindo: descrição do comportamento de cada abordagem, vantagens e desvantagens de cada uma para o cenário da POC, impacto na latência de resposta e no controle sobre o prompt, e a abordagem selecionada com a razão da escolha
5. WHEN qualquer decisão documentada nos critérios 1 a 4 for registrada, THE documento SHALL residir no diretório `docs/` do repositório e SHALL conter a data da decisão e o status (pendente, decidido ou revisado)
