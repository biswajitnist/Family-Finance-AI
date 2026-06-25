import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { HelpAgentResponse } from "../types";

type Message =
  | { role: "user"; text: string }
  | { role: "agent"; response: HelpAgentResponse }
  | { role: "error"; text: string };

const STARTERS = [
  "How do I review an uploaded statement?",
  "How much did I spend this month?",
  "What is in my February statement?",
  "Generate a monthly PDF report.",
];

export function HelpAgent() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function ask(text: string) {
    const question = text.trim();
    if (!question || loading) return;
    setMessages((items) => [...items, { role: "user", text: question }]);
    setLoading(true);
    try {
      const response = await api.helpAgent(question);
      setMessages((items) => [...items, { role: "agent", response }]);
    } catch (error) {
      setMessages((items) => [
        ...items,
        {
          role: "error",
          text: error instanceof Error ? error.message : "Help Agent failed",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function submit(formData: FormData) {
    const message = String(formData.get("message") ?? "");
    const form = document.querySelector<HTMLFormElement>(".help-agent-form");
    form?.reset();
    await ask(message);
  }

  return (
    <>
      <button
        className="help-agent-button"
        aria-expanded={open}
        aria-controls="help-agent-panel"
        onClick={() => setOpen((value) => !value)}
      >
        <span>?</span>
        Help
      </button>
      {open && (
        <aside
          className="help-agent-panel"
          id="help-agent-panel"
          aria-label="Ledger Local Help Agent"
        >
          <header>
            <div>
              <strong>Help Agent</strong>
              <small>Local Ollama · private sources only</small>
            </div>
            <button
              aria-label="Close Help Agent"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
          </header>
          <div className="help-agent-messages">
            {!messages.length && (
              <div className="help-agent-welcome">
                <strong>How can I help?</strong>
                <p>
                  Ask about the app, validated finances, uploaded documents,
                  reports, or a problem you are seeing.
                </p>
                <div>
                  {STARTERS.map((starter) => (
                    <button key={starter} onClick={() => void ask(starter)}>
                      {starter}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((message, index) => {
              if (message.role === "user") {
                return (
                  <div className="help-message user" key={index}>
                    {message.text}
                  </div>
                );
              }
              if (message.role === "error") {
                return (
                  <div className="help-message error" key={index}>
                    {message.text}
                  </div>
                );
              }
              const { response } = message;
              return (
                <div className="help-message agent" key={index}>
                  <span className="intent-label">
                    {response.intent.replaceAll("_", " ")}
                  </span>
                  <p>{response.answer}</p>
                  {!!response.missing_data.length && (
                    <div className="help-missing">
                      <strong>Missing data</strong>
                      {response.missing_data.map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                    </div>
                  )}
                  <div className="source-basis">
                    <small>Source basis</small>
                    {response.source_basis.map((basis) => (
                      <span key={basis}>{basis}</span>
                    ))}
                  </div>
                  {response.report && (
                    <a
                      className="secondary-button"
                      href={api.absoluteApiUrl(response.report.download_url)}
                    >
                      Download {response.report.format.toUpperCase()} report
                    </a>
                  )}
                  {!!response.sources.length && (
                    <details>
                      <summary>{response.sources.length} local source(s)</summary>
                      <pre>{JSON.stringify(response.sources, null, 2)}</pre>
                    </details>
                  )}
                </div>
              );
            })}
            {loading && (
              <div className="help-message agent loading">
                Searching local sources...
              </div>
            )}
            <div ref={endRef} />
          </div>
          <form action={submit} className="help-agent-form">
            <label>
              <span className="sr-only">Ask Help Agent</span>
              <textarea
                name="message"
                placeholder="Ask Ledger Local..."
                rows={2}
                required
              />
            </label>
            <button type="submit" disabled={loading}>
              Send
            </button>
          </form>
        </aside>
      )}
    </>
  );
}
