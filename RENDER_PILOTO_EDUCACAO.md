# Publicação da versão-piloto: Educação

Este roteiro publica **somente a versão-piloto de Educação**. Saúde, Defesa,
Cultura e outros temas não fazem parte do pacote de dados nem devem ser
liberados nesta etapa.

## O que já está preparado

- `render.yaml` cria dois serviços: a interface pública e a API privada.
- A API usa um disco persistente em `/var/data`.
- `storage/render-pilot-bundle/loa-piloto-educacao-render.zip` contém o banco
  derivado e os nove PDFs necessários ao piloto.
- A autenticação está preparada para o Cloudflare Access. Sem os dois valores
  do Cloudflare, a API não aceita cabeçalhos de e-mail enviados pelo navegador.

## Dados que a responsável precisa informar no Render

Preencha como segredos no painel do Render, nunca no repositório:

- `EDITOR_EMAILS`: lista de e-mails autorizados a registrar validação editorial.
- `REVIEWER_EMAILS`: e-mail ou e-mails que podem consultar o relatório de
  devolutivas. Definir antes de liberar o piloto.
- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`: domínio da equipe no Cloudflare Access.
- `CLOUDFLARE_ACCESS_AUDIENCE`: identificador de audiência da aplicação criada
  no Cloudflare Access.

## Ordem segura de publicação

1. Conecte o repositório que contém este projeto ao Render e crie os serviços
   pelo arquivo `render.yaml`.
2. Aguarde a criação do disco persistente da API. A primeira inicialização pode
   mostrar `documents: 0`: isto é apenas modo de preparação, não é o piloto.
3. No Shell da API no Render, copie o arquivo
   `loa-piloto-educacao-render.zip` para `/var/data`, extraia-o ali e confirme
   que existem `/var/data/loa.db` e `/var/data/dados`.
4. Reinicie a API. Só depois que `/health` reportar `documents: 9` e
   `pages: 293`, publique a interface web.
5. No Cloudflare Access, crie uma aplicação para o domínio público da interface
   e permita apenas os e-mails definidos para o piloto. Copie os valores de
   equipe e audiência para os segredos do Render e faça novo deploy da API.
6. Faça uma consulta de Educação e confira uma fonte. Em seguida, faça uma
   pergunta de Saúde: ela deve informar que está fora do escopo do piloto.

## Segurança e limites

O pacote de dados é derivado: ele não altera o banco principal nem os PDFs
originais. As devolutivas registradas pelos usuários ficam armazenadas, mas não
geram alteração automática em respostas, dados ou regras. Qualquer melhoria
continua dependendo de autorização editorial.
