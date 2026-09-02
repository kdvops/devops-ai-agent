"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

type Role = "user" | "assistant";
type ImageAttachment = { name: string; type: string; dataUrl: string };
type Message = { role: Role; content: string; time: string; image?: ImageAttachment };
type ChatResult = { reply?: string; status?: string; proposal_id?: string; tool?: string; arguments?: unknown; result?: unknown; detail?: string };

const suggestions = [
  { label: "Estado del cluster", prompt: "Consulta el estado de los nodos del cluster." },
  { label: "Pods con problemas", prompt: "Lista los pods con problemas en el namespace devops-ai." },
  { label: "Logs recientes", prompt: "Revisa los logs recientes del backend en devops-ai." },
];

function now() {
  return new Intl.DateTimeFormat("es-DO", { hour: "2-digit", minute: "2-digit" }).format(new Date());
}

function Icon({ name }: { name: "grid" | "pulse" | "shield" | "arrow" | "spark" | "send" | "check" | "x" }) {
  const paths = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    pulse: <path d="M3 12h4l2.2-6 4.2 12 2.2-6H21" />,
    shield: <><path d="M12 3 20 6v5c0 5-3.4 8.2-8 10-4.6-1.8-8-5-8-10V6l8-3Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    arrow: <><path d="M5 12h13" /><path d="m13 6 6 6-6 6" /></>,
    spark: <><path d="m12 3-1.4 5.6L5 10l5.6 1.4L12 17l1.4-5.6L19 10l-5.6-1.4L12 3Z" /><path d="m19 16-.6 2.4L16 19l2.4.6L19 22l.6-2.4L22 19l-2.4-.6L19 16Z" /></>,
    send: <><path d="m22 2-7 20-4-9-9-4Z" /><path d="M22 2 11 13" /></>,
    check: <path d="m5 12 4.5 4.5L19 7" />,
    x: <><path d="m6 6 12 12" /><path d="m18 6-12 12" /></>,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24">{paths[name]}</svg>;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([{ role: "assistant", content: "Estoy listo para ayudarte a entender y operar tu infraestructura. Puedo consultar Kubernetes, inspeccionar repositorios y proponer cambios controlados.", time: now() }]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<ChatResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const [selectedImage, setSelectedImage] = useState<ImageAttachment | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const api = process.env.NEXT_PUBLIC_API_URL ?? "/api";

  useEffect(() => {
    fetch(`${api}/health`).then((response) => setOnline(response.ok)).catch(() => setOnline(false));
  }, [api]);

  function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.type)) {
      setMessages((current) => [...current, { role: "assistant", content: "Formato no compatible. Adjunta JPEG, PNG, WebP o GIF.", time: now() }]);
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setMessages((current) => [...current, { role: "assistant", content: "La imagen supera el límite de 5 MB.", time: now() }]);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setSelectedImage({ name: file.name, type: file.type, dataUrl: String(reader.result) });
    reader.readAsDataURL(file);
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const value = input.trim();
    if (!value || busy) return;
    setInput("");
    setMessages((current) => [...current, { role: "user", content: value, time: now(), image: selectedImage ?? undefined }]);
    setBusy(true);
    try {
      const response = await fetch(`${api}/chat`, { method: "POST", headers: { "content-type": "application/json", "x-user": "operator-local" }, body: JSON.stringify({ message: value, images: selectedImage ? [selectedImage.dataUrl] : [], history: messages.map(({ role, content }) => ({ role, content })) }) });
      const result: ChatResult = await response.json();
      if (!response.ok) throw new Error(result.detail || result.reply || "No se pudo completar la solicitud.");
      setMessages((current) => [...current, { role: "assistant", content: result.reply || "La operación fue procesada.", time: now() }]);
      if (result.status === "WAITING_CONFIRMATION") setPending(result);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", content: error instanceof Error ? error.message : "Error inesperado.", time: now() }]);
    } finally { setSelectedImage(null); setBusy(false); }
  }

  async function confirm(approved: boolean) {
    if (!pending?.proposal_id) return;
    setBusy(true);
    try {
      const response = await fetch(`${api}/confirmations`, { method: "POST", headers: { "content-type": "application/json", "x-user": "operator-local" }, body: JSON.stringify({ proposal_id: pending.proposal_id, approved }) });
      const result: ChatResult = await response.json();
      if (!response.ok) throw new Error(result.detail || "No se pudo resolver la propuesta.");
      setMessages((current) => [...current, { role: "assistant", content: approved ? `Acción completada.\n${JSON.stringify(result.result ?? result, null, 2)}` : "Acción cancelada. No se modificó el estado.", time: now() }]);
      setPending(null);
    } catch (error) {
      setMessages((current) => [...current, { role: "assistant", content: error instanceof Error ? error.message : "No se pudo resolver la propuesta.", time: now() }]);
    } finally { setBusy(false); }
  }

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Icon name="spark" /></div><div><strong>DevOps AI</strong><span>control plane</span></div></div>
      <nav><a className="nav-item active"><Icon name="grid" /> Conversación</a><a className="nav-item"><Icon name="pulse" /> Operaciones</a><a className="nav-item"><Icon name="shield" /> Auditoría <small>próximamente</small></a></nav>
      <div className="sidebar-bottom"><div className="mini-card"><span className="mini-label">ENTORNO ACTIVO</span><strong>K3s · desarrollo</strong><span className="mini-status"><i /> Conectado</span></div><div className="sidebar-foot"><span className="avatar">OL</span><span>operator-local</span><span className="dots">•••</span></div></div>
    </aside>
    <section className="workspace">
      <header className="topbar"><div><p className="breadcrumb">WORKSPACE <span>/</span> ASISTENTE</p><h1>Centro de operaciones</h1></div><div className={`connection ${online === false ? "offline" : ""}`}><i /> {online === null ? "verificando" : online ? "sistema operativo" : "sin conexión"}</div></header>
      <div className="content-grid">
        <section className="chat-panel">
          <div className="panel-heading"><div><span className="section-kicker">ASISTENTE INTELIGENTE</span><h2>¿Qué quieres revisar?</h2></div><span className="secure-pill"><Icon name="shield" /> acciones protegidas</span></div>
          <div className="messages" aria-live="polite">{messages.map((item, index) => <div className={`message-row ${item.role}`} key={`${item.role}-${index}`}><div className="message-avatar">{item.role === "assistant" ? <Icon name="spark" /> : "OL"}</div><div className="message-wrap"><div className="message-meta"><strong>{item.role === "assistant" ? "DevOps AI" : "Tú"}</strong><time>{item.time}</time></div>{item.image && <img className="message-image" src={item.image.dataUrl} alt={`Adjunto ${item.image.name}`} />}{item.content && <div className="message">{item.content}</div>}</div></div>)}{busy && <div className="message-row assistant"><div className="message-avatar"><Icon name="spark" /></div><div className="message-wrap"><div className="message-meta"><strong>DevOps AI</strong><time>ahora</time></div><div className="message typing"><i /><i /><i /></div></div></div>}{pending && <div className="approval-card"><div className="approval-top"><span className="approval-icon"><Icon name="shield" /></span><div><span className="section-kicker">REVISIÓN HUMANA</span><h3>Confirmación requerida</h3></div><span className="pending-tag">pendiente</span></div><p>El agente propone ejecutar una operación que modificará el estado del sistema.</p><div className="proposal-code"><span>TOOL</span><strong>{pending.tool}</strong><code>{JSON.stringify(pending.arguments, null, 2)}</code></div><div className="approval-actions"><button className="approve" onClick={() => confirm(true)} disabled={busy}><Icon name="check" /> Aprobar operación</button><button className="reject" onClick={() => confirm(false)} disabled={busy}><Icon name="x" /> Cancelar</button></div></div>}</div>
          <div className="suggestions">{suggestions.map((item) => <button key={item.label} onClick={() => setInput(item.prompt)}>{item.label}<Icon name="arrow" /></button>)}</div>
          {selectedImage && <div className="attachment-preview"><img src={selectedImage.dataUrl} alt="Vista previa del adjunto" /><span>{selectedImage.name}</span><button type="button" onClick={() => setSelectedImage(null)} aria-label="Quitar imagen"><Icon name="x" /></button></div>}
          <form className="composer" onSubmit={send}><input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={chooseImage} hidden /><button type="button" className="attach-button" onClick={() => fileInput.current?.click()} disabled={busy} aria-label="Adjuntar imagen">+</button><div className="composer-input"><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder={busy ? "El agente está trabajando…" : "Describe una consulta o tarea…"} disabled={busy} rows={1} /><span>ENTER ↵</span></div><button className="send-button" aria-label="Enviar mensaje" disabled={busy || (!input.trim() && !selectedImage)}><Icon name="send" /></button></form>
          <p className="composer-note"><Icon name="shield" /> Las operaciones de cambio siempre requieren tu aprobación explícita.</p>
        </section>
        <aside className="insights"><div className="insight-card accent-card"><div className="card-top"><span className="card-icon"><Icon name="pulse" /></span><span className="live-dot">● LIVE</span></div><span className="section-kicker">ESTADO DEL SISTEMA</span><h3>Todo bajo control</h3><p>El agente está listo para consultar recursos y ayudarte con tus operaciones.</p><div className="metric"><strong>{online ? "Operativo" : online === false ? "Revisar conexión" : "Verificando"}</strong><span>API del agente</span></div></div><div className="insight-card"><div className="card-top"><span className="section-kicker">CAPACIDADES</span><span className="cap-count">05</span></div><ul className="capabilities"><li><i className="green" /> Consultar Kubernetes</li><li><i className="green" /> Inspeccionar logs</li><li><i className="green" /> Trabajar con Git</li><li><i className="yellow" /> Proponer cambios</li><li><i className="yellow" /> Requiere aprobación</li></ul></div><div className="tip-card"><span className="tip-mark"><Icon name="spark" /></span><div><strong>Consejo rápido</strong><p>Sé específico con el namespace, el workload o el repositorio que quieres revisar.</p></div></div></aside>
      </div>
      <footer><span>DevOps AI Agent <b>v0.2</b></span><span>OpenAI Agents SDK <i /> Kubernetes ready</span></footer>
    </section>
  </main>;
}
