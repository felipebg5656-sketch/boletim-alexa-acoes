# Boletim da Bolsa no Echo Show 5 (21h)

Projeto pessoal, gratuito dentro das cotas dos serviços, para narrar **cotações de 10 ativos brasileiros, manchetes e proventos** pela Alexa no Echo Show 5.

## Como funciona

1. **GitHub Actions** executa `generate.py` diariamente às **20h de Brasília** (23h UTC), ou quando você clicar em *Run workflow*.
2. A **brapi** fornece uma cotação individual para cada ticker. No plano gratuito há atraso aproximado de 30 minutos. Uma chave gratuita é obrigatória para todos os ativos.
3. A API pública **Dados B3** consulta os eventos de dividendos e JCP por empresa, filtrando classe PN/ON e mostrando pagamentos futuros e anúncios recentes. Os dados podem não contemplar um anúncio antes de sua publicação nas bases consultadas.
4. **Google Notícias RSS** fornece **manchetes**, não resumos do texto completo. O script seleciona no máximo 4 títulos recentes, associados às 10 empresas.
5. **GitHub Pages** publica um arquivo estático HTTPS `briefing.json` conforme o formato Flash Briefing da Amazon, e uma página de acompanhamento `index.html`.
6. A **Flash Briefing Skill** da Alexa lê o conteúdo. Sua rotina diária começa às 21h, quando configurada no aplicativo Alexa.

**Importante:** a Amazon pode demorar até ~30 minutos para atualizar o cache do Flash Briefing. Programar a coleta uma hora antes ajuda, mas não garante atualização/execução em minuto exato. GitHub Actions também pode sofrer atrasos na execução de tarefas agendadas.

## 1. Criar uma chave gratuita da brapi

- Acesse https://brapi.dev/ e crie uma conta (plano **Grátis**).
- No painel, gere sua chave de API. **Não cole a chave no código, em mensagens ou arquivos públicos**.
- Limites publicados na consulta: 15.000 requisições/mês; 1 ticker por requisição; cotações ~30 min atrasadas; dividendos não incluídos. Por isso usamos Dados B3 para proventos.

## 2. Criar o repositório no GitHub

- Acesse https://github.com/new e crie um repositório **público** chamado, por exemplo, `boletim-alexa-acoes`.
- Descompacte este pacote e envie **todos os arquivos**, inclusive a pasta oculta `.github/workflows/`.
- Abra **Settings → Secrets and variables → Actions → New repository secret**.
- Crie o segredo **`BRAPI_API_KEY`** e cole o valor no campo secreto **do GitHub**.
- Opcional: em **Variables**, crie `PUBLIC_URL` com a URL do site do GitHub Pages, quando existir. Sem isso, o link "Saiba mais" da Alexa abre a página do fornecedor de cotação; o conteúdo do boletim permanece correto.

**Privacidade:** o GitHub Pages é público. O conteúdo gerado expõe tickers e notícias, mas não quantidades, CPF, corretora nem chave brapi. Se você não quiser tornar pública a lista, use uma arquitetura privada com integração diferente.

## 3. Habilitar GitHub Pages

- No repositório, entre em **Settings → Pages**.
- Em **Build and deployment → Source**, selecione **GitHub Actions**.
- Abra **Actions → Publicar boletim na Alexa → Run workflow → Run workflow**.
- Após executar com sucesso, em **Settings → Pages** haverá um endereço semelhante a:
  `https://SEU-USUARIO.github.io/boletim-alexa-acoes/`
- Abra no navegador a página acima (painel) e `https://SEU-USUARIO.github.io/boletim-alexa-acoes/briefing.json` (feed JSON). **Troque SEU-USUARIO pelo seu nome de usuário real**.

A página `briefing.json` deve conter uma lista JSON com `uid`, `updateDate`, `titleText`, `mainText` e `redirectionUrl`.

Se a execução falhar por ausência da chave, corrija `BRAPI_API_KEY` no GitHub. Se falhar por cotações indisponíveis, veja os logs de Actions para identificar tickers sem resposta; o script se recusa a publicar se menos de 10 entre 10 retornarem dados.

## 4. Criar a Flash Briefing Skill na Amazon

- Acesse https://developer.amazon.com/alexa/console/ask com **a mesma conta Amazon** que usa no Echo Show 5.
- Clique em **Create Skill / Criar skill**.
- Nome da skill: **Boletim de Ações**.
- Idioma: **Português (Brasil)**.
- Modelo: **Flash Briefing**. Hospedagem: **Provision your own** (conteúdo externo).
- No campo da mensagem de erro, escreva: `O boletim da bolsa está temporariamente indisponível.`
- Adicione **um feed** com estas características:
  - **Preamble:** `Do Boletim de Ações.`
  - **Name:** `Bolsa e Proventos`.
  - **Content update frequency:** `Daily`.
  - **Content type:** `Text`.
  - **Content genre:** `Business` ou opção financeira equivalente.
  - **Feed:** URL pública terminada em `/briefing.json`.
  - **Feed Icon:** uma imagem PNG/JPG quadrada de 512 × 512 px (pode criar no Canva).
