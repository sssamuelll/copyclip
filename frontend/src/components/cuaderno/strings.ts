// Two-locale chrome strings for the answer-turn UI. unknown/absent -> en.
// The `en` values are verbatim the strings the components shipped with.
type Lang = 'es' | 'en'

const STRINGS: Record<Lang, Record<string, string>> = {
  en: {
    gotit_prompt: 'does this answer the question?',
    gotit_got: 'I got this',
    gotit_didnt: "I didn't",
    gotit_marked_got: '✓ marked: got this',
    gotit_saved_pre: 'saved to ',
    gotit_saved_mid: 'this matters',
    gotit_saved_post: '. ask anything else when ready.',
    gotit_marked_didnt: "↻ marked: didn't",
    gotit_didnt_msg: 'where did it break? try a follow-up below or rephrase.',
    you_asked: 'you asked',
    go_deeper: 'go deeper',
    running: 'running…',
    banner_ungrounded_kicker: 'not grounded',
    banner_ungrounded_text:
      'This answer is not anchored to code the tutor actually read, so it may be invented. Either the project does not cover this, or the tutor answered too soon. Re-ask, or point at a specific file, function, or commit.',
    banner_off_target_kicker: 'off target',
    banner_off_target_text:
      'This is grounded in the code, but it answers a different question than you asked. Re-ask to redirect it to what you meant.',
    banner_insufficient_evidence_kicker: 'insufficient evidence',
    banner_insufficient_evidence_text:
      'The tutor looked but the project does not contain enough to answer this confidently. What it would need is named above.',
    banner_partial_kicker: 'partial answer',
    banner_partial_text: 'This answer was interrupted before it finished. It may be incomplete.',
    banner_fallback_kicker: 'no answer',
    banner_fallback_text: 'The tutor could not produce an answer for this question this time.',
  },
  es: {
    gotit_prompt: '¿esto responde la pregunta?',
    gotit_got: 'lo capté',
    gotit_didnt: 'no lo capté',
    gotit_marked_got: '✓ marcado: lo capté',
    gotit_saved_pre: 'guardado en ',
    gotit_saved_mid: 'esto importa',
    gotit_saved_post: '. pregunta lo que quieras cuando estés listo.',
    gotit_marked_didnt: '↻ marcado: no lo capté',
    gotit_didnt_msg: '¿dónde se rompió? prueba un seguimiento abajo o reformula.',
    you_asked: 'preguntaste',
    go_deeper: 'profundiza',
    running: 'corriendo…',
    banner_ungrounded_kicker: 'sin fundamento',
    banner_ungrounded_text:
      'Esta respuesta no está anclada a código que el tutor haya leído de verdad, así que podría estar inventada. O el proyecto no lo cubre, o el tutor respondió demasiado pronto. Vuelve a preguntar, o apunta a un archivo, función o commit específico.',
    banner_off_target_kicker: 'fuera de foco',
    banner_off_target_text:
      'Esto está anclado al código, pero responde una pregunta distinta a la que hiciste. Vuelve a preguntar para redirigirlo a lo que querías decir.',
    banner_insufficient_evidence_kicker: 'evidencia insuficiente',
    banner_insufficient_evidence_text:
      'El tutor buscó, pero el proyecto no contiene lo suficiente para responder esto con confianza. Lo que haría falta está nombrado arriba.',
    banner_partial_kicker: 'respuesta parcial',
    banner_partial_text: 'Esta respuesta se interrumpió antes de terminar. Puede estar incompleta.',
    banner_fallback_kicker: 'sin respuesta',
    banner_fallback_text: 'El tutor no pudo producir una respuesta para esta pregunta esta vez.',
  },
}

export function pickLang(lang?: string | null): Lang {
  return lang === 'es' ? 'es' : 'en'
}

export function t(key: string, lang?: string | null): string {
  const l = pickLang(lang)
  return STRINGS[l][key] ?? STRINGS.en[key] ?? key
}
