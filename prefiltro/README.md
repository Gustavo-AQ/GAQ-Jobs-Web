# Pré-filtro de vagas

Script em Python 3.11 ou superior (o CI usa 3.13; só a biblioteca padrão — veja `requirements.txt`) que lê posts brutos de vaga, descarta os que claramente não servem e pontua o restante de 0 a 100. A ideia é baratear o passo seguinte: só os posts que passam daqui vão para um assistente de IA avaliar a aderência final.

O piso salarial padrão é **R$ 1.800**. Post sem salário informado **não** é eliminado por isso. Não há lista de empresas a evitar.

Os filtros eliminatórios de idioma, horário e local presencial ficam no config, são editáveis e podem estar vazios ou `null` — lista/campo vazio desliga aquele filtro. O arquivo versionado é `config.example.json` (perfil genérico de exemplo, com a estrutura dos filtros). Copie para `config.json` para ajustar idiomas, horário e cidades no seu uso; essa cópia fica de fora do Git.

## Uso

Se `config.json` não existir ao lado do script, o padrão é `config.example.json`.

```bash
cd prefiltro
cp config.example.json config.json   # opcional
python3 prefiltro.py entrada.json -o saida.json
python3 prefiltro.py entrada.json -o saida.json --min-score 40
python3 prefiltro.py entrada.json -o saida.json --ja-enviados ja_enviados.txt
python3 prefiltro.py entrada.json -o saida.json --config config.json
```

Rode a partir desta pasta ou passe caminhos absolutos. Há um arquivo de teste e um script que confere os filtros ligados e desligados (sempre contra `config.example.json`):

```bash
python3 prefiltro.py exemplos.json -o /tmp/saida_exemplos.json
python3 testes.py
```

O coletor grava no mesmo formato de entrada (`texto`, `url`, `autor`, `data`, `fonte`). Depois da coleta:

```bash
python3 prefiltro.py ../coletor/vagas_coletadas.json -o ../coletor/vagas_prefiltradas.json
```

### Entrada

- **JSON**: lista de posts, ou um objeto com `posts` / `vagas`.
- **JSONL**: um objeto por linha.
- **Texto**: posts separados por uma linha `---`.

Cada post precisa de `texto`. Campos opcionais: `url`, `autor`, `data`, `fonte`.

`--ja-enviados` aceita URLs (uma por linha) ou um JSON com lista de URLs / objetos com `url`. Esses posts são pulados.

### Saída

JSON com `vagas` (somente as que passaram, da maior para a menor nota), cada uma com `score`, `razoes`, `nivel_detectado`, `modelo_detectado`, `salario_detectado` e `componentes`. O resumo (lidos, descartes por motivo, mantidos) vai para o stdout. A saída também registra quais filtros eliminatórios estavam ativos.

## Como a nota é calculada

Depois de normalizar o texto (minúsculas, sem acento), o script aplica **regras duras** e só então pontua:

1. Não é oferta de vaga (ex.: "estou em busca", *open to work*, anúncio de curso).
2. Nível sênior / lead / especialista / staff / principal **sem** citar júnior, trainee, estágio ou pleno.
3. Idioma da lista `idiomas_eliminatorios` aparece como **obrigatório**, fluente ou *required* — não como diferencial/plus. Lista vazia desliga o filtro.
4. Turno da lista `horarios_eliminatorios` (ex.: noturno) ou jornada com término depois de `horario_limite_fim`, **somente quando o horário está explícito**. Horário desconhecido não elimina. "Estudar no período noturno" não conta como jornada noturna. Campos vazios desligam o filtro.
5. Presencial ou híbrido fora da UF de `local_presencial` (e, se `cidades` tiver itens, fora dessas cidades). Remoto sempre passa. Sem informação de local, não elimina. `cidades` vazia aceita qualquer cidade da UF. Objeto vazio ou sem `uf` desliga o filtro.
6. Salário (ou teto da faixa) abaixo do piso. Entende `R$ 1.500`, `1,5k`, `3k`, `2 mil`.
7. Duplicata (mesma URL, mesmo texto ou quase-duplicata por similaridade).

A nota 0–100 é uma média ponderada de:

| Componente     | Peso padrão | O que mede                                      |
|----------------|-------------|-------------------------------------------------|
| habilidades    | 50          | Cruzamento com o stack do perfil (pesos no config) |
| área           | 20          | Núcleo (IA / backend) ou adjacente (dados, RPA, DevOps, QA) |
| nível          | 15          | Júnior/trainee valem mais; pleno é aceitável    |
| modelo/local   | 15          | Remoto primeiro; híbrido/presencial na UF depois |

