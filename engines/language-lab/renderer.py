# engines/language-lab/renderer.py
#
# WHAT: Interactive HTML rendering for Language Lab lesson packs —
#       vocab flashcards, grammar drills, listening items wired to
#       segment audio, and a final evaluation screen with score
#       breakdown (P7.4).
# WHY:  Same separation as journey-core: generation produces validated
#       data (P7.2); rendering produces presentation. The renderer never
#       calls a model. Browser-side checking mirrors the deterministic
#       graders in engines/language-lab/graders.py (normalize_answer /
#       accent folding / slash alternatives) so what the learner
#       experiences agrees with what the app would score offline.
#       Free-form translations cannot be judged in a browser — the UI
#       says so honestly and falls back to self-grade against the
#       reference answer.
# BREAKS IF DELETED: Lesson packs remain raw JSON; the flagship has no
#       learner-facing surface.

from __future__ import annotations

import html
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["LanguageLabRenderer", "render_lesson_pack_html"]

_BLANK_MARKER = "___"


# ---------------------------------------------------------------------------
# Static assets (kept .format-free so braces stay literal)
# ---------------------------------------------------------------------------

_CSS = """\
:root {
  --bg:#f8f9fa; --card-bg:#fff; --text:#1a1a2e; --muted:#6c757d;
  --accent:#4361ee; --accent-light:#eef2ff; --success:#2ec4b6;
  --error:#e63946; --border:#dee2e6; --radius:8px;
  --shadow:0 2px 8px rgba(0,0,0,.08);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;padding:2rem}
h1{font-size:1.75rem;margin-bottom:.25rem}
.badge{display:inline-block;background:var(--accent-light);color:var(--accent);
  font-size:.8rem;font-weight:600;padding:.2em .6em;border-radius:4px;
  margin:.75rem .35rem 1.5rem 0;text-transform:capitalize}
.card{background:var(--card-bg);border:1px solid var(--border);
  border-radius:var(--radius);box-shadow:var(--shadow);padding:1.5rem;
  margin-bottom:1.5rem;max-width:720px}
.card h2{font-size:1.2rem;margin-bottom:.75rem}
.turn{margin-bottom:.6rem}
.turn .speaker{font-weight:700;color:var(--accent)}
.flip-grid{display:flex;flex-wrap:wrap;gap:1rem}
.flip-card{width:200px;height:130px;perspective:800px;cursor:pointer}
.flip-inner{position:relative;width:100%;height:100%;
  transition:transform .4s;transform-style:preserve-3d}
.flip-card.flipped .flip-inner{transform:rotateY(180deg)}
.flip-face{position:absolute;inset:0;backface-visibility:hidden;border:1px solid var(--border);
  border-radius:var(--radius);padding:.75rem;display:flex;flex-direction:column;
  justify-content:center;text-align:center;background:var(--card-bg)}
.flip-back{transform:rotateY(180deg);background:var(--accent-light)}
.term{font-weight:700;font-size:1.05rem}
.reading{color:var(--muted);font-size:.85rem}
.selfgrade{margin-top:.5rem;display:flex;gap:.4rem;justify-content:center}
.selfgrade button{border:1px solid var(--border);border-radius:6px;
  padding:.25rem .6rem;cursor:pointer;font-size:.8rem;background:var(--card-bg)}
.selfgrade button.got{background:#d1fae5;color:#065f46}
.selfgrade button.again{background:#fee2e2;color:#7f1d1d}
.drill{margin:.5rem 0;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
.drill input,.q input{padding:.45rem .6rem;border:1px solid var(--border);
  border-radius:6px;font-size:.95rem}
.drill button,.q button{padding:.45rem .9rem;border:1px solid var(--accent);
  border-radius:6px;background:var(--accent-light);color:var(--accent);
  cursor:pointer;font-size:.9rem}
.mark{font-weight:600;margin-left:.4rem}
.mark.ok{color:var(--success)} .mark.bad{color:var(--error)}
.q{margin:.9rem 0}
.opts{list-style:none;display:flex;flex-direction:column;gap:.5rem;margin-top:.4rem}
.opts button{width:100%;text-align:left;padding:.6rem .8rem;border:1px solid var(--border);
  border-radius:6px;background:var(--card-bg);cursor:pointer;font-size:.95rem}
.opts button.sel-ok{background:#d1fae5;border-color:var(--success)}
.opts button.sel-bad{background:#fee2e2;border-color:var(--error)}
audio{display:block;margin-top:.4rem}
.listening-row{display:flex;gap:.75rem;align-items:center;margin:.5rem 0;flex-wrap:wrap}
#final-screen h2{margin-bottom:.5rem}
.breakdown{list-style:none;margin:.75rem 0}
.breakdown li{padding:.15rem 0}
.reset{margin-top:1rem;padding:.5rem 1rem;border:1px solid var(--border);
  border-radius:var(--radius);background:var(--card-bg);cursor:pointer}
"""

