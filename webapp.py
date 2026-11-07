"""Minimal demo page: stages, provenance chain, examiner chat and draft report.

    DATABASE_URL=sqlite:///demo.db python webapp.py        # http://127.0.0.1:8001
    CODEVIVA_USE_LLM=1 ...                                 # enable the model layer

Local demo only: no auth, binds to 127.0.0.1, synthetic data.
"""
from __future__ import annotations

import os
import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import explain
from artifacts import read_artifact, round_dir
from db_adapter import list_submissions
from examiner import InterviewTransport
from pipeline import RunContext, run_pipeline
from stages import DEFAULT_KB, build_stages, make_context_options

DB = os.environ.get("DATABASE_URL", "sqlite:///demo.db")
RUNS = Path(os.environ.get("CODEVIVA_RUNS", "runs"))
USE_OPENAI = "1" in (os.environ.get("CODEVIVA_USE_LLM"), os.environ.get("CODEVIVA_USE_OPENAI"))

app = FastAPI(title="CodeViva oral assessment demo")


class QueueTransport(InterviewTransport):
    """Bridges the blocking Examiner loop to HTTP polling."""

    def __init__(self) -> None:
        self.outbox: List[Dict[str, str]] = []
        self.inbox: "queue.Queue[Optional[str]]" = queue.Queue()
        self.done = False
        self.error = ""

    def send(self, text: str) -> None:
        self.outbox.append({"speaker": "examiner", "text": text})

    def receive(self) -> Optional[str]:
        try:
            answer = self.inbox.get(timeout=3600)  # long pauses are fine
        except queue.Empty:
            return None
        if answer is not None:
            self.outbox.append({"speaker": "student", "text": answer})
        return answer


SESSIONS: Dict[str, QueueTransport] = {}


def _sid(value: str) -> str:
    if not value.isdigit():
        raise HTTPException(400, "submission id must be numeric")
    return value


def _ctx(sid: str, **opts: Any) -> RunContext:
    return RunContext(submission_id=sid, round_no=1, run_dir=round_dir(RUNS, sid, 1), runs_root=RUNS, seed=sid,
                      options=make_context_options(db=DB, kb_dirs=DEFAULT_KB, use_openai=USE_OPENAI, **opts))


def _stage_rows(run_dir: Path) -> List[Dict[str, Any]]:
    rows = []
    for stage in build_stages():
        path = run_dir / stage.filename
        if path.exists():
            meta = read_artifact(path)["meta"]
            rows.append({"id": stage.id, "name": stage.name, "summary": meta["summary"], "model": meta["model"],
                         "in": meta["count_in"], "out": meta["count_out"]})
        else:
            rows.append({"id": stage.id, "name": stage.name, "summary": "not run", "model": None, "in": "", "out": ""})
    return rows


@app.get("/api/submissions")
def submissions() -> List[Dict[str, Any]]:
    return list_submissions(DB)


class PlanReq(BaseModel):
    submission: str


@app.post("/api/plan")
def plan(req: PlanReq) -> Dict[str, Any]:
    sid = _sid(req.submission)
    ctx = _ctx(sid)
    try:
        run_pipeline(build_stages(), ctx, stop_after="5")
    except Exception as exc:  # surface a clear message to the page
        raise HTTPException(400, str(exc))
    run = explain.load_run(ctx.run_dir)
    qs = run["5"]["data"]["questions"]
    return {"stages": _stage_rows(ctx.run_dir), "mode": run["5"]["data"]["mode"],
            "questions": [{"id": q["id"], "dimension": q["dimension"], "text": q["text"],
                           "citations": [f"{c['file']}:{c['line']}" if c.get("line") else
                                         f"commit {str(c.get('commit'))[:7]}" for c in q["citations"]],
                           "explain": explain.explain(run, q["id"])} for q in qs],
            "not_triggered": run["5"]["data"]["not_triggered"]}


