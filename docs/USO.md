# Manual de uso GAQ Jobs Web

Entre em https://jobs.gaqtech.dev com e-mail e senha definidos no servidor. Não há cadastro público.

## Navegação

Todas as vagas apresenta todas as oportunidades. Oportunidades mostra NAO_AVALIADA e INTERESSE. Candidaturas concentra inscrições, entrevistas, testes, ofertas e resultados. O botão ‹ recolhe a barra lateral e › expande.

## Filtros

Podem ser combinados: busca textual, modalidade, contrato, aderência mínima e data da coleta (últimos 7/30/90 dias ou período personalizado). Ordene por data, aderência ou cargo. Há paginação.

O filtro de data usa primeira_coleta no fuso America/Sao_Paulo; não equivale à data do anúncio.

## Detalhes

Clique numa vaga para abrir detalhes, descrição, competências, informações salariais e histórico. O botão Abrir vaga original abre o anúncio em outra aba; Copiar guarda o link. Apenas URLs com http ou https são aceitas.

## Status e anotações

Administradores podem escolher um status, editar observações e clicar em Salvar alterações. O banco registra cada mudança de status em vagas_status_hist. Usuários LEITURA não podem editar.

## Integração e segurança

O Grok continua pesquisando e atualizando vagas pelo n8n, independentemente do painel. O frontend não acessa SQL diretamente. Senhas são armazenadas como hash Argon2id; sessões ficam no PostgreSQL.

Limitações: sem recuperação de senha por e-mail, MFA, anexos, autoinscrição pela interface ou verificação Gmail independente na v1.