- Teste a skill no console e no seu Echo Show, associado à mesma conta Amazon. Caso a versão de desenvolvimento não apareça, siga os testes de publicação/certificação da Amazon. A Amazon controla a disponibilidade e aprovação, não o script.

**Atenção:** recursos de *Alexa Skill Blueprints* são diferentes do Developer Console; a Amazon anunciou descontinuação da criação/edição via Blueprints a partir de 20/11/2026. Este projeto **não depende de Blueprints**.

## 5. Criar a rotina de voz diária (às 21h)

Depois de ter testado/habilitado a skill:

- No app **Amazon Alexa → Mais → Configurações → Notícias → Resumo de notícias**, ative **Bolsa e Proventos**. Desative as outras fontes se quiser ouvir apenas seu boletim.
- Vá a **Mais → Rotinas → +**.
- Nome: `Boletim da Bolsa — 21h`.
- **Quando:** `Programação → Às 21:00 → Todos os dias`.
- **Ação:** `Notícias → Resumo de notícias` (o nome varia conforme a versão do app).
- Se houver o campo **De / Ouvir Alexa de**, selecione seu **Echo Show 5 do quarto**.
- Salve e teste. Se o aplicativo não permitir iniciar o resumo por rotina, experimente adicionar a ação **Personalizar** com `leia meu resumo de notícias` como última ação. O comportamento pode variar por versão/conta.

### E integrar com a rotina "Boa noite"?

Se quiser ouvir o boletim **somente ao dizer** "Alexa, boa noite", adicione a ação `Notícias / Resumo de notícias` à sua rotina Boa noite. Se quiser ouvir **automaticamente às 21h**, mantenha uma rotina separada por horário. Evite incluir o mesmo boletim em ambas se não quiser repetição.

## 6. Ajustar seus tickers

No arquivo `generate.py`, edite `ASSETS`. Padrões escolhidos:

| Empresa | Ticker configurado | Classe |
| --- | --- | --- |
| Itaú | ITUB4 | PN |
| Bradesco | BBDC4 | PN |
| Banco ABC Brasil | ABCB4 | PN |
| CPFL Energia | CPFE3 | ON |
| AXIA Energia | AXIA3 | ON |
| ISA Energia | ISAE4 | PN |
| Porto Seguro | PSSA3 | ON |
| BB Seguridade | BBSE3 | ON |
| Caixa Seguridade | CXSE3 | ON |
| Sanepar | SAPR4 | PN |

As **classes das suas posições** não foram confirmadas; por exemplo, SAPR11 é diferente de SAPR4 e tem regras de proporção de proventos distintas. Se trocar para `SAPR11`, o script não calculará automaticamente os pagamentos da UNIT a partir de ON/PN: adapte o código antes de usar valores por UNIT. Não é necessário cadastrar valores investidos nem quantidades para esta versão.

## 7. Segurança, limites e observações

- **Não inventa cotações**: sem dados confirmados aparece indisponível. Quando alguma cotação não está acessível, a publicação é interrompida para preservar a versão anterior.
- **Proventos não são créditos garantidos**: para receber, é preciso ter posição elegível na data-com. Valores publicados são **brutos por ação**. Verifique documentos oficiais de RI.
- As manchetes são de terceiros e podem conter termos enviesados ou falsos. O script cita o título, não valida o texto integral. Não gera recomendação financeira nem afirma que manchetes são fatos confirmados.
- O site do GitHub Pages é público (a Alexa exige um feed público HTTPS). Não guarde nenhuma senha, e-mail ou posição financeira no repositório.
- O script usa Python apenas da biblioteca padrão e cotações gratuitas. Pode sofrer mudanças nos provedores, autenticação, limites e políticas comerciais.
- Em pregões sem negociação, a data da última cotação será anunciada quando disponível.

## Fontes / documentação

- API BRAPI: https://brapi.dev/docs e https://brapi.dev/faq/api-e-gratis-mesmo
- API de proventos Dados B3: https://dadosb3.com/api
- Amazon Flash Briefing: https://developer.amazon.com/pt-BR/docs/alexa/flashbriefing/steps-to-create-a-flash-briefing-skill.html
- Formato do feed Alexa: https://developer.amazon.com/en-US/docs/alexa/flashbriefing/flash-briefing-skill-api-feed-reference.html
- GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
