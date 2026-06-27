import { useEffect, useState } from "react";

import { api } from "../api";
import type { ChatResponse } from "../types";

export function ChatPanel() {
  const [answer, setAnswer] = useState<ChatResponse | null>(null);
  const [status, setStatus] = useState("Checking local AI...");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void api.aiStatus().then((result) =>
      setStatus(
        result.available && result.model_installed
          ? `Ollama ${result.model} ready`
          : result.available
            ? `Ollama running · pull ${result.model}`
            : "Database answers active · Ollama service offline",
      ),
    );
  }, []);

  async function ask(formData: FormData) {
    setLoading(true);
    try {
      setAnswer(await api.chat(String(formData.get("question"))));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="chat-layout">
      <article className="panel chat-intro">
        <p className="eyebrow">Private finance assistant</p>
        <h2>Ask your database</h2>
        <p>
          Numeric answers are calculated from validated records. Local Ollama
          is used only for classification when explicitly enabled.
        </p>
        <span className="privacy-pill">{status}</span>
        <div className="prompt-list">
          <span>How much did I spend on groceries in May 2026?</span>
          <span>Show my total debt balance.</span>
          <span>What is my estimated net worth?</span>
          <span>How much income did I record this year?</span>
        </div>
      </article>
      <article className="panel">
        <form action={ask} className="chat-form">
          <label>
            Your question
            <textarea
              name="question"
              placeholder="Ask about spending, income, debt, or net worth..."
              required
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Calculating..." : "Ask Ledger Local"}
          </button>
        </form>
        {answer && (
          <div className="answer-card">
            <p className="eyebrow">Answer</p>
            <h3>{answer.answer}</h3>
            <p>{answer.calculation_basis}</p>
            <div className="answer-meta">
              <span>Confidence {Math.round(answer.confidence * 100)}%</span>
              <span>{answer.sources.length} source record(s)</span>
            </div>
            {answer.missing_data_warning && (
              <p className="warning-text">{answer.missing_data_warning}</p>
            )}
            {answer.sources.length > 0 && (
              <details>
                <summary>Source records</summary>
                <pre>{JSON.stringify(answer.sources, null, 2)}</pre>
              </details>
            )}
          </div>
        )}
      </article>
    </section>
  );
}
