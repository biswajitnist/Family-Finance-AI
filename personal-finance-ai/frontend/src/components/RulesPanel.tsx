import { useEffect, useState } from "react";

import { api } from "../api";
import { confirmAction } from "../confirmAction";
import type { Category, ResourceRecord } from "../types";

interface RulesPanelProps {
  categories: Category[];
  refreshKey?: number;
}

export function RulesPanel({ categories, refreshKey }: RulesPanelProps) {
  const [rules, setRules] = useState<ResourceRecord[]>([]);
  const [actionType, setActionType] = useState("category");
  const [message, setMessage] = useState("");
  const [editingRule, setEditingRule] = useState<ResourceRecord | null>(null);

  async function load() {
    try {
      setRules(await api.resources("rules"));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load rules");
    }
  }

  useEffect(() => {
    void load();
  }, [refreshKey]);

  async function save(formData: FormData) {
    try {
      const payload = {
        name: formData.get("name"),
        condition_type: formData.get("condition_type"),
        condition_value: formData.get("condition_value"),
        action_type: actionType,
        action_value: formData.get("action_value"),
        priority: Number(editingRule?.priority ?? 100),
        is_active: Boolean(editingRule?.is_active ?? true),
      };
      if (editingRule) {
        await api.updateResource("rules", Number(editingRule.id), payload);
        setMessage("Rule updated.");
      } else {
        await api.createResource("rules", payload);
        setMessage("Rule saved. It will run on new imported rows.");
      }
      setEditingRule(null);
      setActionType("category");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save rule");
    }
  }

  async function remove(id: number) {
    try {
      const confirmed = await confirmAction({
        title: "Delete rule?",
        message: "Delete this automation rule? New imports will no longer use it.",
        confirmLabel: "Delete rule",
      });
      if (!confirmed) return;
      await api.deleteResource("rules", id);
      setMessage("Rule deleted.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not delete rule");
    }
  }

  async function applyAll() {
    try {
      const result = await api.applyRules();
      setMessage(
        `${result.updated} pending transaction(s) matched saved rules or merchant history.`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not apply rules");
    }
  }

  return (
    <section className="module-layout rules-layout">
      <article className="panel">
        <div className="panel-heading rules-heading">
          <div>
            <p className="eyebrow">Finance module</p>
            <h2>Rules</h2>
            <p className="section-copy">
              Automatically categorize familiar merchants and descriptions
              during statement imports.
            </p>
          </div>
          <button className="secondary-button" onClick={applyAll}>
            Apply all rules
          </button>
        </div>

        <form
          action={save}
          className="rule-form"
          key={editingRule ? `edit-${editingRule.id}` : "new-rule"}
        >
          <div className="rule-step">
            <span className="rule-step-number">1</span>
            <div>
              <strong>Name this rule</strong>
              <small>Use a name that explains what the rule does.</small>
            </div>
          </div>
          <label className="rule-field rule-field-wide">
            <span>Rule name</span>
            <input
              name="name"
              defaultValue={String(editingRule?.name ?? "")}
              placeholder="Example: REWE groceries"
              required
            />
          </label>

          <div className="rule-step">
            <span className="rule-step-number">2</span>
            <div>
              <strong>When this happens</strong>
              <small>Choose where Ledger Local should look for matching text.</small>
            </div>
          </div>
          <div className="rule-field-grid">
            <label className="rule-field">
              <span>Look in</span>
              <select
                name="condition_type"
                defaultValue={String(editingRule?.condition_type ?? "vendor")}
                required
              >
                <option value="vendor">Merchant name</option>
                <option value="keyword">Description or reference</option>
              </select>
            </label>
            <label className="rule-field">
              <span>Text contains</span>
              <input
                name="condition_value"
                defaultValue={String(editingRule?.condition_value ?? "")}
                placeholder="Example: REWE"
                required
              />
            </label>
          </div>

          <div className="rule-step">
            <span className="rule-step-number">3</span>
            <div>
              <strong>Do this automatically</strong>
              <small>Select a saved category or correct the transaction type.</small>
            </div>
          </div>
          <div className="rule-field-grid">
            <label className="rule-field">
              <span>Action</span>
              <select
                name="action_type"
                value={actionType}
                onChange={(event) => setActionType(event.target.value)}
              >
                <option value="category">Set category</option>
                <option value="transaction_type">
                  Set income or expense type
                </option>
              </select>
            </label>
            <label className="rule-field">
              <span>
                {actionType === "category" ? "Choose category" : "Choose type"}
              </span>
              <select
                key={actionType}
                name="action_value"
                defaultValue={String(editingRule?.action_value ?? "")}
                required
              >
                <option value="" disabled>
                  {actionType === "category"
                    ? "Select an existing category"
                    : "Select income or expense"}
                </option>
                {actionType === "category" ? (
                  categories.map((category) => (
                    <option key={category.id} value={category.name}>
                      {category.name} ({category.type})
                    </option>
                  ))
                ) : (
                  <>
                    <option value="credit">Income (credit)</option>
                    <option value="debit">Expense (debit)</option>
                  </>
                )}
              </select>
            </label>
          </div>

          {!categories.length && actionType === "category" && (
            <p className="rule-warning">
              No categories are available. Create a category before saving this
              rule.
            </p>
          )}
          <div className="resource-form-actions">
            <button
              className="rule-submit"
              disabled={actionType === "category" && !categories.length}
              type="submit"
            >
              {editingRule ? "Update rule" : "Add rule"}
            </button>
            {editingRule && (
              <button
                className="secondary-button"
                onClick={() => {
                  setEditingRule(null);
                  setActionType("category");
                  setMessage("Edit cancelled.");
                }}
                type="button"
              >
                Cancel
              </button>
            )}
          </div>
          {message && <p className="form-message rule-message">{message}</p>}
        </form>
      </article>

      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Automatic classification</p>
            <h2>Saved rules</h2>
            <p className="section-copy">
              Rules are checked in order before local AI classification.
            </p>
          </div>
          <span className="count-pill">{rules.length}</span>
        </div>
        {!rules.length ? (
          <div className="rule-empty-state">
            <strong>No rules yet</strong>
            <p>Add your first rule for a merchant you categorize regularly.</p>
          </div>
        ) : (
          <div className="rule-list">
            {rules.map((rule) => (
              <article className="saved-rule" key={String(rule.id)}>
                <div>
                  <strong>{String(rule.name)}</strong>
                  <p>
                    {rule.condition_type === "vendor"
                      ? "Merchant contains"
                      : "Description contains"}{" "}
                    <b>{String(rule.condition_value)}</b>
                  </p>
                </div>
                <div className="saved-rule-result">
                  <span>
                    {rule.action_type === "category" ? "Category" : "Type"}
                  </span>
                  <strong>{String(rule.action_value)}</strong>
                </div>
                <div className="saved-rule-actions">
                  <button
                    className="secondary-button"
                    onClick={() => {
                      setEditingRule(rule);
                      setActionType(String(rule.action_type ?? "category"));
                      setMessage(`Editing ${String(rule.name)}.`);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                    type="button"
                  >
                    Edit
                  </button>
                  <button
                    className="secondary-button danger-outline"
                    onClick={() => remove(Number(rule.id))}
                    type="button"
                  >
                    Delete
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </article>
    </section>
  );
}