_JS = """\
function normAnswer(s){
  var EDGE="\\"'\\u201c\\u201d\\u2018\\u2019….,!?;:\\u00bf\\u00a1";
  s=String(s).trim();
  while(s.length&&EDGE.indexOf(s.charAt(0))!==-1)s=s.slice(1);
  while(s.length&&EDGE.indexOf(s.charAt(s.length-1))!==-1)s=s.slice(0,-1);
  return s.toLowerCase().replace(/\\s+/g,' ').trim();
}
function foldAccents(s){
  return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
}
function gradeKeyed(key,input){
  var keys=key.split('/').map(normAnswer).filter(Boolean);
  var norm=normAnswer(input);
  if(!norm)return'empty';
  if(keys.indexOf(norm)!==-1)return'ok';
  var fk=keys.map(foldAccents),fn=foldAccents(norm);
  if(fk.indexOf(fn)!==-1)return'folded';
  return'bad';
}
var SCORE={};
function bump(section,delta){SCORE[section]=(SCORE[section]||0)+delta;}
function mark(el,state,text){
  el.classList.remove('ok','bad');
  if(state==='ok'||state==='folded')el.classList.add('ok');else el.classList.add('bad');
  el.textContent=text;
}
function checkDrill(btn){
  var wrap=btn.closest('.drill,.listening-row');
  var input=wrap.querySelector('input');
  var m=wrap.querySelector('.mark');
  var res=gradeKeyed(btn.dataset.answer,input.value);
  if(res==='empty'){mark(m,'bad','type an answer');return;}
  if(res==='ok'){bump('grammar',1);mark(m,'ok','Correct!');}
  else if(res==='folded'){bump('grammar',1);mark(m,'ok','Correct (accents ignored)');}
  else{mark(m,'bad','Not quite — expected: '+btn.dataset.answer);}
  input.disabled=true;btn.disabled=true;
}
function chooseOpt(btn){
  var q=btn.closest('.q'),buttons=q.querySelectorAll('.opts button');
  Array.prototype.forEach.call(buttons,function(b){b.disabled=true;});
  if(String(btn.dataset.index)===btn.dataset.correct){
    btn.classList.add('sel-ok');bump('evaluation',1);
    mark(q.querySelector('.mark'),'ok','Correct!');
  }else{
    btn.classList.add('sel-bad');
    buttons[parseInt(btn.dataset.correct,10)].classList.add('sel-ok');
    mark(q.querySelector('.mark'),'bad','Incorrect');
  }
}
function checkBlank(btn){
  var wrap=btn.closest('.q'),input=wrap.querySelector('input');
  var res=gradeKeyed(btn.dataset.answer,input.value);
  if(res==='empty'){mark(wrap.querySelector('.mark'),'bad','type an answer');return;}
  if(res==='ok'){bump('evaluation',1);mark(wrap.querySelector('.mark'),'ok','Correct!');}
  else if(res==='folded'){bump('evaluation',1);
    mark(wrap.querySelector('.mark'),'ok','Correct (accents ignored)');}
  else{
    var ref=wrap.querySelector('.reference');
    ref.style.display='block';
    mark(wrap.querySelector('.mark'),'bad','Check the reference — still right? Tell yourself:');
    var sg=wrap.querySelector('.selfgrade-inline');
    sg.style.display='inline-flex';
  }
}
function selfGrade(btn,section,points){
  var face=btn.closest('.flip-face')||btn.closest('.q');
  var buttons=(face||document).querySelectorAll('.selfgrade button, .selfgrade-inline button');
  Array.prototype.forEach.call(buttons,function(b){b.disabled=true;b.style.opacity=.6;});
  btn.style.opacity=1;
  if(btn.dataset.grade==='got'){bump(section,points||1);}
  var label=face.querySelector('.mark');
  if(label){label.className='mark '+(btn.dataset.grade==='got'?'ok':'bad');
    label.textContent=btn.dataset.grade==='got'?'Marked correct':'Marked for review';}
  refreshFinal();
}
function finish(){
  var el=document.getElementById('breakdown');
  var rows=[];
  var order=['flashcards','grammar','evaluation'];
  for(var i=0;i<order.length;i++){
    var k=order[i];
    if(SCORE[k]!==undefined)rows.push('<li>'+k+': <strong>'+SCORE[k]+'</strong></li>');
  }
  el.innerHTML=rows.join('');
  document.getElementById('final-screen').style.display='block';
  document.getElementById('final-screen').scrollIntoView({behavior:'smooth'});
}
function refreshFinal(){}
"""


