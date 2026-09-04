# Auditoria do pacote de publicação

Data: 2026-09-03

Status: **pacote de dados homologados construído e validado; integração à imagem ainda pendente**. O artefato local está em `storage/release/loa-homologada-render.zip`. A imagem Docker continua incorporando o banco antigo, restrito à Educação, até a próxima etapa controlada.

## Pacote homologado construído

- Formato: `consulta-loa-homologated-bundle-v1`.
- Registros publicados: 2.829, todos com `evidence_status=homologated`.
- Registros não classificados excluídos: 514.
- Evidências: 1.602 páginas em 33 volumes oficiais.
- Cobertura: 30 áreas com registros, além de 31 áreas cadastradas no mapa editorial.
- Regras editoriais ativas: 16; segmentos históricos: 48.
- Tamanho do ZIP esparso: 36.597.792 bytes (redução aproximada de 87,6% em relação aos 295.430.836 bytes do primeiro pacote completo).
- SHA-256 do ZIP: `3d78178eb261c7b3176a21821f03ef9c1999e21c1e0ff5178eba88edb48544e8`.
- Manifesto externo: `storage/release/manifest.json`.
- Integridade: ZIP, hashes, SQLite e chaves estrangeiras aprovados. O conteúdo interno das 1.602 páginas retidas foi comparado com os PDFs originais sem divergências.
- PDFs esparsos: cada página citada permanece na posição PDF original; páginas intermediárias não utilizadas são placeholders em branco. A inspeção visual e a renderização comparativa das páginas PDF 327 de `2022_volume4.pdf` e 385 de `2024_volume4.pdf` produziram imagens idênticas às originais.
- Isolamento: tabelas de feedback, consultas salvas, auditoria e ingestão contêm zero linhas no pacote. O PostgreSQL de feedback não foi acessado nem alterado.
- Testes: 65 aprovados; auditoria de resolução com 540 unidades, 2.732 combinações unidade/exercício e zero falhas.

## Arquivos que devem entrar na liberação

### Aplicação e regras executáveis

- `.env.example`
- `apps/api/loa_api/config.py`
- `apps/api/loa_api/main.py`
- `apps/api/loa_api/models.py`
- `apps/api/loa_api/search.py`
- `apps/api/loa_api/editorial_map.py`
- `apps/web/src/app/page.tsx`
- `config/mapa_editorial.yml`
- `migrations/versions/b41c9d8e7a10_add_editorial_map.py`

### Construção, auditoria e testes

- `scripts/build_editorial_map.py`
- `scripts/load_institution_inventory.py`
- `scripts/audit_unit_query_resolution.py`
- `tests/test_vocabulary.py`
- `tests/test_editorial_map.py`
- `tests/test_pilot_scope.py`
- `tests/test_comparison.py`

### Rastreabilidade editorial

- `scripts/inventories/*.json`: 266 inventários, todos com JSON válido. Eles ocupam aproximadamente 227 KiB e podem entrar no repositório como evidência estruturada, mas não precisam ser copiados para a imagem de execução.
- Os checkpoints de `storage/homologation` permanecem fora do Git e da imagem. São 685 arquivos locais de trabalho e devem ser preservados no armazenamento editorial, não publicados junto com a aplicação.

## Arquivos que não devem entrar

- `.env`: contém configuração local e permanece ignorado.
- `.venv/`, `.next/`, `.pytest_cache/`, `.pnpm-store/` e caches equivalentes.
- `tmp/`: 154 arquivos e aproximadamente 419 MiB de PDFs e imagens de inspeção.
- `apps/web/next-env.d.ts`: alteração automática do Next.js; restaurar para a versão rastreada antes do commit.
- Scripts exploratórios sem dependência de execução (`scripts/audit_transport.py`, `scripts/inspect_development_area.py` e `scripts/validate_economy_area.py`) devem ficar fora do primeiro pacote, salvo decisão explícita de mantê-los como ferramentas internas.

## Bloqueadores encontrados

1. Resolvido: o `Dockerfile` copia `pilot-seed/loa-homologada-render.zip`, extrai em `/app/loa-data` e define `PILOT_EDUCATION_ONLY=false` na imagem.
2. Resolvido: o banco operacional de 328 MiB não entra na imagem; o banco homologado otimizado está dentro do pacote validado.
3. Resolvido: `render.yaml` define `PILOT_EDUCATION_ONLY=false`, alinhado ao Dockerfile e aos padrões da API.
4. Resolvido: a interface anuncia o acervo homologado completo de 2019 a 2026 e não contém mais uma lista restrita de áreas.
5. Resolvido no pacote: mapa editorial, regras e segmentos históricos estão presentes e validados.
6. Resolvido: a suíte completa tem 65 testes aprovados; auditoria de resolução tem zero falhas.

## Validação da configuração final

- Compilação de produção do Next.js concluída sem erros de TypeScript.
- Suíte Python: 65 testes aprovados.
- `git diff --check`: sem erros de espaços ou marcadores de conflito.
- O serviço do Render mantém o mesmo nome para atualizar a instalação existente, e o PostgreSQL de feedback continua referenciado separadamente por `FEEDBACK_DATABASE_URL`.

## Decisão para o próximo passo

Construir um novo artefato de dados a partir de `storage/loa.db`, contendo somente registros homologados e as páginas necessárias para rastreabilidade; validar sua integridade; então atualizar `Dockerfile`, `render.yaml` e os textos/configurações da interface para consumir esse artefato. O banco de feedback do Render deve continuar separado e não pode ser sobrescrito pelo pacote da LOA.
