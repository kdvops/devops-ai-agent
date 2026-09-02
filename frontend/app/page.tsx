"use client";

import { FormEvent, useState } from "react";

type Message = { role: "user" | "assistant"; content: string };
type ChatResult = { reply: string; status?: string; proposal_id?: string; tool?: string; arguments?: unknown };

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([{ role: "assistant", content: "Soy tu agente DevOps. Puedo consultar Kubernetes y proponer cambios controlados." }]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<ChatResult | null>(null);
  const [busy, setBusy] = useState(false);
  const api = process.env.NEXT_PUBLIC_API_URL ?? "/api";

  async function send(event: FormEvent) {
    event.preventDefault();
    const value = input.trim();
    if (!value || busy) return;
    setInput(""); setMessages((current) => [...current, { role: "user", content: value }]); setBusy(true);
    try {
      const response = await fetch(`${api}/chat`, { method: "POST", headers: { "content-type": "application/json", "x-user": "operator-local" }, body: JSON.stringify({ message: value, history: messages }) });
      const result: ChatResult = await response.json();
      if (!response.ok) throw new Error(result.reply || "No se pudo completar la solicitud.");
      setMessages((current) => [...current, { role: "assistant", content: result.reply }]);
      if (result.status === "WAITING_CONFIRMATION") setPending(result);
    } catch (error) { setMessages((current) => [...current, { role: "assistant", content: error instanceof Error ? error.message : "Error inesperado." }]); }
    finally { setBusy(false); }
  }

  async function confirm(approved: boolean) {
    if (!pending?.proposal_id) return;
    const response = await fetch(`${api}/confirmations`, { method: "POST", headers: { "content-type": "application/json", "x-user": "operator-local" }, body: JSON.stringify({ proposal_id: pending.proposal_id, approved }) });
    const result = await response.json();
    setMessages((current) => [...current, { role: "assistant", content: approved ? `Acción completada: ${JSON.stringify(result.result ?? result)}` : "Acción cancelada." }]); setPending(null);
  }

  return <main><header><div><p className="eyebrow">CONTROL PLANE / DEVOPS</p><h1>DevOps AI Agent</h1><p className="muted">Tu copiloto para entender y operar Kubernetes con aprobación humana.</p></div><span className="status">● conectado</span></header><section className="shell"><div className="conversation">{messages.map((item, index) => <div className={`message ${item.role}`} key={`${item.role}-${index}`}>{item.content}</div>)}{pending && <div className="approval"><b>Confirmación requerida</b><p>{pending.tool}</p><code>{JSON.stringify(pending.arguments, null, 2)}</code><div><button onClick={() => confirm(true)}>Aprobar</button><button className="quiet" onClick={() => confirm(false)}>Cancelar</button></div></div>}</div><form onSubmit={send}><input value={input} onChange={(event) => setInput(event.target.value)} placeholder={busy ? "El agente está trabajando…" : "Pregunta por tu clúster…"} disabled={busy} /><button disabled={busy}>Enviar</button></form></section></main>;
}