@app.post("/api/interview")
def start_interview(req: PlanReq) -> Dict[str, str]:
    sid = _sid(req.submission)
    if not (round_dir(RUNS, sid, 1) / "stage5_plan.json").exists():
        raise HTTPException(400, "build the plan first")
    transport = QueueTransport()
    session = uuid.uuid4().hex[:12]
    SESSIONS[session] = transport

    def worker() -> None:
        try:
            run_pipeline(build_stages(), _ctx(sid, transport=transport), from_stage="6", stop_after="7")
        except Exception as exc:
            transport.error = str(exc)
        finally:
            transport.done = True

    threading.Thread(target=worker, daemon=True).start()
    return {"session": session}


@app.get("/api/interview/{session}")
def poll(session: str, after: int = 0) -> Dict[str, Any]:
    t = SESSIONS.get(session)
    if t is None:
        raise HTTPException(404, "unknown session")
    return {"messages": t.outbox[after:], "done": t.done, "error": t.error}


class Answer(BaseModel):
    text: str


@app.post("/api/interview/{session}/answer")
def answer(session: str, body: Answer) -> Dict[str, bool]:
    t = SESSIONS.get(session)
    if t is None or t.done:
        raise HTTPException(404, "no active session")
    t.inbox.put(body.text[:5000])
    return {"ok": True}


@app.get("/api/report/{submission}")
def report(submission: str) -> Dict[str, Any]:
    run_dir = round_dir(RUNS, _sid(submission), 1)
    if not (run_dir / "report.json").exists():
        raise HTTPException(404, "no report yet")
    return {"report": read_artifact(run_dir / "report.json")["data"], "stages": _stage_rows(run_dir),
            "markdown": (run_dir / "report.md").read_text(encoding="utf-8")}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>CodeViva Examiner</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--muted:#6e6e73;--line:#e3e3e0;--accent:#2f6fdf;--warn:#b25000;--ok:#1d7a46}
@media (prefers-color-scheme:dark){:root{--bg:#141415;--card:#1d1d1f;--ink:#f2f2f2;--muted:#a1a1a6;--line:#333;--accent:#6ea0ff;--warn:#ff9f43;--ok:#4cd38a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 10px}
.sub{color:var(--muted);margin:0 0 20px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:800px){.grid{grid-template-columns:1fr}}
button,select{font:inherit;padding:6px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}button:disabled{opacity:.5;cursor:default}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.q{border-top:1px solid var(--line);padding:10px 0}.q:first-child{border-top:0}.tag{font-size:12px;color:var(--muted)}
pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:10px;font-size:12px;overflow-x:auto}
#chat{height:380px;overflow-y:auto;display:flex;flex-direction:column;gap:8px;padding:4px}
.msg{padding:8px 10px;border-radius:8px;max-width:88%}.examiner{background:var(--bg);border:1px solid var(--line)}
.student{background:var(--accent);color:#fff;align-self:flex-end}form{display:flex;gap:8px;margin-top:10px}
input[type=text]{flex:1;font:inherit;padding:7px 10px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink)}
.flag{color:var(--warn);font-weight:600}.okc{color:var(--ok);font-weight:600}blockquote{margin:4px 0;padding-left:10px;border-left:3px solid var(--line);color:var(--muted)}
.banner{background:var(--bg);border:1px solid var(--warn);border-radius:8px;padding:10px;font-size:13px}
</style></head><body><main>
<h1>CodeViva oral assessment</h1><p class="sub">Code-grounded interview: synthetic demo data, round 1. Grades are AI-drafted and need review by a named academic.</p>
<div class="card"><label>Submission <select id="sub"></select></label> <button class="primary" id="planBtn">Build plan</button> <span id="mode" class="tag"></span></div>
<div class="grid"><div class="card"><h2>Pipeline stages</h2><table id="stages"></table></div>
<div class="card"><h2>Questions and evidence trail</h2><div id="qs" class="tag">Build a plan to see questions.</div></div></div>
<div class="grid"><div class="card"><h2>Interview (text)</h2><div id="chat"></div>
<form id="f"><input type="text" id="ans" placeholder="Type your answer. 'repeat' or 'pass' work too." autocomplete="off" disabled>
<button id="send" disabled>Send</button></form><p><button id="startBtn" disabled>Start interview</button></p></div>
<div class="card"><h2>Draft report</h2><div id="report" class="tag">Appears after the interview.</div></div></div>
</main><script>
const $=s=>document.querySelector(s);let session=null,seen=0,timer=null;
function el(t,c,txt){const e=document.createElement(t);if(c)e.className=c;if(txt!==undefined)e.textContent=txt;return e}
async function api(p,o){const r=await fetch(p,o);const j=await r.json();if(!r.ok)throw new Error(j.detail||r.statusText);return j}
function post(p,b){return api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})}
function stages(rows){const t=$('#stages');t.replaceChildren();const h=el('tr');['#','Stage','Summary','In→Out'].forEach(x=>h.append(el('th','',x)));t.append(h);
 rows.forEach(r=>{const tr=el('tr');[r.id,r.name+(r.model?' ('+r.model+')':''),r.summary,r.in===''?'':r.in+'→'+r.out].forEach(x=>tr.append(el('td','',String(x))));t.append(tr)})}