# ---------------------------------------------------------------------------
# Small fragment templates (.format targets)
# ---------------------------------------------------------------------------

_DIALOGUE_TURN = (
    '<div class="turn"><span class="speaker">{speaker}:</span> {content}'
    '{audio}</div>\n'
)

_AUDIO_TAG = '<audio controls preload="none" src="{src}"></audio>'

_FLIP_CARD = """\
<div class="flip-card" onclick="this.classList.toggle('flipped')">
  <div class="flip-inner">
    <div class="flip-face"><div class="term">{term}</div><div class="reading">{reading}</div></div>
    <div class="flip-face flip-back"><div>{translation}</div><div class="reading">{example}</div>
      <div class="selfgrade">
        <button data-grade="got" onclick="event.stopPropagation();selfGrade(this,'flashcards',1)">Got it</button>
        <button data-grade="again" onclick="event.stopPropagation();selfGrade(this,'flashcards',0)">Again</button>
      </div>
      <span class="mark"></span>
    </div>
  </div>
</div>
"""

_GRAMMAR_CARD = """\
<div class="card">
  <h2>{point}</h2>
  <p>{explanation}</p>
{drills}
</div>
"""

_DRILL = (
    '<div class="drill"><span>{prompt}</span>'
    '<input type="text" placeholder="your answer"/>'
    '<button data-answer="{answer}" onclick="checkDrill(this)">Check</button>'
    '<span class="mark"></span></div>\n'
)

_MC_ITEM = """\
<div class="q"><p><strong>{question}</strong></p>
  <ul class="opts">{options}</ul><span class="mark"></span>
</div>
"""

_MC_OPTION = (
    '<li><button data-index="{index}" data-correct="{correct}" '
    'onclick="chooseOpt(this)">{text}</button></li>'
)

_BLANK_ITEM = (
    '<div class="q"><p>{before}<input type="text" size="14"/>{after}</p>'
    '<button data-answer="{answer}" onclick="checkBlank(this)">Check</button>'
    '<p class="reference" style="display:none">Reference answer: '
    '<strong>{answer_display}</strong> — free-form answers can\'t be '
    'auto-judged offline.</p>'
    '<span class="selfgrade-inline" style="display:none;gap:.4rem">'
    '<button data-grade="got" onclick="selfGrade(this,\'evaluation\',1)">I was right</button>'
    '<button data-grade="again" onclick="selfGrade(this,\'evaluation\',0)">I was wrong</button>'
    '</span><span class="mark"></span></div>\n'
)

_TRANSLATION_ITEM = (
    '<div class="q"><p><strong>{prompt}</strong></p>'
    '<input type="text" placeholder="in {target}"/>'
    '<button data-answer="{answer}" onclick="checkBlank(this)">Check</button>'
    '<p class="reference" style="display:none">Reference answer: '
    '<strong>{answer_display}</strong> — valid alternative word orders '
    'can\'t be auto-judged offline.</p>'
    '<span class="selfgrade-inline" style="display:none;gap:.4rem">'
    '<button data-grade="got" onclick="selfGrade(this,\'evaluation\',1)">I was right</button>'
    '<button data-grade="again" onclick="selfGrade(this,\'evaluation\',0)">I was wrong</button>'
    '</span><span class="mark"></span></div>\n'
)

