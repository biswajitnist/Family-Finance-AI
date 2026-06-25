import { createRoot } from "react-dom/client";

type ConfirmTone = "danger" | "default";

interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
}

export function confirmAction({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
}: ConfirmOptions): Promise<boolean> {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);

  return new Promise((resolve) => {
    function close(result: boolean) {
      root.unmount();
      host.remove();
      resolve(result);
    }

    root.render(
      <div
        className="confirm-modal-backdrop"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) close(false);
        }}
      >
        <article className={`confirm-modal ${tone}`} role="alertdialog" aria-modal="true">
          <div>
            <p className="eyebrow">Confirm action</p>
            <h2>{title}</h2>
            <p>{message}</p>
          </div>
          <footer>
            <button
              className="secondary-button"
              onClick={() => close(false)}
              type="button"
            >
              {cancelLabel}
            </button>
            <button
              className="confirm-modal-primary"
              onClick={() => close(true)}
              type="button"
            >
              {confirmLabel}
            </button>
          </footer>
        </article>
      </div>,
    );
  });
}