async function load(){const s=await api('/api/submissions');s.forEach(x=>{const o=el('option','', 'Submission '+x.id+' · '+x.assignment);o.value=x.id;$('#sub').append(o)})}
$('#planBtn').onclick=async()=>{try{const p=await post('/api/plan',{submission:$('#sub').value});stages(p.stages);$('#mode').textContent='mode: '+p.mode;
 const qs=$('#qs');qs.replaceChildren();qs.className='';p.questions.forEach(q=>{const d=el('div','q');d.append(el('div','tag',q.id+' · '+q.dimension+' · '+q.citations.join(', ')));
 d.append(el('div','',q.text));const det=el('details');det.append(el('summary','tag','Why this question?'));det.append(el('pre','',q.explain));d.append(det);qs.append(d)});
 if(p.not_triggered.length){qs.append(el('div','tag','Not triggered: '+p.not_triggered.map(x=>x.rule_id).join(', ')))}
 $('#startBtn').disabled=false}catch(e){alert(e.message)}};
$('#startBtn').onclick=async()=>{const r=await post('/api/interview',{submission:$('#sub').value});session=r.session;seen=0;$('#chat').replaceChildren();
 $('#ans').disabled=false;$('#send').disabled=false;$('#startBtn').disabled=true;timer=setInterval(poll,700)};
async function poll(){const r=await api('/api/interview/'+session+'?after='+seen);r.messages.forEach(m=>{$('#chat').append(el('div','msg '+m.speaker,m.text))});seen+=r.messages.length;
 if(r.messages.length)$('#chat').scrollTop=1e9;if(r.done){clearInterval(timer);$('#ans').disabled=true;$('#send').disabled=true;$('#startBtn').disabled=false;
 if(r.error)alert(r.error);else showReport()}}
$('#f').onsubmit=async e=>{e.preventDefault();const t=$('#ans').value.trim();if(!t)return;$('#ans').value='';await post('/api/interview/'+session+'/answer',{text:t})};
async function showReport(){const r=await api('/api/report/'+$('#sub').value);stages(r.stages);const rep=r.report,box=$('#report');box.replaceChildren();box.className='';
 box.append(el('div','banner',rep.disclaimer));box.append(el('p',rep.needs_human_review?'flag':'okc',rep.needs_human_review?'Needs human review':'No review flags'));
 rep.review_reasons.forEach(x=>box.append(el('div','tag','• '+x)));box.append(el('p','','Draft total: '+rep.total+' / '+rep.max_total+' · grader: '+rep.grader));
 rep.dimensions.forEach(d=>{const s=el('div','q');s.append(el('div','',d.label+': '+(d.score===null?'not scored':d.score)+'  (passes '+d.pass_scores.join(' / ')+')'));
 d.quotes.forEach(q=>s.append(el('blockquote','','"'+q+'"')));box.append(s)})}
load();
</script></body></html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8001")))