O corte padrão é **score >= 40**: propositalmente folgado. O assistente de IA decide a aderência final.

As habilidades do config de exemplo descrevem um stack genérico de Python, backend e IA; áreas adjacentes (RPA, QA, DevOps etc.) servem só para reconhecer o tipo da vaga.

## Exemplos dos filtros eliminatórios

Estes quatro campos são opcionais. Vazio, `null` ou `""` desliga aquele filtro. O `config.example.json` vem com o primeiro bloco, e `testes.py` confere os dois comportamentos.

Filtros ligados (é o exemplo versionado):

```json
"idiomas_eliminatorios": ["espanhol"],
"horarios_eliminatorios": ["noturno"],
"horario_limite_fim": "19:00",
"local_presencial": { "uf": "SP", "cidades": [] }
```

- `espanhol` só elimina quando o anúncio exige o idioma (fluente, obrigatório, *required*). "Espanhol é um diferencial" passa.
- `noturno` elimina turno/plantão noturno explícito. "Cursando faculdade no período noturno" não é jornada.
- `19:00` elimina se o término da jornada está escrito e passa desse horário (ex.: das 9h às 20h). "Horário a combinar" não elimina. `""` desliga só este corte; o turno noturno continua valendo se a lista não estiver vazia.
- `cidades: []` aceita presencial ou híbrido em qualquer cidade de SP (Campinas passa; Curitiba sai). Remoto sempre passa. Sem cidade no texto, não elimina.

Restringir à capital:

```json
"local_presencial": { "uf": "SP", "cidades": ["São Paulo"] }
```

Híbrido em Campinas passa a ser descartado. Presencial sem cidade continua, porque não há local para comparar.

Tudo desligado:

```json
"idiomas_eliminatorios": [],
"horarios_eliminatorios": null,
"horario_limite_fim": null,
"local_presencial": { "uf": "", "cidades": [] }
```

`local_presencial: null` ou `{}` também desliga o filtro de local. Outra UF funciona do mesmo jeito (`"uf": "RJ"`); `cidades` vazia significa qualquer cidade daquele estado.

## Como ajustar o config

Não precisa editar o código. Copie `config.example.json` para `config.json` e altere a cópia. Os campos mais úteis:

- `min_score` — corte da nota (padrão 40). Suba se ainda passar muita coisa; desça se estiver cortando vaga boa.
- `salario_piso` — piso em BRL (padrão 1800). Só elimina quando o post **mostra** um valor/faixa abaixo disso.
- `idiomas_eliminatorios` — lista de idiomas que eliminam a vaga só se forem exigidos (ex.: `["espanhol"]`). `[]` ou `null` desliga.
- `horarios_eliminatorios` — turnos que eliminam quando explícitos (ex.: `["noturno"]`). `[]` ou `null` desliga.
- `horario_limite_fim` — se a jornada termina depois desse horário (ex.: `"19:00"`), elimina. `""` ou `null` desliga o corte de horário, sem afetar o filtro de turno.
- `local_presencial` — `{ "uf": "SP", "cidades": [] }`. UF vazia desliga o filtro. `cidades` vazia aceita qualquer cidade da UF; com nomes, o presencial/híbrido fica restrito a essas cidades.
- `similaridade_duplicata` — limiar Jaccard para quase-duplicata (padrão 0,85).
- `habilidades_teto` — soma de pesos que já vale 100 no componente de skills (padrão 30). Se poucas skills estiverem estourando a nota, aumente um pouco.
- `pesos` — peso de cada componente (não precisam somar 100; o script normaliza).
- `habilidades` — lista `{termo, aliases, peso}`. Aumente o `peso` do que é mais central no perfil; acrescente aliases se um termo aparece escrito de outro jeito.
- `areas.nucleo` / `areas.adjacentes` — termos que identificam o tipo da vaga.
- `niveis_aceitaveis` / `niveis_senior` — sinais de nível.
- `nao_e_vaga` — frases de candidato (*open to work*) e de anúncio de curso.
- `local_sp` / `locais_fora_sp` — léxico de cidades e estados usado pelo filtro de `local_presencial` quando a UF é SP. Para outras UFs o script usa uma lista curta interna de capitais e cidades grandes.

Depois de mudar o config, rode de novo nos `exemplos.json` (e o `testes.py`) e confira se os casos de manter/descartar continuam fazendo sentido.
