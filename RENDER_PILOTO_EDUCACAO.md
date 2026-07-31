# Publicação do piloto gratuito: Educação

Esta configuração publica somente o piloto de Educação. Saúde, Defesa,
Cultura e outros temas permanecem fora da aplicação.

## Arquitetura gratuita

- `render.yaml` cria um único serviço web gratuito e um PostgreSQL gratuito
  usado exclusivamente para feedbacks, relatórios e consultas salvas.
- `pilot-seed/loa-piloto-educacao-render.zip` contém o banco derivado e os
  nove PDFs do piloto. O pacote é incorporado à imagem de publicação, portanto
  é restaurado sempre que o serviço gratuito reinicia.
- O Cloudflare Access restringe o acesso aos e-mails autorizados.

## Segredos necessários no Render

Preencha no painel do Render, nunca no repositório:

- `EDITOR_EMAILS`: e-mails autorizados a registrar validação editorial.
- `REVIEWER_EMAILS`: e-mail ou e-mails que podem baixar o relatório de
  devolutivas.
- `CLOUDFLARE_ACCESS_TEAM_DOMAIN`: domínio da equipe no Cloudflare Access.
- `CLOUDFLARE_ACCESS_AUDIENCE`: identificador de audiência da aplicação.

## Publicação

1. No Render, crie um Blueprint a partir deste repositório.
2. Confira que a revisão mostra apenas `consulta-loa-piloto` e
   `consulta-loa-feedback`, ambos no plano `free`.
3. Informe os segredos solicitados e faça a publicação.
4. No Cloudflare Access, crie a aplicação para o endereço público do Render,
   permita somente os e-mails do piloto e copie os dois valores de configuração
   para o Render.
5. Faça uma consulta de Educação e confira uma fonte. Uma pergunta de Saúde
   deve retornar que o tema está fora do escopo.

## Limites

O serviço gratuito pode dormir depois de 15 minutos de inatividade e levar
cerca de um minuto para voltar. O PostgreSQL gratuito expira após 30 dias;
baixe o relatório de feedback antes desse prazo. Nenhuma devolutiva altera
automaticamente dados, respostas ou regras: melhorias exigem autorização
editorial.
