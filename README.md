# LOA — Pesquisa com evidências

Aplicação interna para pesquisa rastreável nas Leis Orçamentárias Anuais da União.

## Princípio editorial

Nenhuma resposta pode ser apresentada sem evidência documental. O resumo da aplicação
é sempre separado do texto original, e toda evidência informa documento, exercício e
página física do PDF.

## Estrutura

- `apps/api`: API FastAPI, modelo de dados, indexação e busca.
- `apps/web`: interface Next.js.
- `tests`: regras editoriais e testes do pipeline.
- `../dados`: PDFs originais, tratados como somente leitura.
- `../docs`: requisitos obrigatórios.

## Execução local

1. Copie `.env.example` para `.env`.
2. Crie o ambiente Python e instale `.[dev]`.
3. Inicie o PostgreSQL com `docker compose up -d db`, ou mantenha o SQLite padrão para desenvolvimento.
4. Execute a indexação com `python -m loa_api.cli`.
5. Inicie a API com `uvicorn loa_api.main:app --app-dir apps/api --reload`.
6. Em `apps/web`, instale as dependências e execute `pnpm dev`.

Em produção, execute as migrações com `alembic upgrade head` e configure
`AUTH_REQUIRED=true`. O acesso editorial pode ser restringido pela lista
`EDITOR_EMAILS`. A aplicação confia somente nos cabeçalhos autenticados encaminhados
pela plataforma; ela não mantém senhas próprias.

Para catalogar rapidamente os documentos sem extrair todas as páginas, use
`python -m loa_api.cli --catalog-only`.

## Estado do acervo

- 88 documentos catalogados.
- 19.116 páginas indexadas.
- 39.905 fragmentos contextualizados.
- Páginas sem texto nativo permanecem marcadas para OCR/revisão e nunca recebem
  conteúdo inventado.

## Salvaguardas implementadas

- Bloqueio de respostas sobre execução, pagamentos, empenhos e liquidações.
- Números de quatro dígitos permanecem ambíguos sem contexto explícito de exercício.
- Fragmentos guardam documento, ano, página PDF, página impressa quando identificada
  e texto original.
- Comparações só são liberadas quando há registros estruturados para todos os anos e
  as unidades são compatíveis.
- Consultas permanentes preservam a resposta e as evidências da ocasião.
- Exportações em PDF reproduzem as evidências e a nota editorial.
- Ações de exportação e criação de consultas permanentes são registradas em auditoria.
- O painel mostra quantas páginas ainda aguardam homologação.
- Respostas incluem identificador de requisição e cabeçalhos contra cache,
  enquadramento e interpretação indevida de conteúdo.

## Piloto interno

Antes do piloto, configure PostgreSQL, execute `alembic upgrade head`, restrinja
`EDITOR_EMAILS` e mantenha os PDFs em armazenamento somente leitura. Faça backup
diário do banco e retenha os arquivos originais pelo hash SHA-256. Enquanto
`homologation_complete` for falso, o painel exibe o aviso e páginas pendentes não
podem sustentar respostas editoriais.