_TRANSFORMATION_ITEM = (
    '<div class="q"><p><strong>{prompt}</strong></p>'
    '<input type="text" placeholder="rewrite the sentence"/>'
    '<button data-answer="{answer}" onclick="checkBlank(this)">Check</button>'
    '<p class="reference" style="display:none">Reference rewrite: '
    '<strong>{answer_display}</strong> — equally valid rewrites '
    'can\'t be auto-judged offline.</p>'
    '<span class="selfgrade-inline" style="display:none;gap:.4rem">'
    '<button data-grade="got" onclick="selfGrade(this,\'evaluation\',1)">I was right</button>'
    '<button data-grade="again" onclick="selfGrade(this,\'evaluation\',0)">I was wrong</button>'
    '</span><span class="mark"></span></div>\n'
)

_LISTENING_ROW = (
    '<div class="listening-row">'
    '<audio controls preload="none" src="{src}"></audio>'
    '<input type="text" size="30" placeholder="what do you hear?"/>'
    '<button data-answer="{answer}" onclick="checkDrill(this)">Check</button>'
    '<span class="mark"></span></div>\n'
)

_FINAL_SCREEN = """\
<div class="card" id="final-screen" style="display:none;margin-top:2rem">
  <h2>Session complete!</h2>
  <ul class="breakdown" id="breakdown"></ul>
  <button class="reset" onclick="location.reload()">Start over</button>
</div>
"""

_FINISH_BAR = (
    '<button class="reset" onclick="finish()">Show my score</button>'
)


