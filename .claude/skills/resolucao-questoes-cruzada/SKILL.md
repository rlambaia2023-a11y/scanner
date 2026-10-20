---
name: resolucao-questoes-cruzada
description: "Resolve provas, listas e questões (objetivas e discursivas) com gabarito justificado, cruzando fontes da internet e bancos de questões (QConcursos, TEC, provas anteriores) e entregando respostas humanizadas. Use para 'resolva', 'gabarito', 'responda essas questões', fotos de prova. Não use para criar questões novas ou corrigir redação."
metadata:
  version: '1.0'
---

# Resolução de questões com cruzamento de fontes

Aplica-se a fotos, PDFs ou textos com questões de prova, concurso, residência ou faculdade (o usuário é mestre em odontologia, mas vale para qualquer área).

## Fluxo

1. **Transcreva** cada questão e alternativa a partir do material. Marque trechos ilegíveis em vez de inventar texto; se uma alternativa estiver cortada, diga isso na resposta.
2. **Resolva primeiro por raciocínio próprio**, anotando internamente a resposta candidata e o conceito testado.
3. **Procure a questão em bancos de questões**: busque um trecho literal do enunciado (8–15 palavras) e variações. Priorize QConcursos, TEC Concursos, gabaritos oficiais da banca, provas anteriores da instituição, Passei Direto e Estratégia/Gran. Registre o gabarito oficial ou o mais votado, a banca e o ano quando encontrados.
4. **Cruze com fonte técnica confiável**: livro-texto, diretriz, artigo revisado, manual de conselho/sociedade ou material universitário. Em saúde, prefira fontes acadêmicas e diretrizes a blogs.
5. **Compare as três evidências** (raciocínio, banco, literatura):
   - Concordam → resposta firme.
   - Gabarito oficial diverge da literatura → informe o gabarito oficial como resposta "para a prova" e explique a divergência técnica.
   - Mais de uma alternativa defensável ou nenhuma correta → indique a mais provável pela intenção do examinador e sinalize possível recurso.
   - Questão não encontrada em banco → diga que a resposta se apoia na literatura.
6. **Redija** no formato abaixo. Concluído quando toda questão tem letra (ou resposta discursiva), justificativa e fonte citada.

## Formato de saída

- Abertura de uma ou duas frases, mencionando questões ambíguas.
- Tabela-resumo `Questão | Resposta` para as objetivas.
- Uma seção por questão: `### N. Letra — ideia central da alternativa`, seguida de 1–3 parágrafos curtos de justificativa, com o motivo pelo qual as distratoras mais tentadoras estão erradas quando isso ajudar.
- Quando houver, uma linha "Banco de questões: [banca, ano — gabarito](url)".
- Discursivas: texto corrido pronto para ser escrito na prova, em sequência lógica, sem tópicos excessivos; depois, opcionalmente, os pontos-chave que o corretor espera.
- Citações inline em toda afirmação técnica.

## Humanização

Escreva como um aluno bem preparado, com o tom ajustado ao tipo de questão (salvo pedido diferente do usuário):

- Discursivas: respostas escritas como para o professor, em tom respeitoso e objetivo, mostrando que o aluno domina o conteúdo.
- Justificativas das objetivas: explicações como para um colega, mais próximas e didáticas, mas ainda precisas.

Em todos os casos:

- Português natural, frases de tamanho variado, voz ativa, terminologia técnica correta sem pedantismo.
- Evite marcas de texto gerado: "Certamente", "Vale ressaltar que", "Em suma", "É importante destacar", listas de três adjetivos, conclusões repetindo o enunciado, emojis e exclamações.
- Não abra todas as justificativas com a mesma estrutura; vá direto ao conceito decisivo.
- Discursivas devem soar como resposta de aluno bem preparado: primeira pessoa evitada, sem meta-comentários ("nesta resposta, abordarei").
- Ressalvas clínicas entram como observação breve, não como aviso genérico.

## Exemplo

Entrada: foto com "9. A relação central é: A) ... B) posição articular independente de contato dentário ..."

Saída:

```
### 9. B — Posição articular, independente do contato dentário

A relação central é definida pela posição dos côndilos na fossa, e não pelo engrenamento dos dentes. Por isso pode ser registrada em desdentados totais e serve de referência para montar os modelos no articulador [fonte](url). A alternativa A confunde relação central com máxima intercuspidação.

Banco de questões: [Banca X, 2022 — gabarito B](url)
```