class LanguageLabRenderer:
    """
    Contract: convert a validated lesson pack dict into one interactive,
    self-contained HTML string. Never calls a model; never mutates the
    pack. Output is deterministic — identical input yields identical
    bytes.

    audio_files maps segment keys to playable sources:
      - "dialogue-<i>" -> audio for dialogue turn i
      - "listening-<i>" -> audio used by listening item i (defaults to
        dialogue-<i>'s source)
    """

    def render(self, pack: dict[str, Any], *,
               audio_files: Optional[dict[str, str]] = None) -> str:
        topic = str(pack.get("topic") or "").strip()
        level = str(pack.get("level") or "").strip()
        target = str(pack.get("target_language") or "").strip()
        known = str(pack.get("known_language") or "").strip()
        dialogue = pack.get("dialogue") or []
        vocab = pack.get("vocab_cards") or []
        grammar = pack.get("grammar_cards") or []
        evaluation = pack.get("evaluation") or []
        if not (topic and dialogue and vocab and grammar and evaluation):
            raise ValueError(
                "Lesson pack needs topic, dialogue, vocab_cards, "
                "grammar_cards and evaluation to render")

        parts = [
            f"<h1>{html.escape(topic)}</h1>",
            f'<span class="badge">{level}</span>',
            f'<span class="badge">{target} &rarr; {known}</span>',
            self._render_dialogue(dialogue, audio_files),
            self._render_vocab(vocab),
            *[self._render_grammar(card) for card in grammar],
            self._render_evaluation(evaluation, dialogue, target,
                                    known, level, audio_files),
        ]

        head = (f"<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                f"<meta charset=\"utf-8\"/>\n"
                f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>\n"
                f"<title>{html.escape(topic)}</title>\n<style>{_CSS}</style>\n"
                f"</head>\n<body>\n")
        tail = (_FINAL_SCREEN + "\n<script>" + _JS + "</script>\n</body>\n</html>\n")
        out = head + "\n".join(parts) + "\n" + _FINISH_BAR + "\n" + tail
        logger.info("Rendered lesson pack HTML: %s (%d vocab, %d grammar, %d eval)",
                    topic, len(vocab), len(grammar), len(evaluation))
        return out

    # -- sections ----------------------------------------------------------

    def _render_dialogue(self, dialogue, audio_files):
        turns = []
        for i, seg in enumerate(dialogue):
            audio = ""
            src = (audio_files or {}).get(f"dialogue-{i}")
            if src:
                audio = "<br/>" + _AUDIO_TAG.format(src=html.escape(str(src)))
            turns.append(_DIALOGUE_TURN.format(
                speaker=html.escape(str(seg.get("speaker", ""))),
                content=html.escape(str(seg.get("content", ""))),
                audio=audio,
            ))
        body = "".join(turns)
        return (f'<div class="card"><h2>Dialogue</h2>{body}</div>')

    def _render_vocab(self, vocab):
        cards = "".join(_FLIP_CARD.format(
            term=html.escape(str(c.get("term", ""))),
            reading=html.escape(str(c.get("reading", ""))),
            translation=html.escape(str(c.get("translation", ""))),
            example=html.escape(str(c.get("example", ""))),
        ) for c in vocab)
        return f'<div class="card"><h2>Vocabulary</h2><div class="flip-grid">{cards}</div></div>'

    def _render_grammar(self, card):
        drills = "".join(_DRILL.format(
            prompt=html.escape(str(d.get("prompt", ""))),
            answer=html.escape(str(d.get("answer", "")), quote=True),
        ) for d in card.get("drills", []))
        return _GRAMMAR_CARD.format(
            point=html.escape(str(card.get("point", ""))),
            explanation=html.escape(str(card.get("explanation", ""))),
            drills=drills,
        )

    def _render_evaluation(self, evaluation, dialogue, target, known,
                           level, audio_files):
        blocks = ['<div class="card"><h2>Evaluation</h2>']
        for i, item in enumerate(evaluation):
            kind = item.get("type")
            if kind == "multiple_choice":
                blocks.append(self._render_mc(item))
            elif kind == "fill_in_blank":
                blocks.append(self._render_blank(item))
            elif kind == "translation":
                blocks.append(self._render_translation(item, target))
            elif kind == "transformation":
                blocks.append(self._render_transformation(item))
            else:  # validator rejects unknown types; stay honest if it slips
                blocks.append(f'<p class="reading">Unsupported item type: '
                              f'{html.escape(str(kind))}</p>')
        listening = self._render_listening(dialogue, audio_files)
        if listening:
            blocks.append(listening)
        blocks.append("</div>")
        return "\n".join(blocks)

    def _render_mc(self, item):
        options = item.get("options") or []
        correct = item.get("correct_index")
        rendered = "".join(
            _MC_OPTION.format(
                index=i, correct=correct,
                text=html.escape(str(opt)),
            ) for i, opt in enumerate(options))
        return _MC_ITEM.format(
            question=html.escape(str(item.get("question", ""))),
            options=rendered,
        )

    def _render_blank(self, item):
        sentence = str(item.get("sentence_with_blank", ""))
        answer = str(item.get("answer", ""))
        before, _, after = sentence.partition(_BLANK_MARKER)
        return _BLANK_ITEM.format(
            before=html.escape(before),
            after=html.escape(after),
            answer=html.escape(answer, quote=True),
            answer_display=html.escape(answer),
        )

    def _render_translation(self, item, target):
        answer = str(item.get("answer", ""))
        return _TRANSLATION_ITEM.format(
            prompt=html.escape(str(item.get("prompt", ""))),
            target=html.escape(target),
            answer=html.escape(answer, quote=True),
            answer_display=html.escape(answer),
        )

    def _render_transformation(self, item):
        answer = str(item.get("answer", ""))
        return _TRANSFORMATION_ITEM.format(
            prompt=html.escape(str(item.get("prompt", ""))),
            answer=html.escape(answer, quote=True),
            answer_display=html.escape(answer),
        )

    def _render_listening(self, dialogue, audio_files):
        if not audio_files:
            return ""
        rows = []
        for i, seg in enumerate(dialogue):
            src = audio_files.get(f"listening-{i}",
                                  audio_files.get(f"dialogue-{i}"))
            if not src:
                continue
            rows.append(_LISTENING_ROW.format(
                src=html.escape(str(src)),
                answer=html.escape(str(seg.get("content", "")), quote=True),
            ))
        if not rows:
            return ""
        return ("<h2>Listening</h2><p class=\"reading\">Type exactly what "
                "you hear.</p>" + "".join(rows))


def render_lesson_pack_html(
    pack: dict[str, Any], *,
    audio_files: Optional[dict[str, str]] = None,
) -> str:
    """Contract: thin wrapper around LanguageLabRenderer.render()."""
    return LanguageLabRenderer().render(pack, audio_files=audio_files)
